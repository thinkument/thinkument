# think-backend/tests/wippp/test_exploded_world_datum_runtime_bounds_e2e.py
from __future__ import annotations

"""
Exploded World Datum Runtime Bounds E2E
=======================================

This sheet zooms into datum-widget authoring and the engine-side remote/bounds.

It proves the Q runtime contract from the developer's point of view:

    Q input:
        core/datum shell
        raw fill
        partially validated fill
        prefill
        bounded state
        structural satisfaction flag
        reexplode count
        max limits
        compact ctx

    Q output:
        done
        blocked
        reexplode

    Engine guardrails:
        max_reexplosions is a hard cap on line-3 outputs;
        messages are windowed;
        proc_notes is windowed;
        lifecycle writes are refs/previews, not payload copies;
        malformed widget output becomes a datum-local manual error;
        P datums bypass the Q shell entirely;
        Q rows are bounded per datum, not one giant append-only payload;
        default query paths are compact and opt into values explicitly.

These tests are intentionally E2E through AppTableSessionAPI rather than unit
tests of datum_lifecycle.py only.
"""

import time
from typing import Any, Dict, List, Mapping, Sequence

from __exceptions.engine import DatumLifecycleContractError

import pytest

from __datomatonTM import (
    register_datum_widget_v1,
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    DATUM_LIFECYCLE_STATUS_REEXPLODED,
    KEY_DATUM_LIFECYCLE,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_RUNTIME_WRITE_INDEX
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


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _bool_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "bool", "required": required}


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
    return [{"public_step_name": step_name.replace(".", "_"), "step_fn": step_name, "fn_args": {}}]


def _create(
    api,
    step_name: str,
    *,
    include_full_multiframespec_in_ctx: bool = True,
) -> tuple[str, Dict[str, Any]]:
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_full_multiframespec_in_ctx": include_full_multiframespec_in_ctx,
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return sid, ctx


def _one_q_form(
    *,
    app_form_id: str,
    widget: str,
    max_reexplosions: int,
    max_proc_notes: int = 2,
    max_messages: int = 3,
    micro_name: str = "value",
    micro_type: str = "text",
    required: bool = True,
    seed_state: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if micro_type == "number":
        micro = _number_micro(micro_name, required=required)
    elif micro_type == "bool":
        micro = _bool_micro(micro_name, required=required)
    else:
        micro = _text_micro(micro_name, required=required)

    return {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "D",
                "title": "D",
                "micros": [micro],
                "lifecycle": {
                    "widget": widget,
                    "max_reexplosions": max_reexplosions,
                    "max_proc_notes": max_proc_notes,
                    "max_messages": max_messages,
                    "state": dict(seed_state if seed_state is not None else {"seeded": True}),
                },
            }
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["D"]}]}],
    }


def _q_datum(
    datum_id: str,
    *,
    widget: str,
    micros: Sequence[Mapping[str, Any]] | None = None,
    max_reexplosions: int = 0,
    max_proc_notes: int = 2,
    max_messages: int = 3,
    state: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "id": datum_id,
        "title": datum_id,
        "micros": [dict(m) for m in (micros or [_text_micro()])],
        "lifecycle": {
            "widget": widget,
            "max_reexplosions": max_reexplosions,
            "max_proc_notes": max_proc_notes,
            "max_messages": max_messages,
            "state": dict(state or {}),
        },
    }


def _row(api, sid: str, form_id: str, datum_id: str = "D") -> Mapping[str, Any]:
    st = api._get(sid).state
    return st[KEY_DATUM_LIFECYCLE]["forms"][form_id]["datums"][datum_id]


def _runtime_lifecycle_writes(
    api,
    sid: str,
    *,
    max_results: int = 10_000,
    include_values: bool = False,
) -> List[Mapping[str, Any]]:
    st = api._get(sid).state
    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": max_results,
            "include_values": include_values,
        },
    )
    assert q["ok"] is True
    return list(q["writes"])


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


def _pending_datum_shell(
    ctx: Mapping[str, Any],
    datum_id: str,
) -> Mapping[str, Any]:
    """
    Return the pending datum shell/decl for a datum from any public-compatible
    ctx shape.

    Some ctxs expose:
        datum_widgets_on_this_span = [{"field_id": "D", "datum_args": {...}}]

    Others expose only pending ids and put richer info under:
        datum_widget_decls["D"].
    """
    for item in ctx.get("datum_widgets_on_this_span", []) or []:
        if isinstance(item, Mapping):
            fid = item.get("field_id") or item.get("id") or item.get("name")
            if str(fid) == str(datum_id):
                datum_args = item.get("datum_args")
                if isinstance(datum_args, Mapping):
                    return datum_args

                if "micros" in item:
                    return item

    decls = ctx.get("datum_widget_decls") or {}
    if isinstance(decls, Mapping):
        decl = decls.get(datum_id)
        if isinstance(decl, Mapping):
            datum_args = decl.get("datum_args")
            if isinstance(datum_args, Mapping):
                return datum_args
            if "micros" in decl:
                return decl

    raise AssertionError(
        f"Could not find pending datum shell for {datum_id!r}. "
        f"ctx keys={sorted(str(k) for k in ctx.keys())}"
    )

    
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
    assert _runtime_lifecycle_writes(api, sid) == []

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


def _working_prefill_for(
    api,
    sid: str,
    form_id: str,
    datum_id: str,
    *,
    frame_id: str = "F",
    span_id: str = "S",
) -> Mapping[str, Any]:
    st = api._get(sid).state
    form = st[KEY_DATUM_LIFECYCLE]["forms"][form_id]
    span_key = f"{frame_id}\x1f{span_id}"

    by_span = form.get("working_prefills_by_span") or {}
    val = ((by_span.get(span_key) or {}).get(datum_id))
    if isinstance(val, Mapping):
        return val

    row = form["datums"][datum_id]
    row_prefills = row.get("working_prefills") or {}
    val = ((row_prefills.get(span_key) or {}).get(datum_id))
    if isinstance(val, Mapping):
        return val

    return {}


# ---------------------------------------------------------------------------
# Widget I/O contract
# ---------------------------------------------------------------------------


def test_widget_input_contains_precise_compact_runtime_context_and_seed_state():
    seen: List[Dict[str, Any]] = []

    def inspecting_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q))
        return {
            "status": "done",
            "message": {"level": "success", "text": "ok"},
            "state": {"observed": True},
        }

    register_datum_widget_v1("test.bounds.inspect", inspecting_widget, overwrite=True)

    form_id = "bounds.inspect"
    step_name = "test.bounds.inspect.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.inspect",
            max_reexplosions=0,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "hello"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(seen) == 1
    q = seen[0]

    assert q["form_id"] == form_id
    assert q["frame_id"] == "F"
    assert q["span_id"] == "S"
    assert q["datum_id"] == "D"

    assert isinstance(q["datum"], Mapping)
    assert q["datum"]["id"] == "D"
    assert _semantic_micros(q["datum"]["micros"]) == [_text_micro("value")]

    assert q["raw_fill"] == {"value": "hello"}
    assert q["partial_fill"] == {"value": "hello"}
    assert (q.get("prefill") or {}) == {}
    assert q["structurally_satisfied"] is True
    assert q["state"] == {"seeded": True}
    assert q["reexplode_count"] == 0
    assert q["max_reexplosions"] == 0

    assert q["ctx"]["attempt"] == 1
    assert q["ctx"]["is_revisit"] is False

    # Stable formal coordinates live at the Q-input top level.
    # ctx is intentionally compact auxiliary runtime context and should not
    # be required to duplicate every top-level coordinate under legacy names.
    assert q["form_id"] == form_id
    assert q["frame_id"] == "F"
    assert q["span_id"] == "S"

    # If ctx exposes duplicate coordinates, they must agree, but they are not
    # part of the minimum Q-widget contract.
    if "form_id" in q["ctx"]:
        assert q["ctx"]["form_id"] == form_id
    if "frame_id" in q["ctx"]:
        assert q["ctx"]["frame_id"] == "F"
    if "span_id" in q["ctx"]:
        assert q["ctx"]["span_id"] == "S"
    if "fillspan_name" in q["ctx"]:
        assert q["ctx"]["fillspan_name"] == "S"

    row = _row(api, sid, form_id)
    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert row["state"] == {"observed": True}
    assert row["messages"][-1]["text"] == "ok"


def test_widget_input_partial_fill_is_type_normalized_before_q_sees_it():
    seen: List[Dict[str, Any]] = []

    def inspect_number(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q))
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {}}

    register_datum_widget_v1("test.bounds.inspect.number", inspect_number, overwrite=True)

    form_id = "bounds.inspect.number"
    step_name = "test.bounds.inspect.number.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.inspect.number",
            max_reexplosions=0,
            micro_type="number",
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "42"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(seen) == 1
    assert seen[0]["raw_fill"] == {"value": "42"}
    assert seen[0]["partial_fill"] == {"value": 42}


def test_widget_input_sees_structurally_unsatisfied_optional_and_required_shapes():
    seen: List[Dict[str, Any]] = []

    def inspect_missing(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q))
        return {
            "status": "blocked",
            "message": {"level": "error", "text": "missing as expected"},
            "state": {"saw_missing": True},
        }

    register_datum_widget_v1("test.bounds.inspect.missing", inspect_missing, overwrite=True)

    form_id = "bounds.inspect.missing"
    step_name = "test.bounds.inspect.missing.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.inspect.missing",
            max_reexplosions=0,
            required=True,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "D" in ctx["last_error"]

    assert len(seen) == 1
    assert seen[0]["partial_fill"] == {}
    assert seen[0]["structurally_satisfied"] is False


# ---------------------------------------------------------------------------
# Hard bounds: max_reexplosions, messages, proc_notes
# ---------------------------------------------------------------------------


def test_max_reexplosions_zero_forces_satisfied_even_when_widget_asks_to_reexplode():
    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "micros": [_text_micro("again")],
                "lifecycle": {
                    "widget": "test.bounds.force.zero",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            },
            "state": {"wanted": "reexplode"},
            "message": {"level": "info", "text": "again"},
            "proc_notes": {"x": "y"},
        }

    register_datum_widget_v1("test.bounds.force.zero", always_reexplode, overwrite=True)

    form_id = "bounds.force.zero"
    step_name = "test.bounds.force.zero.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.force.zero",
            max_reexplosions=0,
            max_proc_notes=1,
            max_messages=2,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    row = _row(api, sid, form_id)
    assert row["status"] == DATUM_LIFECYCLE_STATUS_FORCED_DONE
    assert row["forced_done"] is True
    assert row["reexplode_count"] == 0
    assert row["state"] == {"wanted": "reexplode"}


def test_messages_and_proc_notes_are_windowed_across_many_reexplodes():
    giant = "B" * 200_000

    def window_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "micros": [_text_micro(f"v{n}")],
                "lifecycle": {
                    "widget": "test.bounds.window",
                    "max_reexplosions": 8,
                    "max_proc_notes": 2,
                    "max_messages": 3,
                },
            },
            "fill": {f"v{n}": ""},
            "state": {"n": n + 1},
            "message": {"level": "info", "text": f"msg-{n}"},
            "proc_notes": {"i": n, "giant": giant},
        }

    register_datum_widget_v1("test.bounds.window", window_widget, overwrite=True)

    form_id = "bounds.window"
    step_name = "test.bounds.window.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.window",
            max_reexplosions=8,
            max_proc_notes=2,
            max_messages=3,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    micro = "value"
    for i in range(5):
        ctx = api.step_session(sid, fill={"D": {micro: "x"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        micro = f"v{i}"

    row = _row(api, sid, form_id)

    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row["reexplode_count"] == 5
    assert len(row["messages"]) == 3
    assert [m["text"] for m in row["messages"]] == ["msg-2", "msg-3", "msg-4"]
    assert len(row["proc_notes"]) == 2
    assert [b["i"] for b in row["proc_notes"]] == [3, 4]


def test_zero_message_and_proc_notes_limits_are_respected():
    def quiet_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "micros": [_text_micro(f"v{n}")],
                "lifecycle": {
                    "widget": "test.bounds.zero.windows",
                    "max_reexplosions": 3,
                    "max_proc_notes": 0,
                    "max_messages": 0,
                },
            },
            "fill": {f"v{n}": ""},
            "state": {"n": n + 1},
            "message": {"level": "info", "text": f"msg-{n}"},
            "proc_notes": {"n": n},
        }

    register_datum_widget_v1("test.bounds.zero.windows", quiet_reexplode, overwrite=True)

    form_id = "bounds.zero.windows"
    step_name = "test.bounds.zero.windows.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.zero.windows",
            max_reexplosions=3,
            max_proc_notes=0,
            max_messages=0,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    row = _row(api, sid, form_id)
    assert row["reexplode_count"] == 1
    assert row["messages"] == []
    assert row["proc_notes"] == []


def test_max_reexplosions_hard_cap_progresses_after_exact_cap_without_unbounded_loop():
    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "micros": [_text_micro(f"v{n}")],
                "lifecycle": {
                    "widget": "test.bounds.cap.two",
                    "max_reexplosions": 2,
                    "max_proc_notes": 1,
                    "max_messages": 3,
                },
            },
            "fill": {f"v{n}": ""},
            "state": {"n": n + 1},
            "message": {"level": "info", "text": f"again-{n}"},
            "proc_notes": {"n": n},
        }

    register_datum_widget_v1("test.bounds.cap.two", always_reexplode, overwrite=True)

    form_id = "bounds.cap.two"
    step_name = "test.bounds.cap.two.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.cap.two",
            max_reexplosions=2,
            max_proc_notes=1,
            max_messages=3,
        ),
    )

    api = _api()
    sid, ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"v0": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"v1": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    row = _row(api, sid, form_id)
    assert row["status"] == DATUM_LIFECYCLE_STATUS_FORCED_DONE
    assert row["forced_done"] is True
    assert row["reexplode_count"] == 2


def test_reexplode_count_and_state_are_seen_monotonically_by_widget():
    seen: List[tuple[int, Mapping[str, Any]]] = []

    def monotonic(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        seen.append((n, dict(q.get("state") or {})))
        if n < 3:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro(f"v{n}")],
                    "lifecycle": {
                        "widget": "test.bounds.monotonic",
                        "max_reexplosions": 3,
                        "max_proc_notes": 2,
                        "max_messages": 3,
                    },
                },
                "fill": {f"v{n}": ""},
                "state": {"last": n},
                "message": {"level": "info", "text": f"r{n}"},
                "proc_notes": {"n": n},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {"last": n}}

    register_datum_widget_v1("test.bounds.monotonic", monotonic, overwrite=True)

    form_id = "bounds.monotonic"
    step_name = "test.bounds.monotonic.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.monotonic",
            max_reexplosions=3,
            max_proc_notes=2,
            max_messages=3,
            seed_state={"last": -1},
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    micro = "value"
    for i in range(4):
        ctx = api.step_session(sid, fill={"D": {micro: "x"}})
        micro = f"v{i}"

    assert ctx["kind"] == "ATCOMPLETION"
    assert [n for n, _state in seen] == [0, 1, 2, 3]
    assert [state.get("last") for _n, state in seen] == [-1, 0, 1, 2]
    assert _row(api, sid, form_id)["state"] == {"last": 3}


# ---------------------------------------------------------------------------
# Runtime index compactness and value-ref behavior
# ---------------------------------------------------------------------------


def test_large_proc_notes_is_state_only_not_runtime_index_or_default_query_payload():
    giant = "X" * 1_000_000

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.bounds.large.proc_notes",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"giant": giant},
        }

    register_datum_widget_v1("test.bounds.large.proc_notes", widget, overwrite=True)

    form_id = "bounds.large.proc_notes"
    step_name = "test.bounds.large.proc_notes.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.large.proc_notes",
            max_reexplosions=1,
            max_proc_notes=1,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    st = api._get(sid).state
    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "X", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "X", 1000)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 5,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert not _contains_run(q, "X", 1000)

    q_values = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 1,
            "include_values": True,
        },
    )
    assert q_values["ok"] is True
    assert _contains_run(q_values, "X", 1000)


def test_runtime_write_index_records_lifecycle_refs_not_mutable_full_rows():
    def one_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        if n == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "widget": "test.bounds.write.refs",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 3,
                    },
                },
                "fill": {"confirm": ""},
                "state": {"phase": "confirm"},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"phase": "confirm"},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {"phase": "done"}}

    register_datum_widget_v1("test.bounds.write.refs", one_reexplode, overwrite=True)

    form_id = "bounds.write.refs"
    step_name = "test.bounds.write.refs.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.write.refs",
            max_reexplosions=1,
            max_proc_notes=1,
            max_messages=3,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    writes = _runtime_lifecycle_writes(api, sid, include_values=False)
    assert len(writes) == 2

    for w in writes:
        assert w.get("write_kind") == WRITE_KIND_DATUM_LIFECYCLE
        assert not _contains_run(w, "confirm", 100)

    writes_with_values = _runtime_lifecycle_writes(api, sid, include_values=True)
    assert len(writes_with_values) == 2
    assert any(_contains_run(w, "confirm", 1) for w in writes_with_values)


def test_runtime_query_max_results_is_honored_for_many_lifecycle_writes():
    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {"ok": True}}

    register_datum_widget_v1("test.bounds.query.limit.done", done, overwrite=True)

    n = 12
    fs = {
        "app_form_id": "bounds.query.limit",
        "datums": [
            _q_datum(
                f"D{i}",
                widget="test.bounds.query.limit.done",
                max_reexplosions=0,
                max_proc_notes=1,
                max_messages=1,
            )
            for i in range(n)
        ],
        "frames": [{"id": "F", "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)]}],
    }
    step_name = "test.bounds.query.limit.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    assert ctx["kind"] == "ATCOMPLETION"

    st = api._get(sid).state
    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 5,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) == 5


# ---------------------------------------------------------------------------
# Malformed widget output and datum-local errors
# ---------------------------------------------------------------------------


def test_malformed_widget_outputs_are_fatal():
    cases = {
        "invalid_status": lambda _q: {"status": "banana", "state": {}, "message": "bad"},
        "not_mapping": lambda _q: ["not", "mapping"],
        "reexplode_without_datum": lambda _q: {"status": "reexplode", "state": {}, "message": "missing datum"},
        "non_json_state": lambda _q: {"status": "done", "state": {"bad": object()}, "message": "bad"},
    }

    for suffix, fn in cases.items():
        widget = f"test.bounds.malformed.{suffix}"
        register_datum_widget_v1(widget, fn, overwrite=True)

        form_id = f"bounds.malformed.{suffix}"
        step_name = f"test.bounds.malformed.{suffix}.step"
        _register_step(
            step_name,
            _one_q_form(
                app_form_id=form_id,
                widget=widget,
                max_reexplosions=1,
            ),
        )

        api = _api()
        sid, _ctx = _create(api, step_name)

        with pytest.raises(DatumLifecycleContractError):
            ctx = api.step_session(sid, fill={"D": {"value": "x"}})


def test_malformed_widget_error_is_fatal():
    def bad_widget(_q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "done", "state": {"bad": object()}, "message": "not-json"}

    register_datum_widget_v1("test.bounds.bad.no.write", bad_widget, overwrite=True)

    form_id = "bounds.bad.no.write"
    step_name = "test.bounds.bad.no.write.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.bad.no.write",
            max_reexplosions=1,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)
    
    with pytest.raises(DatumLifecycleContractError):
        ctx = api.step_session(sid, fill={"D": {"value": "x"}})

    _assert_no_committed_lifecycle_for_form(api, sid, form_id)


def test_blocked_widget_is_manual_error_without_lifecycle_commit_or_redo_surface():
    calls = 0

    def blocked(q: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "blocked",
            "message": {"level": "error", "text": "business rule failed"},
            "state": {"calls": calls},
        }

    register_datum_widget_v1("test.bounds.blocked.no.commit", blocked, overwrite=True)

    form_id = "bounds.blocked.no.commit"
    step_name = "test.bounds.blocked.no.commit.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.blocked.no.commit",
            max_reexplosions=1,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["last_error"]["D"]

    _assert_no_committed_lifecycle_for_form(api, sid, form_id)

    with pytest.raises(Exception):
        api.redo_last_step(sid)


def test_blocked_then_valid_retry_commits_exactly_one_lifecycle_write():
    calls: List[Mapping[str, Any]] = []

    def gate(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(dict(q))
        val = str((q.get("partial_fill") or {}).get("value", ""))
        if val != "ok":
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "say ok"},
                "state": {"last": val},
            }
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {"last": val}}

    register_datum_widget_v1("test.bounds.block.retry", gate, overwrite=True)

    form_id = "bounds.block.retry"
    step_name = "test.bounds.block.retry.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.block.retry",
            max_reexplosions=0,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "D" in ctx["last_error"]

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(calls) == 2
    assert _row(api, sid, form_id)["state"] == {"last": "ok"}
    assert len(_runtime_lifecycle_writes(api, sid)) == 1


# ---------------------------------------------------------------------------
# P fast path / Q opt-in only
# ---------------------------------------------------------------------------


def test_plain_p_datums_bypass_q_lifecycle_even_when_many_and_fast():
    n = 180
    fs = {
        "app_form_id": "bounds.p.fast",
        "datums": [{"id": f"D{i}", "title": f"D{i}", "micros": [_text_micro()]} for i in range(n)],
        "frames": [{"id": "F", "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)]}],
    }
    step_name = "test.bounds.p.fast.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    st = api._get(sid).state
    lifecycle = st.get(KEY_DATUM_LIFECYCLE)
    if isinstance(lifecycle, Mapping):
        forms = lifecycle.get("forms", {})
        assert forms in ({}, None)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 10_000,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert q["writes"] == []

    print(
        "[exploded-bounds-summary] p_bypass_q "
        f"n={n} elapsed={elapsed:.6f}s avg_fill_ms={elapsed * 1000 / n:.3f}"
    )

    assert elapsed < 10.0


def test_mixed_p_and_q_span_runs_q_only_for_lifecycle_datums():
    calls: List[str] = []

    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(str(q["datum_id"]))
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {"ok": True}}

    register_datum_widget_v1("test.bounds.mixed.only.q", done, overwrite=True)

    fs = {
        "app_form_id": "bounds.mixed.only.q",
        "datums": [
            {"id": "P", "title": "P", "micros": [_text_micro()]},
            _q_datum("Q", widget="test.bounds.mixed.only.q", max_reexplosions=0),
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["P", "Q"]}]}],
    }
    step_name = "test.bounds.mixed.only.q.step"
    _register_step(step_name, fs)

    api = _api()
    sid, ctx = _create(api, step_name)
    assert set(_ctx_pending_field_ids(ctx)) == {"P", "Q"}

    ctx = api.step_session(sid, fill={"P": {"value": "p"}, "Q": {"value": "q"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert calls == ["Q"]
    form_row = api._get(sid).state[KEY_DATUM_LIFECYCLE]["forms"]["bounds.mixed.only.q"]["datums"]
    assert set(form_row) == {"Q"}
    assert len(_runtime_lifecycle_writes(api, sid)) == 1


def test_datum_with_empty_lifecycle_mapping_is_q_opt_in_and_uses_registered_widget():
    calls: List[Mapping[str, Any]] = []

    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(dict(q))
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {"ok": True}}

    register_datum_widget_v1("test.bounds.empty.lifecycle", done, overwrite=True)

    fs = {
        "app_form_id": "bounds.empty.lifecycle",
        "datums": [
            {
                "id": "D",
                "title": "D",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.bounds.empty.lifecycle",
                },
            }
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["D"]}]}],
    }
    step_name = "test.bounds.empty.lifecycle.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(calls) == 1
    assert _row(api, sid, "bounds.empty.lifecycle")["status"] == DATUM_LIFECYCLE_STATUS_DONE


# ---------------------------------------------------------------------------
# Scale and asymptotic guardrails
# ---------------------------------------------------------------------------


def test_many_q_done_datums_have_one_lifecycle_row_and_write_per_q_fill_and_scale_linearly():
    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        if not q.get("structurally_satisfied"):
            return {"status": "blocked", "message": {"level": "error", "text": "missing"}, "state": {}}
        return {"status": "done", "message": {"level": "success", "text": ""}, "state": {"ok": True}}

    register_datum_widget_v1("test.bounds.many.done", done, overwrite=True)

    n = 100
    fs = {
        "app_form_id": "bounds.many.done",
        "datums": [
            {
                "id": f"D{i}",
                "title": f"D{i}",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.bounds.many.done",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            }
            for i in range(n)
        ],
        "frames": [{"id": "F", "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)]}],
    }
    step_name = "test.bounds.many.done.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    st = api._get(sid).state
    form_row = st[KEY_DATUM_LIFECYCLE]["forms"]["bounds.many.done"]
    assert len(form_row["datums"]) == n

    for i in range(n):
        assert form_row["datums"][f"D{i}"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": n + 10,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) == n

    print(
        "[exploded-bounds-summary] many_q_done "
        f"n={n} elapsed={elapsed:.6f}s avg_fill_ms={elapsed * 1000 / n:.3f} "
        f"lifecycle_writes={len(q['writes'])}"
    )

    assert elapsed < 15.0


def test_many_q_reexploding_datums_have_bounded_rows_and_two_writes_each():
    def once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        datum_id = str(q["datum_id"])
        if n == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "widget": "test.bounds.many.reexplode.once",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 2,
                    },
                },
                "fill": {"confirm": ""},
                "state": {"phase": "confirm", "id": datum_id},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"id": datum_id},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"phase": "done", "id": datum_id},
        }

    register_datum_widget_v1("test.bounds.many.reexplode.once", once, overwrite=True)

    n = 50
    fs = {
        "app_form_id": "bounds.many.reexplode.once",
        "datums": [
            _q_datum(
                f"D{i}",
                widget="test.bounds.many.reexplode.once",
                max_reexplosions=1,
                max_proc_notes=1,
                max_messages=2,
            )
            for i in range(n)
        ],
        "frames": [{"id": "F", "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)]}],
    }
    step_name = "test.bounds.many.reexplode.once.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"draft-{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    form_row = api._get(sid).state[KEY_DATUM_LIFECYCLE]["forms"]["bounds.many.reexplode.once"]
    assert len(form_row["datums"]) == n
    for i in range(n):
        row = form_row["datums"][f"D{i}"]
        assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
        assert row["reexplode_count"] == 1
        assert len(row["proc_notes"]) <= 1
        assert len(row["messages"]) <= 2

    writes = _runtime_lifecycle_writes(api, sid, max_results=2 * n + 10)
    assert len(writes) == 2 * n

    print(
        "[exploded-bounds-summary] many_q_reexplode_once "
        f"n={n} elapsed={elapsed:.6f}s avg_step_ms={elapsed * 1000 / (2 * n):.3f} "
        f"lifecycle_writes={len(writes)}"
    )

    assert elapsed < 20.0


def test_many_large_proc_notes_reexplodes_do_not_pollute_runtime_index_payloads():
    giant = "Z" * 500_000

    def once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        n = int(q.get("reexplode_count", 0) or 0)
        if n == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "widget": "test.bounds.large.scale",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 1,
                    },
                },
                "fill": {"confirm": ""},
                "state": {},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"giant": giant},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {}}

    register_datum_widget_v1("test.bounds.large.scale", once, overwrite=True)

    n = 12
    fs = {
        "app_form_id": "bounds.large.scale",
        "datums": [
            _q_datum(
                f"D{i}",
                widget="test.bounds.large.scale",
                max_reexplosions=1,
                max_proc_notes=1,
                max_messages=1,
            )
            for i in range(n)
        ],
        "frames": [{"id": "F", "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)]}],
    }
    step_name = "test.bounds.large.scale.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"draft-{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"

    st = api._get(sid).state
    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "Z", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "Z", 1000)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 2 * n + 10,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) == 2 * n
    assert not _contains_run(q, "Z", 1000)


def test_q_done_complexity_does_not_degrade_when_prior_plain_p_history_is_large():
    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "done", "message": {"level": "success", "text": "ok"}, "state": {"ok": True}}

    register_datum_widget_v1("test.bounds.after.p.done", done, overwrite=True)

    p_n = 140
    q_n = 40
    datums: List[Dict[str, Any]] = []
    spans: List[Dict[str, Any]] = []

    for i in range(p_n):
        did = f"P{i}"
        datums.append({"id": did, "title": did, "micros": [_text_micro()]})
        spans.append({"id": f"SP{i}", "owns": [did]})

    for i in range(q_n):
        did = f"Q{i}"
        datums.append(
            _q_datum(
                did,
                widget="test.bounds.after.p.done",
                max_reexplosions=0,
                max_proc_notes=1,
                max_messages=1,
            )
        )
        spans.append({"id": f"SQ{i}", "owns": [did]})

    fs = {
        "app_form_id": "bounds.after.p",
        "datums": datums,
        "frames": [{"id": "F", "spans": spans}],
    }
    step_name = "test.bounds.after.p.step"
    _register_step(step_name, fs)

    api = _api()
    sid, _ctx = _create(api, step_name)

    for i in range(p_n):
        ctx = api.step_session(sid, fill={f"P{i}": {"value": f"p{i}"}})

    t0 = time.perf_counter()
    for i in range(q_n):
        ctx = api.step_session(sid, fill={f"Q{i}": {"value": f"q{i}"}})
    q_elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(_runtime_lifecycle_writes(api, sid, max_results=q_n + 10)) == q_n

    print(
        "[exploded-bounds-summary] q_after_large_p_history "
        f"p_n={p_n} q_n={q_n} q_elapsed={q_elapsed:.6f}s "
        f"q_avg_fill_ms={q_elapsed * 1000 / q_n:.3f}"
    )

    assert q_elapsed < 10.0


# ---------------------------------------------------------------------------
# Reexplode replacement datum / prefill / current datum shell contract
# ---------------------------------------------------------------------------

def _shell_micros(shell: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """
    Return micros from either authoring datum shape or runtime/manual ctx shape.

    Authoring/Q input shape:
        {"micros": [{"name": ..., "type": ..., "required": ...}]}

    Public manual ctx/runtime shell shape:
        {"micro_input_fields": [{"name": ..., "type": ..., "required": ...}]}

    Some ctx payloads may also expose a lossy list of names under "micros";
    that is useful only for field names, not semantic micro equality.
    """
    micros = shell.get("micros")
    if isinstance(micros, Sequence) and not isinstance(micros, (str, bytes)):
        out: List[Mapping[str, Any]] = []
        for m in micros:
            if isinstance(m, Mapping):
                out.append(m)
            else:
                out.append({"name": str(m)})
        return out

    micro_input_fields = shell.get("micro_input_fields")
    if isinstance(micro_input_fields, Sequence) and not isinstance(micro_input_fields, (str, bytes)):
        return [m for m in micro_input_fields if isinstance(m, Mapping)]

    return []


def _shell_micro_names(shell: Mapping[str, Any]) -> List[str]:
    return [str(m.get("name")) for m in _shell_micros(shell) if m.get("name") is not None]


def test_reexplode_replacement_datum_changes_next_manual_surface_and_prefill_without_leaking_prefill_as_widget_state():
    seen: List[Mapping[str, Any]] = []

    def replace(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q))
        if int(q.get("reexplode_count", 0) or 0) == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "title": "D Confirm",
                    "micros": [_text_micro("confirm"), _text_micro("note", required=False)],
                    "lifecycle": {
                        "widget": "test.bounds.replace.surface",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 3,
                    },
                },
                "fill": {"note": ""},
                "prefill": {"confirm": "prefilled", "note": "optional"},
                "state": {"phase": "confirm"},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"phase": "confirm"},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"phase": "done"},
        }

    register_datum_widget_v1("test.bounds.replace.surface", replace, overwrite=True)

    form_id = "bounds.replace.surface"
    step_name = "test.bounds.replace.surface.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.replace.surface",
            max_reexplosions=1,
            max_proc_notes=1,
            max_messages=3,
        ),
    )

    api = _api()
    sid, ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert _ctx_pending_field_ids(ctx) == ["D"]

    row = _row(api, sid, form_id)
    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert _working_prefill_for(api, sid, form_id, "D") == {
        "confirm": "prefilled",
        "note": "optional",
    }



    ctx = api.step_session(sid, fill={"D": {"confirm": "yes", "note": ""}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(seen) == 2
    assert seen[1]["datum"]["title"] == "D Confirm"

    # Prefill is a manual-surface/UI hint, not widget memory.
    # Widget continuity must flow through state/proc_notes/reexplode_count instead.
    assert seen[1]["prefill"] is None
    assert seen[1]["state"] == {"phase": "confirm"}
    assert seen[1]["partial_fill"] == {"confirm": "yes", "note": ""}


def test_reexplode_can_switch_micro_types_and_next_q_gets_normalized_new_shape():
    seen: List[Mapping[str, Any]] = []

    def switch_to_number(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q))
        if int(q.get("reexplode_count", 0) or 0) == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_number_micro("amount")],
                    "lifecycle": {
                        "widget": "test.bounds.switch.number",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 2,
                    },
                },
                "fill": {"amount": ""},
                "state": {"phase": "amount"},
                "message": {"level": "info", "text": "amount"},
                "proc_notes": {"phase": "amount"},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {}}

    register_datum_widget_v1("test.bounds.switch.number", switch_to_number, overwrite=True)

    form_id = "bounds.switch.number"
    step_name = "test.bounds.switch.number.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.switch.number",
            max_reexplosions=1,
            max_proc_notes=1,
            max_messages=2,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"amount": "123"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert len(seen) == 2
    assert seen[1]["raw_fill"] == {"amount": "123"}
    assert seen[1]["partial_fill"] == {"amount": 123}


# ---------------------------------------------------------------------------
# Undo/redo with bounded lifecycle patches
# ---------------------------------------------------------------------------


def test_undo_redo_of_reexplode_restores_lifecycle_row_without_snapshot_bloat():
    def once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        if int(q.get("reexplode_count", 0) or 0) == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "widget": "test.bounds.undo.redo.row",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 2,
                    },
                },
                "fill": {"confirm": ""},
                "state": {"phase": "confirm"},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"phase": "confirm"},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {"phase": "done"}}

    register_datum_widget_v1("test.bounds.undo.redo.row", once, overwrite=True)

    form_id = "bounds.undo.redo.row"
    step_name = "test.bounds.undo.redo.row.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.undo.redo.row",
            max_reexplosions=1,
            max_proc_notes=1,
            max_messages=2,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert _row(api, sid, form_id)["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "D" in _ctx_pending_field_ids(ctx)

    _assert_no_committed_lifecycle_for_form(api, sid, form_id)

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert _row(api, sid, form_id)["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert _row(api, sid, form_id)["state"] == {"phase": "confirm"}


def test_undo_redo_of_q_done_restores_done_row_and_form_fill():
    def done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {"value": q["partial_fill"]}}

    register_datum_widget_v1("test.bounds.undo.redo.done", done, overwrite=True)

    form_id = "bounds.undo.redo.done"
    step_name = "test.bounds.undo.redo.done.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.undo.redo.done",
            max_reexplosions=0,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert _row(api, sid, form_id)["status"] == DATUM_LIFECYCLE_STATUS_DONE

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    _assert_no_committed_lifecycle_for_form(api, sid, form_id)

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"
    assert _row(api, sid, form_id)["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert _row(api, sid, form_id)["state"] == {"value": {"value": "x"}}


# ---------------------------------------------------------------------------
# Developer-facing negative/edge authoring cases
# ---------------------------------------------------------------------------


def test_widget_cannot_make_invalid_reexploded_required_shape_succeed_silently():
    def invalid_required_shape(q: Mapping[str, Any]) -> Mapping[str, Any]:
        if int(q.get("reexplode_count", 0) or 0) == 0:
            return {
                "status": "reexplode",
                "datum": {
                    **dict(q["datum"]),
                    "micros": [_text_micro("confirm", required=True)],
                    "lifecycle": {
                        "widget": "test.bounds.invalid.shape",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 2,
                    },
                },
                "fill": {"confirm": ""},
                "state": {},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {},
            }
        return {"status": "done", "message": {"level": "success", "text": "done"}, "state": {}}

    register_datum_widget_v1("test.bounds.invalid.shape", invalid_required_shape, overwrite=True)

    form_id = "bounds.invalid.shape"
    step_name = "test.bounds.invalid.shape.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.invalid.shape",
            max_reexplosions=1,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "D" in ctx["last_error"]


def test_widget_done_with_structurally_invalid_fill_is_rejected_unless_forced_by_cap():
    def done_anyway(q: Mapping[str, Any]) -> Mapping[str, Any]:
        assert q["structurally_satisfied"] is False
        return {
            "status": "done",
            "message": {"level": "success", "text": "not allowed"},
            "state": {"tried": True},
        }

    register_datum_widget_v1("test.bounds.done.invalid.fill", done_anyway, overwrite=True)

    form_id = "bounds.done.invalid.fill"
    step_name = "test.bounds.done.invalid.fill.step"
    _register_step(
        step_name,
        _one_q_form(
            app_form_id=form_id,
            widget="test.bounds.done.invalid.fill",
            max_reexplosions=0,
            required=True,
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D": {}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "D" in ctx["last_error"]

    _assert_no_committed_lifecycle_for_form(api, sid, form_id)