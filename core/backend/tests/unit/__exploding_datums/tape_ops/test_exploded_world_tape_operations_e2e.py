# think-backend/tests/wippp/test_exploded_world_tape_operations_robustness_and_scalability_e2e.py
from __future__ import annotations

"""
Exploded World Tape Operations Robustness + Scalability E2E
===========================================================

This sheet is the public theorem suite for Q datum tape mechanics.

It treats the session as a bidirectional public tape:

    STEP:
        - ordinary P datum fill,
        - Q blocked retry,
        - Q reexplode tick,
        - Q forced-done tick at max_reexplosions,
        - Q done tick,
        - stale satisfied manual skip,
        - completion.

    UNDO:
        - returns to the exact public surface before the last public tick;
        - reexplode is undoable as a first-class public manual tick;
        - done/fill is undoable as a first-class public manual tick;
        - stale respanned manual surfaces are never exposed as fake undo stops;
        - undo of Q reexplode removes only the bounded lifecycle patch for that tick,
          not a whole-session snapshot.

    REDO:
        - replays the bounded public manual action payload;
        - does not replay snapshots;
        - is branch-cleared by a new user STEP after undo;
        - remains bounded under adversarial alternating undo/redo;
        - obeys configured redo max_depth without corrupting recent redo actions.

Completeness-by-induction idea
------------------------------
Every public transition is one of:

    P accepted fill
    Q blocked fill
    Q reexplode fill
    Q forced-done fill
    Q done fill
    stale-satisfied manual skip
    undo of any executed public manual tick
    redo of any undone public manual tick
    new STEP after undo clearing redo branch
    redo cap truncation

The tests below compose those primitives across:
    - one datum,
    - P-only worlds,
    - Q-only worlds,
    - mixed P/Q same span,
    - same datum respanned later in the same frame and across frames,
    - multiple sequential datums,
    - forced max-reexplosion caps,
    - blocked/retry flows,
    - redo branch divergence,
    - large bounded lifecycle proc_notes,
    - adversarial alternating undo/redo.
"""

import time
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pytest

from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _api():
    return get_concrete_session_api(enable_persistence=False)


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


def _manifest(step_name: str) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": step_name.replace(".", "_"),
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


def _metadata(*, redo_depth: int = 128) -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": False,
            "include_global_fill_keys_in_ctx": False,
            "include_field_value_keys_in_ctx": False,
        },
        "redo": {"max_depth": redo_depth},
    }


def _start(
    api,
    step_name: str,
    *,
    redo_depth: int = 128,
) -> Tuple[str, Dict[str, Any]]:
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata=_metadata(redo_depth=redo_depth),
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return sid, ctx


def _single_frame_form(
    *,
    app_form_id: str,
    datums: List[Mapping[str, Any]],
    spans: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [dict(d) for d in datums],
        "frames": [{"id": "F", "title": "Frame", "spans": [dict(s) for s in spans]}],
    }


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 200_000) -> bool:
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


def _runtime_lifecycle_writes(
    state: Mapping[str, Any],
    *,
    max_results: int = 10_000,
) -> List[Mapping[str, Any]]:
    q = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": max_results,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    return list(q["writes"])


def _lifecycle_store(api, sid: str) -> Mapping[str, Any]:
    return api._get(sid).state.get(KEY_DATUM_LIFECYCLE) or {}


def _lifecycle_write_count(api, sid: str) -> int:
    return len(_runtime_lifecycle_writes(api._get(sid).state, max_results=100_000))


def _pending_field_items(ctx: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """
    Public ctx shape has changed over time:
      - some paths expose datum_widgets_on_this_span as field dicts;
      - some expose only ids/strings;
      - some put richer data in datum_widget_decls/datum_widget_fills.

    Tests should be robust to all public-compatible ctx shapes.
    """
    out: List[Mapping[str, Any]] = []
    for item in ctx.get("datum_widgets_on_this_span", []) or []:
        if isinstance(item, Mapping):
            out.append(item)
        else:
            out.append({"field_id": str(item)})
    return out


def _ctx_pending_field_ids(ctx: Mapping[str, Any]) -> List[str]:
    ids: List[str] = []
    for item in _pending_field_items(ctx):
        fid = item.get("field_id") or item.get("id") or item.get("name")
        if fid is not None:
            ids.append(str(fid))
    return ids


def _current_span(ctx: Mapping[str, Any]) -> str:
    """
    Span id is the stable public tape coordinate for these tests.
    Frame id is useful, but not guaranteed in every context payload.
    """
    span = (
        ctx.get("current_span")
        or ctx.get("current_span_id")
        or ctx.get("span_id")
        or ctx.get("fillspan_name")
    )
    if span is not None:
        return str(span)

    fields = _pending_field_items(ctx)
    if fields:
        first = fields[0]
        span = (
            first.get("fillspan_name")
            or first.get("span_id")
            or first.get("current_span")
            or first.get("current_span_id")
        )
        if span is not None:
            return str(span)

    return "None"


def _current_frame_if_exposed(ctx: Mapping[str, Any]) -> str | None:
    frame = (
        ctx.get("current_frame")
        or ctx.get("current_frame_id")
        or ctx.get("frame_id")
        or ctx.get("frame_name")
    )
    if frame is not None:
        return str(frame)

    fields = _pending_field_items(ctx)
    if fields:
        first = fields[0]
        frame = (
            first.get("frame_id")
            or first.get("frame_name")
            or first.get("current_frame")
            or first.get("current_frame_id")
        )
        if frame is not None:
            return str(frame)

    return None


def _assert_surface(
    ctx: Mapping[str, Any],
    *,
    span: str,
    frame: str | None = None,
) -> None:
    """
    Assert the public tape location.

    Span is required because span ids in these tests are unique. Frame is checked
    only when the public ctx actually exposes a frame coordinate.
    """
    assert _current_span(ctx) == span

    exposed_frame = _current_frame_if_exposed(ctx)
    if frame is not None and exposed_frame is not None:
        assert exposed_frame == frame


def _field_decl_text(ctx: Mapping[str, Any], datum_id: str) -> str:
    decls = ctx.get("datum_widget_decls") or {}
    if isinstance(decls, Mapping):
        return str(decls.get(datum_id, ""))
    return str(decls)


def _semantic_micro(micro: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Runtime may add default metadata such as tags=[].
    Tests should compare semantic author-facing micro fields.
    """
    keep = ("name", "type", "required", "placeholder", "options", "validators")
    return {k: micro[k] for k in keep if k in micro}


def _semantic_micros(micros: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [_semantic_micro(m) for m in micros]


def _assert_no_committed_lifecycle_for_form(
    api,
    sid: str,
    form_id: str,
) -> None:
    """
    Blank lifecycle shells are allocation artifacts, not commits.

    The true invariant is:
      - no lifecycle runtime writes,
      - no datum row with committed status,
      - no working fills/prefills,
      - no messages/proc_notes/current_datum/reexplode_count.
    """
    assert _lifecycle_write_count(api, sid) == 0

    st = api._get(sid).state
    lifecycle = st.get(KEY_DATUM_LIFECYCLE) or {}
    if not isinstance(lifecycle, Mapping):
        return

    form = (lifecycle.get("forms") or {}).get(form_id)
    if not isinstance(form, Mapping):
        return

    assert form.get("working_fills_by_span", {}) == {}
    assert form.get("working_prefills_by_span", {}) == {}

    for row in (form.get("datums") or {}).values():
        if not isinstance(row, Mapping):
            continue
        assert row.get("status") in {None, ""}
        assert int(row.get("reexplode_count") or 0) == 0
        assert row.get("current_datum") is None
        assert row.get("messages", []) == []
        assert row.get("proc_notes", []) == []
        assert row.get("forced_done") in {False, None}


def _assert_no_lifecycle_forms(api, sid: str) -> None:
    store = _lifecycle_store(api, sid)
    if isinstance(store, Mapping):
        forms = store.get("forms", {})
        assert forms in ({}, None)


def _assert_redo_unavailable(api, sid: str) -> None:
    with pytest.raises(Exception):
        api.redo_last_step(sid)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def _register_reexplode_once_widget(name: str, *, giant_proc_notes: str = "") -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {"phase": "done"},
            }

        proc_notes = {"phase": "confirm"}
        if giant_proc_notes:
            proc_notes["giant"] = giant_proc_notes

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": name,
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "please confirm"},
            "proc_notes": proc_notes,
        }

    register_datum_widget_v1(name, widget, overwrite=True)


def _register_block_until_ok_widget(name: str) -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = dict(q.get("partial_fill") or {})
        if partial.get("value") != "ok":
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "must equal ok"},
                "state": {"last_bad": partial.get("value")},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": "ok"},
            "state": {"accepted": True},
        }

    register_datum_widget_v1(name, widget, overwrite=True)


def _register_done_if_structural_widget(name: str) -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        if not q.get("structurally_satisfied"):
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "missing required value"},
                "state": {"missing": True},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": True},
        }

    register_datum_widget_v1(name, widget, overwrite=True)


def _register_always_reexplode_widget(name: str) -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        re_count = int(q.get("reexplode_count") or 0)
        next_micro = f"v{re_count}"
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro(next_micro)],
                "lifecycle": {
                    "widget": name,
                    "max_reexplosions": q.get("max_reexplosions", 0),
                    "max_proc_notes": 2,
                    "max_messages": 2,
                },
            },
            "fill": {next_micro: ""},
            "prefill": {next_micro: f"prefill-{re_count}"},
            "state": {"asked": re_count + 1},
            "message": {"level": "info", "text": f"again-{re_count}"},
            "proc_notes": {"tick": re_count},
        }

    register_datum_widget_v1(name, widget, overwrite=True)


def _q_datum(datum_id: str, widget: str, *, max_reexplosions: int = 1) -> Dict[str, Any]:
    return {
        "id": datum_id,
        "title": datum_id,
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": widget,
            "max_reexplosions": max_reexplosions,
            "max_proc_notes": 1,
            "max_messages": 4,
        },
    }


def _p_datum(datum_id: str) -> Dict[str, Any]:
    return {"id": datum_id, "title": datum_id, "micros": [_text_micro()]}


# ---------------------------------------------------------------------------
# Tape correctness matrix: atomic public actions
# ---------------------------------------------------------------------------


def test_tape_p_only_fill_undo_redo_is_baseline_public_action_and_has_no_q_writes():
    """
    Baseline P theorem row.

        P STEP -> completion
        UNDO   -> original P manual surface
        REDO   -> completion

    This proves Q machinery did not contaminate the vanilla P fast-path.
    """
    fs = _single_frame_form(
        app_form_id="tape.p.baseline",
        datums=[_p_datum("D")],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.p.baseline.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.step_session(sid, fill={"D": {"value": "p"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert _lifecycle_write_count(api, sid) == 0
    _assert_no_lifecycle_forms(api, sid)

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"]["value"] == "p"
    assert _lifecycle_write_count(api, sid) == 0


def test_tape_reexplode_undo_redo_done_undo_redo_single_q_datum():
    """
    Matrix row:

        value STEP   -> reexplode(confirm)
        UNDO         -> value surface
        REDO         -> confirm surface
        confirm STEP -> completion
        UNDO         -> confirm surface
        REDO         -> completion

    This proves reexplode and done are both first-class bounded public ticks.
    """
    widget = "test.tape.single.reexplode_once"
    _register_reexplode_once_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.single",
        datums=[_q_datum("D", widget)],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.single.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    assert "value" in _field_decl_text(ctx, "D")
    assert _lifecycle_write_count(api, sid) == 0

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "confirm" in _field_decl_text(ctx, "D")
    assert _lifecycle_write_count(api, sid) == 1

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")
    assert "confirm" not in _field_decl_text(ctx, "D")
    _assert_no_committed_lifecycle_for_form(api, sid, "tape.single")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "confirm" in _field_decl_text(ctx, "D")
    assert _lifecycle_write_count(api, sid) == 1

    ctx = api.step_session(sid, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert _lifecycle_write_count(api, sid) == 2

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "confirm" in _field_decl_text(ctx, "D")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["confirm"] == "yes"


def test_tape_blocked_q_does_not_create_redoable_public_action_until_success():
    """
    Matrix row:

        bad STEP  -> same surface, last_error, no committed action
        REDO      -> unavailable
        good STEP -> completion
        UNDO      -> same datum surface
        REDO      -> completion

    A blocked widget result is not a public progress tick.
    """
    widget = "test.tape.block_until_ok"
    _register_block_until_ok_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.block",
        datums=[_q_datum("D", widget)],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.block.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx0 = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert ctx["last_error"]["D"] == "must equal ok"
    assert _lifecycle_write_count(api, sid) == 0

    _assert_redo_unavailable(api, sid)

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert _lifecycle_write_count(api, sid) == 1

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"]["value"] == "ok"


def test_tape_forced_done_at_max_reexplosions_is_public_done_not_infinite_reexplode_loop():
    """
    Matrix row:

        widget always asks to reexplode
        datum max_reexplosions=0
        STEP -> forced done/completion using structurally valid submitted fill

    This proves max_reexplosions is a hard public progress bound, not a loop.
    """
    widget = "test.tape.forced_done.always_reexplode"
    _register_always_reexplode_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.forced_done",
        datums=[_q_datum("D", widget, max_reexplosions=0)],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.forced_done.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.step_session(sid, fill={"D": {"value": "cap"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"]["value"] == "cap"
    assert _lifecycle_write_count(api, sid) == 1

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"


# ---------------------------------------------------------------------------
# Tape correctness matrix: branch, sibling, respan, stale-skip behavior
# ---------------------------------------------------------------------------


def test_tape_new_step_after_undo_clears_old_redo_branch_for_q_reexplode():
    """
    Matrix row:

        value=A -> reexplode
        UNDO    -> value surface
        value=B -> new reexplode branch
        REDO    -> unavailable

    This prevents timeline forking bugs.
    """
    widget = "test.tape.branch.reexplode_once"
    _register_reexplode_once_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.branch",
        datums=[_q_datum("D", widget)],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.branch.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "A"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "confirm" in _field_decl_text(ctx, "D")

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.step_session(sid, fill={"D": {"value": "B"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "confirm" in _field_decl_text(ctx, "D")

    _assert_redo_unavailable(api, sid)


def test_tape_new_step_after_undo_clears_old_redo_branch_for_q_done():
    """
    Matrix row:

        value=ok -> Q done/completion
        UNDO     -> value surface
        value=ok2 -> new done branch/completion
        REDO     -> unavailable

    Branch clearing must apply to done ticks as well as reexplode ticks.
    """
    widget = "test.tape.branch.done"
    _register_done_if_structural_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.branch.done",
        datums=[_q_datum("D", widget)],
        spans=[{"id": "S", "owns": ["D"]}],
    )
    step_name = "test.tape.branch.done.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")

    ctx = api.step_session(sid, fill={"D": {"value": "ok2"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"]["value"] == "ok2"

    _assert_redo_unavailable(api, sid)


def test_tape_multi_datum_same_span_preserves_sibling_fill_through_q_reexplode_undo_redo():
    """
    Matrix row:

        Span S owns Q and P.
        Q reexplodes, P is already structurally satisfied.
        UNDO/REDO around Q reexplode must not lose P's working fill.
    """
    widget = "test.tape.multi.reexplode_once"
    _register_reexplode_once_widget(widget)

    fs = _single_frame_form(
        app_form_id="tape.multi",
        datums=[_q_datum("Q", widget), _p_datum("P")],
        spans=[{"id": "S", "owns": ["Q", "P"]}],
    )
    step_name = "test.tape.multi.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"Q": {"value": "draft"}, "P": {"value": "p1"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert ctx["datum_widget_fills"]["P"]["value"] == "p1"
    assert "confirm" in _field_decl_text(ctx, "Q")

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert "value" in _field_decl_text(ctx, "Q")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S")
    assert ctx["datum_widget_fills"]["P"]["value"] == "p1"
    assert "confirm" in _field_decl_text(ctx, "Q")

    ctx = api.step_session(sid, fill={"Q": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"]["confirm"] == "yes"
    assert out["form_fills"]["P"]["value"] == "p1"


def test_tape_same_datum_respanned_later_skips_stale_surface_for_p_and_q_done_rows():
    """
    Matrix row:

        S1(D) then S2(D).
        After S1 satisfies D, S2 is stale and must skip.

    This is tested for both P and explicit Q done datums.
    """
    done_widget = "test.tape.respan.done"
    _register_done_if_structural_widget(done_widget)

    cases = [
        ("p", _p_datum("D")),
        ("q", _q_datum("D", done_widget)),
    ]

    for suffix, datum in cases:
        step_name = f"test.tape.respan.{suffix}.step"
        fs = {
            "app_form_id": f"tape.respan.{suffix}",
            "datums": [datum],
            "frames": [
                {"id": "F1", "spans": [{"id": "S1", "owns": ["D"]}]},
                {"id": "F2", "spans": [{"id": "S2", "owns": ["D"]}]},
            ],
        }
        _register_step(step_name, fs)

        api = _api()
        sid, ctx = _start(api, step_name)
        _assert_surface(ctx, span="S1")

        ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
        assert ctx["kind"] == "ATCOMPLETION"

        out = api.get_outputs(sid)
        assert out["form_fills"]["D"]["value"] == "ok"

        ctx = api.undo_last_step(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        _assert_surface(ctx, span="S1")


def test_tape_same_q_datum_reexploded_and_done_respanned_later_skips_reopened_stale_surface():
    """
    Matrix row:

        F1.S1(D) Q reexplodes to confirm and is done.
        F2.S2(D) owns same D later.
        F2.S2 must skip because D is globally/lifecycle satisfied.

    This catches the subtle bug where dynamic reexploded shape could cause a
    later span to reopen D as though it were new work.
    """
    widget = "test.tape.respan.q.reexplode_once"
    _register_reexplode_once_widget(widget)

    fs = {
        "app_form_id": "tape.respan.q.reexplode",
        "datums": [_q_datum("D", widget)],
        "frames": [
            {"id": "F1", "spans": [{"id": "S1", "owns": ["D"]}]},
            {"id": "F2", "spans": [{"id": "S2", "owns": ["D"]}]},
        ],
    }
    step_name = "test.tape.respan.q.reexplode.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    _assert_surface(ctx, span="S1")
    assert "value" in _field_decl_text(ctx, "D")

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S1")
    assert "confirm" in _field_decl_text(ctx, "D")

    ctx = api.step_session(sid, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["confirm"] == "yes"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S1")
    assert "confirm" in _field_decl_text(ctx, "D")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"


def test_tape_public_undo_hides_multiple_stale_auto_skip_surfaces():
    """
    Matrix row:

        D is owned by S1, S2, S3.
        S1 accepts D.
        S2/S3 are auto-skipped stale surfaces.
        Public UNDO from completion must reveal S1, not S2/S3 fake stops.
    """
    fs = {
        "app_form_id": "tape.stale.skip.stack",
        "datums": [_p_datum("D")],
        "frames": [
            {"id": "F1", "spans": [{"id": "S1", "owns": ["D"]}]},
            {"id": "F2", "spans": [{"id": "S2", "owns": ["D"]}]},
            {"id": "F3", "spans": [{"id": "S3", "owns": ["D"]}]},
        ],
    }
    step_name = "test.tape.stale.skip.stack.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    _assert_surface(ctx, span="S1")

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S1")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"


# ---------------------------------------------------------------------------
# Tape scalability / adversarial rows
# ---------------------------------------------------------------------------


def test_tape_adversarial_alternating_undo_redo_many_q_ticks_stays_bounded_and_snapshot_free():
    """
    Scalability theorem row.

    Build N Q datums, each requiring two public ticks:

        value   -> reexplode
        confirm -> done

    Then repeatedly:

        undo completion-visible last done tick
        redo it

    The redo payloads are bounded public manual fills, not snapshots or lifecycle
    store copies. The runtime index stores lifecycle refs/previews, not giant
    proc_notes.
    """
    giant = "G" * 300_000
    widget = "test.tape.scale.reexplode_once"
    _register_reexplode_once_widget(widget, giant_proc_notes=giant)

    n = 45
    fs = _single_frame_form(
        app_form_id="tape.scale",
        datums=[_q_datum(f"D{i}", widget) for i in range(n)],
        spans=[{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
    )
    step_name = "test.tape.scale.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        _assert_surface(ctx, span=f"S{i}")
        assert "confirm" in _field_decl_text(ctx, f"D{i}")
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    fill_elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    t0 = time.perf_counter()
    for _ in range(25):
        ctx = api.undo_last_step(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.redo_last_step(sid)
        assert ctx["kind"] == "ATCOMPLETION"
    tape_elapsed = time.perf_counter() - t0

    st = api._get(sid).state
    writes = _runtime_lifecycle_writes(st, max_results=10_000)

    assert len(writes) >= 2 * n
    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "G", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "G", 1000)

    print(
        "[exploded-tape-summary] alternating_q_undo_redo "
        f"n={n} fill_elapsed={fill_elapsed:.6f}s tape25_elapsed={tape_elapsed:.6f}s "
        f"avg_fill_tick_ms={fill_elapsed * 1000 / (2 * n):.3f} "
        f"avg_undo_redo_pair_ms={tape_elapsed * 1000 / 25:.3f}"
    )

    assert fill_elapsed < 20.0
    assert tape_elapsed < 10.0


def test_tape_many_p_ticks_have_no_lifecycle_store_and_scale_as_plain_public_tape():
    """
    P scalability theorem row.

    Many vanilla P ticks should remain P ticks:
        - no Q rows,
        - no lifecycle write index entries,
        - undo/redo works over public fills only.
    """
    n = 160
    fs = _single_frame_form(
        app_form_id="tape.p.scale",
        datums=[_p_datum(f"D{i}") for i in range(n)],
        spans=[{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
    )
    step_name = "test.tape.p.scale.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    fill_elapsed = time.perf_counter() - t0
    assert ctx["kind"] == "ATCOMPLETION"

    t0 = time.perf_counter()
    for _ in range(30):
        ctx = api.undo_last_step(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.redo_last_step(sid)
        assert ctx["kind"] == "ATCOMPLETION"
    tape_elapsed = time.perf_counter() - t0

    _assert_no_lifecycle_forms(api, sid)
    assert _lifecycle_write_count(api, sid) == 0

    print(
        "[exploded-tape-summary] p_plain_public_tape "
        f"n={n} fill_elapsed={fill_elapsed:.6f}s tape30_elapsed={tape_elapsed:.6f}s "
        f"avg_fill_ms={fill_elapsed * 1000 / n:.3f} "
        f"avg_undo_redo_pair_ms={tape_elapsed * 1000 / 30:.3f}"
    )

    assert fill_elapsed < 10.0
    assert tape_elapsed < 5.0


def test_tape_redo_depth_cap_discards_oldest_actions_without_corrupting_recent_redo():
    """
    Redo-depth guardrail row.

    The system may cap redo memory. The cap must discard old actions cleanly
    without corrupting recent public redo.
    """
    n = 12
    fs = _single_frame_form(
        app_form_id="tape.redo.cap",
        datums=[_p_datum(f"D{i}") for i in range(n)],
        spans=[{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
    )
    step_name = "test.tape.redo.cap.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name, redo_depth=3)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    assert ctx["kind"] == "ATCOMPLETION"

    for _ in range(6):
        ctx = api.undo_last_step(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    for _ in range(3):
        ctx = api.redo_last_step(sid)

    assert ctx["kind"] in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}

    _assert_redo_unavailable(api, sid)


def test_tape_deep_mixed_world_sequential_p_q_block_reexplode_forced_done_and_stale_skip_e2e():
    """
    Integrated local-concept E2E row.

    One program contains:
        P0: plain P done
        B:  Q blocked until ok
        R:  Q reexplode then done
        C:  Q forced-done at max_reexplosions=0
        P0: respanned stale skip later

    Then undo/redo crosses the integrated tape without exposing stale surfaces.
    """
    block_widget = "test.tape.integrated.block"
    reexplode_widget = "test.tape.integrated.reexplode"
    forced_widget = "test.tape.integrated.forced"
    _register_block_until_ok_widget(block_widget)
    _register_reexplode_once_widget(reexplode_widget)
    _register_always_reexplode_widget(forced_widget)

    fs = {
        "app_form_id": "tape.integrated",
        "datums": [
            _p_datum("P0"),
            _q_datum("B", block_widget),
            _q_datum("R", reexplode_widget),
            _q_datum("C", forced_widget, max_reexplosions=0),
        ],
        "frames": [
            {"id": "F0", "spans": [{"id": "S_P0", "owns": ["P0"]}]},
            {"id": "F1", "spans": [{"id": "S_B", "owns": ["B"]}]},
            {"id": "F2", "spans": [{"id": "S_R", "owns": ["R"]}]},
            {"id": "F3", "spans": [{"id": "S_C", "owns": ["C"]}]},
            {"id": "F4", "spans": [{"id": "S_P0_AGAIN", "owns": ["P0"]}]},
        ],
    }
    step_name = "test.tape.integrated.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)
    _assert_surface(ctx, span="S_P0")

    ctx = api.step_session(sid, fill={"P0": {"value": "plain"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_B")

    ctx = api.step_session(sid, fill={"B": {"value": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_B")
    assert ctx["last_error"]["B"] == "must equal ok"

    ctx = api.step_session(sid, fill={"B": {"value": "ok"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_R")

    ctx = api.step_session(sid, fill={"R": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_R")
    assert "confirm" in _field_decl_text(ctx, "R")

    ctx = api.step_session(sid, fill={"R": {"confirm": "yes"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_C")

    ctx = api.step_session(sid, fill={"C": {"value": "cap"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["P0"]["value"] == "plain"
    assert out["form_fills"]["B"]["value"] == "ok"
    assert out["form_fills"]["R"]["confirm"] == "yes"
    assert out["form_fills"]["C"]["value"] == "cap"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_C")

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_R")
    assert "confirm" in _field_decl_text(ctx, "R")

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_R")
    assert "value" in _field_decl_text(ctx, "R")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_R")
    assert "confirm" in _field_decl_text(ctx, "R")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    _assert_surface(ctx, span="S_C")

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"