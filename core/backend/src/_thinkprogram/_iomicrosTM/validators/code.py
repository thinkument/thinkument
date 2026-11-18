from __future__ import annotations

from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


def _line_count(value: Any) -> int:
    value = unwrap(value)
    if not isinstance(value, str):
        return 0
    return sum(1 for line in value.splitlines() if line.strip())


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["print('hello')", {"__boxed__": True, "value": "x = 1"}],
        "invalid_examples": ["", "   ", {"__boxed__": True, "value": ""}, None],
        "modality": "code",
    }],
    description="Non-blank code snippet.",
)
def is_nonempty_code(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    ok = isinstance(value, str) and bool(value.strip())
    return ok, None if ok else "code snippet must be non-empty"


@guidance_for("is_nonempty_code")
def is_nonempty_code_guidance() -> Dict[str, Any]:
    return {"message": "Provide a non-empty code snippet.", "modality": "code"}


@validator(
    arg_combos=[{
        "args": {"min_lines": 2},
        "valid_examples": ["line1\nline2", {"__boxed__": True, "value": "a = 1\nb = 2\n"}],
        "invalid_examples": ["single line", "", None],
        "modality": "code",
    }],
    description="Require at least N non-empty lines of code.",
)
def min_code_lines(value: Any, *, min_lines: int) -> tuple[bool, str | None]:
    minimum = int(min_lines)
    ok = minimum >= 0 and _line_count(value) >= minimum
    return ok, None if ok else f"must contain at least {minimum} non-empty lines"


@guidance_for("min_code_lines")
def min_code_lines_guidance(*, min_lines: int) -> Dict[str, Any]:
    minimum = int(min_lines)
    return {
        "message": f"Provide at least {minimum} non-empty lines of code.",
        "args": {"min_lines": minimum},
        "modality": "code",
    }


@validator(
    arg_combos=[{
        "args": {"max_lines": 2},
        "valid_examples": ["line1", "line1\nline2", {"__boxed__": True, "value": "a\n\nb"}],
        "invalid_examples": ["a\nb\nc", None],
        "modality": "code",
    }],
    description="Require at most N non-empty lines of code.",
)
def max_code_lines(value: Any, *, max_lines: int) -> tuple[bool, str | None]:
    maximum = int(max_lines)
    ok = maximum >= 0 and isinstance(unwrap(value), str) and _line_count(value) <= maximum
    return ok, None if ok else f"must contain at most {maximum} non-empty lines"


@guidance_for("max_code_lines")
def max_code_lines_guidance(*, max_lines: int) -> Dict[str, Any]:
    maximum = int(max_lines)
    return {
        "message": f"Use no more than {maximum} non-empty lines of code.",
        "args": {"max_lines": maximum},
        "modality": "code",
    }


__all__ = [
    "is_nonempty_code",
    "is_nonempty_code_guidance",
    "min_code_lines",
    "min_code_lines_guidance",
    "max_code_lines",
    "max_code_lines_guidance",
]
