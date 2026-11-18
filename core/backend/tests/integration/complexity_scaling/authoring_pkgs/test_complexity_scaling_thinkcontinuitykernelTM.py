# think-backend/tests/wippp/test_think_kernel_stepfn_complexity_e2e.py

from __future__ import annotations

"""
Think Kernel StepFn Complexity / Forever-Scale E2E
=================================================

This sheet is the executable complexity addendum for Think Kernel v1.

It intentionally lives outside the main continuity E2E sheet so that the main
file stays focused on semantic correctness, lowering shape, public seams, and
runtime continuity.

This file locks the forever-scale laws:

- manifest lowering grows linearly with authored K step count;
- one touched datum produces one lifecycle write;
- one shared history alias fans out without multiplying runtime queries;
- many distinct history aliases fan in with one query per distinct prior fact;
- duplicate aliases pointing at the same prior fact dedupe to one query;
- include_value=False keeps history/runtime-write surfaces metadata/ref-sized;
- include_value=True is the explicit materialization boundary;
- giant user-authored values live in current lifecycle state only unless the
  source language or widget explicitly materializes/archives them;
- default manual IO payload limits reject giant submits before state/index growth;
- max_payload_chars=0 explicitly opts into large authored values;
- user-authored compute is isolated from runtime index/history machinery.

Optional crazy tests are off by default and can be enabled with:

    THINK_KERNEL_SCALE_CRAZY=1
    THINK_KERNEL_USER_CRAZY=1
"""

import json
import os
import time
from collections.abc import Mapping
from typing import Any, Dict

import pytest

from __exceptions.engine import InvalidExternalFillError
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    lower_program_to_app_table_bundle,
)

from _thinkprogram._thinkcontinuitykernelTM import _history as thinkcontinuitykernelTM_history
from _thinkprogram._thinkcontinuitykernelTM.api import (
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
    KERNEL_STEP_FN_NAME_V1,
    LANG_THINKING_FLOW_EXPLICIT_V1,
    manifest_from_kernel_program_v1,
    register_kernel_step_fn_v1,
    register_kernel_widget_v1,
    register_thinking_flow_explicit_language_v1,
)


# ---------------------------------------------------------------------------
# Test toggles
# ---------------------------------------------------------------------------


RUN_KERNEL_SCALE_CRAZY = os.environ.get("THINK_KERNEL_SCALE_CRAZY") == "1"
RUN_KERNEL_USER_CRAZY = os.environ.get("THINK_KERNEL_USER_CRAZY") == "1"


# ---------------------------------------------------------------------------
# Tiny standalone helpers copied from the continuity sheet
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


# ---------------------------------------------------------------------------
# Safe bounded shape scanners
# ---------------------------------------------------------------------------


def _kernel_bounded_container_stats(
    obj: Any,
    *,
    max_nodes: int = 120_000,
) -> Dict[str, int]:
    """
    Safe structural scanner.

    Do not json.dumps huge runtime state in complexity tests. This helper walks
    object shape and string lengths without constructing a giant aggregate repr.
    """
    seen: set[int] = set()
    stack: list[Any] = [obj]

    visited_nodes = 0
    mappings = 0
    sequences = 0
    strings = 0
    total_string_chars_seen = 0
    max_string_chars_seen = 0

    while stack and visited_nodes < max_nodes:
        cur = stack.pop()
        visited_nodes += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            strings += 1
            n = len(cur)
            total_string_chars_seen += n
            max_string_chars_seen = max(max_string_chars_seen, n)
            continue

        if isinstance(cur, Mapping):
            mappings += 1
            for k, v in cur.items():
                if isinstance(k, str):
                    strings += 1
                    n = len(k)
                    total_string_chars_seen += n
                    max_string_chars_seen = max(max_string_chars_seen, n)
                else:
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            sequences += 1
            stack.extend(cur)
            continue

    return {
        "visited_nodes": visited_nodes,
        "mappings": mappings,
        "sequences": sequences,
        "strings": strings,
        "total_string_chars_seen": total_string_chars_seen,
        "max_string_chars_seen": max_string_chars_seen,
        "truncated": int(bool(stack)),
    }


def _kernel_contains_run_bounded(
    obj: Any,
    *,
    char: str,
    run_len: int,
    max_nodes: int = 120_000,
) -> bool:
    needle = str(char) * int(run_len)
    seen: set[int] = set()
    stack: list[Any] = [obj]
    visited_nodes = 0

    while stack and visited_nodes < max_nodes:
        cur = stack.pop()
        visited_nodes += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
            continue

        if isinstance(cur, Mapping):
            for k, v in cur.items():
                if isinstance(k, str) and needle in k:
                    return True
                if not isinstance(k, str):
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _kernel_json_size_small(obj: Any) -> int:
    """
    Only use on known-small source/manifests, or intentional bounded payload
    attempts. Never use this on runtime state with giant user payloads.
    """
    return len(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr))


def _kernel_state(api: Any, sid: str) -> Mapping[str, Any]:
    state = api._get(str(sid)).state
    assert isinstance(state, Mapping)
    return state


def _kernel_runtime_index(api: Any, sid: str) -> Mapping[str, Any]:
    idx = _kernel_state(api, sid).get("_runtime_write_index_v1")
    assert isinstance(idx, Mapping)
    return idx


def _kernel_lifecycle_rows(
    api: Any,
    sid: str,
    *,
    form_id: str,
) -> Mapping[str, Any]:
    rows = (
        _kernel_state(api, sid)
        .get("_datum_lifecycle_v1", {})
        .get("forms", {})
        .get(str(form_id), {})
        .get("datums", {})
    )
    assert isinstance(rows, Mapping)
    return rows


def _kernel_query_lifecycle_writes(
    state: Mapping[str, Any],
    *,
    public_step_name: str | None = None,
    include_values: bool = False,
    max_results: int = 100_000,
) -> list[Mapping[str, Any]]:
    q: Dict[str, Any] = {
        "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
        "include_values": bool(include_values),
        "max_results": int(max_results),
    }
    if public_step_name is not None:
        q["public_step_name"] = str(public_step_name)

    out = query_runtime_writes_v1(state, q)
    assert out["ok"] is True
    rows = out.get("writes") or []
    assert isinstance(rows, list)
    return [row for row in rows if isinstance(row, Mapping)]


# ---------------------------------------------------------------------------
# Scale widgets
# ---------------------------------------------------------------------------


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


def _kernel_scale_k(
    i: int,
    *,
    datum_count: int = 1,
    widget: str = "test.kernel.scale.source",
    history_queries: Mapping[str, Any] | None = None,
    past_wires_for_all: Mapping[str, list[str]] | None = None,
    form_prefix: str = "kernel.scale",
    datum_prefix: str = "D",
) -> Dict[str, Any]:
    datums = [
        _kernel_scale_datum(
            f"{datum_prefix}{j}",
            widget=widget,
            past_wires=past_wires_for_all,
            mount_explode=False,
        )
        for j in range(int(datum_count))
    ]

    return {
        "kind": "think_kernel_step_v1",
        "kernel_args_surface_version": "v1",
        "step": {
            "id": f"{form_prefix}.K{i}",
            "title": f"K{i}",
            "args": {"i": int(i)},
        },
        "form": {
            "id": f"{form_prefix}.K{i}.form",
            "title": f"K{i} Form",
            "args": {},
        },
        "frame": {"id": "F", "title": "Frame", "args": {}},
        "span": {"id": "S", "title": "Span", "args": {}},
        "history_queries": dict(history_queries or {}),
        "datums": datums,
        "kernel_flags": {
            "copy_form_frame_span_args_into_each_datum": False,
            "mount_explode_default": False,
        },
    }


def _kernel_history_query(
    *,
    from_step: str,
    datum_id: str = "D0",
    include_value: bool = True,
    required: bool = True,
    max_results: int = 128,
    select: str = KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
) -> Dict[str, Any]:
    return {
        "from_step": str(from_step),
        "datum_id": str(datum_id),
        "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
        "include_value": bool(include_value),
        "required": bool(required),
        "max_results": int(max_results),
        "select": str(select),
    }


def _kernel_source_program(
    step_count: int,
    *,
    datum_count: int = 1,
    form_prefix: str = "kernel.scale.sources",
) -> list[Dict[str, Any]]:
    return [
        _kernel_scale_k(
            i,
            datum_count=datum_count,
            widget="test.kernel.scale.source",
            form_prefix=form_prefix,
        )
        for i in range(int(step_count))
    ]


def _run_kernel_program_fill_all(
    program: list[Mapping[str, Any]],
    *,
    fill_value: Any = "ok",
    via_higher_language: bool = False,
) -> tuple[Any, str, Mapping[str, Any]]:
    """
    Drive a kernel program using direct API calls.

    This avoids runner snapshot overhead in complexity tests.

    If fill_value is callable, it receives only datum_id. Use
    _run_kernel_program_fill_all_with_ctx(...) when the fill depends on the
    current form/step context.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    api = _api()

    if via_higher_language:
        register_thinking_flow_explicit_language_v1()
        created = api.create_VM_session_from_program(
            program=list(program),
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata=_manual_io_metadata(),
            get_map=False,
        )
    else:
        created = api.create_VM_session(
            manifest=_manifest_from_kernel_program(list(program)),
            initial_parameter_overrides={},
            session_metadata=_manual_io_metadata(),
            get_map=False,
        )

    sid = str(created["session_id"])

    ctx = api.step_session(sid)

    guard = 0
    while str(ctx.get("kind") or "") != "ATCOMPLETION":
        guard += 1
        assert guard < 100_000

        if ctx["kind"] == "MANUALFILLNEEDEDSTEP":
            pending = list(ctx.get("datum_widgets_on_this_span") or [])
            assert pending

            fill = {
                str(did): {"value": fill_value(did) if callable(fill_value) else fill_value}
                for did in pending
            }
            ctx = api.step_session(sid, fill=fill)
            continue

        ctx = api.step_session(sid)

    return api, sid, ctx


def _run_kernel_program_fill_all_with_ctx(
    program: list[Mapping[str, Any]],
    *,
    fill_value_for_ctx: Any,
    via_higher_language: bool = False,
) -> tuple[Any, str, Mapping[str, Any]]:
    """
    Same as _run_kernel_program_fill_all, but the fill function receives:

        fill_value_for_ctx(ctx, datum_id)

    This lets scale tests submit giant values only to source forms and small
    values to consumer forms, so leak assertions test history/index behavior
    rather than the consumer's own submitted value.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    api = _api()

    if via_higher_language:
        register_thinking_flow_explicit_language_v1()
        created = api.create_VM_session_from_program(
            program=list(program),
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata=_manual_io_metadata(),
            get_map=False,
        )
    else:
        created = api.create_VM_session(
            manifest=_manifest_from_kernel_program(list(program)),
            initial_parameter_overrides={},
            session_metadata=_manual_io_metadata(),
            get_map=False,
        )

    sid = str(created["session_id"])

    ctx = api.step_session(sid)

    guard = 0
    while str(ctx.get("kind") or "") != "ATCOMPLETION":
        guard += 1
        assert guard < 100_000

        if ctx["kind"] == "MANUALFILLNEEDEDSTEP":
            pending = list(ctx.get("datum_widgets_on_this_span") or [])
            assert pending

            fill = {
                str(did): {
                    "value": (
                        fill_value_for_ctx(ctx, str(did))
                        if callable(fill_value_for_ctx)
                        else fill_value_for_ctx
                    )
                }
                for did in pending
            }
            ctx = api.step_session(sid, fill=fill)
            continue

        ctx = api.step_session(sid)

    return api, sid, ctx


# ---------------------------------------------------------------------------
# Complexity tests
# ---------------------------------------------------------------------------


def test_kernel_complexity_taxonomy_is_explicitly_documented() -> None:
    axes = {
        "kernel_program_step_count",
        "datums_per_kernel_step",
        "unique_history_query_count",
        "duplicate_history_alias_count",
        "fanout_datums_per_history_query",
        "fanin_history_queries_per_datum",
        "datum_write_payload_size",
        "include_values_false_ref_preview",
        "include_values_true_explicit_materialization",
        "same_datum_id_across_forms",
        "manifest_lowering_size",
        "validation_backward_reference_indexing",
        "runtime_write_index_size",
        "public_facade_higher_language_entrypoint",
        "mixed_adversarial_cross_axis",
        "optional_crazy_scale",
    }

    assert len(axes) == 16
    assert "duplicate_history_alias_count" in axes
    assert "mixed_adversarial_cross_axis" in axes


def test_kernel_lowering_size_scales_linearly_with_number_of_k_steps() -> None:
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    small_n = 10
    large_n = 100

    small_program = _kernel_source_program(small_n, form_prefix="kernel.lower.small")
    large_program = _kernel_source_program(large_n, form_prefix="kernel.lower.large")

    small_bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=small_program,
    )
    large_bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=large_program,
    )

    assert len(small_bundle.app_table_manifest) == small_n
    assert len(large_bundle.app_table_manifest) == large_n

    assert {row["step_fn"] for row in large_bundle.app_table_manifest} == {
        KERNEL_STEP_FN_NAME_V1,
    }

    small_size = _kernel_json_size_small(small_bundle.app_table_manifest)
    large_size = _kernel_json_size_small(large_bundle.app_table_manifest)

    ratio = large_size / max(1, small_size)
    expected_linear = large_n / small_n

    print(
        "[kernel-complexity-summary] lowering_program_length "
        f"small_n={small_n} small_size={small_size} "
        f"large_n={large_n} large_size={large_size} "
        f"ratio={ratio:.3f}"
    )

    assert ratio < expected_linear * 2.0


def test_kernel_runtime_many_sequential_k_steps_scales_with_executed_steps_not_history_scan() -> None:
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    step_count = 50
    program = _kernel_source_program(
        step_count,
        form_prefix="kernel.runtime.many_steps",
    )

    _KERNEL_SCALE_WIDGET_CALLS.clear()

    t0 = time.perf_counter()
    api, sid, ctx = _run_kernel_program_fill_all(
        program,
        fill_value=lambda did: f"value-{did}",
    )
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(_KERNEL_SCALE_WIDGET_CALLS) == step_count

    state = _kernel_state(api, sid)
    writes = _kernel_query_lifecycle_writes(
        state,
        include_values=False,
        max_results=step_count + 10,
    )

    assert len(writes) == step_count

    idx = _kernel_runtime_index(api, sid)
    idx_stats = _kernel_bounded_container_stats(idx)

    print(
        "[kernel-complexity-summary] runtime_many_k_steps "
        f"step_count={step_count} elapsed={elapsed:.6f}s "
        f"widget_calls={len(_KERNEL_SCALE_WIDGET_CALLS)} "
        f"lifecycle_writes={len(writes)} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']}"
    )

    assert elapsed < 20.0
    assert idx_stats["total_string_chars_seen"] < 600_000


def test_kernel_many_datums_in_one_k_step_scales_with_touched_datums_and_one_write_each() -> None:
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    datum_count = 160
    program = [
        _kernel_scale_k(
            0,
            datum_count=datum_count,
            widget="test.kernel.scale.source",
            form_prefix="kernel.runtime.wide_step",
        )
    ]

    _KERNEL_SCALE_WIDGET_CALLS.clear()

    t0 = time.perf_counter()
    api, sid, ctx = _run_kernel_program_fill_all(
        program,
        fill_value=lambda did: f"value-{did}",
    )
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(_KERNEL_SCALE_WIDGET_CALLS) == datum_count

    rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id="kernel.runtime.wide_step.K0.form",
    )
    assert len(rows) == datum_count

    writes = _kernel_query_lifecycle_writes(
        _kernel_state(api, sid),
        public_step_name="kernel.runtime.wide_step.K0",
        include_values=False,
        max_results=datum_count + 10,
    )
    assert len(writes) == datum_count

    print(
        "[kernel-complexity-summary] runtime_many_datums_one_k "
        f"datum_count={datum_count} elapsed={elapsed:.6f}s "
        f"widget_calls={len(_KERNEL_SCALE_WIDGET_CALLS)} "
        f"lifecycle_writes={len(writes)}"
    )

    assert elapsed < 20.0


def test_kernel_many_datums_share_one_history_query_without_multiplying_queries(monkeypatch: Any) -> None:
    """
    Fanout theorem:

        one history alias
        many consumer datums wire that alias

    The kernel should query runtime writes once for the alias, then inject that
    resolved row into every datum.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    fanout_datums = 80
    query_calls: list[Mapping[str, Any]] = []

    real_query = query_runtime_writes_v1

    def counted_query(state: Mapping[str, Any], query: Any) -> Any:
        if isinstance(query, Mapping) and query.get("write_kinds") == [WRITE_KIND_DATUM_LIFECYCLE]:
            query_calls.append(dict(query))
        return real_query(state, query)

    monkeypatch.setattr(thinkcontinuitykernelTM_history, "query_runtime_writes_v1", counted_query)
    monkeypatch.setitem(globals(), "query_runtime_writes_v1", counted_query)

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.fanout",
    )

    k2 = _kernel_scale_k(
        1,
        datum_count=fanout_datums,
        widget="test.kernel.scale.consumer",
        history_queries={
            "prior_D0": _kernel_history_query(
                from_step="kernel.fanout.K0",
                datum_id="D0",
                include_value=True,
            )
        },
        past_wires_for_all={"shared_prior": ["prior_D0"]},
        form_prefix="kernel.fanout",
    )

    _KERNEL_SCALE_WIDGET_CALLS.clear()

    api, sid, ctx = _run_kernel_program_fill_all([k1, k2], fill_value="ok")

    assert ctx["kind"] == "ATCOMPLETION"

    assert len(_KERNEL_SCALE_WIDGET_CALLS) == 1 + fanout_datums

    lifecycle_query_calls = [
        q for q in query_calls
        if q.get("public_step_name") == "kernel.fanout.K0"
    ]
    assert len(lifecycle_query_calls) == 1

    rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id="kernel.fanout.K1.form",
    )
    assert len(rows) == fanout_datums

    for row in rows.values():
        state = row.get("state") or {}
        assert state["fanin_count"] == 1
        assert state["history_keys"] == ["shared_prior"]

    print(
        "[kernel-complexity-summary] fanout_one_history_to_many_datums "
        f"fanout_datums={fanout_datums} "
        f"history_queries={len(lifecycle_query_calls)} "
        f"consumer_calls={fanout_datums}"
    )


def test_kernel_many_history_fanins_into_one_datum_queries_only_unique_prior_facts(monkeypatch: Any) -> None:
    """
    Fanin theorem:

        H prior source steps
        one consumer datum
        H declared unique history queries

    Runtime query count should be H, because H distinct prior facts were
    explicitly requested. The consumer receives H fanned-in facts.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    history_count = 12
    query_calls: list[Mapping[str, Any]] = []

    real_query = query_runtime_writes_v1

    def counted_query(state: Mapping[str, Any], query: Any) -> Any:
        if isinstance(query, Mapping) and query.get("write_kinds") == [WRITE_KIND_DATUM_LIFECYCLE]:
            query_calls.append(dict(query))
        return real_query(state, query)

    monkeypatch.setattr(thinkcontinuitykernelTM_history, "query_runtime_writes_v1", counted_query)
    monkeypatch.setitem(globals(), "query_runtime_writes_v1", counted_query)

    sources = [
        _kernel_scale_k(
            i,
            datum_count=1,
            widget="test.kernel.scale.source",
            form_prefix="kernel.fanin",
        )
        for i in range(history_count)
    ]

    history_queries = {
        f"prior_{i}": _kernel_history_query(
            from_step=f"kernel.fanin.K{i}",
            datum_id="D0",
            include_value=True,
        )
        for i in range(history_count)
    }
    past_wires = {
        f"from_K{i:03d}": [f"prior_{i}"]
        for i in range(history_count)
    }

    consumer = _kernel_scale_k(
        history_count,
        datum_count=1,
        widget="test.kernel.scale.consumer",
        history_queries=history_queries,
        past_wires_for_all=past_wires,
        form_prefix="kernel.fanin",
    )

    api, sid, ctx = _run_kernel_program_fill_all(
        sources + [consumer],
        fill_value="ok",
    )

    assert ctx["kind"] == "ATCOMPLETION"

    source_query_calls = [
        q for q in query_calls
        if str(q.get("public_step_name") or "").startswith("kernel.fanin.K")
    ]
    assert len(source_query_calls) == history_count

    consumer_state = _latest_lifecycle_state(
        api,
        sid,
        form_id=f"kernel.fanin.K{history_count}.form",
        datum_id="D0",
    )
    assert consumer_state["fanin_count"] == history_count
    assert consumer_state["history_keys"] == [
        f"from_K{i:03d}" for i in range(history_count)
    ]

    print(
        "[kernel-complexity-summary] fanin_many_histories_to_one_datum "
        f"history_count={history_count} "
        f"history_queries={len(source_query_calls)} "
        f"consumer_fanin={consumer_state['fanin_count']}"
    )


def test_kernel_duplicate_history_aliases_are_deduped_to_one_runtime_query(monkeypatch: Any) -> None:
    """
    Duplicate alias theorem:

        alias_a and alias_b point to the exact same prior lifecycle row.

    The optimized resolver should query once and assign the same resolved row to
    both aliases.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    query_calls: list[Mapping[str, Any]] = []

    real_query = query_runtime_writes_v1

    def counted_query(state: Mapping[str, Any], query: Any) -> Any:
        if isinstance(query, Mapping) and query.get("write_kinds") == [WRITE_KIND_DATUM_LIFECYCLE]:
            query_calls.append(dict(query))
        return real_query(state, query)

    monkeypatch.setattr(thinkcontinuitykernelTM_history, "query_runtime_writes_v1", counted_query)
    monkeypatch.setitem(globals(), "query_runtime_writes_v1", counted_query)

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.dedup",
    )

    same_spec = _kernel_history_query(
        from_step="kernel.dedup.K0",
        datum_id="D0",
        include_value=True,
    )

    k2 = _kernel_scale_k(
        1,
        datum_count=1,
        widget="test.kernel.scale.consumer",
        history_queries={
            "same_a": dict(same_spec),
            "same_b": dict(same_spec),
        },
        past_wires_for_all={
            "a": ["same_a"],
            "b": ["same_b"],
        },
        form_prefix="kernel.dedup",
    )

    api, sid, ctx = _run_kernel_program_fill_all([k1, k2], fill_value="ok")

    assert ctx["kind"] == "ATCOMPLETION"

    relevant = [
        q for q in query_calls
        if q.get("public_step_name") == "kernel.dedup.K0"
    ]
    assert len(relevant) == 1

    consumer_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.dedup.K1.form",
        datum_id="D0",
    )
    assert consumer_state["fanin_count"] == 2
    assert consumer_state["history_keys"] == ["a", "b"]

    print(
        "[kernel-complexity-summary] duplicate_history_alias_dedup "
        f"aliases=2 unique_runtime_queries={len(relevant)}"
    )


def test_kernel_large_source_datum_write_does_not_leak_into_history_when_include_value_false() -> None:
    """
    Large value theorem, safe/default path:

        K1 writes a giant lifecycle state.
        K2 requests K1.D0 with include_value=False.

    The giant value may exist in current lifecycle state because the user wrote
    it. It must not be duplicated into:
      - runtime write index,
      - K2 past wires,
      - runtime write query rows without values.

    The consumer's own submitted fill is intentionally small so this test does
    not confuse explicit current consumer input with historical materialization.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    giant = "G" * 250_000

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.large.no_values",
    )

    k2 = _kernel_scale_k(
        1,
        datum_count=1,
        widget="test.kernel.scale.consumer",
        history_queries={
            "prior": _kernel_history_query(
                from_step="kernel.large.no_values.K0",
                datum_id="D0",
                include_value=False,
            )
        },
        past_wires_for_all={"prior_without_value": ["prior"]},
        form_prefix="kernel.large.no_values",
    )

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx(
        [k1, k2],
        fill_value_for_ctx=lambda ctx, did: (
            giant
            if str(ctx.get("form_id") or "") == "kernel.large.no_values.K0.form"
            else "consumer-ok"
        ),
    )

    assert ctx["kind"] == "ATCOMPLETION"

    state = _kernel_state(api, sid)
    lifecycle = state.get("_datum_lifecycle_v1")
    assert _kernel_contains_run_bounded(lifecycle, char="G", run_len=1000)

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="G", run_len=1000)

    k2_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.large.no_values.K1.form",
        datum_id="D0",
    )
    assert k2_state["confirmed"] == "consumer-ok"
    assert k2_state["history_value_presence"] == {"prior_without_value": False}
    assert not _kernel_contains_run_bounded(k2_state, char="G", run_len=1000)

    q_without_values = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.large.no_values.K0",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 10,
        },
    )
    assert q_without_values["ok"] is True
    assert not _kernel_contains_run_bounded(
        q_without_values,
        char="G",
        run_len=1000,
    )

    print(
        "[kernel-complexity-summary] large_history_include_value_false "
        "giant_chars=250000 index_leak=0 consumer_leak=0 query_leak=0"
    )


def test_kernel_include_values_true_is_explicit_materialization_boundary() -> None:
    """
    Explicit materialization theorem:

        include_value=True intentionally moves the resolved lifecycle row into
        the current datum's past wires.

    This may copy large current values into the consumer state. That is not a
    hidden engine leak; it is an explicit source-language request.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    giant = "V" * 80_000

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.large.with_values",
    )

    k2 = _kernel_scale_k(
        1,
        datum_count=1,
        widget="test.kernel.scale.consumer",
        history_queries={
            "prior": _kernel_history_query(
                from_step="kernel.large.with_values.K0",
                datum_id="D0",
                include_value=True,
            )
        },
        past_wires_for_all={"prior_with_value": ["prior"]},
        form_prefix="kernel.large.with_values",
    )

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx(
        [k1, k2],
        fill_value_for_ctx=lambda ctx, did: (
            giant
            if str(ctx.get("form_id") or "") == "kernel.large.with_values.K0.form"
            else "consumer-ok"
        ),
    )

    assert ctx["kind"] == "ATCOMPLETION"

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="V", run_len=1000)

    k2_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.large.with_values.K1.form",
        datum_id="D0",
    )

    assert k2_state["confirmed"] == "consumer-ok"
    assert k2_state["history_value_presence"] == {"prior_with_value": True}
    assert k2_state["history_value_string_chars_seen"]["prior_with_value"] >= 80_000

    print(
        "[kernel-complexity-summary] include_values_true_materializes_explicitly "
        "giant_chars=80000 index_leak=0 consumer_materialized=1"
    )


def test_kernel_higher_language_public_facade_many_steps_many_datums_e2e_stays_machine_code_only() -> None:
    """
    Highest-seam scale theorem:

        create_VM_session_from_program(
            program=[K1..KN],
            program_language="thinking_flow_explicit",
        )

    lowers once to ordinary app-table rows. Runtime executes only
    think.kernel.v1.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    step_count = 8
    datums_per_step = 8

    program = _kernel_source_program(
        step_count,
        datum_count=datums_per_step,
        form_prefix="kernel.public.scale",
    )

    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=program,
    )

    assert len(bundle.app_table_manifest) == step_count
    assert {row["step_fn"] for row in bundle.app_table_manifest} == {
        KERNEL_STEP_FN_NAME_V1
    }

    _KERNEL_SCALE_WIDGET_CALLS.clear()

    api, sid, ctx = _run_kernel_program_fill_all(
        program,
        fill_value="ok",
        via_higher_language=True,
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(_KERNEL_SCALE_WIDGET_CALLS) == step_count * datums_per_step

    writes = _kernel_query_lifecycle_writes(
        _kernel_state(api, sid),
        include_values=False,
        max_results=step_count * datums_per_step + 10,
    )
    assert len(writes) == step_count * datums_per_step

    print(
        "[kernel-complexity-summary] public_higher_language_many_steps_datums "
        f"step_count={step_count} datums_per_step={datums_per_step} "
        f"widget_calls={len(_KERNEL_SCALE_WIDGET_CALLS)} "
        f"lifecycle_writes={len(writes)}"
    )


def test_kernel_mixed_cross_axis_default_surfaces_do_not_duplicate_large_values() -> None:
    """
    Mixed adversarial default theorem.

    Axes combined:
      - multiple K steps,
      - multiple source datums per K,
      - multiple history queries,
      - fanout into multiple consumer datums,
      - large source lifecycle values,
      - include_value=False default-safe history wiring.

    Expected:
      - source lifecycle current state contains giant values;
      - runtime index does not;
      - consumer past wires do not;
      - query preview does not;
      - writes scale with explicit touched datums.

    Consumer fills are intentionally small so the test checks historical
    materialization, not user-authored consumer current values.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    source_steps = 6
    datums_per_source_step = 4
    consumer_datums = 10
    giant = "M" * 90_000

    sources = [
        _kernel_scale_k(
            i,
            datum_count=datums_per_source_step,
            widget="test.kernel.scale.source",
            form_prefix="kernel.mixed",
        )
        for i in range(source_steps)
    ]

    history_queries: Dict[str, Any] = {}
    past_wires: Dict[str, list[str]] = {}

    for i in range(source_steps):
        alias = f"prior_K{i}_D0"
        history_queries[alias] = _kernel_history_query(
            from_step=f"kernel.mixed.K{i}",
            datum_id="D0",
            include_value=False,
        )
        past_wires[f"from_K{i}_D0"] = [alias]

    consumer = _kernel_scale_k(
        source_steps,
        datum_count=consumer_datums,
        widget="test.kernel.scale.consumer",
        history_queries=history_queries,
        past_wires_for_all=past_wires,
        form_prefix="kernel.mixed",
    )

    _KERNEL_SCALE_WIDGET_CALLS.clear()

    consumer_form_id = f"kernel.mixed.K{source_steps}.form"

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx(
        sources + [consumer],
        fill_value_for_ctx=lambda ctx, did: (
            "consumer-ok"
            if str(ctx.get("form_id") or "") == consumer_form_id
            else giant
        ),
    )

    assert ctx["kind"] == "ATCOMPLETION"

    expected_source_writes = source_steps * datums_per_source_step
    expected_consumer_writes = consumer_datums
    expected_total_writes = expected_source_writes + expected_consumer_writes

    state = _kernel_state(api, sid)
    lifecycle = state.get("_datum_lifecycle_v1")
    assert _kernel_contains_run_bounded(lifecycle, char="M", run_len=1000)

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="M", run_len=1000)

    consumer_rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id=consumer_form_id,
    )
    assert len(consumer_rows) == consumer_datums

    for row in consumer_rows.values():
        q_state = row.get("state") or {}
        assert q_state["confirmed"] == "consumer-ok"
        assert q_state["fanin_count"] == source_steps
        assert not _kernel_contains_run_bounded(q_state, char="M", run_len=1000)
        assert all(v is False for v in q_state["history_value_presence"].values())

    writes = _kernel_query_lifecycle_writes(
        state,
        include_values=False,
        max_results=expected_total_writes + 10,
    )
    assert len(writes) == expected_total_writes
    assert not _kernel_contains_run_bounded(writes, char="M", run_len=1000)

    print(
        "[kernel-complexity-summary] mixed_cross_axis_default_safe "
        f"source_steps={source_steps} "
        f"datums_per_source_step={datums_per_source_step} "
        f"consumer_datums={consumer_datums} "
        f"history_queries={source_steps} "
        f"expected_writes={expected_total_writes} "
        f"actual_writes={len(writes)} "
        "index_leak=0 consumer_leak=0 query_leak=0"
    )


@pytest.mark.skipif(
    not RUN_KERNEL_SCALE_CRAZY,
    reason="set THINK_KERNEL_SCALE_CRAZY=1",
)
def test_kernel_optional_crazy_many_steps_many_datums_many_histories() -> None:
    """
    Optional stress diagnostic.

    This is intentionally not a default CI gate. It proves the same laws at a
    larger shape and prints the profile.

    Consumer fills are small; source fills are giant. That keeps the leak checks
    focused on history/query/index materialization.
    """
    register_kernel_scale_widgets_v1()
    register_kernel_step_fn_v1()

    source_steps = int(os.environ.get("THINK_KERNEL_SCALE_SOURCE_STEPS", "25"))
    datums_per_source_step = int(os.environ.get("THINK_KERNEL_SCALE_SOURCE_DATUMS", "10"))
    consumer_datums = int(os.environ.get("THINK_KERNEL_SCALE_CONSUMER_DATUMS", "25"))
    giant_chars = int(os.environ.get("THINK_KERNEL_SCALE_GIANT_CHARS", "25000"))

    giant = "C" * giant_chars

    sources = [
        _kernel_scale_k(
            i,
            datum_count=datums_per_source_step,
            widget="test.kernel.scale.source",
            form_prefix="kernel.crazy",
        )
        for i in range(source_steps)
    ]

    history_queries = {
        f"prior_{i}": _kernel_history_query(
            from_step=f"kernel.crazy.K{i}",
            datum_id="D0",
            include_value=False,
        )
        for i in range(source_steps)
    }
    past_wires = {
        f"from_K{i:03d}": [f"prior_{i}"]
        for i in range(source_steps)
    }

    consumer = _kernel_scale_k(
        source_steps,
        datum_count=consumer_datums,
        widget="test.kernel.scale.consumer",
        history_queries=history_queries,
        past_wires_for_all=past_wires,
        form_prefix="kernel.crazy",
    )

    consumer_form_id = f"kernel.crazy.K{source_steps}.form"

    t0 = time.perf_counter()
    api, sid, ctx = _run_kernel_program_fill_all_with_ctx(
        sources + [consumer],
        fill_value_for_ctx=lambda ctx, did: (
            "consumer-ok"
            if str(ctx.get("form_id") or "") == consumer_form_id
            else giant
        ),
    )
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    expected_writes = source_steps * datums_per_source_step + consumer_datums

    writes = _kernel_query_lifecycle_writes(
        _kernel_state(api, sid),
        include_values=False,
        max_results=expected_writes + 10,
    )
    assert len(writes) == expected_writes

    idx = _kernel_runtime_index(api, sid)
    idx_stats = _kernel_bounded_container_stats(idx)

    assert not _kernel_contains_run_bounded(idx, char="C", run_len=1000)
    assert not _kernel_contains_run_bounded(writes, char="C", run_len=1000)

    consumer_rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id=consumer_form_id,
    )
    assert len(consumer_rows) == consumer_datums
    for row in consumer_rows.values():
        q_state = row.get("state") or {}
        assert q_state["confirmed"] == "consumer-ok"
        assert not _kernel_contains_run_bounded(q_state, char="C", run_len=1000)
        assert all(v is False for v in q_state["history_value_presence"].values())

    print(
        "[kernel-complexity-summary] optional_crazy_kernel_scale "
        f"source_steps={source_steps} "
        f"datums_per_source_step={datums_per_source_step} "
        f"consumer_datums={consumer_datums} "
        f"giant_chars={giant_chars} "
        f"elapsed={elapsed:.6f}s "
        f"expected_writes={expected_writes} "
        f"actual_writes={len(writes)} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']}"
    )


# ---------------------------------------------------------------------------
# Kernel user-degree-of-freedom stress addendum
# ---------------------------------------------------------------------------


_KERNEL_USER_DOF_WIDGET_CALLS: list[Dict[str, Any]] = []


def _kernel_estimated_a4_word12_pages(
    chars: int,
    *,
    chars_per_page: int = 3_000,
) -> int:
    """
    Rough prose diagnostic.

    A typical A4 / MS Word / 12pt page is often around 2,500-3,500 characters
    depending on margins, spacing, and paragraph breaks. We use 3,000 chars/page
    as a stable complexity-test explanation unit.
    """
    chars = max(0, int(chars))
    chars_per_page = max(1, int(chars_per_page))
    return (chars + chars_per_page - 1) // chars_per_page


def _manual_io_metadata_for_kernel_user_dof(
    *,
    max_payload_chars: int | None = None,
    max_fields_per_submit: int | None = None,
) -> Dict[str, Any]:
    manual_io = dict(_manual_io_metadata()["manual_io"])

    if max_payload_chars is not None:
        manual_io["max_payload_chars"] = int(max_payload_chars)

    if max_fields_per_submit is not None:
        manual_io["max_fields_per_submit"] = int(max_fields_per_submit)

    return {"manual_io": manual_io}


def _run_kernel_program_fill_all_with_ctx_and_manual_policy(
    program: list[Mapping[str, Any]],
    *,
    fill_value_for_ctx: Any,
    manual_io_overrides: Mapping[str, Any] | None = None,
    via_higher_language: bool = False,
) -> tuple[Any, str, Mapping[str, Any]]:
    """
    Same driver as _run_kernel_program_fill_all_with_ctx(...), but lets stress
    tests opt into larger manual-IO payloads.

    This is intentionally separate from the default helper so default tests keep
    proving the standard cap behavior.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()
    register_kernel_user_dof_widgets_v1()

    api = _api()

    metadata = _manual_io_metadata()
    if manual_io_overrides:
        manual_io = dict(metadata.get("manual_io") or {})
        manual_io.update(dict(manual_io_overrides))
        metadata["manual_io"] = manual_io

    if via_higher_language:
        register_thinking_flow_explicit_language_v1()
        created = api.create_VM_session_from_program(
            program=list(program),
            program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
            initial_parameter_overrides={},
            session_metadata=metadata,
            get_map=False,
        )
    else:
        created = api.create_VM_session(
            manifest=_manifest_from_kernel_program(list(program)),
            initial_parameter_overrides={},
            session_metadata=metadata,
            get_map=False,
        )

    sid = str(created["session_id"])

    ctx = api.step_session(sid)

    guard = 0
    while str(ctx.get("kind") or "") != "ATCOMPLETION":
        guard += 1
        assert guard < 100_000

        if ctx["kind"] == "MANUALFILLNEEDEDSTEP":
            pending = list(ctx.get("datum_widgets_on_this_span") or [])
            assert pending

            fill = {
                str(did): {
                    "value": (
                        fill_value_for_ctx(ctx, str(did))
                        if callable(fill_value_for_ctx)
                        else fill_value_for_ctx
                    )
                }
                for did in pending
            }
            ctx = api.step_session(sid, fill=fill)
            continue

        ctx = api.step_session(sid)

    return api, sid, ctx


def register_kernel_user_dof_widgets_v1() -> None:
    """
    Widgets that intentionally exercise user-authored degrees of freedom.

    These are not "engine bottleneck" widgets. They model what happens when the
    user/program author deliberately asks for:
      - heavier compute,
      - larger state,
      - explicit hydrated history,
      - explicit archival/duplication of hydrated history.
    """

    def heavy_compute_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        datum_args = dict(datum.get("args") or {})
        loops = int(datum_args.get("loops") or 0)
        datum_id = str(q.get("datum_id") or datum["id"])
        partial = dict(q.get("partial_fill") or {})

        acc = 0
        for i in range(loops):
            acc = (acc + ((i ^ len(datum_id)) % 97)) % 1_000_000_007

        _KERNEL_USER_DOF_WIDGET_CALLS.append(
            {
                "widget": "heavy_compute",
                "datum_id": datum_id,
                "loops": loops,
            }
        )

        return {
            "status": "done",
            "state": {
                "datum_id": datum_id,
                "loops": loops,
                "compute_result": acc,
                "value": partial.get("value"),
            },
            "message": {"level": "success", "text": "heavy compute done"},
        }

    def archival_consumer_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        datum_args = dict(datum.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        history = dict(kernel_args.get("past_wires") or {})
        partial = dict(q.get("partial_fill") or {})
        datum_id = str(q.get("datum_id") or datum["id"])

        store_history = bool(datum_args.get("store_history", False))

        _KERNEL_USER_DOF_WIDGET_CALLS.append(
            {
                "widget": "archival_consumer",
                "datum_id": datum_id,
                "history_count": len(history),
                "store_history": store_history,
            }
        )

        state: Dict[str, Any] = {
            "datum_id": datum_id,
            "confirmed": partial.get("value"),
            "history_count": len(history),
            "history_keys": sorted(str(k) for k in history.keys()),
            "stored_history": store_history,
        }

        if store_history:
            # Explicit user-authored materialization. This is intentionally heavy
            # when include_value=True and the prior lifecycle value is huge.
            state["archived_history"] = history
        else:
            state["history_value_presence"] = {
                str(k): isinstance(v, Mapping) and "value" in v
                for k, v in history.items()
            }

        return {
            "status": "done",
            "state": state,
            "message": {"level": "success", "text": "archival consumer done"},
        }

    register_kernel_widget_v1(
        "test.kernel.user.heavy_compute",
        heavy_compute_widget,
        args={
            "loops": {"type": "int", "required": False, "default": 0},
        },
        past_wires={},
        overwrite=True,
    )
    register_kernel_widget_v1(
        "test.kernel.user.archival_consumer",
        archival_consumer_widget,
        args={
            "store_history": {"type": "bool", "required": False, "default": False},
        },
        past_wires={
            "hydrated_prior": {"multiplicity": "one", "required": False},
            **{
                f"from_K{i:03d}": {"multiplicity": "one", "required": False}
                for i in range(300)
            },
        },
        overwrite=True,
    )


def _kernel_user_dof_source_program(
    *,
    form_prefix: str,
    datum_count: int,
    widget: str,
    args_for_each: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    k = _kernel_scale_k(
        0,
        datum_count=datum_count,
        widget=widget,
        form_prefix=form_prefix,
    )
    for d in k["datums"]:
        d["args"] = dict(args_for_each or {})
    return k


def _set_args_for_all_datums(
    k: Dict[str, Any],
    args: Mapping[str, Any],
) -> Dict[str, Any]:
    out = dict(k)
    out["datums"] = [dict(d) for d in list(k["datums"])]
    for d in out["datums"]:
        d["args"] = dict(args)
    return out


def test_kernel_default_manual_io_cap_rejects_multi_page_giant_submit_before_state_or_index_growth() -> None:
    """
    Default manual-IO cap theorem.

    The default artery is capped at 2,000,000 compact JSON chars. A single
    intentionally huge submit must fail before it becomes lifecycle state,
    runtime index content, or history/query material.

    This is a good cap hit, not a scalability failure.

    Rough prose scale:
      - cap = ~2,000,000 compact JSON chars;
      - at ~3,000 chars / A4 Word 12pt page, cap is ~667 pages;
      - this test attempts about 2.88M raw value chars, roughly ~960 pages,
        before JSON overhead.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    datum_count = 16
    giant_chars = 180_000
    default_cap_chars = 2_000_000
    giant = "U" * giant_chars

    k = _kernel_scale_k(
        0,
        datum_count=datum_count,
        widget="test.kernel.scale.source",
        form_prefix="kernel.default_payload_cap",
    )

    api = _api()
    created = api.create_VM_session(
        manifest=_manifest_from_kernel_program([k]),
        initial_parameter_overrides={},
        session_metadata=_manual_io_metadata(),
        get_map=False,
    )
    sid = str(created["session_id"])

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    pending = list(ctx.get("datum_widgets_on_this_span") or [])
    assert len(pending) == datum_count

    fill = {str(did): {"value": giant} for did in pending}
    attempted_payload_chars = _kernel_json_size_small(fill)

    assert attempted_payload_chars > default_cap_chars

    attempted_pages = _kernel_estimated_a4_word12_pages(attempted_payload_chars)
    cap_pages = _kernel_estimated_a4_word12_pages(default_cap_chars)

    with pytest.raises(InvalidExternalFillError):
        api.step_session(sid, fill=fill)

    state = _kernel_state(api, sid)

    writes = _kernel_query_lifecycle_writes(
        state,
        public_step_name="kernel.default_payload_cap.K0",
        include_values=False,
        max_results=datum_count + 10,
    )
    assert writes == []

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="U", run_len=1000)

    lifecycle = state.get("_datum_lifecycle_v1")
    assert not _kernel_contains_run_bounded(lifecycle, char="U", run_len=1000)

    print(
        "[kernel-complexity-summary] default_manual_io_payload_cap_hit "
        f"datum_count={datum_count} "
        f"giant_chars_per_datum={giant_chars} "
        f"attempted_payload_chars={attempted_payload_chars} "
        f"default_cap_chars={default_cap_chars} "
        f"attempted_a4_word12_pages_est={attempted_pages} "
        f"cap_a4_word12_pages_est={cap_pages} "
        "state_growth=0 index_growth=0 writes=0"
    )


def test_kernel_user_authored_compute_cost_is_isolated_from_index_and_history_surfaces() -> None:
    """
    User compute theorem.

    The engine cannot make user-authored compute free. The expected cost is in
    the widget loop itself.

    The kernel/runtime obligation is narrower:
      - no giant runtime index growth,
      - no accidental history materialization,
      - exactly one lifecycle write per touched datum,
      - result state remains small because the widget writes small state.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()
    register_kernel_user_dof_widgets_v1()

    datum_count = 12
    small_loops = 1_000
    large_loops = 20_000

    def run_compute(loops: int) -> tuple[float, int, Dict[str, int]]:
        _KERNEL_USER_DOF_WIDGET_CALLS.clear()

        k = _kernel_user_dof_source_program(
            form_prefix=f"kernel.user_compute.{loops}",
            datum_count=datum_count,
            widget="test.kernel.user.heavy_compute",
            args_for_each={"loops": loops},
        )

        t0 = time.perf_counter()
        api, sid, ctx = _run_kernel_program_fill_all([k], fill_value="ok")
        elapsed = time.perf_counter() - t0

        assert ctx["kind"] == "ATCOMPLETION"
        assert len(_KERNEL_USER_DOF_WIDGET_CALLS) == datum_count
        assert all(call["loops"] == loops for call in _KERNEL_USER_DOF_WIDGET_CALLS)

        writes = _kernel_query_lifecycle_writes(
            _kernel_state(api, sid),
            public_step_name=f"kernel.user_compute.{loops}.K0",
            include_values=False,
            max_results=datum_count + 10,
        )
        assert len(writes) == datum_count

        idx_stats = _kernel_bounded_container_stats(_kernel_runtime_index(api, sid))
        assert idx_stats["total_string_chars_seen"] < 250_000

        return elapsed, len(writes), idx_stats

    small_t, small_writes, small_idx = run_compute(small_loops)
    large_t, large_writes, large_idx = run_compute(large_loops)

    assert small_writes == datum_count
    assert large_writes == datum_count

    # Loose ceiling: catches accidental engine walls while allowing the user's
    # own compute loop to dominate. The expected increase is due to loops, not
    # index/query/history machinery.
    assert large_t < max(8.0, small_t * 40.0)

    # Index size should stay in the same metadata-scale neighborhood; compute
    # loops should not create hidden runtime-index payloads.
    assert large_idx["total_string_chars_seen"] < (
        small_idx["total_string_chars_seen"] * 3 + 100_000
    )

    print(
        "[kernel-complexity-summary] user_authored_compute_isolated "
        f"datum_count={datum_count} "
        f"small_loops={small_loops} small_t={small_t:.6f}s "
        f"large_loops={large_loops} large_t={large_t:.6f}s "
        f"small_index_chars={small_idx['total_string_chars_seen']} "
        f"large_index_chars={large_idx['total_string_chars_seen']}"
    )


def test_kernel_large_authored_source_state_opt_in_grows_current_state_not_runtime_index_or_default_query() -> None:
    """
    Opt-in user payload theorem.

    The default artery rejects enormous submits. With max_payload_chars=0, the
    caller explicitly opts into real large-value state/storage work.

    Then:
      - huge values are allowed as current lifecycle state;
      - runtime index still stays ref/preview-sized;
      - include_values=False query rows still do not contain the huge values.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    datum_count = 16
    giant = "U" * 180_000

    k = _kernel_scale_k(
        0,
        datum_count=datum_count,
        widget="test.kernel.scale.source",
        form_prefix="kernel.user_payload_optin",
    )

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx_and_manual_policy(
        [k],
        fill_value_for_ctx=lambda ctx, did: giant,
        manual_io_overrides={"max_payload_chars": 0},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    state = _kernel_state(api, sid)
    lifecycle = state.get("_datum_lifecycle_v1")
    assert _kernel_contains_run_bounded(lifecycle, char="U", run_len=1000)

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="U", run_len=1000)

    q_preview = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.user_payload_optin.K0",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": datum_count,
        },
    )
    assert q_preview["ok"] is True
    assert len(q_preview["writes"]) == datum_count
    assert not _kernel_contains_run_bounded(q_preview, char="U", run_len=1000)

    submitted_payload_chars = datum_count * len(giant)
    submitted_pages = _kernel_estimated_a4_word12_pages(submitted_payload_chars)

    print(
        "[kernel-complexity-summary] large_authored_source_state_optin_default_safe "
        f"datum_count={datum_count} "
        f"giant_chars_per_datum={len(giant)} "
        f"submitted_raw_chars={submitted_payload_chars} "
        f"submitted_a4_word12_pages_est={submitted_pages} "
        "current_state_has_value=1 index_leak=0 query_preview_leak=0"
    )


def test_kernel_explicit_include_values_export_opt_in_scales_with_requested_rows_and_value_size() -> None:
    """
    Explicit export theorem.

    include_values=True is a materialization boundary. Returning values is
    expected to scale with:

        requested rows × value size

    Because this test intentionally submits more than the default manual-IO cap,
    it opts in with max_payload_chars=0.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    datum_count = 18
    giant = "E" * 120_000

    k = _kernel_scale_k(
        0,
        datum_count=datum_count,
        widget="test.kernel.scale.source",
        form_prefix="kernel.explicit_export_optin",
    )

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx_and_manual_policy(
        [k],
        fill_value_for_ctx=lambda ctx, did: giant,
        manual_io_overrides={"max_payload_chars": 0},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    state = _kernel_state(api, sid)

    t0 = time.perf_counter()
    preview = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.explicit_export_optin.K0",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 6,
        },
    )
    preview_t = time.perf_counter() - t0

    assert preview["ok"] is True
    assert len(preview["writes"]) == 6
    assert not _kernel_contains_run_bounded(preview, char="E", run_len=1000)

    t0 = time.perf_counter()
    values_3 = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.explicit_export_optin.K0",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 3,
        },
    )
    values_3_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    values_9 = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "kernel.explicit_export_optin.K0",
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 9,
        },
    )
    values_9_t = time.perf_counter() - t0

    assert values_3["ok"] is True
    assert values_9["ok"] is True
    assert len(values_3["writes"]) == 3
    assert len(values_9["writes"]) == 9

    assert _kernel_contains_run_bounded(values_3, char="E", run_len=1000)
    assert _kernel_contains_run_bounded(values_9, char="E", run_len=1000)

    stats_3 = _kernel_bounded_container_stats(values_3)
    stats_9 = _kernel_bounded_container_stats(values_9)

    assert stats_9["total_string_chars_seen"] > stats_3["total_string_chars_seen"]

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="E", run_len=1000)

    raw_chars = datum_count * len(giant)
    pages = _kernel_estimated_a4_word12_pages(raw_chars)

    print(
        "[kernel-complexity-summary] explicit_include_values_export_optin "
        f"datum_count={datum_count} value_chars_per_datum={len(giant)} "
        f"raw_authored_chars={raw_chars} "
        f"a4_word12_pages_est={pages} "
        f"preview_rows=6 preview_t={preview_t:.6f}s "
        f"values3_t={values_3_t:.6f}s values9_t={values_9_t:.6f}s "
        f"values3_chars={stats_3['total_string_chars_seen']} "
        f"values9_chars={stats_9['total_string_chars_seen']} "
        "index_leak=0"
    )


def test_kernel_many_duplicate_history_aliases_scale_as_alias_fanin_but_still_one_query(monkeypatch: Any) -> None:
    """
    Alias fanin theorem.

    The user can author many aliases. That makes the datum's q input/history
    surface wider, which is a real authored cost.

    But duplicate aliases pointing to the same prior fact must not multiply
    runtime-write queries.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()

    alias_count = 200
    query_calls: list[Mapping[str, Any]] = []

    real_query = query_runtime_writes_v1

    def counted_query(state: Mapping[str, Any], query: Any) -> Any:
        if (
            isinstance(query, Mapping)
            and query.get("write_kinds") == [WRITE_KIND_DATUM_LIFECYCLE]
        ):
            query_calls.append(dict(query))
        return real_query(state, query)

    monkeypatch.setattr(thinkcontinuitykernelTM_history, "query_runtime_writes_v1", counted_query)
    monkeypatch.setitem(globals(), "query_runtime_writes_v1", counted_query)

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.alias_fanin",
    )

    same_spec = _kernel_history_query(
        from_step="kernel.alias_fanin.K0",
        datum_id="D0",
        include_value=False,
    )

    history_queries = {
        f"same_{i:03d}": dict(same_spec)
        for i in range(alias_count)
    }
    past_wires = {
        f"alias_{i:03d}": [f"same_{i:03d}"]
        for i in range(alias_count)
    }

    k2 = _kernel_scale_k(
        1,
        datum_count=1,
        widget="test.kernel.scale.consumer",
        history_queries=history_queries,
        past_wires_for_all=past_wires,
        form_prefix="kernel.alias_fanin",
    )

    t0 = time.perf_counter()
    api, sid, ctx = _run_kernel_program_fill_all([k1, k2], fill_value="ok")
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    relevant_queries = [
        q for q in query_calls
        if q.get("public_step_name") == "kernel.alias_fanin.K0"
    ]
    assert len(relevant_queries) == 1

    consumer_state = _latest_lifecycle_state(
        api,
        sid,
        form_id="kernel.alias_fanin.K1.form",
        datum_id="D0",
    )

    assert consumer_state["fanin_count"] == alias_count
    assert len(consumer_state["history_keys"]) == alias_count
    assert consumer_state["history_keys"][0] == "alias_000"
    assert consumer_state["history_keys"][-1] == f"alias_{alias_count - 1:03d}"

    print(
        "[kernel-complexity-summary] duplicate_alias_fanin_many "
        f"alias_count={alias_count} "
        f"unique_runtime_queries={len(relevant_queries)} "
        f"elapsed={elapsed:.6f}s"
    )


def test_kernel_user_authored_archival_of_hydrated_history_is_explicit_state_growth_not_index_growth() -> None:
    """
    Explicit archival theorem.

    This intentionally expensive pattern is user-authored:

        include_value=True
        many consumer datums
        widget stores the full hydrated history row in its own state

    The resulting current lifecycle state may duplicate the large prior value.
    That is expected. The engine's obligation is that runtime index and default
    query previews still do not duplicate it.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()
    register_kernel_user_dof_widgets_v1()

    consumer_datums = 8
    giant = "A" * 100_000

    k1 = _kernel_scale_k(
        0,
        datum_count=1,
        widget="test.kernel.scale.source",
        form_prefix="kernel.archival",
    )

    k2 = _kernel_scale_k(
        1,
        datum_count=consumer_datums,
        widget="test.kernel.user.archival_consumer",
        history_queries={
            "prior": _kernel_history_query(
                from_step="kernel.archival.K0",
                datum_id="D0",
                include_value=True,
            )
        },
        past_wires_for_all={"hydrated_prior": ["prior"]},
        form_prefix="kernel.archival",
    )
    k2 = _set_args_for_all_datums(k2, {"store_history": True})

    api, sid, ctx = _run_kernel_program_fill_all_with_ctx(
        [k1, k2],
        fill_value_for_ctx=lambda ctx, did: (
            giant
            if str(ctx.get("form_id") or "") == "kernel.archival.K0.form"
            else "consumer-ok"
        ),
    )

    assert ctx["kind"] == "ATCOMPLETION"

    state = _kernel_state(api, sid)
    lifecycle = state.get("_datum_lifecycle_v1")

    # Current state contains the giant value because source wrote it and
    # consumers explicitly archived hydrated history.
    assert _kernel_contains_run_bounded(lifecycle, char="A", run_len=1000)

    idx = _kernel_runtime_index(api, sid)
    assert not _kernel_contains_run_bounded(idx, char="A", run_len=1000)

    preview = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": False,
            "max_results": 100,
        },
    )
    assert preview["ok"] is True
    assert not _kernel_contains_run_bounded(preview, char="A", run_len=1000)

    consumer_rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id="kernel.archival.K1.form",
    )
    assert len(consumer_rows) == consumer_datums

    for row in consumer_rows.values():
        q_state = row.get("state") or {}
        assert q_state["stored_history"] is True
        assert q_state["history_count"] == 1
        assert "archived_history" in q_state
        assert _kernel_contains_run_bounded(q_state, char="A", run_len=1000)

    archived_raw_chars = consumer_datums * len(giant)
    archived_pages = _kernel_estimated_a4_word12_pages(archived_raw_chars)

    print(
        "[kernel-complexity-summary] explicit_archival_hydrated_history "
        f"consumer_datums={consumer_datums} "
        f"giant_chars={len(giant)} "
        f"explicit_archived_raw_chars_est={archived_raw_chars} "
        f"explicit_archived_a4_word12_pages_est={archived_pages} "
        "current_state_growth=expected index_leak=0 preview_leak=0"
    )


@pytest.mark.skipif(
    not RUN_KERNEL_USER_CRAZY,
    reason="set THINK_KERNEL_USER_CRAZY=1",
)
def test_kernel_optional_user_crazy_compute_values_fanin_and_archival() -> None:
    """
    Optional user-degree stress diagnostic.

    This combines the intentionally expensive user knobs:
      - many source steps,
      - heavy source widget compute,
      - huge source values,
      - many unique history queries,
      - many archiving consumer datums,
      - include_value=True.

    Expected:
      - runtime grows because the user asked for compute + hydrated archival;
      - current lifecycle state contains giant values;
      - runtime index still does not;
      - include_values=False query preview still does not.

    Since this intentionally exceeds the default manual-IO cap, it opts in with
    max_payload_chars=0.
    """
    register_kernel_step_fn_v1()
    register_kernel_scale_widgets_v1()
    register_kernel_user_dof_widgets_v1()

    source_steps = int(os.environ.get("THINK_KERNEL_USER_CRAZY_SOURCE_STEPS", "8"))
    source_datums = int(os.environ.get("THINK_KERNEL_USER_CRAZY_SOURCE_DATUMS", "3"))
    consumer_datums = int(os.environ.get("THINK_KERNEL_USER_CRAZY_CONSUMER_DATUMS", "8"))
    compute_loops = int(os.environ.get("THINK_KERNEL_USER_CRAZY_COMPUTE_LOOPS", "15000"))
    giant_chars = int(os.environ.get("THINK_KERNEL_USER_CRAZY_GIANT_CHARS", "50000"))

    giant = "Z" * giant_chars

    sources: list[Dict[str, Any]] = []
    for i in range(source_steps):
        k = _kernel_scale_k(
            i,
            datum_count=source_datums,
            widget="test.kernel.user.heavy_compute",
            form_prefix="kernel.user_crazy",
        )
        k = _set_args_for_all_datums(k, {"loops": compute_loops})
        sources.append(k)

    history_queries = {
        f"prior_{i:03d}": _kernel_history_query(
            from_step=f"kernel.user_crazy.K{i}",
            datum_id="D0",
            include_value=True,
        )
        for i in range(source_steps)
    }
    past_wires = {
        f"from_K{i:03d}": [f"prior_{i:03d}"]
        for i in range(source_steps)
    }

    consumer = _kernel_scale_k(
        source_steps,
        datum_count=consumer_datums,
        widget="test.kernel.user.archival_consumer",
        history_queries=history_queries,
        past_wires_for_all=past_wires,
        form_prefix="kernel.user_crazy",
    )
    consumer = _set_args_for_all_datums(consumer, {"store_history": True})

    consumer_form_id = f"kernel.user_crazy.K{source_steps}.form"

    _KERNEL_USER_DOF_WIDGET_CALLS.clear()

    t0 = time.perf_counter()
    api, sid, ctx = _run_kernel_program_fill_all_with_ctx_and_manual_policy(
        sources + [consumer],
        fill_value_for_ctx=lambda ctx, did: (
            "consumer-ok"
            if str(ctx.get("form_id") or "") == consumer_form_id
            else giant
        ),
        manual_io_overrides={"max_payload_chars": 0},
    )
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    expected_writes = source_steps * source_datums + consumer_datums

    state = _kernel_state(api, sid)
    writes = _kernel_query_lifecycle_writes(
        state,
        include_values=False,
        max_results=expected_writes + 10,
    )
    assert len(writes) == expected_writes
    assert not _kernel_contains_run_bounded(writes, char="Z", run_len=1000)

    lifecycle = state.get("_datum_lifecycle_v1")
    assert _kernel_contains_run_bounded(lifecycle, char="Z", run_len=1000)

    idx = _kernel_runtime_index(api, sid)
    idx_stats = _kernel_bounded_container_stats(idx)
    assert not _kernel_contains_run_bounded(idx, char="Z", run_len=1000)

    consumer_rows = _kernel_lifecycle_rows(
        api,
        sid,
        form_id=consumer_form_id,
    )
    assert len(consumer_rows) == consumer_datums

    for row in consumer_rows.values():
        q_state = row.get("state") or {}
        assert q_state["stored_history"] is True
        assert q_state["history_count"] == source_steps
        assert _kernel_contains_run_bounded(q_state, char="Z", run_len=1000)

    authored_raw_chars = source_steps * source_datums * giant_chars
    archived_raw_chars = consumer_datums * source_steps * giant_chars
    authored_pages = _kernel_estimated_a4_word12_pages(authored_raw_chars)
    archived_pages = _kernel_estimated_a4_word12_pages(archived_raw_chars)

    print(
        "[kernel-complexity-summary] optional_user_crazy "
        f"source_steps={source_steps} "
        f"source_datums={source_datums} "
        f"consumer_datums={consumer_datums} "
        f"compute_loops={compute_loops} "
        f"giant_chars={giant_chars} "
        f"elapsed={elapsed:.6f}s "
        f"expected_writes={expected_writes} "
        f"actual_writes={len(writes)} "
        f"user_widget_calls={len(_KERNEL_USER_DOF_WIDGET_CALLS)} "
        f"authored_raw_chars={authored_raw_chars} "
        f"authored_a4_word12_pages_est={authored_pages} "
        f"explicit_archived_raw_chars_est={archived_raw_chars} "
        f"explicit_archived_a4_word12_pages_est={archived_pages} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        "index_leak=0 preview_leak=0 current_state_growth=expected"
    )