from __future__ import annotations

import re
from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap

_THIS_MODULE = "_thinkprogram._iomicrosTM.validators.text"


def text_validator_path(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        raise ValueError("text validator name must be non-empty")
    return f"{_THIS_MODULE}:{name}"


def text_validator_spec(name: str, *, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"path": text_validator_path(name), "args": dict(args or {})}


def nonempty_str_validator_spec(*, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return text_validator_spec("is_nonempty_str", args=args)


def min_words_validator_spec(min_words: int) -> Dict[str, Any]:
    return text_validator_spec("min_words", args={"min_words": int(min_words)})


def max_words_validator_spec(max_words: int) -> Dict[str, Any]:
    return text_validator_spec("max_words", args={"max_words": int(max_words)})


def min_length_validator_spec(min_length: int) -> Dict[str, Any]:
    return text_validator_spec("min_length", args={"min_length": int(min_length)})


def max_length_validator_spec(max_length: int) -> Dict[str, Any]:
    return text_validator_spec("max_length", args={"max_length": int(max_length)})


def pattern_validator_spec(*, pattern: str, flags: int = 0) -> Dict[str, Any]:
    return text_validator_spec(
        "pattern",
        args={"pattern": str(pattern), "flags": int(flags)},
    )


def _word_count(value: Any) -> int:
    value = unwrap(value)
    if not isinstance(value, str):
        return 0
    return len(re.findall(r"\b\w+\b", value, flags=re.UNICODE))


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["a", "  hello  ", {"__boxed__": True, "value": "hello"}],
        "invalid_examples": ["", "   ", {"__boxed__": True, "value": ""}, None, 3],
        "modality": "text",
    }],
    description="Requires a non-blank string after explicit leaf unboxing.",
)
def is_nonempty_str(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    ok = isinstance(value, str) and bool(value.strip())
    return ok, None if ok else "must be a non-blank string"


@guidance_for("is_nonempty_str")
def is_nonempty_str_guidance() -> Dict[str, Any]:
    return {"message": "Enter a non-blank value.", "modality": "text"}


@validator(
    arg_combos=[{
        "args": {"min_words": 2},
        "valid_examples": ["hello world", {"__boxed__": True, "value": "alpha beta"}],
        "invalid_examples": ["hello", "", None],
        "modality": "text",
    }],
    description="Require at least N Unicode word tokens.",
)
def min_words(value: Any, *, min_words: int) -> tuple[bool, str | None]:
    minimum = int(min_words)
    if minimum < 0:
        return False, "min_words must be >= 0"
    ok = _word_count(value) >= minimum
    return ok, None if ok else f"must have at least {minimum} words"


@guidance_for("min_words")
def min_words_guidance(*, min_words: int) -> Dict[str, Any]:
    minimum = int(min_words)
    return {
        "message": f"Provide at least {minimum} words.",
        "args": {"min_words": minimum},
        "modality": "text",
    }


@validator(
    arg_combos=[{
        "args": {"max_words": 5},
        "valid_examples": ["one two", {"__boxed__": True, "value": "up to five words"}, ""],
        "invalid_examples": ["one two three four five six"],
        "modality": "text",
    }],
    description="Require at most N Unicode word tokens.",
)
def max_words(value: Any, *, max_words: int) -> tuple[bool, str | None]:
    maximum = int(max_words)
    if maximum < 0:
        return False, "max_words must be >= 0"
    ok = _word_count(value) <= maximum
    return ok, None if ok else f"must have at most {maximum} words"


@guidance_for("max_words")
def max_words_guidance(*, max_words: int) -> Dict[str, Any]:
    maximum = int(max_words)
    return {
        "message": f"Keep it to {maximum} words or fewer.",
        "args": {"max_words": maximum},
        "modality": "text",
    }


@validator(
    arg_combos=[{
        "args": {"min_length": 3},
        "valid_examples": ["abc", "abcd", {"__boxed__": True, "value": "hello"}],
        "invalid_examples": ["ab", "", None],
        "modality": "text",
    }],
    description="Require a string with at least N characters.",
)
def min_length(value: Any, *, min_length: int) -> tuple[bool, str | None]:
    value = unwrap(value)
    minimum = int(min_length)
    if minimum < 0:
        return False, "min_length must be >= 0"
    ok = isinstance(value, str) and len(value) >= minimum
    return ok, None if ok else f"must contain at least {minimum} characters"


@guidance_for("min_length")
def min_length_guidance(*, min_length: int) -> Dict[str, Any]:
    minimum = int(min_length)
    return {
        "message": f"Use at least {minimum} characters.",
        "args": {"min_length": minimum},
        "modality": "text",
    }


@validator(
    arg_combos=[{
        "args": {"max_length": 5},
        "valid_examples": ["", "abc", {"__boxed__": True, "value": "hello"}],
        "invalid_examples": ["abcdef", None],
        "modality": "text",
    }],
    description="Require a string with at most N characters.",
)
def max_length(value: Any, *, max_length: int) -> tuple[bool, str | None]:
    value = unwrap(value)
    maximum = int(max_length)
    if maximum < 0:
        return False, "max_length must be >= 0"
    ok = isinstance(value, str) and len(value) <= maximum
    return ok, None if ok else f"must contain at most {maximum} characters"


@guidance_for("max_length")
def max_length_guidance(*, max_length: int) -> Dict[str, Any]:
    maximum = int(max_length)
    return {
        "message": f"Use no more than {maximum} characters.",
        "args": {"max_length": maximum},
        "modality": "text",
    }


@validator(
    arg_combos=[{
        "args": {"pattern": r"^[A-Z]{3}\d{3}$", "flags": 0},
        "valid_examples": ["ABC123", {"__boxed__": True, "value": "XYZ000"}],
        "invalid_examples": ["abc123", "AB12", None],
        "modality": "text",
    }],
    description="String must fully match a regular expression.",
)
def pattern(value: Any, *, pattern: str, flags: int = 0) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, str):
        return False, "must be a string"
    try:
        compiled = re.compile(str(pattern), int(flags))
    except re.error as exc:
        return False, f"invalid regex: {exc}"
    ok = compiled.fullmatch(value) is not None
    return ok, None if ok else "value does not match required pattern"


@guidance_for("pattern")
def pattern_guidance(*, pattern: str, flags: int = 0) -> Dict[str, Any]:
    return {
        "message": f"Match the required format: /{pattern}/",
        "args": {"pattern": str(pattern), "flags": int(flags)},
        "modality": "text",
    }


__all__ = [
    "text_validator_path",
    "text_validator_spec",
    "nonempty_str_validator_spec",
    "min_words_validator_spec",
    "max_words_validator_spec",
    "min_length_validator_spec",
    "max_length_validator_spec",
    "pattern_validator_spec",
    "is_nonempty_str",
    "is_nonempty_str_guidance",
    "min_words",
    "min_words_guidance",
    "max_words",
    "max_words_guidance",
    "min_length",
    "min_length_guidance",
    "max_length",
    "max_length_guidance",
    "pattern",
    "pattern_guidance",
]
