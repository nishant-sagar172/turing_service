"""Date resolver — pure functions only (plus a minimal router with no
middleware, database or environment): request normalisation, calendar maths,
bookability rules and the HTTP shape of POST /v1/dates/resolve.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.middleware import _OPEN_PATHS, AuthMiddleware
from app.routers import dates as dates_router
from app.schemas.dates import DateResolveRequest, DateResolveResponse
from app.services.date_resolver import COUNTRY_RULES, resolve_date

RULE = COUNTRY_RULES["IN"]
# Friday 2026-11-27 10:00 IST
NOW = datetime(2026, 11, 27, 4, 30, tzinfo=UTC)
SATURDAY_NOW = datetime(2026, 11, 28, 4, 30, tzinfo=UTC)


def _resolve(body: dict[str, Any], now: datetime = NOW) -> DateResolveResponse:
    return resolve_date(DateResolveRequest.model_validate(body), now, RULE)


def _ymd(info: Any) -> str:
    return info.date.isoformat()


# --- criteria 1-3: days_from_today -------------------------------------------


def test_days_from_today_five_is_allowed_wednesday() -> None:
    res = _resolve({"kind": "days_from_today", "days": 5})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-02"
    assert res.resolved.weekday == "Wednesday"
    assert res.allowed is True
    assert res.reason is None


def test_days_from_today_parso_lands_on_closed_sunday() -> None:
    res = _resolve({"kind": "days_from_today", "days": 2})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-29"
    assert res.resolved.weekday == "Sunday"
    assert res.allowed is False
    assert res.reason == "closed_day"
    assert [(_ymd(a), a.weekday) for a in res.alternatives] == [
        ("2026-11-28", "Saturday"),
        ("2026-11-30", "Monday"),
    ]


def test_days_from_today_tomorrow_is_allowed() -> None:
    res = _resolve({"kind": "days_from_today", "days": 1})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-28"
    assert res.resolved.weekday == "Saturday"
    assert res.allowed is True


def test_days_from_today_zero_is_too_soon_with_earliest_alternative() -> None:
    res = _resolve({"kind": "days_from_today", "days": 0})
    assert res.allowed is False
    assert res.reason == "too_soon"
    assert "2026-11-28" in [_ymd(a) for a in res.alternatives]


# --- criteria 4-5: weekday ---------------------------------------------------


@pytest.mark.parametrize(
    ("occurrence", "expected"),
    [(1, "2026-11-28"), (2, "2026-12-05"), (3, "2026-12-12")],
)
def test_weekday_saturday_occurrences(occurrence: int, expected: str) -> None:
    res = _resolve({"kind": "weekday", "weekday": "saturday", "occurrence": occurrence})
    assert res.resolved is not None
    assert _ymd(res.resolved) == expected
    assert [_ymd(c) for c in res.candidates] == [
        "2026-11-28",
        "2026-12-05",
        "2026-12-12",
    ]
    assert all(c.allowed for c in res.candidates)


def test_weekday_on_a_saturday_is_strictly_after_today() -> None:
    res = _resolve({"kind": "weekday", "weekday": "saturday"}, SATURDAY_NOW)
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-05"


def test_weekday_sunday_is_closed() -> None:
    res = _resolve({"kind": "weekday", "weekday": "sunday"})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-29"
    assert res.allowed is False
    assert res.reason == "closed_day"
    assert res.candidates[0].allowed is False


# --- criterion 6: day_of_month -----------------------------------------------


def test_day_of_month_passed_day_rolls_to_next_month() -> None:
    res = _resolve({"kind": "day_of_month", "day": 15})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-15"
    assert res.resolved.weekday == "Tuesday"
    assert res.rolled_to_next_month is True


def test_day_of_month_31_rolls_to_december() -> None:
    res = _resolve({"kind": "day_of_month", "day": 31})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-31"
    assert res.resolved.weekday == "Thursday"
    assert res.rolled_to_next_month is True


def test_day_of_month_feb_30_is_invalid_date() -> None:
    res = _resolve({"kind": "day_of_month", "day": 30, "month": 2})
    assert res.resolved is None
    assert res.allowed is False
    assert res.reason == "invalid_date"


def test_day_of_month_with_month_uses_next_year_when_passed() -> None:
    res = _resolve({"kind": "day_of_month", "day": 15, "month": 3})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2027-03-15"


def test_day_of_month_today_is_too_soon_and_not_rolled() -> None:
    res = _resolve({"kind": "day_of_month", "day": 27})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-27"
    assert res.reason == "too_soon"
    assert res.rolled_to_next_month is False


# --- criterion 7: days_from_date ---------------------------------------------


def test_days_from_date_adds_days_to_given_date() -> None:
    res = _resolve({"kind": "days_from_date", "from_date": "2026-12-03", "days": 5})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-08"
    assert res.resolved.weekday == "Tuesday"
    assert res.allowed is True


# --- criteria 8-9: country and timezone --------------------------------------


@pytest.mark.parametrize("country", [None, "", "  "])
def test_blank_country_defaults_to_india(country: str | None) -> None:
    body: dict[str, Any] = {"kind": "days_from_today", "days": 5}
    if country is not None:
        body["country"] = country
    assert _resolve(body).country == "IN"


def test_today_uses_ist_across_the_utc_date_boundary() -> None:
    now = datetime(2026, 11, 27, 23, 30, tzinfo=UTC)
    res = _resolve({"kind": "days_from_today", "days": 1}, now)
    assert _ymd(res.today) == "2026-11-28"
    assert res.today.weekday == "Saturday"


# --- criterion 10: input tolerance -------------------------------------------


def test_numbers_as_strings_are_accepted() -> None:
    res = _resolve({"kind": "days_from_today", "days": "5"})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-02"


@pytest.mark.parametrize("weekday", ["SAT", "Sat", "saturday", "SATURDAY", " sat "])
def test_weekday_spellings_are_normalised(weekday: str) -> None:
    res = _resolve({"kind": "weekday", "weekday": weekday})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-28"


@pytest.mark.parametrize("blank", ["", "none", "None", "null", "%(weekday)s"])
def test_blank_strings_and_placeholders_are_absent_for_unused_fields(
    blank: str,
) -> None:
    res = _resolve(
        {
            "kind": "days_from_today",
            "days": 5,
            "weekday": blank,
            "from_date": blank,
            "day": blank,
            "month": blank,
        }
    )
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-02"


def test_zero_day_and_month_are_absent_for_other_kinds() -> None:
    res = _resolve({"kind": "days_from_today", "days": 5, "day": 0, "month": 0})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-12-02"


@pytest.mark.parametrize("occurrence", [0, "", "0", None])
def test_occurrence_zero_or_blank_means_first(occurrence: Any) -> None:
    res = _resolve({"kind": "weekday", "weekday": "saturday", "occurrence": occurrence})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-28"


def test_extra_unknown_fields_are_ignored() -> None:
    res = _resolve({"kind": "days_from_today", "days": 5, "unexpected": "x"})
    assert res.allowed is True


def test_days_zero_is_a_real_value() -> None:
    res = _resolve({"kind": "days_from_today", "days": 0})
    assert res.reason == "too_soon"


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "next_blue_moon"},
        {"kind": "weekday", "weekday": "funday"},
        {"kind": "days_from_today", "days": 367},
        {"kind": "days_from_date", "days": 5},
        {"kind": "days_from_today"},
        {"kind": "weekday"},
        {"kind": "day_of_month"},
    ],
)
def test_invalid_requests_fail_validation(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DateResolveRequest.model_validate(body)


# --- criterion 11: route and open paths --------------------------------------


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(dates_router.router, prefix="/v1")
    return TestClient(app)


def test_route_returns_expected_shape() -> None:
    resp = _client().post(
        "/v1/dates/resolve", json={"kind": "days_from_today", "days": 5}
    )
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "today",
        "resolved",
        "allowed",
        "reason",
        "candidates",
        "alternatives",
        "message",
    ):
        assert key in data
    assert isinstance(data["allowed"], bool)
    assert isinstance(data["candidates"], list)
    assert isinstance(data["alternatives"], list)
    assert isinstance(data["message"], str)
    assert isinstance(data["today"], dict)


def test_route_rejects_unsupported_country() -> None:
    resp = _client().post(
        "/v1/dates/resolve",
        json={"kind": "days_from_today", "days": 5, "country": "US"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unsupported_country"
    assert "IN" in detail["supported"]


def test_route_rejects_invalid_body() -> None:
    resp = _client().post(
        "/v1/dates/resolve", json={"kind": "days_from_date", "days": 5}
    )
    assert resp.status_code == 422


def test_route_accepts_string_numbers_and_loose_weekday() -> None:
    resp = _client().post(
        "/v1/dates/resolve",
        json={"kind": "weekday", "weekday": "SAT", "occurrence": "2", "day": "0"},
    )
    assert resp.status_code == 200


def test_resolve_path_is_open_and_business_paths_are_not() -> None:
    assert "/v1/dates/resolve" in _OPEN_PATHS
    assert "/v1/calls" not in _OPEN_PATHS


# --- criterion 12: weekday cross-check with Zeller's congruence --------------

_ZELLER_NAMES = (
    "Saturday",
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
)


def _zeller_weekday(year: int, month: int, day: int) -> str:
    if month < 3:
        month += 12
        year -= 1
    k, j = year % 100, year // 100
    h = (day + (13 * (month + 1)) // 5 + k + k // 4 + j // 4 + 5 * j) % 7
    return _ZELLER_NAMES[h]


def test_weekday_matches_zeller_for_every_date_2024_to_2046() -> None:
    now = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    current = date(2024, 1, 1)
    end = date(2046, 12, 31)
    mismatches: list[str] = []
    while current <= end:
        req = DateResolveRequest(kind="days_from_date", from_date=current, days=0)
        res = resolve_date(req, now, RULE)
        expected = _zeller_weekday(current.year, current.month, current.day)
        if res.resolved is None or res.resolved.weekday != expected:
            mismatches.append(current.isoformat())
        current += timedelta(days=1)
    assert mismatches == []


# --- extension: bounds, horizon, edge cases, country, auth -------------------


def _post(body: dict[str, Any]) -> Any:
    return _client().post("/v1/dates/resolve", json=body)


@pytest.mark.parametrize("from_date", ["9999-12-31", "1999-12-31", "2101-01-01"])
def test_from_date_outside_2000_2100_is_rejected(from_date: str) -> None:
    body = {"kind": "days_from_date", "from_date": from_date, "days": 1}
    with pytest.raises(ValidationError):
        DateResolveRequest.model_validate(body)
    assert _post(body).status_code == 422


@pytest.mark.parametrize("from_date", ["2000-01-01", "2100-12-31"])
def test_from_date_bounds_are_inclusive(from_date: str) -> None:
    req = DateResolveRequest.model_validate(
        {"kind": "days_from_date", "from_date": from_date, "days": 1}
    )
    assert req.from_date == date.fromisoformat(from_date)


def test_days_from_date_beyond_horizon_is_too_far() -> None:
    res = _resolve({"kind": "days_from_date", "from_date": "2027-11-27", "days": 366})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2028-11-27"
    assert res.allowed is False
    assert res.reason == "too_far"


def test_days_from_today_365_is_last_open_day() -> None:
    res = _resolve({"kind": "days_from_today", "days": 365})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2027-11-27"
    assert res.allowed is True


def test_days_from_today_366_is_closed_with_backward_alternative_only() -> None:
    res = _resolve({"kind": "days_from_today", "days": 366})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2027-11-28"
    assert res.resolved.weekday == "Sunday"
    assert res.reason == "closed_day"
    assert [_ymd(a) for a in res.alternatives] == ["2027-11-27"]


def test_closed_tomorrow_when_today_is_saturday_has_only_forward_alternative() -> None:
    res = _resolve({"kind": "days_from_today", "days": 1}, SATURDAY_NOW)
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2026-11-29"
    assert res.reason == "closed_day"
    assert [_ymd(a) for a in res.alternatives] == ["2026-11-30"]


def test_weekday_occurrence_8_is_seven_weeks_after_first() -> None:
    res = _resolve({"kind": "weekday", "weekday": "saturday", "occurrence": 8})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2027-01-16"
    assert len(res.candidates) == 3


def test_weekday_occurrence_9_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DateResolveRequest.model_validate(
            {"kind": "weekday", "weekday": "saturday", "occurrence": 9}
        )


def test_leap_day_next_leap_year_is_too_far() -> None:
    res = _resolve({"kind": "day_of_month", "day": 29, "month": 2})
    assert res.resolved is not None
    assert _ymd(res.resolved) == "2028-02-29"
    assert res.reason == "too_far"


def test_negative_days_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DateResolveRequest.model_validate({"kind": "days_from_today", "days": -1})


@pytest.mark.parametrize("country", [123, ["IN"], "ABCDEFGHI"])
def test_bad_country_is_rejected(country: Any) -> None:
    body = {"kind": "days_from_today", "days": 5, "country": country}
    with pytest.raises(ValidationError):
        DateResolveRequest.model_validate(body)
    assert _post(body).status_code == 422


@pytest.mark.parametrize("country", ["us", " US "])
def test_route_unsupported_country_any_case(country: str) -> None:
    resp = _post({"kind": "days_from_today", "days": 5, "country": country})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "unsupported_country"


@pytest.mark.parametrize("country", [None, "", "  "])
def test_route_blank_country_is_india(country: str | None) -> None:
    resp = _post({"kind": "days_from_today", "days": 5, "country": country})
    assert resp.status_code == 200
    assert resp.json()["country"] == "IN"


@pytest.mark.parametrize("day", ["²", "9" * 5000])
def test_hostile_day_values_are_422_not_500(day: str) -> None:
    resp = _post({"kind": "day_of_month", "day": day})
    assert resp.status_code == 422


def test_real_auth_middleware_leaves_resolve_open_and_protects_others() -> None:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.middleware("http")
    async def _set_request_id(request: Any, call_next: Any) -> Any:
        request.state.request_id = "test"
        return await call_next(request)

    app.include_router(dates_router.router, prefix="/v1")
    client = TestClient(app)
    ok = client.post("/v1/dates/resolve", json={"kind": "days_from_today", "days": 5})
    assert ok.status_code == 200
    assert client.get("/v1/calls").status_code == 401
