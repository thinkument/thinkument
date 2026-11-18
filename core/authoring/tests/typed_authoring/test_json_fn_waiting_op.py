"""Contract tests for asyncwork.await_result and asyncwork.poll within JSON function chains."""
import pytest
from JSONfnchainTM import compile_flow, execute_flow, FlowRuntimeError
from authoring_funneling.b_typed_JSON_widget_declaration.vocab_hub import THINKUMENT_GLOBAL_VOCAB
from authoring_w_persistence_async import submit_async_work_v1
from epsilinesTM_serveragnostic import (
    ASYNCWORK_DONE_CHANNEL,
    VISIBILITY_OWNER_ONLY,
    bind_eps_sink_v1,
    bind_eps_reader_v1,
    emit_eps_v1,
)
from live_vial._json_shell.eps_log import InMemoryEpsLog


@pytest.fixture
def memory_log():
    return InMemoryEpsLog()


@pytest.fixture
def bound_eps(memory_log):
    def sink(channel, payload, **kwargs):
        run_id = kwargs.pop("run_id", "test_run_wait_op")
        owner_id = kwargs.pop("owner_id", "test_owner_wait_op")
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


def test_json_flow_await_result_success(bound_eps):
    """Verify that a JSON DAG invoking asyncwork.await_result successfully resolves the promise."""
    # 1. Simulate an async task submission
    handle = submit_async_work_v1(
        target="data_synthesis_task",
        kwargs={"sample_id": 99},
        ref="async/synth/001",
    )

    # 2. Complete the task in background
    emit_eps_v1(
        channel=ASYNCWORK_DONE_CHANNEL,
        payload={
            "target": "data_synthesis_task",
            "outcome": "success",
            "result": {"status": "analyzed", "score": "98"},
            "duration_ms": 15.0,
        },
        ref=handle.done_ref,
        parent_ref=handle.ref,
    )

    # 3. JSON flow takes $mouth.task (promise descriptor) and awaits it
    flow = {
        "steps": [
            {
                "id": "awaited",
                "fn": "asyncwork.await_result",
                "args": {
                    "promise": "$mouth.task",
                    "timeout_seconds": 5.0,
                },
            },
        ],
        "returns": "$awaited",
    }

    from bindings2bindingsTM import Dict, Map, Str
    plan = compile_flow(flow, {"mouth": Dict({"task": Map(Str)})}, None, THINKUMENT_GLOBAL_VOCAB)

    scope = {
        "mouth": {
            "task": {"ref": handle.ref, "status": "running"},
        },
    }

    result = execute_flow(plan, scope, vocab=THINKUMENT_GLOBAL_VOCAB)
    assert result["outcome"] == "success"
    assert result["result"] == {"status": "analyzed", "score": "98"}


def test_json_flow_await_result_polymorphic_pass_through():
    """Verify that asyncwork.await_result acts as an identity pass-through for sync data."""
    flow = {
        "steps": [
            {
                "id": "awaited",
                "fn": "asyncwork.await_result",
                "args": {
                    "promise": "$mouth.immediate_data",
                    "timeout_seconds": 5.0,
                },
            },
        ],
        "returns": "$awaited",
    }

    from bindings2bindingsTM import Dict, Map, Str
    plan = compile_flow(flow, {"mouth": Dict({"immediate_data": Map(Str)})}, None, THINKUMENT_GLOBAL_VOCAB)

    scope = {
        "mouth": {
            "immediate_data": {"title": "Fast Compute", "category": "sync"},
        },
    }

    result = execute_flow(plan, scope, vocab=THINKUMENT_GLOBAL_VOCAB)
    assert result["outcome"] == "immediate_sync"
    assert result["result"] == {"title": "Fast Compute", "category": "sync"}


def test_json_flow_poll_op(bound_eps):
    """Verify that asyncwork.poll inspects doneness without blocking."""
    handle = submit_async_work_v1(
        target="long_batch_job",
        ref="async/batch/100",
    )

    flow = {
        "steps": [
            {
                "id": "status_check",
                "fn": "asyncwork.poll",
                "args": {
                    "promise": "$mouth.job",
                },
            },
        ],
        "returns": "$status_check",
    }

    from bindings2bindingsTM import Dict, Map, Str
    plan = compile_flow(flow, {"mouth": Dict({"job": Map(Str)})}, None, THINKUMENT_GLOBAL_VOCAB)
    scope = {"mouth": {"job": {"ref": handle.ref, "status": "running"}}}

    # Step 1: Still running
    res1 = execute_flow(plan, scope, vocab=THINKUMENT_GLOBAL_VOCAB)
    assert res1["is_done"] == "false"
    assert res1["outcome"] == "ongoing"

    # Step 2: Settle task
    emit_eps_v1(
        channel=ASYNCWORK_DONE_CHANNEL,
        payload={
            "target": "long_batch_job",
            "outcome": "success",
            "result": {"output_file": "/data/out.csv"},
        },
        ref=handle.done_ref,
        parent_ref=handle.ref,
    )

    # Step 3: Poll again -> now done!
    res2 = execute_flow(plan, scope, vocab=THINKUMENT_GLOBAL_VOCAB)
    assert res2["is_done"] == "true"
    assert res2["outcome"] == "success"
    assert res2["result"] == {"output_file": "/data/out.csv"}
