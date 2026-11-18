# think-backend/tests/wipppp/integration/reexploding_datums/test_datum_lifecycle_system_flags_e2e.py

from __future__ import annotations

"""
Datum Lifecycle System Flags E2E
================================

This file is both an integration test suite and a developer-facing executable
spec for lifecycle-enabled datums.

It is intentionally pedagogical.

The target reader is a developer writing a new datum widget for the first time,
but the laws here should remain precise enough for engine-level maintenance.

Core model
----------

A step function emits a form tree:

    step fn
        ->
    multiframespec
        ->
    frames
        ->
    spans
        ->
    datums

A span is the manual progression unit.

A lifecycle datum is one datum inside that emitted tree whose local behavior is
delegated to a registered datum widget.

The widget is a compact Markovian state machine:

    widget(
        datum_k,
        state_k,
        signal_k,
        fill_or_partial_fill_k,
        ctx_k,
        caps
    )
        ->
    {
        status,
        state_{k+1},
        optional datum_{k+1},
        optional fill_or_prefill,
        optional message,
        optional proc_notes,
    }

The engine owns:

    - step execution,
    - frame/span traversal,
    - manual step planning,
    - mount-time evaluation,
    - touched-field fill evaluation,
    - lifecycle-row persistence,
    - cap enforcement,
    - fill/prefill buckets,
    - span completion.

The widget owns:

    - local datum interpretation,
    - local validation,
    - local reexplosion,
    - compact semantic state evolution,
    - current datum shape,
    - current lifecycle notes/annotations.

Developer memory-channel law
----------------------------

Use lifecycle state for anything the next widget call must reason from.

Use proc_notes for bounded side/debug/provenance metadata that may be inspected
later, but that the widget should not need as its source of truth.

Use message for human-readable current lifecycle notes, errors, warnings, or
explanations.

Formally:

    state:
        - semantic;
        - durable current-effective memory;
        - passed back into the next widget call;
        - not bounded by max_proc_notes or max_messages.

    proc_notes:
        - diagnostic/provenance annotation;
        - retained on the current lifecycle row;
        - bounded by max_proc_notes;
        - not the Markovian source of truth for the next widget call.

    message:
        - human-readable lifecycle note;
        - retained on the current lifecycle row;
        - bounded by max_messages;
        - not a global append-only event log;
        - not the Markovian source of truth for the next widget call.

The next widget call should be able to decide from:

    state + signal + ctx + datum + current fill/partial fill + caps

If the next widget call needs some fact, that fact belongs in state.

Declarative lifecycle flags
---------------------------

A lifecycle-enabled datum may declare:

    lifecycle = {
        "widget": "...",
        "state": {...},
        "mount_explode": bool,
        "max_reexplosions": int,
        "exhausted_means_satisfied": bool,
        "max_proc_notes": int,
        "max_messages": int,
    }

widget:
    Selects the registered datum widget.

state:
    Seeds the first lifecycle row.
    After the first widget result, returned state becomes the current-effective
    state. The seed is not replayed.

mount_explode:
    False means no widget call before first fill.
    True means the widget receives a span-local mount signal before rendering
    for that span.

    Mount is span-local, not merely datum-global. The same logical datum id can
    appear on multiple spans. A later span mount is a new lifecycle signal even
    if the same datum was already mounted or satisfied in an earlier span.

max_reexplosions:
    Caps status="reexplode" transitions.
    If exhausted, the engine forces datum satisfaction instead of allowing an
    infinite reexplode loop.
    Exhaustion means bounded forward progress, not permanent span blocking.

exhausted_means_satisfied:
    Defaults to True.

    True preserves the historical behavior:

        when max_reexplosions is exhausted, the engine marks the datum
        forced_done so the span can advance.

    False means:

        when max_reexplosions is exhausted, the datum blocks and remains
        unsatisfied. The span cannot advance if that datum is authoritative.

    Developer consequence:

        use True for ordinary bounded-progress flows;
        use False for hard-stop flows such as captcha-like gates, irreversible
        failed checks, or must-pass widgets.

max_proc_notes:
    Bounds row["proc_notes"] only.
    It does not cap lifecycle.state, fills, prefills, runtime writes, messages,
    or reexplosions.

max_messages:
    Bounds row["messages"] only.
    It does not cap lifecycle.state, fills, prefills, runtime writes, proc_notes,
    or reexplosions.

Span behavior
-------------

Default span satisfaction:

    span is satisfied iff all required owned datums are satisfied.

For lifecycle datums:

    satisfied iff lifecycle status is done or forced_done.

For plain datums:

    satisfied iff the fill structurally satisfies the datum.

Only touched/manual-signaled pending lifecycle datums are evaluated on fill.
A widget should not assume that all sibling datums in the span are re-evaluated
on every submit.

Authoritative span datums
-------------------------

Spans may declare a subset of owned datums as authoritative:

    span.my_authoritative_datums = ["A"]

Accepted aliases:

    my_authoritative_datums
    authoritative_datums
    authoritative_owns
    authoritative

Law:

    - missing authoritative declaration means all owned datums are
      authoritative, preserving old behavior;
    - declared authoritative ids must be a non-empty subset of owns;
    - all authoritative datums must be satisfied for the span to advance;
    - non-authoritative datums may still be filled;
    - a submit vector is processed before span satisfaction is recomputed.

This is span-level behavior, not widget-level behavior.
"""

from collections.abc import Mapping
from typing import Any, Dict

from __exceptions.engine import DatumLifecycleContractError

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)


from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)

from __exceptions.engine import FatalEngineError
import pytest


from __datomatonTM import (
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    DATUM_LIFECYCLE_STATUS_REEXPLODED,
    KEY_DATUM_LIFECYCLE,
    register_datum_widget_v1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


def _signal(q: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = q.get("signal") or {}
    if isinstance(raw, Mapping):
        return raw
    return {}


def _signal_kind(q: Mapping[str, Any]) -> str:
    """
    Preferred payload shape is q["signal"]["kind"].

    Some older tests/widgets historically inspected q["signal_kind"], so this
    helper accepts both while documenting signal.kind as the canonical model.
    """

    signal = _signal(q)
    return str(signal.get("kind") or q.get("signal_kind") or "")


def _signal_info(q: Mapping[str, Any]) -> Mapping[str, Any]:
    signal = _signal(q)
    info = signal.get("info") or {}
    if isinstance(info, Mapping):
        return info
    return {}


def _partial_fill(q: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Lifecycle fill signals are modeled as partial/touched fills.

    Prefer q["partial_fill"] when present. Fall back to q["fill"] for tolerance
    across local engine call-shape revisions.
    """

    raw = q.get("partial_fill")
    if raw is None:
        raw = q.get("fill")
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def _datum_lifecycle(datum: Mapping[str, Any]) -> Dict[str, Any]:
    lifecycle = datum.get("lifecycle") or {}
    if isinstance(lifecycle, Mapping):
        return dict(lifecycle)
    return {}


def _with_lifecycle(
    datum: Mapping[str, Any],
    *,
    widget_name: str,
    **overrides: Any,
) -> Dict[str, Any]:
    return {
        **dict(datum),
        "lifecycle": {
            **_datum_lifecycle(datum),
            "widget": widget_name,
            **overrides,
        },
    }


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "multiframespec": dict(multiframespec),
        }

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _manifest(step_name: str) -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": "datum_lifecycle_system_flags",
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


def _session_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": False,
        }
    }


def _start_session(step_name: str) -> tuple[Any, str, Mapping[str, Any]]:
    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata=_session_metadata(),
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return api, sid, ctx


def _lifecycle_row(
    api: Any,
    sid: str,
    *,
    app_form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    state = api._get(sid).state
    row = (
        state.get(KEY_DATUM_LIFECYCLE, {})
        .get("forms", {})
        .get(app_form_id, {})
        .get("datums", {})
        .get(datum_id, {})
    )
    assert isinstance(row, Mapping)
    assert row
    return row


def _single_q_multiframespec(
    *,
    app_form_id: str,
    widget_name: str,
    lifecycle: Mapping[str, Any],
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
                    **dict(lifecycle),
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": [datum_id],
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# initial_state + Markovian state
# ---------------------------------------------------------------------------


def test_initial_state_seeds_first_lifecycle_row_then_widget_state_becomes_current_effective() -> None:
    """
    initial_state law.

    lifecycle.state seeds the first row.

    After that, widget-returned state is the current-effective state read by
    the next explosion.

    This proves:

        state_{k+1 input} = state_k output

    not:

        state_{k+1 input} = original initial_state

    Therefore state is the widget's Markovian semantic memory.
    """

    app_form_id = "task_c.initial_state.current_effective"
    widget_name = "test.task_c.initial_state.current_effective"

    seen_previous_states: list[dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        previous = dict(q.get("state") or {})
        partial = _partial_fill(q)
        datum = dict(q["datum"])

        seen_previous_states.append(previous)

        events = list(previous.get("events") or [])
        seed = previous.get("seed")
        generation = int(previous.get("generation") or 0)

        if _signal_kind(q) == "mount":
            events.append("mount")
            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        mount_explode=True,
                        max_reexplosions=4,
                        max_proc_notes=2,
                        max_messages=4,
                    ),
                    "micros": [_text_micro("mounted_value")],
                },
                "fill": {"mounted_value": ""},
                "state": {
                    "seed": seed,
                    "generation": generation + 1,
                    "events": events,
                    "last_seen": "mount",
                },
                "message": {
                    "level": "info",
                    "text": "mounted",
                },
            }

        if "mounted_value" in partial:
            events.append(f"fill:{partial['mounted_value']}")
            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        mount_explode=True,
                        max_reexplosions=4,
                        max_proc_notes=2,
                        max_messages=4,
                    ),
                    "micros": [_text_micro("confirm")],
                },
                "fill": {"confirm": ""},
                "state": {
                    "seed": seed,
                    "generation": generation + 1,
                    "events": events,
                    "last_seen": partial["mounted_value"],
                },
                "message": {
                    "level": "info",
                    "text": "confirm",
                },
            }

        events.append(f"done:{partial.get('confirm')}")
        return {
            "status": "done",
            "state": {
                "seed": seed,
                "generation": generation + 1,
                "events": events,
                "last_seen": partial.get("confirm"),
            },
            "message": {
                "level": "success",
                "text": "done",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    step_name = "test.task_c.initial_state.current_effective.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "state": {
                    "seed": "from_initial_state",
                    "generation": 0,
                    "events": [],
                },
                "mount_explode": True,
                "max_reexplosions": 4,
                "max_proc_notes": 2,
                "max_messages": 4,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)

    assert ctx["current_span"] == "S"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    mount_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert mount_row["state"] == {
        "seed": "from_initial_state",
        "generation": 1,
        "events": ["mount"],
        "last_seen": "mount",
    }

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_value": "alpha"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(ctx["datum_widget_decls"]["Q"])

    row_after_reexplode = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_reexplode["state"] == {
        "seed": "from_initial_state",
        "generation": 2,
        "events": ["mount", "fill:alpha"],
        "last_seen": "alpha",
    }

    ctx = api.step_session(
        sid,
        fill={"Q": {"confirm": "beta"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert final_row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert final_row["state"] == {
        "seed": "from_initial_state",
        "generation": 3,
        "events": ["mount", "fill:alpha", "done:beta"],
        "last_seen": "beta",
    }

    # The widget saw initial_state only on the first invocation.
    assert seen_previous_states[0]["seed"] == "from_initial_state"
    assert seen_previous_states[0]["generation"] == 0

    # Later invocations saw the immediately prior current-effective state.
    assert seen_previous_states[1]["generation"] == 1
    assert seen_previous_states[2]["generation"] == 2


# ---------------------------------------------------------------------------
# mount_explode
# ---------------------------------------------------------------------------


def test_mount_explode_false_does_not_call_widget_before_first_fill() -> None:
    """
    mount_explode=False law.

    A lifecycle datum does not run at first render unless it opts into mount.

    This keeps old fill-driven Q behavior compatible.

    Developer consequence:

        use mount_explode=False when the widget should react only after the
        user touches/fills the datum.
    """

    app_form_id = "task_c.mount_false"
    widget_name = "test.task_c.mount_false"

    calls: list[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(_signal_kind(q))
        return {
            "status": "done",
            "state": {
                "called": len(calls),
            },
            "message": {
                "level": "success",
                "text": "done",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    step_name = "test.task_c.mount_false.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 0,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == []

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "first-fill"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    assert calls == ["fill"]


def test_mount_explode_true_runs_before_first_user_fill_and_can_change_current_datum() -> None:
    """
    mount_explode=True law.

    A lifecycle datum can run before first user input and reexplode into its
    first current-effective datum shape.

    Developer consequence:

        use mount_explode=True when the first rendered shape depends on state,
        prior run context, lookup results, or span-local mount context.
    """

    app_form_id = "task_c.mount_true"
    widget_name = "test.task_c.mount_true"

    calls: list[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(_signal_kind(q))
        datum = dict(q["datum"])
        partial = _partial_fill(q)

        if _signal_kind(q) == "mount":
            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        mount_explode=True,
                        max_reexplosions=3,
                    ),
                    "micros": [_text_micro("mounted_value")],
                },
                "fill": {"mounted_value": ""},
                "state": {
                    "phase": "mounted",
                },
                "message": {
                    "level": "info",
                    "text": "mounted before first fill",
                },
            }

        assert partial == {"mounted_value": "ok"}
        return {
            "status": "done",
            "state": {
                "phase": "done",
                "accepted": partial["mounted_value"],
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    step_name = "test.task_c.mount_true.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": True,
                "max_reexplosions": 3,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)

    assert calls == ["mount"]
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "mounted_value" in str(ctx["datum_widget_decls"]["Q"])

    row_after_mount = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_mount["state"] == {"phase": "mounted"}
    assert row_after_mount["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_value": "ok"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    assert calls == ["mount", "fill"]

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert final_row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert final_row["state"] == {
        "phase": "done",
        "accepted": "ok",
    }


# ---------------------------------------------------------------------------
# max_reexplosions
# ---------------------------------------------------------------------------


def test_max_reexplosions_exhaustion_forces_satisfied_instead_of_blocking_forever() -> None:
    """
    max_reexplosions law.

    If a widget keeps returning status="reexplode", the engine does not let the
    span loop forever.

    Once the cap is exhausted, the datum is forced done and the span may
    complete.

    Therefore max_reexplosions exhaustion means bounded forward progress, not
    permanent span blocking.

    Developer consequence:

        design every reexploding widget to converge before the cap.
    """

    app_form_id = "task_c.max_reexplosions"
    widget_name = "test.task_c.max_reexplosions"

    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **_with_lifecycle(
                    datum,
                    widget_name=widget_name,
                    max_reexplosions=1,
                ),
                "micros": [_text_micro("again")],
            },
            "fill": {"again": ""},
            "state": {
                "attempt_seen": int(q.get("reexplode_count") or 0),
            },
            "message": {
                "level": "warning",
                "text": "asking again",
            },
        }

    register_datum_widget_v1(widget_name, always_reexplode, overwrite=True)

    step_name = "test.task_c.max_reexplosions.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 1,
                "exhausted_means_satisfied": True,
                "max_messages": 4,
            },
        ),
    )

    api, sid, _ctx = _start_session(step_name)

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "first"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "again" in str(ctx["datum_widget_decls"]["Q"])

    row_after_first = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_first["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row_after_first["reexplode_count"] == 1

    ctx = api.step_session(
        sid,
        fill={"Q": {"again": "second"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )

    assert final_row["status"] == DATUM_LIFECYCLE_STATUS_FORCED_DONE
    assert final_row["forced_done"] is True

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"]["again"] == "second"


def test_max_reexplosions_exhaustion_can_block_forever_when_configured_not_satisfied() -> None:
    """
    exhausted_means_satisfied=False law.

    This is the hard-stop variant of max_reexplosions.

    If the widget keeps asking to reexplode after the cap is exhausted, the
    engine returns a blocked lifecycle result instead of forced_done.

    The span stays pending because the authoritative datum is unsatisfied.
    """

    app_form_id = "task_c.max_reexplosions.blocks_when_configured"
    widget_name = "test.task_c.max_reexplosions.blocks_when_configured"

    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **_with_lifecycle(
                    datum,
                    widget_name=widget_name,
                    max_reexplosions=1,
                    exhausted_means_satisfied=False,
                ),
                "micros": [_text_micro("again")],
            },
            "fill": {"again": ""},
            "state": {
                "attempt_seen": int(q.get("reexplode_count") or 0),
            },
            "message": {
                "level": "warning",
                "text": "asking again",
            },
        }

    register_datum_widget_v1(widget_name, always_reexplode, overwrite=True)

    step_name = "test.task_c.max_reexplosions.blocks_when_configured.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 1,
                "exhausted_means_satisfied": False,
                "max_messages": 4,
            },
        ),
    )

    api, sid, _ctx = _start_session(step_name)

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "first"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "again" in str(ctx["datum_widget_decls"]["Q"])

    row_after_first = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_first["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row_after_first["reexplode_count"] == 1

    ctx = api.step_session(
        sid,
        fill={"Q": {"again": "second"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["last_error"]["Q"].startswith("maximum reexplosions reached")

    row_after_block = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_block["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row_after_block.get("forced_done") is not True


# ---------------------------------------------------------------------------
# max_proc_notes + max_messages
# ---------------------------------------------------------------------------


def test_max_proc_notes_and_max_messages_bound_current_lifecycle_row_lists_only() -> None:
    """
    max_proc_notes / max_messages law.

    max_proc_notes bounds row["proc_notes"].

    max_messages bounds row["messages"].

    Neither flag caps:
      - lifecycle.state,
      - accepted form_fills,
      - form_prefills,
      - runtime write count,
      - max_reexplosions.

    These flags exist because messages and proc_notes are retained in the current
    datum lifecycle row for rendering/debugging, not because they are global
    append-only logs.

    Developer consequence:

        If the next widget call must reason from something, put it in state.

        If it is only diagnostic/provenance metadata, put it in proc_notes.

        If it is a human-readable lifecycle note, put it in message.
    """

    app_form_id = "task_c.proc_notes_messages"
    widget_name = "test.task_c.proc_notes_messages"

    target_reexplosions = 5

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        previous = dict(q.get("state") or {})
        n = int(previous.get("n") or 0)

        next_state = {
            "n": n + 1,
            "large_uncapped_by_proc_notes_or_messages": {
                "keys": [f"k{i}" for i in range(n + 1)],
            },
        }

        if n < target_reexplosions:
            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        max_reexplosions=20,
                        max_proc_notes=2,
                        max_messages=3,
                    ),
                    "micros": [_text_micro("value")],
                },
                "fill": {"value": ""},
                "state": next_state,
                "message": {
                    "level": "info",
                    "text": f"phase-{n + 1}",
                },
                "proc_notes": {
                    "phase": n + 1,
                    "debug_only": True,
                },
            }

        return {
            "status": "done",
            "state": next_state,
            "message": {
                "level": "success",
                "text": "done",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    step_name = "test.task_c.proc_notes_messages.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 20,
                "max_proc_notes": 2,
                "max_messages": 3,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)

    for i in range(target_reexplosions + 1):
        ctx = api.step_session(
            sid,
            fill={"Q": {"value": f"tick-{i}"}},
        )

    assert ctx["kind"] == "ATCOMPLETION"

    row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )

    assert row["state"]["n"] == target_reexplosions + 1

    # max_proc_notes capped only the retained proc_notes list.
    assert [b["phase"] for b in row["proc_notes"]] == [4, 5]

    # max_messages capped only the retained message list.
    assert [m["text"] for m in row["messages"]] == [
        "phase-4",
        "phase-5",
        "done",
    ]

    # lifecycle.state was not capped by max_proc_notes or max_messages.
    assert row["state"]["large_uncapped_by_proc_notes_or_messages"]["keys"] == [
        "k0",
        "k1",
        "k2",
        "k3",
        "k4",
        "k5",
    ]


# ---------------------------------------------------------------------------
# mount_explode across spans
# ---------------------------------------------------------------------------


def test_mount_explode_is_span_local_and_later_span_sees_prior_current_state() -> None:
    """
    Cross-span mount law.

    The same logical datum id Q appears on S_FIRST and S_SECOND.

    Because mount_explode=True:

        S_FIRST mount runs.
        S_FIRST fill completes.
        S_SECOND mount still runs later.

    The S_SECOND mount receives the current-effective state produced by S_FIRST,
    so a widget can intentionally carry compact continuity across spans.

    Developer consequence:

        The datum lifecycle row is current-effective across the run, but mount
        delivery is span-local.
    """

    app_form_id = "task_c.mount_span_local"
    widget_name = "test.task_c.mount_span_local"

    mounted_spans: list[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        info = _signal_info(q)
        previous = dict(q.get("state") or {})
        partial = _partial_fill(q)

        span_id = str(info.get("span_id") or q.get("span_id") or "")
        prior_values = list(previous.get("values") or [])
        prior_mounts = list(previous.get("mounts") or [])

        if _signal_kind(q) == "mount":
            mounted_spans.append(span_id)
            prior_mounts.append(span_id)
            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        mount_explode=True,
                        max_reexplosions=20,
                        max_messages=8,
                    ),
                    "micros": [_text_micro(f"mounted_{span_id}")],
                },
                "fill": {f"mounted_{span_id}": ""},
                "state": {
                    "mounts": prior_mounts,
                    "values": prior_values,
                    "last_signal": f"mount:{span_id}",
                },
                "message": {
                    "level": "info",
                    "text": f"mounted:{span_id}",
                },
            }

        submitted = next(iter(partial.values()))
        prior_values.append(str(submitted))

        return {
            "status": "done",
            "state": {
                "mounts": prior_mounts,
                "values": prior_values,
                "last_signal": f"done:{span_id}",
            },
            "message": {
                "level": "success",
                "text": f"done:{span_id}",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "state": {
                        "mounts": [],
                        "values": [],
                    },
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                },
            },
            {
                "id": "SIDE",
                "title": "SIDE",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_FIRST", "owns": ["Q"]},
                    {"id": "S_SIDE", "owns": ["SIDE"]},
                    {"id": "S_SECOND", "owns": ["Q"]},
                ],
            }
        ],
    }

    step_name = "test.task_c.mount_span_local.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)

    assert ctx["current_span"] == "S_FIRST"
    assert "mounted_S_FIRST" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_S_FIRST": "first"}},
    )
    assert ctx["current_span"] == "S_SIDE"

    ctx = api.step_session(
        sid,
        fill={"SIDE": {"value": "plain"}},
    )
    assert ctx["current_span"] == "S_SECOND"

    assert "mounted_S_SECOND" in str(ctx["datum_widget_decls"]["Q"])

    row_before_second_fill = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_before_second_fill["state"]["mounts"] == [
        "S_FIRST",
        "S_SECOND",
    ]
    assert row_before_second_fill["state"]["values"] == ["first"]

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_S_SECOND": "second"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )

    assert mounted_spans == ["S_FIRST", "S_SECOND"]
    assert final_row["state"]["mounts"] == ["S_FIRST", "S_SECOND"]
    assert final_row["state"]["values"] == ["first", "second"]


# ---------------------------------------------------------------------------
# touched-field behavior inside larger spans
# ---------------------------------------------------------------------------


def test_only_touched_pending_lifecycle_datums_reexplode_on_manual_fill() -> None:
    """
    Touched-field law.

    In a span with multiple lifecycle datums, a manual submit for Q1 should not
    cause unrelated pending Q2 to reexplode just because Q2 is a sibling in the
    same span.

    Developer consequence:

        A widget should be local to its datum. Do not design sibling widgets
        that require being called on every submit unless the engine explicitly
        signals them.
    """

    app_form_id = "task_c.touched_only"

    q1_widget_name = "test.task_c.touched_only.q1"
    q2_widget_name = "test.task_c.touched_only.q2"

    calls: list[tuple[str, str]] = []

    def q1_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(("Q1", _signal_kind(q)))
        return {
            "status": "done",
            "state": {
                "accepted": _partial_fill(q),
            },
        }

    def q2_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(("Q2", _signal_kind(q)))
        return {
            "status": "done",
            "state": {
                "accepted": _partial_fill(q),
            },
        }

    register_datum_widget_v1(q1_widget_name, q1_widget, overwrite=True)
    register_datum_widget_v1(q2_widget_name, q2_widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "Q1",
                "title": "Q1",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": q1_widget_name,
                    "mount_explode": False,
                    "max_reexplosions": 2,
                },
            },
            {
                "id": "Q2",
                "title": "Q2",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": q2_widget_name,
                    "mount_explode": False,
                    "max_reexplosions": 2,
                },
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["Q1", "Q2"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.touched_only.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"Q1": {"value": "one"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == [("Q1", "fill")]

    ctx = api.step_session(
        sid,
        fill={"Q2": {"value": "two"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == [("Q1", "fill"), ("Q2", "fill")]


# ---------------------------------------------------------------------------
# Authoritative datums
# ---------------------------------------------------------------------------


def test_authoritative_datum_satisfies_whole_span_even_when_siblings_are_pending() -> None:
    """
    Authoritative-span law.

    Span semantics:

        span owns A, B
        span.my_authoritative_datums = ["A"]

    If A is satisfied, the whole span is satisfied, even if B is still pending.

    This is a span-level override, not a datum lifecycle behavior.
    """

    app_form_id = "task_c.authoritative_span"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "Non-authoritative B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                        "my_authoritative_datums": ["A"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.authoritative_span.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "authoritative"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "authoritative"
    assert "B" not in out["form_fills"]


def test_authoritative_span_processes_non_authoritative_sibling_fills_in_same_submit_before_advancing() -> None:
    """
    Fill-vector absorption law.

    Authoritative controls advancement, not whether sibling fills are ignored.

    If a submit contains both:
        A authoritative and valid
        B non-authoritative and valid

    both are committed before the span advances.
    """

    app_form_id = "task_c.authoritative_span_absorbs_sibling_fill"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "Non-authoritative B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                        "my_authoritative_datums": ["A"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.authoritative_span_absorbs_sibling_fill.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "authoritative"},
            "B": {"value": "also-accepted"},
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "authoritative"
    assert out["form_fills"]["B"]["value"] == "also-accepted"


def test_authoritative_span_with_multiple_authorities_requires_all_authorities() -> None:
    """
    Multiple-authoritative law.

    If a span declares A and B authoritative, A alone is not enough.
    The span advances only after both A and B are satisfied.
    """

    app_form_id = "task_c.authoritative_span_requires_all_authorities"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "Authoritative B",
                "micros": [_text_micro("value")],
            },
            {
                "id": "C",
                "title": "Non-authoritative C",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B", "C"],
                        "my_authoritative_datums": ["A", "B"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.authoritative_span_requires_all_authorities.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "one"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"B": {"value": "two"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "one"
    assert out["form_fills"]["B"]["value"] == "two"
    assert "C" not in out["form_fills"]


def test_missing_authoritative_declaration_preserves_all_owned_datums_required_behavior() -> None:
    """
    Back-compat law.

    If a span has no authoritative declaration, all owned datums are
    authoritative. This is the historical behavior.
    """

    app_form_id = "task_c.authoritative_span_default_all"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.authoritative_span_default_all.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "one"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"B": {"value": "two"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "one"
    assert out["form_fills"]["B"]["value"] == "two"


# ---------------------------------------------------------------------------
# Additional developer-facing stories:
# proper/improper system flag usage and expectations
# ---------------------------------------------------------------------------


def test_exhausted_means_satisfied_defaults_to_true_for_back_compat() -> None:
    """
    Default exhaustion law.

    exhausted_means_satisfied is optional.

    If omitted, the engine preserves historical behavior:

        max_reexplosions exhausted
            ->
        forced_done
            ->
        span may advance

    Developer consequence:

        omit exhausted_means_satisfied for ordinary bounded-progress widgets
        where "too many reexplosions" should become forward progress.

        set exhausted_means_satisfied=False only for hard-stop widgets.
    """

    app_form_id = "task_c.default_exhaustion_is_satisfied"
    widget_name = "test.task_c.default_exhaustion_is_satisfied"

    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **_with_lifecycle(
                    datum,
                    widget_name=widget_name,
                    max_reexplosions=1,
                    # Intentionally omit exhausted_means_satisfied.
                ),
                "micros": [_text_micro("again")],
            },
            "fill": {"again": ""},
            "state": {
                "seen_reexplode_count": int(q.get("reexplode_count") or 0),
            },
            "message": {
                "level": "warning",
                "text": "still reexploding",
            },
        }

    register_datum_widget_v1(widget_name, always_reexplode, overwrite=True)

    step_name = "test.task_c.default_exhaustion_is_satisfied.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 1,
                # Intentionally omit exhausted_means_satisfied.
            },
        ),
    )

    api, sid, _ctx = _start_session(step_name)

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "first"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    row_after_first = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_first["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row_after_first["reexplode_count"] == 1

    ctx = api.step_session(
        sid,
        fill={"Q": {"again": "second"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert final_row["status"] == DATUM_LIFECYCLE_STATUS_FORCED_DONE
    assert final_row["forced_done"] is True


def test_blocked_status_rejects_current_submit_without_committing_fill_or_satisfied_lifecycle_status() -> None:
    """
    blocked status law.

    A widget may return status="blocked" to reject the current touched fill.

    That is not:

        - done;
        - forced_done;
        - reexplode;
        - a fill commit;
        - span satisfaction.

    The engine may create a lifecycle placeholder row while evaluating the datum,
    but the blocked result is not committed as a satisfied lifecycle state.

    Developer consequence:

        use blocked for recoverable validation failure.

        The rejected form fill is not committed.

        The span remains pending.

        The retry should be able to submit a corrected value.
    """

    app_form_id = "task_c.blocked_status_no_commit"
    widget_name = "test.task_c.blocked_status_no_commit"

    calls: list[dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = _partial_fill(q)
        calls.append(
            {
                "signal": _signal_kind(q),
                "partial": partial,
                "state": dict(q.get("state") or {}),
            }
        )

        value = str(partial.get("value") or "")

        if value == "bad":
            return {
                "status": "blocked",
                "state": {
                    "last_rejected": value,
                },
                "message": {
                    "level": "error",
                    "text": "bad value rejected",
                },
            }

        return {
            "status": "done",
            "state": {
                "accepted": value,
            },
            "message": {
                "level": "success",
                "text": "accepted",
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    step_name = "test.task_c.blocked_status_no_commit.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "state": {
                    "seed": "initial",
                },
                "mount_explode": False,
                "max_reexplosions": 2,
                "max_messages": 4,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "bad"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["last_error"]["Q"] == "bad value rejected"

    state = api._get(sid).state
    lifecycle_rows = (
        state.get(KEY_DATUM_LIFECYCLE, {})
        .get("forms", {})
        .get(app_form_id, {})
        .get("datums", {})
    )

    # The engine may create a placeholder row while evaluating a lifecycle
    # datum, but the blocked result must not become a satisfied status.
    if "Q" in lifecycle_rows:
        blocked_placeholder = lifecycle_rows["Q"]

        assert blocked_placeholder.get("status") not in {
            DATUM_LIFECYCLE_STATUS_DONE,
            DATUM_LIFECYCLE_STATUS_FORCED_DONE,
            DATUM_LIFECYCLE_STATUS_REEXPLODED,
        }
        assert blocked_placeholder.get("forced_done") is not True

    # The rejected fill was not committed.
    out = api.get_outputs(sid)
    assert "Q" not in out.get("form_fills", {})

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "good"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    final_row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert final_row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert final_row["state"] == {"accepted": "good"}

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"]["value"] == "good"

    # The first blocked submit did not commit a successful lifecycle transition.
    assert calls[0]["state"] == {"seed": "initial"}

    

def test_non_authoritative_lifecycle_datum_does_not_block_span_when_untouched() -> None:
    """
    Non-authoritative untouched law.

    A non-authoritative lifecycle datum may be pending, invalid, or capable of
    blocking if touched.

    But if it is not touched and all authoritative datums are satisfied, it does
    not prevent span advancement.

    Developer consequence:

        authoritative controls span advancement.

        touched-field evaluation controls which lifecycle widgets run.

        Non-authoritative does not mean the datum is deleted or globally ignored.
    """

    app_form_id = "task_c.nonauthoritative_lifecycle_untouched"
    widget_name = "test.task_c.nonauthoritative_lifecycle_untouched"

    calls: list[str] = []

    def hard_stop_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(_signal_kind(q))
        return {
            "status": "blocked",
            "state": {
                "should_not_have_been_called": True,
            },
            "message": {
                "level": "error",
                "text": "Q blocks when touched",
            },
        }

    register_datum_widget_v1(widget_name, hard_stop_widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative plain datum",
                "micros": [_text_micro("value")],
            },
            {
                "id": "Q",
                "title": "Non-authoritative hard-stop lifecycle datum",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": False,
                    "max_reexplosions": 0,
                    "exhausted_means_satisfied": False,
                },
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "Q"],
                        "my_authoritative_datums": ["A"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.nonauthoritative_lifecycle_untouched.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "authoritative"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == []

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "authoritative"
    assert "Q" not in out["form_fills"]


def test_touched_non_authoritative_blocking_lifecycle_datum_rejects_whole_submit() -> None:
    """
    Non-authoritative touched law.

    Non-authoritative affects span-completion requirements only.

    It does not mean:

        - invalid touched fills are ignored;
        - blocked lifecycle results are ignored;
        - sibling fills in the same submit are partially committed.

    If a submit touches both:

        A authoritative and valid
        Q non-authoritative but blocked

    the whole submit is rejected.

    Developer consequence:

        do not include optional/non-authoritative widget fills in a submit vector
        unless they are valid according to that widget.
    """

    app_form_id = "task_c.nonauthoritative_lifecycle_touched_blocks"
    widget_name = "test.task_c.nonauthoritative_lifecycle_touched_blocks"

    calls: list[Dict[str, Any]] = []

    def hard_stop_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = _partial_fill(q)
        calls.append(
            {
                "signal": _signal_kind(q),
                "partial": partial,
            }
        )

        return {
            "status": "blocked",
            "state": {
                "rejected": partial,
            },
            "message": {
                "level": "error",
                "text": "optional Q was touched and rejected",
            },
        }

    register_datum_widget_v1(widget_name, hard_stop_widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative plain datum",
                "micros": [_text_micro("value")],
            },
            {
                "id": "Q",
                "title": "Non-authoritative lifecycle datum",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": False,
                    "max_reexplosions": 0,
                    "exhausted_means_satisfied": False,
                    "max_messages": 4,
                },
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "Q"],
                        "my_authoritative_datums": ["A"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.nonauthoritative_lifecycle_touched_blocks.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "authoritative"},
            "Q": {"value": "bad optional value"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["last_error"]["Q"] == "optional Q was touched and rejected"

    # The non-authoritative blocked Q caused the submit to fail atomically.
    # A was not partially committed.
    out = api.get_outputs(sid)
    assert "A" not in out.get("form_fills", {})
    assert "Q" not in out.get("form_fills", {})

    assert calls == [
        {
            "signal": "fill",
            "partial": {"value": "bad optional value"},
        }
    ]

    # Retrying with only the authoritative datum lets the span advance.
    ctx = api.step_session(
        sid,
        fill={"A": {"value": "authoritative"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "authoritative"
    assert "Q" not in out["form_fills"]


@pytest.mark.parametrize(
    "alias",
    [
        "my_authoritative_datums",
        "authoritative_datums",
        "authoritative_owns",
        "authoritative",
    ],
)
def test_authoritative_span_aliases_are_equivalent(alias: str) -> None:
    """
    Authoritative alias law.

    The engine accepts four spellings for the same span-level concept:

        my_authoritative_datums
        authoritative_datums
        authoritative_owns
        authoritative

    All aliases mean:

        declared ids are the complete authoritative subset;
        all declared authoritative ids must be satisfied;
        non-declared owned ids are non-authoritative.
    """

    app_form_id = f"task_c.authoritative_alias.{alias}"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "Non-authoritative B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                        alias: ["A"],
                    }
                ],
            }
        ],
    }

    step_name = f"test.task_c.authoritative_alias.{alias}.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"A": {"value": alias}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == alias
    assert "B" not in out["form_fills"]


@pytest.mark.parametrize(
    "bad_authoritative",
    [
        [],
        ["NOT_OWNED"],
        ["A", "NOT_OWNED"],
    ],
)
def test_invalid_authoritative_declarations_fail_fast(bad_authoritative: list[str]) -> None:
    """
    Improper authoritative declaration law.

    A declared authoritative set must be:

        - non-empty;
        - a subset of span.owns.

    Invalid declarations are engine/spec errors, not runtime optional behavior.

    Developer consequence:

        use missing declaration to mean "all owned datums are authoritative."

        do not use [] to mean "nothing required."
    """

    suffix = "_".join(bad_authoritative) if bad_authoritative else "empty"
    app_form_id = f"task_c.invalid_authoritative.{suffix}"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                        "my_authoritative_datums": bad_authoritative,
                    }
                ],
            }
        ],
    }

    step_name = f"test.task_c.invalid_authoritative.{suffix}.step"
    _register_step(step_name, multiframespec)

    with pytest.raises(ValueError):
        _start_session(step_name)


def test_mount_signal_contains_span_local_context_for_widget_decisions() -> None:
    """
    Mount signal context law.

    mount_explode=True sends a real lifecycle signal before first user fill.

    The signal is span-local.

    The widget may use signal.info to make first-render decisions based on the
    current frame/span/datum context.

    Developer consequence:

        use signal.kind == "mount" plus signal.info for first-render decisions.

        do not fake mount behavior by treating an empty fill as a mount.
    """

    app_form_id = "task_c.mount_signal_context"
    widget_name = "test.task_c.mount_signal_context"

    seen_mount_infos: list[dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])

        if _signal_kind(q) == "mount":
            info = dict(_signal_info(q))
            seen_mount_infos.append(info)

            span_id = str(info.get("span_id") or "")
            frame_id = str(info.get("frame_id") or "")

            return {
                "status": "reexplode",
                "datum": {
                    **_with_lifecycle(
                        datum,
                        widget_name=widget_name,
                        mount_explode=True,
                        max_reexplosions=4,
                    ),
                    "micros": [_text_micro("mounted_context")],
                },
                "fill": {
                    "mounted_context": f"{frame_id}:{span_id}",
                },
                "state": {
                    "mount_info": info,
                },
                "message": {
                    "level": "info",
                    "text": f"mounted for {frame_id}:{span_id}",
                },
            }

        partial = _partial_fill(q)
        return {
            "status": "done",
            "state": {
                "accepted": partial,
            },
        }

    register_datum_widget_v1(widget_name, widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 4,
                },
            }
        ],
        "frames": [
            {
                "id": "F_CONTEXT",
                "spans": [
                    {
                        "id": "S_CONTEXT",
                        "owns": ["Q"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.mount_signal_context.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_CONTEXT"
    assert "mounted_context" in str(ctx["datum_widget_decls"]["Q"])

    assert len(seen_mount_infos) == 1

    mount_info = seen_mount_infos[0]

    # Current E2E contract: mount carries span-local routing context.
    #
    # Do not assert app_form_id/datum_id here unless the engine explicitly
    # decides to make those part of signal.info.
    assert mount_info["frame_id"] == "F_CONTEXT"
    assert mount_info["span_id"] == "S_CONTEXT"

    row_after_mount = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row_after_mount["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row_after_mount["state"]["mount_info"]["span_id"] == "S_CONTEXT"

    ctx = api.step_session(
        sid,
        fill={"Q": {"mounted_context": "F_CONTEXT:S_CONTEXT"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"


def test_invalid_widget_status_is_fatal() -> None:
    """
    Improper widget status law.

    A datum widget must return a supported status.

    Unsupported statuses are programmer errors.

    At the E2E session layer, the important contract is:

        - the bad result is not treated as done;
        - the fill is not committed;
        - the span does not advance;
        - the user/developer gets a field-level error.

    Lower-level unit tests may assert FatalEngineError directly from lifecycle
    normalization helpers. This E2E test asserts the session-facing behavior.
    """

    app_form_id = "task_c.invalid_widget_status"
    widget_name = "test.task_c.invalid_widget_status"

    def invalid_status_widget(_q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "ok_but_not_a_lifecycle_status",
            "state": {
                "this_should_not_commit": True,
            },
            "message": {
                "level": "info",
                "text": "invalid status should fail",
            },
        }

    register_datum_widget_v1(widget_name, invalid_status_widget, overwrite=True)

    step_name = "test.task_c.invalid_widget_status.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 2,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    with pytest.raises(DatumLifecycleContractError):
        ctx = api.step_session(
            sid,
            fill={"Q": {"value": "trigger invalid status"}},
        )

    

def test_reexplode_result_without_replacement_datum_is_fatal() -> None:
    """
    Improper reexplode contract law.

    status="reexplode" means:

        replace the current-effective datum shape.

    Therefore the widget should provide datum_{k+1}.

    At the E2E session layer, malformed reexplode output must not be silently
    treated as done and must not commit the submitted fill.

    Developer consequence:

        when returning reexplode, always return the complete next datum shape,
        including lifecycle metadata needed for future calls.
    """

    app_form_id = "task_c.reexplode_without_datum"
    widget_name = "test.task_c.reexplode_without_datum"

    def malformed_reexplode_widget(_q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "reexplode",
            # Intentionally omit "datum".
            "fill": {
                "value": "replacement fill without replacement datum",
            },
            "state": {
                "malformed": True,
            },
            "message": {
                "level": "error",
                "text": "malformed reexplode",
            },
        }

    register_datum_widget_v1(widget_name, malformed_reexplode_widget, overwrite=True)

    step_name = "test.task_c.reexplode_without_datum.step"
    _register_step(
        step_name,
        _single_q_multiframespec(
            app_form_id=app_form_id,
            widget_name=widget_name,
            lifecycle={
                "mount_explode": False,
                "max_reexplosions": 2,
            },
        ),
    )

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    with pytest.raises(DatumLifecycleContractError):
    
        ctx = api.step_session(
            sid,
            fill={"Q": {"value": "trigger malformed reexplode"}},
        )


def test_plain_required_sibling_still_validates_when_submitted_with_authoritative_fill() -> None:
    """
    Submitted sibling validation law.

    Authoritative controls whether the span may advance.

    It does not disable validation for non-authoritative siblings that are
    actually submitted.

    If a non-authoritative sibling is submitted in an invalid structural shape,
    the submit is rejected.

    Developer consequence:

        optional/non-authoritative siblings should be omitted from the fill
        vector unless the client has a structurally valid fill for them.
    """

    app_form_id = "task_c.nonauthoritative_plain_invalid_shape"

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Authoritative A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "B",
                "title": "Non-authoritative B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["A", "B"],
                        "my_authoritative_datums": ["A"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.nonauthoritative_plain_invalid_shape.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "authoritative"},
            # B is touched but structurally invalid because required "value"
            # is omitted.
            "B": {},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "B" in ctx["last_error"]

    out = api.get_outputs(sid)
    assert "A" not in out.get("form_fills", {})
    assert "B" not in out.get("form_fills", {})

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "authoritative"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "authoritative"
    assert "B" not in out["form_fills"]


def test_authoritative_lifecycle_datum_must_be_lifecycle_satisfied_not_merely_structurally_filled() -> None:
    """
    Lifecycle satisfaction law for authoritative datums.

    A lifecycle datum is satisfied by lifecycle status, not merely by having a
    structurally valid fill.

    If authoritative Q returns blocked, the span cannot advance even if the
    submitted fill structurally satisfies Q's micros.

    Developer consequence:

        for lifecycle datums, widget status is the source of satisfaction.

        structural fill validity is necessary input hygiene, not final
        lifecycle satisfaction.
    """

    app_form_id = "task_c.authoritative_lifecycle_status_controls_satisfaction"
    widget_name = "test.task_c.authoritative_lifecycle_status_controls_satisfaction"

    def gate_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        value = str(_partial_fill(q).get("value") or "")

        if value != "pass":
            return {
                "status": "blocked",
                "state": {
                    "last_value": value,
                },
                "message": {
                    "level": "error",
                    "text": "gate did not pass",
                },
            }

        return {
            "status": "done",
            "state": {
                "last_value": value,
                "passed": True,
            },
            "message": {
                "level": "success",
                "text": "gate passed",
            },
        }

    register_datum_widget_v1(widget_name, gate_widget, overwrite=True)

    multiframespec = {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "Q",
                "title": "Authoritative lifecycle gate",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": False,
                    "max_reexplosions": 0,
                    "exhausted_means_satisfied": False,
                    "max_messages": 4,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": ["Q"],
                        "my_authoritative_datums": ["Q"],
                    }
                ],
            }
        ],
    }

    step_name = "test.task_c.authoritative_lifecycle_status_controls_satisfaction.step"
    _register_step(step_name, multiframespec)

    api, sid, ctx = _start_session(step_name)
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "structurally valid but semantically blocked"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["last_error"]["Q"] == "gate did not pass"

    out = api.get_outputs(sid)
    assert "Q" not in out.get("form_fills", {})

    ctx = api.step_session(
        sid,
        fill={"Q": {"value": "pass"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"

    row = _lifecycle_row(
        api,
        sid,
        app_form_id=app_form_id,
        datum_id="Q",
    )
    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert row["state"]["passed"] is True

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"]["value"] == "pass"
