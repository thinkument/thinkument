from __future__ import annotations

"""Pure-Python validation and serialization helpers without external financial dependencies."""

import json
import re
from collections.abc import Mapping
from typing import Any, Dict

MAX_INTEGER = 2**63 - 1


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", value
    ):
        raise ValueError("invalid identifier")
    return value


def integer(value: int) -> int:
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise ValueError("quantity must be a nonnegative signed 64-bit integer")
    return value


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def frozen_json(value: Any, *, maximum: int = 16384) -> Any:
    def check(v: Any, depth: int = 0) -> Any:
        if depth > 20:
            raise ValueError("JSON nesting exceeds limit")
        if isinstance(v, Mapping):
            if any(not isinstance(k, str) for k in v):
                raise ValueError("JSON keys must be strings")
            return {k: check(val, depth + 1) for k, val in v.items()}
        if isinstance(v, (list, tuple)):
            return [check(item, depth + 1) for item in v]
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        raise ValueError(f"unsupported json value: {type(v)}")

    checked = check(value)
    encoded = json.dumps(checked, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > maximum:
        raise ValueError(f"JSON byte limit exceeded ({maximum} bytes)")
    return checked


def units(value: Any) -> Dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("units must be an object")
    if not value:
        raise ValueError("units mapping cannot be empty")
    cleaned = {}
    for k, v in value.items():
        identifier(k)
        integer(v)
        cleaned[k] = v
    return cleaned


__all__ = [
    "MAX_INTEGER",
    "identifier",
    "integer",
    "plain",
    "frozen_json",
    "units",
]
