# PLAN: JSONfnchainTM — Standalone JSON-Declared Function Flow Runtime
## Authoritative Tooling Specification with Adaptive $b2b$ Delegation, Bounded Concurrency, Typed Lexical Scopes & Atomic Execution

---

## 1. Executive Summary & Architectural Invariants

### 1.1 Package Identity & Location
* **Package Name:** `JSONfnchainTM`
* **Root Location:** [`thinkument/tooling/src/JSONfnchainTM/`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/)
* **Sibling Packages:** `bindings2bindingsTM`, `DOMScriptrTM`
* **Dependencies:** Pure Python ($\ge 3.10$), `bindings2bindingsTM` (for schema verification, expression parsing, and binding evaluation). **Zero dependencies** on Django, Celery, ThinkPrograms, or Widgets.

### 1.2 Core Purpose & DX Philosophy
`JSONfnchainTM` is the standalone, statically verified runtime for declaring, compiling, and executing chains of function calls entirely in JSON. It provides:
1. **Developer-First Ergonomics:** Clean, modern syntax with zero AST boilerplate (`"args"`, flat `"if"`/`"then"`/`"else"`, `"over"`, `"init"`, `"update"`, `"$path"` string references, and primitive auto-boxing).
2. **Dual-Phase Safety:**
   * **Static Compilation (`compile_flow`):** Verifies all references, input/output schemas, construct nesting, identifier collisions, and function contracts before any runtime execution begins. Emits helpful diagnostic error messages with "Did you mean?" suggestions on typos.
   * **Atomic Runtime Execution (`execute_flow`):** Executes nodes sequentially or concurrently, delegating parameter mapping and value delivery to compiled $b2b$ recipes. From the caller's perspective, execution is atomic: it either returns the complete, validated result or raises a structured `FlowRuntimeError`.
3. **Bounded I/O Concurrency (`parallel` & concurrent `map`):** Supports fanning out independent I/O-bound operations (e.g. parallel vendor LLM calls) concurrently using a bounded thread pool, joining results before proceeding. Started tasks settle on failure to prevent orphaned work.
4. **Execution Interceptors & Attempt Identity:** A clean lifecycle hook protocol (`before_step`, `after_step`, `on_step_error`) with unique `attempt_id` coordinates, allowing host applications to attach telemetry, billing, or audit holds without leaking host concerns into the core engine.
5. **Deterministic Recipe Portability:** Serialized recipes store only versioned canonical flow structures, verified function contracts, and canonical $b2b$ ASTs. No Python callables, execution states, or thread futures are ever serialized.

---

## 2. Adaptive Integration with $b2b$

A foundational design requirement is that **`JSONfnchainTM` delegates pure expression parsing, typing, and evaluation to `bindings2bindingsTM` without duplicating $b2b$ logic**.

### 2.1 The Opaque Expression Delegation Pattern via `D.sugar()`
In `JSONfnchainTM`, the runtime and compiler never attempt to parse individual expression tokens or interpret paths inside bindings. Instead, `JSONfnchainTM` delegates shorthand parsing directly to `bindings2bindingsTM.D.sugar(step.args)` before passing the canonical AST to `compile_binding`:

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│ JSONfnchainTM Flow Node (Author writes clean, ergonomic JSON)                    │
│   id: "generate_summary"                                                         │
│   fn: "llm.summarize"                                                            │
│   args: {                                                                        │
│     "text":    "$extract_step.body",                                             │
│     "length":  250,                                                              │
│     "flag":    {"$cond": ["$step_0.valid", true, false]}                         │
│   }                                                                              │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼ (Lowers via b2b D.sugar into canonical AST)
┌──────────────────────────────────────────────────────────────────────────────────┐
│ bindings2bindingsTM Compiler                                                     │
│   sources_schema = { "parameters": Schema(...), "extract_step": Schema(...) }    │
│   target_schema  = fn_def.inputs_schema                                          │
│   canonical_expr = D.sugar(node.args)                                            │
│                                                                                  │
│   -> compile_binding(sources_schema, target_schema, canonical_expr)              │
│   -> returns BindingPlan (immutable, serialized v2 recipe)                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Reusing the Complete 39-Operator $b2b$ Expression Algebra
As detailed in [`PLAN_bindings2bindingsTM_complete_specification.MD`](file:///Users/adarshjeewajee/Desktop/startups/PLAN_bindings2bindingsTM_complete_specification.MD), $b2b$ provides a mathematically complete 39-operator table:
* **Rich In-Line Bindings:** Inside any `CallNode`, bindings can use `D.cond` (ternary), `D.default` (null-coalescing), `D.filter`, `D.merge`, `D.outer` (parent scope), aggregations (`sum`, `any`, `all`, `min`, `max`), and pure arithmetic without custom Python glue functions.
* **Native Predicates for Flow Control:** `BranchNode` conditions (`if`) and `LoopNode` termination checks (`while`) are directly authored as $b2b$ boolean expressions (`$gt`, `$eq`, `$and`, `$not`, `$in`, `$all`, `$any`), validated at compile-time to return `Schema("bool")`.

### 2.3 Public Type Inference via `infer_expression_type`
To inspect collection item schemas (`map.over`) or state schemas (`loop.init`) without reaching into private $b2b$ internals, `JSONfnchainTM` relies on $b2b$'s public helper:
```python
infer_expression_type(source_types: dict[str, Schema], expression: Any, *, expected_type: Schema | None = None) -> Schema
```
This preserves a clean, sanctioned integration boundary between the two packages.

---

## 3. The Polished 5-Construct Grammar Specification

```mermaid
flowchart TD
    START([Start Flow]) --> N0{"Node Type"}
    
    subgraph 1. Call
        N0 -->|fn| C1["Evaluate args b2b binding against current scope"]
        C1 --> C2["Invoke interceptor.before_step(ctx, args)"]
        C2 --> C3["Invoke registered fn(args, ctx)"]
        C3 --> C4["Validate return dict against output_schema"]
        C4 --> C5["Invoke interceptor.after_step(ctx, args, result)"]
        C5 --> C6["Store result in scope under node.id"]
    end

    subgraph 2. Branch
        N0 -->|if / then / else| B1["Evaluate if predicate (b2b Bool)"]
        B1 -->|True| B2["Execute then sub-flow"]
        B1 -->|False| B3["Execute else sub-flow (or no-op)"]
        B2 --> B4["Publish reconciled returns under node.id"]
        B3 --> B4
    end

    subgraph 3. Map
        N0 -->|map| M1["Evaluate over expression to List(T)"]
        M1 --> M2["For each item: bind $current, $index; run body"]
        M2 --> M3["Collect results into ordered List"]
        M3 --> M4["Store List in scope under node.id"]
    end

    subgraph 4. Loop
        N0 -->|loop| L1["Initialize state from init (or state_type)"]
        L1 --> L2{"Iteration < max AND while predicate True?"}
        L2 -->|Yes| L3["Execute loop steps with $state, $iteration"]
        L3 --> L4["Evaluate update b2b expression -> new state"]
        L4 --> L5["Discard iteration step results; iter++"]
        L5 --> L2
        L2 -->|No| L6["Evaluate returns (or return state)"]
        L6 --> L7["Store loop result in scope under node.id"]
    end

    subgraph 5. Parallel (Fork-Join)
        N0 -->|parallel| P1["Evaluate input bindings for all child calls"]
        P1 --> P2["Fan out calls concurrently via ThreadPoolExecutor"]
        P2 --> P3["Wait for all calls to settle (join)"]
        P3 --> P4["Publish closed Dict under node.id: {child_id: result}"]
    end
    
    C6 --> NEXT{"More Nodes?"}
    B4 --> NEXT
    M4 --> NEXT
    L7 --> NEXT
    P4 --> NEXT
    NEXT -->|Yes| N0
    NEXT -->|No| END_FLOW["Evaluate final flow returns expression"]
```

### 3.1 Construct Specifications & Rules

#### 1. `CallNode` (Direct Function Execution)
* **Ergonomic Syntax:**
  ```json
  {
    "id": "format_step",
    "fn": "text.template",
    "args": {
      "template": "Hello, {name}!",
      "vars": {"name": "$parameters.user_name"}
    }
  }
  ```
* **Grammar Invariant:** The parameter key is strictly `"args"`. Speculative aliases (`"inputs"`, `"bindings"`) are rejected to keep the grammar clean and canonical. If a function accepts no parameters, `"args"` may be omitted (defaults to `{}`).
* **Result Publishing:** The validated output of the registered function is published in scope under `node.id`.

#### 2. `BranchNode` (Conditional Routing)
* **Ergonomic Syntax (Flat & Block Forms):**
  ```json
  {
    "id": "check_status",
    "if": {"$gt": ["$step_a.score", 0.85]},
    "then": [
      {
        "id": "accept",
        "fn": "review.accept",
        "args": {"id": "$parameters.id"}
      }
    ],
    "else": [
      {
        "id": "reject",
        "fn": "review.reject",
        "args": {"id": "$parameters.id"}
      }
    ],
    "returns": {"$cond": [{"$gt": ["$step_a.score", 0.85]}, "$accept", "$reject"]}
  }
  ```
* **Block Synonym:** `"branch": {"if": ..., "then": ..., "else": ..., "returns": ...}` is also supported.
* **Valued vs. Unvalued Branches:**
  - **Valued Branch:** When the branch provides a result to subsequent steps, both `then` and `else` arms must explicitly specify `returns`. Both branch result schemas are statically reconciled using $b2b$'s `reconcile_common_schema`. The chosen result is published under `node.id`.
  - **Unvalued Branch (Side Effects Only):** When `returns` is omitted, `else` may also be omitted. The branch publishes `{}` under `node.id`.
* **Scope Isolation:** Step IDs inside `then` and `else` blocks are private to their respective arms and do not leak into the outer scope.

#### 3. `MapNode` (Batch Mapping with Optional Concurrency)
* **Ergonomic Syntax:**
  ```json
  {
    "id": "summaries",
    "map": {
      "over": "$step_a.documents",
      "item_as": "doc",
      "parallel": true,
      "max_concurrency": 4,
      "steps": [ ... ],
      "returns": "$summarize.text"
    }
  }
  ```
* **Single-Call Sugar:** For simple 1-to-1 transforms, authors can write:
  ```json
  {
    "id": "uppercase_titles",
    "map": {
      "over": "$step_a.documents",
      "call": {
        "fn": "text.uppercase",
        "args": {"text": "$current.title"}
      }
    }
  }
  ```
* **Identifiers & Scoping:**
  - Default item binding: `$current`. Custom alias: `"item_as": "name"`.
  - Positional index: `$index: Int`.
  - Multistep maps require explicit `"returns"`.
  - Item-local steps are discarded after each item executes.
  - The map publishes an ordered `List(T)` under `node.id`.

#### 4. `LoopNode` (Stateful Bounded Iteration)
* **Ergonomic Syntax:**
  ```json
  {
    "id": "refine_draft",
    "loop": {
      "init": {"draft": "$mouth.draft", "score": 0.0},
      "max": 5,
      "on_max": "return_current",
      "while": {"$lt": ["$state.score", 0.90]},
      "steps": [ ... ],
      "update": {
        "draft": "$rewrite.text",
        "score": "$critique.score"
      }
    }
  }
  ```
* **Field Rules:**
  - `"init"`: Initial state expression. Optional `"state_type"` schema can be provided if `init` is ambiguous (e.g. empty list).
  - `"max"`: Required non-negative integer iteration ceiling.
  - `"on_max"`: `"raise"` (default, raises `MaxIterationsExceededError`) or `"return_current"`.
  - `"while"`: $b2b$ boolean predicate evaluated before each iteration.
  - `"update"`: Expression evaluated at the end of each iteration to produce the next `$state`. Must match the initial state schema exactly.
  - `"returns"`: Optional. If omitted, returns the final `$state`.
* **Intermediate Step Isolation:** Step outputs inside loop iterations are discarded at the end of each iteration to prevent stale state accumulation. The loop publishes its final outcome under `node.id`.

#### 5. `ParallelNode` (Concurrent Fork-Join Fan-Out)
* **Ergonomic Syntax:**
  ```json
  {
    "id": "gather_insights",
    "parallel": [
      {
        "id": "creative_draft",
        "fn": "vendor.llm.chat_completion",
        "args": {"prompt": {"$text": ["Creative: ", "$mouth.brief"]}}
      },
      {
        "id": "practical_draft",
        "fn": "vendor.llm.chat_completion",
        "args": {"prompt": {"$text": ["Practical: ", "$mouth.brief"]}}
      }
    ]
  }
  ```
* **Child Step Restriction:** In v1, `parallel` contains direct `CallNode` children only. This avoids nested scheduler deadlocks.
* **Namespaced Publication:** The outputs of child calls are published as a closed `Dict` under the parallel node's ID:
  ```text
  $gather_insights.creative_draft.text
  $gather_insights.practical_draft.text
  ```
  Child IDs do not flatten into the parent scope, preventing naming collisions.
* **Concurrency Settlement:** If any child call fails, started sibling calls are allowed to settle before `FlowRuntimeError` is raised, ensuring clean credit and telemetry tracking.

---

## 4. Scoping & Lexical Rules

### 4.1 Identifier Rules
* Identifier syntax: `[A-Za-z_][A-Za-z0-9_]*`
* Function names may be dotted (e.g. `vendor.llm.chat_completion`).
* **Reserved Identifiers:**
  - `item`, `outer`: Reserved for $b2b$ expression collection scopes.
  - `current`, `index`: Flow map item and positional index.
  - `state`, `iteration`: Flow loop state and 0-based iteration index.
* Node IDs within the same lexical scope must be unique and cannot shadow visible external sources.

### 4.2 Structural Lexical Ordering (No DAG Complexity)
Execution order is structurally defined:
* Sequential step lists run in order.
* Forward references to later steps are rejected statically during compilation.
* Because the execution flow is structurally determined by the 5 constructs, no arbitrary topological sort or general DAG scheduler is needed.

---

## 5. Function Registry (`FunctionVocab`) & Interceptor Contract

### 5.1 Function Registration & Contract Snapshots
`FunctionVocab` manages approved Python callables:
```python
vocab = FunctionVocab()
vocab.register(
    name="vendor.llm.chat_completion",
    fn=my_llm_callable,
    inputs=Dict({"prompt": Str}),
    output=Dict({"text": Str}),
    version="1.0"
)
```
* **Contract Verification:** At the beginning of `execute_flow`, the engine captures a snapshot of referenced function signatures and versions. If a function signature drifts, execution fails before any calls are dispatched.

### 5.2 Attempt Identity & Lifecycle Interceptor
Every function attempt receives a unique `FlowAttemptContext`:
```python
@dataclass(frozen=True)
class FlowAttemptContext:
    execution_id: str
    attempt_id: str
    node_path: list[str | int]
    map_indices: list[int]
    loop_iterations: list[int]
    host_context: Any = None
```
Hooks in `FlowInterceptor`:
```python
class FlowInterceptor:
    def before_step(self, ctx: FlowAttemptContext, args: dict[str, Any]) -> None:
        pass

    def after_step(self, ctx: FlowAttemptContext, args: dict[str, Any], result: dict[str, Any]) -> None:
        pass

    def on_step_error(self, ctx: FlowAttemptContext, args: dict[str, Any], error: Exception) -> None:
        pass
```
* Hooks are called symmetrically for every started function attempt.
* Telemetry, billing, and credit holds use `ctx.attempt_id` as their stable, thread-safe key.

---

## 6. Execution Model & Bounded Concurrency

### 6.1 Single Bounded Thread Pool
* Concurrent operations (`parallel` and concurrent `map`) share a single bounded `ThreadPoolExecutor` per flow execution.
* Default execution-wide concurrency ceiling: `8` (host-configurable).
* Concurrent maps enforce bounded in-flight task scheduling so massive lists do not flood memory or thread queues.
* **Deadlock Protection:** A concurrent map body cannot contain another concurrent construct.

### 6.2 Atomic Execution Guarantee
* `execute_flow` returns either the complete, validated result or raises `FlowRuntimeError`.
* No partial states or resumable cursors are exposed.
* In-flight tasks settle before failure propagation. The core library does not claim automatic rollback of external side effects; external transactionality belongs to host applications and registered functions.

---

## 7. Portable Recipes & Security Verification

### 7.1 Recipe Envelope (Version 1)
Canonical serialization produces portable JSON:
```json
{
  "version": 1,
  "sources": {
    "parameters": {"kind": "dict", "fields": {"brief": {"kind": "str"}}}
  },
  "target": {
    "kind": "dict", "fields": {"result": {"kind": "str"}}
  },
  "functions": {
    "vendor.llm.chat_completion": {
      "version": "1.0",
      "inputs": {"kind": "dict", "fields": {"prompt": {"kind": "str"}}},
      "output": {"kind": "dict", "fields": {"text": {"kind": "str"}}}
    }
  },
  "flow": {
    "steps": [ ... canonical normalized AST nodes ... ],
    "returns": { ... b2b canonical AST ... }
  }
}
```

### 7.2 Restoration Safety
* `FlowPlan.from_json(recipe, vocab=vocab)`:
  - Re-verifies JSON grammar and versions.
  - Matches recorded function contracts against supplied vocabulary.
  - Recompiles canonical b2b ASTs.
  - Re-runs all lexical and type checks.
  - Rejects arbitrary imports, execution state, or tampered signatures.
* Structural bounds: Maximum construct nesting depth = `64`, maximum flow nodes = `10,000`.

---

## 8. World-Class Static Diagnostics ("Did you mean?")

To provide an exceptional developer experience, `compile_flow` uses standard library `difflib.get_close_matches`:
* **Function Typo Detection:**
  `FlowCompilationError: Step 'llm_step' references unknown function 'vendor.llm.chat_complation'. Did you mean 'vendor.llm.chat_completion'?`
* **Scope Reference Typo Detection:**
  `FlowCompilationError: Step 'llm_step' references unknown field 'contex' on source 'mouth'. Did you mean 'context'?`

---

## 9. Exact Files to Add and Modify in `thinkument/tooling`

### 9.1 Packaging
* **File to Modify:** [`thinkument/tooling/pyproject.toml`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/pyproject.toml)
* **Change:** Add `{ include = "JSONfnchainTM", from = "src" }` to `tool.poetry.packages`.

### 9.2 Source Modules in `thinkument/tooling/src/JSONfnchainTM/`
1. [`__init__.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/__init__.py): Public API exports (`compile_flow`, `execute_flow`, `FunctionVocab`, `FlowPlan`, `FlowInterceptor`, `FlowAttemptContext`, exceptions).
2. [`errors.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/errors.py): Structured exceptions (`FlowCompilationError`, `FlowRuntimeError`, `MaxIterationsExceededError`) with diagnostic details.
3. [`vocab.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/vocab.py): `FunctionVocab` with contract snapshotting and closest-match search.
4. [`grammar.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/grammar.py): AST nodes (`CallNode`, `BranchNode`, `MapNode`, `LoopNode`, `ParallelNode`), reserved identifier checks, and canonical normalization.
5. [`compiler.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/compiler.py): Lexical scope stack, static type reconciliation via `reconcile_common_schema`, expression lowering via `D.sugar`, `infer_expression_type` delegation, and "Did you mean?" suggestions.
6. [`runtime.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/runtime.py): Sequential driver, branch evaluation, map/loop runners, and bounded `ThreadPoolExecutor` concurrent fork-join dispatcher.
7. [`interceptor.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/interceptor.py): Thread-safe `FlowInterceptor` base class and `FlowAttemptContext`.

### 9.3 Documentation & Test Suite
* Add [`thinkument/tooling/src/JSONfnchainTM/README.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/JSONfnchainTM/).
* Add unit test suite [`thinkument/tooling/tests/unit/test_JSONfnchainTM.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/tests/unit/test_JSONfnchainTM.py):
  1. `test_vocab_registration_and_schema_validation`
  2. `test_linear_call_chain_with_canonical_args`
  3. `test_branching_conditional_flat_if_then_else`
  4. `test_map_iteration_with_default_current`
  5. `test_map_iteration_single_call_sugar`
  6. `test_stateful_loop_init_update_and_default_return`
  7. `test_stateful_loop_max_iterations_return_current`
  8. `test_parallel_fork_join_concurrency_and_namespacing`
  9. `test_flow_interceptor_lifecycle_and_attempt_identity`
  10. `test_static_rejection_with_did_you_mean_suggestion`
  11. `test_runtime_error_fail_closed_and_settlement`
  12. `test_plan_serialization_roundtrip_v1`
* Add scaling test suite [`thinkument/tooling/tests/unit/test_JSONfnchainTM_scaling.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/tests/unit/test_JSONfnchainTM_scaling.py).
* Add integration test suite [`thinkument/tooling/tests/integration/test_JSONfnchainTM_installation.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/tests/integration/test_JSONfnchainTM_installation.py).
