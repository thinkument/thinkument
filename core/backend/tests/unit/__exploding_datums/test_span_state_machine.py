from __future__ import annotations

"""
Span Vector State Machine — Q Formalism E2E
===========================================

This file is executable documentation for the App Table datum lifecycle model.

Mental model
------------
A step function emits a multiframespec. The engine lowers that emitted form into
ordered manual span stops. Each span S owns an ordered vector of datum machines:

    V_S = (D1, D2, ..., Dk)

A public submit is a candidate transition over the whole current span vector:

    T_submit(V_S, fill) -> Decision

where Decision is exactly one of:

    blocked(error)
        Keep the public span vector unchanged. No candidate fills commit.

    reexplode(Di -> Di')
        Keep the same current span. Persist the lifecycle shell for Di. Rebuild
        the public span vector with Di' and require another submit.

    done(V_S')
        Commit all authoritative accepted datum fills for the span atomically.
        Advance to the next unsatisfied manual span, or completion.

This is a product-vector machine, not independent field submission. A P datum
without lifecycle is a fast-path datum machine. A Q datum has a lifecycle widget
that may block, finish, or reexplode into a new datum spec. A span is satisfied
only when all authoritative datum machines in its vector are satisfied.

Ownership boundaries
--------------------
The engine owns:
    - span atomicity;
    - datum lifecycle persistence;
    - Q reexplosion caps;
    - forced-done safety;
    - undo/redo public tape semantics;
    - compact runtime-write query/index surfaces.

The widget owns only:
    - interpreting its datum-local partial fill;
    - returning one lifecycle decision;
    - proposing a replacement datum spec on reexplode.

The renderer/front-end owns only:
    - presenting the current public vector;
    - submitting fills back through the engine-normalized input wall.

Proofs in this sheet
--------------------
1. P datums remain P-fast-path and do not create Q lifecycle rows.
2. Q reexplode is a public transition on the same span vector.
3. Undo after Q reexplode restores the previous vector/shell.
4. Redo after that undo restores the reexploded vector/shell.
5. Blocking Q does not commit partial state.
6. Multi-datum spans are atomic: a P sibling is not durably committed if a Q
   sibling reexplodes.
7. Forced-done cap dominates hostile widgets.
8. Respanned Q datums reuse lifecycle state and skip once satisfied.
9. Redo branch clears after a new public vector transition.
10. Runner history stays slim even when lifecycle proc_notes is large.
11. Many Q transitions scale with public actions, not snapshots/history.

Reference pseudocode
--------------------
For a current manual step over span S with owned datums owns(S):

    def submit_span(S, fill):
        candidate = []
        lifecycle_patch = []

        for datum in owns(S):
            machine = datum_machine(datum)
            decision = machine.evaluate(fill.get(datum.id))

            if decision.blocked:
                return same_public_vector_with_error()

            if decision.reexplode:
                lifecycle_patch.append(decision.shell_patch)
                return same_span_with_reexploded_vector(lifecycle_patch)

            candidate.append(decision.accepted_fill)

        commit_all(candidate)
        mark_span_satisfied(S)
        return next_unsatisfied_span_or_completion()

The tests below assert that this is the observed public behavior.
"""

import time
from typing import Any, Dict, List, Mapping

import pytest

from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
    run_session_against_script_headless,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api():
    return get_concrete_session_api()


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _manifest(step_name: str) -> List[Dict[str, Any]]:
    return [{"public_step_name": "app", "step_fn": step_name, "fn_args": {}}]


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _datum_by_id_from_ctx(ctx: Mapping[str, Any], datum_id: str) -> Dict[str, Any]:
    fs = ctx.get("multiframespec")
    if not isinstance(fs, Mapping):
        return {}

    for d in list(fs.get("datums") or []):
        if isinstance(d, Mapping) and str(d.get("id") or "") == str(datum_id):
            return dict(d)

    return {}


def _micro_names(datum: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for m in list(datum.get("micros") or []):
        if isinstance(m, Mapping):
            out.append(str(m.get("name") or "value"))
    return out or ["value"]


def _lifecycle_row(api, sid: str, form_id: str, datum_id: str) -> Dict[str, Any]:
    state = api._get(sid).state
    store = state.get(KEY_DATUM_LIFECYCLE)
    if not isinstance(store, Mapping):
        return {}

    forms = store.get("forms")
    if not isinstance(forms, Mapping):
        return {}

    form = forms.get(str(form_id))
    if not isinstance(form, Mapping):
        return {}

    datums = form.get("datums")
    if not isinstance(datums, Mapping):
        return {}

    row = datums.get(str(datum_id))
    return dict(row) if isinstance(row, Mapping) else {}


def _span_vector(
    api,
    sid: str,
    ctx: Mapping[str, Any],
    owns: List[str],
) -> Dict[str, Any]:
    """
    Build a compact pedagogical view of the current public span vector.

    This intentionally does not expose every implementation detail. It gives
    each test a stable way to speak in the formalism:

        V_S = {
            current_span,
            owns,
            datums: {
                D: {
                    pending,
                    status,
                    micros,
                    has_committed_fill,
                    reexplode_count,
                    forced_done,
                }
            }
        }
    """
    form_id = str(ctx.get("form_id") or ctx.get("app_form_id") or "")
    pending = set(str(x) for x in list(ctx.get("datum_widgets_on_this_span") or []))

    outputs = api.get_outputs(sid)
    fills = outputs.get("form_fills") if isinstance(outputs, Mapping) else {}
    fills = fills if isinstance(fills, Mapping) else {}

    datums: Dict[str, Any] = {}

    for did in owns:
        datum = _datum_by_id_from_ctx(ctx, did)
        row = _lifecycle_row(api, sid, form_id, did)

        lifecycle_status = row.get("status") if row else None
        if lifecycle_status:
            status = str(lifecycle_status)
        elif did in fills:
            status = "done_p"
        else:
            status = "pending_p"

        datums[did] = {
            "datum_id": did,
            "pending": did in pending,
            "status": status,
            "micros": _micro_names(datum),
            "has_committed_fill": did in fills,
            "reexplode_count": int(row.get("reexplode_count", 0) or 0) if row else 0,
            "forced_done": bool(row.get("forced_done", False)) if row else False,
        }

    return {
        "kind": ctx.get("kind"),
        "form_id": form_id,
        "current_span": ctx.get("current_span"),
        "owns": list(owns),
        "datums": datums,
    }


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 200_000) -> bool:
    """
    Recursive containment check used to prove giant lifecycle proc_notes stays out
    of slim public/query surfaces.
    """
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
            for k, v in cur.items():
                stack.append(k)
                stack.append(v)
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


# ---------------------------------------------------------------------------
# Datum lifecycle widgets
# ---------------------------------------------------------------------------


def _register_widgets() -> None:
    """
    Register deterministic widget machines used by the tests.

    Each widget receives a datum-local lifecycle query and returns one of the
    engine-recognized Q decisions:
        - blocked
        - reexplode
        - done
    """

    def q_confirm_once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            ok = str(partial.get("confirm") or "").strip().lower() in {
                "yes",
                "y",
                "true",
                "1",
            }
            if not ok:
                return {
                    "status": "blocked",
                    "message": {"level": "error", "text": "confirmation must be yes"},
                    "state": {"phase": "confirm"},
                }

            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm value",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "span.vector.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "please confirm"},
            "proc_notes": {"audit": "tiny"},
        }

    def q_amount_cap(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = dict(q.get("partial_fill") or {})
        try:
            amount = float(partial.get("value"))
        except Exception:
            amount = 0.0

        if amount > 10:
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "amount too high"},
                "state": {"last_amount": amount},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": "amount accepted"},
            "state": {"last_amount": amount},
        }

    def q_hostile_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("again")],
                "lifecycle": {
                    "widget": "span.vector.q_hostile_reexplode",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            },
            "fill": {"again": ""},
            "state": {"hostile": True},
            "message": {"level": "info", "text": "again"},
            "proc_notes": {"tiny": True},
        }

    def q_giant_reexplode_once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "span.vector.q_giant_reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"giant": "Z" * 700_000},
        }

    register_datum_widget_v1(
        "span.vector.q_confirm_once",
        q_confirm_once,
        overwrite=True,
    )
    register_datum_widget_v1(
        "span.vector.q_amount_cap",
        q_amount_cap,
        overwrite=True,
    )
    register_datum_widget_v1(
        "span.vector.q_hostile_reexplode",
        q_hostile_reexplode,
        overwrite=True,
    )
    register_datum_widget_v1(
        "span.vector.q_giant_reexplode_once",
        q_giant_reexplode_once,
        overwrite=True,
    )


@pytest.fixture(autouse=True)
def _setup() -> None:
    StepFnregistry.clear()
    _register_widgets()


# ---------------------------------------------------------------------------
# Multiframespec fixtures
# ---------------------------------------------------------------------------


def _q_confirm_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.confirm",
        "datums": [
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_Q", "owns": ["Q"]}],
            }
        ],
    }


def _blocking_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.blocking",
        "datums": [
            {
                "id": "AMOUNT",
                "title": "Amount",
                "micros": [_number_micro()],
                "lifecycle": {
                    "widget": "span.vector.q_amount_cap",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {
                "id": "NEXT",
                "title": "Next",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_AMOUNT", "owns": ["AMOUNT"]},
                    {"id": "S_NEXT", "owns": ["NEXT"]},
                ],
            }
        ],
    }


def _multi_datum_atomic_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.atomic",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
            },
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            {
                "id": "C",
                "title": "C",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_AQ", "owns": ["A", "Q"]},
                    {"id": "S_C", "owns": ["C"]},
                ],
            }
        ],
    }


def _respanned_q_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.respanned",
        "datums": [
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            {
                "id": "END",
                "title": "End",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_Q_FIRST", "owns": ["Q"]},
                    {"id": "S_Q_AGAIN", "owns": ["Q"]},
                    {"id": "S_END", "owns": ["END"]},
                ],
            }
        ],
    }


def _forced_done_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.forced",
        "datums": [
            {
                "id": "LOOP",
                "title": "Loop",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_hostile_reexplode",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_LOOP", "owns": ["LOOP"]}],
            }
        ],
    }


def _plain_p_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "span.vector.plain.p",
        "datums": [
            {
                "id": "P",
                "title": "P",
                "micros": [_text_micro()],
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_P", "owns": ["P"]}],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_plain_p_span_vector_uses_fast_path_and_creates_no_q_lifecycle_rows():
    """
    P-fast-path law:

        D_P(fill) -> done_p

    No Q lifecycle row or lifecycle runtime-write row is created for a datum
    with no lifecycle widget.
    """
    step_name = "span.vector.plain.p.step"
    _register_step(step_name, _plain_p_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled"}},
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    v0 = _span_vector(api, sid, ctx, ["P"])

    assert v0["current_span"] == "S_P"
    assert v0["datums"]["P"]["status"] == "pending_p"
    assert v0["datums"]["P"]["pending"] is True

    ctx = api.step_session(sid, fill={"P": {"value": "done"}})
    assert ctx["kind"] == "ATCOMPLETION"

    state = api._get(sid).state
    store = state.get(KEY_DATUM_LIFECYCLE)
    if isinstance(store, Mapping):
        assert store.get("forms") in ({}, None)

    q = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 10,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert q["writes"] == []


def test_q_reexplode_is_same_span_vector_transition_then_done_exits_span():
    """
    Q reexplode law:

        V_S(Q.start) -> V_S'(Q.confirm)

    The current span remains S_Q. Only the Q datum spec/shell changes. A later
    done decision commits the accepted fill and exits the span.
    """
    step_name = "span.vector.q.confirm.step"
    _register_step(step_name, _q_confirm_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {"persistence": "disabled"},
            "redo": {"max_depth": 16},
        },
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    v0 = _span_vector(api, sid, ctx, ["Q"])

    assert v0["current_span"] == "S_Q"
    assert v0["datums"]["Q"]["status"] == "pending_p"
    assert v0["datums"]["Q"]["micros"] == ["start"]

    ctx = api.step_session(sid, fill={"Q": {"start": "x"}})
    v1 = _span_vector(api, sid, ctx, ["Q"])

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert v1["current_span"] == "S_Q"
    assert v1["datums"]["Q"]["status"] == "reexploded"
    assert v1["datums"]["Q"]["micros"] == ["confirm"]
    assert v1["datums"]["Q"]["reexplode_count"] == 1

    ctx = api.step_session(sid, fill={"Q": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"] == {"confirm": "yes"}


def test_undo_and_redo_restore_previous_and_next_span_vectors_around_reexplode():
    """
    Public tape law:

        undo(T_reexplode(V)) == V
        redo(undo(T_reexplode(V))) == T_reexplode(V)

    Undo/redo restores the public vector shape and lifecycle shell, not merely
    the cursor.
    """
    step_name = "span.vector.q.undo.redo.step"
    _register_step(step_name, _q_confirm_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {"persistence": "disabled"},
            "redo": {"max_depth": 16},
        },
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert _span_vector(api, sid, ctx, ["Q"])["datums"]["Q"]["micros"] == ["start"]

    ctx = api.step_session(sid, fill={"Q": {"start": "x"}})
    assert _span_vector(api, sid, ctx, ["Q"])["datums"]["Q"]["micros"] == ["confirm"]

    ctx = api.undo_last_step(sid)
    v_undo = _span_vector(api, sid, ctx, ["Q"])

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert v_undo["current_span"] == "S_Q"
    assert v_undo["datums"]["Q"]["micros"] == ["start"]
    assert v_undo["datums"]["Q"]["reexplode_count"] == 0

    ctx = api.redo_last_step(sid)
    v_redo = _span_vector(api, sid, ctx, ["Q"])

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert v_redo["current_span"] == "S_Q"
    assert v_redo["datums"]["Q"]["micros"] == ["confirm"]
    assert v_redo["datums"]["Q"]["reexplode_count"] == 1


def test_blocking_q_keeps_same_span_and_does_not_commit_invalid_fill():
    """
    Blocking law:

        T_submit(V_S, invalid_fill) -> blocked(error), V_S unchanged

    A blocked Q decision reports an error and keeps the span pending without
    committing the invalid candidate fill.
    """
    step_name = "span.vector.blocking.step"
    _register_step(step_name, _blocking_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled"}},
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["current_span"] == "S_AMOUNT"

    ctx = api.step_session(sid, fill={"AMOUNT": {"value": 99}})
    v_block = _span_vector(api, sid, ctx, ["AMOUNT"])

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_AMOUNT"
    assert "AMOUNT" in (ctx.get("last_error") or {})
    assert v_block["datums"]["AMOUNT"]["has_committed_fill"] is False

    ctx = api.step_session(sid, fill={"AMOUNT": {"value": 5}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_NEXT"

    out = api.get_outputs(sid)
    assert out["form_fills"]["AMOUNT"] == {"value": 5}


def test_multi_datum_span_vector_is_atomic_when_q_sibling_reexplodes():
    """
    Atomic product-vector law:

        S_AQ owns (A, Q)

        submit(A.ok, Q.start) -> reexplode(Q), not commit(A)

    A is valid in the candidate evaluation, but the public accepted transition
    is Q reexplode, not span completion. Therefore A is not durably committed.
    The next submit must provide A again with Q.confirm.
    """
    step_name = "span.vector.atomic.step"
    _register_step(step_name, _multi_datum_atomic_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {"persistence": "disabled"},
            "redo": {"max_depth": 16},
        },
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    v0 = _span_vector(api, sid, ctx, ["A", "Q"])

    assert ctx["current_span"] == "S_AQ"
    assert v0["datums"]["A"]["pending"] is True
    assert v0["datums"]["Q"]["pending"] is True

    ctx = api.step_session(sid, fill={"A": {"value": "a1"}, "Q": {"start": "q1"}})
    v1 = _span_vector(api, sid, ctx, ["A", "Q"])

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_AQ"
    assert v1["datums"]["Q"]["status"] == "reexploded"
    assert v1["datums"]["Q"]["micros"] == ["confirm"]

    assert v1["datums"]["A"]["has_committed_fill"] is False
    assert "A" not in api.get_outputs(sid)["form_fills"]

    ctx = api.step_session(sid, fill={"A": {"value": "a2"}, "Q": {"confirm": "yes"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_C"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"] == {"value": "a2"}
    assert out["form_fills"]["Q"] == {"confirm": "yes"}


def test_forced_done_cap_turns_hostile_reexplode_into_satisfied_vector_component():
    """
    Safety cap law:

        hostile_widget_always_reexplode + max_reexplosions=0 -> forced_done

    Engine policy dominates the widget. A hostile widget cannot trap the span in
    infinite public reexplosion.
    """
    step_name = "span.vector.forced.step"
    _register_step(step_name, _forced_done_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled"}},
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["current_span"] == "S_LOOP"

    ctx = api.step_session(sid, fill={"LOOP": {"start": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    row = _lifecycle_row(api, sid, "span.vector.forced", "LOOP")
    assert row["status"] == "forced_done"
    assert row["forced_done"] is True


def test_respanned_q_datum_reuses_lifecycle_state_and_later_span_skips_when_satisfied():
    """
    Respanning law:

        Q appears in S_Q_FIRST and S_Q_AGAIN.

    Once Q's lifecycle row is satisfied, a later span that owns the same datum
    observes the satisfied datum machine and is skipped.
    """
    step_name = "span.vector.respanned.step"
    _register_step(step_name, _respanned_q_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled"}},
    )
    sid = str(st["session_id"])

    ctx = api.step_session(sid)
    assert ctx["current_span"] == "S_Q_FIRST"

    ctx = api.step_session(sid, fill={"Q": {"start": "x"}})
    assert ctx["current_span"] == "S_Q_FIRST"

    ctx = api.step_session(sid, fill={"Q": {"confirm": "yes"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_END"

    row = _lifecycle_row(api, sid, "span.vector.respanned", "Q")
    assert row["status"] == "done"


def test_redo_branch_clears_after_new_vector_transition():
    """
    Branching tape law:

        undo(old_transition)
        new_transition
        redo(old_transition) is unavailable

    Redo is a branch, not a second future. Once a new public vector transition
    happens after undo, the old redo branch is cleared.
    """
    step_name = "span.vector.branch.step"
    _register_step(step_name, _q_confirm_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {"persistence": "disabled"},
            "redo": {"max_depth": 16},
        },
    )
    sid = str(st["session_id"])

    api.step_session(sid)
    api.step_session(sid, fill={"Q": {"start": "old"}})

    ctx = api.undo_last_step(sid)
    assert _span_vector(api, sid, ctx, ["Q"])["datums"]["Q"]["micros"] == ["start"]

    ctx = api.step_session(sid, fill={"Q": {"start": "new"}})
    assert _span_vector(api, sid, ctx, ["Q"])["datums"]["Q"]["micros"] == ["confirm"]

    with pytest.raises(Exception):
        api.redo_last_step(sid)


def test_script_history_stays_slim_even_when_q_proc_notes_is_giant():
    """
    Surface slimness law:

    Large lifecycle proc_notes may live in engine lifecycle state, but must not
    leak into slim runner history or compact runtime-write query surfaces.
    """
    fs = {
        "app_form_id": "span.vector.giant",
        "datums": [
            {
                "id": "G",
                "title": "G",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_giant_reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": "S_G", "owns": ["G"]}],
            }
        ],
    }

    step_name = "span.vector.giant.step"
    _register_step(step_name, fs)

    api = _api()
    result = run_session_against_script_headless(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled"}},
        api=api,
        keep_full_history=False,
        script=[
            {"action": "STEP", "until_stop": True},
            {"action": "STEP", "fill": {"G.start": "x"}},
            {
                "action": "STEP",
                "fill": {"G.confirm": "yes"},
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    assert result.ctx["kind"] == "ATCOMPLETION"
    assert not _contains_run(result.history, "Z", 1000)

    state = api._get(result.session_id).state
    assert _contains_run(state[KEY_DATUM_LIFECYCLE], "Z", 1000)
    assert not _contains_run(state[KEY_RUNTIME_WRITE_INDEX], "Z", 1000)

    q = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 10,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert not _contains_run(q, "Z", 1000)


def test_many_q_span_vector_transitions_scale_with_public_actions_not_snapshot_history():
    """
    Scaling law:

        public ticks ~= 2 * number_of_Q_datums

    This verifies the engine is doing public vector transitions, not building a
    quadratic public history/snapshot artifact as Q lifecycle rows accumulate.
    """

    def q_reexplode_once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "span.vector.q_scale_reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"tiny": True},
        }

    register_datum_widget_v1(
        "span.vector.q_scale_reexplode_once",
        q_reexplode_once,
        overwrite=True,
    )

    n = 80
    fs = {
        "app_form_id": "span.vector.scale",
        "datums": [
            {
                "id": f"D{i}",
                "title": f"D{i}",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "span.vector.q_scale_reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            }
            for i in range(n)
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
            }
        ],
    }

    step_name = "span.vector.scale.step"
    _register_step(step_name, fs)

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "profile": True,
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    t0 = time.perf_counter()

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    for i in range(n):
        ctx = runner.step(fill={f"D{i}.start": f"x{i}"})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert ctx["current_span"] == f"S{i}"

        ctx = runner.step(fill={f"D{i}.confirm": "yes"})

    elapsed = time.perf_counter() - t0
    assert ctx["kind"] == "ATCOMPLETION"

    print(
        "[span-vector-summary] many_q_vector_transitions "
        f"n={n} public_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f}"
    )

    assert elapsed < 20.0
    assert len(runner.history) == 2 * n + 1
    assert not _contains_run(runner.history, "multiframespec", 1)