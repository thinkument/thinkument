# think-backend/tests/wipppp/test_selective_reexplosion_public_tape_e2e.py
from __future__ import annotations

"""
Selective Reexplosion Public Tape E2E
====================================

This sheet locks Task E end-to-end:

    In a multi-datum span, a manual submit evaluates lifecycle only for datums
    touched by that submit.

The feature must integrate with public tape semantics:

    - partial accepted same-span submits are public undo/redo ticks;
    - Q reexplode ticks are public undo/redo ticks;
    - untouched Q siblings are not evaluated by collateral span progress checks;
    - plain P sibling working fills survive reexplode and commit later;
    - undo/redo restores the exact same logical same-span state;
    - taking a new step after undo clears the old redo branch;
    - blocked Q siblings remain untouched until explicitly submitted.

This is intentionally separate from the plain public tape diagnostics. The plain
file should stay P-only. This file is the Q/selective-reexplosion tape contract.
"""

from typing import Any, Dict, List, Mapping, Sequence

import pytest


from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    get_latest_engine_form_page_data_read
)

from __datomatonTM import (
    register_datum_widget_v1
)
from __datomatonTM import (
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_BLOCKED,
    DATUM_LIFECYCLE_STATUS_REEXPLODED,
    KEY_DATUM_LIFECYCLE,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.__persistence.config import set_session_repo
from _thinkengine.__persistence.repo import SessionRepo
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _api():
    set_session_repo(SessionRepo)
    return get_concrete_session_api()


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


def _start(
    api,
    step_name: str,
    *,
    include_full_multiframespec_in_ctx: bool = False,
) -> tuple[str, Dict[str, Any]]:
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": step_name.replace(".", "_"),
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_full_multiframespec_in_ctx": include_full_multiframespec_in_ctx,
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            },
            "redo": {"max_depth": 128},
        },
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return sid, ctx


def _state(api, sid: str) -> Dict[str, Any]:
    return api._get(sid).state


def _rows(api, sid: str, form_id: str) -> Dict[str, Any]:
    state = _state(api, sid)
    lifecycle = state.get(KEY_DATUM_LIFECYCLE) or {}
    forms = lifecycle.get("forms") or {}
    form = forms.get(form_id) or {}
    return dict(form.get("datums") or {})


def _is_active_lifecycle_row(row: Mapping[str, Any]) -> bool:
    """
    Undo may restore a neutral/default row:

        {
            "status": None,
            "current_datum": None,
            "messages": [],
            "proc_notes": [],
            ...
        }

    That row is not semantically active. Treat it as no live lifecycle state.
    """
    if row.get("status") is not None:
        return True
    if row.get("current_datum") is not None:
        return True
    if row.get("messages"):
        return True
    if row.get("proc_notes"):
        return True
    if row.get("state"):
        return True
    if int(row.get("reexplode_count", 0) or 0) != 0:
        return True
    if bool(row.get("forced_done", False)):
        return True
    return False


def _active_rows(api, sid: str, form_id: str) -> Dict[str, Any]:
    return {
        fid: row
        for fid, row in _rows(api, sid, form_id).items()
        if isinstance(row, Mapping) and _is_active_lifecycle_row(row)
    }


def _runtime_lifecycle_writes(api, sid: str) -> List[Mapping[str, Any]]:
    q = query_runtime_writes_v1(
        _state(api, sid),
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 10_000,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    return list(q["writes"])


def _write_mentions(obj: Any, needle: str) -> bool:
    """
    Runtime write previews are intentionally compact and may not expose stable
    top-level form_id/field_id keys. This helper lets tests assert absence or
    presence without coupling to preview shape.
    """
    seen: set[int] = set()
    stack = [obj]

    while stack:
        cur = stack.pop()
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if cur == needle:
                return True
        elif isinstance(cur, Mapping):
            stack.extend(cur.keys())
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _field_decl_text(ctx: Mapping[str, Any], fid: str) -> str:
    return str((ctx.get("datum_widget_decls") or {}).get(fid) or "")


def _field_value(ctx: Mapping[str, Any], fid: str) -> Mapping[str, Any]:
    values = ctx.get("datum_widget_fills") or {}
    val = values.get(fid) or {}
    assert isinstance(val, Mapping)
    return val


def _pending_ids(ctx: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for item in list(ctx.get("datum_widgets_on_this_span") or []):
        if isinstance(item, Mapping):
            fid = (
                item.get("field_id")
                or item.get("id")
                or item.get("name")
                or item.get("datum_id")
            )
            if fid is not None:
                out.append(str(fid))
        else:
            out.append(str(item))
    return out


def _single_span_multiframespec(
    *,
    app_form_id: str,
    datums: Sequence[Mapping[str, Any]],
    span_id: str = "S",
    frame_id: str = "F",
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [dict(d) for d in datums],
        "frames": [
            {
                "id": frame_id,
                "spans": [
                    {
                        "id": span_id,
                        "owns": [str(d["id"]) for d in datums],
                    }
                ],
            }
        ],
    }


def _q_datum(
    datum_id: str,
    *,
    widget: str,
    max_reexplosions: int = 1,
    title: str | None = None,
) -> Dict[str, Any]:
    return {
        "id": datum_id,
        "title": title or datum_id,
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": widget,
            "max_reexplosions": max_reexplosions,
            "max_proc_notes": 2,
            "max_messages": 8,
        },
    }


def _p_datum(datum_id: str, *, title: str | None = None) -> Dict[str, Any]:
    return {
        "id": datum_id,
        "title": title or datum_id,
        "micros": [_text_micro()],
    }


# ---------------------------------------------------------------------------
# Selective Q causality
# ---------------------------------------------------------------------------


def test_selective_q_submit_evaluates_only_touched_q_in_same_span():
    """
    Core Task E law.

    A, B, and C are all Q datums in one span. Submitting A must evaluate only A.
    B and C must not get active lifecycle rows, writes, messages, or widget calls.
    """

    form_id = "selective.q.only_touched"
    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        fid = str(q.get("datum_id") or q.get("field_id") or q["datum"]["id"])
        calls.append(fid)

        if not bool(q.get("structurally_satisfied")):
            return {
                "status": "blocked",
                "message": {"level": "error", "text": f"{fid} missing"},
                "state": {"called": fid},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": f"{fid} done"},
            "state": {"called": fid},
        }

    register_datum_widget_v1("test.selective.q.only_touched", widget, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum("A", widget="test.selective.q.only_touched"),
            _q_datum("B", widget="test.selective.q.only_touched"),
            _q_datum("C", widget="test.selective.q.only_touched"),
        ],
    )
    step_name = "test.selective.q.only_touched.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)

    assert ctx["current_span"] == "S"
    assert set(_pending_ids(ctx)) == {"A", "B", "C"}

    ctx = api.step_session(sid, fill={"A": {"value": "a"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == ["A"]

    rows = _active_rows(api, sid, form_id)
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    writes = _runtime_lifecycle_writes(api, sid)
    assert len(writes) == 1
    assert _write_mentions(writes[0], "A")
    assert not _write_mentions(writes[0], "B")
    assert not _write_mentions(writes[0], "C")

    ctx = api.step_session(sid, fill={"B": {"value": "b"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == ["A", "B"]

    ctx = api.step_session(sid, fill={"C": {"value": "c"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == ["A", "B", "C"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "a"
    assert out["form_fills"]["B"]["value"] == "b"
    assert out["form_fills"]["C"]["value"] == "c"


def test_selective_q_reexplode_confirm_does_not_evaluate_untouched_q_sibling():
    """
    Reexplode causality law.

    A reexplodes and later confirms. B is a sibling Q in the same span.
    Neither A's reexplode nor A's confirm may invoke B.
    """

    form_id = "selective.q.reexplode.no_sibling"
    calls: Dict[str, int] = {"A": 0, "B": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "A done"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.selective.q.reexplode.A",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 8,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm A"},
            "proc_notes": {"small": True},
        }

    def widget_b(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["B"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "B done"},
            "state": {"phase": "done"},
        }

    register_datum_widget_v1("test.selective.q.reexplode.A", widget_a, overwrite=True)
    register_datum_widget_v1("test.selective.q.reexplode.B", widget_b, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum("A", widget="test.selective.q.reexplode.A"),
            _q_datum("B", widget="test.selective.q.reexplode.B", max_reexplosions=0),
        ],
    )
    step_name = "test.selective.q.reexplode.no_sibling.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "draft"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == {"A": 1, "B": 0}
    assert "confirm" in _field_decl_text(ctx, "A")

    rows = _active_rows(api, sid, form_id)
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED

    overlays = get_latest_engine_form_page_data_read(
        state=_state(api, sid),
        form_id=form_id,
        frame_id="F",
        span_id="S",
    )
    assert overlays["A"]["confirm"] in {"", "yes"}

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == {"A": 2, "B": 0}

    rows = _active_rows(api, sid, form_id)
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    ctx = api.step_session(sid, fill={"B": {"value": "bee"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 2, "B": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "bee"


# ---------------------------------------------------------------------------
# Partial same-span public tape semantics
# ---------------------------------------------------------------------------


def test_partial_plain_p_submit_is_public_tick_and_does_not_touch_q_sibling():
    """
    Partial submit law.

    P and Q share one span. Submitting P alone should:
      - accept/cache/commit P progress;
      - keep the same logical span public;
      - not invoke Q;
      - expose P's value in the same-span context.
    """

    form_id = "selective.partial.p_then_q"
    calls: Dict[str, int] = {"Q": 0}

    def widget_q(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["Q"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "Q done"},
            "state": {},
        }

    register_datum_widget_v1("test.selective.partial.Q", widget_q, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _p_datum("P"),
            _q_datum("Q", widget="test.selective.partial.Q", max_reexplosions=0),
        ],
    )
    step_name = "test.selective.partial.p_then_q.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"P": {"value": "plain"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == {"Q": 0}
    assert _field_value(ctx, "P")["value"] == "plain"
    assert _active_rows(api, sid, form_id) == {}

    ctx = api.step_session(sid, fill={"Q": {"value": "queue"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"Q": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["P"]["value"] == "plain"
    assert out["form_fills"]["Q"]["value"] == "queue"


def test_partial_plain_p_submit_undo_redo_replays_without_touching_q_sibling():
    """
    Partial public tape law.

    A partial accepted P submit inside a larger span is still a public tape tick:
      - undo removes it;
      - redo reapplies it;
      - redo must not invoke untouched Q sibling;
      - final Q submit completes the original span.
    """

    form_id = "selective.partial.undo_redo"
    calls: Dict[str, int] = {"Q": 0}

    def widget_q(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["Q"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "Q done"},
            "state": {},
        }

    register_datum_widget_v1("test.selective.partial.undo_redo.Q", widget_q, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _p_datum("P"),
            _q_datum("Q", widget="test.selective.partial.undo_redo.Q", max_reexplosions=0),
        ],
    )
    step_name = "test.selective.partial.undo_redo.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"P": {"value": "one"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert _field_value(ctx, "P")["value"] == "one"
    assert calls == {"Q": 0}

    ctx = api.undo_last_step(sid)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "P" not in (ctx.get("datum_widget_fills") or {})
    assert calls == {"Q": 0}
    assert _active_rows(api, sid, form_id) == {}

    ctx = api.redo_last_step(sid)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert _field_value(ctx, "P")["value"] == "one"
    assert calls == {"Q": 0}

    ctx = api.step_session(sid, fill={"Q": {"value": "two"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"Q": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["P"]["value"] == "one"
    assert out["form_fills"]["Q"]["value"] == "two"


# ---------------------------------------------------------------------------
# Reexplode + working fill + tape navigation
# ---------------------------------------------------------------------------


def test_reexplode_with_plain_p_sibling_undo_redo_preserves_working_fill_and_commits_later():
    """
    Working-fill preservation law.

    A and B share one span:
      - A is Q and reexplodes.
      - B is plain P.
      - First submit sends A and B together.
      - A reexplodes; B becomes same-span working progress.
      - Undo returns to pre-reexplode/pre-B state.
      - Redo returns to reexploded A with B still visible.
      - Confirming A alone completes and commits both A and B.
    """

    form_id = "selective.reexplode.p_sibling.undo_redo"
    calls: Dict[str, int] = {"A": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "A done"},
                "state": {"confirmed": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm A",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.selective.reexplode.p_sibling.A",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 8,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm A"},
            "proc_notes": {"small": "ok"},
        }

    register_datum_widget_v1("test.selective.reexplode.p_sibling.A", widget_a, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum("A", widget="test.selective.reexplode.p_sibling.A"),
            _p_datum("B"),
        ],
    )
    step_name = "test.selective.reexplode.p_sibling.undo_redo.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "draft"},
            "B": {"value": "plain-b"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1}
    assert "confirm" in _field_decl_text(ctx, "A")
    assert _field_value(ctx, "B")["value"] == "plain-b"

    rows = _active_rows(api, sid, form_id)
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED

    ctx = api.undo_last_step(sid)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "value" in _field_decl_text(ctx, "A")
    assert "confirm" not in _field_decl_text(ctx, "A")
    assert "B" not in (ctx.get("datum_widget_fills") or {})
    assert _active_rows(api, sid, form_id) == {}
    assert calls == {"A": 1}

    ctx = api.redo_last_step(sid)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "confirm" in _field_decl_text(ctx, "A")
    assert _field_value(ctx, "B")["value"] == "plain-b"
    assert calls == {"A": 2}

    rows = _active_rows(api, sid, form_id)
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 3}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "plain-b"

    rows = _active_rows(api, sid, form_id)
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE


def test_reexplode_undo_then_new_branch_clears_old_redo_and_keeps_selective_semantics():
    """
    Branch law for reexplode.

    After undoing a reexplode tick, taking a different same-span submit must
    clear the old redo branch. The new branch must still respect touched-only
    evaluation.
    """

    form_id = "selective.reexplode.branch_clear"
    calls: Dict[str, int] = {"A": 0, "B": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "A done"},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.selective.branch.A",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm A"},
        }

    def widget_b(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["B"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "B done"},
            "state": {},
        }

    register_datum_widget_v1("test.selective.branch.A", widget_a, overwrite=True)
    register_datum_widget_v1("test.selective.branch.B", widget_b, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum("A", widget="test.selective.branch.A"),
            _q_datum("B", widget="test.selective.branch.B", max_reexplosions=0),
        ],
    )
    step_name = "test.selective.reexplode.branch_clear.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "draft"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0}
    assert "confirm" in _field_decl_text(ctx, "A")

    ctx = api.undo_last_step(sid)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0}
    assert _active_rows(api, sid, form_id) == {}

    # New branch: fill B instead of redoing A.
    ctx = api.step_session(sid, fill={"B": {"value": "bee"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 1}

    with pytest.raises(Exception):
        api.redo_last_step(sid)

    # A is still untouched in this new branch; now fill A from its original surface.
    ctx = api.step_session(sid, fill={"A": {"value": "new-a"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 2, "B": 1}
    assert "confirm" in _field_decl_text(ctx, "A")

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 3, "B": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "bee"


# ---------------------------------------------------------------------------
# Blocked/retry sibling behavior
# ---------------------------------------------------------------------------


def test_blocked_q_sibling_is_not_collaterally_blocked_until_touched_then_retries_cleanly():
    """
    Blocked sibling law.

    A and B are Q datums in one span.
      - Filling A must not invoke or block B.
      - Filling B with a bad value blocks only B and does not disturb A.
      - Retrying B succeeds and completes the span.
    """

    form_id = "selective.blocked.sibling.retry"
    calls: Dict[str, int] = {"A": 0, "B": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "A done"},
            "state": {},
        }

    def widget_b(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["B"] += 1
        partial = dict(q.get("partial_fill") or {})
        if partial.get("value") != "ok":
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "B must be ok"},
                "state": {"last": partial.get("value")},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": "B done"},
            "state": {"last": "ok"},
        }

    register_datum_widget_v1("test.selective.blocked.A", widget_a, overwrite=True)
    register_datum_widget_v1("test.selective.blocked.B", widget_b, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum("A", widget="test.selective.blocked.A", max_reexplosions=0),
            _q_datum("B", widget="test.selective.blocked.B", max_reexplosions=0),
        ],
    )
    step_name = "test.selective.blocked.sibling.retry.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "a"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0}

    rows = _active_rows(api, sid, form_id)
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    ctx = api.step_session(sid, fill={"B": {"value": "bad"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 1}
    assert ctx["last_error"]["B"] == "B must be ok"

    rows = _active_rows(api, sid, form_id)
    assert "A" in rows
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    # Blocked is a public validation/error stop. Some implementations persist a
    # blocked lifecycle row, while the compact path may leave no active row for
    # B. The stable contract is: B was called, the user sees the error, and B
    # did not commit.
    if "B" in rows:
        assert rows["B"]["status"] in {DATUM_LIFECYCLE_STATUS_BLOCKED, None}

    out = api.get_outputs(sid)
    assert out.get("form_fills", {}).get("B") is None

    ctx = api.step_session(sid, fill={"B": {"value": "ok"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 1, "B": 2}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "a"
    assert out["form_fills"]["B"]["value"] == "ok"

    rows = _active_rows(api, sid, form_id)
    assert rows["B"]["status"] == DATUM_LIFECYCLE_STATUS_DONE


# ---------------------------------------------------------------------------
# Wider span stress: selective evaluations stay exactly proportional to touches
# ---------------------------------------------------------------------------


def test_wide_same_span_selective_evaluation_count_matches_number_of_touched_q_datums():
    """
    Wide-span law.

    One span owns many Q datums. Filling every other datum should evaluate
    exactly those datums and no others. Completing the rest later should bring
    total calls to exactly n.
    """

    form_id = "selective.wide.same_span"
    n = 30
    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        fid = str(q.get("datum_id") or q.get("field_id") or q["datum"]["id"])
        calls.append(fid)
        return {
            "status": "done",
            "message": {"level": "success", "text": f"{fid} done"},
            "state": {"called": fid},
        }

    register_datum_widget_v1("test.selective.wide.widget", widget, overwrite=True)

    fs = _single_span_multiframespec(
        app_form_id=form_id,
        datums=[
            _q_datum(f"D{i}", widget="test.selective.wide.widget", max_reexplosions=0)
            for i in range(n)
        ],
    )
    step_name = "test.selective.wide.same_span.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _start(api, step_name)

    first_wave = [i for i in range(n) if i % 2 == 0]
    second_wave = [i for i in range(n) if i % 2 == 1]

    for i in first_wave:
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    assert calls == [f"D{i}" for i in first_wave]

    active = _active_rows(api, sid, form_id)
    assert set(active) == {f"D{i}" for i in first_wave}

    writes = _runtime_lifecycle_writes(api, sid)
    assert len(writes) == len(first_wave)

    for i in second_wave[:-1]:
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={f"D{second_wave[-1]}": {"value": f"v{second_wave[-1]}"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == [f"D{i}" for i in first_wave + second_wave]

    out = api.get_outputs(sid)
    assert len(out["form_fills"]) == n
    for i in range(n):
        assert out["form_fills"][f"D{i}"]["value"] == f"v{i}"

    writes = _runtime_lifecycle_writes(api, sid)
    assert len(writes) == n

    active = _active_rows(api, sid, form_id)
    assert set(active) == {f"D{i}" for i in range(n)}