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
| `Promise(T)` | Asynchronous computation handle for `T`; carries `{ "ref": str, "status": str, "result": Nullable(T) }` |


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
