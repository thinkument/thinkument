# think-backend/src/thinkcontinuitykernelTM/_helpers.py

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict


def require_mapping(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return dict(value)


def require_nonempty_str(value: Any, path: str) -> str:
    s = str(value or "").strip()
    if not s or s.lower() == "none":
        raise ValueError(f"{path} must be a non-empty string")
    return s


def deep_dead_json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def assert_dead_jsonable(value: Any) -> None:
    json.dumps(value, sort_keys=True)


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr)


def kernel_version(k: Mapping[str, Any]) -> str:
    return str(k.get("kernel_args_surface_version") or "").strip()


def kernel_arg_type_ok(value: Any, typ: str) -> bool:
    typ = str(typ or "json")

    if typ == "json":
        try:
            json.dumps(value, sort_keys=True)
            return True
        except TypeError:
            return False

    if typ == "str":
        return isinstance(value, str)

    if typ == "int":
        return isinstance(value, int) and not isinstance(value, bool)

    if typ == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    if typ == "bool":
        return isinstance(value, bool)

    if typ == "dict":
        return isinstance(value, Mapping)

    if typ == "list":
        return isinstance(value, list)

    if typ == "list[str]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)

    if typ == "list[int]":
        return (
            isinstance(value, list)
            and all(isinstance(x, int) and not isinstance(x, bool) for x in value)
        )

    raise ValueError(f"unknown kernel arg type {typ!r}")