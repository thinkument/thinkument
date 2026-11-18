from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict


def deepcopy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def assert_dead_json(value: Any, *, path: str) -> None:
    try:
        json.dumps(value, sort_keys=True)
    except TypeError as exc:
        raise ValueError(f"{path} must be dead JSON") from exc


def require_mapping(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be mapping")
    return dict(value)


def require_nonempty_str(value: Any, path: str) -> str:
    s = str(value or "").strip()
    if not s:
        raise ValueError(f"{path} must be non-empty string")
    return s


def reject_unknown_keys_v1(
    obj: Mapping[str, Any],
    allowed: set[str],
    *,
    path: str,
) -> None:
    extra = set(dict(obj)) - set(allowed)
    if extra:
        raise ValueError(f"{path} has unknown keys: {sorted(extra)}")


def deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy_json(dict(base or {}))
    for key, value in dict(patch or {}).items():
        if (
            key in out
            and isinstance(out[key], Mapping)
            and isinstance(value, Mapping)
        ):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy_json(value)
    return out


def assert_no_key_recursively(value: Any, forbidden_key: str, *, path: str) -> None:
    if isinstance(value, Mapping):
        if forbidden_key in value:
            raise ValueError(f"{path} may not author {forbidden_key!r}")
        for key, child in value.items():
            assert_no_key_recursively(
                child,
                forbidden_key,
                path=f"{path}.{key}",
            )
    elif isinstance(value, list):
        for i, child in enumerate(value):
            assert_no_key_recursively(
                child,
                forbidden_key,
                path=f"{path}[{i}]",
            )


def kernel_arg_type_ok_v1(value: Any, typ: str) -> bool:
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


def assert_list_of_strings(value: Any, *, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{path} must be list[str]")
    return list(value)


def assert_mapping_or_empty(value: Any, *, path: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be mapping")
    return dict(value)