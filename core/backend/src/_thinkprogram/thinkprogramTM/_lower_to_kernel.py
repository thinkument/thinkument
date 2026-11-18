from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
)

from _thinkprogram._thinkcontinuitykernelTM.api import (
    validate_kernel_program_v1,
)

from ._constants import (
    _ALLOWED_FLOW_ITEM_KEYS_V1,
    _ALLOWED_OVERRIDE_KEYS_V1,
    _ALLOWED_PROGRAM_INFO_KEYS_V1,
    _ALLOWED_PROGRAM_KEYS_V1,
    _ALLOWED_WIDGET_DEF_KEYS_V1,
    _DEFAULT_KERNEL_FLAGS_V1,
    _DEFAULT_LIFECYCLE_V1,
)

from ._helpers import (
    assert_list_of_strings,
    assert_mapping_or_empty,
    assert_no_key_recursively,
    deep_merge,
    deepcopy_json,
    reject_unknown_keys_v1,
    require_mapping,
    require_nonempty_str,
)
from ._symbols import bind_think_program_symbols_v1
from ._validation import (
    history_spec_v1,
    kernel_widget_contract_from_repr_v1,
    validate_args_against_contract_v1,
    validate_wire_names_against_contract_v1,
)
from ._wires import (
    AppearanceV1,
    safe_alias_v1,
    source_logical_widget_ids_v1,
    unique_alias_v1,
)


def lower_think_program_to_kernel_program_v1(
    program: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    run = bind_think_program_symbols_v1(program)

    assert_no_key_recursively(run.get("program", {}), "micros", path="run.program")

    run_map = require_mapping(run, "run")
    program_map = require_mapping(run_map.get("program"), "run.program")

    reject_unknown_keys_v1(
        program_map,
        _ALLOWED_PROGRAM_KEYS_V1,
        path="run.program",
    )

    info = require_mapping(program_map.get("info"), "run.program.info")

    reject_unknown_keys_v1(
        info,
        _ALLOWED_PROGRAM_INFO_KEYS_V1,
        path="run.program.info",
    )

    program_id = require_nonempty_str(info.get("id"), "run.program.info.id")
    program_title = require_nonempty_str(info.get("title"), "run.program.info.title")
    del program_title


    widgets = require_mapping(program_map.get("widgets"), "run.program.widgets")
    flow = program_map.get("flow")
    if not isinstance(flow, list) or not flow:
        raise ValueError("run.program.flow must be non-empty list")

    normalized_widgets: Dict[str, Dict[str, Any]] = {}

    for logical_widget_id_raw, widget_raw in widgets.items():
        logical_widget_id = require_nonempty_str(
            logical_widget_id_raw,
            "logical widget id",
        )

        wd = require_mapping(
            widget_raw,
            f"run.program.widgets[{logical_widget_id!r}]",
        )

        reject_unknown_keys_v1(
            wd,
            _ALLOWED_WIDGET_DEF_KEYS_V1,
            path=f"run.program.widgets[{logical_widget_id!r}]",
        )

        widget_name = require_nonempty_str(
            wd.get("widget"),
            f"run.program.widgets[{logical_widget_id!r}].widget",
        )

        contract = kernel_widget_contract_from_repr_v1(widget_name)
        if not bool(contract.get("enforce_no_premount_shell", False)):
            raise ValueError(
                "think_program_v1 only supports mount-shelling widgets. "
                f"Widget {widget_name!r} is not registered with "
                "enforce_no_premount_shell=true."
            )

        args = validate_args_against_contract_v1(
            logical_widget_id=logical_widget_id,
            widget_name=widget_name,
            args=dict(wd.get("args") or {}),
            path=f"run.program.widgets[{logical_widget_id!r}]",
        )

        wires = validate_wire_names_against_contract_v1(
            logical_widget_id=logical_widget_id,
            widget_name=widget_name,
            wires=dict(wd.get("wires") or {}),
            path=f"run.program.widgets[{logical_widget_id!r}]",
        )

        lifecycle = deep_merge(
            _DEFAULT_LIFECYCLE_V1,
            assert_mapping_or_empty(
                wd.get("lifecycle") or {},
                path=f"run.program.widgets[{logical_widget_id!r}].lifecycle",
            ),
        )
        lifecycle["mount_explode"] = True

        normalized_widgets[logical_widget_id] = {
            "logical_widget_id": logical_widget_id,
            "widget": widget_name,
            "title": str(wd.get("title") or logical_widget_id),
            "args": args,
            "lifecycle": lifecycle,
            "wires": wires,
            "tags": assert_list_of_strings(
                wd.get("tags") or [],
                path=f"run.program.widgets[{logical_widget_id!r}].tags",
            ),
            "roles": assert_list_of_strings(
                wd.get("roles") or [],
                path=f"run.program.widgets[{logical_widget_id!r}].roles",
            ),
            "system_flags": assert_mapping_or_empty(
                wd.get("system_flags") or {},
                path=f"run.program.widgets[{logical_widget_id!r}].system_flags",
            ),
            "authoritative": bool(wd.get("authoritative", True)),
        }

    explicit: list[Dict[str, Any]] = []
    prior: Dict[str, list[AppearanceV1]] = {}
    seen_flow_ids: set[str] = set()

    for flow_index, flow_raw in enumerate(flow):
        f = require_mapping(flow_raw, f"run.program.flow[{flow_index}]")

        reject_unknown_keys_v1(
            f,
            _ALLOWED_FLOW_ITEM_KEYS_V1,
            path=f"run.program.flow[{flow_index}]",
        )

        flow_id = require_nonempty_str(
            f.get("id"),
            f"run.program.flow[{flow_index}].id",
        )

        if flow_id in seen_flow_ids:
            raise ValueError(f"duplicate flow id: {flow_id!r}")
        seen_flow_ids.add(flow_id)

        flow_title = str(f.get("title") or flow_id)

        flow_widgets = f.get("widgets")
        if not isinstance(flow_widgets, list) or not flow_widgets:
            raise ValueError(f"flow {flow_id!r}.widgets must be non-empty list")

        if len(set(flow_widgets)) != len(flow_widgets):
            raise ValueError(f"flow {flow_id!r} may not repeat a logical widget id")

        for logical_widget_id in flow_widgets:
            if logical_widget_id not in normalized_widgets:
                raise ValueError(
                    f"flow {flow_id!r} references unknown logical widget "
                    f"{logical_widget_id!r}"
                )

        authoritative = f.get("authoritative")
        if authoritative is not None:
            if not isinstance(authoritative, list):
                raise ValueError(f"flow {flow_id!r}.authoritative must be list[bool]")
            if len(authoritative) != len(flow_widgets):
                raise ValueError(
                    f"flow {flow_id!r}.authoritative length must match widgets"
                )
            if not all(isinstance(x, bool) for x in authoritative):
                raise ValueError(f"flow {flow_id!r}.authoritative must be list[bool]")

        flow_roles = assert_list_of_strings(
            f.get("roles") or [],
            path=f"flow {flow_id!r}.roles",
        )

        overrides = assert_mapping_or_empty(
            f.get("overrides") or {},
            path=f"flow {flow_id!r}.overrides",
        )
        unknown_override_keys = set(overrides) - _ALLOWED_OVERRIDE_KEYS_V1
        if unknown_override_keys:
            raise ValueError(
                f"flow {flow_id!r}.overrides has unknown keys: "
                f"{sorted(unknown_override_keys)}"
            )

        for override_kind, override_map_raw in overrides.items():
            if not isinstance(override_map_raw, Mapping):
                raise ValueError(
                    f"flow {flow_id!r}.overrides.{override_kind} must be mapping"
                )

            for logical_widget_id in dict(override_map_raw):
                if logical_widget_id not in flow_widgets:
                    raise ValueError(
                        f"flow {flow_id!r}.overrides.{override_kind} references "
                        f"widget {logical_widget_id!r} not present in this flow item"
                    )

        step_id = f"{program_id}.{flow_id}"
        form_id = f"{program_id}.{flow_id}.form"

        k: Dict[str, Any] = {
            "kind": "think_kernel_step_v1",
            "kernel_args_surface_version": "v1",
            "step": {
                "id": step_id,
                "title": flow_title,
            },
            "form": {
                "id": form_id,
                "title": flow_title,
            },
            "frame": {
                "id": "frame",
                "title": flow_title,
            },
            "span": {
                "id": "span",
                "title": flow_title,
                **({"roles": flow_roles} if flow_roles else {}),
            },
            "history_queries": {},
            "datums": [],
            "kernel_flags": _DEFAULT_KERNEL_FLAGS_V1
        }

        current_appearances: list[AppearanceV1] = []

        for widget_position, logical_widget_id in enumerate(flow_widgets):
            base = deepcopy_json(normalized_widgets[logical_widget_id])

            args_patch = assert_mapping_or_empty(
                dict(overrides.get("args") or {}).get(logical_widget_id) or {},
                path=f"flow {flow_id!r}.overrides.args[{logical_widget_id!r}]",
            )
            lifecycle_patch = assert_mapping_or_empty(
                dict(overrides.get("lifecycle") or {}).get(logical_widget_id) or {},
                path=f"flow {flow_id!r}.overrides.lifecycle[{logical_widget_id!r}]",
            )
            system_flags_patch = assert_mapping_or_empty(
                dict(overrides.get("system_flags") or {}).get(logical_widget_id) or {},
                path=f"flow {flow_id!r}.overrides.system_flags[{logical_widget_id!r}]",
            )

            args = deep_merge(base["args"], args_patch)
            lifecycle = deep_merge(base["lifecycle"], lifecycle_patch)
            lifecycle["mount_explode"] = True

            system_flags = deep_merge(base["system_flags"], system_flags_patch)
            system_flags["logical_widget_id"] = logical_widget_id

            tags_override = dict(overrides.get("tags") or {})
            if logical_widget_id in tags_override:
                tags = assert_list_of_strings(
                    tags_override[logical_widget_id],
                    path=f"flow {flow_id!r}.overrides.tags[{logical_widget_id!r}]",
                )
            else:
                tags = assert_list_of_strings(
                    base["tags"],
                    path=f"run.program.widgets[{logical_widget_id!r}].tags",
                )

            roles_override = dict(overrides.get("roles") or {})
            if logical_widget_id in roles_override:
                roles = assert_list_of_strings(
                    roles_override[logical_widget_id],
                    path=f"flow {flow_id!r}.overrides.roles[{logical_widget_id!r}]",
                )
            else:
                roles = assert_list_of_strings(
                    base.get("roles") or [],
                    path=f"run.program.widgets[{logical_widget_id!r}].roles",
                )

            title_override = dict(overrides.get("title") or {})
            if logical_widget_id in title_override:
                title = str(title_override[logical_widget_id])
            else:
                title = str(base["title"])

            wires = deepcopy_json(base["wires"])
            wire_patch = assert_mapping_or_empty(
                dict(overrides.get("wires") or {}).get(logical_widget_id) or {},
                path=f"flow {flow_id!r}.overrides.wires[{logical_widget_id!r}]",
            )
            for wire_name, wire_value in wire_patch.items():
                if wire_value is None:
                    wires.pop(wire_name, None)
                else:
                    wires[wire_name] = deepcopy_json(wire_value)

            widget_name = str(base["widget"])

            validate_args_against_contract_v1(
                logical_widget_id=logical_widget_id,
                widget_name=widget_name,
                args=args,
                path=f"flow {flow_id!r} appearance {logical_widget_id!r}",
            )

            validate_wire_names_against_contract_v1(
                logical_widget_id=logical_widget_id,
                widget_name=widget_name,
                wires=wires,
                path=f"flow {flow_id!r} appearance {logical_widget_id!r}",
            )

            contract = kernel_widget_contract_from_repr_v1(widget_name)
            wire_contract = dict(contract.get("past_wires") or {})

            past_wires: Dict[str, list[str]] = {}

            for wire_name, wire_raw in dict(wires or {}).items():
                wire = require_mapping(
                    wire_raw,
                    f"flow {flow_id!r}.{logical_widget_id}.wires[{wire_name!r}]",
                )
                history = history_spec_v1(
                    wire.get("history"),
                    path=(
                        f"flow {flow_id!r}.{logical_widget_id}"
                        f".wires[{wire_name!r}].history"
                    ),
                )

                source_ids = source_logical_widget_ids_v1(
                    source=wire.get("from"),
                    current_logical_widget_id=logical_widget_id,
                    path=f"flow {flow_id!r}.{logical_widget_id}.wires[{wire_name!r}]",
                )

                aliases: list[str] = []

                for source_id in source_ids:
                    appearances = list(prior.get(source_id) or [])
                    if not appearances:
                        if history["required"]:
                            raise ValueError(
                                f"required wire {logical_widget_id}.{wire_name} "
                                f"has no prior source {source_id!r}"
                            )
                        continue

                    if history["select"] == "latest":
                        selected = [appearances[-1]]
                    else:
                        selected = appearances

                    for appearance in selected:
                        base_alias = safe_alias_v1(
                            logical_widget_id,
                            wire_name,
                            source_id,
                            history["select"],
                            appearance.step_id,
                        )
                        alias = unique_alias_v1(base_alias, k["history_queries"])

                        k["history_queries"][alias] = {
                            "from_step": appearance.step_id,
                            "datum_id": appearance.datum_id,
                            "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                            "include_value": True,
                            "required": bool(history["required"]),
                            "select": history["select"],
                            "max_results": int(history["max_results"]),
                        }
                        aliases.append(alias)

                multiplicity = str(
                    dict(wire_contract[wire_name]).get("multiplicity") or "one"
                )
                if aliases:
                    if multiplicity == "one" and len(aliases) != 1:
                        raise ValueError(
                            f"wire {logical_widget_id}.{wire_name} requires exactly one "
                            f"resolved alias, got {len(aliases)}"
                        )
                    past_wires[wire_name] = aliases
                elif bool(dict(wire_contract[wire_name]).get("required", False)):
                    raise ValueError(
                        f"wire {logical_widget_id}.{wire_name} is required by widget "
                        "contract but resolved no aliases"
                    )

            datum = {
                "id": logical_widget_id,
                "widget": widget_name,
                "title": title,
                "micros": [],
                "lifecycle": lifecycle,
                "past_wires": past_wires,
                "args": args,
                "tags": tags,
                "roles": roles,
                "system_flags": system_flags,
                "authoritative": (
                    authoritative[widget_position]
                    if authoritative is not None
                    else bool(base["authoritative"])
                ),
            }

            k["datums"].append(datum)
            current_appearances.append(
                AppearanceV1(
                    logical_widget_id=logical_widget_id,
                    step_id=step_id,
                    datum_id=logical_widget_id,
                )
            )

        authoritative_count = sum(
            1
            for datum in k["datums"]
            if bool(datum.get("authoritative", True))
        )
        if authoritative_count < 1:
            raise ValueError(
                f"flow {flow_id!r} lowers to a span with no authoritative datums; "
                "the current multiframespec runtime requires at least one "
                "authoritative datum per generated span"
            )

        explicit.append(k)

        for appearance in current_appearances:
            prior.setdefault(appearance.logical_widget_id, []).append(appearance)

    return validate_kernel_program_v1(explicit)