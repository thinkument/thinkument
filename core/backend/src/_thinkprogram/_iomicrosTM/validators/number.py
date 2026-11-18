from __future__ import annotations

import math
from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.tiny_coercers import coerce_integer, coerce_number
from _thinkprogram._iomicrosTM.validators._common import unwrap

_THIS_MODULE = "_thinkprogram._iomicrosTM.validators.number"


def number_validator_path(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        raise ValueError("number validator name must be non-empty")
    return f"{_THIS_MODULE}:{name}"


def number_validator_spec(name: str, *, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"path": number_validator_path(name), "args": dict(args or {})}


def positive_int_validator_spec() -> Dict[str, Any]:
    return number_validator_spec("is_positive_int")


def min_number_validator_spec(min_value: int | float) -> Dict[str, Any]:
    return number_validator_spec("min_number", args={"min_value": min_value})


def max_number_validator_spec(max_value: int | float) -> Dict[str, Any]:
    return number_validator_spec("max_number", args={"max_value": max_value})


def _as_number(value: Any) -> int | float | None:
    try:
        return coerce_number(unwrap(value))
    except (TypeError, ValueError):
        return None


def _as_integer(value: Any) -> int | None:
    try:
        return coerce_integer(unwrap(value))
    except (TypeError, ValueError):
        return None


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [0, 1.25, -3, "4.5", {"__boxed__": True, "value": "6"}],
        "invalid_examples": [True, "x", float("inf"), None],
        "modality": "number",
    }],
    description="Finite numeric value; booleans are excluded.",
)
def is_finite_number(value: Any) -> tuple[bool, str | None]:
    out = _as_number(value)
    ok = out is not None and not isinstance(out, bool)
    if isinstance(out, float):
        ok = ok and math.isfinite(out)
    return ok, None if ok else "must be a finite number"


@guidance_for("is_finite_number")
def is_finite_number_guidance() -> Dict[str, Any]:
    return {"message": "Enter a finite number.", "modality": "number"}


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [0, 1, -3, "5", 7.0, {"__boxed__": True, "value": "8"}],
        "invalid_examples": [1.2, "4.5", True, "x", None],
        "modality": "integer",
    }],
    description="Canonical integer value; integral floats and integer strings are accepted.",
)
def is_integer(value: Any) -> tuple[bool, str | None]:
    ok = _as_integer(value) is not None
    return ok, None if ok else "must be an integer"


@guidance_for("is_integer")
def is_integer_guidance() -> Dict[str, Any]:
    return {"message": "Enter a whole number.", "modality": "integer"}


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [1, {"__boxed__": True, "value": 3}, "5"],
        "invalid_examples": [0, -1, 1.2, "x", None, True],
        "modality": "integer",
    }],
    description="Positive integer (> 0).",
)
def is_positive_int(value: Any) -> tuple[bool, str | None]:
    out = _as_integer(value)
    ok = out is not None and out > 0
    return ok, None if ok else "must be a positive integer"


@guidance_for("is_positive_int")
def is_positive_int_guidance() -> Dict[str, Any]:
    return {"message": "Enter an integer greater than 0.", "modality": "integer"}


@validator(
    arg_combos=[{
        "args": {"min_value": 3},
        "valid_examples": [3, 3.5, 5, {"__boxed__": True, "value": 10}, "7.25"],
        "invalid_examples": [2.99, 0, -5, "x", True],
        "modality": "number",
    }],
    description="Finite number >= min_value without integer truncation.",
)
def min_number(value: Any, *, min_value: int | float) -> tuple[bool, str | None]:
    out = _as_number(value)
    minimum = _as_number(min_value)
    if minimum is None:
        return False, "min_value must be numeric"
    ok = out is not None and out >= minimum
    return ok, None if ok else f"must be >= {minimum}"


@guidance_for("min_number")
def min_number_guidance(*, min_value: int | float) -> Dict[str, Any]:
    minimum = coerce_number(min_value)
    return {
        "message": f"Provide a number >= {minimum}.",
        "args": {"min_value": minimum},
        "modality": "number",
    }


@validator(
    arg_combos=[{
        "args": {"max_value": 10},
        "valid_examples": [0, 9.9, 10, {"__boxed__": True, "value": 7}, "9.5"],
        "invalid_examples": [10.01, 11, 100, "oops", True],
        "modality": "number",
    }],
    description="Finite number <= max_value without integer truncation.",
)
def max_number(value: Any, *, max_value: int | float) -> tuple[bool, str | None]:
    out = _as_number(value)
    maximum = _as_number(max_value)
    if maximum is None:
        return False, "max_value must be numeric"
    ok = out is not None and out <= maximum
    return ok, None if ok else f"must be <= {maximum}"


@guidance_for("max_number")
def max_number_guidance(*, max_value: int | float) -> Dict[str, Any]:
    maximum = coerce_number(max_value)
    return {
        "message": f"Provide a number <= {maximum}.",
        "args": {"max_value": maximum},
        "modality": "number",
    }


__all__ = [
    "number_validator_path",
    "number_validator_spec",
    "positive_int_validator_spec",
    "min_number_validator_spec",
    "max_number_validator_spec",
    "is_finite_number",
    "is_finite_number_guidance",
    "is_integer",
    "is_integer_guidance",
    "is_positive_int",
    "is_positive_int_guidance",
    "min_number",
    "min_number_guidance",
    "max_number",
    "max_number_guidance",
]
