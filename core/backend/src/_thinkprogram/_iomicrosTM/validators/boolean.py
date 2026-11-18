from __future__ import annotations

from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.tiny_coercers import coerce_bool
from _thinkprogram._iomicrosTM.validators._common import unwrap


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [True, False, 1, 0, "yes", "off", {"__boxed__": True, "value": "true"}],
        "invalid_examples": [2, -1, "maybe", None],
        "modality": "boolean",
    }],
    description="Value must be explicitly coercible to a boolean.",
)
def is_boolean(value: Any) -> tuple[bool, str | None]:
    try:
        raw = unwrap(value)
        coerce_bool(raw)
        ok = raw is not None
    except (TypeError, ValueError):
        ok = False
    return ok, None if ok else "must be a boolean value"


@guidance_for("is_boolean")
def is_boolean_guidance() -> Dict[str, Any]:
    return {"message": "Choose true or false.", "modality": "boolean"}


__all__ = ["is_boolean", "is_boolean_guidance"]
