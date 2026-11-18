from __future__ import annotations

from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json
from _thinkprogram._iomicrosTM.validators._common import unwrap


def _dead(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    try:
        assert_dead_json(value, path="value")
    except Exception as exc:
        return False, str(exc)
    return True, None


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [{"a": 1}, {"value": 1}, [1, "x", None], "scalar", 3, False, None],
        "invalid_examples": [{1: "bad-key"}, (1, 2), float("nan")],
        "modality": "object-json",
    }],
    description="Strict dead-JSON value: string-keyed objects, arrays, or JSON scalars.",
)
def is_dead_json(value: Any) -> tuple[bool, str | None]:
    return _dead(value)


@guidance_for("is_dead_json")
def is_dead_json_guidance() -> Dict[str, Any]:
    return {
        "message": "Provide JSON-compatible data with string object keys and finite numbers.",
        "modality": "object-json",
    }


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [
            {"a": 1},
            {"value": 1},
            {"__boxed__": True, "value": {"nested": [1, 2]}},
        ],
        "invalid_examples": [[], "x", None, {1: "bad"}],
        "modality": "json_object",
    }],
    description="Strict dead-JSON object.",
)
def is_json_object(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, dict):
        return False, "must be a JSON object"
    return _dead(value)


@guidance_for("is_json_object")
def is_json_object_guidance() -> Dict[str, Any]:
    return {"message": "Provide a JSON object.", "modality": "json_object"}


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [[], [1, 2], {"__boxed__": True, "value": ["x"]}],
        "invalid_examples": [{}, "x", None, [float("inf")]],
        "modality": "json_array",
    }],
    description="Strict dead-JSON array.",
)
def is_json_array(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, list):
        return False, "must be a JSON array"
    return _dead(value)


@guidance_for("is_json_array")
def is_json_array_guidance() -> Dict[str, Any]:
    return {"message": "Provide a JSON array.", "modality": "json_array"}


__all__ = [
    "is_dead_json",
    "is_dead_json_guidance",
    "is_json_object",
    "is_json_object_guidance",
    "is_json_array",
    "is_json_array_guidance",
]
