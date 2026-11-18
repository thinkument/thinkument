from __future__ import annotations

from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [r"x^2 + y^2", {"__boxed__": True, "value": r"\frac{1}{2}"}],
        "invalid_examples": ["", "   ", {"__boxed__": True, "value": ""}, None],
        "modality": "latex_math",
    }],
    description="Non-blank LaTeX math fragment. This is not a full TeX parser.",
)
def is_nonempty_latex(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    ok = isinstance(value, str) and bool(value.strip())
    return ok, None if ok else "LaTeX math expression must be non-empty"


@guidance_for("is_nonempty_latex")
def is_nonempty_latex_guidance() -> Dict[str, Any]:
    return {
        "message": "Provide a LaTeX math expression, for example x^2 + y^2.",
        "modality": "latex_math",
    }


__all__ = ["is_nonempty_latex", "is_nonempty_latex_guidance"]
