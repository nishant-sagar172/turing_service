"""Schemas for the date resolver endpoint (see app/services/date_resolver.py)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_COUNTRY = "IN"

DateReason = Literal["too_soon", "too_far", "closed_day", "invalid_date"]

_OPTIONAL_FIELDS = ("days", "weekday", "day", "month", "from_date", "period")
# 1-based fields: the Bolna tool sends 0 as a "not applicable" sentinel.
_ZERO_MEANS_ABSENT = ("day", "month")
_EMPTY_WORDS = frozenset({"", "none", "null", "n/a"})
# Bolna leaves "%(name)s" in place when the variable was never filled.
_PLACEHOLDER = re.compile(r"^%\(.*\)s$")
_ZEROS = re.compile(r"0+", re.ASCII)

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_WEEKDAY_ALIASES = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
PERIODS = (
    "this_week",
    "next_week",
    "week_after_next",
    "month_start",
    "month_middle",
    "month_end",
)
_REQUIRED_BY_KIND = {
    "days_from_today": ("days",),
    "weekday": ("weekday",),
    "weekday_of_month": ("weekday",),
    "period": ("period",),
    "day_of_month": ("day",),
    "days_from_date": ("from_date", "days"),
}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    return text.lower() in _EMPTY_WORDS or bool(_PLACEHOLDER.match(text))


def _is_zero(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return _ZEROS.fullmatch(value.strip()) is not None
    return isinstance(value, int) and value == 0


class DateResolveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    country: str = Field(default=DEFAULT_COUNTRY, max_length=8)
    kind: Literal[
        "days_from_today",
        "weekday",
        "weekday_of_month",
        "day_of_month",
        "days_from_date",
        "period",
    ]
    days: int | None = Field(default=None, ge=0, le=366)
    weekday: str | None = None
    occurrence: int = Field(default=1, ge=1, le=8)
    day: int | None = Field(default=None, ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)
    from_date: date | None = None
    period: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        cleaned = dict(data)
        for name in _OPTIONAL_FIELDS:
            if name in cleaned and _is_blank(cleaned[name]):
                cleaned[name] = None
        for name in _ZERO_MEANS_ABSENT:
            if name in cleaned and _is_zero(cleaned[name]):
                cleaned[name] = None
        if "occurrence" in cleaned and (
            _is_blank(cleaned["occurrence"]) or _is_zero(cleaned["occurrence"])
        ):
            cleaned["occurrence"] = 1
        return cleaned

    @field_validator("country", mode="before")
    @classmethod
    def _normalise_country(cls, value: Any) -> Any:
        if value is None:
            return DEFAULT_COUNTRY
        if not isinstance(value, str):
            return value
        return value.strip().upper() or DEFAULT_COUNTRY

    @field_validator("weekday", mode="before")
    @classmethod
    def _normalise_weekday(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("weekday must be an English weekday name")
        text = value.strip().lower()
        text = _WEEKDAY_ALIASES.get(text, text)
        if text not in WEEKDAYS:
            raise ValueError(f"unknown weekday: {value!r}")
        return text

    @field_validator("period", mode="before")
    @classmethod
    def _normalise_period(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("period must be a text value")
        text = value.strip().lower().replace(" ", "_").replace("-", "_")
        if text not in PERIODS:
            raise ValueError(f"unknown period: {value!r}")
        return text

    @field_validator("from_date")
    @classmethod
    def _bound_from_date(cls, value: date | None) -> date | None:
        if value is not None and not 2000 <= value.year <= 2100:
            raise ValueError("from_date year out of range")
        return value

    @model_validator(mode="after")
    def _require_fields_for_kind(self) -> Self:
        required = _REQUIRED_BY_KIND[self.kind]
        missing = [name for name in required if getattr(self, name) is None]
        if missing:
            raise ValueError(f"kind={self.kind} requires: {', '.join(missing)}")
        return self


class DateInfo(BaseModel):
    date: date
    weekday: str
    spoken: str


class DateOption(DateInfo):
    allowed: bool


class DateResolveResponse(BaseModel):
    country: str
    today: DateInfo
    resolved: DateInfo | None = None
    days_from_today: int | None = None
    allowed: bool
    reason: DateReason | None = None
    candidates: list[DateOption] = Field(default_factory=list)
    alternatives: list[DateInfo] = Field(default_factory=list)
    rolled_to_next_month: bool = False
    message: str
