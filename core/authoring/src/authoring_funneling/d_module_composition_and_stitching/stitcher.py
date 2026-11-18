from __future__ import annotations

"""
authoring_funneling.d_module_composition_and_stitching.stitcher
==============================================================
The Core Module Stitcher & Flow Lowerer for Thinkument programs.
Lowers imported (P x C x SM) modules into a flat, verified, typed program
governed by the 3 formal laws of SM composition and hermetic parameter scoping.
"""

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from bindings2bindingsTM import CompilationError
from .manifest import normalize_think_module_v1
from .registry import ModuleCatalogRegistry
from .stitching_registry import SMPocketStitchingPolicy, SMPocketStitchingRegistry

MAX_IMPORT_DEPTH = 8


def stitch_program_modules(
    program: Mapping[str, Any],
    *,
    session_metadata: Optional[Mapping[str, Any]] = None,
    catalog: Optional[Any] = None,
    _depth: int = 0,
    _call_stack: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Stitch and lower all imported (P x C) modules in a program and its SM.
    
    Args:
        program: The input program (e.g. unified_typed_jsonic_think_program_v1).
        session_metadata: Optional outer session metadata (SM).
        catalog: Optional module catalog (defaults to ModuleCatalogRegistry).
        _depth: Current recursion depth (internal guard).
        _call_stack: List of module references in current import chain for cycle detection.

    Returns:
        (stitched_program, stitched_session_metadata)
    """
    if _depth > MAX_IMPORT_DEPTH:
        raise CompilationError(
            "max_import_depth_exceeded",
            ("P", "import"),
            f"Module import recursion exceeded maximum depth of {MAX_IMPORT_DEPTH}",
        )

    cat = catalog or ModuleCatalogRegistry
    call_stack = list(_call_stack or [])

    p = deepcopy(dict(program))
    sm = deepcopy(dict(session_metadata or {}))

    if "run" in p and isinstance(p["run"], Mapping) and "program" in p["run"]:
        p_body = p["run"]["program"]
    else:
        p_body = p

    try:
        widgets = p_body["widgets"]
        flow = p_body["flow"]
    except (KeyError, TypeError) as exc:
        raise CompilationError("invalid_program", ("P",)) from exc

    if not isinstance(widgets, Mapping) or not isinstance(flow, list):
        raise CompilationError("invalid_program_structure", ("P",))

    lowered_widgets: Dict[str, Dict[str, Any]] = {}
    lowered_flow: List[Dict[str, Any]] = []

    # Map of exported aliases: e.g. "step_approval.verdict" -> "step_approval__review_step.reviewer_widget.outputs.verdict"
    export_projections: Dict[str, Dict[str, str]] = {}

    # 1. First process widgets table: resolve any 1-step leaf module imports in widgets
    for wid, wdecl in widgets.items():
        if not isinstance(wdecl, Mapping):
            raise CompilationError("invalid_widget", ("P", "widgets", wid))

        if "import" in wdecl:
            mod_ref = str(wdecl["import"]).strip()
            if mod_ref in call_stack:
                raise CompilationError("cyclic_import_error", ("P", "widgets", wid, "import"), f"Cyclic import: {' -> '.join(call_stack + [mod_ref])}")

            mod = cat.get_module(mod_ref)
            mod_p_body = mod["P"].get("run", {}).get("program", mod["P"])
            mod_flow = mod_p_body.get("flow", [])
            mod_widgets = mod_p_body.get("widgets", {})

            if len(mod_flow) != 1 or len(mod_widgets) != 1:
                raise CompilationError(
                    "compound_flow_in_step_error",
                    ("P", "widgets", wid, "import"),
                    f"Module {mod_ref!r} has {len(mod_flow)} steps and cannot be mounted as a single leaf widget node. Import it in flow instead.",
                )

            # Validate arguments against module interface
            args = _validate_and_bind_module_args(wdecl.get("args", {}), mod, ("P", "widgets", wid, "args"))
            role_map = dict(wdecl.get("role_map", {}))
            _validate_role_map(role_map, mod, ("P", "widgets", wid, "role_map"))

            # Single leaf widget extraction
            orig_wid, orig_wdecl = next(iter(mod_widgets.items()))
            cloned_wdecl = deepcopy(orig_wdecl)

            # Remap roles on the widget
            w_roles = list(cloned_wdecl.get("roles") or [])
            cloned_wdecl["roles"] = [role_map.get(r, r) for r in w_roles]

            # Merge args/parameters into config
            inner_w = cloned_wdecl.get("widget") or cloned_wdecl.get("inline_widget") or cloned_wdecl.get("inline")
            if isinstance(inner_w, Mapping):
                decl_args = inner_w.get("declaration", {}).get("args", {})
                for k, v in args.items():
                    if k in decl_args:
                        cloned_wdecl.setdefault("args", {})[k] = v

            # Retain outer bindings / wires if specified
            if "bindings" in wdecl:
                cloned_wdecl["bindings"] = deepcopy(wdecl["bindings"])

            lowered_widgets[wid] = cloned_wdecl
        else:
            lowered_widgets[wid] = deepcopy(wdecl)

    # 2. Process flow: resolve step-level subflow module imports
    seen_step_ids: Set[str] = set()

    for step_idx, step in enumerate(flow):
        if not isinstance(step, Mapping):
            raise CompilationError("invalid_flow", ("P", "flow", step_idx))

        if "import" in step:
            import_step_id = str(step.get("id") or f"import_{step_idx}").strip()
            mod_ref = str(step["import"]).strip()

            if mod_ref in call_stack:
                raise CompilationError("cyclic_import_error", ("P", "flow", step_idx, "import"), f"Cyclic import: {' -> '.join(call_stack + [mod_ref])}")

            mod = cat.get_module(mod_ref)
            args = _validate_and_bind_module_args(step.get("args", {}), mod, ("P", "flow", step_idx, "args"))
            role_map = dict(step.get("role_map", {}))
            _validate_role_map(role_map, mod, ("P", "flow", step_idx, "role_map"))

            # Recursively stitch inner module if it also has imports
            stitched_sub_p, stitched_sub_sm = stitch_program_modules(
                mod["P"],
                session_metadata=mod.get("SM", {}),
                catalog=cat,
                _depth=_depth + 1,
                _call_stack=call_stack + [mod_ref],
            )

            sub_p_body = stitched_sub_p.get("run", {}).get("program", stitched_sub_p)
            sub_widgets = sub_p_body.get("widgets", {})
            sub_flow = sub_p_body.get("flow", [])

            # Lower and namespace each widget in the imported module
            namespaced_widget_ids: Dict[str, str] = {}
            for sub_wid, sub_wdecl in sub_widgets.items():
                ns_wid = f"{import_step_id}__{sub_wid}"
                namespaced_widget_ids[sub_wid] = ns_wid

                cloned_wdecl = deepcopy(sub_wdecl)
                # Remap roles
                w_roles = list(cloned_wdecl.get("roles") or [])
                cloned_wdecl["roles"] = [role_map.get(r, r) for r in w_roles]

                # Merge bound module args into widget static config
                inner_w = cloned_wdecl.get("widget") or cloned_wdecl.get("inline_widget") or cloned_wdecl.get("inline")
                if isinstance(inner_w, Mapping):
                    decl_args = inner_w.get("declaration", {}).get("args", {})
                    for k, v in args.items():
                        if k in decl_args:
                            cloned_wdecl.setdefault("args", {})[k] = v

                lowered_widgets[ns_wid] = cloned_wdecl

            # Inline each step in the subflow
            for sub_step_idx, sub_step in enumerate(sub_flow):
                sub_step_id = str(sub_step.get("id") or f"sub_{sub_step_idx}").strip()
                ns_step_id = f"{import_step_id}__{sub_step_id}"

                if ns_step_id in seen_step_ids:
                    raise CompilationError("duplicate_step_id_error", ("P", "flow"), f"Duplicate step ID: {ns_step_id!r}")
                seen_step_ids.add(ns_step_id)

                stitched_sub_step = deepcopy(sub_step)
                stitched_sub_step["id"] = ns_step_id
                stitched_sub_step["widgets"] = [
                    namespaced_widget_ids.get(w, f"{import_step_id}__{w}")
                    for w in sub_step.get("widgets", [])
                ]

                # If this was the final step of the module, record export projections
                if sub_step_idx == len(sub_flow) - 1:
                    last_widget = stitched_sub_step["widgets"][-1] if stitched_sub_step["widgets"] else None
                    if last_widget:
                        for out_key in mod.get("interface", {}).get("outputs", {}).keys():
                            export_projections.setdefault(import_step_id, {})[out_key] = f"{last_widget}.{out_key}"

                lowered_flow.append(stitched_sub_step)
        else:
            step_id = str(step.get("id") or f"step_{step_idx}").strip()
            if step_id in seen_step_ids:
                raise CompilationError("duplicate_step_id_error", ("P", "flow", step_idx), f"Duplicate step ID: {step_id!r}")
            seen_step_ids.add(step_id)
            lowered_flow.append(deepcopy(step))

    # 3. Assemble lowered program
    p_body["widgets"] = lowered_widgets
    p_body["flow"] = lowered_flow

    # 4. Compose session metadata according to the 3 formal laws
    stitched_sm = _compose_session_metadata(sm)

    return p, stitched_sm


def _validate_and_bind_module_args(
    supplied_args: Mapping[str, Any],
    module: Mapping[str, Any],
    path: Tuple[str, ...],
) -> Dict[str, Any]:
    """Validate supplied args against module interface inputs and return bound parameters."""
    if not isinstance(supplied_args, Mapping):
        raise CompilationError("invalid_arguments", path, "Arguments must be a mapping")

    inputs_decl = module.get("interface", {}).get("inputs", {})
    defaults = module.get("C", {}).get("parameters", {})
    bound: Dict[str, Any] = {}

    # Check for unknown arguments
    for k in supplied_args.keys():
        if k not in inputs_decl:
            raise CompilationError("unknown_argument_error", (*path, k), f"Unknown argument {k!r} for module {module['name']!r}")

    # Check for required arguments and populate defaults
    for k, spec in inputs_decl.items():
        is_required = spec.get("required", False) if isinstance(spec, Mapping) else False
        if k in supplied_args:
            bound[k] = deepcopy(supplied_args[k])
        elif k in defaults:
            bound[k] = deepcopy(defaults[k])
        elif isinstance(spec, Mapping) and "default" in spec:
            bound[k] = deepcopy(spec["default"])
        elif is_required:
            raise CompilationError("missing_required_argument", (*path, k), f"Missing required argument {k!r} for module {module['name']!r}")

    return bound


def _validate_role_map(
    role_map: Mapping[str, str],
    module: Mapping[str, Any],
    path: Tuple[str, ...],
) -> None:
    """Validate that all mapped source roles exist in the module declaration."""
    mod_roles = module.get("interface", {}).get("roles", {})
    for src_role in role_map.keys():
        if src_role not in mod_roles:
            raise CompilationError("unknown_source_role_error", (*path, src_role), f"Role {src_role!r} is not declared by module {module['name']!r}. Declared: {list(mod_roles.keys())}")


def _compose_session_metadata(outer_sm: Mapping[str, Any]) -> Dict[str, Any]:
    """Compose outer session metadata enforcing Host Sovereign invariants."""
    res = deepcopy(dict(outer_sm))
    # Enforce defaults for sovereign physics if missing
    res.setdefault("manual_io", {"persistence": "disabled"})
    res.setdefault("session_storage", {"events_snapshot_window": 32})
    return res


__all__ = [
    "MAX_IMPORT_DEPTH",
    "stitch_program_modules",
]
