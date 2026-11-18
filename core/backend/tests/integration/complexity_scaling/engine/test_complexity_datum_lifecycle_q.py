# think-backend/tests/wipppp/test_complexity_datum_lifecycle_q.py
from __future__ import annotations

"""
Datum Lifecycle Q correctness and complexity tests.

These tests lock in the post-fix contract:

1. Plain P datums remain plain P datums.
   They do not create Q lifecycle rows or datum-lifecycle write events.

2. Explicit Q datums exercise lifecycle machinery only when opted in through
   datum["lifecycle"].

3. Q lifecycle correctness covers:
   - done
   - blocked/retry
   - reexplode overlays
   - forced done when max_reexplosions is reached
   - bounded messages and proc_notes
   - effective multiframespec mutation after reexplode
   - lifecycle query/index preview discipline

4. Q lifecycle complexity covers:
   - no hidden payload duplication in runtime index/query
   - current-form reads do not scale with unrelated historical forms
   - undo and redo stay bounded
   - redo test matches the public API contract by alternating undo/redo rather
     than assuming an arbitrarily materialized redo queue after many undos.

5. Task E span-local correctness covers:
   - submitting one datum in a multi-datum span evaluates only touched Q datums
   - untouched sibling Q datums are not invoked merely because they are pending
   - reexplode preserves accepted sibling working fills
   - partial multi-datum progress remains undoable/redoable as public tape state
"""

import os
import statistics
import time
from typing import Any, Dict, Iterable, List, Mapping

import pytest

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    get_engine_form_page_epoch_from_id,
    get_latest_engine_form_page_data_read
)

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)

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

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


RUN_Q_CRAZY = os.environ.get("APP_TABLE_Q_COMPLEXITY_CRAZY", "0") == "1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _register_step(name: str, fs: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(fs)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _create_manifest(api, step_names: Iterable[str]) -> str:
    st = api.create_VM_session(
        manifest=[
            {"public_step_name": f"step_{i}", "step_fn": step_name, "fn_args": {}}
            for i, step_name in enumerate(step_names)
        ],
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}
    return sid


def _create(api, step_name: str) -> str:
    return _create_manifest(api, [step_name])


def _state(api, sid: str) -> Dict[str, Any]:
    return api._get(sid).state


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


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 100_000) -> bool:
    needle = ch * n
    seen: set[int] = set()
    stack = [obj]
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


def _median(fn, repeats: int = 5) -> float:
    vals = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        vals.append(time.perf_counter() - t0)
    return statistics.median(vals)


def _q_datum_id(q: Mapping[str, Any]) -> str:
    """
    Compatibility helper for tests while Q payload naming settles.

    Prefer datum_id when present, then field_id, then datum.id.
    """

    return str(q.get("datum_id") or q.get("field_id") or q["datum"]["id"])


def _make_many_p_multiframespec(n: int, *, app_form_id: str | None = None) -> Dict[str, Any]:
    datums = [
        {"id": f"D{i}", "title": f"D{i}", "micros": [_text_micro()]}
        for i in range(n)
    ]
    return {
        "app_form_id": app_form_id or f"p.many.{n}",
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
            }
        ],
    }


def _make_q_multiframespec(
    n: int,
    *,
    app_form_id: str | None = None,
    widget: str = "test.q.done_if_structural",
    max_reexplosions: int = 1,
    max_proc_notes: int = 2,
    max_messages: int = 8,
) -> Dict[str, Any]:
    datums = [
        {
            "id": f"D{i}",
            "title": f"D{i}",
            "micros": [_text_micro()],
            "lifecycle": {
                "widget": widget,
                "max_reexplosions": max_reexplosions,
                "max_proc_notes": max_proc_notes,
                "max_messages": max_messages,
            },
        }
        for i in range(n)
    ]
    return {
        "app_form_id": app_form_id or f"q.many.{n}",
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
            }
        ],
    }


def _register_done_if_structural_widget(
    name: str = "test.q.done_if_structural",
) -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        if not bool(q.get("structurally_satisfied")):
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "required fields missing"},
                "state": dict(q.get("state") or {}),
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": ""},
            "state": dict(q.get("state") or {}),
        }

    register_datum_widget_v1(name, widget, overwrite=True)


# ---------------------------------------------------------------------------
# P compatibility
# ---------------------------------------------------------------------------


def test_plain_p_datums_do_not_create_q_lifecycle_rows_or_writes():
    n = 200
    step_name = "test.q.p_fast_path.no_lifecycle"
    _register_step(step_name, _make_many_p_multiframespec(n, app_form_id="p.fast.path"))

    api = _api()
    sid = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert len(out["form_fills"]) == n

    st = _state(api, sid)
    assert _runtime_lifecycle_writes(st) == []

    lifecycle = st.get(KEY_DATUM_LIFECYCLE)
    if isinstance(lifecycle, Mapping):
        forms = lifecycle.get("forms")
        assert not forms

    print(
        "[q-complexity-summary] p_fast_path_no_q "
        f"n={n} elapsed={elapsed:.6f}s avg_fill_ms={elapsed * 1000 / n:.3f}"
    )

    assert elapsed < 10.0


def test_plain_p_large_values_are_not_duplicated_into_q_lifecycle_or_q_index():
    n = 24
    giant = "p" * 200_000

    step_name = "test.q.p_fast_path.large_values"
    _register_step(step_name, _make_many_p_multiframespec(n, app_form_id="p.large.values"))

    api = _api()
    sid = _create(api, step_name)

    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": giant}})

    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    assert _runtime_lifecycle_writes(st) == []
    assert not _contains_run(st.get(KEY_RUNTIME_WRITE_INDEX), "p", 1000)

    lifecycle = st.get(KEY_DATUM_LIFECYCLE)
    if isinstance(lifecycle, Mapping):
        assert not _contains_run(lifecycle, "p", 1000)


# ---------------------------------------------------------------------------
# Q correctness
# ---------------------------------------------------------------------------


def test_q_done_creates_lifecycle_row_and_lifecycle_write_only_for_q_datum():
    _register_done_if_structural_widget()

    fs = _make_q_multiframespec(
        1,
        app_form_id="q.done.one",
        widget="test.q.done_if_structural",
    )
    step_name = "test.q.done.one.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D0": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.done.one"]["datums"]["D0"]

    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert row["forced_done"] is False
    assert row["reexplode_count"] == 0
    assert get_engine_form_page_epoch_from_id(st, "q.done.one") >= 1

    writes = _runtime_lifecycle_writes(st)
    assert len(writes) == 1


def test_q_blocked_does_not_commit_bad_fill_and_allows_retry_to_done():
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = dict(q.get("partial_fill") or {})
        if partial.get("value") != "ok":
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "must be ok"},
                "state": {"last": partial.get("value")},
            }
        return {
            "status": "done",
            "message": {"level": "success", "text": ""},
            "state": {"last": "ok"},
        }

    register_datum_widget_v1("test.q.block_then_done", widget, overwrite=True)

    fs = _make_q_multiframespec(
        1,
        app_form_id="q.block.retry",
        widget="test.q.block_then_done",
    )
    step_name = "test.q.block.retry.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D0": {"value": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    assert api.get_session_context(sid)["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D0": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D0"]["value"] == "ok"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.block.retry"]["datums"]["D0"]
    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert row["state"] == {"last": "ok"}


def test_q_reexplode_updates_effective_multiframespec_overlays_then_done_clears_working_overlay():
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {"confirmed": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm value",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.reexplode.once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 8,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"asked": True},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"small": "bag"},
        }

    register_datum_widget_v1("test.q.reexplode.once", widget, overwrite=True)

    fs = _make_q_multiframespec(
        1,
        app_form_id="q.reexplode.once",
        widget="test.q.reexplode.once",
        max_reexplosions=1,
    )
    step_name = "test.q.reexplode.once.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D0": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    st = _state(api, sid)

    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.reexplode.once"]["datums"]["D0"]
    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row["reexplode_count"] == 1
    assert row["current_datum"]["title"] == "Confirm value"
    assert row["current_datum"]["micros"][0]["name"] == "confirm"

    effective = hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
        multiframespec=fs,
        state=st,
        form_id="q.reexplode.once",
    )
    effective_d0 = dict(effective["datums"][0])
    assert effective_d0["title"] == "Confirm value"
    assert effective_d0["micros"][0]["name"] == "confirm"

    overlays = get_latest_engine_form_page_data_read(
        state=st,
        form_id="q.reexplode.once",
        frame_id="F",
        span_id="S0",
    )
    assert overlays["D0"]["confirm"] in {"", "yes"}

    ctx = api.step_session(sid, fill={"D0": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.reexplode.once"]["datums"]["D0"]

    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE
    assert row["state"] == {"confirmed": True}

    overlays = get_latest_engine_form_page_data_read(
        state=st,
        form_id="q.reexplode.once",
        frame_id="F",
        span_id="S0",
    )
    assert overlays == {}


def test_q_max_reexplosions_zero_forces_done_without_structural_loop():
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "micros": [_text_micro("never_needed")],
                "lifecycle": {
                    "widget": "test.q.always_reexplode_forced",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                },
            },
            "state": {"wanted_reexplode": True},
            "message": {"level": "info", "text": "would reexplode"},
            "proc_notes": {"tiny": "x"},
        }

    register_datum_widget_v1("test.q.always_reexplode_forced", widget, overwrite=True)

    fs = _make_q_multiframespec(
        1,
        app_form_id="q.force.done",
        widget="test.q.always_reexplode_forced",
        max_reexplosions=0,
        max_proc_notes=1,
    )
    step_name = "test.q.force.done.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D0": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.force.done"]["datums"]["D0"]

    assert row["status"] == DATUM_LIFECYCLE_STATUS_FORCED_DONE
    assert row["forced_done"] is True
    assert row["reexplode_count"] == 0
    assert row["state"] == {"wanted_reexplode": True}


def test_q_proc_notes_and_messages_windows_are_bounded_under_repeated_reexplodes():
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        re_count = int(q.get("reexplode_count", 0) or 0)
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro(f"v{re_count}")],
                "lifecycle": {
                    "widget": "test.q.always_reexplode.window",
                    "max_reexplosions": 10,
                    "max_proc_notes": 2,
                    "max_messages": 3,
                },
            },
            "state": {"n": re_count + 1},
            "message": {"level": "info", "text": f"again-{re_count}"},
            "proc_notes": {"payload": "b" * 50_000, "i": re_count},
        }

    register_datum_widget_v1("test.q.always_reexplode.window", widget, overwrite=True)

    fs = {
        "app_form_id": "q.window",
        "datums": [
            {
                "id": "D",
                "title": "D",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.always_reexplode.window",
                    "max_reexplosions": 10,
                    "max_proc_notes": 2,
                    "max_messages": 3,
                },
            }
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["D"]}]}],
    }
    step_name = "test.q.window.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    field_name = "value"
    for i in range(5):
        ctx = api.step_session(sid, fill={"D": {field_name: "x"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        field_name = f"v{i}"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"]["q.window"]["datums"]["D"]

    assert len(row["proc_notes"]) <= 2
    assert len(row["messages"]) <= 3
    assert row["reexplode_count"] == 5


# ---------------------------------------------------------------------------
# Q complexity and query/index discipline
# ---------------------------------------------------------------------------


def test_q_reexplode_large_proc_notes_is_state_only_not_runtime_index_or_query_payload():
    giant = "x" * 1_000_000

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
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
                    "widget": "test.q.reexplode.large_proc_notes",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "state": {"small": True},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"giant": giant},
        }

    register_datum_widget_v1("test.q.reexplode.large_proc_notes", widget, overwrite=True)

    n = 80
    fs = _make_q_multiframespec(
        n,
        app_form_id="q.large.proc_notes",
        widget="test.q.reexplode.large_proc_notes",
        max_reexplosions=1,
        max_proc_notes=1,
    )
    step_name = "test.q.large.proc_notes.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)

    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "x", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "x", 1000)

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
    assert not _contains_run(q, "x", 1000)

    print(
        "[q-complexity-summary] q_large_proc_notes_reexplode_then_done "
        f"n={n} manual_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f}"
    )

    assert elapsed < 20.0


def test_same_session_many_prior_forms_do_not_make_current_q_read_scan_history():
    _register_done_if_structural_widget("test.q.current_read.done")

    def _one_p_multiframespec(*, datum_id: str, app_form_id: str) -> Dict[str, Any]:
        return {
            "app_form_id": app_form_id,
            "datums": [
                {
                    "id": datum_id,
                    "title": datum_id,
                    "micros": [_text_micro()],
                }
            ],
            "frames": [
                {
                    "id": "F",
                    "spans": [{"id": "S", "owns": [datum_id]}],
                }
            ],
        }

    def _one_q_target_multiframespec(
        *,
        datum_id: str,
        app_form_id: str,
    ) -> Dict[str, Any]:
        return {
            "app_form_id": app_form_id,
            "datums": [
                {
                    "id": datum_id,
                    "title": datum_id,
                    "micros": [_text_micro()],
                    "lifecycle": {
                        "widget": "test.q.current_read.done",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 4,
                    },
                }
            ],
            "frames": [
                {
                    "id": "F",
                    "spans": [{"id": "S", "owns": [datum_id]}],
                }
            ],
        }

    def run(form_count: int) -> float:
        api = _api()
        step_names: List[str] = []

        for i in range(form_count):
            datum_id = f"P{i}"
            fs = _one_p_multiframespec(
                datum_id=datum_id,
                app_form_id=f"q.history.unrelated.{form_count}.{i}",
            )
            step_name = f"test.q.history.unrelated.{form_count}.{i}"
            _register_step(step_name, fs)
            step_names.append(step_name)

        target_datum_id = f"Q_TARGET_{form_count}"
        target_fs = _one_q_target_multiframespec(
            datum_id=target_datum_id,
            app_form_id=f"q.history.target.{form_count}",
        )
        target_step = f"test.q.history.target.{form_count}"
        _register_step(target_step, target_fs)
        step_names.append(target_step)

        sid = _create_manifest(api, step_names)

        for i in range(form_count):
            ctx = api.step_session(sid, fill={f"P{i}": {"value": f"x{i}"}})
            assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        ctx = api.get_session_context(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert ctx["form_id"] == f"q.history.target.{form_count}"
        assert ctx["datum_widgets_on_this_span"] == [target_datum_id]

        return _median(lambda: api.get_session_context(sid), repeats=10)

    small = run(10)
    large = run(120)

    ratio = large / max(small, 1e-9)

    print(
        "[q-complexity-summary] same_session_history_current_q_read "
        f"small={small:.8f}s large={large:.8f}s ratio={ratio:.3f}"
    )

    assert large < max(0.08, small * 12.0)


def test_many_q_done_datums_scale_linearly_and_lifecycle_writes_are_one_per_q_manual_fill():
    _register_done_if_structural_widget("test.q.many.done")

    n = 160
    fs = _make_q_multiframespec(
        n,
        app_form_id="q.many.done.linear",
        widget="test.q.many.done",
    )
    step_name = "test.q.many.done.linear.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    writes = _runtime_lifecycle_writes(st, max_results=n + 20)

    assert len(writes) == n

    print(
        "[q-complexity-summary] q_many_done_linear "
        f"n={n} elapsed={elapsed:.6f}s avg_fill_ms={elapsed * 1000 / n:.3f} "
        f"lifecycle_writes={len(writes)}"
    )

    assert elapsed < 20.0


def test_q_reexplode_undo_restores_only_previous_lifecycle_tick_and_stays_bounded():
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {"done": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.undo.reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {"asked": True},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"payload": "u" * 200_000},
        }

    register_datum_widget_v1("test.q.undo.reexplode_once", widget, overwrite=True)

    n = 50
    fs = _make_q_multiframespec(
        n,
        app_form_id="q.undo.reexplode",
        widget="test.q.undo.reexplode_once",
        max_reexplosions=1,
        max_proc_notes=1,
    )
    step_name = "test.q.undo.reexplode.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"

    t0 = time.perf_counter()
    for _ in range(20):
        api.undo_last_step(sid)
    undo_elapsed = time.perf_counter() - t0

    st = _state(api, sid)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "u", 1000)

    print(
        "[q-complexity-summary] q_reexplode_undo_bounded "
        f"n={n} undo20={undo_elapsed:.6f}s"
    )

    assert undo_elapsed < 10.0


def test_undo_depth_is_bounded_for_plain_p_manual_fills():
    n = 120
    step_name = "test.q.undo.depth.p"
    _register_step(step_name, _make_many_p_multiframespec(n, app_form_id="p.undo.depth"))

    api = _api()
    sid = _create(api, step_name)

    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})

    assert api.get_session_context(sid)["kind"] == "ATCOMPLETION"

    t0 = time.perf_counter()
    for _ in range(40):
        api.undo_last_step(sid)
    undo_elapsed = time.perf_counter() - t0

    ctx = api.get_session_context(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    print(
        "[q-complexity-summary] p_undo_depth_bounded "
        f"n={n} undo40={undo_elapsed:.6f}s avg_undo_ms={undo_elapsed * 1000 / 40:.3f}"
    )

    assert undo_elapsed < 10.0


def test_redo_is_bounded_when_exercised_at_each_undo_stop():
    """
    Redo API contract test.

    Public redo replays bounded public manual actions. The stable contract is:
    after a public undo exposes a redoable manual stop, one redo replays that
    action. Alternating undo/redo measures the actual public redo path without
    assuming that clients can batch-consume an arbitrary deep redo queue after
    many independent public undos.
    """

    n = 80
    step_name = "test.q.redo.alternating.p"
    _register_step(step_name, _make_many_p_multiframespec(n, app_form_id="p.redo.alternating"))

    api = _api()
    sid = _create(api, step_name)

    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})

    assert api.get_session_context(sid)["kind"] == "ATCOMPLETION"

    undo_times = []
    redo_times = []

    for _ in range(25):
        t0 = time.perf_counter()
        api.undo_last_step(sid)
        undo_times.append(time.perf_counter() - t0)

        assert api.get_session_context(sid)["kind"] == "MANUALFILLNEEDEDSTEP"

        t0 = time.perf_counter()
        api.redo_last_step(sid)
        redo_times.append(time.perf_counter() - t0)

        assert api.get_session_context(sid)["kind"] == "ATCOMPLETION"

    undo_elapsed = sum(undo_times)
    redo_elapsed = sum(redo_times)

    print(
        "[q-complexity-summary] p_redo_alternating_bounded "
        f"undo25={undo_elapsed:.6f}s redo25={redo_elapsed:.6f}s "
        f"avg_undo_ms={undo_elapsed * 1000 / 25:.3f} "
        f"avg_redo_ms={redo_elapsed * 1000 / 25:.3f}"
    )

    assert undo_elapsed < 10.0
    assert redo_elapsed < 10.0


# ---------------------------------------------------------------------------
# Task E: touched-datum-only lifecycle evaluation inside multi-datum spans
# ---------------------------------------------------------------------------


def test_q_manual_submit_evaluates_only_touched_q_datum_not_untouched_q_siblings():
    """
    Task E regression.

    A single span owns many Q datums. Submitting D0 must call only D0's widget.
    Untouched Q siblings must not be evaluated merely because they are pending
    in the same span.
    """

    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = _q_datum_id(q)
        calls.append(datum_id)

        if not bool(q.get("structurally_satisfied")):
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "missing"},
                "state": {"called": datum_id},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": ""},
            "state": {"called": datum_id},
        }

    register_datum_widget_v1("test.q.task_e.touched_only", widget, overwrite=True)

    n = 20
    fs = {
        "app_form_id": "q.task_e.touched_only",
        "datums": [
            {
                "id": f"D{i}",
                "title": f"D{i}",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.touched_only",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            }
            for i in range(n)
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S_ALL",
                        "owns": [f"D{i}" for i in range(n)],
                    }
                ],
            }
        ],
    }

    step_name = "test.q.task_e.touched_only.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"D0": {"value": "v0"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == ["D0"]

    st = _state(api, sid)
    rows = st[KEY_DATUM_LIFECYCLE]["forms"]["q.task_e.touched_only"]["datums"]

    assert set(rows) == {"D0"}
    assert rows["D0"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    # Runtime write query is a lightweight preview. Do not assert full payload
    # keys such as form_id/field_id here; those are intentionally omitted from
    # the preview shape.
    writes = _runtime_lifecycle_writes(st)
    assert len(writes) == 1


def test_q_reexplode_with_plain_p_sibling_preserves_working_fill_and_does_not_require_resubmit():
    """
    Task E regression.

    One span owns Q + plain P.

    First submit sends both A and B:
    - A is Q and reexplodes.
    - B is plain P and structurally valid.

    The first tick must reexplode only A, preserve B's accepted working fill,
    and keep the same logical span active.

    Second submit sends only A's confirmation. B must not need resubmission.
    The span should complete and commit both A and B.
    """

    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = _q_datum_id(q)
        calls.append(datum_id)

        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {"confirmed": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm A",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.task_e.reexplode_with_p_sibling",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"asked": True},
            "message": {"level": "info", "text": "confirm A"},
            "proc_notes": {"small": "ok"},
        }

    register_datum_widget_v1(
        "test.q.task_e.reexplode_with_p_sibling",
        widget,
        overwrite=True,
    )

    fs = {
        "app_form_id": "q.task_e.reexplode_with_p_sibling",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.reexplode_with_p_sibling",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S_AB",
                        "owns": ["A", "B"],
                    }
                ],
            }
        ],
    }

    step_name = "test.q.task_e.reexplode_with_p_sibling.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "draft"},
            "B": {"value": "plain-b"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == ["A"]

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"][
        "q.task_e.reexplode_with_p_sibling"
    ]["datums"]["A"]

    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row["reexplode_count"] == 1

    overlays = get_latest_engine_form_page_data_read(
        state=st,
        form_id="q.task_e.reexplode_with_p_sibling",
        frame_id="F",
        span_id="S_AB",
    )

    assert overlays["A"]["confirm"] in {"", "yes"}

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == ["A", "A"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "plain-b"

    st = _state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"][
        "q.task_e.reexplode_with_p_sibling"
    ]["datums"]["A"]
    assert row["status"] == DATUM_LIFECYCLE_STATUS_DONE


def test_task_e_partial_multi_datum_span_undo_redo_restores_touched_only_progress():
    """
    Task E undo/redo regression.

    In a multi-datum span, a partial accepted submit should be a public tape
    action. Undo removes that partial progress. Redo reapplies it. Untouched Q
    siblings must not be evaluated during either path.

    The lifecycle container may remain allocated after undo; the invariant is
    that the undone datum is no longer done/satisfied and redo replays only the
    original touched datum.
    """

    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = _q_datum_id(q)
        calls.append(datum_id)

        if not bool(q.get("structurally_satisfied")):
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "missing"},
                "state": {"called": datum_id},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": ""},
            "state": {"called": datum_id},
        }

    register_datum_widget_v1("test.q.task_e.undo_redo_touched_only", widget, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.undo_redo_touched_only",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.undo_redo_touched_only",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.undo_redo_touched_only",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S_AB",
                        "owns": ["A", "B"],
                    }
                ],
            }
        ],
    }

    step_name = "test.q.task_e.undo_redo_touched_only.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "a"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == ["A"]

    st = _state(api, sid)
    rows = st[KEY_DATUM_LIFECYCLE]["forms"][
        "q.task_e.undo_redo_touched_only"
    ]["datums"]
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    api.undo_last_step(sid)

    ctx = api.get_session_context(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["form_id"] == "q.task_e.undo_redo_touched_only"

    st = _state(api, sid)
    forms = st.get(KEY_DATUM_LIFECYCLE, {}).get("forms", {})
    form = forms.get("q.task_e.undo_redo_touched_only", {})
    rows = form.get("datums", {})

    # Undo may preserve the lifecycle form/row container for bounded structural
    # reuse, but the previously accepted A row must no longer be done.
    if "A" in rows:
        assert rows["A"].get("status") != DATUM_LIFECYCLE_STATUS_DONE

    api.redo_last_step(sid)

    ctx = api.get_session_context(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    assert calls == ["A", "A"]

    st = _state(api, sid)
    rows = st[KEY_DATUM_LIFECYCLE]["forms"][
        "q.task_e.undo_redo_touched_only"
    ]["datums"]
    assert set(rows) == {"A"}
    assert rows["A"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    ctx = api.step_session(sid, fill={"B": {"value": "b"}})
    assert ctx["kind"] == "ATCOMPLETION"

    assert calls == ["A", "A", "B"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "a"
    assert out["form_fills"]["B"]["value"] == "b"

# ---------------------------------------------------------------------------
# Optional crazy diagnostic + Task E win proof
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not RUN_Q_CRAZY, reason="set APP_TABLE_Q_COMPLEXITY_CRAZY=1")
def test_crazy_many_q_datums_reexplode_once_diagnostic():
    """
    Optional all-touched diagnostic.

    This is intentionally the expensive case.

    Every Q datum is manually submitted, every Q datum reexplodes once, and
    every Q datum is then confirmed. Therefore this scenario should scale with
    the number of datums:

        work ~= O(number_of_touched_datums)
        writes == 2 * n
        manual_ticks == 2 * n

    Task E does not make this case constant-time, because all datums genuinely
    changed. This test is skipped by default because it is a stress diagnostic,
    not a normal correctness gate.
    """

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
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
                **dict(q["datum"]),
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.crazy.reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"small": "ok"},
        }

    register_datum_widget_v1("test.q.crazy.reexplode_once", widget, overwrite=True)

    n = int(os.environ.get("APP_TABLE_Q_COMPLEXITY_N", "500"))

    step_name = "test.q.crazy.reexplode_once.step"
    _register_step(
        step_name,
        _make_q_multiframespec(
            n,
            app_form_id=f"q.crazy.reexplode.{n}",
            widget="test.q.crazy.reexplode_once",
            max_reexplosions=1,
            max_proc_notes=1,
        ),
    )

    api = _api()
    sid = _create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": "x"}})
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    st = _state(api, sid)
    writes = _runtime_lifecycle_writes(st, max_results=10_000_000)

    # Reexplode + done for every touched Q datum.
    assert len(writes) == 2 * n

    print(
        "[q-complexity-summary] crazy_all_touched_q_reexplode_once "
        f"n={n} manual_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f} "
        f"lifecycle_writes={len(writes)}"
    )


def test_task_e_crazy_wide_span_one_touched_q_datum_does_not_scale_widget_work_or_writes():
    """
    Task E win proof.

    This uses the same kind of crazy-wide Q surface as the skipped diagnostic,
    but changes the important variable:

        the span owns many Q datums,
        but the submit touches only D0.

    Before Task E, manual IO walked/evaluated pending span fields. In a span
    owning D0..D999, this one-field submit:

        {"D0": {"value": "x"}}

    could still invoke Q widgets for D1..D999 merely because they were pending
    siblings. That made one user's tiny edit scale with the whole span width and
    could create sibling lifecycle rows, writes, messages, proc_notes, and memory
    pressure.

    After Task E, Q evaluation is driven by touched datums, not all pending
    datums:

        work ~= O(number_of_touched_datums)
        writes == 1
        lifecycle_rows == {"D0"}

    The span remains incomplete because D1..D999 are still pending, but they stay
    inert. They are not evaluated, mutated, written, or materialized.
    """

    n = int(os.environ.get("APP_TABLE_Q_ONE_TOUCHED_N", "1000"))
    giant = "z" * 250_000

    calls: List[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum_id = _q_datum_id(q)
        calls.append(datum_id)

        # Make accidental sibling evaluation both expensive and visible.
        # Fixed behavior stores this only for D0.
        # Pre-fix behavior would create this for every accidentally evaluated
        # pending sibling.
        return {
            "status": "reexplode",
            "datum": {
                **dict(q["datum"]),
                "title": f"Confirm {datum_id}",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.task_e.one_touched_crazy",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"called": datum_id},
            "message": {"level": "info", "text": f"confirm {datum_id}"},
            "proc_notes": {"giant": giant},
        }

    register_datum_widget_v1("test.q.task_e.one_touched_crazy", widget, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.one_touched_crazy",
        "datums": [
            {
                "id": f"D{i}",
                "title": f"D{i}",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.one_touched_crazy",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            }
            for i in range(n)
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S_ALL",
                        "owns": [f"D{i}" for i in range(n)],
                    }
                ],
            }
        ],
    }

    step_name = "test.q.task_e.one_touched_crazy.step"
    _register_step(step_name, fs)

    api = _api()
    sid = _create(api, step_name)

    t0 = time.perf_counter()
    ctx = api.step_session(sid, fill={"D0": {"value": "x"}})
    elapsed = time.perf_counter() - t0

    # The span is intentionally still incomplete because only D0 was touched.
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    # This is the hard proof. The pre-Task-E bug would call many/all siblings.
    assert calls == ["D0"]

    st = _state(api, sid)

    rows = st[KEY_DATUM_LIFECYCLE]["forms"]["q.task_e.one_touched_crazy"]["datums"]

    # Untouched sibling Q datums remain inert: no rows, no statuses, no proc_notes.
    assert set(rows) == {"D0"}

    row = rows["D0"]
    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row["reexplode_count"] == 1
    assert row["current_datum"]["micros"][0]["name"] == "confirm"
    assert row["proc_notes"][-1]["giant"] == giant

    writes = _runtime_lifecycle_writes(st, max_results=n + 10)

    # One touched datum produced one lifecycle write.
    # Pre-fix sibling evaluation would inflate this toward n.
    assert len(writes) == 1

    # The large payload may exist in lifecycle state for the one touched datum,
    # but it must not be duplicated into the runtime write index or query preview.
    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "z", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "z", 1000)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": n + 10,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) == 1
    assert not _contains_run(q, "z", 1000)

    print(
        "[q-complexity-summary] task_e_one_touched_crazy_wide_span "
        f"n={n} touched=1 calls={len(calls)} lifecycle_writes={len(writes)} "
        f"elapsed={elapsed:.6f}s"
    )

    assert elapsed < 5.0