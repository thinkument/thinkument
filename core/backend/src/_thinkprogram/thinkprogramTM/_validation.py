from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional

from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    kernel_widget_class_repr_v1,
)

from ._helpers import (
    deepcopy_json,
    kernel_arg_type_ok_v1,
    require_mapping,
)


def kernel_widget_contract_from_repr_v1(widget_name: str) -> Dict[str, Any]:
    rep = kernel_widget_class_repr_v1(widget_name)
    contract = rep.get("inferred_kernel_contract_spec")
    if not isinstance(contract, Mapping):
        raise ValueError(f"widget {widget_name!r} has no readable kernel contract")
    return dict(contract)


def validate_args_against_contract_v1(
    *,
    logical_widget_id: str,
    widget_name: str,
    args: Mapping[str, Any],
    path: str,
) -> Dict[str, Any]:
    contract = kernel_widget_contract_from_repr_v1(widget_name)
    arg_specs = dict(contract.get("args") or {})
    arg_map = dict(args or {})

    unknown = set(arg_map) - set(arg_specs)
    if unknown:
        raise ValueError(
            f"{path} logical widget {logical_widget_id!r} has unknown args: "
            f"{sorted(unknown)}"
        )

    for arg_name, spec_raw in arg_specs.items():
        spec = dict(spec_raw)
        required = bool(spec.get("required", False))
        typ = str(spec.get("type") or "json")

        if required and arg_name not in arg_map:
            raise ValueError(
                f"{path} logical widget {logical_widget_id!r} "
                f"missing required arg {arg_name!r}"
            )

        if arg_name in arg_map and not kernel_arg_type_ok_v1(
            arg_map[arg_name],
            typ,
        ):
            raise ValueError(
                f"{path} logical widget {logical_widget_id!r} "
                f"arg {arg_name!r} must be {typ}"
            )

    return deepcopy_json(arg_map)


def validate_wire_names_against_contract_v1(
    *,
    logical_widget_id: str,
    widget_name: str,
    wires: Mapping[str, Any],
    path: str,
) -> Dict[str, Any]:
    contract = kernel_widget_contract_from_repr_v1(widget_name)
    wire_specs = dict(contract.get("past_wires") or {})
    wire_map = dict(wires or {})

    unknown = set(wire_map) - set(wire_specs)
    if unknown:
        raise ValueError(
            f"{path} logical widget {logical_widget_id!r} has unknown wires: "
            f"{sorted(unknown)}"
        )

    for wire_name, wire_spec in wire_map.items():
        if wire_spec is None:
            continue
        if not isinstance(wire_spec, Mapping):
            raise ValueError(f"{path}.wires[{wire_name!r}] must be mapping or null")
        if "from" not in wire_spec:
            raise ValueError(f"{path}.wires[{wire_name!r}] missing from")
        if "history" not in wire_spec:
            raise ValueError(f"{path}.wires[{wire_name!r}] missing history")

    return deepcopy_json(wire_map)


def history_spec_v1(raw: Mapping[str, Any], *, path: str) -> Dict[str, Any]:
    h = require_mapping(raw, path)

    allowed = {
        "select",
        "required",
        "max_results",
    }
    unknown = set(h) - allowed
    if unknown:
        raise ValueError(f"{path} has unknown keys: {sorted(unknown)}")

    select = str(h.get("select") or "latest")
    if select not in {"latest", "all"}:
        raise ValueError(f"{path}.select must be latest|all")

    required = h.get("required", False)
    if not isinstance(required, bool):
        raise ValueError(f"{path}.required must be boolean")

    max_results = h.get("max_results", 20)
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ValueError(f"{path}.max_results must be integer")
    if max_results < 1:
        raise ValueError(f"{path}.max_results must be >= 1")

    return {
        "select": select,
        "required": required,
        "max_results": max_results,
    }