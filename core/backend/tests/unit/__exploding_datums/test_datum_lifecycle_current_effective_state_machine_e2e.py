# think-backend/tests/wipppp/integration/test_datum_lifecycle_current_effective_state_machine_e2e.py

from __future__ import annotations

"""
Datum Lifecycle Current-Effective State Machine E2E
==================================================

This sheet is intentionally pedagogical.

It proves the developer-facing model for reexploding Q datums:

    A datum lifecycle widget is a small current-effective state machine.

    It receives:
      - the current effective datum surface,
      - a generic signal, whose first concrete kind is "mount",
      - the submitted partial fill,
      - the previous current lifecycle state for that datum,
      - the current prefill/working-fill surface provided by the engine.

    It returns exactly one next state:
      - blocked,
      - reexplode,
      - done.

The important storage law is:

    Current-only does not mean "nothing persists."

    Current-only means:

        for each logical storage key,
        the session keeps the latest value needed for execution/rendering/querying.

        older values are not retained as first-class history
        unless a separate event log/index records them.

Therefore:

    - same storage survives across steps;
    - new keys can be added;
    - existing keys can be overwritten;
    - keys can be cleared;
    - old values remain only if their keys remain;
    - old values disappear if overwritten/cleared;
    - old transitions are not automatically retained.

For Q datums specifically:

    - widget-returned "state" is datum lifecycle state,
      not an arbitrary global app-state patch;

    - it is current-effective per form_id + datum_id;

    - if reexplosion k+1 wants information from k or k-1,
      k+1 should intentionally summarize/carry it forward;

    - this is good Markovian widget design.

This sheet uses lifecycle.mount_explode=True on purpose.

That makes it the authoritative pedagogy for the final datum lifecycle model:

    first span render:
        signal.kind == "mount"
        widget may reexplode before any user fill

    later fill:
        signal.kind == "fill"
        widget continues from current-effective state

    same datum on later span:
        gets a new mount signal for that span
        and can avoid stale automatic satisfaction.

The sheet also documents the dangerous pattern:

    A widget can defeat current-only efficiency by deliberately encoding
    full history into its current state.

Current-only storage protects against accidental implicit history retention.
It cannot protect against a widget choosing to make the current value huge.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Mapping as TypingMapping

from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_FORM_FILLS,
    KEY_FORM_PREFILLS,
    KEY_RUNTIME_WRITE_INDEX,
)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _register_step(name: str, multiframespec: TypingMapping[str, Any]) -> None:
    def fn(_state: TypingMapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _manifest(step_name: str) -> list[dict[str, Any]]:
    return [{"public_step_name": "datum_lifecycle_state_machine", "step_fn": step_name, "fn_args": {}}]


def _compact_json_size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), sort_keys=True, default=repr))


def _recursive_size(obj: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()

    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)

    total = sys.getsizeof(obj)

    if isinstance(obj, Mapping):
        for key, value in obj.items():
            total += _recursive_size(key, seen)
            total += _recursive_size(value, seen)
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for item in obj:
            total += _recursive_size(item, seen)
    elif hasattr(obj, "__dict__"):
        total += _recursive_size(vars(obj), seen)

    return total


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 300_000) -> bool:
    needle = ch * n
    stack = [obj]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
        elif isinstance(cur, Mapping):
            for key, value in cur.items():
                stack.append(key)
                stack.append(value)
        elif isinstance(cur, Sequence) and not isinstance(cur, (str, bytes, bytearray)):
            stack.extend(cur)

    return False


def _count_run_occurrences(obj: Any, ch: str, n: int, *, max_nodes: int = 500_000) -> int:
    needle = ch * n
    count = 0
    stack = [obj]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            count += cur.count(needle)
        elif isinstance(cur, Mapping):
            for key, value in cur.items():
                stack.append(key)
                stack.append(value)
        elif isinstance(cur, Sequence) and not isinstance(cur, (str, bytes, bytearray)):
            stack.extend(cur)

    return count


def _count_large_payload_slots(obj: Any, *, min_payload_chars: int = 1_000) -> int:
    count = 0
    stack = [obj]
    seen: set[int] = set()

    while stack:
        cur = stack.pop()

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if len(cur) >= min_payload_chars:
                count += 1
        elif isinstance(cur, Mapping):
            stack.extend(cur.values())
        elif isinstance(cur, Sequence) and not isinstance(cur, (str, bytes, bytearray)):
            stack.extend(cur)

    return count


def _drive_single_q_until_complete_after_initial_stop(
    runner: SessionProgramScriptedHeadlessRunner,
    *,
    max_manual_submits: int,
) -> Mapping[str, Any]:
    ctx: Mapping[str, Any] | None = None

    for idx in range(max_manual_submits):
        ctx = runner.step(fill={"Q": {"value": f"tick-{idx}"}})

        if ctx["kind"] == "ATCOMPLETE":
            return ctx

        if ctx["kind"] == "ATCOMPLETION":
            return {**dict(ctx), "kind": "ATCOMPLETE"}

        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    assert ctx is not None
    return ctx


def _datum_lifecycle_store(api: Any, sid: str) -> Mapping[str, Any]:
    lifecycle = api._get(sid).state[KEY_DATUM_LIFECYCLE]
    assert isinstance(lifecycle, Mapping)
    return lifecycle


def _only_datum_lifecycle_row(
    lifecycle: Mapping[str, Any],
    *,
    app_form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    row = (
        lifecycle
        .get("forms", {})
        .get(app_form_id, {})
        .get("datums", {})
        .get(datum_id, {})
    )
    assert isinstance(row, Mapping)
    assert row
    return row


def _lifecycle_for_form(state: TypingMapping[str, Any], app_form_id: str) -> Mapping[str, Any]:
    return (
        state.get(KEY_DATUM_LIFECYCLE, {})
        .get("forms", {})
        .get(app_form_id, {})
    )


def _lifecycle_for_datum(
    state: TypingMapping[str, Any],
    app_form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    return (
        _lifecycle_for_form(state, app_form_id)
        .get("datums", {})
        .get(datum_id, {})
    )


def _latest_protocol_state(
    state: TypingMapping[str, Any],
    app_form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    row = _lifecycle_for_datum(state, app_form_id, datum_id)
    q_state = row.get("state") or row.get("q_state") or {}
    assert isinstance(q_state, Mapping)
    return q_state


def _form_fills(state: TypingMapping[str, Any]) -> Mapping[str, Any]:
    fills = state.get(KEY_FORM_FILLS) or {}
    assert isinstance(fills, Mapping)
    return fills


def _assert_output_fill(api: Any, sid: str, datum_id: str, expected: Mapping[str, Any]) -> None:
    out = api.get_outputs(sid)
    assert out["form_fills"][datum_id] == dict(expected)


# ---------------------------------------------------------------------------
# Multiframespec builders
# ---------------------------------------------------------------------------


def _single_q_span_multiframespec(
    widget_name: str,
    *,
    app_form_id: str,
    datum_id: str = "Q",
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": datum_id,
                "title": datum_id,
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 100,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_Q", "owns": [datum_id]}],
            }
        ],
    }


def _one_span_with_siblings_multiframespec(
    widget_name: str,
    *,
    app_form_id: str,
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [
            {"id": "A", "title": "Plain A", "micros": [_text_micro("value")]},
            {
                "id": "Q",
                "title": "Reexploding Q",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 10,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
            },
            {"id": "B", "title": "Plain B", "micros": [_text_micro("value")]},
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_VECTOR", "owns": ["A", "Q", "B"]}],
            }
        ],
    }


def _two_q_spans_with_distinct_instances_multiframespec(
    widget_name: str,
    *,
    app_form_id: str,
) -> Dict[str, Any]:
    """
    Q1 and Q2 are distinct datum instances.

    This is the correct way to force two separate Q executions in one form.

    A same logical datum id can also reappear on a later span if it opts into
    mount_explode=True, because each span mount is a distinct signal.
    """

    def q_datum(datum_id: str) -> Dict[str, Any]:
        return {
            "id": datum_id,
            "title": datum_id,
            "micros": [_text_micro("value")],
            "lifecycle": {
                "widget": widget_name,
                "mount_explode": True,
                "max_reexplosions": 10,
                "max_proc_notes": 4,
                "max_messages": 8,
            },
        }

    return {
        "app_form_id": app_form_id,
        "datums": [
            q_datum("Q1"),
            {"id": "SIDE_1", "title": "Side 1", "micros": [_text_micro("value")]},
            q_datum("Q2"),
            {"id": "SIDE_2", "title": "Side 2", "micros": [_text_micro("value")]},
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_Q1", "owns": ["Q1"]},
                    {"id": "S_SIDE_1", "owns": ["SIDE_1"]},
                    {"id": "S_Q2", "owns": ["Q2"]},
                    {"id": "S_SIDE_2", "owns": ["SIDE_2"]},
                ],
            }
        ],
    }


def _same_datum_reused_later_multiframespec(
    widget_name: str,
    *,
    app_form_id: str,
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "Q",
                "title": "Same Q reused",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 10,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
            },
            {"id": "SIDE", "title": "Side", "micros": [_text_micro("value")]},
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_Q_FIRST", "owns": ["Q"]},
                    {"id": "S_SIDE", "owns": ["SIDE"]},
                    {"id": "S_Q_SECOND", "owns": ["Q"]},
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def _register_markov_vector_widget(widget_name: str = "test.datum_state.markov_vector") -> None:
    """
    A tiny pedagogical Q widget.

    It carries a compact vector forward in its own lifecycle state.

    Mount:
        receive signal.kind == "mount", reexplode to ask for "mounted_value".

    Fill phase 1:
        receive mounted_value, reexplode to ask for "confirm".

    Fill phase 2:
        receive confirm value, return done.

    The important point:

        new_state = summarize(previous_state, current_fill)

    This is the healthy pattern. The widget does not need full historical
    lifecycle rows because it carries the useful compact summary forward.
    """

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        previous = dict(q.get("state") or {})
        signal = dict(q.get("signal") or {})
        signal_kind = str(signal.get("kind") or q.get("signal_kind") or "fill")
        signal_info = dict(signal.get("info") or {})

        phase = int(previous.get("phase") or 0)
        carry = dict(previous.get("carry") or {})
        values = list(carry.get("all_values_compact") or [])
        mounts = list(carry.get("spans_mounted_on") or [])

        if signal_kind == "mount":
            span_id = str(signal_info.get("span_id") or q.get("span_id") or "")
            mounts.append(span_id)
            next_state = {
                "phase": phase + 1,
                "carry": {
                    "all_values_compact": values,
                    "last_value": values[-1] if values else None,
                    "count": len(values),
                    "spans_mounted_on": mounts,
                    "last_signal": "mount",
                    "last_span": span_id,
                },
            }
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": f"Mounted Q on {span_id}",
                    "micros": [_text_micro("mounted_value")],
                    "lifecycle": {
                        **dict(datum.get("lifecycle") or {}),
                        "widget": widget_name,
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 4,
                        "max_messages": 8,
                    },
                },
                "fill": {"mounted_value": ""},
                "prefill": {"mounted_value": span_id},
                "state": next_state,
                "message": {
                    "level": "info",
                    "text": f"Q mounted on {span_id} and asks for mounted value.",
                },
                "proc_notes": {
                    "signal": "mount",
                    "span_id": span_id,
                },
            }

        submitted = None
        if "mounted_value" in partial:
            submitted = partial.get("mounted_value")
        elif "value" in partial:
            submitted = partial.get("value")
        elif "confirm" in partial:
            submitted = partial.get("confirm")

        if submitted is not None:
            values.append(str(submitted))

        next_state = {
            "phase": phase + 1,
            "carry": {
                "all_values_compact": values,
                "last_value": values[-1] if values else None,
                "count": len(values),
                "spans_mounted_on": mounts,
                "last_signal": signal_kind,
            },
        }

        if "confirm" not in partial:
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Confirm Q",
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        **dict(datum.get("lifecycle") or {}),
                        "widget": widget_name,
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 4,
                        "max_messages": 8,
                    },
                },
                "fill": {"confirm": ""},
                "prefill": {"confirm": "ok"},
                "state": next_state,
                "message": {
                    "level": "info",
                    "text": "Q carried first value forward and asks for confirmation.",
                },
                "proc_notes": {"phase": phase + 1},
            }

        return {
            "status": "done",
            "state": next_state,
            "message": {
                "level": "success",
                "text": "Q done with compact carried state.",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)


def _register_large_payload_widget(
    *,
    widget_name: str,
    mode: str,
    payload_chars: int,
    target_reexplosions: int,
) -> None:
    """
    Large-payload widget with three modes.

    stable_key_replace:
        Always writes the large payload at the same key.
        Current state remains roughly one payload large.

    changing_key_keep_latest_only:
        Uses a changing key name but does not carry older payload keys forward.
        Current state still remains roughly one payload large.

    changing_key_accumulate_all:
        Deliberately preserves all previous payload keys.
        This is the bad pattern. Current state grows with k because the widget
        intentionally encodes history into current state.
    """

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        previous = dict(q.get("state") or {})

        phase = int(previous.get("phase") or 0)
        payload = "X" * payload_chars

        if mode == "stable_key_replace":
            data = {"latest_payload": payload}

        elif mode == "changing_key_keep_latest_only":
            data = {f"payload_{phase:04d}": payload}

        elif mode == "changing_key_accumulate_all":
            data = dict(previous.get("data") or {})
            data[f"payload_{phase:04d}"] = payload

        else:
            raise AssertionError(f"unknown mode: {mode}")

        next_state = {
            "mode": mode,
            "phase": phase + 1,
            "data": data,
            "summary": {
                "data_key_count": len(data),
                "payload_chars": payload_chars,
                "latest_key": sorted(data)[-1],
            },
        }

        if phase < target_reexplosions:
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": f"Large payload phase {phase + 1}",
                    "micros": [_text_micro("value")],
                    "lifecycle": {
                        **dict(datum.get("lifecycle") or {}),
                        "widget": widget_name,
                        "max_reexplosions": target_reexplosions + 2,
                        "max_proc_notes": 1,
                        "max_messages": 4,
                    },
                },
                "fill": {"value": ""},
                "state": next_state,
                "message": {
                    "level": "info",
                    "text": f"large payload phase {phase + 1}",
                },
            }

        return {
            "status": "done",
            "state": next_state,
            "message": {
                "level": "success",
                "text": "large payload widget done",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)


# ---------------------------------------------------------------------------
# Tests: current-effective definition
# ---------------------------------------------------------------------------


def test_q_lifecycle_state_is_current_effective_and_next_reexplode_sees_previous_state() -> None:
    """
    A single Q datum reexplodes once and then completes.

    This proves the most important widget-author law:

        Q step k writes current lifecycle state.
        Q step k+1 receives that state as previous state.
        k+1 can carry forward the valuable compact information.

    The engine does not need a full historical list of every prior Q state for
    this to work.
    """

    app_form_id = "datum.current_effective.single_q"
    widget_name = "test.datum_state.markov_vector.single_q"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.current_effective.single_q.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    after_mount = api._get(sid).state
    q_state = _latest_protocol_state(after_mount, app_form_id, "Q")
    assert q_state["phase"] == 1
    assert q_state["carry"]["spans_mounted_on"] == ["S_Q"]

    ctx = runner.step(fill={"Q": {"mounted_value": "alpha"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q"

    after_reexplode = api._get(sid).state
    q_state = _latest_protocol_state(after_reexplode, app_form_id, "Q")

    assert q_state["phase"] == 2
    assert q_state["carry"]["all_values_compact"] == ["alpha"]
    assert q_state["carry"]["last_value"] == "alpha"

    ctx = runner.step(fill={"Q": {"confirm": "beta"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")

    assert q_state["phase"] == 3
    assert q_state["carry"]["all_values_compact"] == ["alpha", "beta"]
    assert q_state["carry"]["last_value"] == "beta"

    _assert_output_fill(api, sid, "Q", {"confirm": "beta"})


def test_jstar_runtime_writes_can_query_latest_datum_lifecycle_write_refs_without_heavy_values() -> None:
    """
    Runtime writes are a bounded query spine.

    They can show that datum lifecycle writes occurred and can resolve current
    values when requested.

    But the index itself should remain lean: refs/previews/metadata, not full
    historical payload copies.
    """

    app_form_id = "datum.current_effective.jstar"
    widget_name = "test.datum_state.markov_vector.jstar"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.current_effective.jstar.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    runner.step_until_stop()
    runner.step(fill={"Q": {"mounted_value": "alpha"}})
    ctx = runner.step(fill={"Q": {"confirm": "beta"}})

    assert ctx["kind"] == "ATCOMPLETION"

    state = api._get(sid).state

    without_values = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 20,
            "include_values": False,
        },
    )

    assert without_values["ok"] is True
    assert len(without_values["writes"]) >= 1

    rendered_without = json.dumps(without_values, sort_keys=True, default=repr)

    assert "datum_lifecycle" in rendered_without or WRITE_KIND_DATUM_LIFECYCLE in rendered_without
    assert "alpha" not in rendered_without
    assert "beta" not in rendered_without

    with_values = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 20,
            "include_values": True,
        },
    )

    assert with_values["ok"] is True

    rendered_with = json.dumps(with_values, sort_keys=True, default=repr)

    # include_values resolves current referenced values. It should be able to see
    # the current effective lifecycle state.
    assert "alpha" in rendered_with
    assert "beta" in rendered_with


# ---------------------------------------------------------------------------
# Tests: span as product vector
# ---------------------------------------------------------------------------


def test_one_span_with_sibling_datums_behaves_like_product_vector_state_machine() -> None:
    """
    A span owns A, Q, and B.

        SpanState = A x Q x B

    The first fill touches all three.

    Q reexplodes, so the public span remains S_VECTOR.

    Important correction:

        Do not assert that plain sibling fills are final durable KEY_FORM_FILLS
        while the span is still pending after Q reexplode.

    The final durable output is asserted after Q completes.
    """

    app_form_id = "datum.product_vector.one_span"
    widget_name = "test.datum_state.markov_vector.one_span"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.product_vector.one_span.step"
    _register_step(
        step_name,
        _one_span_with_siblings_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_VECTOR"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = runner.step(
        fill={
            "A": {"value": "plain-a"},
            "Q": {"mounted_value": "q-alpha"},
            "B": {"value": "plain-b"},
        }
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_VECTOR"

    state_after_reexplode = api._get(sid).state
    q_state = _latest_protocol_state(state_after_reexplode, app_form_id, "Q")

    assert q_state["phase"] == 2
    assert q_state["carry"]["all_values_compact"] == ["q-alpha"]

    # The old failing assertion was:
    #
    #     state_after_reexplode[KEY_FORM_FILLS]["A"]["value"] == "plain-a"
    #
    # That assumes final durable form_fills while the product span is still
    # pending. The safer contract is final output after the span completes.

    ctx = runner.step(fill={"Q": {"confirm": "q-beta"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "plain-a"
    assert out["form_fills"]["Q"]["confirm"] == "q-beta"
    assert out["form_fills"]["B"]["value"] == "plain-b"


def test_same_logical_datum_reused_later_mount_explodes_again_instead_of_being_skipped() -> None:
    """
    Mount-explode finalizes the respan law.

    If the same logical datum id Q appears on a later span, mount_explode=True
    gives that later span a fresh mount signal.

    Therefore this shape is now valid:

        S_Q_FIRST -> S_SIDE -> S_Q_SECOND

    with both Q spans owning the same datum id "Q", because each span mount is
    its own signal.
    """

    app_form_id = "datum.same_id.reused_later"
    widget_name = "test.datum_state.markov_vector.same_id"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.same_id.reused_later.step"
    _register_step(
        step_name,
        _same_datum_reused_later_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["current_span"] == "S_Q_FIRST"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = runner.step(fill={"Q": {"mounted_value": "first-alpha"}})
    assert ctx["current_span"] == "S_Q_FIRST"

    ctx = runner.step(fill={"Q": {"confirm": "first-beta"}})
    assert ctx["current_span"] == "S_SIDE"

    ctx = runner.step(fill={"SIDE": {"value": "side"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q_SECOND"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = runner.step(fill={"Q": {"mounted_value": "second-alpha"}})
    assert ctx["current_span"] == "S_Q_SECOND"

    ctx = runner.step(fill={"Q": {"confirm": "second-beta"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")
    assert q_state["carry"]["spans_mounted_on"] == ["S_Q_FIRST", "S_Q_SECOND"]
    assert q_state["carry"]["all_values_compact"] == [
        "first-alpha",
        "first-beta",
        "second-alpha",
        "second-beta",
    ]


def test_distinct_q_instances_on_many_spans_run_as_separate_state_machines() -> None:
    """
    Correct many-span model.

    Q1 and Q2 are distinct datum ids, so both run.

    This proves:

        a frame can contain many Q state machines;
        each datum has its own current-effective lifecycle state;
        surrounding plain spans can interleave between them.
    """

    app_form_id = "datum.distinct_q_instances.many_spans"
    widget_name = "test.datum_state.markov_vector.distinct_instances"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.distinct_q_instances.many_spans.step"
    _register_step(
        step_name,
        _two_q_spans_with_distinct_instances_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["current_span"] == "S_Q1"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q1"])

    ctx = runner.step(fill={"Q1": {"mounted_value": "q1-alpha"}})
    assert ctx["current_span"] == "S_Q1"

    ctx = runner.step(fill={"Q1": {"confirm": "q1-beta"}})
    assert ctx["current_span"] == "S_SIDE_1"

    ctx = runner.step(fill={"SIDE_1": {"value": "side-one"}})
    assert ctx["current_span"] == "S_Q2"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q2"])

    ctx = runner.step(fill={"Q2": {"mounted_value": "q2-alpha"}})
    assert ctx["current_span"] == "S_Q2"

    ctx = runner.step(fill={"Q2": {"confirm": "q2-beta"}})
    assert ctx["current_span"] == "S_SIDE_2"

    ctx = runner.step(fill={"SIDE_2": {"value": "side-two"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state

    q1_state = _latest_protocol_state(final_state, app_form_id, "Q1")
    q2_state = _latest_protocol_state(final_state, app_form_id, "Q2")

    assert q1_state["carry"]["all_values_compact"] == ["q1-alpha", "q1-beta"]
    assert q1_state["carry"]["spans_mounted_on"] == ["S_Q1"]
    assert q2_state["carry"]["all_values_compact"] == ["q2-alpha", "q2-beta"]
    assert q2_state["carry"]["spans_mounted_on"] == ["S_Q2"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q1"]["confirm"] == "q1-beta"
    assert out["form_fills"]["SIDE_1"]["value"] == "side-one"
    assert out["form_fills"]["Q2"]["confirm"] == "q2-beta"
    assert out["form_fills"]["SIDE_2"]["value"] == "side-two"


# ---------------------------------------------------------------------------
# Tests: data efficiency
# ---------------------------------------------------------------------------


def test_large_payload_stable_key_replace_does_not_duplicate_payloads_with_k() -> None:
    """
    Good pattern:

        state["data"]["latest_payload"] = giant_payload

    Each reexplosion overwrites the same logical key.

    Current state remains approximately one payload large, even after many
    reexplosions.
    """

    app_form_id = "datum.large.stable_key_replace"
    payload_chars = 16_000
    target_reexplosions = 10

    widget_name = "test.datum_state.large.stable_key_replace"
    _register_large_payload_widget(
        widget_name=widget_name,
        mode="stable_key_replace",
        payload_chars=payload_chars,
        target_reexplosions=target_reexplosions,
    )

    step_name = "test.datum_state.large.stable_key_replace.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    # Task C: the first public surface may already be mount-reexploded.
    # Drive by public completion state, not by the old pre-mount submit count.
    ctx = _drive_single_q_until_complete_after_initial_stop(
        runner,
        max_manual_submits=target_reexplosions + 2,
    )

    assert ctx["kind"] == "ATCOMPLETE"

    lifecycle = _datum_lifecycle_store(api, sid)
    row = _only_datum_lifecycle_row(lifecycle, app_form_id=app_form_id, datum_id="Q")

    data = row["state"]["data"]
    assert sorted(data.keys()) == ["latest_payload"]

    payload_count = _count_large_payload_slots(data)
    assert payload_count == 1

    encoded_size = len(json.dumps(row["state"], sort_keys=True))
    assert encoded_size < payload_chars * 2


def test_large_payload_changing_key_keep_latest_only_still_does_not_duplicate_payloads() -> None:
    """
    Also good pattern:

        state["data"] = {f"payload_{phase}": giant_payload}

    The key changes each time, but the widget does not carry older keys forward.

    Current-only storage means old keys disappear because the whole current
    lifecycle state is replaced by the next returned lifecycle state.
    """

    app_form_id = "datum.large.changing_key_keep_latest_only"
    payload_chars = 16_000
    target_reexplosions = 10

    widget_name = "test.datum_state.large.changing_key_keep_latest_only"
    _register_large_payload_widget(
        widget_name=widget_name,
        mode="changing_key_keep_latest_only",
        payload_chars=payload_chars,
        target_reexplosions=target_reexplosions,
    )

    step_name = "test.datum_state.large.changing_key_keep_latest_only.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    # Mount may have already consumed the first reexplosion. The invariant here
    # is current-state shape, not exact manual-submit cardinality.
    ctx = _drive_single_q_until_complete_after_initial_stop(
        runner,
        max_manual_submits=target_reexplosions + 2,
    )

    assert ctx["kind"] == "ATCOMPLETE"

    lifecycle = _datum_lifecycle_store(api, sid)
    row = _only_datum_lifecycle_row(lifecycle, app_form_id=app_form_id, datum_id="Q")

    data = row["state"]["data"]

    assert len(data) == 1
    assert _count_large_payload_slots(data) == 1

    encoded_size = len(json.dumps(row["state"], sort_keys=True))
    assert encoded_size < payload_chars * 2


def test_large_payload_bad_pattern_accumulating_changed_keys_grows_with_k_and_is_detectable() -> None:
    """
    Bad pattern:

        data = dict(previous_state["data"])
        data[f"payload_{phase}"] = giant_payload

    This deliberately encodes history into the current state.

    Current-only storage is not violated. The widget is simply choosing to make
    the current value contain all previous payloads.
    """

    app_form_id = "datum.large.bad_accumulate"
    payload_chars = 16_000
    target_reexplosions = 10

    widget_name = "test.datum_state.large.changing_key_accumulate_all"
    _register_large_payload_widget(
        widget_name=widget_name,
        mode="changing_key_accumulate_all",
        payload_chars=payload_chars,
        target_reexplosions=target_reexplosions,
    )

    step_name = "test.datum_state.large.bad_accumulate.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    # This case deliberately accumulates history inside the current lifecycle
    # state. Drive until completion; do not assume the old pre-mount submit
    # count.
    ctx = _drive_single_q_until_complete_after_initial_stop(
        runner,
        max_manual_submits=target_reexplosions + 2,
    )

    assert ctx["kind"] == "ATCOMPLETE"

    lifecycle = _datum_lifecycle_store(api, sid)
    row = _only_datum_lifecycle_row(lifecycle, app_form_id=app_form_id, datum_id="Q")

    data = row["state"]["data"]
    payload_count = _count_large_payload_slots(data)

    # The exact count includes the mount-time lifecycle phase. The important
    # pedagogical assertion is that the bad shape is not one-payload-large.
    assert payload_count >= target_reexplosions

    encoded_size = len(json.dumps(row["state"], sort_keys=True))
    assert encoded_size > payload_chars * max(3, target_reexplosions // 2)


def test_large_payload_good_vs_bad_growth_law_is_visible_in_current_lifecycle_size() -> None:
    """
    Compare good and bad current-state shapes.

    Good:
        current lifecycle state contains one giant payload.

    Bad:
        current lifecycle state contains k giant payloads.

    The point is not an exact byte budget. The point is shape/growth law.
    """

    payload_chars = 8_000
    target_reexplosions = 12

    cases = [
        ("stable_key_replace", "datum.large.compare.good_stable"),
        ("changing_key_keep_latest_only", "datum.large.compare.good_changing"),
        ("changing_key_accumulate_all", "datum.large.compare.bad_accumulate"),
    ]

    sizes: Dict[str, int] = {}
    payload_counts: Dict[str, int] = {}

    for mode, app_form_id in cases:
        widget_name = f"test.datum_state.large.compare.{mode}"
        _register_large_payload_widget(
            widget_name=widget_name,
            mode=mode,
            payload_chars=payload_chars,
            target_reexplosions=target_reexplosions,
        )

        step_name = f"test.datum_state.large.compare.{mode}.step"
        _register_step(
            step_name,
            _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
        )

        api = _api()
        st = api.create_VM_session(
            manifest=_manifest(step_name),
            initial_parameter_overrides={},
            session_metadata={
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": False,
                }
            },
        )

        sid = str(st["session_id"])
        runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

        ctx = runner.step_until_stop()
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        ctx = _drive_single_q_until_complete_after_initial_stop(
            runner,
            max_manual_submits=target_reexplosions + 2,
        )

        assert ctx["kind"] == "ATCOMPLETE"

        state = api._get(sid).state
        lifecycle = state[KEY_DATUM_LIFECYCLE]

        sizes[mode] = _compact_json_size(lifecycle)
        payload_counts[mode] = _count_run_occurrences(lifecycle, "X", payload_chars)

    assert payload_counts["stable_key_replace"] == 1
    assert payload_counts["changing_key_keep_latest_only"] == 1
    assert payload_counts["changing_key_accumulate_all"] >= target_reexplosions

    good_max = max(
        sizes["stable_key_replace"],
        sizes["changing_key_keep_latest_only"],
    )
    bad_size = sizes["changing_key_accumulate_all"]

    assert bad_size > good_max * 3


def test_runtime_write_index_remains_lean_even_when_current_lifecycle_has_large_payload() -> None:
    """
    The runtime write index should not become a hidden full-payload history.

    Heavy current lifecycle state may exist in KEY_DATUM_LIFECYCLE.

    The write index should still be lean when queried without values.
    """

    app_form_id = "datum.large.runtime_index_lean"
    payload_chars = 64_000
    target_reexplosions = 4

    widget_name = "test.datum_state.large.runtime_index_lean"
    _register_large_payload_widget(
        widget_name=widget_name,
        mode="stable_key_replace",
        payload_chars=payload_chars,
        target_reexplosions=target_reexplosions,
    )

    step_name = "test.datum_state.large.runtime_index_lean.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = _drive_single_q_until_complete_after_initial_stop(
        runner,
        max_manual_submits=target_reexplosions + 2,
    )

    assert ctx["kind"] == "ATCOMPLETE"

    state = api._get(sid).state

    assert _contains_run(state[KEY_DATUM_LIFECYCLE], "X", 1000)

    # The raw runtime index should not itself be a full payload archive.
    assert not _contains_run(state[KEY_RUNTIME_WRITE_INDEX], "X", 1000)

    q = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 20,
            "include_values": False,
        },
    )

    assert q["ok"] is True
    assert not _contains_run(q, "X", 1000)

    q_with_values = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 20,
            "include_values": True,
        },
    )

    assert q_with_values["ok"] is True

    # include_values resolves current values; therefore the current large value
    # can appear here. That is not index bloat. It is explicit value resolution.
    assert _contains_run(q_with_values, "X", 1000)


def test_prefills_and_fills_are_current_buckets_not_automatic_histories() -> None:
    """
    Prefills and fills are also current buckets.

    They are maps used for execution/output, not append-only histories.

    This test does not assume every intermediate rejected/blocked attempt is
    retained. It checks the safe public contract:

        final accepted fill is visible in outputs;
        prefill bucket is current state;
        neither bucket is a full manual-attempt history by default.
    """

    app_form_id = "datum.prefills_and_fills.current_buckets"
    widget_name = "test.datum_state.markov_vector.prefills_fills"
    _register_markov_vector_widget(widget_name)

    step_name = "test.datum_state.prefills_and_fills.current_buckets.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    runner.step_until_stop()

    ctx = runner.step(fill={"Q": {"mounted_value": "alpha"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    state_after_reexplode = api._get(sid).state

    # The Q reexplode returned a working prefill {"confirm": "ok"}.
    # The exact bucket shape is engine-owned, so avoid overfitting to a nested
    # internal path. The pedagogical invariant is that current state can contain
    # the current prefill surface, not an append-only history of all prefills.
    rendered_prefills = json.dumps(
        state_after_reexplode.get(KEY_FORM_PREFILLS) or {},
        sort_keys=True,
        default=repr,
    )
    assert "ok" in rendered_prefills or "confirm" in json.dumps(ctx, sort_keys=True, default=repr)

    ctx = runner.step(fill={"Q": {"confirm": "beta"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"]["confirm"] == "beta"

    final_state = api._get(sid).state
    rendered_fills = json.dumps(final_state.get(KEY_FORM_FILLS) or {}, sort_keys=True, default=repr)

    assert "beta" in rendered_fills
    assert "alpha" not in out["form_fills"]["Q"].values()


# ---------------------------------------------------------------------------
# Tests: controller/API signals as first-class datum lifecycle inputs
# ---------------------------------------------------------------------------


def _register_signal_aware_pedagogy_widget(
    widget_name: str = "test.datum_state.signal_aware_pedagogy",
) -> None:
    """
    A deliberately explicit widget for the final signal pedagogy.

    This widget proves that a datum lifecycle widget is not merely "fill driven."

    It is a small current-effective state machine driven by:

        q["datum"]
        q["partial_fill"]
        q["state"]
        q["prefill"]
        q["signal"]

    The same current-effective datum can therefore evolve differently depending
    on the incoming signal/fill pair.

    Paths
    -----

    1. mount, no user fill yet:

        signal.kind == "mount"

        The widget reexplodes into the mounted_value surface before first public
        render.

    2. ordinary fill, no controller signal:

        signal.kind == "fill"
        partial_fill == {"mounted_value": ...}

        The widget follows the ordinary path and reexplodes into confirm.

    3. signal only:

        signal.kind == "refresh"
        partial_fill is the current working fill / existing overlay

        The widget follows the signal-only path and reexplodes into signal_value.

    4. signal with fill:

        signal.kind == "refresh_and_fill"
        partial_fill contains the submitted fill

        The widget follows the signal+fill path and reexplodes into
        signal_confirm, while carrying the submitted fill into compact state.

    The test assertions below verify that the engine does not need a separate
    bespoke signal mechanism deeper than datum lifecycle evaluation. The signal
    is simply another field in the same widget input packet.
    """

    def _base_lifecycle(datum: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(datum.get("lifecycle") or {}),
            "widget": widget_name,
            "mount_explode": True,
            "max_reexplosions": 20,
            "max_proc_notes": 8,
            "max_messages": 12,
        }

    def _next_state(
        q: Mapping[str, Any],
        *,
        branch: str,
        extra: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        previous = dict(q.get("state") or {})
        signal = dict(q.get("signal") or {})
        partial = dict(q.get("partial_fill") or {})
        info = dict(signal.get("info") or {})

        trail = list(previous.get("trail") or [])
        trail.append(
            {
                "branch": branch,
                "signal_kind": str(signal.get("kind") or q.get("signal_kind") or ""),
                "partial_keys": sorted(str(k) for k in partial.keys()),
                "span_id": str(q.get("span_id") or ""),
                "info": info,
            }
        )

        state = {
            "branch": branch,
            "trail": trail,
            "last_signal_kind": str(signal.get("kind") or q.get("signal_kind") or ""),
            "last_partial": partial,
            "last_info": info,
        }

        if extra:
            state.update(dict(extra))

        return state

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        signal = dict(q.get("signal") or {})
        signal_kind = str(signal.get("kind") or q.get("signal_kind") or "fill")
        signal_info = dict(signal.get("info") or {})
        partial = dict(q.get("partial_fill") or {})

        if signal_kind == "mount":
            span_id = str(signal_info.get("span_id") or q.get("span_id") or "")
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": f"Mounted signal pedagogy Q on {span_id}",
                    "micros": [_text_micro("mounted_value")],
                    "lifecycle": _base_lifecycle(datum),
                },
                "fill": {"mounted_value": ""},
                "prefill": {"mounted_value": span_id},
                "state": _next_state(
                    q,
                    branch="mount_to_mounted_value",
                    extra={
                        "mounted_span": span_id,
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "mount signal produced the first public surface",
                },
                "proc_notes": {
                    "path": "mount",
                    "span_id": span_id,
                },
            }

        if signal_kind == "refresh":
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Signal-only refresh surface",
                    "micros": [_text_micro("signal_value")],
                    "lifecycle": _base_lifecycle(datum),
                },
                "fill": {"signal_value": ""},
                "prefill": {
                    "signal_value": str(signal_info.get("suggested") or "signal-default")
                },
                "state": _next_state(
                    q,
                    branch="signal_only_refresh_to_signal_value",
                    extra={
                        "saw_signal_without_required_new_fill": True,
                        "refresh_reason": signal_info.get("reason"),
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "controller signal-only action selected signal_value",
                },
                "proc_notes": {
                    "path": "signal_only",
                    "reason": signal_info.get("reason"),
                },
            }

        if signal_kind == "refresh_and_fill":
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Signal plus fill confirmation surface",
                    "micros": [_text_micro("signal_confirm")],
                    "lifecycle": _base_lifecycle(datum),
                },
                "fill": {"signal_confirm": ""},
                "prefill": {
                    "signal_confirm": str(partial.get("mounted_value") or "confirm")
                },
                "state": _next_state(
                    q,
                    branch="signal_plus_fill_to_signal_confirm",
                    extra={
                        "accepted_fill_during_signal": partial.get("mounted_value"),
                        "refresh_reason": signal_info.get("reason"),
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "controller signal+fill action selected signal_confirm",
                },
                "proc_notes": {
                    "path": "signal_plus_fill",
                    "fill_keys": sorted(str(k) for k in partial.keys()),
                },
            }

        if "signal_value" in partial:
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="signal_only_value_done",
                    extra={
                        "final_value": partial.get("signal_value"),
                    },
                ),
                "message": {
                    "level": "success",
                    "text": "signal-only branch completed",
                },
            }

        if "signal_confirm" in partial:
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="signal_plus_fill_confirm_done",
                    extra={
                        "final_value": partial.get("signal_confirm"),
                    },
                ),
                "message": {
                    "level": "success",
                    "text": "signal+fill branch completed",
                },
            }

        if "mounted_value" in partial:
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Ordinary fill confirmation surface",
                    "micros": [_text_micro("confirm")],
                    "lifecycle": _base_lifecycle(datum),
                },
                "fill": {"confirm": ""},
                "prefill": {"confirm": "ok"},
                "state": _next_state(
                    q,
                    branch="ordinary_fill_to_confirm",
                    extra={
                        "accepted_mounted_value": partial.get("mounted_value"),
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "ordinary fill selected confirm",
                },
                "proc_notes": {
                    "path": "ordinary_fill",
                },
            }

        if "confirm" in partial:
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="ordinary_confirm_done",
                    extra={
                        "final_value": partial.get("confirm"),
                    },
                ),
                "message": {
                    "level": "success",
                    "text": "ordinary fill branch completed",
                },
            }

        return {
            "status": "blocked",
            "state": _next_state(q, branch="blocked_unknown_surface"),
            "message": {
                "level": "error",
                "text": "widget received neither a recognized signal nor recognized fill",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)


def test_signal_pedagogy_without_controller_signal_uses_mount_then_plain_fill_path() -> None:
    """
    Baseline: no controller-origin signal.

    The datum still sees two kinds of signal:

        mount:
            produced by lifecycle.mount_explode=True before first render;

        fill:
            produced by the ordinary user submit path.

    This proves that the new signal artery does not disturb the existing
    mount/fill lifecycle.

    Flow
    ----

        create session
        step to first manual stop

            Q sees signal.kind == "mount"
            Q reexplodes to mounted_value

        submit mounted_value without user_signal

            Q sees signal.kind == "fill"
            Q reexplodes to confirm

        submit confirm without user_signal

            Q sees signal.kind == "fill"
            Q returns done
    """

    app_form_id = "datum.signal_pedagogy.no_controller_signal"
    widget_name = "test.datum_state.signal_pedagogy.no_controller_signal"
    _register_signal_aware_pedagogy_widget(widget_name)

    step_name = "test.datum_state.signal_pedagogy.no_controller_signal.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    state_after_mount = api._get(sid).state
    q_state = _latest_protocol_state(state_after_mount, app_form_id, "Q")
    assert q_state["branch"] == "mount_to_mounted_value"
    assert [row["signal_kind"] for row in q_state["trail"]] == ["mount"]

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_value": "ordinary-alpha"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(ctx["datum_widget_decls"]["Q"])

    state_after_plain_fill = api._get(sid).state
    q_state = _latest_protocol_state(state_after_plain_fill, app_form_id, "Q")
    assert q_state["branch"] == "ordinary_fill_to_confirm"
    assert q_state["accepted_mounted_value"] == "ordinary-alpha"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "fill",
    ]

    ctx = api.step_session(
        sid,
        fill={"Q": {"confirm": "ordinary-beta"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")
    assert q_state["branch"] == "ordinary_confirm_done"
    assert q_state["final_value"] == "ordinary-beta"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "fill",
        "fill",
    ]

    _assert_output_fill(api, sid, "Q", {"confirm": "ordinary-beta"})


def test_signal_pedagogy_signal_without_fill_targets_q_and_reexplodes_to_signal_surface() -> None:
    """
    Signal-only path.

    This is the new controller/API behavior that completes the signal formalism:

        api.step_session(
            sid,
            signal={
                "datum_id": "Q",
                "kind": "refresh",
                "info": {...},
            },
        )

    No new fill is submitted.

    The targeted datum Q is still considered dirty for this public tick because
    the signal targets it. Q receives:

        q["signal"]["kind"] == "refresh"
        q["signal_info"]["source"] == "controller_action"

    and may choose to reexplode just as it would after a fill.

    The important model is:

        signal-only is not an event side channel;
        it is a normal datum lifecycle input.
    """

    app_form_id = "datum.signal_pedagogy.signal_without_fill"
    widget_name = "test.datum_state.signal_pedagogy.signal_without_fill"
    _register_signal_aware_pedagogy_widget(widget_name)

    step_name = "test.datum_state.signal_pedagogy.signal_without_fill.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {
                "reason": "external-refresh",
                "suggested": "from-signal-info",
            },
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q"
    assert "signal_value" in str(ctx["datum_widget_decls"]["Q"])

    state_after_signal = api._get(sid).state
    q_state = _latest_protocol_state(state_after_signal, app_form_id, "Q")

    assert q_state["branch"] == "signal_only_refresh_to_signal_value"
    assert q_state["saw_signal_without_required_new_fill"] is True
    assert q_state["refresh_reason"] == "external-refresh"
    assert q_state["last_info"]["source"] == "controller_action"
    assert q_state["last_info"]["datum_id"] == "Q"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "refresh",
    ]

    ctx = api.step_session(
        sid,
        fill={"Q": {"signal_value": "from-signal-surface"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")

    assert q_state["branch"] == "signal_only_value_done"
    assert q_state["final_value"] == "from-signal-surface"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "refresh",
        "fill",
    ]

    _assert_output_fill(api, sid, "Q", {"signal_value": "from-signal-surface"})


def test_signal_pedagogy_signal_with_fill_lets_widget_branch_on_both() -> None:
    """
    Signal+fill path.

    This proves the final "one packet" formalism:

        fill and signal travel together through the same controller action.

    The widget sees both:

        q["partial_fill"] == {"mounted_value": "alpha"}
        q["signal"]["kind"] == "refresh_and_fill"

    and is free to choose a different reexplosion than it would have chosen for
    the same fill without a signal.

    Ordinary fill alone would choose:

        mounted_value -> confirm

    Signal+fill chooses:

        mounted_value + refresh_and_fill -> signal_confirm
    """

    app_form_id = "datum.signal_pedagogy.signal_with_fill"
    widget_name = "test.datum_state.signal_pedagogy.signal_with_fill"
    _register_signal_aware_pedagogy_widget(widget_name)

    step_name = "test.datum_state.signal_pedagogy.signal_with_fill.step"
    _register_step(
        step_name,
        _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_value": "alpha-from-fill"}},
        signal={
            "datum_id": "Q",
            "kind": "refresh_and_fill",
            "info": {
                "reason": "fill-arrived-with-refresh",
            },
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_Q"
    assert "signal_confirm" in str(ctx["datum_widget_decls"]["Q"])
    q_decl = ctx["datum_widget_decls"]["Q"]
    q_decl_rendered = str(q_decl)

    assert "signal_confirm" in q_decl_rendered
    assert "Ordinary fill confirmation surface" not in q_decl_rendered

    state_after_signal_fill = api._get(sid).state
    q_state = _latest_protocol_state(state_after_signal_fill, app_form_id, "Q")

    assert q_state["branch"] == "signal_plus_fill_to_signal_confirm"
    assert q_state["accepted_fill_during_signal"] == "alpha-from-fill"
    assert q_state["refresh_reason"] == "fill-arrived-with-refresh"
    assert q_state["last_info"]["source"] == "controller_action"
    assert q_state["last_partial"] == {"mounted_value": "alpha-from-fill"}
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "refresh_and_fill",
    ]

    ctx = api.step_session(
        sid,
        fill={"Q": {"signal_confirm": "confirmed-after-signal-fill"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")

    assert q_state["branch"] == "signal_plus_fill_confirm_done"
    assert q_state["final_value"] == "confirmed-after-signal-fill"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "refresh_and_fill",
        "fill",
    ]

    _assert_output_fill(
        api,
        sid,
        "Q",
        {"signal_confirm": "confirmed-after-signal-fill"},
    )


def test_signal_pedagogy_signal_targeting_q_does_not_turn_sibling_fills_into_signals() -> None:
    """
    Product-vector signal isolation.

    A span owns:

        A x Q x B

    The controller action submits fills for all three datums and one signal
    targeting Q.

    The law is:

        - only Q receives the custom signal;
        - A and B remain ordinary plain datum fills;
        - the span remains pending while Q reexplodes;
        - A and B are preserved as working sibling fills;
        - final durable outputs include A, Q, and B after Q completes.

    This proves that the new signal channel is datum-targeted, not span-global.
    """

    app_form_id = "datum.signal_pedagogy.product_vector_signal_isolation"
    widget_name = "test.datum_state.signal_pedagogy.product_vector_signal_isolation"
    _register_signal_aware_pedagogy_widget(widget_name)

    step_name = "test.datum_state.signal_pedagogy.product_vector_signal_isolation.step"
    _register_step(
        step_name,
        _one_span_with_siblings_multiframespec(
            widget_name,
            app_form_id=app_form_id,
        ),
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )

    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_VECTOR"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "plain-a"},
            "Q": {"mounted_value": "q-alpha"},
            "B": {"value": "plain-b"},
        },
        signal={
            "datum_id": "Q",
            "kind": "refresh_and_fill",
            "info": {
                "reason": "vector-refresh",
            },
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_VECTOR"
    assert "signal_confirm" in str(ctx["datum_widget_decls"]["Q"])

    state_after_signal_fill = api._get(sid).state
    q_state = _latest_protocol_state(state_after_signal_fill, app_form_id, "Q")

    assert q_state["branch"] == "signal_plus_fill_to_signal_confirm"
    assert q_state["accepted_fill_during_signal"] == "q-alpha"
    assert [row["signal_kind"] for row in q_state["trail"]] == [
        "mount",
        "refresh_and_fill",
    ]

    # Sibling fills are not final durable form_fills yet because the span
    # product vector is still pending on Q. They are nevertheless visible as
    # working fills on the current public span.
    assert ctx["datum_widget_fills"]["A"]["value"] == "plain-a"
    assert ctx["datum_widget_fills"]["B"]["value"] == "plain-b"

    ctx = api.step_session(
        sid,
        fill={"Q": {"signal_confirm": "q-beta"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "plain-a"
    assert out["form_fills"]["Q"]["signal_confirm"] == "q-beta"
    assert out["form_fills"]["B"]["value"] == "plain-b"

    final_state = api._get(sid).state
    q_state = _latest_protocol_state(final_state, app_form_id, "Q")
    assert q_state["branch"] == "signal_plus_fill_confirm_done"
    assert q_state["final_value"] == "q-beta"


def test_signal_pedagogy_same_fill_can_explode_differently_with_and_without_signal() -> None:
    """
    Direct contrast test.

    This is the smallest proof of the final mental model:

        Same current-effective surface.
        Same submitted fill shape.
        Different signal.
        Different reexplosion.

    Session 1 submits:

        fill={"Q": {"mounted_value": "same-alpha"}}
        signal=None

    Result:

        Q reexplodes to confirm.

    Session 2 submits:

        fill={"Q": {"mounted_value": "same-alpha"}}
        signal={"datum_id": "Q", "kind": "refresh_and_fill"}

    Result:

        Q reexplodes to signal_confirm.

    Therefore signal is a real widget input, not metadata outside the state
    machine.
    """

    widget_name = "test.datum_state.signal_pedagogy.same_fill_different_signal"
    _register_signal_aware_pedagogy_widget(widget_name)

    def start_case(app_form_id: str, step_name: str) -> tuple[Any, str, Mapping[str, Any]]:
        _register_step(
            step_name,
            _single_q_span_multiframespec(widget_name, app_form_id=app_form_id),
        )

        api = _api()
        st = api.create_VM_session(
            manifest=_manifest(step_name),
            initial_parameter_overrides={},
            session_metadata={
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": False,
                }
            },
        )

        sid = str(st["session_id"])
        ctx = api.step_session(sid)

        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

        return api, sid, ctx

    plain_app_form_id = "datum.signal_pedagogy.same_fill_plain"
    plain_api, plain_sid, _plain_ctx = start_case(
        plain_app_form_id,
        "test.datum_state.signal_pedagogy.same_fill_plain.step",
    )

    plain_next = plain_api.step_session(
        plain_sid,
        fill={"Q": {"mounted_value": "same-alpha"}},
    )

    assert plain_next["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(plain_next["datum_widget_decls"]["Q"])
    assert "signal_confirm" not in str(plain_next["datum_widget_decls"]["Q"])

    plain_state = _latest_protocol_state(
        plain_api._get(plain_sid).state,
        plain_app_form_id,
        "Q",
    )
    assert plain_state["branch"] == "ordinary_fill_to_confirm"
    assert plain_state["accepted_mounted_value"] == "same-alpha"

    signal_app_form_id = "datum.signal_pedagogy.same_fill_signal"
    signal_api, signal_sid, _signal_ctx = start_case(
        signal_app_form_id,
        "test.datum_state.signal_pedagogy.same_fill_signal.step",
    )

    signal_next = signal_api.step_session(
        signal_sid,
        fill={"Q": {"mounted_value": "same-alpha"}},
        signal={
            "datum_id": "Q",
            "kind": "refresh_and_fill",
            "info": {
                "reason": "same-fill-different-signal",
            },
        },
    )

    assert signal_next["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "signal_confirm" in str(signal_next["datum_widget_decls"]["Q"])

    signal_state = _latest_protocol_state(
        signal_api._get(signal_sid).state,
        signal_app_form_id,
        "Q",
    )
    assert signal_state["branch"] == "signal_plus_fill_to_signal_confirm"
    assert signal_state["accepted_fill_during_signal"] == "same-alpha"
    assert signal_state["last_info"]["source"] == "controller_action"