from __future__ import annotations

"""Comprehensive unit tests for epsilinesTM live usage, referencing, hierarchies, and targeted reads."""

from concurrent.futures import ThreadPoolExecutor
import contextvars
import threading
import pytest

from epsilinesTM_serveragnostic import (
    CannotReadTransientEpsChannelError,
    EpsReaderNotConfigured,
    EpsSinkNotConfigured,
    MODE_NONE,
    MODE_PERSISTENCE,
    RETENTION_DURABLE,
    RETENTION_NONE,
    VISIBILITY_ALL_NO_MODULATION,
    VISIBILITY_ALL_WITH_MODULATION,
    VISIBILITY_OWNER_ONLY,
    bind_eps_reader_v1,
    bind_eps_sink_v1,
    emit_eps_v1,
    read_eps_v1,
    register_eps_channel_v1,
    require_registered_eps_channel_v1,
    unregister_eps_channel_v1,
    EpsChannelSpecV1,
)
from epsilinesTM_serveragnostic.subapps import ServiceReadyWidget
from epsilinesTM_serveragnostic.subapps.analytics.template_thinkwidget_analytics_powered import (
    AnalyticaPoweredDatumLifecycleWidget,
)
from live_vial._json_shell.eps_log import InMemoryEpsLog


# Test fixture for memory eps log provider
@pytest.fixture
def memory_log():
    log = InMemoryEpsLog()
    return log


@pytest.fixture
def bound_memory_log(memory_log):
    def sink(channel, payload, **kwargs):
        run_id = kwargs.pop("run_id", "test_run_123")
        owner_id = kwargs.pop("owner_id", "test_owner_abc")
        ref = kwargs.pop("ref", None)
        parent_ref = kwargs.pop("parent_ref", None)
        meta = kwargs.pop("meta", None)
        vis = kwargs.pop("visibility", VISIBILITY_ALL_WITH_MODULATION)
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


@pytest.fixture(autouse=True)
def cleanup_custom_channels():
    yield
    for ch in ("test.live_stream", "test.hierarchical_task", "test.owner_only"):
        try:
            unregister_eps_channel_v1(ch)
        except Exception:
            pass


def test_emit_eps_returns_ref_and_records(bound_memory_log):
    # Register test channel
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.hierarchical_task",
            app="analytica",
            schema="test_task_v1",
            event="task_step",
            validator=lambda p: {"task": str(p.get("task", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    # 1. Emit with explicit ref
    ref1 = emit_eps_v1(
        "test.hierarchical_task",
        {"task": "Root Goal"},
        ref="plan/root",
        meta={"phase": "init"},
    )
    assert ref1 == "plan/root"

    # 2. Emit with auto-allocated ref
    ref2 = emit_eps_v1(
        "test.hierarchical_task",
        {"task": "Child Step"},
        parent_ref=ref1,
        meta={"phase": "exec"},
    )
    assert ref2 != ""
    assert isinstance(ref2, str)


def test_point_seek_returns_single_envelope_or_none(bound_memory_log):
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.hierarchical_task",
            app="analytica",
            schema="test_task_v1",
            event="task_step",
            validator=lambda p: {"task": str(p.get("task", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    emit_eps_v1("test.hierarchical_task", {"task": "Find Me"}, ref="target_node")

    # Point seek returns single dict
    item = read_eps_v1("test.hierarchical_task", ref="target_node")
    assert isinstance(item, dict)
    assert item["ref"] == "target_node"
    assert item["payload"]["task"] == "Find Me"
    assert item["channel"] == "test.hierarchical_task"

    # Point seek for nonexistent ref returns None
    missing = read_eps_v1("test.hierarchical_task", ref="nonexistent_node")
    assert missing is None


def test_hierarchy_seek_and_sub_dir_batch(bound_memory_log):
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.hierarchical_task",
            app="analytica",
            schema="test_task_v1",
            event="task_step",
            validator=lambda p: {"task": str(p.get("task", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    # Build tree:
    # goal/root
    # ├── goal/branch_a
    # │   ├── goal/branch_a/sub_1
    # │   └── goal/branch_a/sub_2
    # └── goal/branch_b
    emit_eps_v1("test.hierarchical_task", {"task": "Root"}, ref="goal/root")
    emit_eps_v1("test.hierarchical_task", {"task": "Branch A"}, ref="goal/branch_a", parent_ref="goal/root")
    emit_eps_v1("test.hierarchical_task", {"task": "Sub 1"}, ref="goal/branch_a/sub_1", parent_ref="goal/branch_a")
    emit_eps_v1("test.hierarchical_task", {"task": "Sub 2"}, ref="goal/branch_a/sub_2", parent_ref="goal/branch_a")
    emit_eps_v1("test.hierarchical_task", {"task": "Branch B"}, ref="goal/branch_b", parent_ref="goal/root")

    # 1. Hierarchy seek on goal/root -> returns 2 direct children (branch_a, branch_b)
    children = read_eps_v1("test.hierarchical_task", parent_ref="goal/root")
    assert isinstance(children, list)
    assert len(children) == 2
    child_refs = {c["ref"] for c in children}
    assert child_refs == {"goal/branch_a", "goal/branch_b"}

    # 2. Sub-dir prefix batch seek on "goal/branch_a/*" -> returns sub_1 and sub_2
    sub_nodes = read_eps_v1("test.hierarchical_task", ref_prefix="goal/branch_a/")
    assert isinstance(sub_nodes, list)
    assert len(sub_nodes) == 2
    sub_refs = {s["ref"] for s in sub_nodes}
    assert sub_refs == {"goal/branch_a/sub_1", "goal/branch_a/sub_2"}


def test_cannot_read_transient_channel_fails_fast(bound_memory_log):
    # Register transient streaming channel with mode=MODE_NONE
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.live_stream",
            app="analytica",
            schema="stream_v1",
            event="chunk",
            validator=lambda p: {"chunk": str(p.get("chunk", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_NONE,
            retention=RETENTION_NONE,
        )
    )

    # Emission on transient channel succeeds
    emit_eps_v1("test.live_stream", {"chunk": "audio_1"})

    # Reading from transient channel fails fast
    with pytest.raises(CannotReadTransientEpsChannelError) as exc_info:
        read_eps_v1("test.live_stream", ref="any")
    assert "mode='none'" in str(exc_info.value)


def test_role_modulation_on_read(bound_memory_log):
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.owner_only",
            app="analytica",
            schema="secret_v1",
            event="secret_fact",
            validator=lambda p: {"secret": str(p.get("secret", ""))},
            visibility=VISIBILITY_OWNER_ONLY,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    emit_eps_v1("test.owner_only", {"secret": "super_private"}, ref="sec_1")

    # Non-owner read returns None for point seek on owner-only
    non_owner_read = read_eps_v1("test.owner_only", ref="sec_1", for_owner=False)
    assert non_owner_read is None

    # Owner read returns cleartext
    owner_read = read_eps_v1("test.owner_only", ref="sec_1", for_owner=True)
    assert owner_read is not None
    assert owner_read["payload"]["secret"] == "super_private"


def test_widget_runtime_box_emission_and_read(bound_memory_log):
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.hierarchical_task",
            app="analytica",
            schema="test_task_v1",
            event="task_step",
            validator=lambda p: {"task": str(p.get("task", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    # Test widget class
    class MyAlgorithmWidget(ServiceReadyWidget):
        run_id = "widget_run_777"
        _role = "author"

    def mock_emit(payload, name=None, **kwargs):
        return emit_eps_v1(name, payload, run_id="widget_run_777", **kwargs)

    widget = MyAlgorithmWidget(q={}, emit=mock_emit)

    # Widget writes using Jobsian call
    ref = widget.emit_eps_v1(
        "test.hierarchical_task",
        {"task": "Algorithm step 1"},
        ref="w_step_1",
    )
    assert ref == "w_step_1"

    # Widget reads back using Jobsian call
    node = widget.read_eps_v1("test.hierarchical_task", ref="w_step_1")
    assert node is not None
    assert node["payload"]["task"] == "Algorithm step 1"


def test_concurrency_multi_threaded_emissions_and_reads(bound_memory_log):
    register_eps_channel_v1(
        EpsChannelSpecV1(
            channel="test.hierarchical_task",
            app="analytica",
            schema="test_task_v1",
            event="task_step",
            validator=lambda p: {"task": str(p.get("task", ""))},
            visibility=VISIBILITY_ALL_NO_MODULATION,
            mode=MODE_PERSISTENCE,
            retention=RETENTION_DURABLE,
        )
    )

    # 10 concurrent threads emitting and reading
    num_threads = 10
    items_per_thread = 20

    def worker(thread_idx: int):
        for i in range(items_per_thread):
            ref = f"thread_{thread_idx}/task_{i}"
            parent = f"thread_{thread_idx}/task_{i-1}" if i > 0 else f"thread_{thread_idx}/root"
            allocated = emit_eps_v1(
                "test.hierarchical_task",
                {"task": f"Work item {thread_idx}-{i}"},
                ref=ref,
                parent_ref=parent,
            )
            assert allocated == ref
            
            # Immediately read back
            item = read_eps_v1("test.hierarchical_task", ref=ref)
            assert item is not None
            assert item["payload"]["task"] == f"Work item {thread_idx}-{i}"

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(contextvars.copy_context().run, worker, t)
            for t in range(num_threads)
        ]
        for f in futures:
            f.result()

    # Verify prefix batch query across threads
    thread_0_items = read_eps_v1("test.hierarchical_task", ref_prefix="thread_0/")
    assert len(thread_0_items) == items_per_thread
