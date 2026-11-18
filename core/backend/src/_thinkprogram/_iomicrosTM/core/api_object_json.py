from __future__ import annotations

"""Explicit object <-> dead-JSON helpers.

Tagged reconstruction is intentionally deny-by-default.  A user-controlled
``__class__`` string must never become an unrestricted import primitive.
"""

import importlib
from typing import Any, Mapping, Optional, Set

from _thinkprogram._iomicrosTM.core.micro_registry import get_micro_type_definition
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json


def _class_path(obj: Any) -> str:
    cls = obj.__class__
    return f"{cls.__module__}:{cls.__qualname__}"


def _resolve_class(path: str) -> type:
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)
    if not module_name or not attr_path or "<locals>" in attr_path:
        raise ValueError(f"Bad class path: {path!r}")
    obj: Any = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"Resolved object for {path!r} is not a class")
    return obj


def dump_object_json(obj: Any, *, tag_class: bool = False) -> Any:
    definition = get_micro_type_definition("object-json")
    if not callable(definition.coerce):
        raise RuntimeError("object-json micro has no coercer")
    data = definition.coerce(obj)
    assert_dead_json(data, path="object_json.data")
    if not tag_class:
        return data
    payload = {"__class__": _class_path(obj), "data": data}
    assert_dead_json(payload, path="object_json.tagged")
    return payload


def load_object_json(
    payload: Any,
    *,
    allow: Optional[Set[str]] = None,
    class_registry: Optional[Mapping[str, type]] = None,
) -> Any:
    """Reconstruct a tagged payload only through an explicit allow surface.

    Untagged JSON is returned unchanged.  Tagged JSON requires either:
      * ``class_registry={path: Class}`` (preferred), or
      * ``allow={path, ...}``, after which that exact path may be imported.
    """
    if not isinstance(payload, dict):
        return payload
    if "__class__" not in payload or "data" not in payload:
        return payload

    if set(payload) != {"__class__", "data"}:
        raise ValueError("Tagged object-json payload may contain only '__class__' and 'data'")

    class_path = payload.get("__class__")
    data = payload.get("data")
    if not isinstance(class_path, str) or not class_path.strip():
        raise ValueError("Tagged object-json payload has bad '__class__'")
    class_path = class_path.strip()
    assert_dead_json(data, path="object_json.data")

    cls: type
    registry = dict(class_registry or {})
    if class_path in registry:
        cls = registry[class_path]
        if not isinstance(cls, type):
            raise TypeError(f"class_registry[{class_path!r}] is not a class")
    else:
        if allow is None:
            raise ValueError(
                "Tagged object-json reconstruction is deny-by-default; "
                "provide class_registry or an explicit allow set"
            )
        if class_path not in set(allow):
            raise ValueError(f"Class {class_path!r} is not in allow-list")
        cls = _resolve_class(class_path)

    for constructor_name in ("from_json", "from_object_json"):
        constructor = getattr(cls, constructor_name, None)
        if callable(constructor):
            return constructor(data)

    raise ValueError(
        f"Class {class_path!r} does not provide from_json()/from_object_json()"
    )


__all__ = ["dump_object_json", "load_object_json"]
