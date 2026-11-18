# think-backend/src/thinkcontinuitykernelTM/_contracts.py

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict

from __datomatonTM import (
    _WIDGET_REGISTRY_V1,
    register_datum_widget_v1,
)

from ._constants import (
    KERNEL_RESERVED_ARG_KEY_V1,
    SUPPORTED_KERNEL_ARG_TYPES_V1,
)
from ._helpers import (
    deep_dead_json_copy,
    kernel_arg_type_ok,
    require_mapping,
    require_nonempty_str,
)

_KERNEL_WIDGET_CONTRACTS_V1: Dict[str, Dict[str, Any]] = {}

def normalize_kernel_widget_contract_v1(
    *,
    name: str,
    args: Mapping[str, Any] | None = None,
    past_wires: Mapping[str, Any] | None = None,
    enforce_no_premount_shell: bool = False,
) -> Dict[str, Any]:
    normalized_args: Dict[str, Any] = {}

    for arg_name_raw, spec_raw in dict(args or {}).items():
        arg_name = require_nonempty_str(arg_name_raw, "kernel widget arg name")
        if arg_name == KERNEL_RESERVED_ARG_KEY_V1:
            raise ValueError(f"{KERNEL_RESERVED_ARG_KEY_V1!r} is reserved")

        spec = require_mapping(spec_raw, f"kernel widget arg {arg_name!r}")
        typ = str(spec.get("type") or "json")
        required = bool(spec.get("required", False))
        has_default = "default" in spec

        if typ not in SUPPORTED_KERNEL_ARG_TYPES_V1:
            raise ValueError(f"unknown kernel arg type {typ!r}")

        if has_default and not kernel_arg_type_ok(spec["default"], typ):
            raise ValueError(f"default for arg {arg_name!r} must be {typ}")

        normalized_args[arg_name] = {
            "type": typ,
            "required": required,
            **({"default": deep_dead_json_copy(spec["default"])} if has_default else {}),
        }

    normalized_wires: Dict[str, Any] = {}

    for wire_name_raw, spec_raw in dict(past_wires or {}).items():
        wire_name = require_nonempty_str(wire_name_raw, "kernel widget wire name")
        spec = require_mapping(spec_raw, f"kernel widget wire {wire_name!r}")

        multiplicity = str(spec.get("multiplicity") or "one")
        if multiplicity not in {"one", "many"}:
            raise ValueError(
                f"kernel widget wire {wire_name!r} multiplicity must be one|many"
            )

        normalized_wires[wire_name] = {
            "multiplicity": multiplicity,
            "required": bool(spec.get("required", False)),
        }

    contract = {
        "name": str(name),
        "args": normalized_args,
        "past_wires": normalized_wires,
        "enforce_no_premount_shell": bool(enforce_no_premount_shell),
    }

    json.dumps(contract, sort_keys=True)
    return contract


def register_kernel_widget_v1(
    name: str,
    fn: Any,
    *,
    args: Mapping[str, Any] | None = None,
    past_wires: Mapping[str, Any] | None = None,
    enforce_no_premount_shell: bool = False,
    overwrite: bool = False,
) -> None:
    register_datum_widget_v1(name, fn, overwrite=overwrite)

    if name in _KERNEL_WIDGET_CONTRACTS_V1 and not overwrite:
        raise ValueError(f"kernel widget contract already registered: {name!r}")

    _KERNEL_WIDGET_CONTRACTS_V1[name] = normalize_kernel_widget_contract_v1(
        name=name,
        args=args or {},
        past_wires=past_wires or {},
        enforce_no_premount_shell=enforce_no_premount_shell,
    )
def kernel_widget_contract_v1(widget: str) -> Dict[str, Any]:
    if widget not in _WIDGET_REGISTRY_V1:
        raise ValueError(f"unknown datum widget {widget!r}")

    if widget not in _KERNEL_WIDGET_CONTRACTS_V1:
        raise ValueError(f"datum widget {widget!r} has no kernel contract")

    return dict(_KERNEL_WIDGET_CONTRACTS_V1[widget])


def apply_kernel_arg_defaults_v1(
    *,
    widget: str,
    args: Mapping[str, Any],
) -> Dict[str, Any]:
    contract = kernel_widget_contract_v1(widget)
    out = dict(args)

    for arg_name, spec in dict(contract.get("args") or {}).items():
        if arg_name not in out and "default" in spec:
            out[arg_name] = deep_dead_json_copy(spec["default"])

    return out