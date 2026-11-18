# think-backend/src/thinkprogramTM/__integrate_thinkkernel_pulls_thinkwidgets.py

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict, Optional, Tuple

from __datomatonTM import _WIDGET_REGISTRY_V1

from _thinkprogram._thinkcontinuitykernelTM._contracts import (
    _KERNEL_WIDGET_CONTRACTS_V1,
    kernel_widget_contract_v1,
    normalize_kernel_widget_contract_v1,
)
from _thinkprogram._thinkcontinuitykernelTM._helpers import deep_dead_json_copy, require_nonempty_str


_KERNEL_WIDGET_CLASS_REPRS_V1: Dict[str, Dict[str, Any]] = {}

_ARGSPACE_KEYS_V1 = (
    "args",
    "argspace",
    "kernel_args",
    "kernel_argspace",
)
_WIRESPACE_KEYS_V1 = (
    "wires",
    "wire_space",
    "wirespace",
    "past_wires",
    "kernel_wires",
    "kernel_wire_space",
    "kernel_wirespace",
    "kernel_past_wires",
)


def _json_safe_or_repr_v1(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, sort_keys=True))
    except TypeError:
        return repr(value)


def _mapping_or_none_v1(value: Any, *, path: str) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return dict(value)


def _first_mapping_config_value_v1(
    config: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    path: str,
) -> Optional[Dict[str, Any]]:
    found_key: Optional[str] = None
    found_value: Optional[Dict[str, Any]] = None

    for key in keys:
        if key not in config:
            continue

        value = _mapping_or_none_v1(config.get(key), path=f"{path}.{key}")

        if found_key is not None and value != found_value:
            raise ValueError(
                f"{path} contains conflicting static contract keys "
                f"{found_key!r} and {key!r}"
            )

        found_key = key
        found_value = value

    return found_value


def _registered_widget_name_from_class_or_name_v1(widget: Any) -> str:
    if isinstance(widget, str):
        return require_nonempty_str(widget, "widget name")

    name = getattr(widget, "__datum_widget_registered_name_v1__", None)
    if name:
        return require_nonempty_str(name, "widget class registered name")

    compiled = getattr(widget, "__datum_widget_compiled_fn_v1__", None)
    if compiled is not None:
        name = getattr(compiled, "__datum_widget_registered_name_v1__", None)
        if name:
            return require_nonempty_str(name, "widget compiled registered name")

    raise ValueError(
        "expected a registered widget name or a class produced by the "
        "class-widget adapter with __datum_widget_registered_name_v1__"
    )


def _registered_datum_widget_fn_v1(widget_name: str) -> Any:
    name = require_nonempty_str(widget_name, "widget name")

    if name not in _WIDGET_REGISTRY_V1:
        raise ValueError(
            f"datum widget {name!r} is not registered in the base platform registry"
        )

    fn = _WIDGET_REGISTRY_V1[name]
    if not callable(fn):
        raise TypeError(f"datum widget registry entry {name!r} is not callable")

    return fn


def _class_and_fn_for_widget_v1(widget_class_or_name: Any) -> Tuple[str, Any, Any]:
    name = _registered_widget_name_from_class_or_name_v1(widget_class_or_name)
    fn = _registered_datum_widget_fn_v1(name)
    cls = getattr(fn, "__datum_widget_class_v1__", None)

    if not isinstance(widget_class_or_name, str):
        if cls is not None and cls is not widget_class_or_name:
            raise ValueError(
                f"registered widget {name!r} points at class "
                f"{cls!r}, not supplied class {widget_class_or_name!r}"
            )
        cls = widget_class_or_name

    return name, fn, cls


def _static_contract_config_v1(
    *,
    fn: Any,
    cls: Any = None,
) -> Dict[str, Any]:
    """
    Collect static class-widget config without importing thinkwidgetTM.

    The class adapter stores decorator config on the class and compiled function
    under __datum_widget_class_config_v1__. This bridge duck-types that metadata
    and treats it as optional.
    """
    merged: Dict[str, Any] = {}

    for source in (cls, fn):
        if source is None:
            continue

        config = getattr(source, "__datum_widget_class_config_v1__", None)
        if isinstance(config, Mapping):
            merged.update(dict(config))

    return merged


def infer_thinkwidget_kernel_contract_spec_v1(
    widget_class_or_name: Any,
) -> Dict[str, Any]:
    """
    Infer kernel argspace/wire-space from a registered class widget.

    Supported static decorator spellings inside @thinkwidgetTM_config(...):

        args={...}
        argspace={...}
        kernel_args={...}
        kernel_argspace={...}

        wires={...}
        past_wires={...}
        wirespace={...}
        kernel_wires={...}
        kernel_past_wires={...}

        enforce_no_premount_shell=True | False

    The returned shape is the kernel-native grammar:

        {
            "args": {...},
            "past_wires": {...},
            "enforce_no_premount_shell": bool,
        }
    """
    name, fn, cls = _class_and_fn_for_widget_v1(widget_class_or_name)
    config = _static_contract_config_v1(fn=fn, cls=cls)

    args = _first_mapping_config_value_v1(
        config,
        _ARGSPACE_KEYS_V1,
        path=f"widget {name!r} static config",
    )
    past_wires = _first_mapping_config_value_v1(
        config,
        _WIRESPACE_KEYS_V1,
        path=f"widget {name!r} static config",
    )

    return {
        "args": deep_dead_json_copy(args or {}),
        "past_wires": deep_dead_json_copy(past_wires or {}),
        "enforce_no_premount_shell": bool(
            config.get("enforce_no_premount_shell", False)
        ),
    }


def infer_registered_widget_class_repr_v1(widget_name: str) -> Dict[str, Any]:
    """
    Return stable kernel-side metadata for an already registered datum widget.

    Runtime execution still uses the ordinary datum widget name and the already
    compiled DatumWidgetFnV1 callable.
    """
    name = require_nonempty_str(widget_name, "widget name")
    fn = _registered_datum_widget_fn_v1(name)

    cls = getattr(fn, "__datum_widget_class_v1__", None)

    compiled_fn_repr = {
        "module": str(getattr(fn, "__module__", "")),
        "qualname": str(getattr(fn, "__qualname__", getattr(fn, "__name__", ""))),
        "name": str(getattr(fn, "__name__", "")),
    }

    class_repr = None
    if cls is not None:
        class_repr = {
            "module": str(getattr(cls, "__module__", "")),
            "qualname": str(getattr(cls, "__qualname__", getattr(cls, "__name__", ""))),
            "name": str(getattr(cls, "__name__", "")),
        }

    contract_spec = infer_thinkwidget_kernel_contract_spec_v1(name)

    out = {
        "widget_name": name,
        "registry": "datum_widget_v1",
        "static_lowering": "class_or_author_surface_to_datum_lifecycle_fn_v1",
        "runtime_contract": "ordinary DatumWidgetFnV1 called with ordinary q packet",
        "kernel_runtime_seam": "q['datum']['args'] and q['datum']['args']['__kernel']",
        "compiled_lifecycle_fn": compiled_fn_repr,
        "class": class_repr,
        "is_class_authored": cls is not None,
        "adapter_config": _json_safe_or_repr_v1(
            getattr(fn, "__datum_widget_class_config_v1__", {})
        ),
        "signal_catchers": _json_safe_or_repr_v1(
            getattr(fn, "__datum_widget_signal_catchers_v1__", {})
        ),
        "inferred_kernel_contract_spec": contract_spec,
    }

    json.dumps(out, sort_keys=True)
    return out


def register_existing_datum_widget_as_kernel_widget_v1(
    widget_name: str,
    *,
    args: Mapping[str, Any] | None = None,
    past_wires: Mapping[str, Any] | None = None,
    enforce_no_premount_shell: bool = False,
    overwrite: bool = False,
    class_repr: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Attach a kernel contract to an already registered datum widget.

    This bridge does not re-register or wrap the base platform lifecycle fn.
    It only records the kernel sidecar contract and optional class/static repr.
    """
    name = require_nonempty_str(widget_name, "widget name")
    _registered_datum_widget_fn_v1(name)

    if name in _KERNEL_WIDGET_CONTRACTS_V1 and not overwrite:
        raise ValueError(f"kernel widget contract already registered: {name!r}")

    contract = normalize_kernel_widget_contract_v1(
        name=name,
        args=args or {},
        past_wires=past_wires or {},
        enforce_no_premount_shell=enforce_no_premount_shell,
    )
    _KERNEL_WIDGET_CONTRACTS_V1[name] = contract

    if class_repr is None:
        repr_out = infer_registered_widget_class_repr_v1(name)
    else:
        repr_out = deep_dead_json_copy(dict(class_repr))
        repr_out.setdefault("widget_name", name)
        json.dumps(repr_out, sort_keys=True)

    _KERNEL_WIDGET_CLASS_REPRS_V1[name] = repr_out

    return {
        "ok": True,
        "widget_name": name,
        "kernel_contract": kernel_widget_contract_v1(name),
        "class_repr": kernel_widget_class_repr_v1(name),
    }


def pull_thinkwidget_class_into_kernel_v1(
    widget_class_or_name: Any,
    *,
    args: Mapping[str, Any] | None = None,
    past_wires: Mapping[str, Any] | None = None,
    wires: Mapping[str, Any] | None = None,
    enforce_no_premount_shell: bool | None = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Public convenience seam for split-project class widgets.

    Explicit pull arguments win. Otherwise, the bridge reads the class-widget
    static decorator config and reuses the kernel's existing contract grammar.
    """
    name, _fn, _cls = _class_and_fn_for_widget_v1(widget_class_or_name)

    if past_wires is not None and wires is not None and dict(past_wires) != dict(wires):
        raise ValueError("past_wires and wires specify conflicting contracts")

    inferred = infer_thinkwidget_kernel_contract_spec_v1(widget_class_or_name)

    final_args = (
        _mapping_or_none_v1(args, path="args")
        if args is not None
        else dict(inferred["args"])
    )
    final_wires = (
        _mapping_or_none_v1(past_wires, path="past_wires")
        if past_wires is not None
        else (
            _mapping_or_none_v1(wires, path="wires")
            if wires is not None
            else dict(inferred["past_wires"])
        )
    )
    final_enforce_no_premount_shell = (
        bool(enforce_no_premount_shell)
        if enforce_no_premount_shell is not None
        else bool(inferred.get("enforce_no_premount_shell", False))
    )

    return register_existing_datum_widget_as_kernel_widget_v1(
        name,
        args=final_args or {},
        past_wires=final_wires or {},
        enforce_no_premount_shell=final_enforce_no_premount_shell,
        overwrite=overwrite,
    )


def kernel_widget_class_repr_v1(widget_name: str) -> Dict[str, Any]:
    """
    Return optional class/static-authoring repr for a kernel widget.

    This metadata is not needed for runtime execution. It is useful for tests,
    debug UIs, schema displays, and proving the kernel contract was attached to
    the exact class-authored widget already present in the base registry.
    """
    name = require_nonempty_str(widget_name, "widget name")

    if name not in _KERNEL_WIDGET_CLASS_REPRS_V1:
        if name not in _WIDGET_REGISTRY_V1:
            raise ValueError(f"unknown datum widget {name!r}")
        return infer_registered_widget_class_repr_v1(name)

    return deep_dead_json_copy(_KERNEL_WIDGET_CLASS_REPRS_V1[name])


def list_kernel_widget_class_reprs_v1() -> Dict[str, Dict[str, Any]]:
    return {
        name: deep_dead_json_copy(repr_out)
        for name, repr_out in sorted(_KERNEL_WIDGET_CLASS_REPRS_V1.items())
    }


__all__ = [
    "infer_registered_widget_class_repr_v1",
    "infer_thinkwidget_kernel_contract_spec_v1",
    "kernel_widget_class_repr_v1",
    "list_kernel_widget_class_reprs_v1",
    "pull_thinkwidget_class_into_kernel_v1",
    "register_existing_datum_widget_as_kernel_widget_v1",
]