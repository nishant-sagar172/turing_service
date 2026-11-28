"""Pure, India-first date arithmetic for voice agents (no I/O, no clock reads).

The agent reduces the caller's phrase to structured fields; this module does
the calendar maths and says whether the date is bookable under the country's
rules.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from app.schemas.dates import (
    DateInfo,
    DateOption,
    DateReason,
    DateResolveRequest,
    DateResolveResponse,
    WEEKDAYS,
)


@dataclass(frozen=True)
class CountryRule:
    utc_offset_minutes: int
    closed_weekdays: frozenset[int]  # Monday=0 .. Sunday=6
    min_lead_days: int
    max_days_ahead: int


COUNTRY_RULES: dict[str, CountryRule] = {
    "IN": CountryRule(
        utc_offset_minutes=330,
        closed_weekdays=frozenset({6}),
        min_lead_days=1,
        max_days_ahead=366,
    ),
}

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_YEARS_TO_SEARCH = 5
_MONTHS_TO_SCAN = 12
_CANDIDATE_COUNT = 3
_WEEK_OFFSETS = {"this_week": 0, "next_week": 1, "week_after_next": 2}
_MONTH_START_DAYS = (1, 7)
_MONTH_MIDDLE_DAYS = (11, 20)
_MONTH_END_LENGTH = 7  # "end of the month" = its last 7 days


def _info(d: date) -> DateInfo:
    weekday = WEEKDAYS[d.weekday()].capitalize()
    spoken = f"{weekday}, {d.day} {_MONTH_NAMES[d.month - 1]} {d.year}"
    return DateInfo(date=d, weekday=weekday, spoken=spoken)


def _option(d: date, today: date, rule: CountryRule) -> DateOption:
    return DateOption(**_info(d).model_dump(), allowed=_reason(d, today, rule) is None)


def _is_open(d: date, rule: CountryRule) -> bool:
    return d.weekday() not in rule.closed_weekdays


def _reason(d: date, today: date, rule: CountryRule) -> DateReason | None:
    if d < today + timedelta(days=rule.min_lead_days):
        return "too_soon"
    if d > today + timedelta(days=rule.max_days_ahead):
        return "too_far"
    if not _is_open(d, rule):
        return "closed_day"
    return None


def _first_allowed(
    start: date, step: int, today: date, rule: CountryRule
) -> date | None:
    """Nearest allowed date from ``start`` (inclusive), moving ``step`` days."""
    earliest = today + timedelta(days=rule.min_lead_days)
    latest = today + timedelta(days=rule.max_days_ahead)
    current = start
    while earliest <= current <= latest:
        if _is_open(current, rule):
            return current
        current += timedelta(days=step)
    return None


def _alternatives(
    d: date, reason: DateReason, today: date, rule: CountryRule
) -> list[DateInfo]:
    earliest = today + timedelta(days=rule.min_lead_days)
    if reason == "too_soon":
        found = [_first_allowed(earliest, 1, today, rule)]
    elif reason == "closed_day":
        found = [
            _first_allowed(d - timedelta(days=1), -1, today, rule),
            _first_allowed(d + timedelta(days=1), 1, today, rule),
        ]
    else:
        found = []
    return [_info(x) for x in found if x is not None]


def _weekday_occurrences(today: date, weekday_index: int, count: int) -> list[date]:
    ahead = (weekday_index - today.weekday()) % 7 or 7
    first = today + timedelta(days=ahead)
    return [first + timedelta(days=7 * i) for i in range(count)]


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_day_of_month(
    today: date, day: int, month: int | None
) -> tuple[date | None, bool]:
    """Return (date, rolled_to_next_month); date is None when none exists."""
    if month is not None:
        for year in range(today.year, today.year + _YEARS_TO_SEARCH):
            found = _safe_date(year, month, day)
            if found is not None and found >= today:
                return found, False
        return None, False
    for offset in range(_MONTHS_TO_SCAN):
        index = today.month - 1 + offset
        found = _safe_date(today.year + index // 12, index % 12 + 1, day)
        if found is not None and found >= today:
            return found, (found.year, found.month) != (today.year, today.month)
    return None, False


def _nth_weekday(year: int, month: int, weekday_index: int, n: int) -> date | None:
    first_weekday = date(year, month, 1).weekday()
    day = 1 + (weekday_index - first_weekday) % 7 + 7 * (n - 1)
    return _safe_date(year, month, day)


def _months_from(today: date, month: int | None) -> Iterator[tuple[int, int]]:
    """(year, month) pairs from this month on, for a year ahead (or the named month)."""
    for offset in range(_MONTHS_TO_SCAN + 1):
        index = today.month - 1 + offset
        year, month_number = today.year + index // 12, index % 12 + 1
        if month is None or month == month_number:
            yield year, month_number


def _resolve_weekday_of_month(
    today: date, weekday_index: int, n: int, month: int | None
) -> tuple[date | None, bool]:
    """e.g. the third Friday of the month; date is None when none exists."""
    for year, month_number in _months_from(today, month):
        found = _nth_weekday(year, month_number, weekday_index, n)
        if found is not None and found >= today:
            return found, month is None and month_number != today.month
    return None, False


def _period_days(period: str, today: date, month: int | None) -> list[list[date]]:
    """Day windows for a period, soonest first (one window for a week)."""
    if period in _WEEK_OFFSETS:
        monday = today - timedelta(days=today.weekday())
        start = monday + timedelta(days=7 * _WEEK_OFFSETS[period])
        return [[start + timedelta(days=i) for i in range(7)]]
    windows = []
    for year, month_number in _months_from(today, month):
        last = calendar.monthrange(year, month_number)[1]
        if period == "month_start":
            first, end = _MONTH_START_DAYS
        elif period == "month_middle":
            first, end = _MONTH_MIDDLE_DAYS
        else:
            first, end = last - _MONTH_END_LENGTH + 1, last
        windows.append([date(year, month_number, d) for d in range(first, end + 1)])
    return windows


def _resolve_period(
    req: DateResolveRequest, today: date, rule: CountryRule
) -> DateResolveResponse:
    """A vague period: list the bookable days in it; the caller picks one."""
    assert req.period is not None
    options: list[DateOption] = []
    for window in _period_days(req.period, today, req.month):
        options = [
            _option(d, today, rule) for d in window if _reason(d, today, rule) is None
        ]
        if options:
            break
    if req.period == "month_end":
        options = options[-_CANDIDATE_COUNT:]
    elif req.period not in _WEEK_OFFSETS:
        options = options[:_CANDIDATE_COUNT]
    if options:
        listed = "; ".join(o.spoken for o in options)
        return DateResolveResponse(
            country=req.country,
            today=_info(today),
            allowed=True,
            candidates=options,
            message=f"Bookable days: {listed}. Ask which day the caller prefers.",
        )
    reason: DateReason = "too_soon" if req.period in _WEEK_OFFSETS else "invalid_date"
    alts = _alternatives(today, "too_soon", today, rule) if reason == "too_soon" else []
    return DateResolveResponse(
        country=req.country,
        today=_info(today),
        allowed=False,
        reason=reason,
        alternatives=alts,
        message=_message(None, reason, alts)
        if reason == "invalid_date"
        else "No bookable day left in that period. Ask the caller for another day.",
    )


def _message(
    resolved: DateInfo | None, reason: DateReason | None, alts: list[DateInfo]
) -> str:
    if resolved is None:
        return "That date does not exist. Ask for another date."
    spoken = resolved.spoken
    if reason is None:
        return f"{spoken} is available."
    if reason == "closed_day":
        offer = " or ".join(a.spoken for a in alts)
        suffix = f" Offer {offer}." if offer else ""
        return f"{spoken} is a closed day.{suffix}"
    if reason == "too_soon":
        earliest = f"; the earliest bookable day is {alts[0].spoken}" if alts else ""
        return f"{spoken} is too soon{earliest}."
    return f"{spoken} is too far ahead. Ask for a nearer date."


def _target_date(
    req: DateResolveRequest, today: date, rule: CountryRule
) -> tuple[date | None, bool, list[DateOption]]:
    """Return (resolved date, rolled_to_next_month, weekday candidates)."""
    if req.kind == "days_from_today":
        return today + timedelta(days=req.days or 0), False, []
    if req.kind == "days_from_date" and req.from_date is not None:
        return req.from_date + timedelta(days=req.days or 0), False, []
    if req.kind == "weekday" and req.weekday is not None:
        index = WEEKDAYS.index(req.weekday)
        count = max(req.occurrence, _CANDIDATE_COUNT)
        dates = _weekday_occurrences(today, index, count)
        candidates = [_option(d, today, rule) for d in dates[:_CANDIDATE_COUNT]]
        return dates[req.occurrence - 1], False, candidates
    if req.kind == "weekday_of_month" and req.weekday is not None:
        index = WEEKDAYS.index(req.weekday)
        found, rolled = _resolve_weekday_of_month(
            today, index, req.occurrence, req.month
        )
        return found, rolled, []
    if req.day is not None:
        found, rolled = _resolve_day_of_month(today, req.day, req.month)
        return found, rolled, []
    return None, False, []


def resolve_date(
    req: DateResolveRequest, now_utc: datetime, rule: CountryRule
) -> DateResolveResponse:
    today = (now_utc + timedelta(minutes=rule.utc_offset_minutes)).date()
    if req.kind == "period":
        return _resolve_period(req, today, rule)
    target, rolled, candidates = _target_date(req, today, rule)
    if target is None:
        return DateResolveResponse(
            country=req.country,
            today=_info(today),
            allowed=False,
            reason="invalid_date",
            message=_message(None, "invalid_date", []),
        )
    reason = _reason(target, today, rule)
    resolved = _info(target)
    alts = _alternatives(target, reason, today, rule) if reason else []
    return DateResolveResponse(
        country=req.country,
        today=_info(today),
        resolved=resolved,
        days_from_today=(target - today).days,
        allowed=reason is None,
        reason=reason,
        candidates=candidates,
        alternatives=alts,
        rolled_to_next_month=rolled,
        message=_message(resolved, reason, alts),
    )
