from __future__ import annotations

"""Unit tests for authoring_w_persistence_async primitives, handles, and widget mixin."""

import pytest

from authoring_w_persistence_async import (
    AsyncWorkHandle,
    AsyncWorkWidgetMixin,
    async_work_target,
    get_async_work_handle_v1,
    get_authoring_target,
    register_authoring_target,
    submit_async_work_v1,
)
from epsilinesTM_serveragnostic import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_PROGRESS_CHANNEL,
    VISIBILITY_OWNER_ONLY,
    bind_eps_reader_v1,
    bind_eps_sink_v1,
    emit_eps_v1,
)
from live_vial._json_shell.eps_log import InMemoryEpsLog


@pytest.fixture
def memory_log():
    return InMemoryEpsLog()


@pytest.fixture
def bound_eps(memory_log):
    def sink(channel, payload, **kwargs):
        run_id = kwargs.pop("run_id", "test_run_auth_01")
        owner_id = kwargs.pop("owner_id", "test_owner_auth")
        ref = kwargs.pop("ref", None)
        parent_ref = kwargs.pop("parent_ref", None)
        meta = kwargs.pop("meta", None)
        vis = kwargs.pop("visibility", VISIBILITY_OWNER_ONLY)
        kwargs.pop("event_id", None)
        kwargs.pop("span_id", None)
        kwargs.pop("record_in_session_queue", None)
        row = memory_log.append(
            run_id=run_id,
            channel=channel,
            payload=payload,
            event_id=ref or "",
            span_id=parent_ref or "",
            owner_id=owner_id,
            meta=meta,
            visibility=vis,
            **kwargs,
        )
        return row.get("event_id") or ""

    def reader(channel, **kwargs):
        return memory_log.query(channel=channel, **kwargs)

    with bind_eps_sink_v1(sink):
        with bind_eps_reader_v1(reader):
            yield memory_log


def test_target_registry_decorator():
    """Verify @async_work_target registers functions cleanly."""
    @async_work_target
    def generate_pdf_report(report_id: str):
        return f"pdf_{report_id}"

    assert get_authoring_target("generate_pdf_report") is generate_pdf_report

    @async_work_target("custom_export_task")
    def export_data(format: str):
        return format

    assert get_authoring_target("custom_export_task") is export_data


def test_submit_async_work_returns_handle(bound_eps):
    """Verify submit_async_work_v1 emits announcement and returns populated handle."""
    handle = submit_async_work_v1(
        target="heavy_matrix_factorization",
        kwargs={"dim": 256},
        timeout_seconds=45.0,
        ref="async/mf_run_01",
        meta={"experiment": "exp_A"},
    )

    assert isinstance(handle, AsyncWorkHandle)
    assert handle.ref == "async/mf_run_01"
    assert handle.done_ref == "async/mf_run_01/done"

    # Immediately after submit, job is running, not done
    assert handle.is_done() is False
    assert handle.get_outcome() is None
    assert handle.get_result() is None

    # Announcement envelope is readable
    ann = handle.get_announcement()
    assert ann is not None
    assert ann["payload"]["target"] == "heavy_matrix_factorization"
    assert ann["payload"]["kwargs"]["dim"] == 256
    assert ann["payload"]["timeout_seconds"] == 45.0


def test_handle_progress_stream_and_terminal_done(bound_eps):
    """Verify handle correctly tracks intermediate progress and reads terminal done sandwich."""
    handle = submit_async_work_v1(
        target="batch_indexer",
        kwargs={"files": 10},
        ref="async/indexer_01",
    )

    # 1. Emit progress ticks
    emit_eps_v1(
        ASYNCWORK_PROGRESS_CHANNEL,
        {"target": "batch_indexer", "percent": 25.0, "step_name": "parsing"},
        parent_ref=handle.ref,
    )
    emit_eps_v1(
        ASYNCWORK_PROGRESS_CHANNEL,
        {"target": "batch_indexer", "percent": 75.0, "step_name": "indexing"},
        parent_ref=handle.ref,
    )

    all_p = handle.get_all_progress()
    assert len(all_p) == 2
    assert all_p[0]["payload"]["percent"] == 25.0
    assert all_p[1]["payload"]["percent"] == 75.0

    latest_p = handle.get_latest_progress()
    assert latest_p is not None
    assert latest_p["payload"]["step_name"] == "indexing"
    assert latest_p["payload"]["percent"] == 75.0

    assert handle.is_done() is False

    # 2. Emit terminal done sandwich
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {
            "target": "batch_indexer",
            "outcome": "success",
            "result": {"indexed_count": 10, "index_id": "idx_abc"},
            "duration_ms": 1245.5,
        },
        ref=handle.done_ref,
        parent_ref=handle.ref,
    )

    assert handle.is_done() is True
    assert handle.get_outcome() == "success"
    assert handle.get_result() == {"indexed_count": 10, "index_id": "idx_abc"}
    assert handle.get_duration_ms() == 1245.5
    assert handle.get_error() is None


def test_handle_wait_until_done(bound_eps):
    """Verify Mode 2 bounded synchronous wait completes on done or raises TimeoutError."""
    handle = submit_async_work_v1(
        target="fast_computation",
        ref="async/fast_comp_01",
    )

    # Emit done immediately
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {"target": "fast_computation", "outcome": "success", "result": 100},
        ref=handle.done_ref,
        parent_ref=handle.ref,
    )

    res = handle.wait_until_done(timeout_seconds=2.0, poll_interval=0.05)
    assert res["payload"]["result"] == 100

    # Unclosed job should raise TimeoutError
    stuck_handle = submit_async_work_v1(
        target="stuck_computation",
        ref="async/stuck_01",
    )
    with pytest.raises(TimeoutError, match="did not complete within"):
        stuck_handle.wait_until_done(timeout_seconds=0.1, poll_interval=0.02)


def test_widget_mixin_cross_widget_wire_flow(bound_eps):
    """Verify Philosophy 2 cross-widget async work flow via AsyncWorkWidgetMixin."""
    class Step1ProducerWidget(AsyncWorkWidgetMixin):
        def explode(self):
            # Step 1: Submits heavy work in <5ms, writes ref to state
            handle = self.submit_async_work_v1(
                target="generate_large_asset",
                kwargs={"asset_id": "asset_42"},
                ref="async/asset_42",
            )
            return {"task_ref": handle.ref}

    class Step2ConsumerWidget(AsyncWorkWidgetMixin):
        def explode(self, wires: dict):
            task_ref = wires["task_ref"]
            if not self.is_async_work_done_v1(task_ref):
                # Still running: update micro-shell with progress
                latest = self.get_async_work_progress_v1(task_ref)
                pct = latest["payload"]["percent"] if latest else 0.0
                return {"done": False, "shell": f"Generating... {pct}%"}

            # Finished: extract result and mark done
            result = self.get_async_work_result_v1(task_ref)
            return {"done": True, "shell": f"Ready: {result['url']}"}

    producer = Step1ProducerWidget()
    state = producer.explode()
    assert state["task_ref"] == "async/asset_42"

    consumer = Step2ConsumerWidget()
    # Check while still pending
    res1 = consumer.explode(wires=state)
    assert res1["done"] is False
    assert "0.0%" in res1["shell"]

    # Progress emitted
    emit_eps_v1(
        ASYNCWORK_PROGRESS_CHANNEL,
        {"target": "generate_large_asset", "percent": 50.0},
        parent_ref="async/asset_42",
    )
    res2 = consumer.explode(wires=state)
    assert res2["done"] is False
    assert "50.0%" in res2["shell"]

    # Done sandwich emitted
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {
            "target": "generate_large_asset",
            "outcome": "success",
            "result": {"url": "https://storage.thinkument.com/assets/asset_42.png"},
            "duration_ms": 820.0,
        },
        ref="async/asset_42/done",
        parent_ref="async/asset_42",
    )

    res3 = consumer.explode(wires=state)
    assert res3["done"] is True
    assert res3["shell"] == "Ready: https://storage.thinkument.com/assets/asset_42.png"
