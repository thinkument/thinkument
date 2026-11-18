from __future__ import annotations

"""
Datum lifecycle class-adapter complexity tests.

This file is intentionally separate from the main class-adapter behavior,
inheritance, controller, and kernel integration tests.

Class Adapter Complexity Addendum
=================================

This addendum imports the lower Q lifecycle complexity contract into the
class-adapter surface.

Lower platform guarantees already proved elsewhere:
    - plain P datums do not enter Q machinery;
    - Q machinery runs only for datums with datum["lifecycle"];
    - touched-datum filtering prevents pending siblings from being evaluated;
    - runtime write index/query previews do not duplicate large lifecycle values;
    - lifecycle messages/proc_notes/state windows are capped by lower policy;
    - undo/redo operate over bounded public tape actions;
    - same-session current-form reads do not scan unrelated historical forms.

This addendum proves the class adapter preserves those properties.

The adapter adds only this per lifecycle invocation:
    1. instantiate one Python object;
    2. copy q["state"] into self._state;
    3. build one small ergonomic input envelope:
           position, fill_data, limits, stats, signal
    4. dispatch one method:
           _on_mount / _on_fill / @signal_catcher
    5. normalize True or Reexplode(...) into the existing platform result shape.

It does not add:
    - a new runtime storage bucket;
    - a new write index path;
    - proc_notes;
    - blocked status;
    - raw event payloads beyond message-shaped event payloads;
    - sibling-datum scans;
    - history scans;
    - hidden copies of large fills/state/messages into runtime query previews.

Therefore runtime work remains:

    O(number of lifecycle datums actually invoked)

not:

    O(number of datums in the program)
    O(number of datums in the span)
    O(number of prior forms)
    O(size of unrelated lifecycle state)

The only data that can scale is data the widget author deliberately writes:
    - self attributes -> lifecycle state;
    - messages through self.message(...);
    - Reexplode datum/fill/prefill surfaces.

The platform caps remain the governing controls:
    - max_reexplosions
    - max_messages
    - runtime write query max_results
    - manual IO payload caps
    - session storage/redo caps

These tests deliberately use class widgets, not raw Q functions, to prove the
adapter inherits the lower complexity wins without reintroducing old bottlenecks.
"""

import os
import statistics
import time
from typing import Any, Dict, Iterable, Mapping, List

import pytest

from __datomatonTM import (
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_REEXPLODED,
    KEY_DATUM_LIFECYCLE,
)
from _thinkprogram.thinkwidgetTM import (
    ADAPTER_RESERVED_STATE_KEY,
    DatumLifecycleWidget,
    Reexplode,
    thinkwidgetTM_config
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


RUN_ADAPTER_COMPLEXITY_CRAZY = (
    os.environ.get("APP_TABLE_CLASS_ADAPTER_COMPLEXITY_CRAZY", "0") == "1"
)


ADAPTER_COMPLEXITY_CALLS: List[str] = []


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _text_micro(
    name: str = "value",
    *,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


def _register_step(
    name: str,
    multiframespec: Mapping[str, Any],
) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _adapter_complexity_state(api: Any, sid: str) -> Dict[str, Any]:
    return api._get(sid).state


def _adapter_complexity_runtime_lifecycle_writes(
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


def _adapter_complexity_contains_run(
    obj: Any,
    ch: str,
    n: int,
    *,
    max_nodes: int = 100_000,
) -> bool:
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


def _adapter_complexity_median(fn, repeats: int = 5) -> float:
    vals = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        vals.append(time.perf_counter() - t0)
    return statistics.median(vals)


def _adapter_complexity_create_manifest(
    api: Any,
    step_names: Iterable[str],
) -> str:
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": f"class_adapter_complexity_step_{i}",
                "step_fn": step_name,
                "fn_args": {},
            }
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


def _adapter_complexity_create(
    api: Any,
    step_name: str,
) -> str:
    return _adapter_complexity_create_manifest(api, [step_name])


def _adapter_complexity_q_multiframespec(
    n: int,
    *,
    app_form_id: str,
    widget_name: str,
    wide_span: bool = False,
    max_reexplosions: int = 1,
    max_messages: int = 8,
    mount_explode: bool = False,
) -> Dict[str, Any]:
    datums = [
        {
            "id": f"D{i}",
            "title": f"D{i}",
            "micros": [_text_micro()],
            "lifecycle": {
                "widget": widget_name,
                "mount_explode": bool(mount_explode),
                "max_reexplosions": max_reexplosions,
                "max_messages": max_messages,
                "max_proc_notes": 0,
            },
        }
        for i in range(n)
    ]

    if wide_span:
        spans = [
            {
                "id": "S_ALL",
                "owns": [f"D{i}" for i in range(n)],
            }
        ]
    else:
        spans = [
            {
                "id": f"S{i}",
                "owns": [f"D{i}"],
            }
            for i in range(n)
        ]

    return {
        "app_form_id": app_form_id,
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "spans": spans,
            }
        ],
    }


@thinkwidgetTM_config("test.adapter.complexity.done", overwrite=True)
class AdapterComplexityDoneWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        ADAPTER_COMPLEXITY_CALLS.append(f"mount:{position['datum_id']}")
        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        ADAPTER_COMPLEXITY_CALLS.append(position["datum_id"])
        assert set(limits) == {"max_reexplosions", "max_messages"}
        assert set(stats) == {"reexplode_count", "num_messages"}

        if not fill_data["shell_satisfaction_check"]:
            raise ValueError("class adapter complexity widget expected valid fill")

        self.done_value = dict(fill_data["current_fills"])
        self.message("success", f"done {position['datum_id']}")
        return True


@thinkwidgetTM_config("test.adapter.complexity.large_state", overwrite=True)
class AdapterComplexityLargeStateWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        raise AssertionError("mount should not run in this complexity test")

    def _on_fill(self, signal, position, fill_data, limits, stats):
        ADAPTER_COMPLEXITY_CALLS.append(position["datum_id"])
        self.large_private_state = "x" * 1_000_000
        self.small_marker = position["datum_id"]
        self.message("info", "large state written once")
        return True


@thinkwidgetTM_config("test.adapter.complexity.reexplode_window", overwrite=True)
class AdapterComplexityReexplodeWindowWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        raise AssertionError("mount should not run in this complexity test")

    def _on_fill(self, signal, position, fill_data, limits, stats):
        ADAPTER_COMPLEXITY_CALLS.append(position["datum_id"])

        re_count = int(stats["reexplode_count"])
        self.n = re_count + 1
        self.message("info", f"again-{re_count}")

        return Reexplode(
            next_fill_shell={
                **dict(fill_data["fill_shell"]),
                "micros": [_text_micro(f"v{re_count}")],
                "lifecycle": {
                    "widget": "test.adapter.complexity.reexplode_window",
                    "mount_explode": False,
                    "max_reexplosions": 10,
                    "max_messages": 3,
                    "max_proc_notes": 0,
                },
            },
            pre_computed_fills={f"v{re_count}": ""},
        )


@thinkwidgetTM_config("test.adapter.complexity.reexplode_once", overwrite=True)
class AdapterComplexityReexplodeOnceWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        raise AssertionError("mount should not run in this complexity test")

    def _on_fill(self, signal, position, fill_data, limits, stats):
        ADAPTER_COMPLEXITY_CALLS.append(position["datum_id"])
        current = dict(fill_data["current_fills"])

        if "confirm" in current:
            self.confirmed = True
            self.message("success", "confirmed")
            return True

        self.asked = True
        self.message("info", "confirm")
        return Reexplode(
            next_fill_shell={
                **dict(fill_data["fill_shell"]),
                "title": f"Confirm {position['datum_id']}",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.adapter.complexity.reexplode_once",
                    "mount_explode": False,
                    "max_reexplosions": 1,
                    "max_messages": 4,
                    "max_proc_notes": 0,
                },
            },
            pre_computed_fills={"confirm": ""},
            prefill_hints={"confirm": "yes"},
        )


def test_adapter_complexity_many_done_datums_are_linear_and_one_write_per_touched_q():
    """
    The adapter does not change lower Q scaling.

    Each manual tick touches exactly one class-backed Q datum. Therefore:
        calls == n
        lifecycle writes == n
        runtime work ~= O(n touched datums)
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = 160
    form_id = "adapter.complexity.many.done.linear"
    step_name = "adapter.complexity.many.done.linear.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.done",
            wide_span=False,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert ADAPTER_COMPLEXITY_CALLS == [f"D{i}" for i in range(n)]

    st = _adapter_complexity_state(api, sid)
    writes = _adapter_complexity_runtime_lifecycle_writes(
        st,
        max_results=n + 20,
    )
    assert len(writes) == n

    rows = st[KEY_DATUM_LIFECYCLE]["forms"][form_id]["datums"]
    assert len(rows) == n
    assert all(row["status"] == DATUM_LIFECYCLE_STATUS_DONE for row in rows.values())

    print(
        "[class-adapter-complexity-summary] many_done_linear "
        f"n={n} elapsed={elapsed:.6f}s avg_fill_ms={elapsed * 1000 / n:.3f} "
        f"calls={len(ADAPTER_COMPLEXITY_CALLS)} lifecycle_writes={len(writes)}"
    )

    assert elapsed < 20.0


def test_adapter_complexity_wide_span_one_touched_datum_does_not_scan_or_eval_siblings():
    """
    The most important inherited lower-platform win.

    One span owns many class-backed Q datums. A submit touches only D0.
    The adapter must not cause D1..Dn to instantiate, dispatch, write messages,
    create lifecycle rows, or create runtime lifecycle writes.

    This proves the class abstraction preserves Task-E touched-datum-only work.
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = int(os.environ.get("APP_TABLE_CLASS_ADAPTER_WIDE_SPAN_N", "1000"))
    form_id = "adapter.complexity.wide.one_touched"
    step_name = "adapter.complexity.wide.one_touched.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.done",
            wide_span=True,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    t0 = time.perf_counter()
    ctx = api.step_session(sid, fill={"D0": {"value": "v0"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ADAPTER_COMPLEXITY_CALLS == ["D0"]

    st = _adapter_complexity_state(api, sid)
    rows = st[KEY_DATUM_LIFECYCLE]["forms"][form_id]["datums"]

    assert set(rows) == {"D0"}
    assert rows["D0"]["status"] == DATUM_LIFECYCLE_STATUS_DONE

    writes = _adapter_complexity_runtime_lifecycle_writes(
        st,
        max_results=n + 10,
    )
    assert len(writes) == 1

    print(
        "[class-adapter-complexity-summary] wide_span_one_touched "
        f"n={n} touched=1 elapsed={elapsed:.6f}s "
        f"calls={len(ADAPTER_COMPLEXITY_CALLS)} lifecycle_writes={len(writes)}"
    )

    assert elapsed < 5.0


def test_adapter_complexity_large_self_state_is_not_duplicated_into_runtime_index_or_query_preview():
    """
    The adapter maps self attributes to result["state"].

    Therefore deliberately large self state can exist in the lifecycle row.
    The adapter must not additionally duplicate it into:
        - runtime write index;
        - runtime lifecycle query previews;
        - emitted message payloads.

    This inherits the lower runtime-index discipline.
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = 40
    form_id = "adapter.complexity.large.state"
    step_name = "adapter.complexity.large.state.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.large_state",
            wide_span=False,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert ADAPTER_COMPLEXITY_CALLS == [f"D{i}" for i in range(n)]

    st = _adapter_complexity_state(api, sid)

    lifecycle = st[KEY_DATUM_LIFECYCLE]
    assert _adapter_complexity_contains_run(lifecycle, "x", 1000)

    runtime_index = st[KEY_RUNTIME_WRITE_INDEX]
    assert not _adapter_complexity_contains_run(runtime_index, "x", 1000)

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
    assert not _adapter_complexity_contains_run(q, "x", 1000)

    drained = api.drain_session_events(sid)
    assert drained
    assert not _adapter_complexity_contains_run(drained, "x", 1000)

    print(
        "[class-adapter-complexity-summary] large_self_state_not_indexed "
        f"n={n} elapsed={elapsed:.6f}s avg_tick_ms={elapsed * 1000 / n:.3f}"
    )

    assert elapsed < 20.0


def test_adapter_complexity_reexplode_message_window_is_bounded_and_proc_notes_absent():
    """
    The adapter does not expose proc_notes and authors messages only through
    self.message(...).

    Lower platform max_messages still bounds carried lifecycle messages even
    under repeated class-authored reexplodes.
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    form_id = "adapter.complexity.reexplode.window"
    step_name = "adapter.complexity.reexplode.window.step"

    fs = {
        "app_form_id": form_id,
        "datums": [
            {
                "id": "D",
                "title": "D",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.adapter.complexity.reexplode_window",
                    "mount_explode": False,
                    "max_reexplosions": 10,
                    "max_messages": 3,
                    "max_proc_notes": 0,
                },
            }
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["D"]}]}],
    }

    _register_step(step_name, fs)

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    field_name = "value"
    for i in range(5):
        ctx = api.step_session(sid, fill={"D": {field_name: "x"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        field_name = f"v{i}"

    st = _adapter_complexity_state(api, sid)
    row = st[KEY_DATUM_LIFECYCLE]["forms"][form_id]["datums"]["D"]

    assert row["status"] == DATUM_LIFECYCLE_STATUS_REEXPLODED
    assert row["reexplode_count"] == 5
    assert row["state"]["n"] == 5
    assert len(row["messages"]) <= 3
    assert row.get("proc_notes") in (None, [])

    reserved = row["state"][ADAPTER_RESERVED_STATE_KEY]
    assert reserved["last_precomputed_fills"] == {"v4": ""}

    assert ADAPTER_COMPLEXITY_CALLS == ["D"] * 5


def test_adapter_complexity_reexplode_then_done_is_two_writes_per_touched_datum_only():
    """
    Every touched datum genuinely does two lifecycle evaluations:
        first fill -> reexplode
        confirm    -> done

    Therefore writes == 2 * n and calls == 2 * n.

    This test proves the adapter does not add hidden extra lifecycle writes
    beyond the lower platform's reexplode/done transitions.
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = 80
    form_id = "adapter.complexity.reexplode.then.done"
    step_name = "adapter.complexity.reexplode.then.done.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.reexplode_once",
            wide_span=False,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        ctx = api.step_session(sid, fill={f"D{i}": {"value": "draft"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(ADAPTER_COMPLEXITY_CALLS) == 2 * n

    st = _adapter_complexity_state(api, sid)
    writes = _adapter_complexity_runtime_lifecycle_writes(
        st,
        max_results=2 * n + 20,
    )
    assert len(writes) == 2 * n

    rows = st[KEY_DATUM_LIFECYCLE]["forms"][form_id]["datums"]
    assert len(rows) == n
    assert all(row["status"] == DATUM_LIFECYCLE_STATUS_DONE for row in rows.values())

    print(
        "[class-adapter-complexity-summary] reexplode_then_done "
        f"n={n} manual_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f} "
        f"calls={len(ADAPTER_COMPLEXITY_CALLS)} lifecycle_writes={len(writes)}"
    )

    assert elapsed < 20.0


def test_adapter_complexity_current_form_reads_do_not_scale_with_prior_unrelated_forms():
    """
    The adapter does not create a new current-form read path.

    This mirrors the lower Q history-read discipline:
        many prior completed forms
        then one current class-backed Q form

    Repeated get_session_context on the current form should not scale
    catastrophically with unrelated historical forms.
    """

    def _one_plain_form(*, datum_id: str, app_form_id: str) -> Dict[str, Any]:
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

    def _run(form_count: int) -> float:
        ADAPTER_COMPLEXITY_CALLS.clear()

        api = _api()
        step_names: List[str] = []

        for i in range(form_count):
            datum_id = f"P{i}"
            step_name = f"adapter.complexity.history.p.{form_count}.{i}"
            _register_step(
                step_name,
                _one_plain_form(
                    datum_id=datum_id,
                    app_form_id=f"adapter.complexity.history.p.{form_count}.{i}",
                ),
            )
            step_names.append(step_name)

        target_datum_id = f"Q_TARGET_{form_count}"
        target_step = f"adapter.complexity.history.target.{form_count}"
        target_form_id = f"adapter.complexity.history.target.{form_count}"

        _register_step(
            target_step,
            {
                "app_form_id": target_form_id,
                "datums": [
                    {
                        "id": target_datum_id,
                        "title": target_datum_id,
                        "micros": [_text_micro()],
                        "lifecycle": {
                            "widget": "test.adapter.complexity.done",
                            "mount_explode": False,
                            "max_reexplosions": 1,
                            "max_messages": 4,
                            "max_proc_notes": 0,
                        },
                    }
                ],
                "frames": [
                    {
                        "id": "F",
                        "spans": [{"id": "S", "owns": [target_datum_id]}],
                    }
                ],
            },
        )
        step_names.append(target_step)

        sid = _adapter_complexity_create_manifest(api, step_names)

        for i in range(form_count):
            ctx = api.step_session(sid, fill={f"P{i}": {"value": f"x{i}"}})
            assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        ctx = api.get_session_context(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert ctx["form_id"] == target_form_id
        assert ctx["datum_widgets_on_this_span"] == [target_datum_id]

        return _adapter_complexity_median(
            lambda: api.get_session_context(sid),
            repeats=10,
        )

    small = _run(10)
    large = _run(120)

    ratio = large / max(small, 1e-9)

    print(
        "[class-adapter-complexity-summary] current_form_read_history "
        f"small={small:.8f}s large={large:.8f}s ratio={ratio:.3f}"
    )

    assert large < max(0.08, small * 12.0)


def test_adapter_complexity_undo_redo_replays_only_public_tape_action():
    """
    Undo/redo remains the lower public tape operation.

    The adapter contributes no extra redo queue or hidden history. Replaying
    one class-backed Q action should invoke exactly the same handler again and
    restore the same lifecycle row state.
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = 40
    form_id = "adapter.complexity.undo.redo"
    step_name = "adapter.complexity.undo.redo.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.done",
            wide_span=False,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": f"v{i}"}})

    assert api.get_session_context(sid)["kind"] == "ATCOMPLETION"
    assert len(ADAPTER_COMPLEXITY_CALLS) == n

    undo_times = []
    redo_times = []

    for _ in range(20):
        t0 = time.perf_counter()
        ctx = api.undo_last_step(sid)
        undo_times.append(time.perf_counter() - t0)

        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        t0 = time.perf_counter()
        ctx = api.redo_last_step(sid)
        redo_times.append(time.perf_counter() - t0)

        assert ctx["kind"] == "ATCOMPLETION"

    assert len(ADAPTER_COMPLEXITY_CALLS) == n + 20

    undo_elapsed = sum(undo_times)
    redo_elapsed = sum(redo_times)

    print(
        "[class-adapter-complexity-summary] undo_redo_public_tape "
        f"n={n} undo20={undo_elapsed:.6f}s redo20={redo_elapsed:.6f}s "
        f"avg_undo_ms={undo_elapsed * 1000 / 20:.3f} "
        f"avg_redo_ms={redo_elapsed * 1000 / 20:.3f}"
    )

    assert undo_elapsed < 10.0
    assert redo_elapsed < 10.0


@pytest.mark.skipif(
    not RUN_ADAPTER_COMPLEXITY_CRAZY,
    reason="set APP_TABLE_CLASS_ADAPTER_COMPLEXITY_CRAZY=1",
)
def test_adapter_complexity_crazy_all_touched_reexplode_once_diagnostic():
    """
    Optional expensive diagnostic.

    Every class-backed Q datum is touched, reexploded once, and confirmed.
    This is intentionally O(n) because all n datums genuinely changed.

    The proof target is not constant time. The target is:
        calls == 2 * n
        writes == 2 * n
        no extra adapter writes beyond lower reexplode/done writes
    """

    ADAPTER_COMPLEXITY_CALLS.clear()

    n = int(os.environ.get("APP_TABLE_CLASS_ADAPTER_COMPLEXITY_N", "500"))
    form_id = f"adapter.complexity.crazy.reexplode.{n}"
    step_name = f"adapter.complexity.crazy.reexplode.{n}.step"

    _register_step(
        step_name,
        _adapter_complexity_q_multiframespec(
            n,
            app_form_id=form_id,
            widget_name="test.adapter.complexity.reexplode_once",
            wide_span=False,
            max_reexplosions=1,
            max_messages=4,
        ),
    )

    api = _api()
    sid = _adapter_complexity_create(api, step_name)

    t0 = time.perf_counter()
    for i in range(n):
        api.step_session(sid, fill={f"D{i}": {"value": "draft"}})
        ctx = api.step_session(sid, fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert len(ADAPTER_COMPLEXITY_CALLS) == 2 * n

    st = _adapter_complexity_state(api, sid)
    writes = _adapter_complexity_runtime_lifecycle_writes(
        st,
        max_results=10_000_000,
    )

    assert len(writes) == 2 * n

    print(
        "[class-adapter-complexity-summary] crazy_all_touched_reexplode_once "
        f"n={n} manual_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f} "
        f"calls={len(ADAPTER_COMPLEXITY_CALLS)} lifecycle_writes={len(writes)}"
    )