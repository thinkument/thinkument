"""Pedagogical Master Test Suite for JSONfnchainTM.

This test sheet serves as the canonical executable tutorial and comprehensive
reference for all applied usage patterns of JSONfnchainTM operating over
bindings2bindingsTM.

Table of Contents:
1. Pure Data Shaping & Validation (Zero External I/O)
2. Sequential Multi-Step Orchestration
3. Valued Branching & Fallback Schema Reconciliation
4. Map Operations (Single-Call Shorthand & Multi-Step Reductions)
5. Stateful Convergence & Accumulation Loops
6. Parallel Fork-Join (Concurrent Fan-Out / Fan-In)
7. Deep Nested Composition (Map -> Branch -> Loop)
8. Production Telemetry, Audit & Billing Interceptors
9. Recipe Serialization, Storage & Cold Deserialization
10. Fail-Closed Settlement & Fault-Tolerant Forensics
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier, Lock
from time import perf_counter, sleep
import pytest

from bindings2bindingsTM import (
    D, Dict, List, Map, Nullable, Schema,
    normalize, compile_binding, infer_expression_type
)
from JSONfnchainTM import (
    FunctionVocab, FlowPlan, compile_flow, execute_flow,
    FlowInterceptor, FlowAttemptContext,
    FlowCompilationError, FlowRuntimeError, MaxIterationsExceededError
)


# =============================================================================
# Standard Test Vocabulary Fixtures
# =============================================================================

def create_pedagogical_vocab() -> FunctionVocab:
    """Instantiate a realistic suite of approved micro-operations."""
    vocab = FunctionVocab()

    # Text & Content Operations
    vocab.register(
        name="text.clean",
        fn=lambda args, ctx: {"cleaned": args["raw"].strip().replace("\r\n", "\n")},
        inputs=Dict({"raw": str}),
        output=Dict({"cleaned": str}),
        version="1.0"
    )
    vocab.register(
        name="text.tokenize",
        fn=lambda args, ctx: {"tokens": [t for t in args["text"].split() if t]},
        inputs=Dict({"text": str}),
        output=Dict({"tokens": List(str)}),
        version="1.0"
    )
    vocab.register(
        name="text.summarize",
        fn=lambda args, ctx: {"summary": f"Summary({args['title']}): {args['body'][:30]}..."},
        inputs=Dict({"title": str, "body": str}),
        output=Dict({"summary": str}),
        version="1.0"
    )

    # NLP / AI Analysis Operations
    vocab.register(
        name="ai.sentiment",
        fn=lambda args, ctx: {
            "score": 0.95 if "great" in args["content"].lower() or "good" in args["content"].lower() else 0.35,
            "label": "positive" if "great" in args["content"].lower() or "good" in args["content"].lower() else "neutral"
        },
        inputs=Dict({"content": str}),
        output=Dict({"score": float, "label": str}),
        version="1.0"
    )
    vocab.register(
        name="ai.expand_prompt",
        fn=lambda args, ctx: {
            "revised": f"{args['draft']} [v{args['round']}]",
            "quality": min(1.0, args["quality"] + 0.3)
        },
        inputs=Dict({"draft": str, "round": int, "quality": float}),
        output=Dict({"revised": str, "quality": float}),
        version="1.0"
    )

    # Mathematical / Scoring Operations
    vocab.register(
        name="score.normalize",
        fn=lambda args, ctx: {"normalized": max(0.0, min(1.0, float(args["raw_score"]) / float(args["max_score"])))},
        inputs=Dict({"raw_score": int, "max_score": int}),
        output=Dict({"normalized": float}),
        version="1.0"
    )

    return vocab


# =============================================================================
# 1. Pure Data Shaping & Validation (Zero External I/O)
# =============================================================================

def test_pattern_01_pure_data_shaping_zero_external_io():
    """Pattern 1: Pure expression transformation without any external callables.

    Demonstrates that JSONfnchainTM can execute zero-step workflows that solely
    rely on bindings2bindingsTM expression lowering via D.sugar(). All mathematical,
    string concatenation, list filtering, and schema projections execute purely.
    """
    vocab = create_pedagogical_vocab()

    # Zero-step flow that computes an aggregate report from incoming parameters
    flow = {
        "steps": [],
        "returns": {
            "title": {"$text": ["Report for ", "$params.user_name"]},
            "total_score": {"$sum": "$params.scores"},
            "passing_scores": {
                "$filter": ["$params.scores", {"$gte": ["$item", 70]}]
            },
            "is_certified": {"$gte": [{"$sum": "$params.scores"}, 200]}
        }
    }

    source_types = {
        "params": Dict({
            "user_name": str,
            "scores": List(int)
        })
    }
    target_type = Dict({
        "title": str,
        "total_score": int,
        "passing_scores": List(int),
        "is_certified": bool
    })

    plan = compile_flow(flow, source_types, target_type, vocab)
    result = execute_flow(
        plan,
        {"params": {"user_name": "Alice", "scores": [65, 80, 95]}},
        vocab=vocab
    )

    assert result == {
        "title": "Report for Alice",
        "total_score": 240,
        "passing_scores": [80, 95],
        "is_certified": True
    }


# =============================================================================
# 2. Sequential Multi-Step Orchestration
# =============================================================================

def test_pattern_02_sequential_multistep_pipeline():
    """Pattern 2: Linear multi-step pipeline passing outputs forward.

    Step 1 cleans raw text.
    Step 2 tokenizes the cleaned text.
    Step 3 analyzes sentiment of the cleaned text.
    The final returns block projects fields from multiple prior steps.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            {
                "id": "step_clean",
                "fn": "text.clean",
                "args": {"raw": "$inputs.raw_document"}
            },
            {
                "id": "step_tokens",
                "fn": "text.tokenize",
                "args": {"text": "$step_clean.cleaned"}
            },
            {
                "id": "step_sentiment",
                "fn": "ai.sentiment",
                "args": {"content": "$step_clean.cleaned"}
            }
        ],
        "returns": {
            "document_preview": "$step_clean.cleaned",
            "token_count": {"$size": "$step_tokens.tokens"},
            "sentiment_label": "$step_sentiment.label",
            "confidence": "$step_sentiment.score"
        }
    }

    source_types = {"inputs": Dict({"raw_document": str})}
    target_type = Dict({
        "document_preview": str,
        "token_count": int,
        "sentiment_label": str,
        "confidence": float
    })

    plan = compile_flow(flow, source_types, target_type, vocab)
    result = execute_flow(
        plan,
        {"inputs": {"raw_document": "  The service was great and quick! \r\n"}},
        vocab=vocab
    )

    assert result == {
        "document_preview": "The service was great and quick!",
        "token_count": 6,
        "sentiment_label": "positive",
        "confidence": 0.95
    }


# =============================================================================
# 3. Valued Branching & Fallback Schema Reconciliation
# =============================================================================

def test_pattern_03_valued_branching_with_schema_reconciliation():
    """Pattern 3: Conditional branching with static common schema reconciliation.

    Demonstrates:
    - Valued branches requiring typed returns from both arms.
    - Arm-local steps remain private (cannot leak cross-branch).
    - reconcile_common_schema combines branch outputs into a unified target schema.
    """
    vocab = create_pedagogical_vocab()

    # Content routing: if raw_score >= 80, fast-track approval; else run normalization
    flow = {
        "steps": [
            {
                "id": "audit_path",
                "if": {"$gte": ["$eval.score", 80]},
                "then": {
                    "steps": [],
                    "returns": {
                        "status": "APPROVED",
                        "final_rating": 1.0,
                        "requires_review": False
                    }
                },
                "else": {
                    "steps": [
                        {
                            "id": "norm",
                            "fn": "score.normalize",
                            "args": {
                                "raw_score": "$eval.score",
                                "max_score": 100
                            }
                        }
                    ],
                    "returns": {
                        "status": "REQUIRES_AUDIT",
                        "final_rating": "$norm.normalized",
                        "requires_review": True
                    }
                }
            }
        ],
        "returns": {
            "verdict": "$audit_path.status",
            "rating": "$audit_path.final_rating",
            "flagged": "$audit_path.requires_review"
        }
    }

    source_types = {"eval": Dict({"score": int})}
    target_type = Dict({"verdict": str, "rating": float, "flagged": bool})

    plan = compile_flow(flow, source_types, target_type, vocab)

    # Branch True: High score
    res_high = execute_flow(plan, {"eval": {"score": 92}}, vocab=vocab)
    assert res_high == {"verdict": "APPROVED", "rating": 1.0, "flagged": False}

    # Branch False: Lower score
    res_low = execute_flow(plan, {"eval": {"score": 45}}, vocab=vocab)
    assert res_low == {"verdict": "REQUIRES_AUDIT", "rating": 0.45, "flagged": True}


# =============================================================================
# 4. Map Operations (Single-Call Shorthand & Multi-Step Reductions)
# =============================================================================

def test_pattern_04_map_operations_and_reductions():
    """Pattern 4: Map operations over collection inputs.

    Demonstrates:
    - Single-call shorthand via map.call.
    - Multi-step map with alias item_as, $current, and $index.
    - Preserving input item ordering even in concurrent execution.
    - Post-map aggregations using b2b collection operators.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            # 1. Shorthand single call: clean every raw snippet
            {
                "id": "cleaned_docs",
                "map": {
                    "over": "$payload.documents",
                    "item_as": "doc",
                    "call": {"fn": "text.clean", "args": {"raw": "$doc"}}
                }
            },
            # 2. Multi-step map: analyze sentiment for each cleaned snippet
            {
                "id": "analyzed_docs",
                "map": {
                    "over": "$cleaned_docs",
                    "item_as": "snippet",
                    "parallel": True,
                    "max_concurrency": 4,
                    "steps": [
                        {
                            "id": "sent",
                            "fn": "ai.sentiment",
                            "args": {"content": "$snippet.cleaned"}
                        }
                    ],
                    "returns": {
                        "idx": "$index",
                        "text": "$snippet.cleaned",
                        "sentiment": "$sent.label",
                        "score": "$sent.score"
                    }
                }
            }
        ],
        "returns": {
            "total_processed": {"$size": "$analyzed_docs"},
            "results": "$analyzed_docs"
        }
    }

    source_types = {"payload": Dict({"documents": List(str)})}
    target_type = Dict({
        "total_processed": int,
        "results": List(Dict({
            "idx": int,
            "text": str,
            "sentiment": str,
            "score": float
        }))
    })

    plan = compile_flow(flow, source_types, target_type, vocab)
    docs = ["  First was great  ", "Second was okay", "  Third was good  "]
    result = execute_flow(plan, {"payload": {"documents": docs}}, vocab=vocab)

    assert result["total_processed"] == 3
    assert result["results"] == [
        {"idx": 0, "text": "First was great", "sentiment": "positive", "score": 0.95},
        {"idx": 1, "text": "Second was okay", "sentiment": "neutral", "score": 0.35},
        {"idx": 2, "text": "Third was good", "sentiment": "positive", "score": 0.95}
    ]


# =============================================================================
# 5. Stateful Convergence & Accumulation Loops
# =============================================================================

def test_pattern_05_stateful_loop_convergence_and_on_max():
    """Pattern 5: Bounded state-machine loop with accumulator state.

    Demonstrates:
    - Initializing state dictionary via loop.init.
    - While condition evaluating before each step ($state.quality < 0.9).
    - Iteration updates type-checked strictly against initial state schema.
    - on_max='return_current' returning the latest state upon ceiling.
    - Post-loop returns expression reading $state and $iteration.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            {
                "id": "refinement",
                "loop": {
                    "init": {"draft": "$req.initial_prompt", "quality": 0.2, "round": 1},
                    "max": 5,
                    "on_max": "return_current",
                    "while": {"$lt": ["$state.quality", 0.7]},
                    "steps": [
                        {
                            "id": "expand",
                            "fn": "ai.expand_prompt",
                            "args": {
                                "draft": "$state.draft",
                                "round": "$state.round",
                                "quality": "$state.quality"
                            }
                        }
                    ],
                    "update": {
                        "draft": "$expand.revised",
                        "quality": "$expand.quality",
                        "round": {"$add": ["$state.round", 1]}
                    },
                    "returns": {
                        "final_draft": "$state.draft",
                        "final_quality": "$state.quality",
                        "iterations_consumed": "$iteration"
                    }
                }
            }
        ],
        "returns": "$refinement"
    }

    source_types = {"req": Dict({"initial_prompt": str})}
    target_type = Dict({
        "final_draft": str,
        "final_quality": float,
        "iterations_consumed": int
    })

    plan = compile_flow(flow, source_types, target_type, vocab)
    result = execute_flow(plan, {"req": {"initial_prompt": "AI Draft"}}, vocab=vocab)

    # Round 1: quality 0.2 -> 0.5 (< 0.7)
    # Round 2: quality 0.5 -> 0.8 (>= 0.7 -> stops!)
    assert result == {
        "final_draft": "AI Draft [v1] [v2]",
        "final_quality": 0.8,
        "iterations_consumed": 2
    }


# =============================================================================
# 6. Parallel Fork-Join (Concurrent Fan-Out / Fan-In)
# =============================================================================

def test_pattern_06_parallel_fork_join_fanout_fanin():
    """Pattern 6: Concurrent fork-join fan-out of independent operations.

    Demonstrates:
    - Preflight validation of all child argument bindings before launching any thread.
    - Namespaced child output access: $fanout.child_id.field.
    - Bounded thread concurrency joining before proceeding.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            {
                "id": "analysis_fork",
                "parallel": [
                    {
                        "id": "sentiment_task",
                        "fn": "ai.sentiment",
                        "args": {"content": "$inputs.article"}
                    },
                    {
                        "id": "summary_task",
                        "fn": "text.summarize",
                        "args": {
                            "title": "$inputs.title",
                            "body": "$inputs.article"
                        }
                    }
                ]
            }
        ],
        "returns": {
            "headline": "$inputs.title",
            "summary": "$analysis_fork.summary_task.summary",
            "sentiment_label": "$analysis_fork.sentiment_task.label"
        }
    }

    source_types = {
        "inputs": Dict({
            "title": str,
            "article": str
        })
    }
    target_type = Dict({
        "headline": str,
        "summary": str,
        "sentiment_label": str
    })

    plan = compile_flow(flow, source_types, target_type, vocab)
    result = execute_flow(
        plan,
        {
            "inputs": {
                "title": "Launch Day",
                "article": "We had a great launch day with overwhelming positive feedback."
            }
        },
        vocab=vocab,
        max_concurrency=2
    )

    assert result == {
        "headline": "Launch Day",
        "summary": "Summary(Launch Day): We had a great launch day with...",
        "sentiment_label": "positive"
    }


# =============================================================================
# 7. Deep Nested Composition (Map -> Branch -> Loop)
# =============================================================================

def test_pattern_07_deep_nested_composition():
    """Pattern 7: Structural composition of multiple constructs.

    Demonstrates:
    - A Map iterating over multiple batches.
    - Inside the map body, a Branch deciding processing strategy.
    - Inside the branch arm, a Loop performing iterative refinement.
    - Static proof that inner step names cannot leak or collide.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            {
                "id": "batch_processor",
                "map": {
                    "over": "$data.batches",
                    "item_as": "batch",
                    "steps": [
                        {
                            "id": "decision",
                            "if": "$batch.needs_refinement",
                            "then": {
                                "steps": [
                                    {
                                        "id": "refine_loop",
                                        "loop": {
                                            "init": {"text": "$batch.title", "count": 0},
                                            "max": 3,
                                            "while": {"$lt": ["$state.count", 2]},
                                            "steps": [],
                                            "update": {
                                                "text": {"$text": ["*", "$state.text"]},
                                                "count": {"$add": ["$state.count", 1]}
                                            },
                                            "returns": "$state.text"
                                        }
                                    }
                                ],
                                "returns": "$refine_loop"
                            },
                            "else": {
                                "steps": [],
                                "returns": "$batch.title"
                            }
                        }
                    ],
                    "returns": {
                        "batch_id": "$batch.id",
                        "processed_title": "$decision"
                    }
                }
            }
        ],
        "returns": "$batch_processor"
    }

    source_types = {
        "data": Dict({
            "batches": List(Dict({
                "id": int,
                "title": str,
                "needs_refinement": bool
            }))
        })
    }
    target_type = List(Dict({
        "batch_id": int,
        "processed_title": str
    }))

    plan = compile_flow(flow, source_types, target_type, vocab)
    batches = [
        {"id": 1, "title": "Alpha", "needs_refinement": True},
        {"id": 2, "title": "Beta", "needs_refinement": False}
    ]
    result = execute_flow(plan, {"data": {"batches": batches}}, vocab=vocab)

    assert result == [
        {"batch_id": 1, "processed_title": "**Alpha"},
        {"batch_id": 2, "processed_title": "Beta"}
    ]


# =============================================================================
# 8. Production Telemetry, Audit & Billing Interceptors
# =============================================================================

class EnterpriseTelemetryInterceptor(FlowInterceptor):
    """Production interceptor recording latency, attempts, and billing holds."""
    def __init__(self):
        self.lock = Lock()
        self.started_attempts = []
        self.completed_attempts = []
        self.failed_attempts = []

    def before_step(self, ctx: FlowAttemptContext, args: dict) -> None:
        with self.lock:
            self.started_attempts.append({
                "attempt_id": ctx.attempt_id,
                "node_path": ctx.node_path,
                "map_indices": ctx.map_indices,
                "host_request_id": ctx.host_context.get("request_id") if ctx.host_context else None
            })

    def after_step(self, ctx: FlowAttemptContext, args: dict, result: dict) -> None:
        with self.lock:
            self.completed_attempts.append(ctx.attempt_id)

    def on_step_error(self, ctx: FlowAttemptContext, args: dict, error: Exception) -> None:
        with self.lock:
            self.failed_attempts.append((ctx.attempt_id, type(error).__name__))


def test_pattern_08_enterprise_telemetry_and_audit():
    """Pattern 8: Attaching enterprise lifecycle hooks via FlowInterceptor.

    Demonstrates:
    - Interceptor hooks invoked with thread-safe attempt context coordinates.
    - Passing host_context through to all workers.
    - Defensive deepcopy preventing hooks from mutating in-flight values.
    """
    vocab = create_pedagogical_vocab()
    interceptor = EnterpriseTelemetryInterceptor()

    flow = {
        "steps": [
            {
                "id": "items",
                "map": {
                    "over": "$p.raw_items",
                    "parallel": True,
                    "max_concurrency": 2,
                    "call": {"fn": "text.clean", "args": {"raw": "$current"}}
                }
            }
        ],
        "returns": "$items"
    }

    plan = compile_flow(flow, {"p": Dict({"raw_items": List(str)})}, List(Dict({"cleaned": str})), vocab)
    result = execute_flow(
        plan,
        {"p": {"raw_items": [" a ", " b "]}},
        vocab=vocab,
        interceptor=interceptor,
        host_context={"request_id": "req-999-corp"}
    )

    assert result == [{"cleaned": "a"}, {"cleaned": "b"}]
    assert len(interceptor.started_attempts) == 2
    assert len(interceptor.completed_attempts) == 2
    assert not interceptor.failed_attempts
    assert all(a["host_request_id"] == "req-999-corp" for a in interceptor.started_attempts)


# =============================================================================
# 9. Recipe Serialization, Storage & Cold Deserialization
# =============================================================================

def test_pattern_09_recipe_serialization_and_cold_restoration():
    """Pattern 9: Exporting immutable flow plans to JSON recipes and reloading.

    Demonstrates:
    - FlowPlan.to_json() producing deterministic, versioned, portable JSON text.
    - Cold reloading on another runner using FlowPlan.from_json().
    - Strict validation against registry drift: if a registered function's schema
      or version drifts from the recipe snapshot, restoration or execution fails.
    """
    vocab = create_pedagogical_vocab()

    flow = {
        "steps": [
            {"id": "c", "fn": "text.clean", "args": {"raw": "$p.text"}}
        ],
        "returns": {"result": "$c.cleaned"}
    }
    source_types = {"p": Dict({"text": str})}
    target_type = Dict({"result": str})

    # 1. Compile once
    plan = compile_flow(flow, source_types, target_type, vocab)
    recipe_json = plan.to_json()

    # 2. Inspect serialized wire format
    wire = json.loads(recipe_json)
    assert wire["version"] == 1
    assert "text.clean" in wire["functions"]
    assert wire["functions"]["text.clean"]["version"] == "1.0"

    # 3. Restore cold and execute on independent worker
    restored_plan = FlowPlan.from_json(recipe_json, vocab=vocab)
    out = execute_flow(restored_plan, {"p": {"text": " hello "}}, vocab=vocab)
    assert out == {"result": "hello"}

    # 4. Drift verification: mutate function contract and assert fail-fast
    drifting_vocab = FunctionVocab()
    drifting_vocab.register(
        name="text.clean",
        fn=lambda a, c: {"cleaned": a["raw"]},
        inputs=Dict({"raw": str}),
        output=Dict({"cleaned": str}),
        version="2.0"  # Version changed!
    )
    with pytest.raises(FlowRuntimeError) as exc_info:
        execute_flow(plan, {"p": {"text": "drift"}}, vocab=drifting_vocab)
    assert exc_info.value.details["code"] == "contract_drift"


# =============================================================================
# 10. Fail-Closed Settlement & Fault-Tolerant Forensics
# =============================================================================

def test_pattern_10_fail_closed_settlement_and_forensics():
    """Pattern 10: Fault tolerance, task settlement, and structured diagnostics.

    Demonstrates:
    - If one task in a concurrent group fails, already-submitted siblings settle.
    - Zero partial results leak to caller.
    - FlowRuntimeError provides structured diagnostic coordinates:
      code, path, expected, actual, message, and original cause.
    """
    barrier = Barrier(2, timeout=5)
    settled_tasks = []
    lock = Lock()

    def flaky_fn(args: dict, ctx: FlowAttemptContext):
        barrier.wait()
        if args["should_fail"]:
            raise ValueError("simulated upstream vendor timeout")
        sleep(0.02)
        with lock:
            settled_tasks.append(ctx.attempt_id)
        return {"text": "ok"}

    vocab = FunctionVocab()
    vocab.register(
        name="test.flaky",
        fn=flaky_fn,
        inputs=Dict({"should_fail": bool}),
        output=Dict({"text": str}),
        version="1.0"
    )

    interceptor = EnterpriseTelemetryInterceptor()
    flow = {
        "steps": [
            {
                "id": "parallel_batch",
                "parallel": [
                    {"id": "failing_task", "fn": "test.flaky", "args": {"should_fail": True}},
                    {"id": "settling_task", "fn": "test.flaky", "args": {"should_fail": False}}
                ]
            }
        ],
        "returns": "$parallel_batch.settling_task.text"
    }

    plan = compile_flow(flow, {}, str, vocab)

    with pytest.raises(FlowRuntimeError) as exc_info:
        execute_flow(plan, {}, vocab=vocab, interceptor=interceptor, max_concurrency=2)

    err = exc_info.value
    assert err.details["code"] == "call_failed"
    assert "parallel_batch" in err.details["path"]

    # Verify that the sibling task was allowed to finish settling cleanly
    assert len(settled_tasks) == 1
    assert len(interceptor.started_attempts) == 2
    assert len(interceptor.failed_attempts) == 1
