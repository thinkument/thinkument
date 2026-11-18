"""Unit tests for AsyncWorkFlowInterceptor hooks, progress calculation, and telemetry."""
import pytest
from JSONfnchainTM import compile_flow, execute_flow, FunctionVocab, FlowAttemptContext
from authoring_funneling.b_typed_JSON_widget_declaration.interceptor import AsyncWorkFlowInterceptor
from bindings2bindingsTM import Float, Dict, Str


def create_vocab():
    vocab = FunctionVocab()
    vocab.register(name="math.add", inputs=Dict({"a": Float, "b": Float}), output=Dict({"result": Float}),
                   fn=lambda a, c: {"result": a["a"] + a["b"]}, version="1")
    vocab.register(name="math.multiply", inputs=Dict({"a": Float, "b": Float}), output=Dict({"result": Float}),
                   fn=lambda a, c: {"result": a["a"] * a["b"]}, version="1")
    return vocab


def test_progress_interceptor_callback_ticks():
    """Verify that AsyncWorkFlowInterceptor invokes progress callback with percentages."""
    vocab = create_vocab()
    flow = {
        "steps": [
            {"id": "step1", "fn": "math.add", "args": {"a": 2.0, "b": 3.0}},
            {"id": "step2", "fn": "math.multiply", "args": {"a": "$step1.result", "b": 4.0}},
        ],
        "returns": "$step2",
    }
    plan = compile_flow(flow, {}, None, vocab)

    ticks = []
    def on_progress(**kwargs):
        ticks.append(kwargs)

    interceptor = AsyncWorkFlowInterceptor(
        widget=None,
        progress_callback=on_progress,
        announcement_ref="async/test/001",
        total_steps=2,
    )

    result = execute_flow(
        plan,
        {},
        vocab=vocab,
        interceptor=interceptor,
        host_context={"operation_id": "op_test"},
    )

    assert result == {"result": 20.0}
    assert len(ticks) == 2
    assert ticks[0]["step_index"] == 1
    assert ticks[0]["total_steps"] == 2
    assert ticks[0]["percent"] == 50.0
    assert ticks[0]["step_name"] == "step1"

    assert ticks[1]["step_index"] == 2
    assert ticks[1]["total_steps"] == 2
    assert ticks[1]["percent"] == 100.0
    assert ticks[1]["step_name"] == "step2"


def test_progress_interceptor_direct_eps_emission():
    """Verify that when no progress callback is provided, interceptor emits to ASYNCWORK_PROGRESS_CHANNEL."""
    from epsilinesTM_serveragnostic import ASYNCWORK_PROGRESS_CHANNEL, bind_eps_sink_v1
    vocab = create_vocab()
    flow = {
        "steps": [
            {"id": "add", "fn": "math.add", "args": {"a": 10.0, "b": 5.0}},
        ],
        "returns": "$add",
    }
    plan = compile_flow(flow, {}, None, vocab)

    emitted = []
    def mock_sink(channel, payload, **kwargs):
        emitted.append((channel, payload, kwargs))
        return "event_id_01"

    interceptor = AsyncWorkFlowInterceptor(
        announcement_ref="async/flow/direct_eps",
        total_steps=1,
    )

    with bind_eps_sink_v1(mock_sink):
        result = execute_flow(plan, {}, vocab=vocab, interceptor=interceptor)

    assert result == {"result": 15.0}
    assert len(emitted) == 1
    channel, payload, kwargs = emitted[0]
    assert channel == ASYNCWORK_PROGRESS_CHANNEL
    assert kwargs.get("parent_ref") == "async/flow/direct_eps"
    assert payload["percent"] == 100.0
    assert payload["step_name"] == "add"
    assert payload["step_index"] == 1
