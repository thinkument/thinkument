"""Contract tests for asynchronous JSONic widget execution, static flow classification, and promise output ports."""
import pytest
from copy import deepcopy
from bindings2bindingsTM import Dict, Str, Int, Promise
from authoring_funneling.b_typed_JSON_widget_declaration import (
    prepare_json_widget_v1,
    register_prepared_json_widget_v1,
    execute_json_flow_target,
)
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE
from authoring_w_persistence_async import (
    get_async_work_handle_v1,
    submit_async_work_v1,
)
from epsilinesTM_serveragnostic import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_PROGRESS_CHANNEL,
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
        run_id = kwargs.pop("run_id", "test_run_async_json")
        owner_id = kwargs.pop("owner_id", "test_owner_async_json")
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


def test_static_flow_classification():
    """Verify that compile-time flow analysis categorizes pure vs async transitions accurately."""
    manifest = {
        "kind": "json_widget_v1",
        "name": "flow_classifier.test",
        "declaration": {
            "inputs": {},
            "outputs": {"sync_res": {"count": "int"}, "async_res": {"kind": "promise", "item": {"title": "str"}}},
        },
        "signals": {
            "mount": {
                "steps": [
                    {"id": "add", "fn": "math.add", "args": {"a": 1.0, "b": 2.0}},
                ],
                "outputs": {"sync_res": {"count": 3}},
                "done": True,
            },
            "fill": {
                "done": True,
                "keep": "*",
            },
            "call_vendor": {
                "steps": [
                    {"id": "chat", "fn": "vendor.llm.chat_completion", "args": {"prompt": "Hi", "model": None, "temperature": None}},
                ],
                "done": True,
                "keep": "*",
            },
            "explicit_sync": {
                "execution": "sync",
                "steps": [
                    {"id": "c", "fn": "text.concat", "args": {"parts": ["a", "b"], "sep": "-"}},
                ],
                "done": True,
                "keep": "*",
            },
            "explicit_async": {
                "execution": "async",
                "steps": [
                    {"id": "c", "fn": "text.concat", "args": {"parts": ["x", "y"], "sep": ":"}},
                ],
                "done": True,
                "keep": "*",
            },
        },
    }

    prepared = prepare_json_widget_v1(manifest)
    async_flags = dict(getattr(prepared.widget_class, "_async_transitions"))

    assert async_flags["mount"] is False
    assert async_flags["fill"] is False
    assert async_flags["call_vendor"] is True
    assert async_flags["explicit_sync"] is False
    assert async_flags["explicit_async"] is True


def test_json_widget_async_execution_lifecycle(bound_eps):
    """Verify full async transition lifecycle: snap dispatch (<5ms), reexplode shell, and terminal completion."""
    manifest = {
        "kind": "json_widget_v1",
        "name": "async_widget_lifecycle.test",
        "declaration": {
            "inputs": {},
            "outputs": {
                "report": {"kind": "promise", "item": {"summary": "str"}},
                "status": {"msg": "str"},
            },
        },
        "signals": {
            "mount": {
                "outputs": {
                    "report": {"ref": "pending", "status": "init"},
                    "status": {"msg": "ready"},
                },
                "reexplode": {"title": "Async Worker Demo", "micros": [{"name": "btn", "type": "action"}]},
            },
            "fill": {
                "done": True,
                "keep": "*",
            },
            "start_job": {
                "execution": "async",
                "steps": [
                    {"id": "p1", "fn": "text.concat", "args": {"parts": ["Batch", "42"], "sep": " "}},
                    {"id": "p2", "fn": "text.template", "args": {"template": "Generated: {{title}}", "vars": {"title": "$p1.text"}}},
                ],
                "outputs": {
                    "report": {"summary": "$p2.text"},
                    "status": {"msg": "complete"},
                },
                "done": True,
            },
        },
    }

    prepared = register_prepared_json_widget_v1(prepare_json_widget_v1(manifest))
    from authoring_funneling import compile_strict_program

    program_spec = {
        'kind': 'think_program_v1',
        'surface_version': 'v1',
        'symbols': {},
        'puppeteering': {},
        'run': {
            'program': {
                'info': {'id': 'test_p', 'title': 'Test'},
                'widgets': {'w': {'widget': manifest['name'], 'bindings': {}}},
                'flow': [{'id': 'first', 'widgets': ['w']}],
            },
            'config': {},
        },
    }
    compiled = compile_strict_program(program_spec)
    args = {**compiled['run']['program']['widgets']['w']['args'],
            **compiled['run']['program']['flow'][0]['overrides']['args']['w']}

    events = []
    def emit(payload, *, name, **_kwargs):
        events.append((name, deepcopy(payload)))
        return {}

    widget = prepared(q={"form_id": "f", "frame_id": "fr", "span_id": "s", "datum_id": "w"}, emit=emit)
    fill = {"fill_shell": {"id": "w", "args": args, "micros": [{"name": "btn", "type": "action"}]}, "current_fills": {}}

    # 1. Mount: synchronous fast-path (<1ms)
    mount_res = widget._on_mount({}, fill, {}, {})
    assert mount_res.next_fill_shell["title"] == "Async Worker Demo"
    assert widget.outputs.read("status", "msg") == "ready"

    # 2. Trigger async transition `start_job`
    # In interactive snap dispatch (<5ms), this must:
    # - Submit asyncwork.announce
    # - Store ref in widget state
    # - Write promise descriptor to output port
    # - Return Reexplode progress shell
    snap_res = widget.json_signal_start_job({}, {}, fill, {}, {})
    assert snap_res.next_fill_shell["title"] == "Started start_job..."

    ref = widget._state.get("_async_work_ref_start_job")
    assert ref is not None
    assert ref.startswith("async/jsonfnchain.execute_transition/")

    # Output port declared as Promise receives the descriptor
    assert widget.outputs.read("report", "ref") == ref
    assert widget.outputs.read("report", "status") == "running"

    # Verify announcement in eps log
    handle = get_async_work_handle_v1(ref)
    assert handle.is_done() is False

    # 3. Simulate background execution on QUEUE_ASYNCWORK
    # Celery worker invokes execute_json_flow_target
    recipe_json = widget._compiled_transitions["start_job"].to_json()
    root_scope = widget._build_root_scope(fill, {})

    target_res = execute_json_flow_target(
        recipe_json=recipe_json,
        root_scope=root_scope,
        operation_id="op_123",
        widget_id=widget.__class__.__name__,
        transition_name="start_job",
        announcement_ref=ref,
    )

    # Worker finishes and emits asyncwork.done sandwich
    emit_eps_v1(
        channel=ASYNCWORK_DONE_CHANNEL,
        payload={
            "target": "jsonfnchain.execute_transition",
            "outcome": "success",
            "result": target_res,
            "duration_ms": 12.5,
        },
        ref=handle.done_ref,
        parent_ref=ref,
    )

    assert handle.is_done() is True
    assert handle.get_outcome() == "success"

    # 4. Next tick: widget inspects handle, sees completion, and applies final outputs
    done_res = widget.json_signal_start_job({}, {}, fill, {}, {})
    assert done_res is True

    # Output ports now carry final resolved data
    assert widget.outputs.read("report", "summary") == "Generated: Batch 42"
    assert widget.outputs.read("status", "msg") == "complete"
    assert "_async_work_ref_start_job" not in widget._state
