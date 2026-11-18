# think-backend/src/thinkcontinuitykernelTM/_validation.py

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict, List

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
)

from ._constants import (
    KERNEL_ARGS_SURFACE_VERSION_V1,
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
    KERNEL_KIND_V1,
    KERNEL_RESERVED_ARG_KEY_V1,
    SUPPORTED_KERNEL_HISTORY_SELECTORS_V1,
)
from ._contracts import kernel_widget_contract_v1
from ._helpers import (
    kernel_arg_type_ok,
    kernel_version,
    require_mapping,
    require_nonempty_str,
)


def validate_kernel_datum_contract_v1(
    *,
    datum: Mapping[str, Any],
    history_aliases: set[str],
    path: str,
) -> Dict[str, Any]:
    d = dict(datum)
    widget = require_nonempty_str(d.get("widget"), f"{path}.widget")
    contract = kernel_widget_contract_v1(widget)

    args = d.get("args", {})
    if not isinstance(args, Mapping):
        raise ValueError(f"{path}.args must be mapping")
    args = dict(args)

    if KERNEL_RESERVED_ARG_KEY_V1 in args:
        raise ValueError(
            f"{path}.args may not contain reserved key {KERNEL_RESERVED_ARG_KEY_V1!r}"
        )

    arg_specs = dict(contract.get("args") or {})
    unknown_args = set(args) - set(arg_specs)
    if unknown_args:
        raise ValueError(
            f"{path} for widget {widget!r} has unknown args: {sorted(unknown_args)}"
        )

    for arg_name, spec_raw in arg_specs.items():
        spec = dict(spec_raw)
        required = bool(spec.get("required", False))
        typ = str(spec.get("type") or "json")

        if required and arg_name not in args:
            raise ValueError(f"{path} missing required arg {arg_name!r}")

        if arg_name in args and not kernel_arg_type_ok(args[arg_name], typ):
            raise ValueError(f"{path} arg {arg_name!r} must be {typ}")

    past_wires = d.get("past_wires", {})
    if not isinstance(past_wires, Mapping):
        raise ValueError(f"{path}.past_wires must be mapping")
    past_wires = dict(past_wires)

    wire_specs = dict(contract.get("past_wires") or {})
    unknown_wires = set(past_wires) - set(wire_specs)
    if unknown_wires:
        raise ValueError(
            f"{path} for widget {widget!r} has unknown wires: {sorted(unknown_wires)}"
        )

    for wire_name, spec_raw in wire_specs.items():
        spec = dict(spec_raw)
        multiplicity = str(spec.get("multiplicity") or "one")
        required = bool(spec.get("required", False))

        if wire_name not in past_wires:
            if required:
                raise ValueError(f"{path} missing required wire {wire_name!r}")
            continue

        aliases = past_wires[wire_name]
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            raise ValueError(f"{path}.past_wires[{wire_name!r}] must be list[str]")

        if multiplicity == "one" and len(aliases) != 1:
            raise ValueError(
                f"{path}.past_wires[{wire_name!r}] requires exactly one alias"
            )

        if multiplicity == "many" and required and len(aliases) < 1:
            raise ValueError(
                f"{path}.past_wires[{wire_name!r}] requires at least one alias"
            )

        missing_aliases = set(aliases) - history_aliases
        if missing_aliases:
            raise ValueError(
                f"{path}.past_wires[{wire_name!r}] references unknown "
                f"history queries: {sorted(missing_aliases)}"
            )

    return d


def validate_kernel_step_surface_v1(k: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Validate one K in isolation.

    Whole-program validation adds uniqueness and backward-reference checks.
    """
    k = require_mapping(k, "kernel")

    if str(k.get("kind") or KERNEL_KIND_V1) != KERNEL_KIND_V1:
        raise ValueError(f"kernel.kind must be {KERNEL_KIND_V1}")

    if kernel_version(k) != KERNEL_ARGS_SURFACE_VERSION_V1:
        raise ValueError(
            f"kernel.kernel_args_surface_version must be {KERNEL_ARGS_SURFACE_VERSION_V1}"
        )

    step = require_mapping(k.get("step"), "kernel.step")
    form = require_mapping(k.get("form"), "kernel.form")
    frame = require_mapping(k.get("frame"), "kernel.frame")
    span = require_mapping(k.get("span"), "kernel.span")

    require_nonempty_str(step.get("id"), "kernel.step.id")
    require_nonempty_str(form.get("id"), "kernel.form.id")
    require_nonempty_str(frame.get("id"), "kernel.frame.id")
    require_nonempty_str(span.get("id"), "kernel.span.id")

    for role_key in ("role", "roles"):
        if role_key in span:
            if role_key == "role":
                require_nonempty_str(span.get("role"), "kernel.span.role")
            else:
                roles = span.get("roles")
                if not isinstance(roles, list) or not all(isinstance(x, str) for x in roles):
                    raise ValueError("kernel.span.roles must be list[str]")

    history_queries = k.get("history_queries", {})
    if not isinstance(history_queries, Mapping):
        raise ValueError("kernel.history_queries must be mapping")

    for name, spec_raw in history_queries.items():
        alias = require_nonempty_str(name, "kernel.history_queries key")
        spec = require_mapping(spec_raw, f"kernel.history_queries[{alias}]")
        require_nonempty_str(
            spec.get("from_step"),
            f"history_queries[{alias}].from_step",
        )
        require_nonempty_str(
            spec.get("datum_id"),
            f"history_queries[{alias}].datum_id",
        )

        write_kind = str(spec.get("write_kind") or WRITE_KIND_DATUM_LIFECYCLE)
        if write_kind != WRITE_KIND_DATUM_LIFECYCLE:
            raise ValueError("v1 supports only datum_lifecycle history queries")

        select = str(spec.get("select") or KERNEL_HISTORY_QUERY_SELECT_LATEST_V1)
        if select not in SUPPORTED_KERNEL_HISTORY_SELECTORS_V1:
            raise ValueError(f"history_queries[{alias}].select must be latest|all")

    datums = k.get("datums")
    if not isinstance(datums, list):
        raise ValueError("kernel.datums must be a list")

    history_aliases = set(str(x) for x in dict(history_queries).keys())

    seen: set[str] = set()
    for i, d_raw in enumerate(datums):
        d = require_mapping(d_raw, f"kernel.datums[{i}]")
        did = require_nonempty_str(d.get("id"), f"kernel.datums[{i}].id")
        if did in seen:
            raise ValueError(f"duplicate datum id in kernel surface: {did!r}")
        seen.add(did)

        widget = require_nonempty_str(d.get("widget"), f"kernel.datums[{i}].widget")
        contract = kernel_widget_contract_v1(widget)

        micros = d.get("micros")
        if not isinstance(micros, list):
            raise ValueError(f"kernel.datums[{i}].micros must be list")

        if bool(contract.get("enforce_no_premount_shell", False)) and micros:
            raise ValueError(
                f"kernel.datums[{i}] widget {widget!r} enforces no premount shell; "
                "datum.micros must be empty and first usable shell must be created "
                "by mount explosion"
            )

        lifecycle = d.get("lifecycle")
        if lifecycle is not None and not isinstance(lifecycle, Mapping):
            raise ValueError(f"kernel.datums[{i}].lifecycle must be mapping")

        if "roles" in d:
            roles = d.get("roles")
            if not isinstance(roles, list) or not all(isinstance(x, str) for x in roles):
                raise ValueError(f"kernel.datums[{i}].roles must be list[str]")

        if "role" in d:
            require_nonempty_str(d.get("role"), f"kernel.datums[{i}].role")

        validate_kernel_datum_contract_v1(
            datum=d,
            history_aliases=history_aliases,
            path=f"kernel.datums[{i}]",
        )

    json.dumps(k, sort_keys=True)
    return dict(k)


def validate_kernel_program_v1(program: Any) -> List[Dict[str, Any]]:
    if not isinstance(program, list):
        raise ValueError("kernel program must be list[K]")

    out = [validate_kernel_step_surface_v1(k) for k in program]

    step_ids: set[str] = set()
    form_ids: set[str] = set()
    prior_steps: Dict[str, Dict[str, Any]] = {}

    for k in out:
        step_id = str(k["step"]["id"])
        form_id = str(k["form"]["id"])

        if step_id in step_ids:
            raise ValueError(f"duplicate kernel step id: {step_id!r}")
        step_ids.add(step_id)

        if form_id in form_ids:
            raise ValueError(f"duplicate kernel form id: {form_id!r}")
        form_ids.add(form_id)

        for alias, spec in dict(k.get("history_queries") or {}).items():
            from_step = str(spec["from_step"])
            datum_id = str(spec["datum_id"])

            if from_step not in prior_steps:
                raise ValueError(
                    f"history query {alias!r} on {step_id!r} points to "
                    f"non-prior or unknown step {from_step!r}"
                )

            prior_datum_ids = {str(d["id"]) for d in prior_steps[from_step]["datums"]}
            if datum_id not in prior_datum_ids:
                raise ValueError(
                    f"history query {alias!r} points to unknown prior datum "
                    f"{from_step}.{datum_id}"
                )

        prior_steps[step_id] = k

    return out