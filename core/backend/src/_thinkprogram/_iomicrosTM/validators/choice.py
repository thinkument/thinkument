from __future__ import annotations

from typing import Any, Dict, Iterable

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


def _options(options: Iterable[Any]) -> list[Any]:
    return list(options) if options is not None else []


@validator(
    arg_combos=[{
        "args": {"options": ["kg", "lb", "cm", "mm"]},
        "valid_examples": ["kg", {"__boxed__": True, "value": "cm"}],
        "invalid_examples": ["stone", {"__boxed__": True, "value": "oz"}, None],
        "modality": "select",
    }],
    description="Value must equal one item from a fixed option sequence.",
)
def in_allowed(value: Any, *, options: Iterable[Any]) -> tuple[bool, str | None]:
    value = unwrap(value)
    try:
        ok = any(value == option for option in _options(options))
    except Exception:
        ok = False
    return ok, None if ok else "value not in allowed options"


@guidance_for("in_allowed")
def in_allowed_guidance(*, options: Iterable[Any]) -> Dict[str, Any]:
    options_list = _options(options)
    return {
        "message": "Choose one of the allowed options.",
        "options": options_list,
        "args": {"options": options_list},
        "modality": "select",
    }


@validator(
    arg_combos=[{
        "args": {"options": ["a", "b", "c"]},
        "valid_examples": [["a"], ["a", "c"], {"__boxed__": True, "value": ["b"]}],
        "invalid_examples": [["a", "z"], "a", None],
        "modality": "multi_select",
    }],
    description="Every selected list item must be one of the allowed options.",
)
def all_in_allowed(value: Any, *, options: Iterable[Any]) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, list):
        return False, "must be a list of selected options"
    allowed = _options(options)
    ok = all(any(item == option for option in allowed) for item in value)
    return ok, None if ok else "one or more selected values are not allowed"


@guidance_for("all_in_allowed")
def all_in_allowed_guidance(*, options: Iterable[Any]) -> Dict[str, Any]:
    options_list = _options(options)
    return {
        "message": "Choose only from the allowed options.",
        "options": options_list,
        "args": {"options": options_list},
        "modality": "multi_select",
    }


__all__ = [
    "in_allowed",
    "in_allowed_guidance",
    "all_in_allowed",
    "all_in_allowed_guidance",
]
