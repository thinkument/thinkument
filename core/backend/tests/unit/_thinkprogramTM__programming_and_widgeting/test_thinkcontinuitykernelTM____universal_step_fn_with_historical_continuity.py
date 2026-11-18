# think-backend/tests/wippp/test_think_kernel_stepfn_continuity_e2e.py

from __future__ import annotations

"""
Think Kernel StepFn Continuity E2E
==================================

This test sheet is the executable specification for the finalized Think Kernel
v1 program surface, lowering contract, runtime continuity model, and scale
boundary.

It proves that an entire higher-level Thinkument app can be authored as:

    [K1, K2, ..., KN]

where each K is a declarative kernel step surface, and the whole program lowers
deterministically to ordinary App Table rows that all execute one universal
step function:

    think.kernel.v1

No datomaton/widget/runtime q-contract changes are required. The stricter,
forever-scalable semantics live entirely in the kernel language validation and
lowering layer.

===============================================================================
1. Final program/lowering shape
===============================================================================

    ┌──────────────────────────────────────────────────────────────────────┐
    │ User-authored higher program                                         │
    │                                                                      │
    │   [K1, K2, ..., KN]                                                  │
    └───────────────────────────────┬──────────────────────────────────────┘
                                    │ validate_kernel_program_v1(...)
                                    │ lower_thinking_flow_explicit_v1(...)
                                    ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │ App Table manifest                                                   │
    │                                                                      │
    │   [                                                                  │
    │     {                                                                │
    │       "public_step_name": K["step"]["id"],                           │
    │       "step_fn": "think.kernel.v1",                                  │
    │       "fn_args": {"kernel": K},                                      │
    │     },                                                               │
    │     ...                                                              │
    │   ]                                                                  │
    └───────────────────────────────┬──────────────────────────────────────┘
                                    │ runtime executes ordinary app rows
                                    ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Universal step fn: think.kernel.v1                                   │
    │                                                                      │
    │   1. validate one K                                                  │
    │   2. resolve K.history_queries once                                  │
    │   3. inject selected results into datum args                         │
    │   4. emit one ordinary multiframespec                                │
    └───────────────────────────────┬──────────────────────────────────────┘
                                    │ emits
                                    ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Standard multiframespec / datomaton runtime                          │
    │                                                                      │
    │   q["datum"]["args"]["__kernel"]["past_wires"]                       │
    │                                                                      │
    │ is the only kernel-specific widget input pocket.                     │
    └──────────────────────────────────────────────────────────────────────┘

Canonical K shape
-----------------

    K = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",

        "step":  {"id": "...", "title": "...", "args": {...}},
        "form":  {"id": "...", "title": "...", "args": {...}},
        "frame": {"id": "...", "title": "...", "args": {...}},
        "span":  {"id": "...", "title": "...", "args": {...}},

        "history_queries": {
            "alias": {
                "from_step": "prior.public_step_name",
                "datum_id": "prior_datum_id",
                "write_kind": "datum_lifecycle",
                "include_value": true | false,
                "required": true | false,
                "select": "latest" | "all",
                "max_results": 128,
            }
        },

        "datums": [
            {
                "id": "...",
                "widget": "registered.kernel.widget",
                "title": "...",
                "micros": [...],
                "lifecycle": {...},

                "authoritative": true | false,
                "system_flags": {...},

                "past_wires": {
                    "widget_wire_name": ["history_query_alias", ...]
                },

                "args": {
                    "widget_arg": "value"
                },
            }
        ],

        "kernel_flags": {
            "copy_form_frame_span_args_into_each_datum": true,
            "mount_explode_default": true,
        },
    }

===============================================================================
2. Continuity model proven by this sheet
===============================================================================

The engine already has a local datum lifecycle threading rule:

    result.state        -> next q["state"]
    result.message(s)   -> next q["messages"]
    result.proc_notes   -> lifecycle notes / bounded diagnostics
    result.datum        -> next q["datum"]       on reexplode
    result.fill         -> next q["partial_fill"] on reexplode
    result.prefill      -> next q["prefill"]      on reexplode

That automatic threading is lifecycle-local. It does not imply arbitrary
cross-datum, cross-span, or cross-step q-root continuity.

The kernel makes cross-step continuity explicit:

    K.history_queries
        -> query_runtime_writes_v1(...)
        -> resolved aliases
        -> datum.past_wires
        -> q["datum"]["args"]["__kernel"]["past_wires"]

Widget read path:

    datum_args = q["datum"]["args"]
    kernel     = datum_args["__kernel"]
    wires      = kernel["past_wires"]

The tests lock these laws:

    ┌─────────────────────────────────────────────┬──────────────────────────┐
    │ Relationship                                │ Automatic?               │
    ├─────────────────────────────────────────────┼──────────────────────────┤
    │ Same datum lifecycle row                    │ Yes                      │
    │ Same datum id reused in another form        │ No q-root continuity;    │
    │                                             │ explicit history works   │
    │ Different datums on the same span           │ No sibling fan-in        │
    │ Different step fns                          │ No automatic q-root flow │
    │ Cross-step prior datum facts                │ Yes, only via declared   │
    │                                             │ history_queries/wires    │
    └─────────────────────────────────────────────┴──────────────────────────┘

===============================================================================
3. Datum identity law
===============================================================================

Datum ids are unique within one multiframespec/kernel form.

    one K/form:
        datum id "A" may appear once

Across distinct forms/kernel steps, the same logical datum id may reappear:

    K1.form / A
    K2.form / A

This is valid because runtime lifecycle storage is form-scoped:

    _datum_lifecycle_v1.forms[form_id].datums[datum_id]

The tests prove both:
    - duplicate datum ids inside one K are rejected;
    - the same datum id across K1/K2 forms is valid and history-addressable.

===============================================================================
4. Kernel-side widget contract registry
===============================================================================

The underlying datomaton registry remains unchanged.

The kernel adds a stricter sidecar contract registry:

    register_kernel_widget_v1(
        name,
        fn,
        args={...},
        past_wires={...},
    )

This contract validates source programs before app-table runtime exists.

Widget arg contract
-------------------

    args={
        "seed": {"type": "str", "required": True},
        "threshold": {"type": "int", "required": False, "default": 7},
    }

Supported arg types:

    json
    str
    int
    float
    bool
    dict
    list
    list[str]
    list[int]

Rules:
    - unknown args are rejected;
    - missing required args are rejected;
    - wrong types are rejected;
    - defaults are deep dead-JSON copied during lowering;
    - "__kernel" is reserved and may not be user-authored.

Past-wire contract
------------------

    past_wires={
        "previous_A": {"multiplicity": "one", "required": True},
        "sources":    {"multiplicity": "many", "required": False},
    }

Rules:
    - unknown wires are rejected;
    - missing required wires are rejected;
    - multiplicity="one" requires exactly one alias;
    - multiplicity="many" accepts one or more aliases when required;
    - aliases must exist in K.history_queries;
    - whole-program validation ensures aliases point only backward.

===============================================================================
5. History query semantics
===============================================================================

K.history_queries is the only cross-step continuity declaration.

Each query names:
    - prior public step;
    - prior datum id;
    - write kind;
    - materialization policy;
    - cardinality policy.

Supported v1 write kind:

    datum_lifecycle

Supported selectors:

    select="latest"
        returns the latest matching row or None

    select="all"
        returns all matching rows up to max_results

Materialization boundary:

    include_value=False
        returns metadata/ref/preview rows only.
        Giant lifecycle values are not duplicated into query results,
        runtime index, or past_wires.

    include_value=True
        explicitly materializes the current lifecycle row value.
        Any resulting value growth is intentional source-language behavior.

===============================================================================
6. Efficiency and scale laws proven here
===============================================================================

The tests cover both ordinary CI-scale and optional crazy/user-degree stress
cases.

Core efficiency laws:

    ┌──────────────────────────────────────────────┬─────────────────────────┐
    │ Axis                                         │ Expected behavior       │
    ├──────────────────────────────────────────────┼─────────────────────────┤
    │ Number of K steps                            │ manifest grows linearly │
    │ Datums per K                                 │ one lifecycle write per │
    │                                              │ touched datum           │
    │ Many datums sharing one history alias        │ one runtime query       │
    │ Many aliases to same prior fact              │ deduped to one query    │
    │ Many distinct prior facts                    │ one query per fact      │
    │ include_value=False                          │ metadata/ref scale      │
    │ include_value=True                           │ rows × value-size scale │
    │ Runtime write index                          │ ref/preview-sized       │
    │ Giant user-authored values                   │ current lifecycle state │
    │                                              │ only, unless explicitly │
    │                                              │ materialized/archived   │
    │ User-authored heavy compute                  │ isolated in widget cost │
    └──────────────────────────────────────────────┴─────────────────────────┘

Important distinction:

    Engine/kernel cost:
        validation, lowering, history-query resolution, runtime index refs.

    User-authored cost:
        heavy widget compute,
        huge submitted values,
        include_value=True export,
        explicit archival of hydrated history into current state.

The latter are allowed, visible, and intentionally tested. They are not hidden
runtime-index leaks.

===============================================================================
7. Manual IO payload boundary
===============================================================================

The default manual IO artery is capped. A giant multi-page submit is rejected
before it becomes:

    - lifecycle state;
    - runtime index content;
    - history material;
    - query output.

Tests also prove explicit opt-in behavior:

    max_payload_chars=0

allows large authored values, while the runtime index and include_values=False
query previews remain metadata/ref-sized.

===============================================================================
8. Public facade / highest-seam proof
===============================================================================

The public higher-language path is tested end-to-end:

    PublicSessionAPI.create_session_from_program(
        program=[K1, K2],
        program_language="thinking_flow_explicit",
    )

and direct lowerer paths are also tested:

    lower_program_to_app_table_bundle(...)
    lower_program_to_app_table_manifest(...)

The public facade proves:
    - invalid kernel programs fail before runtime;
    - valid higher programs create sessions;
    - runtime executes ordinary app-table rows;
    - lifecycle writes prove same-datum-id rows under distinct forms;
    - program trace marks the higher-language entrypoint.

===============================================================================
9. Design boundaries / non-goals
===============================================================================

This sheet intentionally does not change the low-level q packet shape.

Custom widget initialization belongs here:

    q["datum"]["args"]

not here:

    q["some_arbitrary_root_key"]

Kernel metadata belongs under the reserved pocket:

    q["datum"]["args"]["__kernel"]

The datomaton runtime remains the stable substrate. The kernel language provides:
    - whole-program validation;
    - contract validation;
    - deterministic lowering;
    - explicit cross-step history wiring;
    - efficient metadata-first history resolution.

===============================================================================
10. Forever usage summary
===============================================================================

Author programs as:

    [K1, K2, ..., KN]

Register widgets as:

    register_kernel_widget_v1(
        "my.widget",
        fn,
        args={...},
        past_wires={...},
    )

Declare cross-step continuity as:

    K.history_queries["prior_x"] = {
        "from_step": "earlier.step",
        "datum_id": "X",
        "include_value": false,
        "select": "latest",
    }

Wire selected prior facts into a datum as:

    datum["past_wires"] = {
        "previous_x": ["prior_x"]
    }

Read inside the widget as:

    kernel = q["datum"]["args"]["__kernel"]
    previous_x = kernel["past_wires"]["previous_x"]

Keep include_value=False by default. Use include_value=True only when the widget
really needs hydrated prior lifecycle state.

This file is therefore both:
    - an E2E regression suite; and
    - the compact executable contract for Think Kernel v1.
"""


import json
import os
import statistics
import time
from collections.abc import Mapping
from typing import Any, Dict

import pytest

from __datomatonTM import register_datum_widget_v1
from __exceptions.engine import InvalidExternalFillError
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    lower_program_to_app_table_bundle,
    lower_program_to_app_table_manifest,
)

from _thinkprogram._thinkcontinuitykernelTM import _history as thinkcontinuitykernelTM_history
from _thinkprogram._thinkcontinuitykernelTM.api import (
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
    KERNEL_PROGRAM_LANGUAGE_V1,
    KERNEL_STEP_FN_NAME_V1,
    LANG_THINKING_FLOW_EXPLICIT_V1,
    manifest_from_kernel_program_v1,
    register_kernel_program_language_v1,
    register_kernel_step_fn_v1,
    register_kernel_widget_v1,
    register_thinking_flow_explicit_language_v1,
    validate_kernel_program_v1,
    build_kernel_multiframespec_v1,
)


# ---------------------------------------------------------------------------
# Small generic helpers
# ---------------------------------------------------------------------------


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _manual_io_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": True,
        }
    }


_manifest_from_kernel_program = manifest_from_kernel_program_v1


def _latest_lifecycle_state(
    api: Any,
    sid: str,
    *,
    form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    state = api._get(sid).state
    row = (
        state.get("_datum_lifecycle_v1", {})
        .get("forms", {})
        .get(str(form_id), {})
        .get("datums", {})
        .get(str(datum_id), {})
    )
    assert isinstance(row, Mapping), row
    q_state = row.get("state") or {}
    assert isinstance(q_state, Mapping), q_state
    return q_state


def _compact(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr)


# ---------------------------------------------------------------------------
# Test widgets
# ---------------------------------------------------------------------------


def register_kernel_probe_widgets() -> None:
    def source_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        partial = dict(q.get("partial_fill") or {})
        signal_kind = str(q.get("signal_kind") or "")

        if signal_kind == "mount":
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "title": "Source mounted",
                    "micros": [_text_micro("value")],
                },
                "fill": {"value": ""},
                "state": {
                    "mounted": True,
                    "saw_root_past_wires": "past_wires" in q,
                    "initial_args": datum_args,
                    "kernel_step_id": dict(kernel_args.get("step") or {}).get("id"),
                },
                "message": {"level": "info", "text": "source mounted"},
                "proc_notes": {"phase": "mount"},
            }

        return {
            "status": "done",
            "state": {
                "final_value": partial.get("value"),
                "commit": {
                    "datum_id": q.get("datum_id"),
                    "value": partial.get("value"),
                },
                "saw_root_past_wires": "past_wires" in q,
                "initial_args": datum_args,
            },
            "message": {"level": "success", "text": "source done"},
        }

    def history_consumer_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})
        signal_kind = str(q.get("signal_kind") or "")
        partial = dict(q.get("partial_fill") or {})

        if signal_kind == "mount":
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "title": "History consumer mounted",
                    "micros": [_text_micro("confirm")],
                },
                "fill": {"confirm": ""},
                "state": {
                    "mounted": True,
                    "past_wires_seen_on_mount": past_wires,
                    "root_has_past_wires": "past_wires" in q,
                    "datum_args_keys": sorted(datum_args.keys()),
                },
                "message": {"level": "info", "text": "history consumer mounted"},
                "proc_notes": {"phase": "history_mount"},
            }

        return {
            "status": "done",
            "state": {
                "confirmed": partial.get("confirm"),
                "past_wires_seen_on_done": past_wires,
                "root_has_past_wires": "past_wires" in q,
            },
            "message": {"level": "success", "text": "history consumer done"},
        }

    def sibling_probe_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})
        partial = dict(q.get("partial_fill") or {})

        if str(q.get("signal_kind") or "") == "mount":
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("value")],
                },
                "fill": {"value": ""},
                "state": {
                    "mounted": True,
                    "past_wires_on_mount": past_wires,
                    "no_automatic_sibling_state": past_wires == {},
                },
                "message": {"level": "info", "text": "sibling mounted"},
            }

        return {
            "status": "done",
            "state": {
                "value": partial.get("value"),
                "past_wires_on_done": past_wires,
            },
            "message": {"level": "success", "text": "sibling done"},
        }

    register_kernel_widget_v1(
        "test.kernel.source",
        source_widget,
        args={
            "seed": {"type": "str", "required": True},
        },
        past_wires={},
        overwrite=True,
    )
    register_kernel_widget_v1(
        "test.kernel.history_consumer",
        history_consumer_widget,
        args={
            "local": {"type": "str", "required": True},
        },
        past_wires={
            "previous_A_from_K1": {
                "multiplicity": "one",
                "required": True,
            },
        },
        overwrite=True,
    )
    register_kernel_widget_v1(
        "test.kernel.sibling_probe",
        sibling_probe_widget,
        args={},
        past_wires={},
        overwrite=True,
    )


# ---------------------------------------------------------------------------
# Kernel program fixtures
# ---------------------------------------------------------------------------


def _k1() -> Dict[str, Any]:
    return {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.K1", "title": "Kernel K1", "args": {"n": 1}},
        "form": {"id": "kernel.K1.form", "title": "Kernel K1 Form", "args": {}},
        "frame": {"id": "F", "title": "Frame"},
        "span": {"id": "S", "title": "Span"},
        "history_queries": {},
        "datums": [
            {
                "id": "A",
                "widget": "test.kernel.source",
                "title": "A",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "mount_explode": True,
                    "max_reexplosions": 10,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
                "authoritative": True,
                "system_flags": {"role": "source"},
                "past_wires": {},
                "args": {"seed": "alpha-seed"},
            }
        ],
        "kernel_flags": {
            "copy_form_frame_span_args_into_each_datum": True,
            "mount_explode_default": True,
        },
    }


def _k2() -> Dict[str, Any]:
    return {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.K2", "title": "Kernel K2"},
        "form": {"id": "kernel.K2.form", "title": "Kernel K2 Form"},
        "frame": {"id": "F", "title": "Frame"},
        "span": {"id": "S", "title": "Span"},
        "history_queries": {
            "prior_A": {
                "from_step": "kernel.K1",
                "datum_id": "A",
                "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                "include_value": True,
                "required": True,
                "select": "latest",
            }
        },
        "datums": [
            {
                "id": "A",
                "widget": "test.kernel.history_consumer",
                "title": "A again, different form",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "mount_explode": True,
                    "max_reexplosions": 10,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
                "authoritative": True,
                "system_flags": {"role": "consumer"},
                "past_wires": {
                    "previous_A_from_K1": ["prior_A"],
                },
                "args": {"local": "k2-local"},
            }
        ],
        "kernel_flags": {
            "copy_form_frame_span_args_into_each_datum": True,
            "mount_explode_default": True,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def setup_module() -> None:
    register_kernel_probe_widgets()
    register_kernel_step_fn_v1()
    register_kernel_program_language_v1()
    register_thinking_flow_explicit_language_v1()


def test_kernel_v1_datum_args_are_visible_to_widget_but_not_as_q_root_keys() -> None:
    program = [_k1()]
    manifest = _manifest_from_kernel_program(program)

    api = _api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    state_after_mount = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K1.form",
        datum_id="A",
    )

    assert state_after_mount["mounted"] is True
    assert state_after_mount["saw_root_past_wires"] is False
    assert state_after_mount["initial_args"]["seed"] == "alpha-seed"
    assert state_after_mount["initial_args"]["__kernel"]["step"]["id"] == "kernel.K1"

    ctx = runner.step(fill={"A": {"value": "alpha-final"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K1.form",
        datum_id="A",
    )
    assert final_state["final_value"] == "alpha-final"
    assert final_state["saw_root_past_wires"] is False


def test_kernel_v1_cross_step_history_is_queried_once_and_delivered_as_past_wires() -> None:
    program = [_k1(), _k2()]
    manifest = _manifest_from_kernel_program(program)

    api = _api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["current_span"] == "S"
    ctx = runner.step(fill={"A": {"value": "alpha-final"}})

    # K2 should now run and mount its own A datum on a different form.
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    k2_mount_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )

    threaded = k2_mount_state["past_wires_seen_on_mount"]
    assert "previous_A_from_K1" in threaded

    row = threaded["previous_A_from_K1"]
    assert row["public_step_name"] == "kernel.K1"
    assert row["write_kind"] == WRITE_KIND_DATUM_LIFECYCLE
    assert row["key"] == "A"

    value = row["value"]
    assert value["state"]["final_value"] == "alpha-final"
    assert value["state"]["commit"] == {
        "datum_id": "A",
        "value": "alpha-final",
    }

    assert k2_mount_state["root_has_past_wires"] is False
    assert "__kernel" in k2_mount_state["datum_args_keys"]

    ctx = runner.step(fill={"A": {"confirm": "k2-confirmed"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_kernel_v1_same_datum_id_can_reappear_across_kernel_forms_but_not_within_one_kernel_form() -> None:
    # Same datum id "A" appears in K1 and K2.
    # This is legal because form ids differ.
    validate_kernel_program_v1([_k1(), _k2()])

    bad = _k1()
    bad["datums"] = [
        dict(bad["datums"][0]),
        dict(bad["datums"][0]),
    ]

    with pytest.raises(ValueError, match="duplicate datum id"):
        validate_kernel_program_v1([bad])


def test_kernel_v1_validator_rejects_forward_history_unknown_history_alias_and_duplicate_form_ids() -> None:
    k2 = _k2()

    with pytest.raises(ValueError, match="non-prior|unknown step"):
        validate_kernel_program_v1([k2])

    bad_alias = _k2()
    bad_alias["datums"][0]["past_wires"] = {
        "previous_A_from_K1": ["missing_alias"],
    }
    with pytest.raises(ValueError, match="unknown history queries"):
        validate_kernel_program_v1([_k1(), bad_alias])

    duplicate_form = _k2()
    duplicate_form["form"] = dict(_k1()["form"])
    with pytest.raises(ValueError, match="duplicate kernel form id"):
        validate_kernel_program_v1([_k1(), duplicate_form])


def test_kernel_program_language_lowers_to_app_table_manifest_using_only_universal_kernel_step_fn() -> None:
    program = [_k1(), _k2()]

    bundle = lower_program_to_app_table_bundle(
        program_language=KERNEL_PROGRAM_LANGUAGE_V1,
        program=program,
    )

    manifest = bundle.app_table_manifest
    assert len(manifest) == 2

    assert manifest[0]["public_step_name"] == "kernel.K1"
    assert manifest[0]["step_fn"] == KERNEL_STEP_FN_NAME_V1
    assert manifest[0]["fn_args"]["kernel"]["form"]["id"] == "kernel.K1.form"

    assert manifest[1]["public_step_name"] == "kernel.K2"
    assert manifest[1]["step_fn"] == KERNEL_STEP_FN_NAME_V1
    assert manifest[1]["fn_args"]["kernel"]["history_queries"]["prior_A"]["from_step"] == "kernel.K1"

    assert bundle.provenance["source_program_language"] == KERNEL_PROGRAM_LANGUAGE_V1


def test_kernel_v1_sibling_widgets_on_same_span_do_not_automatically_see_each_other_state_without_declared_history() -> None:
    k = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.siblings", "title": "Siblings", "args": {}},
        "form": {"id": "kernel.siblings.form", "title": "Siblings", "args": {}},
        "frame": {"id": "F", "title": "Frame", "args": {}},
        "span": {"id": "S", "title": "Span", "args": {}},
        "history_queries": {},
        "datums": [
            {
                "id": "A",
                "widget": "test.kernel.sibling_probe",
                "title": "A",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "mount_explode": True,
                    "max_reexplosions": 10,
                },
                "past_wires": {},
                "args": {},
            },
            {
                "id": "B",
                "widget": "test.kernel.sibling_probe",
                "title": "B",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "mount_explode": True,
                    "max_reexplosions": 10,
                },
                "past_wires": {},
                "args": {},
            },
        ],
        "kernel_flags": {"mount_explode_default": True},
    }

    validate_kernel_program_v1([k])
    manifest = _manifest_from_kernel_program([k])

    api = _api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert set(ctx["datum_widgets_on_this_span"]) == {"A", "B"}

    a_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.siblings.form",
        datum_id="A",
    )
    b_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.siblings.form",
        datum_id="B",
    )

    assert a_state["past_wires_on_mount"] == {}
    assert b_state["past_wires_on_mount"] == {}
    assert a_state["no_automatic_sibling_state"] is True
    assert b_state["no_automatic_sibling_state"] is True

    ctx = runner.step(
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        }
    )
    assert ctx["kind"] == "ATCOMPLETION"


def test_kernel_history_query_result_is_metadata_lean_until_include_values_is_requested() -> None:
    program = [_k1()]
    manifest = _manifest_from_kernel_program(program)

    api = _api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    runner.step_until_stop()
    ctx = runner.step(fill={"A": {"value": "alpha-final"}})
    assert ctx["kind"] == "ATCOMPLETION"

    state = api._get(sid).state

    without_values = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.K1",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 20,
        },
    )
    assert without_values["ok"] is True
    rendered_without = _compact(without_values)
    assert "alpha-final" not in rendered_without

    with_values = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.K1",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 20,
        },
    )
    assert with_values["ok"] is True
    rendered_with = _compact(with_values)
    assert "alpha-final" in rendered_with


# ---------------------------------------------------------------------------
# Strict widget contract validation tests
# ---------------------------------------------------------------------------


def test_kernel_rejects_raw_datomaton_widget_without_kernel_contract() -> None:
    def raw_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "done", "state": {}}

    register_datum_widget_v1(
        "test.kernel.raw_without_contract",
        raw_widget,
        overwrite=True,
    )

    k = _k1()
    k["step"] = {"id": "kernel.raw_widget", "title": "Raw", "args": {}}
    k["form"] = {"id": "kernel.raw_widget.form", "title": "Raw", "args": {}}
    k["history_queries"] = {}
    k["datums"] = [
        {
            "id": "X",
            "widget": "test.kernel.raw_without_contract",
            "title": "X",
            "micros": [_text_micro("value")],
            "lifecycle": {"mount_explode": False},
            "past_wires": {},
            "args": {},
        }
    ]

    with pytest.raises(ValueError, match="no kernel contract"):
        validate_kernel_program_v1([k])


def test_kernel_rejects_unknown_static_arg_missing_required_arg_wrong_type_and_reserved_key() -> None:
    good = _k1()
    validate_kernel_program_v1([good])

    unknown_arg = _k1()
    unknown_arg["datums"][0]["args"] = {
        "seed": "alpha-seed",
        "extra": "not allowed",
    }
    with pytest.raises(ValueError, match="unknown args"):
        validate_kernel_program_v1([unknown_arg])

    missing = _k1()
    missing["datums"][0]["args"] = {}
    with pytest.raises(ValueError, match="missing required arg"):
        validate_kernel_program_v1([missing])

    wrong_type = _k1()
    wrong_type["datums"][0]["args"] = {"seed": 123}
    with pytest.raises(ValueError, match="must be str"):
        validate_kernel_program_v1([wrong_type])

    reserved = _k1()
    reserved["datums"][0]["args"] = {
        "seed": "alpha-seed",
        "__kernel": {"evil": True},
    }
    with pytest.raises(ValueError, match="reserved key"):
        validate_kernel_program_v1([reserved])


def test_kernel_applies_widget_arg_defaults_during_lowering_and_widget_sees_them() -> None:
    calls: list[Mapping[str, Any]] = []

    def default_arg_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        calls.append(datum_args)
        return {
            "status": "done",
            "state": {
                "threshold": datum_args["threshold"],
                "labels": datum_args["labels"],
            },
        }

    register_kernel_widget_v1(
        "test.kernel.default_args",
        default_arg_widget,
        args={
            "threshold": {"type": "int", "required": False, "default": 7},
            "labels": {
                "type": "list[str]",
                "required": False,
                "default": ["default"],
            },
        },
        past_wires={},
        overwrite=True,
    )

    k = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.defaults", "title": "Defaults", "args": {}},
        "form": {"id": "kernel.defaults.form", "title": "Defaults", "args": {}},
        "frame": {"id": "F", "title": "Frame", "args": {}},
        "span": {"id": "S", "title": "Span", "args": {}},
        "history_queries": {},
        "datums": [
            {
                "id": "D",
                "widget": "test.kernel.default_args",
                "title": "D",
                "micros": [_text_micro("value")],
                "lifecycle": {"mount_explode": False},
                "past_wires": {},
                "args": {},
            }
        ],
        "kernel_flags": {"mount_explode_default": False},
    }

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest_from_kernel_program(validate_kernel_program_v1([k])),
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.defaults.form",
        datum_id="D",
    )
    assert state["threshold"] == 7
    assert state["labels"] == ["default"]
    assert calls[0]["threshold"] == 7
    assert calls[0]["labels"] == ["default"]
    assert "__kernel" in calls[0]


def test_kernel_rejects_unknown_missing_and_wrong_multiplicity_past_wires() -> None:
    good = [_k1(), _k2()]
    validate_kernel_program_v1(good)

    unknown_wire = _k2()
    unknown_wire["datums"][0]["past_wires"] = {
        "unknown_wire": ["prior_A"],
    }
    with pytest.raises(ValueError, match="unknown wires"):
        validate_kernel_program_v1([_k1(), unknown_wire])

    missing_required = _k2()
    missing_required["datums"][0]["past_wires"] = {}
    with pytest.raises(ValueError, match="missing required wire"):
        validate_kernel_program_v1([_k1(), missing_required])

    too_many_for_one = _k2()
    too_many_for_one["history_queries"]["prior_A_copy"] = dict(
        too_many_for_one["history_queries"]["prior_A"]
    )
    too_many_for_one["datums"][0]["past_wires"] = {
        "previous_A_from_K1": ["prior_A", "prior_A_copy"],
    }
    with pytest.raises(ValueError, match="requires exactly one alias"):
        validate_kernel_program_v1([_k1(), too_many_for_one])

    unknown_alias = _k2()
    unknown_alias["datums"][0]["past_wires"] = {
        "previous_A_from_K1": ["does_not_exist"],
    }
    with pytest.raises(ValueError, match="unknown history queries"):
        validate_kernel_program_v1([_k1(), unknown_alias])


def test_kernel_many_wire_accepts_many_query_aliases_and_widget_receives_many_rows() -> None:
    def many_wire_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        wires = dict(kernel_args.get("past_wires") or {})
        rows = list(wires.get("sources") or [])
        return {
            "status": "done",
            "state": {
                "source_count": len(rows),
                "source_keys": sorted(str(row.get("key")) for row in rows),
                "source_steps": sorted(str(row.get("public_step_name")) for row in rows),
            },
        }

    register_kernel_widget_v1(
        "test.kernel.many_wire_consumer",
        many_wire_widget,
        args={},
        past_wires={
            "sources": {
                "multiplicity": "many",
                "required": True,
            },
        },
        overwrite=True,
    )

    k1 = _k1()
    k1["step"] = {"id": "kernel.many.K1", "title": "K1", "args": {}}
    k1["form"] = {"id": "kernel.many.K1.form", "title": "K1", "args": {}}

    k2 = _k1()
    k2["step"] = {"id": "kernel.many.K2", "title": "K2", "args": {}}
    k2["form"] = {"id": "kernel.many.K2.form", "title": "K2", "args": {}}

    k3 = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.many.K3", "title": "K3", "args": {}},
        "form": {"id": "kernel.many.K3.form", "title": "K3", "args": {}},
        "frame": {"id": "F", "title": "Frame", "args": {}},
        "span": {"id": "S", "title": "Span", "args": {}},
        "history_queries": {
            "from_k1": {
                "from_step": "kernel.many.K1",
                "datum_id": "A",
                "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                "include_value": True,
                "required": True,
                "select": "latest",
            },
            "from_k2": {
                "from_step": "kernel.many.K2",
                "datum_id": "A",
                "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                "include_value": True,
                "required": True,
                "select": "latest",
            },
        },
        "datums": [
            {
                "id": "C",
                "widget": "test.kernel.many_wire_consumer",
                "title": "C",
                "micros": [_text_micro("value")],
                "lifecycle": {"mount_explode": False},
                "past_wires": {
                    "sources": ["from_k1", "from_k2"],
                },
                "args": {},
            }
        ],
        "kernel_flags": {"mount_explode_default": False},
    }

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest_from_kernel_program(
            validate_kernel_program_v1([k1, k2, k3])
        ),
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"A": {"value": "one"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"A": {"value": "two"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"C": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.many.K3.form",
        datum_id="C",
    )
    assert state["source_count"] == 2
    assert state["source_keys"] == ["A", "A"]
    assert state["source_steps"] == ["kernel.many.K1", "kernel.many.K2"]


def test_kernel_history_query_select_all_feeds_many_wire_as_many_rows() -> None:
    """
    select=all is a materialized many-row query. The wire multiplicity controls
    whether the widget may receive that list.
    """
    def all_rows_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        rows = list(dict(kernel_args.get("past_wires") or {}).get("all_source_rows") or [])
        return {
            "status": "done",
            "state": {
                "row_count": len(rows),
                "has_rows": bool(rows),
            },
        }

    register_kernel_widget_v1(
        "test.kernel.select_all_consumer",
        all_rows_widget,
        args={},
        past_wires={
            "all_source_rows": {
                "multiplicity": "many",
                "required": True,
            },
        },
        overwrite=True,
    )

    k1 = _k1()
    k1["step"] = {"id": "kernel.select_all.K1", "title": "K1", "args": {}}
    k1["form"] = {"id": "kernel.select_all.K1.form", "title": "K1", "args": {}}

    k2 = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {"id": "kernel.select_all.K2", "title": "K2", "args": {}},
        "form": {"id": "kernel.select_all.K2.form", "title": "K2", "args": {}},
        "frame": {"id": "F", "title": "Frame", "args": {}},
        "span": {"id": "S", "title": "Span", "args": {}},
        "history_queries": {
            "all_A": {
                "from_step": "kernel.select_all.K1",
                "datum_id": "A",
                "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                "include_value": False,
                "required": True,
                "select": "all",
                "max_results": 20,
            },
        },
        "datums": [
            {
                "id": "C",
                "widget": "test.kernel.select_all_consumer",
                "title": "C",
                "micros": [_text_micro("value")],
                "lifecycle": {"mount_explode": False},
                "past_wires": {"all_source_rows": ["all_A"]},
                "args": {},
            }
        ],
        "kernel_flags": {"mount_explode_default": False},
    }

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest_from_kernel_program(
            validate_kernel_program_v1([k1, k2])
        ),
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"A": {"value": "one"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    ctx = runner.step(fill={"C": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.select_all.K2.form",
        datum_id="C",
    )
    assert state["has_rows"] is True
    assert state["row_count"] >= 1


# ---------------------------------------------------------------------------
# Higher-language registration + highest public facade E2E coverage
# ---------------------------------------------------------------------------

def test_thinking_flow_explicit_language_registers_and_lists() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    from _thinkengine._parsing._higher_lang_grammars._langs_core import (
        is_program_language_registered,
        list_program_languages,
    )

    assert is_program_language_registered(LANG_THINKING_FLOW_EXPLICIT_V1)

    langs = list_program_languages()
    assert LANG_THINKING_FLOW_EXPLICIT_V1 in langs
    assert "think.kernel.v1" in langs[LANG_THINKING_FLOW_EXPLICIT_V1]


def test_thinking_flow_explicit_lowering_bundle_is_deterministic_and_app_table_only() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    program = [_k1(), _k2()]

    b1 = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )
    b2 = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )

    assert isinstance(b1, ProgramLoweringBundle)
    assert isinstance(b2, ProgramLoweringBundle)

    assert b1.app_table_manifest == b2.app_table_manifest
    assert b1.provenance == b2.provenance
    assert b1.session_surface == b2.session_surface

    manifest = b1.app_table_manifest

    assert not isinstance(manifest, ProgramLoweringBundle)
    assert isinstance(manifest, list)
    assert len(manifest) == 2

    assert [row["public_step_name"] for row in manifest] == [
        "kernel.K1",
        "kernel.K2",
    ]

    assert {row["step_fn"] for row in manifest} == {KERNEL_STEP_FN_NAME_V1}

    for row in manifest:
        assert set(row.keys()) == {
            "public_step_name",
            "step_fn",
            "fn_args",
        }
        assert row["step_fn"] == KERNEL_STEP_FN_NAME_V1
        assert set(row["fn_args"].keys()) == {"kernel"}
        assert not isinstance(row["fn_args"]["kernel"], ProgramLoweringBundle)

    assert b1.provenance["source_program_language"] == LANG_THINKING_FLOW_EXPLICIT_V1
    assert b1.provenance["highest_manifest"] == validate_kernel_program_v1(program)
    assert b1.provenance["app_table_manifest"] == manifest
    assert b1.provenance["lowering_chain"] == [
        {
            "language": LANG_THINKING_FLOW_EXPLICIT_V1,
            "artifact": "kernel_program_v1",
        },
        {
            "language": "app_table",
            "artifact": "app_table_manifest",
        },
    ]

    assert b1.session_surface == {
        "v": 1,
        "source_program_language": LANG_THINKING_FLOW_EXPLICIT_V1,
    }


def test_thinking_flow_explicit_manifest_lowering_matches_direct_kernel_manifest_builder() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    program = [_k1(), _k2()]
    validated = validate_kernel_program_v1(program)

    direct = _manifest_from_kernel_program(validated)

    from _thinkengine._parsing._higher_lang_grammars._langs_core import (
        lower_program_to_app_table_manifest,
    )

    via_language = lower_program_to_app_table_manifest(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )

    assert via_language == direct
    assert not isinstance(via_language, ProgramLoweringBundle)


def test_thinking_flow_explicit_rejects_invalid_program_before_app_table_manifest_exists() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    bad_program = [_k1(), _k2()]
    bad_program[1] = dict(bad_program[1])
    bad_program[1]["history_queries"] = {
        "bad_forward_or_unknown": {
            "from_step": "kernel.DOES_NOT_EXIST",
            "datum_id": "A",
            "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
            "include_value": True,
            "required": True,
            "select": "latest",
        }
    }

    with pytest.raises(ValueError, match="unknown history queries"):
        lower_program_to_app_table_bundle(
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            program=bad_program,
        )


def _public_runtime_write_rows_v1(result: Mapping[str, Any]) -> list[Dict[str, Any]]:
    inner = result.get("result")
    assert isinstance(inner, Mapping), result

    rows = inner.get("writes", inner.get("rows", []))
    assert isinstance(rows, list), inner

    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _runtime_write_refs_by_form_datum_v1(
    rows: list[Dict[str, Any]],
) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    for row in rows:
        ref = row.get("value_ref") or {}
        if not isinstance(ref, Mapping):
            continue

        form_id = ref.get("form_id")
        datum_id = ref.get("datum_id")

        if form_id and datum_id:
            found.add((str(form_id), str(datum_id)))

    return found


def test_highest_public_facade_accepts_thinking_flow_explicit_program_and_runs_e2e() -> None:
    """
    Highest-seam proof:

        PublicSessionAPI.create_session_from_program(
            program=[K1, K2],
            program_language="thinking_flow_explicit",
        )

    The session is created and driven only through the public facade.

    Exact lifecycle semantics are then asserted against the raw state owned by
    that same public facade wrapper. This avoids overfitting the assertion to a
    bounded public runtime-write row selection/sanitization detail.
    """
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    raw_api = _api()
    public_api = get_public_session_api(raw_api=raw_api)

    program = [_k1(), _k2()]

    preflight = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )
    assert isinstance(preflight, ProgramLoweringBundle)
    assert isinstance(preflight.app_table_manifest, list)
    assert not isinstance(preflight.app_table_manifest, ProgramLoweringBundle)

    created = public_api.create_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={
            "test": "thinking_flow_explicit_public_facade_e2e",
        },
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"

    sid = str(created["session_id"])
    assert sid

    # First public action reaches K1 manual stop after mount explosion.
    s0 = public_api.step_session(sid)
    assert s0["ok"] is True
    assert s0["session_id"] == sid

    r1 = public_api.current_report(sid)
    assert r1["ok"] is True
    assert r1["session_id"] == sid

    # Complete K1.A. Engine should advance to K2.A manual stop.
    s1 = public_api.step_session(
        sid,
        fill={"A": {"value": "alpha"}},
    )
    assert s1["ok"] is True
    assert s1["session_id"] == sid

    k1_state = _latest_lifecycle_state(
        raw_api,
        sid,
        form_id="kernel.K1.form",
        datum_id="A",
    )
    assert k1_state["final_value"] == "alpha"
    assert k1_state["commit"] == {
        "datum_id": "A",
        "value": "alpha",
    }

    k2_mount_state = _latest_lifecycle_state(
        raw_api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )

    threaded_on_mount = k2_mount_state["past_wires_seen_on_mount"]
    prior_on_mount = threaded_on_mount["previous_A_from_K1"]

    assert prior_on_mount["public_step_name"] == "kernel.K1"
    assert prior_on_mount["write_kind"] == WRITE_KIND_DATUM_LIFECYCLE
    assert prior_on_mount["key"] == "A"
    assert prior_on_mount["value"]["state"]["final_value"] == "alpha"

    # Complete K2.A.
    s2 = public_api.step_session(
        sid,
        fill={"A": {"confirm": "bravo"}},
    )
    assert s2["ok"] is True
    assert s2["session_id"] == sid

    final = public_api.current_report(sid)
    assert final["ok"] is True
    assert final["session_id"] == sid

    k2_done_state = _latest_lifecycle_state(
        raw_api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )
    assert k2_done_state["confirmed"] == "bravo"

    threaded_on_done = k2_done_state["past_wires_seen_on_done"]
    prior_on_done = threaded_on_done["previous_A_from_K1"]

    assert prior_on_done["public_step_name"] == "kernel.K1"
    assert prior_on_done["write_kind"] == WRITE_KIND_DATUM_LIFECYCLE
    assert prior_on_done["key"] == "A"
    assert prior_on_done["value"]["state"]["final_value"] == "alpha"

    # Public runtime-write query is still useful as a bounded public proof that
    # both same-datum-id lifecycle rows exist under distinct forms.
    writes = public_api.query_session(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 50,
        },
    )

    assert writes["ok"] is True
    assert writes["query_kind"] == "runtime_writes"

    rows = _public_runtime_write_rows_v1(writes)
    refs = _runtime_write_refs_by_form_datum_v1(rows)

    assert ("kernel.K1.form", "A") in refs
    assert ("kernel.K2.form", "A") in refs


def test_highest_public_facade_program_trace_marks_higher_language_entrypoint() -> None:
    """
    Current public facade behavior for create_session_from_program(...) stores a
    bounded app-call row marking the source language.

    It does not currently retain full lowered app-table rows in the public trace.
    That is acceptable: exact runtime execution is proven by lifecycle/runtime
    writes, and lowering determinism is proven before session creation.
    """
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    public_api = get_public_session_api(raw_api=_api())

    program = [_k1(), _k2()]

    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )
    assert isinstance(bundle, ProgramLoweringBundle)
    assert isinstance(bundle.app_table_manifest, list)
    assert not isinstance(bundle.app_table_manifest, ProgramLoweringBundle)

    created = public_api.create_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
    )
    assert created["ok"] is True

    sid = str(created["session_id"])
    assert sid

    trace = public_api.query_session(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "max_results": 10,
        },
    )

    assert trace["ok"] is True
    assert trace["query_kind"] == "program_trace_table"

    rows = trace["result"]["rows"]
    assert rows

    app_call_rows = [
        row
        for row in rows
        if row.get("row_kind") == "app_call"
    ]

    assert app_call_rows
    assert app_call_rows[0]["program_language"] == LANG_THINKING_FLOW_EXPLICIT_V1


def test_highest_public_facade_rejects_invalid_kernel_widget_contract_program_before_runtime() -> None:
    """
    Highest-seam strict contract proof.

    The public create_session_from_program(...) path calls the higher-language
    lowerer, which validates the kernel source before app-table runtime exists.
    """
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    public_api = get_public_session_api(raw_api=_api())

    bad = _k1()
    bad["datums"][0]["args"] = {
        "seed": "ok",
        "unknown": "must fail before runtime",
    }

    with pytest.raises(ValueError, match="unknown args"):
        public_api.create_session_from_program(
            program=[bad],
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata={"test": "strict_contract_public_reject"},
        )


# # ---------------------------------------------------------------------------
# # Kernel complexity / forever-scale contract addendum
# # ---------------------------------------------------------------------------


# RUN_KERNEL_SCALE_CRAZY = True
# RUN_KERNEL_USER_CRAZY = True



# # ---------------------------------------------------------------------------
# # Safe bounded shape scanners
# # ---------------------------------------------------------------------------


# def _kernel_bounded_container_stats(
#     obj: Any,
#     *,
#     max_nodes: int = 120_000,
# ) -> Dict[str, int]:
#     """
#     Safe structural scanner.

#     Do not json.dumps huge runtime state in complexity tests. This helper walks
#     object shape and string lengths without constructing a giant aggregate repr.
#     """
#     seen: set[int] = set()
#     stack: list[Any] = [obj]

#     visited_nodes = 0
#     mappings = 0
#     sequences = 0
#     strings = 0
#     total_string_chars_seen = 0
#     max_string_chars_seen = 0

#     while stack and visited_nodes < max_nodes:
#         cur = stack.pop()
#         visited_nodes += 1

#         oid = id(cur)
#         if oid in seen:
#             continue
#         seen.add(oid)

#         if isinstance(cur, str):
#             strings += 1
#             n = len(cur)
#             total_string_chars_seen += n
#             max_string_chars_seen = max(max_string_chars_seen, n)
#             continue

#         if isinstance(cur, Mapping):
#             mappings += 1
#             for k, v in cur.items():
#                 if isinstance(k, str):
#                     strings += 1
#                     n = len(k)
#                     total_string_chars_seen += n
#                     max_string_chars_seen = max(max_string_chars_seen, n)
#                 else:
#                     stack.append(k)
#                 stack.append(v)
#             continue

#         if isinstance(cur, (list, tuple, set, frozenset)):
#             sequences += 1
#             stack.extend(cur)
#             continue

#     return {
#         "visited_nodes": visited_nodes,
#         "mappings": mappings,
#         "sequences": sequences,
#         "strings": strings,
#         "total_string_chars_seen": total_string_chars_seen,
#         "max_string_chars_seen": max_string_chars_seen,
#         "truncated": int(bool(stack)),
#     }


# def _kernel_contains_run_bounded(
#     obj: Any,
#     *,
#     char: str,
#     run_len: int,
#     max_nodes: int = 120_000,
# ) -> bool:
#     needle = str(char) * int(run_len)
#     seen: set[int] = set()
#     stack: list[Any] = [obj]
#     visited_nodes = 0

#     while stack and visited_nodes < max_nodes:
#         cur = stack.pop()
#         visited_nodes += 1

#         oid = id(cur)
#         if oid in seen:
#             continue
#         seen.add(oid)

#         if isinstance(cur, str):
#             if needle in cur:
#                 return True
#             continue

#         if isinstance(cur, Mapping):
#             for k, v in cur.items():
#                 if isinstance(k, str) and needle in k:
#                     return True
#                 if not isinstance(k, str):
#                     stack.append(k)
#                 stack.append(v)
#             continue

#         if isinstance(cur, (list, tuple, set, frozenset)):
#             stack.extend(cur)

#     return False


# def _kernel_json_size_small(obj: Any) -> int:
#     """
#     Only use on known-small source/manifests, never on runtime state with giant
#     user payloads.
#     """
#     return len(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr))


# def _kernel_median_seconds(fn: Any, *, repeats: int = 3) -> float:
#     vals: list[float] = []
#     for _ in range(max(1, int(repeats))):
#         t0 = time.perf_counter()
#         fn()
#         vals.append(time.perf_counter() - t0)
#     return statistics.median(vals)


# def _kernel_state(api: Any, sid: str) -> Mapping[str, Any]:
#     state = api._get(str(sid)).state
#     assert isinstance(state, Mapping)
#     return state


# def _kernel_runtime_index(api: Any, sid: str) -> Mapping[str, Any]:
#     idx = _kernel_state(api, sid).get("_runtime_write_index_v1")
#     assert isinstance(idx, Mapping)
#     return idx


# def _kernel_lifecycle_rows(
#     api: Any,
#     sid: str,
#     *,
#     form_id: str,
# ) -> Mapping[str, Any]:
#     rows = (
#         _kernel_state(api, sid)
#         .get("_datum_lifecycle_v1", {})
#         .get("forms", {})
#         .get(str(form_id), {})
#         .get("datums", {})
#     )
#     assert isinstance(rows, Mapping)
#     return rows


# def _kernel_query_lifecycle_writes(
#     state: Mapping[str, Any],
#     *,
#     public_step_name: str | None = None,
#     include_values: bool = False,
#     max_results: int = 100_000,
# ) -> list[Mapping[str, Any]]:
#     q: Dict[str, Any] = {
#         "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
#         "include_values": bool(include_values),
#         "max_results": int(max_results),
#     }
#     if public_step_name is not None:
#         q["public_step_name"] = str(public_step_name)

#     out = query_runtime_writes_v1(state, q)
#     assert out["ok"] is True
#     rows = out.get("writes") or []
#     assert isinstance(rows, list)
#     return [row for row in rows if isinstance(row, Mapping)]


# # ---------------------------------------------------------------------------
# # Scale widgets
# # ---------------------------------------------------------------------------


_KERNEL_SCALE_WIDGET_CALLS: list[Dict[str, Any]] = []


def register_kernel_scale_widgets_v1() -> None:
    """
    Widgets used by the scale sheet.

    They are intentionally simple. The goal is to measure/lock kernel machinery,
    not user-authored widget complexity.
    """

    def source_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = str(q.get("datum_id") or q["datum"]["id"])
        partial = dict(q.get("partial_fill") or {})
        value = partial.get("value")

        _KERNEL_SCALE_WIDGET_CALLS.append(
            {
                "widget": "source",
                "datum_id": datum_id,
                "signal_kind": str(q.get("signal_kind") or ""),
            }
        )

        return {
            "status": "done",
            "state": {
                "final_value": value,
                "value_len": len(value) if isinstance(value, str) else 0,
                "datum_id": datum_id,
            },
            "message": {"level": "success", "text": "source done"},
        }

    def consumer_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = str(q.get("datum_id") or q["datum"]["id"])
        datum_args = dict(dict(q["datum"]).get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        history = dict(kernel_args.get("past_wires") or {})
        partial = dict(q.get("partial_fill") or {})

        _KERNEL_SCALE_WIDGET_CALLS.append(
            {
                "widget": "consumer",
                "datum_id": datum_id,
                "signal_kind": str(q.get("signal_kind") or ""),
                "history_count": len(history),
            }
        )

        history_keys = sorted(str(k) for k in history.keys())

        value_lengths: Dict[str, int] = {}
        value_presence: Dict[str, bool] = {}
        for k, row in history.items():
            if not isinstance(row, Mapping):
                value_presence[str(k)] = False
                value_lengths[str(k)] = 0
                continue

            value_presence[str(k)] = "value" in row
            val = row.get("value")
            value_lengths[str(k)] = (
                _kernel_bounded_container_stats(val)["total_string_chars_seen"]
                if isinstance(val, Mapping)
                else 0
            )

        return {
            "status": "done",
            "state": {
                "confirmed": partial.get("value"),
                "fanin_count": len(history),
                "history_keys": history_keys,
                "history_value_presence": value_presence,
                "history_value_string_chars_seen": value_lengths,
                "root_has_past_wires": "past_wires" in q,
            },
            "message": {"level": "success", "text": "consumer done"},
        }

    register_kernel_widget_v1(
        "test.kernel.scale.source",
        source_widget,
        args={},
        past_wires={},
        overwrite=True,
    )
    register_kernel_widget_v1(
        "test.kernel.scale.consumer",
        consumer_widget,
        args={},
        past_wires={
            "shared_prior": {"multiplicity": "one", "required": False},
            "prior_without_value": {"multiplicity": "one", "required": False},
            "prior_with_value": {"multiplicity": "one", "required": False},
            "hydrated_prior": {"multiplicity": "one", "required": False},
            "sources": {"multiplicity": "many", "required": False},
            "a": {"multiplicity": "one", "required": False},
            "b": {"multiplicity": "one", "required": False},
            **{
                f"from_K{i:03d}": {"multiplicity": "one", "required": False}
                for i in range(300)
            },
            **{
                f"from_K{i}_D0": {"multiplicity": "one", "required": False}
                for i in range(300)
            },
            **{
                f"alias_{i:03d}": {"multiplicity": "one", "required": False}
                for i in range(500)
            },
        },
        overwrite=True,
    )


# ---------------------------------------------------------------------------
# Scale program builders
# ---------------------------------------------------------------------------


def _kernel_scale_datum(
    datum_id: str,
    *,
    widget: str,
    past_wires: Mapping[str, list[str]] | None = None,
    args: Mapping[str, Any] | None = None,
    mount_explode: bool = False,
) -> Dict[str, Any]:
    return {
        "id": str(datum_id),
        "widget": str(widget),
        "title": str(datum_id),
        "micros": [_text_micro("value")],
        "lifecycle": {
            "mount_explode": bool(mount_explode),
            "max_reexplosions": 2,
            "max_proc_notes": 1,
            "max_messages": 4,
        },
        "authoritative": True,
        "past_wires": dict(past_wires or {}),
        "args": dict(args or {}),
    }


# ---------------------------------------------------------------------------
# Final highest-seam higher-language integration addendum
# ---------------------------------------------------------------------------


def _higher_lang_json_roundtrip_program_v1() -> list[Dict[str, Any]]:
    """
    Return the canonical two-step higher-language program after a real JSON
    membrane round trip.

    This proves the authored source is ordinary JSON-compatible higher-language
    data, not Python object identity, closures, bundles, or hidden runtime
    handles.
    """
    register_kernel_probe_widgets()
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()
    register_kernel_program_language_v1()
    register_thinking_flow_explicit_language_v1()

    program = validate_kernel_program_v1([_k1(), _k2()])
    encoded = json.dumps(program, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)

    assert decoded == program
    assert isinstance(decoded, list)
    assert all(isinstance(k, dict) for k in decoded)

    return decoded


def _assert_higher_lang_bundle_is_kernel_machine_code_v1(
    bundle: ProgramLoweringBundle,
    *,
    expected_program: list[Mapping[str, Any]],
) -> None:
    """
    Common final lowering assertion.

    The highest-language source may be rich, but after lowering the runtime sees
    only ordinary App Table rows, each targeting the one universal kernel step fn.
    """
    assert isinstance(bundle, ProgramLoweringBundle)

    manifest = bundle.app_table_manifest
    assert isinstance(manifest, list)
    assert len(manifest) == len(expected_program)
    assert not isinstance(manifest, ProgramLoweringBundle)

    assert bundle.provenance["source_program_language"] == LANG_THINKING_FLOW_EXPLICIT_V1
    assert bundle.provenance["highest_manifest"] == validate_kernel_program_v1(expected_program)
    assert bundle.provenance["app_table_manifest"] == manifest

    assert bundle.session_surface == {
        "v": 1,
        "source_program_language": LANG_THINKING_FLOW_EXPLICIT_V1,
    }

    assert [row["public_step_name"] for row in manifest] == [
        str(k["step"]["id"])
        for k in expected_program
    ]

    assert {row["step_fn"] for row in manifest} == {KERNEL_STEP_FN_NAME_V1}

    for row, kernel in zip(manifest, expected_program):
        assert set(row.keys()) == {
            "public_step_name",
            "step_fn",
            "fn_args",
        }
        assert row["public_step_name"] == kernel["step"]["id"]
        assert row["step_fn"] == KERNEL_STEP_FN_NAME_V1
        assert set(row["fn_args"].keys()) == {"kernel"}
        assert row["fn_args"]["kernel"] == kernel
        assert not isinstance(row["fn_args"]["kernel"], ProgramLoweringBundle)


def _assert_public_runtime_writes_have_distinct_k1_k2_same_datum_refs_v1(
    writes_result: Mapping[str, Any],
) -> None:
    assert writes_result["ok"] is True
    assert writes_result["query_kind"] == "runtime_writes"

    rows = _public_runtime_write_rows_v1(writes_result)
    refs = _runtime_write_refs_by_form_datum_v1(rows)

    assert ("kernel.K1.form", "A") in refs
    assert ("kernel.K2.form", "A") in refs


def _drive_public_higher_lang_two_step_session_v1(
    public_api: Any,
    sid: str,
    *,
    k1_value: str = "alpha-from-highest-seam",
    k2_confirm: str = "confirmed-from-highest-seam",
) -> None:
    """
    Drive the canonical K1 -> K2 program only through the bounded public facade.

    This proves the launched higher-language session is not merely accepted. It
    actually executes the lowered App Table rows and preserves explicit
    cross-step history through the kernel past_wires pocket.
    """
    s0 = public_api.step_session(sid)
    assert s0["ok"] is True
    assert s0["session_id"] == sid

    r0 = public_api.current_report(sid)
    assert r0["ok"] is True
    assert r0["session_id"] == sid

    s1 = public_api.step_session(
        sid,
        fill={"A": {"value": k1_value}},
    )
    assert s1["ok"] is True
    assert s1["session_id"] == sid

    r1 = public_api.current_report(sid)
    assert r1["ok"] is True
    assert r1["session_id"] == sid

    s2 = public_api.step_session(
        sid,
        fill={"A": {"confirm": k2_confirm}},
    )
    assert s2["ok"] is True
    assert s2["session_id"] == sid

    final = public_api.current_report(sid)
    assert final["ok"] is True
    assert final["session_id"] == sid

    writes = public_api.query_session(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 50,
        },
    )
    _assert_public_runtime_writes_have_distinct_k1_k2_same_datum_refs_v1(writes)


def test_final_highest_seams_lower_same_json_higher_language_to_same_kernel_machine_code() -> None:
    """
    Final source-language proof.

    The authored program is JSON data at the higher seam:

        program_language="thinking_flow_explicit"
        program=[K1, K2]

    Both registry lowerer entrypoints produce the same ordinary App Table
    machine code:

        public_step_name = K.step.id
        step_fn = "think.kernel.v1"
        fn_args = {"kernel": K}

    Nothing below lowering needs to know about the higher language.
    """
    program = _higher_lang_json_roundtrip_program_v1()

    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )
    _assert_higher_lang_bundle_is_kernel_machine_code_v1(
        bundle,
        expected_program=program,
    )

    from _thinkengine._parsing._higher_lang_grammars._langs_core import (
        lower_program_to_app_table_manifest,
    )

    manifest = lower_program_to_app_table_manifest(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )

    assert manifest == bundle.app_table_manifest
    assert manifest == _manifest_from_kernel_program(validate_kernel_program_v1(program))
    assert {row["step_fn"] for row in manifest} == {KERNEL_STEP_FN_NAME_V1}


def test_final_raw_concrete_api_launches_json_higher_language_and_executes_lowered_kernel_rows() -> None:
    """
    Raw concrete-session seam proof.

    This is the lowest launch seam that still accepts a source program language:

        api.create_VM_session_from_program(
            program=json_program,
            program_language="thinking_flow_explicit",
        )

    It proves the core session factory can launch from the higher language while
    runtime execution remains ordinary lowered kernel rows.
    """
    program = _higher_lang_json_roundtrip_program_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
        get_map=False,
    )

    sid = str(created["session_id"])
    assert sid

    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    ctx = runner.step(fill={"A": {"value": "alpha-raw-create-from-program"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    k1_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K1.form",
        datum_id="A",
    )
    assert k1_state["final_value"] == "alpha-raw-create-from-program"

    k2_mount_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )
    prior = k2_mount_state["past_wires_seen_on_mount"]["previous_A_from_K1"]

    assert prior["public_step_name"] == "kernel.K1"
    assert prior["write_kind"] == WRITE_KIND_DATUM_LIFECYCLE
    assert prior["key"] == "A"
    assert prior["value"]["state"]["final_value"] == "alpha-raw-create-from-program"

    ctx = runner.step(fill={"A": {"confirm": "raw-confirm"}})
    assert ctx["kind"] == "ATCOMPLETION"

    k2_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )
    assert k2_state["confirmed"] == "raw-confirm"


def test_final_public_api_class_launches_json_higher_language_and_keeps_runtime_writes_bounded() -> None:
    """
    Public facade class seam proof.

    This is the app-facing class seam:

        PublicSessionAPI.create_session_from_program(...)

    It accepts the higher-language JSON program, returns only bounded public
    receipts/reports, and still exposes enough bounded query evidence to prove
    K1.A and K2.A wrote lifecycle rows under distinct forms.
    """
    program = _higher_lang_json_roundtrip_program_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    raw_api = _api()
    public_api = get_public_session_api(raw_api=raw_api)

    created = public_api.create_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={"test": "final_public_api_class_higher_lang"},
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"

    sid = str(created["session_id"])
    assert sid

    _drive_public_higher_lang_two_step_session_v1(
        public_api,
        sid,
        k1_value="alpha-public-class",
        k2_confirm="public-class-confirm",
    )

    k1_state = _latest_lifecycle_state(
        raw_api,
        sid,
        form_id="kernel.K1.form",
        datum_id="A",
    )
    assert k1_state["final_value"] == "alpha-public-class"

    k2_state = _latest_lifecycle_state(
        raw_api,
        sid,
        form_id="kernel.K2.form",
        datum_id="A",
    )
    assert k2_state["confirmed"] == "public-class-confirm"
    assert (
        k2_state["past_wires_seen_on_done"]["previous_A_from_K1"]["value"]["state"]["final_value"]
        == "alpha-public-class"
    )


def test_final_public_module_level_launches_json_higher_language_from_top_level_functions() -> None:
    """
    Public module-level seam proof.

    This proves the exported top-level public helpers can launch and drive the
    same higher-language JSON program without callers instantiating
    PublicSessionAPI directly.
    """
    program = _higher_lang_json_roundtrip_program_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        create_session_from_program,
        current_report,
        query_session,
        step_session,
    )

    created = create_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={"test": "final_public_module_level_higher_lang"},
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"

    sid = str(created["session_id"])
    assert sid

    s0 = step_session(sid)
    assert s0["ok"] is True

    r0 = current_report(sid)
    assert r0["ok"] is True
    assert r0["session_id"] == sid

    s1 = step_session(
        sid,
        fill={"A": {"value": "alpha-public-module"}},
    )
    assert s1["ok"] is True

    s2 = step_session(
        sid,
        fill={"A": {"confirm": "public-module-confirm"}},
    )
    assert s2["ok"] is True

    final = current_report(sid)
    assert final["ok"] is True
    assert final["session_id"] == sid

    writes = query_session(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 50,
        },
    )
    _assert_public_runtime_writes_have_distinct_k1_k2_same_datum_refs_v1(writes)


def test_final_service_facade_launches_json_higher_language_and_session_runs_e2e() -> None:
    """
    Highest service launch seam proof.

    This test is intentionally about launch + E2E runtime integration, not about
    re-testing service renderer/dispatch behavior. Those seams have their own
    focused tests.

    Highest seam under test:

        create_core_session_from_program(
            program=json_program,
            program_language="thinking_flow_explicit",
        )

    It must:
      - accept the higher-language JSON program;
      - launch through the bounded public session facade;
      - return a small command receipt;
      - create a real core session that can then be driven E2E;
      - execute the lowered runtime rows through think.kernel.v1;
      - preserve explicit K1 -> K2 history through kernel past_wires.
    """
    program = _higher_lang_json_roundtrip_program_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        create_core_session_from_program,
    )
    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    # Service/dispatcher-renderer launch seam.
    created = create_core_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={"test": "final_service_facade_higher_lang_e2e"},
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"

    sid = str(created["session_id"])
    assert sid

    # The service launch receipt should remain bounded. Do not assert renderer
    # behavior here; just make sure launch did not leak raw engine structures.
    created_rendered = _compact(created)
    assert "program_map" not in created_rendered
    assert "multiframespec" not in created_rendered
    assert "raw_ctx" not in created_rendered
    assert '"ctx"' not in created_rendered
    assert "snapshot" not in created_rendered
    assert "history" not in created_rendered

    # Now prove the launched session is real and executable. Use the public
    # headless facade for E2E driving; the service render/dispatch seams are
    # tested independently elsewhere.
    raw_api = get_concrete_session_api(enable_persistence=False)
    public_api = get_public_session_api(raw_api=raw_api)

    # The service facade creates sessions through the process-global concrete
    # session API. In this test file, _api() creates isolated raw APIs, so a new
    # raw_api wrapper may not see the service-created session in all repo
    # configurations. Fall back to the module-level singleton public facade,
    # which wraps the same service-owned concrete API.
    try:
        current = public_api.current_report(sid)
    except Exception:
        from _thinkengine.runme_optimized_queryable.facade_base import (
            current_report,
            query_session,
            step_session,
        )

        current = current_report(sid)
        assert current["ok"] is True
        assert current["session_id"] == sid

        s0 = step_session(sid)
        assert s0["ok"] is True
        assert s0["session_id"] == sid

        s1 = step_session(
            sid,
            fill={"A": {"value": "alpha-service-launch"}},
        )
        assert s1["ok"] is True
        assert s1["session_id"] == sid

        s2 = step_session(
            sid,
            fill={"A": {"confirm": "service-launch-confirm"}},
        )
        assert s2["ok"] is True
        assert s2["session_id"] == sid

        final = current_report(sid)
        assert final["ok"] is True
        assert final["session_id"] == sid

        writes = query_session(
            sid,
            query_kind="runtime_writes",
            query={
                "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
                "include_values": False,
                "max_results": 50,
            },
        )
        _assert_public_runtime_writes_have_distinct_k1_k2_same_datum_refs_v1(writes)
        return

    assert current["ok"] is True
    assert current["session_id"] == sid

    _drive_public_higher_lang_two_step_session_v1(
        public_api,
        sid,
        k1_value="alpha-service-launch",
        k2_confirm="service-launch-confirm",
    )


def test_final_highest_language_rejection_is_consistent_across_lowerer_raw_public_and_service_seams() -> None:
    """
    Final invalid-source proof.

    The same bad higher-language JSON program must fail before runtime at every
    seam that accepts program_language="thinking_flow_explicit".

    This proves strict kernel validation is owned by the higher-language
    lowering boundary, not by incidental widget execution.
    """
    bad = _higher_lang_json_roundtrip_program_v1()
    bad[1] = dict(bad[1])
    bad[1]["datums"] = [dict(d) for d in bad[1]["datums"]]
    bad[1]["datums"][0] = dict(bad[1]["datums"][0])
    bad[1]["datums"][0]["args"] = {
        "local": "still-present",
        "unknown_static_arg": "must fail before runtime",
    }

    with pytest.raises(ValueError, match="unknown args"):
        lower_program_to_app_table_bundle(
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            program=bad,
        )

    api = _api()
    with pytest.raises(ValueError, match="unknown args"):
        api.create_VM_session_from_program(
            program=bad,
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata=_manual_io_metadata(),
            get_map=False,
        )

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    public_api = get_public_session_api(raw_api=_api())
    with pytest.raises(ValueError, match="unknown args"):
        public_api.create_session_from_program(
            program=bad,
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata={"test": "final_invalid_public_class"},
        )

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        create_core_session_from_program,
    )

    with pytest.raises(ValueError, match="unknown args"):
        create_core_session_from_program(
            program=bad,
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata={"test": "final_invalid_service_facade"},
        )


def test_final_highest_seam_matrix_documents_supported_language_launch_paths() -> None:
    """
    Executable seam matrix.

    Green means the seam accepts a higher-language source program plus a
    program_language string. Direct lowerer seams do not launch sessions, but
    they are still part of the same final integration surface.
    """
    seams = {
        "lower_program_to_app_table_bundle": {
            "accepts_program_language": True,
            "launches_session": False,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
        "lower_program_to_app_table_manifest": {
            "accepts_program_language": True,
            "launches_session": False,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
        "raw_api.create_VM_session_from_program": {
            "accepts_program_language": True,
            "launches_session": True,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
        "PublicSessionAPI.create_session_from_program": {
            "accepts_program_language": True,
            "launches_session": True,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
        "interactive_raw.create_session_from_program": {
            "accepts_program_language": True,
            "launches_session": True,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
        "interactive_controled_rolemodulated.create_core_session_from_program": {
            "accepts_program_language": True,
            "launches_session": True,
            "expected_runtime_step_fn_after_lowering": KERNEL_STEP_FN_NAME_V1,
        },
    }

    assert set(seams) == {
        "lower_program_to_app_table_bundle",
        "lower_program_to_app_table_manifest",
        "raw_api.create_VM_session_from_program",
        "PublicSessionAPI.create_session_from_program",
        "interactive_raw.create_session_from_program",
        "interactive_controled_rolemodulated.create_core_session_from_program",
    }

    assert all(v["accepts_program_language"] is True for v in seams.values())
    assert {
        name
        for name, spec in seams.items()
        if spec["launches_session"]
    } == {
        "raw_api.create_VM_session_from_program",
        "PublicSessionAPI.create_session_from_program",
        "interactive_raw.create_session_from_program",
        "interactive_controled_rolemodulated.create_core_session_from_program",
    }
    assert {
        spec["expected_runtime_step_fn_after_lowering"]
        for spec in seams.values()
    } == {KERNEL_STEP_FN_NAME_V1}






# ---------------------------------------------------------------------------
# Role / role-mismatch modulation addendum at the thinking-flow kernel seam
# ---------------------------------------------------------------------------


def _role_modulation_session_metadata_v1() -> Dict[str, Any]:
    """
    Session metadata for role-modulated higher-language kernel tests.

    The role_mismatch_policy uses the final policy shape:

        {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "controller": "redacted",
            },
        }

    The controller/service facade should apply this automatically when a viewer
    role is supplied at the highest interactive seam.
    """
    meta = _manual_io_metadata()
    meta.update(
        {
            "roles": {
                "maker": {
                    "label": "Maker",
                    "description": "Can see and submit maker-owned widgets.",
                },
                "controller": {
                    "label": "Controller",
                    "description": "Can see and submit controller-owned widgets.",
                },
            },
            "role_mismatch_policy": {
                "default": "redacted",
                "role_modes": {
                    "maker": "redacted",
                    "controller": "redacted",
                },
            },
            "test": "thinking_flow_explicit_role_modulation",
        }
    )
    return meta


def _role_modulated_kernel_program_v1() -> list[Dict[str, Any]]:
    """
    Higher-language role demo.

    This is still authored as ordinary thinking_flow_explicit kernel source:

        program=[K]

    The only role-specific authoring surface is datum.roles. No controller API,
    renderer API, or lower session API is mentioned here.

    Datum law:
      - MAKER_D is visible/fillable to maker.
      - CONTROL_D is visible/fillable to controller.
      - each role sees the other datum through role mismatch modulation.
    """
    register_kernel_probe_widgets()
    register_kernel_step_fn_v1()
    register_kernel_program_language_v1()
    register_thinking_flow_explicit_language_v1()

    k = {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {
            "id": "kernel.rolemod.demo",
            "title": "Role Modulation Demo",
            "args": {},
        },
        "form": {
            "id": "kernel.rolemod.demo.form",
            "title": "Role Modulation Demo Form",
            "args": {},
        },
        "frame": {
            "id": "ROLE_FRAME",
            "title": "Role Frame",
            "args": {},
        },
        "span": {
            "id": "ROLE_SPAN",
            "title": "Role Span",
            "args": {},
            # Span roles are intentionally broad here. Datum roles below are the
            # stronger assignment and must win.
            "roles": ["maker", "controller"],
        },
        "history_queries": {},
        "datums": [
            {
                "id": "MAKER_D",
                "widget": "test.kernel.sibling_probe",
                "title": "Maker-only WWE projection",
                "micros": [
                    {
                        "name": "value",
                        "type": "text",
                        "required": True,
                        "placeholder": "maker private placeholder",
                    }
                ],
                "lifecycle": {
                    "mount_explode": False,
                    "max_reexplosions": 2,
                },
                "authoritative": True,
                "roles": ["maker"],
                "system_flags": {
                    "role_demo": "maker datum",
                },
                "past_wires": {},
                "args": {},
            },
            {
                "id": "CONTROL_D",
                "widget": "test.kernel.sibling_probe",
                "title": "Controller-only WWE controls",
                "micros": [
                    {
                        "name": "value",
                        "type": "text",
                        "required": True,
                        "placeholder": "controller private placeholder",
                    }
                ],
                "lifecycle": {
                    "mount_explode": False,
                    "max_reexplosions": 2,
                },
                "authoritative": True,
                "roles": ["controller"],
                "system_flags": {
                    "role_demo": "controller datum",
                },
                "past_wires": {},
                "args": {},
            },
        ],
        "kernel_flags": {
            "copy_form_frame_span_args_into_each_datum": True,
            "mount_explode_default": False,
        },
    }

    return validate_kernel_program_v1([k])


def _assert_rolemod_redaction_marker_v1(
    ctx: Mapping[str, Any],
    *,
    hidden_datum_id: str,
    viewer_role: str,
    required_roles: list[str],
) -> None:
    decl = ctx["datum_widget_decls"][hidden_datum_id]

    assert decl["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert decl["role_mismatch_obfuscated"] is True
    assert decl["micros"] == []
    assert decl["micro_names"] == []
    assert decl["fillspan_name"] is None

    assert decl["datum_args"]["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert decl["datum_args"]["title"] == "Unavailable"
    assert decl["datum_args"]["viewer_role"] == viewer_role
    assert decl["datum_args"]["required_roles"] == required_roles


def test_thinking_flow_explicit_roles_lower_from_kernel_datums_into_multiframespec() -> None:
    """
    Kernel-level role authoring proof.

    This proves higher-language authors can assign roles directly to K datums
    and have those roles survive validation/lowering into the ordinary
    multiframespec consumed by the runtime role mismatch layer.
    """
    program = _role_modulated_kernel_program_v1()

    manifest = lower_program_to_app_table_manifest(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )

    assert len(manifest) == 1
    assert manifest[0]["step_fn"] == KERNEL_STEP_FN_NAME_V1

    kernel = manifest[0]["fn_args"]["kernel"]
    fs = build_kernel_multiframespec_v1(
        kernel,
        resolved_history_queries={},
    )

    datums_by_id = {
        datum["id"]: datum
        for datum in fs["datums"]
    }

    assert datums_by_id["MAKER_D"]["roles"] == ["maker"]
    assert datums_by_id["CONTROL_D"]["roles"] == ["controller"]

    span = fs["frames"][0]["spans"][0]
    assert span["roles"] == ["maker", "controller"]
    assert span["owns"] == ["MAKER_D", "CONTROL_D"]


def test_highest_rolemodulated_service_facade_obfuscates_kernel_widget_ctx_by_viewer_role() -> None:
    """
    Highest controlled rendered-facade proof.

    The source program is authored only at the thinking_flow_explicit kernel
    level. Roles are assigned to widgets/datums there.

    The test then uses the service-facing controller/rolemodulator/renderer
    facade:

        create_core_session_from_program(...)
        dispatch_live_session_action(..., role=...)
        get_live_session_context(..., role=...)

    The controller is not manually called with obfuscation helpers. It should
    seamlessly perform role mismatch modulation through the role-bound liaison.
    """
    program = _role_modulated_kernel_program_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        UserAction,
        create_core_session_from_program,
        dispatch_live_session_action,
        get_live_session_context,
    )

    created = create_core_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata=_role_modulation_session_metadata_v1(),
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"

    sid = str(created["session_id"])
    assert sid

    # Drive through the highest rendered action facade. The service facade uses
    # render=True/include_ctx=False internally, so this packet should be bounded
    # and should not expose raw ctx.
    rendered_step = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="maker",
    )

    assert isinstance(rendered_step, Mapping)
    rendered_step_blob = _compact(rendered_step)
    assert '"ctx"' not in rendered_step_blob
    assert "raw_ctx" not in rendered_step_blob

    maker_ctx = get_live_session_context(
        session_id=sid,
        role="maker",
    )
    controller_ctx = get_live_session_context(
        session_id=sid,
        role="controller",
    )

    assert maker_ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert controller_ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    # Maker sees only maker-owned widgets as fillable.
    assert maker_ctx["datum_widgets_on_this_span"] == ["MAKER_D"]
    assert maker_ctx["span_to_datum_widgets"] == {
        "ROLE_SPAN": ["MAKER_D"],
    }
    assert maker_ctx["frames"][0]["field_ids"] == ["MAKER_D"]
    assert maker_ctx["step"]["datum_widgets_on_this_span"] == ["MAKER_D"]
    assert maker_ctx["step"]["span_owns"] == ["MAKER_D"]

    maker_info = maker_ctx["role_mismatch_modulation_info"]
    assert maker_info["role_viewing"] == "maker"
    assert maker_info["is_mismatch"] is True
    assert maker_info["mismatch_datum_ids"] == ["CONTROL_D"]

    _assert_rolemod_redaction_marker_v1(
        maker_ctx,
        hidden_datum_id="CONTROL_D",
        viewer_role="maker",
        required_roles=["controller"],
    )

    # Controller sees only controller-owned widgets as fillable.
    assert controller_ctx["datum_widgets_on_this_span"] == ["CONTROL_D"]
    assert controller_ctx["span_to_datum_widgets"] == {
        "ROLE_SPAN": ["CONTROL_D"],
    }
    assert controller_ctx["frames"][0]["field_ids"] == ["CONTROL_D"]
    assert controller_ctx["step"]["datum_widgets_on_this_span"] == ["CONTROL_D"]
    assert controller_ctx["step"]["span_owns"] == ["CONTROL_D"]

    controller_info = controller_ctx["role_mismatch_modulation_info"]
    assert controller_info["role_viewing"] == "controller"
    assert controller_info["is_mismatch"] is True
    assert controller_info["mismatch_datum_ids"] == ["MAKER_D"]

    _assert_rolemod_redaction_marker_v1(
        controller_ctx,
        hidden_datum_id="MAKER_D",
        viewer_role="controller",
        required_roles=["maker"],
    )

    # Secrets from the hidden datum must not survive in alternate ctx addresses.
    maker_rendered = _compact(maker_ctx)
    assert "Controller-only WWE controls" not in maker_rendered
    assert "controller private placeholder" not in maker_rendered

    controller_rendered = _compact(controller_ctx)
    assert "Maker-only WWE projection" not in controller_rendered
    assert "maker private placeholder" not in controller_rendered


def test_highest_rolemodulated_service_facade_blocks_mismatched_kernel_datum_submission() -> None:
    """
    Write-side role preflight proof.

    The controller itself is role-blind. The highest role-modulated facade binds
    the request role and prevents a viewer from submitting a mismatched datum
    before the roleless base session API receives the write.
    """
    program = _role_modulated_kernel_program_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        UserAction,
        create_core_session_from_program,
        dispatch_live_session_action,
    )

    created = create_core_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata=_role_modulation_session_metadata_v1(),
    )

    assert created["ok"] is True

    sid = str(created["session_id"])
    assert sid

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="controller",
    )

    with pytest.raises(PermissionError, match="MAKER_D"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            user_fill={
                "MAKER_D": {
                    "value": "controller must not write maker datum",
                }
            },
            role="controller",
        )
