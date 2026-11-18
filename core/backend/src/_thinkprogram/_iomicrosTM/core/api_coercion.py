from __future__ import annotations

from typing import Any, Callable, Mapping, Type

from _thinkprogram._iomicrosTM.core.micro_registry import (
    MicroTypeDefinition,
    get_micro_type_definition,
    list_public_micro_types,
    normalize_micro_type_name,
)
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json


def _get_mt(micro_type: str) -> MicroTypeDefinition:
    name = normalize_micro_type_name(micro_type)
    try:
        return get_micro_type_definition(name)
    except KeyError as exc:
        raise ValueError(
            f"Unknown micro type {name!r}. Known: {list_public_micro_types()}"
        ) from exc


def can_coerce_micro(*, src_micro_type: str, dst_micro_type: str) -> bool:
    try:
        src = normalize_micro_type_name(src_micro_type)
        dst = normalize_micro_type_name(dst_micro_type)
        src_def = _get_mt(src)
        _get_mt(dst)
    except (ValueError, KeyError):
        return False
    return src == dst or dst in tuple(src_def.coerce_to_micro_types or ())


def _canonicalize(micro_type: str, raw: Any) -> Any:
    definition = _get_mt(micro_type)
    out = definition.coerce(raw) if callable(definition.coerce) else raw
    if out is not None and definition.python_types:
        if not isinstance(out, tuple(definition.python_types)):
            raise ValueError(
                f"micro {micro_type!r} coercer produced {type(out).__name__}; "
                f"expected {[t.__name__ for t in definition.python_types]}"
            )
    assert_dead_json(out, path=f"micro[{micro_type}]")
    return out


def coerce_micro_value(
    *,
    src_micro_type: str,
    dst_micro_type: str,
    raw: Any,
) -> Any:
    src = normalize_micro_type_name(src_micro_type)
    dst = normalize_micro_type_name(dst_micro_type)
    _get_mt(src)
    _get_mt(dst)

    if not can_coerce_micro(src_micro_type=src, dst_micro_type=dst):
        raise ValueError(f"Micro coercion not allowed: {src!r} -> {dst!r}")

    source_canonical = _canonicalize(src, raw)
    return _canonicalize(dst, source_canonical)


def can_cast_micro_to_python(*, micro_type: str, py_type: Type[Any]) -> bool:
    try:
        definition = _get_mt(micro_type)
    except ValueError:
        return False
    return py_type in dict(definition.python_casts or {})


def cast_micro_value_to_python(
    *,
    micro_type: str,
    py_type: Type[Any],
    raw: Any,
) -> Any:
    name = normalize_micro_type_name(micro_type)
    definition = _get_mt(name)
    casts: Mapping[type, Callable[[Any], Any]] = dict(definition.python_casts or {})
    if py_type not in casts:
        raise ValueError(
            f"{name!r} cannot cast to {getattr(py_type, '__name__', py_type)!s}; "
            f"allowed={[t.__name__ for t in casts]}"
        )

    out = casts[py_type](raw)
    if out is None:
        return None
    if not isinstance(out, py_type):
        raise ValueError(
            f"{name!r} cast produced {type(out).__name__}; expected {py_type.__name__}"
        )
    assert_dead_json(out, path=f"cast[{name}->{py_type.__name__}]")
    return out


__all__ = [
    "can_coerce_micro",
    "coerce_micro_value",
    "can_cast_micro_to_python",
    "cast_micro_value_to_python",
]
