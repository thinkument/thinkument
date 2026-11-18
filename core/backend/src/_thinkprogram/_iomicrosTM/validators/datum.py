from __future__ import annotations

"""Public datum-level validators for cross-field invariants.

These operate on the complete macro mapping. They intentionally do not use the
leaf-validator registry because their modality is the datum, not one micro.
"""

import re
from typing import Any, Mapping, Optional, Sequence, Tuple

from _thinkprogram._iomicrosTM.core.value_semantics import is_blank_value, unbox_leaf


def _fields(fields: Sequence[str] | None) -> list[str]:
    return [
        str(field).strip()
        for field in (fields or [])
        if str(field or "").strip()
    ]


def _value(macro: Mapping[str, Any], field: str) -> Any:
    return unbox_leaf(macro.get(field))


def _word_count(value: Any) -> int:
    value = unbox_leaf(value)
    if not isinstance(value, str):
        return 0
    return len(re.findall(r"\b\w+\b", value, flags=re.UNICODE))


def min_words_in_field(
    macro: Mapping[str, Any], *, field: str, min_words: int
) -> Tuple[bool, Optional[str]]:
    """Require one named text field to contain at least ``min_words`` words."""
    name = str(field or "").strip()
    if not name:
        return False, "min_words_in_field: field is required"
    minimum = int(min_words)
    if minimum < 0:
        return False, "min_words must be >= 0"
    if minimum == 0:
        return True, None

    value = _value(macro, name)
    if is_blank_value(value):
        return False, f"{name} must be non-blank"
    if not isinstance(value, str):
        return False, f"{name} must be a string"

    count = _word_count(value)
    if count < minimum:
        return False, f"{name} must have at least {minimum} words"
    return True, None


def total_words_max(
    macro: Mapping[str, Any],
    *,
    max_words: int,
    fields: Sequence[str] | None = None,
) -> Tuple[bool, Optional[str]]:
    """Limit total words across selected top-level text fields.

    When ``fields`` is omitted, every top-level macro field is considered;
    non-string values contribute zero words.
    """
    maximum = int(max_words)
    if maximum < 0:
        return False, "max_words must be >= 0"

    names = _fields(fields) if fields is not None else [str(key) for key in macro]
    total = sum(_word_count(_value(macro, name)) for name in names)
    if total <= maximum:
        return True, None
    return False, f"total words must be <= {maximum}"


def require_all_or_none(
    macro: Mapping[str, Any], *, fields: Sequence[str]
) -> Tuple[bool, Optional[str]]:
    """Require either every named field to be nonblank or every one to be blank."""
    names = _fields(fields)
    if not names:
        return True, None
    present = [name for name in names if not is_blank_value(_value(macro, name))]
    if not present or len(present) == len(names):
        return True, None
    missing = [name for name in names if is_blank_value(_value(macro, name))]
    return False, f"fields must be all-or-none: present={present}, missing={missing}"


def require_at_least_k(
    macro: Mapping[str, Any], *, fields: Sequence[str], k: int
) -> Tuple[bool, Optional[str]]:
    """Require at least ``k`` named fields to be nonblank."""
    names = _fields(fields)
    required = int(k)
    if required <= 0:
        return True, None
    if required > len(names):
        return False, f"k={required} exceeds number of fields={len(names)}"
    present = [name for name in names if not is_blank_value(_value(macro, name))]
    if len(present) >= required:
        return True, None
    return False, f"need at least {required} fields set among {names}; present={present}"


def require_exactly_k(
    macro: Mapping[str, Any], *, fields: Sequence[str], k: int
) -> Tuple[bool, Optional[str]]:
    """Require exactly ``k`` named fields to be nonblank."""
    names = _fields(fields)
    required = int(k)
    if required < 0 or required > len(names):
        return False, f"k must be between 0 and {len(names)}"
    present = [name for name in names if not is_blank_value(_value(macro, name))]
    if len(present) == required:
        return True, None
    return False, f"need exactly {required} fields set among {names}; present={present}"


def fields_equal(
    macro: Mapping[str, Any], *, fields: Sequence[str]
) -> Tuple[bool, Optional[str]]:
    """Require all named fields to have equal semantic leaf values."""
    names = _fields(fields)
    if len(names) < 2:
        return True, None
    values = [_value(macro, name) for name in names]
    if all(value == values[0] for value in values[1:]):
        return True, None
    return False, f"fields must match: {names}"


def require_field_if_equals(
    macro: Mapping[str, Any],
    *,
    when_field: str,
    equals: Any,
    required_field: str,
) -> Tuple[bool, Optional[str]]:
    """Require one field when another field equals an authored semantic value."""
    when = str(when_field or "").strip()
    required = str(required_field or "").strip()
    if not when or not required:
        return False, "when_field and required_field are required"
    target = unbox_leaf(equals)
    if _value(macro, when) != target:
        return True, None
    if is_blank_value(_value(macro, required)):
        return False, f"{required} is required when {when} == {target!r}"
    return True, None


__all__ = [
    "min_words_in_field",
    "total_words_max",
    "require_all_or_none",
    "require_at_least_k",
    "require_exactly_k",
    "fields_equal",
    "require_field_if_equals",
]
