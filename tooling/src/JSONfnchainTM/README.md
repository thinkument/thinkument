# JSONfnchainTM — typed JSON-declared function flow engine

`JSONfnchainTM` is a standalone Python 3.10+ package for declaring, statically
compiling, executing, and transporting **five** structured function-flow constructs:
`fn`, `if/then/else`, `map`, `loop`, and `parallel`. Python callables are registered
in an explicit `FunctionVocab`; flow authors supply finite JSON-shaped declarations.
The package has **no direct dependency on Django, Celery, ThinkPrograms, Widgets,
DOMScriptrTM, Playwright, or application services**. Its only internal runtime
package dependency is `bindings2bindingsTM` (Python stdlib otherwise).

The underlying `bindings2bindingsTM` package is neither modified nor made aware of
this engine. All `$` paths, operators, static expression types, and expression values
are handled by the **public** b2b APIs (`D.sugar`, `compile_binding`,
`infer_expression_type`, `reconcile_common_schema`, schema utilities). The new engine
owns only flow structure, registry contracts, lexical step scopes, concurrency,
interceptors, and recipe envelopes. No new expression algebra is introduced here.

## First working flow

```python
from bindings2bindingsTM import Dict
from JSONfnchainTM import (
    FunctionVocab, FlowPlan, compile_flow, execute_flow,
)

vocab = FunctionVocab()
vocab.register(
    name="text.upper",
    fn=lambda args, ctx: {"text": args["text"].upper()},
    inputs=Dict({"text": str}),
    output=Dict({"text": str}),
    version="1.0",
)

flow = {
    "steps": [
        {"id": "headline", "fn": "text.upper", "args": {
            "text": "$parameters.headline"
        }}
    ],
    "returns": {"result": "$headline.text"},
}
plan = compile_flow(
    flow,
    {"parameters": Dict({"headline": str})},
    Dict({"result": str}),
    vocab,
)
assert execute_flow(
    plan, {"parameters": {"headline": "hello world"}}, vocab=vocab,
) == {"result": "HELLO WORLD"}

recipe = plan.to_json()
restored = FlowPlan.from_json(recipe, vocab=vocab)
assert execute_flow(restored,
    {"parameters": {"headline": "portable"}}, vocab=vocab,
) == {"result": "PORTABLE"}
```

### Public API

```python
compile_flow(flow: dict, source_types: dict[str, Schema],
             target_type: Schema | None, vocab: FunctionVocab) -> FlowPlan

execute_flow(plan: FlowPlan, source_values: dict, *,
             vocab: FunctionVocab,
             interceptor: FlowInterceptor | None = None,
             host_context: Any = None,
             max_concurrency: int = 8) -> Any

`FlowPlan.from_json(serialized: str, *, vocab: FunctionVocab) -> FlowPlan
FlowPlan.to_json() -> str
FlowPlan.target_type  # normalized b2b Schema
FlowPlan.function_contracts  # detached serialized signature snapshot
```

### Dedicated Authoring Guide & Platform Execution
For higher-level widget authoring and vocabulary extension instructions, see:
- [`AUTHOR-ME.md`](AUTHOR-ME.md): The definitive guide for public JSONic widget authors and internal developers.
- Dedicated Worker Pools: When executing flows inside Thinkument, flows referencing vendor calls or waiting ops run over `QUEUE_ASYNCWORK` to guarantee sub-10ms interactive dispatches.
- Interceptor Progress Hooks: Use `FlowInterceptor` (`before_step`, `after_step`, `on_step_error`) to emit real-time granular progress events (`asyncwork.progress`).


`FunctionVocab.register` accepts keyword-only `name`, `fn`, `inputs`, `output`,
`version` and optional `replace=False`. Both schemas must be *closed* b2b `Dict`
types; versions are nonempty strings; names are dotted Python-identifier segments.
Duplicate registration fails unless `replace=True`. A registered function must have
the calling convention `fn(args: dict, ctx: FlowAttemptContext) -> dict`.
Functions are called only after their arguments have been evaluated and type-checked;
their returned dictionary is validated with `bindings2bindingsTM.validate` before
being published. No implicit type conversion, union, partial dictionary, or
extra output key is allowed. Source projections are validated by b2b on demand.

## JSON authoring rules and expression delegation

In flow JSON, every field that represents an expression may be:

- a primitive literal such as `17`, `False`, `"hello"`;
- an expression reference `"$parameters.user"`, `"$step.text"`;
- a compact b2b expression `{"$gte": ["$state.score", 0.9]}`;
- a fully canonical b2b AST `{"op":"ref","source":"parameters","path":["user"]}`;
- a nested plain JSON dictionary or list, which the **flow layer** constructs as
  b2b `D.dict` or `D.list` expressions, recursively delegating leaves to `D.sugar`.

The last convention is *deliberately different* from calling `D.sugar` on a plain
non-dollar dictionary by itself. b2b's own documented sugar semantics remain
unchanged (plain containers are literals in b2b). This bridge is required to make
flow `args: {"vars": {"name": "$parameters.name"}}` work without adding an
expression parser. To preserve a literal string beginning in `$`, or a literal
JSON object containing `$` syntax, use `{"$value": ...}`. To build a nested b2b
record explicitly, `{"$dict": {"key": expression}}` also works; follow b2b's
rules for constructing nested values inside compact operators.

**Static type behavior is entirely inherited from b2b:** 39 operators, no implicit
Int/Float mixing, exact finite float checking, nullable and closed dictionary
schemas, short-circuit predicates, `D.item`/`D.outer` for expression-local collection
scopes, filtered selections, and strict literal grammar. Flow does not interpret
strings such as `"$a.b"` itself or implement its own comparison operators.

## The five constructs

### 1. Direct call (`fn`)

```json
{"id":"format_step", "fn":"text.template", "args":{
  "template":"Hello, {name}!", "vars":{"name":"$parameters.user_name"}
}}
```

Only `args` is supported; `inputs`, `bindings`, or other aliases are rejected.
Omitting `args` means `{}`. The function's output is available under
`$format_step` and its fields under `$format_step.field`.

### 2. Branch (`if`/`then`/`else` or `branch` block)

```json
{
  "id":"decision",
  "if":{"$gte":["$parameters.score",0.9]},
  "then":{
    "steps":[{"id":"accept","fn":"review.accept",
              "args":{"id":"$parameters.id"}}],
    "returns":"$accept"
  },
  "else":{
    "steps":[{"id":"reject","fn":"review.reject",
              "args":{"id":"$parameters.id"}}],
    "returns":"$reject"
  }
}
```

A branch with a *value* requires an `else` arm and a typed `returns` expression
in **each arm**. Both arm types must admit a `reconcile_common_schema` result;
otherwise compilation fails. Alternatively, a common top-level `returns` field is
compiled *independently against each arm* if it is valid in both arm scopes.
An arm may be a list of steps (for side effects), or a block with `steps` and
optional `returns`. The equivalent block spelling is
`{"id":"decision", "branch":{"if":..., "then":..., "else":...}}`.

**Important correction to the informal planning example:** A top-level conditional
expression that names both `$accept` and `$reject` cannot compile when these IDs
exist only in disjoint arms. Each private ID is available in **its own arm only**.
Use arm-local `returns` as above, or a common expression referencing only sources
visible from both arms. This prevents invalid cross-branch forward references.

If no returns are declared, the branch is *unvalued*: `else` may be omitted and the
outer branch ID receives the closed empty record `{}`. Both arms' intermediate step
IDs are private. A branch predicate is compiled as b2b `Bool`.

### 3. Map (sequential or concurrent)

```json
{
  "id":"titles",
  "map":{
    "over":"$parameters.documents",
    "item_as":"document",
    "parallel":true,
    "max_concurrency":4,
    "steps":[
      {"id":"up","fn":"text.upper","args":{"text":"$document.title"}}
    ],
    "returns":"$up.text"
  }
}
```

`over` must infer `List(T)`. Each iteration sees `$current` (always), `$index`
(exact 0-based Int), and optionally a nonshadowing alias specified with `item_as`.
All enclosing values available before the map remain visible. Each item has a
private step scope; its intermediate values never escape. The output is a stable,
input-ordered `List(U)`. `steps`+`returns` are mandatory for a multistep map.

Single-call shorthand uses:

```json
{"id":"titles", "map":{
  "over":"$parameters.documents",
  "call":{"fn":"text.upper","args":{"text":"$current.title"}}
}}
```

That form automatically builds a private `_call` node and returns its entire validated
output dict for each item (`List(Dict({...}))`). It cannot be combined with a custom
`steps` or `returns` field. A concurrent map forbids **every** concurrent construct
inside its body (including via nested sequential maps, loops, or branches). Thus
no worker ever blocks waiting for work from the same pool.

### 4. Loop (bounded, stateful)

```json
{"id":"refine", "loop":{
  "init":{"draft":"$parameters.draft", "score":0.0},
  "max":5,
  "on_max":"return_current",
  "while":{"$lt":["$state.score",0.9]},
  "steps":[
    {"id":"rewrite","fn":"llm.rewrite",
     "args":{"text":"$state.draft"}}
  ],
  "update":{"draft":"$rewrite.text", "score":0.95}
}}
```

`init`, `while`, `steps`, `update`, and `max` are mandatory. `max` must be an integer
≥ 0; bool is not an integer ceiling. The loop's `while` is evaluated *before* every
iteration, including after the last allowed update. `$state` is the typed state;
`$iteration` is the zero-based number of iterations already completed. After the
body runs, `update` must type-check **exactly** against the initial state schema.
When a literal `[]` or other ambiguous value needs type guidance, provide a
b2b JSON schema with `state_type`.

If `while` remains true after `max` iterations, `on_max: "raise"` (default) raises
`MaxIterationsExceededError`; `"return_current"` terminates successfully with the
current state. If the guard turns false at exactly the ceiling, **no** max error is
raised. Optional `returns` is evaluated **after** termination and has access to
outer sources, `$state`, and `$iteration`, but **not** to discarded iteration-local
step results. If omitted, the final state itself is returned. No intermediate
iteration results are published into the outer scope.

### 5. Parallel (fork-join, direct calls only)

```json
{"id":"insights", "parallel":[
  {"id":"creative", "fn":"vendor.llm.chat_completion",
   "args":{"prompt":{"$text":["Creative: ","$parameters.brief"]}}},
  {"id":"practical", "fn":"vendor.llm.chat_completion",
   "args":{"prompt":{"$text":["Practical: ","$parameters.brief"]}}}
]}
```

`parallel` accepts **direct calls only** in v1. All child argument bindings are
validated before *any* child starts. Children see their enclosing scope, not sibling
outputs. The parent publishes a closed record:
`{"creative": {"text":...}, "practical":{"text":...}}`.
Use `$insights.creative.text`, not `$creative.text`. An empty `parallel` publishes
`{}`. If a child fails, already submitted siblings are allowed to settle before a
structured error is returned; no child result escapes on failure.

## Lexical names and limits

All flow IDs and source names use `[A-Za-z_][A-Za-z0-9_]*`. Function names are dot-
separated identifiers. Reserved flow identifiers are `item`, `outer`, `current`,
`index`, `state`, and `iteration`; `item` and `outer` retain their distinct b2b
collection-expression roles. A step may not shadow any visible source or prior step.
Branch arm IDs can coincide because their lexical scopes are disjoint. Map aliases
may not shadow any source or reserved name (except the default alias `current`).
A step cannot refer to a later sibling; there is no global DAG scheduler.

Maximum construct nesting is **64** and maximum total nodes is **10,000** including
parallel children and generated map single-call children. Large/deep structure
preflight happens before expensive b2b static compilation. These are structural
limits, not a proof of bounded CPU, output memory, vendor cost, or workload sizes;
host admission controls are required for adversarial inputs.

## Interceptors and attempt identity

Every *started* direct function attempt gets a unique `attempt_id`, plus a unique
per-execution `execution_id`. `FlowAttemptContext` is a frozen dataclass with:

```python
FlowAttemptContext(
    execution_id: str, attempt_id: str,
    node_path: tuple[str | int, ...],
    map_indices: tuple[int, ...],
    loop_iterations: tuple[int, ...],
    host_context: Any = None,
)
```

Immutable **tuples** are used instead of the mutable lists in the original planning
sketch. The `node_path` includes lexical IDs, arm names, and iteration indices.
Retries are not implemented by the core; a caller may run a new execution with new
attempt IDs. Hooks run in the thread executing the actual function call:

```python
from JSONfnchainTM import FlowInterceptor
class MyAudit(FlowInterceptor):
    def before_step(self, ctx, args): ...
    def after_step(self, ctx, args, result): ...
    def on_step_error(self, ctx, args, error): ...
```

`before_step` occurs before invoking the callable; `after_step` only after output
validation succeeds. Any exception from `before_step`, the function, output
validation, or `after_step` invokes `on_step_error` exactly once for that attempt.
A failure *while evaluating arguments* is not a started attempt and has no hooks.
If `on_step_error` itself raises, `error_hook_failed` propagates instead of masking
it as a successful call. Hooks receive defensive copies of args/results; they
cannot rewrite the published value. Subclasses that maintain shared state **must**
implement thread-safety (locks, thread-safe queues, etc.). The base class stores no
shared state and has no host-specific billing behavior.

## Execution and atomicity boundary

A single `ThreadPoolExecutor(max_workers=max_concurrency)` is owned by each flow
execution; default `max_concurrency=8`. Concurrent maps use bounded submission with
at most `min(map.max_concurrency, max_concurrency)` in-flight futures, and preserve
results in input order. `parallel` uses the same pool. The static ban on nested
concurrency inside concurrent map workers avoids pool-starvation deadlocks.

**Atomic means caller-visible results only:** `execute_flow` returns one complete,
validated value or raises `FlowRuntimeError` (including the more specific
`MaxIterationsExceededError`). In a failed fork/join, all already started tasks
settle. It does **not** undo external function side effects, release host holds,
refund payments, or guarantee rollback of calls that already reached a vendor.
These belong to host-specific functions or interceptors. At execute entry, every
referenced function contract is compared against an atomic registry snapshot.
Mismatch fails with `contract_drift` before any calls are dispatched. Replacement
of a registration *during* an execution does not affect its captured callable set.

## Recipe wire format and restoration

`FlowPlan.to_json()` produces deterministic compact sorted-key JSON with exactly:

```json
{
  "version":1,
  "sources":{"parameters":{"kind":"dict","fields":{"text":{"kind":"str"}}}},
  "target":{"kind":"str"},
  "functions":{"text.upper":{"version":"1.0",
    "inputs":{"kind":"dict","fields":{"text":{"kind":"str"}}},
    "output":{"kind":"dict","fields":{"text":{"kind":"str"}}}}},
  "flow":{"steps":[{"id":"a","fn":"text.upper",
    "args":{"op":"dict","fields":{
      "text":{"op":"ref","source":"parameters","path":["text"]}}}}],
    "returns":{"op":"ref","source":"a","path":["text"]}}
}
```

Flow recipe version **1** is independent of b2b recipe version **2**. Only static,
canonical flow structures, b2b ASTs, schemas, function names and versioned contracts
are serialized. Python callables, `FlowAttemptContext`, interceptors, future objects,
source values, and host context never enter a recipe. Restoration checks strict
JSON shape/version, rejects duplicate JSON keys and nonfinite constants, reruns
all grammar, lexical, b2b type, and schema checks and compares exact function
contracts with `vocab`. Noncanonical or tampered envelopes fail closed. No arbitrary
import paths, `eval`, general code execution, or recipe-specified callbacks exist.

A recipe is **not** an authorization boundary on its own. Hosts must still supply an
approved `FunctionVocab`, choose appropriate callables, manage secrets, validate
source provenance, and enforce resource/tenant policies.

## Errors and diagnostics

`FlowCompilationError` and `FlowRuntimeError` derive from `FlowError` and expose
JSON-compatible `details` with `code`, `path`, `expected`, `actual`, and `message`.
The original causal exception is available as `cause` and via exception chaining.

### Comprehensive Diagnostic Code Reference

| Phase | Error Code | Trigger Condition / Description |
| :--- | :--- | :--- |
| **Compile** | `invalid_sources` | `source_types` is not a `dict[str, Schema]` or contains non-string keys. |
| **Compile** | `invalid_target` | `target_type` is not a valid b2b Schema. |
| **Compile** | `invalid_grammar` | Missing required keys, unexpected keys, or invalid block structure. |
| **Compile** | `invalid_identifier` | ID fails regex `[A-Za-z_][A-Za-z0-9_]*` or uses a reserved token (`item`, `outer`, `current`, `index`, `state`, `iteration`). |
| **Compile** | `duplicate_identifier` | Step ID shadows an existing input source, parallel sibling, or earlier step in scope. |
| **Compile** | `unknown_construct` | Step is missing a recognized construct keyword (`fn`, `if`/`branch`, `map`, `loop`, `parallel`). |
| **Compile** | `unknown_function` | Step references a function name not in `FunctionVocab` (emits `difflib` suggestion). |
| **Compile** | `unknown_source` | Expression references an undeclared source or unreachable step (emits `difflib` suggestion). |
| **Compile** | `unknown_field` | Expression references a field nonexistent on a closed record schema (emits `difflib` suggestion). |
| **Compile** | `branch_returns` | Valued branch is missing `else` arm or typed returns in both arms. |
| **Compile** | `incompatible_branches` | Arm return schemas cannot be reconciled with `reconcile_common_schema`. |
| **Compile** | `map_requires_list` | `map.over` expression does not infer a `List(T)` schema. |
| **Compile** | `map_returns` | Multistep map is missing mandatory `steps` or `returns` field. |
| **Compile** | `invalid_loop_max` | `loop.max` is negative or not a strict Python integer. |
| **Compile** | `invalid_on_max` | `loop.on_max` is not one of `"raise"` or `"return_current"`. |
| **Compile** | `loop_state_type` | `loop.update` does not match the initial state schema exactly. |
| **Compile** | `nested_concurrency` | A concurrent map worker body contains a nested `parallel` or another concurrent `map`. |
| **Compile** | `node_count_limit` | Flow AST exceeds 10,000 structural nodes. |
| **Compile** | `construct_nesting_limit` | Construct nesting depth exceeds 64 levels. |
| **Compile** | `invalid_recipe` | Wire JSON is malformed, duplicate-keyed, non-finite, tampered, or version-mismatched. |
| **Runtime** | `contract_drift` | A registered function's schema or version differs from the plan's captured snapshot. |
| **Runtime** | `call_failed` | An invoked Python callable raised an unhandled exception. |
| **Runtime** | `value_type` | Returned dictionary fails output schema validation via `b2b.validate()`. |
| **Runtime** | `closed_fields` | Returned dictionary contains unexpected fields not declared in output schema. |
| **Runtime** | `binding_failed` | Argument or return expression evaluation failed against runtime values. |
| **Runtime** | `error_hook_failed` | An interceptor's `on_step_error` hook raised an exception. |
| **Runtime** | `max_iterations` | Loop reached its iteration ceiling with the `while` guard still true (`on_max="raise"`). |

## Pedagogical Master Test Suite

For runnable, tutorial-grade examples of every applied pattern, inspect:
[`tests/unit/test_JSONfnchainTM_pedagogy.py`](../tests/unit/test_JSONfnchainTM_pedagogy.py)

1. **Pure Data Shaping & Validation (Zero I/O)**: Data transformation and reductions without external callables.
2. **Sequential Multi-Step Pipeline**: Forward parameter passing and cross-step projections.
3. **Valued Branching & Fallbacks**: Conditional routing with schema reconciliation.
4. **Map Operations & Reductions**: Single-call shorthand vs. multi-step maps with `$current`, `$index`, and collection reductions.
5. **Stateful Convergence Loops**: Bounded convergence loops with state dictionaries, ceiling safeguards, and post-loop projections.
6. **Parallel Fork-Join (Fan-Out / Fan-In)**: Concurrent independent calls joined into namespaced records.
7. **Deep Nested Composition**: Composing Map $\to$ Branch $\to$ Loop without scope collisions or thread starvation.
8. **Enterprise Telemetry & Audit Interceptors**: Lifecycle tracking, wall-clock timing, attempt coordinates, and billing holds.
9. **Recipe Serialization & Cold Deserialization**: Precompiled plan persistence, wire validation, and drift detection.
10. **Fail-Closed Settlement & Forensics**: Concurrency settlement on failure, zero partial leakage, and structured diagnostics.

## Testing and packaging

From `independent-tooling`, with `pytest` available:

```sh
PYTHONPATH=src python -m pytest -q \
  tests/unit/test_bindings2bindingsTM.py \
  tests/unit/test_bindings2bindingsTM_scaling.py \
  tests/unit/test_JSONfnchainTM.py \
  tests/unit/test_JSONfnchainTM_scaling.py \
  tests/unit/test_JSONfnchainTM_pedagogy.py \
  tests/integration/test_JSONfnchainTM_installation.py \
  tests/integration/test_bindings2bindingsTM_installation.py
```

The JSONfnchainTM installation test builds a *minimal, backend-free* Python wheel
containing exactly the two standalone packages, installs it with `pip --no-deps`
into a fresh venv, then checks isolated imports, compiled/reloaded flows, and
absence of host application imports. It also verifies the updated Poetry include
entries. That test does **not** certify an end-to-end Poetry build of the entire
parent repository; the original b2b installation test exercises that separate path
and requires `build`, `poetry-core`, and the existing `DOMScriptrTM` and
`serviceCredsTM` sibling sources.

The supplied source snapshot did not include those two unrelated sibling package
implementations. Keep the existing Poetry package entries and overlay this delivery
into the real checkout, where the sibling packages already exist. Do **not** replace
those implementations with empty stubs. The original parent `pyproject.toml` retains
its `playwright` dependency; **that is a parent distribution metadata choice**, not
an import dependency of either independent package. A standalone future distribution
would need its own metadata, but none is invented in this delivery.

These tests use deterministic expected results and report timings without making
machine-specific performance claims. `bindings2bindingsTM` remains independent; it
can be upgraded underneath the flow engine as long as its **documented public APIs
and schema/recipe semantics** remain compatible. No runtime engine can guarantee
compatibility with arbitrary breaking b2b changes; new public b2b operators become
usable through the same delegation without flow-specific operator implementations.

Passing `target_type=None` infers and freezes the return schema using b2b.
Worker tasks inherit separate copies of the caller ContextVars; worker writes do
not mutate the caller context or sibling contexts.
