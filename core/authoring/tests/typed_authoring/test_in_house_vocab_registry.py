"""Unit tests for in-house Python function vocabulary registration, validation, and contracts."""
import pytest
from bindings2bindingsTM import Dict, Str, Int, Float, List, Map
from JSONfnchainTM import FunctionVocab, FlowCompilationError, compile_flow, execute_flow


def test_in_house_vocab_registration_and_execution():
    """Verify authoring, registering, and running an in-house custom transformation."""
    vocab = FunctionVocab()

    # Define an in-house data normalization function
    def normalize_slug(args, ctx):
        raw = args["raw_title"]
        cleaned = "".join(c.lower() if c.isalnum() else "-" for c in raw).strip("-")
        return {"slug": cleaned, "length": len(cleaned)}

    vocab.register(
        name="text.slugify",
        inputs=Dict({"raw_title": Str}),
        output=Dict({"slug": Str, "length": Int}),
        fn=normalize_slug,
        version="1.0",
    )

    flow = {
        "steps": [
            {"id": "s1", "fn": "text.slugify", "args": {"raw_title": "Hello Thinkument World 2026!"}},
        ],
        "returns": "$s1",
    }

    plan = compile_flow(flow, {}, None, vocab)
    result = execute_flow(plan, {}, vocab=vocab)

    assert result == {"slug": "hello-thinkument-world-2026", "length": 27}


def test_in_house_vocab_contract_enforcement():
    """Verify that vocab.register enforces closed-record Dict contracts and non-empty versions."""
    vocab = FunctionVocab()

    # Reject non-closed Dict inputs
    with pytest.raises(FlowCompilationError, match="must be closed Dict schemas"):
        vocab.register(
            name="math.square",
            inputs=Float,  # Not a Dict
            output=Dict({"result": Float}),
            fn=lambda a, c: {"result": a * a},
            version="1.0",
        )

    # Reject non-closed Dict outputs
    with pytest.raises(FlowCompilationError, match="must be closed Dict schemas"):
        vocab.register(
            name="math.square",
            inputs=Dict({"num": Float}),
            output=Float,  # Not a Dict
            fn=lambda a, c: a["num"] * a["num"],
            version="1.0",
        )

    # Reject empty version string
    with pytest.raises(FlowCompilationError, match="Version must be a nonempty string"):
        vocab.register(
            name="math.square",
            inputs=Dict({"num": Float}),
            output=Dict({"result": Float}),
            fn=lambda a, c: {"result": a["num"] ** 2},
            version="",
        )
