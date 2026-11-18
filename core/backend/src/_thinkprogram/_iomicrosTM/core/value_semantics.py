from __future__ import annotations

"""Canonical leaf, blank, and dead-JSON semantics for _thinkprogram._iomicrosTM.

This module is deliberately tiny and dependency-free. Every public fills,
coercion, and validation path should use these definitions rather than growing
slightly different local copies.

A box is explicit. Plain mappings are always data, including ``{"value": ...}``.
This prevents envelope heuristics from corrupting legitimate JSON-object atoms.
"""

import math
from dataclasses import is_dataclass
from typing import Any, Mapping


JSON_SCALAR_TYPES = (str, int, float, bool, type(None))
BOX_MARKER = "__boxed__"
BOX_KEYS = frozenset({BOX_MARKER, "value", "micro_type", "kind", "source", "meta"})


class DeadJSONError(TypeError):
    """Raised when a value is not strict JSON-compatible data."""


def unbox_leaf(value: Any) -> Any:
    """Unbox one explicit engine leaf envelope, otherwise return unchanged.

    The only supported envelope marker is ``{"__boxed__": True, ...}``.
    Unmarked mappings are user data even if they contain keys such as ``value``
    or ``micro_type``.
    """
    if not isinstance(value, Mapping):
        return value

    if value.get(BOX_MARKER) is not True or "value" not in value:
        return value

    if not set(str(key) for key in value.keys()).issubset(BOX_KEYS):
        return value

    return value.get("value")


def is_blank_value(value: Any) -> bool:
    """Return whether a value is blank under platform requiredness semantics."""
    value = unbox_leaf(value)
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def assert_dead_json(value: Any, *, path: str = "value") -> None:
    """Assert strict JSON compatibility.

    Rules intentionally match JSON itself rather than "string-coercible" data:
    object keys must already be strings, floats must be finite, tuples and
    dataclasses are rejected, and only list/dict containers are admitted.
    """
    if value is None or isinstance(value, (str, int, bool)):
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise DeadJSONError(f"{path}: float must be finite, got {value!r}")
        return

    if is_dataclass(value) and not isinstance(value, type):
        raise DeadJSONError(
            f"{path}: dataclass is not dead JSON ({type(value).__name__})"
        )

    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DeadJSONError(
                    f"{path}: JSON object keys must be strings; "
                    f"got {type(key).__name__}: {key!r}"
                )
            assert_dead_json(item, path=f"{path}.{key}")
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_dead_json(item, path=f"{path}[{index}]")
        return

    raise DeadJSONError(
        f"{path}: not strict dead JSON: {type(value).__name__}: {value!r}"
    )


__all__ = [
    "JSON_SCALAR_TYPES",
    "BOX_MARKER",
    "BOX_KEYS",
    "DeadJSONError",
    "assert_dead_json",
    "is_blank_value",
    "unbox_leaf",
]
