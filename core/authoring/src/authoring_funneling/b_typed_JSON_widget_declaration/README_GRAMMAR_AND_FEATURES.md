# JSON-defined ThinkWidgets: authoring and operational reference

Status: Layer C canonical specification.  
Governing Laws: [Document 20: Philosophies of a Scalable System of Work](../../../about/framework/20_philosophies_of_a_scalable_system_of_work.MD).

Layer C compiles JSON into the existing StrictServiceWidget lifecycle. It embodies
**Philosophy 3: Public JSONic Authoring & The Single-Envelope Doctrine**:
- Authors write **only one JSON declarative envelope**.
- Authors never interact with Celery queues, thread pools, locks, or backend concurrency machinery.
- All capabilities collapse into the **Custom Python Ops Catalogue** and **Vendor Hub Ops Catalogue**.
- **Static Flow Classification**: Pure in-memory transforms execute sync fast-path ($<0.1$ms); any flow calling vendor LLMs or `asyncwork.await_result` automatically delegates to the dedicated `QUEUE_ASYNCWORK` worker pool.
- Step explosions complete in $<5$ms (**Philosophy 2: Dispatches in a Snap**).

## Public entry point


```python
from authoring_funneling import (
    prepare_json_widget_v1, register_prepared_json_widget_v1,
)
prepared = prepare_json_widget_v1(manifest)  # pure validation and compilation
Widget = register_prepared_json_widget_v1(prepared)  # explicit process registration
```

A manifest may be a dictionary or JSON text. Preparation compiles every signal
without changing either widget registry. Duplicate JSON keys, nonfinite values,
unknown manifest fields, invalid schemas and unknown functions fail closed.
Manifests are limited to 1 MB; the flow compiler also enforces its
construct-depth and node-count limits. Register trusted manifests on every
process that may execute them. Upload endpoints, persistent manifest versions
and cross-process publication remain service-host responsibilities.

Registering the same immutable widget ID and fingerprint is idempotent.
Reusing an ID with changed content fails; use a new versioned ID. Custom
`vocab`, `vendor_bindings`, and `base` are trusted Python host capabilities,
never fields selectable by submitted JSON.
A custom base must inherit JsonDefinedLibraryWidget; Metal uses this extension
to retain LibraryWidget shell admission and renderer metadata.

## Manifest grammar

Required root fields: `kind: "json_widget_v1"`, nonempty identifier `name`, and
`signals` containing `mount` and `fill`. Optional root fields: `title` and
`declaration`. The declaration accepts `args`, `inputs`, `outputs`, `fills`, and
`signal`. Arguments use the ordinary widget argument contract (`type`, `default`,
`required`). Inputs and outputs map port names to schemas. Output ports must be
closed records. `fills` and `signal` declare payload schemas, defaulting to maps
of strings; declare richer records explicitly when sending numbers or objects.
The signal namespace contains the incoming signal's `info` payload when present.

Schema shorthands:

| JSON | Meaning |
| --- | --- |
| `"str"`, `"int"`, `"float"`, `"bool"` | Exact primitive types |
| `"str?"` | Nullable string |
| `["int"]` | Homogeneous integer list |
| `{"title":"str","count":"int"}` | Closed record |
| `{"type":"nullable","item":"str"}` | Nullable value |
| `{"type":"list","item":"str"}` | Homogeneous list |
| `{"type":"map","key":"str","value":"int"}` | String-keyed integer map |
| `{"kind":"dict","fields":{...}}` | Canonical b2b schema |

Each signal contains `steps` and `returns`, or inline outcome fields with optional
`steps`. Never mix `returns` with inline outcome fields. Only the canonical
top-level `signals` form is accepted; the removed `transitions` compatibility
shape is rejected.

Every flow sees detached snapshots of exactly five namespaces:

| Namespace | Contents |
| --- | --- |
| `mouth` | Typed input ports captured by Layer B |
| `prior_outputs` | Last accepted output ports; empty during mount |
| `signal` | Declared incoming payload |
| `fills` | Current micro fill values |
| `config` | Declared widget configuration |

A return must contain exactly one lifecycle choice: `done: true`, or
`reexplode: {title, micros}`. Optional fields are `outputs` and `keep`. Outputs
write complete closed records to staged ports; `keep: "*"` preserves ports not
written, and `keep: ["port"]` names specific prior ports. Duplicate keeps,
write/keep overlap, unknown ports and incomplete outputs fail. Mount must supply
initial outputs; there are no previous values to keep. Layer B commits staged
outputs only after the whole transition succeeds and rolls them back on error.

`reexplode` may additionally set `pre_computed_fills` and `micro_placement`.
Micro names must be unique; precomputed fills must name replacement micros.
Micro records use the native kernel grammar and the selected pack's admission
rules. Metal writes placement to its native `paquete_micro_placement` shell field.
All lists remain subject to b2b's homogeneous type rules: records in a list must
have compatible shapes. Empty or heterogeneous dynamic collections may need
explicit typed function results rather than inference from an ambiguous literal.

## Default vocabulary

| Name | Inputs | Result |
| --- | --- | --- |
| `text.template` | template string, string map vars | text |
| `text.concat` | string list parts, string sep | text |
| `math.add`, `math.multiply` | numeric a, b | numeric result |
| `data.extract` | string map source, string key | nullable string value |
| `vendor.llm.chat_completion` | prompt, nullable model, nullable temperature | text, prompt/completion token usage |
| `vendor.embeddings.generate` | text, nullable model | float vector, dimensions |

Contracts are exact: include nullable argument keys with `null` when unspecified.
Templates replace only simple `{{name}}` tokens; they do not evaluate Jinja,
Python, imports, attributes or arbitrary code. Missing variables raise errors.
Functions are approved by a trusted FunctionVocab; a JSON author cannot register
or import a callable. A plan freezes function contracts, and each execution
snapshots compatible registrations before starting any work.

## Vendor integration and concurrency

There is no automatic test mode and no synthetic provider result selected by an
environment flag. Tests inject explicit prepared-call fakes or pure vocabulary
functions to isolate orchestration. A vendor function without a trusted binding
fails before dispatch.

Pass `vendor_bindings={"vendor.llm.chat_completion": VendorBinding(prepare,
project)}` to the factory. `prepare(args)` returns the keyword arguments for
`widget.execute_vendor_operation_v1`: a prepared call, client, quoted maximum
units, and optional authoritative read-only cost lookup. `project(VendorResult)`
returns the exact function result record. `create_gateway_vendor_binding(ops,
operation_id, request=..., project=...)` performs this adaptation using Vendor
Hub's prepare/quote API. Model routes, credentials and operation policy belong
to this trusted host setup. Examples deliberately require this explicit binding
before their paid `generate` signal can run.

Layer A reserves credits before the prepared call executes, resolves and charges
its authoritative usage before returning, and releases remaining holds during
cleanup. Layer C never infers a charge from a projected token dictionary and
never makes a second reservation in its interceptor. Calls use unique lifecycle
operation/attempt keys. Successful external calls and settled charges remain
real when a sibling fails; only local staged widget outputs roll back.

Flow fan-out is bounded to eight workers per widget execution. Each task inherits
an independent copy of host ContextVars, including accounting and storage
bindings. Worker vendor callbacks close their Django connections in `finally`;
the caller's connections remain owned by the caller. Fork/join waits for started
work to settle before surfacing an error. Widget audit emission uses one
instance lock around envelope creation, emission and index advancement, so
concurrent usage spans cannot reuse an event index. Different widgets and runs
retain their own locks.

## Examples and verification

Crystal's `json_widgets/crystal_ideator.json` and Metal's
`shared_widgets/json_widgets/metal_ideator.json` demonstrate mount replacement,
parallel generation, refreshed precomputed fills, and terminal accepted output.
Both use ordinary strict ports. Metal publishes the same widget across standard
and compact chromes; Crystal has no dependency on Metal rendering.

Use the registered runners so the selected service sheet, dependency locks,
package prerequisites, advisory DB lock and normal Django teardown apply:

```sh
python3 _cicd/cicd/modules/pkgs/run-package-tests.py service-innovations --subset all
rav run test_pkg_tkt_innovations_npm
```

For focused work, repeat `--target tests/...py` on the package runner. The
service's run_tests registration also includes the Layer C unit and integration
modules. Never create or delete an isolated test database manually to bypass
admission. When changing the browser catalogue under a sheet that publishes
static releases, run `rav run collectstatic_tkt` before browser acceptance tests.

This is a registered-callable execution boundary, not a general hostile-code
sandbox. Hosts must still limit input sizes, admit provider operations and
apply their normal API/run quotas before exposing future upload surfaces.

## Complete underlying flow and expression references

The following reference sections describe the engines Layer C consumes. Their
own APIs can describe flows independently of widgets; only the five namespaces
and lifecycle outcomes above are specific to Layer C.


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

FlowPlan.from_json(serialized: str, *, vocab: FunctionVocab) -> FlowPlan
FlowPlan.to_json() -> str
FlowPlan.target_type  # normalized b2b Schema
FlowPlan.function_contracts  # detached serialized signature snapshot
```

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
`independent-tooling/tests/integration/test_JSONfnchainTM_pedagogy.py`

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

# bindings2bindingsTM v2 — portable, typed expression algebra

An independent, **standard-library-only** Python package distributed by the existing
`independent-tooling` project. It does not import Thinkument, DOMScriptrTM, Django,
Celery, Playwright, web APIs, or application services. It evaluates finite, first-order,
side-effect-free expression trees over explicitly supplied JSON-shaped values.

## Quick start

```python
from bindings2bindingsTM import (
    D, Dict, List, Nullable, Map, compile_binding, BindingPlan,
    infer_expression_type,
)

candidate = Dict({"score": float, "label": str})
expr = D.dict({
    "approved": D.filter(D.ref("candidates"), D.gte(D.item("score"), 0.90)),
    "total_score": D.sum(D.map(D.ref("candidates"), D.item("score"))),
    "best_score": D.default(
        D.max(D.map(D.ref("candidates"), D.item("score"))), 0.0
    ),
})
target = Dict({"approved": List(candidate), "total_score": float, "best_score": float})
plan = compile_binding({"candidates": List(candidate)}, target, expr)
result = plan.evaluate({"candidates": [
    {"score": 0.8, "label": "review"},
    {"score": 0.95, "label": "approved"},
]})
assert result == {
    "approved": [{"score": 0.95, "label": "approved"}],
    "total_score": 1.75, "best_score": 0.95,
}
restored = BindingPlan.from_json(plan.to_json())
assert restored.evaluate({"candidates": []}) == {
    "approved": [], "total_score": 0.0, "best_score": 0.0,
}
assert infer_expression_type({"candidates": List(candidate)},
                             D.map(D.ref("candidates"), D.item("label"))) == List(str)
```

`compile_binding(source_types, target_type, expression)` **always requires the explicit
`target_type`**. `infer_expression_type(source_types, expression, *, expected_type=None)`
infers its schema, optionally using an expected schema for ambiguous empty/null literals
and checking that the result fits the expected type. Both validate complete expression
grammars statically; neither runs expressions or reads source values.

## Type system and normalization

| Type | Meaning / exact runtime Python representation |
|---|---|
| `Str` / `str` | Python `str` (Unicode code-point semantics) |
| `Int` / `int` | Python exact `int`; **not** `bool` |
| `Float` / `float` | Finite Python `float` only; **not** `int` |
| `Bool` / `bool` | Python `bool` only |
| `Nullable(T)` | `None` or `T`; nested nullability collapses |
| `List(T)` | Python `list` whose elements each validate against `T` |
| `Dict({name: T, ...})` | Closed Python `dict` with **exactly** the declared string keys |
| `Map(T)` | Open Python `dict` with arbitrary string keys, homogeneous `T` values |

`Schema` objects are immutable and hold indexed, read-only field maps. `normalize(...)`
accepts type constructors, schemas, or the public JSON schema grammar. Input types are
checked without implicit conversions: `int` never fits `float`, `bool` never fits `int`,
`Nullable(T)` never fits a non-null destination, and an open `Map(T)` cannot be assumed
to contain the fields of a closed `Dict`. A closed `Dict` fits `Map(T)` if all its field
types fit `T`. Lists and maps are covariant structurally. No arbitrary unions, optional
record keys, functions, Python objects, recursive schemas, or custom predicates exist.

`reconcile_common_schema(a, b, path=())` returns a representable common supertype
when one exists: identical shapes; `T` and `Nullable(T)` become `Nullable(T)`;
compatible list/map element types reconcile recursively; closed records with the same
keys reconcile fieldwise. A closed record may widen to a homogeneous `Map(T)` where
every member of both operands fits a representable common `T`. There is **no**
`Int`/`Float` promotion and no general union construction. Irreconcilable branches
raise `incompatible_branches`.

`merge_dict_schemas(*schemas, path=())` accepts closed `Dict` schemas only, combines
known keys and reconciles colliding field schemas (possibly widening to `Nullable`).
At runtime the **rightmost value wins**, including `None`. This helper's reconciled
type is a safe over-approximation when a key's value differs between inputs.

## Complete v2 operator set — exactly 39

AST nodes are JSON objects with an `"op"` tag and **exactly** the keys below. No extra
keys, unknown operations, invalid paths, or executable callbacks are accepted.
Canonical `D` helpers construct these nodes; Python values passed to helpers are boxed
as `{"op":"value","value":...}`. `D.value(...)` is the explicit literal constructor.

| Category | Operator (`D` method) | Required AST keys after `op` | Input → output and special semantics |
|---|---|---|---|
| Access (4) | `value` | `value` | Finite JSON literal → inferred schema; ambiguous `None`/`[]` require a hint. |
| | `ref` | `source`, `path` | Named source + string-segment array → projected schema. |
| | `item` | `path` | Current `map`/`filter` item projection. |
| | `outer` | `path`, `levels` | Enclosing lexical item projection; positive integer `levels`, default 1. |
| Structural (4) | `text` | `parts` | Non-null `Str`/`Int`/`Float`/`Bool` → `Str`, concatenated. |
| | `list` | `items` | Homogeneous item expressions → `List(T)`. |
| | `dict` | `fields` | Name → expression object → closed `Dict({...})`. |
| | `map` | `sequence`, `body` | `List(T)` + item-scoped expression `U` → `List(U)`. |
| Conditional (2) | `cond` | `test`, `then`, `else` | `Bool`, branches → common schema; evaluate **only** chosen branch. |
| | `default` | `value`, `fallback` | `Nullable(T)` and compatible nonnullable fallback → `T`; lazy fallback. |
| Predicates (10) | `eq`, `neq` | `left`, `right` | Structurally comparable operands → `Bool`. |
| | `lt`, `lte`, `gt`, `gte` | `left`, `right` | Exact same `Int`/`Float`/`Str` types → `Bool`. |
| | `and`, `or` (`D.and_`, `D.or_`) | `args` | Bool array → Bool; left-to-right short circuit. |
| | `not` (`D.not_`) | `arg` | Bool → Bool. |
| | `in` (`D.in_`) | `item`, `collection` | `T` in `List(T)` or `Str` as a key in `Map`/`Dict` → Bool. |
| Arithmetic (6) | `add`, `sub`, `mul` | `left`, `right` | Same-kind `Int` or `Float` → same type. |
| | `div` | `left`, `right` | Same-kind `Int` or `Float` → finite `Float`. |
| | `mod` | `left`, `right` | `Int`, `Int` → `Int`, Python modulo sign semantics. |
| | `neg` | `arg` | `Int` or `Float` → same type. |
| Transforms (5) | `size` | `value` | `Str`/`List`/`Map`/`Dict` → `Int` count. |
| | `index` | `sequence`, `index` | `List(T)`, `Int` → `Nullable(T)`; negative index; true OOB → `None`. |
| | `slice` | `sequence`, `start`, `end` | `List(T)` or `Str`, Int start and Nullable(Int) end → same sequence type. |
| | `filter` | `sequence`, `predicate` | `List(T)`, scoped Bool predicate → `List(T)`. |
| | `merge` | `dicts` | Array of closed `Dict`s → merged closed `Dict`, rightmost wins. |
| Casts (3) | `to_str` | `value` | Non-null scalar → `Str`, JSON scalar rendering. |
| | `to_int` | `value` | `Str`/`Float`/`Bool` → `Int`; exact integral floats only. |
| | `to_float` | `value` | `Str`/`Int` → finite `Float`. |
| Aggregations (5) | `sum` | `sequence` | `List(Int)` → `Int`; `List(Float)` → `Float`. |
| | `any`, `all` | `sequence` | `List(Bool)` → `Bool`. |
| | `min`, `max` | `sequence` | `List(Int/Float/Str)` → `Nullable(T)`. |

For `D.slice(sequence, start)`, `end` is emitted explicitly as a literal `None`.
Half-open slicing follows Python `sequence[start:end]` and supports negative or
out-of-range endpoints. `size` counts Unicode **code points**, not UTF-8 bytes or
grapheme clusters. `in` does not implement substring search. `and`/`or` are the
canonical AST names; the Python methods have trailing underscores to avoid syntax
keywords. All operands and all *possible* branches must type-check at compile time,
even when runtime short-circuiting avoids their execution.

### Empty collections and numeric invariants

| Expression | Empty input result |
|---|---|
| `D.and_()` | `True` |
| `D.or_()` | `False` |
| `D.sum(List(Int))` | `0` (type `int`) |
| `D.sum(List(Float))` | `0.0` (type `float`) |
| `D.any(List(Bool))` | `False` |
| `D.all(List(Bool))` | `True` |
| `D.min` / `D.max` | `None` |
| `D.index([], index)` | `None` |
| `D.merge()` | `{}` (closed empty `Dict`) |

Integer addition, subtraction, multiplication, negation, sum, and modulo retain Python
arbitrary-precision integers; division always computes a finite float or raises a
structured error. Float arithmetic is finite-only; zero divisors raise
`division_by_zero`, and overflowing floats raise `nonfinite_float`. Mixed `Int` and
`Float` numeric expressions are rejected with `mixed_numeric_types`; explicitly call
`D.to_float(int_expr)` to combine them. `D.to_int(3.0)` → `3`, while
`D.to_int(3.7)` raises `nonintegral_float`. Bool → int is `0`/`1`. Strings for
`to_int` use signed base-10 integer notation without whitespace, separators, or
leading zero padding except `0`; `to_float` accepts signed decimal/exponent notation
without whitespace, hexadecimal, underscores, `NaN`, or `Inf`. Valid decimal strings
that overflow to infinity raise `nonfinite_float`. `to_str` preserves string operands,
and JSON-renders other scalars (`True` → `"true"`, `2.0` → `"2.0"`).

### Lexical scopes

`D.item(*path)` references the innermost item inside `D.map` or `D.filter`.
`D.outer(*path, levels=1)` references the immediately enclosing item; `levels=2`
references its parent. For instance:

```python
expr = D.map(D.ref("groups"), D.map(D.item("rows"),
    D.text(D.outer("name"), ":", D.item("score"))))
```

The compiler checks these references against a *lexical stack of schemas*, not
runtime guessing. Each collection `map` or `filter` pushes exactly one scope for its
body/predicate. `outer` with no enclosing item raises `outer_outside_map`; an invalid
positive level beyond available parents raises `invalid_outer_level`. `D.item`
outside all item scopes raises `item_outside_map`. Parent projections have a separate
per-parent-item cache and are validated once per item/projection.

## Sugar is opt-in, never implicit

Canonical helpers and `node(e)` retain v1 semantics:

```python
D.text("$draft.title")        # literal text, NOT a reference
D.value("$draft.title")       # literal string
D.value({"$gt": [1, 2]})     # literal object, not a comparison
```

Only `D.sugar(...)` interprets a dollar-prefixed string or compact `$operator`:

```python
expression = D.sugar({"$dict": {
    "title": "$draft.title",
    "is_ready": {"$gte": ["$item.score", 0.90]},
    "fallback_label": {"$default": ["$item.label", "Untitled"]},
    "literal": {"$value": "$draft.title"},
}})
```

* `"$draft.title"` becomes `D.ref("draft", "title")`; `"$item.score"` becomes
  `D.item("score")`; `"$outer.field"` becomes `D.outer("field")`;
  `"$outer2.name"` means `D.outer("name", levels=2)`. Dot splitting occurs **only**
  in sugar. For source names or field names containing dots, use canonical `D.ref`.
* `{"$value": value}` boxes `value` **as-is**, no nested expansion. Any already
  canonical `{"op": ...}` expression is copied unchanged; mixing sugar inside such a
  canonical subtree does not recursively desugar it.
* `{"$dict": {"field": expression}}` recursively expands named fields.
  `{"$list": [expression, ...]}` and `{"$text": [...]}` recursively expand members.
* `{"$add": [a,b]}`, `{"$eq": [a,b]}`, `{"$default": [a,b]}` and other binary
  operators use a two-element array. `{"$in": [item, collection]}` uses the same.
  `{"$and": [a,b,...]}`, `{"$or": [...]}`, and `{"$merge": [...]}` are variadic.
  Unary `{"$not": x}`, `{"$neg": x}`, `{"$size": x}`, `{"$to_int": x}`,
  `{"$sum": x}`, etc. accept one expression as their value.
* `{"$map": [sequence, body]}` and `{"$filter": [sequence, predicate]}` take two
  elements; `{"$cond": [test, then, else]}` and
  `{"$slice": [sequence, start, end]}` take three.
  `{"$ref": [source, ...path]}`, `{"$item": [...path]}` and
  `{"$outer": [...path]}` are available when array-form paths are convenient.
* Plain non-dollar dictionaries and arrays passed to `D.sugar` are treated as
  **literal** JSON values, not implicitly interpreted as record/list constructors.
  A single unrecognized `$operator` is rejected with `invalid_sugar`.

`D.sugar` returns inert canonical AST, suitable for `compile_binding`. No expression
evaluator ever treats `$` in a literal string as executable path shorthand.

## JSON wire grammar and version migration

A recipe is a JSON object with **exactly** four fields:

```json
{
  "version": 2,
  "sources": {"draft": {"kind": "dict", "fields": {"title": {"kind": "str"}}}},
  "target": {"kind": "str"},
  "expression": {"op": "ref", "source": "draft", "path": ["title"]}
}
```

`compile_binding` emits **version 2**. `BindingPlan.from_json` accepts version 1
recipes under the original seven operators (`value`, `ref`, `item`, `text`, `list`,
`dict`, `map`) and version 2 recipes under all 39 operators. A restored version 1
plan re-serializes with version 1, and cannot introduce new operations by editing
the version field. Unsupported versions, duplicate JSON keys, extra fields,
malformed schemas/expressions, and forged `certified` fields fail closed.

A compiled `BindingPlan` exposes `target_type`, immutable `dependencies` of the form
`((source_name, (path_segment, ...)), ...)`, `to_json()`, and `evaluate(values)`.
Instructions, schema indexes, dependency tuples, and source/target schemas are
immutable; literal values are JSON encoded in instructions. The 128-entry LRU
restoration cache stores **only verified plans**, never source data. A separate
4096-entry cache stores schema compatibility results. Both caches are bounded.

## Evaluation and zero-scan boundary

A direct `D.ref("source", "field")` validates and deep-copies *only that selected
projection*; it does not validate or enumerate unrelated root fields. A whole-source
`D.ref("source")` validates the whole selected source. A selected `List` or `Map`
projection necessarily validates its whole selected container and its members before
mapping, indexing, slicing, filtering, or aggregation. This is not a claim of O(1)
access to arbitrarily large selected collections. Repeated references to the same
source/path are validated once per invocation, even if copied many times into output.
Map/filter item projections are validated once **per item**; parent projections are
cached **per enclosing item scope**. No cached input values survive an invocation.

The evaluation complexity is O(selected input validation and copying + executed AST
operations + constructed output), not O(total unrelated source data). Repeated
projection outputs still require detached copies. Nested maps intentionally multiply
work. Compile/restore costs (schema normalization, expression checking, encoding,
freezing) are separate. There is **no global evaluation work quota**; host applications
must apply admission controls for large inputs, nested iterations, expression size,
resource usage, and potentially adversarial data. Execution is synchronous and pure.
The host must keep input values stable during evaluation. Returned lists/dicts are
fresh mutable values detached from the inputs and plan.

Schema nesting is bounded to 64, expression/JSON-container nesting to 128. Inputs and
outputs are finite and JSON-shaped, except arbitrary-precision Python `Int` where
JSON serialization may remain subject to the host interpreter's integer-digit limit.
No global state, network, filesystem, random numbers, callbacks, clock, hidden
source traversal, or application runtime integration is part of the library.

## Structured errors

`CompilationError` and `RuntimeValueError` both derive from `BindingError`, carrying
JSON-compatible `details = {"code": ..., "path": [...], "expected": ..., "actual": ...}`.
Compilation checks exact operators, fields, schemas, source names, path segments,
scopes, branch reconciliation, numeric compatibility, and `target_type`. Runtime
checks the selected projections and guards applicable operations. Notable codes:

| Phase | Code | Meaning |
|---|---|---|
| Compile | `invalid_expression`, `invalid_sugar`, `invalid_recipe` | Noncanonical AST, bad opt-in sugar, or untrusted serialized recipe. |
| Compile | `unknown_source`, `unknown_field`, `invalid_path` | Invalid static source projection. |
| Compile | `item_outside_map`, `outer_outside_map`, `invalid_outer_level` | Invalid lexical collection scope reference. |
| Compile | `incompatible_branches`, `default_requires_nullable`, `default_requires_nonnull_fallback` | Incompatible conditional/fallback contracts. |
| Compile | `mixed_numeric_types`, `arithmetic_types`, `comparison_types`, `incomparable_types` | Disallowed type mix or operand type. |
| Compile | `merge_requires_dict`, `incompatible_merge_key` | Open map or incompatible closed-record merge. |
| Compile | `unsupported_aggregation`, `target_type` | Ineligible aggregation operand or incompatible destination schema. |
| Compile | `ambiguous_null`, `ambiguous_empty_list`, `heterogeneous_list` | Insufficient or conflicting literal inference. |
| Runtime | `missing_source`, `missing_projection`, `closed_fields`, `value_type` | Missing or ill-typed selected source data. |
| Runtime | `division_by_zero`, `nonfinite_float` | Bad division/modulo divisor or non-finite float. |
| Runtime | `nonintegral_float`, `invalid_numeric_cast` | Inexact float-to-int conversion or invalid decimal cast. |

Errors are not certificates that a host's resource or concurrency invariants hold.

## Tests and installation

Run from an existing `independent-tooling` checkout with its packaging metadata and
`pytest` available:

```sh
PYTHONPATH=src python -m pytest -q tests/unit/test_bindings2bindingsTM.py tests/unit/test_bindings2bindingsTM_scaling.py
python -m pytest -q tests/integration/test_bindings2bindingsTM_installation.py
```

The integration test builds an actual `independent-tooling` wheel using `python -m
build`, installs it with no dependencies in an isolated Python venv, verifies the
restored bindings expression, and checks for prohibited imports and distributions.
It requires the parent project's `pyproject.toml`/packaging configuration and the
`build` tool. This nine-file update **does not include or invent** parent packaging
metadata. Unit and scaling tests can be run using `PYTHONPATH` as above independently
of that packaging configuration.
