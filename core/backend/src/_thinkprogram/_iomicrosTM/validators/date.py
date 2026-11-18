from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap

_TIME_RE = re.compile(r"^\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?$")


def _string(value: Any) -> str | None:
    value = unwrap(value)
    return value if isinstance(value, str) and value.strip() else None


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["2025-01-02", {"__boxed__": True, "value": "1999-12-31"}],
        "invalid_examples": ["2025/01/02", "2025-13-01", "not-a-date", "", None],
        "modality": "date",
    }],
    description="ISO-8601 calendar date in YYYY-MM-DD form.",
)
def is_iso_date(value: Any) -> tuple[bool, str | None]:
    raw = _string(value)
    if raw is None:
        return False, "value must be a non-blank string"
    try:
        parsed = date.fromisoformat(raw)
        ok = parsed.isoformat() == raw
    except ValueError:
        ok = False
    return ok, None if ok else "must be a valid ISO date (YYYY-MM-DD)"


@guidance_for("is_iso_date")
def is_iso_date_guidance() -> Dict[str, Any]:
    return {"message": "Enter a date in YYYY-MM-DD format.", "modality": "date"}


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["09:30", "09:30:15", {"__boxed__": True, "value": "23:59:59.123"}],
        "invalid_examples": [
            "9:30 AM",
            "9:30",
            "25:00",
            "09:30Z",
            "09:30+01:00",
            "",
            None,
        ],
        "modality": "time",
    }],
    description="Strict local ISO-style time HH:MM[:SS[.ffffff]] without an offset.",
)
def is_iso_time(value: Any) -> tuple[bool, str | None]:
    raw = _string(value)
    if raw is None or _TIME_RE.fullmatch(raw) is None:
        return False, "must be a valid local time (HH:MM[:SS[.ffffff]])"
    try:
        parsed = time.fromisoformat(raw)
        ok = parsed.tzinfo is None
    except ValueError:
        ok = False
    return ok, None if ok else "must be a valid local time (HH:MM[:SS[.ffffff]])"


@guidance_for("is_iso_time")
def is_iso_time_guidance() -> Dict[str, Any]:
    return {
        "message": "Enter a local time such as 09:30 or 09:30:15.",
        "modality": "time",
    }


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [
            "2026-08-21T09:30:00",
            "2026-08-21T09:30:00+00:00",
            {"__boxed__": True, "value": "2026-08-21T09:30"},
        ],
        "invalid_examples": ["2026-08-21", "2026/08/21 09:30", "", None],
        "modality": "datetime",
    }],
    description="ISO-8601 datetime string using a T date/time separator.",
)
def is_iso_datetime(value: Any) -> tuple[bool, str | None]:
    raw = _string(value)
    if raw is None or "T" not in raw:
        return False, "must be a valid ISO datetime with a T separator"
    try:
        datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
        ok = True
    except ValueError:
        ok = False
    return ok, None if ok else "must be a valid ISO datetime"


@guidance_for("is_iso_datetime")
def is_iso_datetime_guidance() -> Dict[str, Any]:
    return {
        "message": "Enter an ISO datetime such as 2026-08-21T09:30:00Z.",
        "modality": "datetime",
    }


@validator(
    arg_combos=[{
        "args": {"min_date": "2025-01-01"},
        "valid_examples": ["2025-01-01", "2026-01-01"],
        "invalid_examples": ["2024-12-31", "bad", None],
        "modality": "date",
    }],
    description="ISO date must be on or after min_date.",
)
def min_date(value: Any, *, min_date: str) -> tuple[bool, str | None]:
    raw = _string(value)
    try:
        current = date.fromisoformat(raw or "")
        minimum = date.fromisoformat(str(min_date))
    except ValueError:
        return False, "value and min_date must be valid ISO dates"
    ok = current >= minimum
    return ok, None if ok else f"date must be on or after {minimum.isoformat()}"


@guidance_for("min_date")
def min_date_guidance(*, min_date: str) -> Dict[str, Any]:
    minimum = date.fromisoformat(str(min_date)).isoformat()
    return {
        "message": f"Choose {minimum} or a later date.",
        "args": {"min_date": minimum},
        "modality": "date",
    }


@validator(
    arg_combos=[{
        "args": {"max_date": "2025-12-31"},
        "valid_examples": ["2025-12-31", "2025-01-01"],
        "invalid_examples": ["2026-01-01", "bad", None],
        "modality": "date",
    }],
    description="ISO date must be on or before max_date.",
)
def max_date(value: Any, *, max_date: str) -> tuple[bool, str | None]:
    raw = _string(value)
    try:
        current = date.fromisoformat(raw or "")
        maximum = date.fromisoformat(str(max_date))
    except ValueError:
        return False, "value and max_date must be valid ISO dates"
    ok = current <= maximum
    return ok, None if ok else f"date must be on or before {maximum.isoformat()}"


@guidance_for("max_date")
def max_date_guidance(*, max_date: str) -> Dict[str, Any]:
    maximum = date.fromisoformat(str(max_date)).isoformat()
    return {
        "message": f"Choose {maximum} or an earlier date.",
        "args": {"max_date": maximum},
        "modality": "date",
    }


__all__ = [
    "is_iso_date",
    "is_iso_date_guidance",
    "is_iso_time",
    "is_iso_time_guidance",
    "is_iso_datetime",
    "is_iso_datetime_guidance",
    "min_date",
    "min_date_guidance",
    "max_date",
    "max_date_guidance",
]
