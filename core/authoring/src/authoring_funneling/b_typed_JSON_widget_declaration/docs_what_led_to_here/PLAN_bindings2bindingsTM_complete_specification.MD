# PLAN: bindings2bindingsTM v2 — Complete Mathematical Specification
## Finalizing the Self-Contained 39-Operator Expression Algebra, Typing & Portability

---

## 1. Executive Summary & Design Invariants

### 1.1 Package Identity & Location
* **Package Name:** `bindings2bindingsTM`
* **Distribution Context:** `thinkument-tooling`
* **Root Location:** [`thinkument/tooling/src/bindings2bindingsTM/`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/)
* **Zero Dependencies:** Pure Python standard library (`json`, `copy`, `functools`, `math`). Zero imports from Thinkument, DOMScriptrTM, Django, Celery, or browser libraries.

### 1.2 The Goal: "Complete in Its Own Bubble"
`bindings2bindingsTM` v2 provides a finite, first-order, statically checked, portable expression language for pure data movement and transformation. It expands from the original 7 v1 operators to a **mathematically complete 39-operator algebra** (including parent-item scoping and pure aggregations).

### 1.3 Confirmed Architectural Invariants
1. **Explicit Opt-In Sugar (`D.sugar`):** Canonical constructors and `node(e)` strictly preserve v1 literal-string semantics (e.g. `D.text("$draft.title")` remains a literal string). Convenient path shorthand (`"$draft.title"`) and compact operators (`{"$gt": ...}`) are parsed only when explicitly requesting `D.sugar(...)`.
2. **Strict Numeric Types (No Implicit Mixing):** No implicit promotion between `Int` and `Float` in arithmetic or comparisons. Mixed numeric operations require explicit `D.to_float(...)`.
3. **Exact Float-to-Int Conversion:** `D.to_int(Float)` succeeds only for finite floating-point values that are exactly integral (`3.0 -> 3`); non-integral floats (`3.7`) raise structured `RuntimeValueError('nonintegral_float')`.
4. **Python-Style Safe Indexing:** `D.index(sequence, idx)` supports negative positions (`-1` = last element). True out-of-bounds indices return `None` (type `Nullable(T)`) without throwing.
5. **Closed Dictionary Merging Only:** `D.merge(*dicts)` accepts closed `Dict` schemas only (known compile-time keys). Colliding keys must have compatible types, and rightmost values take precedence. Open `Map` merges are rejected.
6. **No Global Evaluation Quota:** Synchronous, deterministic evaluation traversing finite selected data. Host applications remain responsible for admission control.
7. **Mandatory `target_type`:** `compile_binding(source_types, target_type, expression)` requires an explicit destination contract.
8. **Enclosing Scope Access (`D.outer`):** Explicit access to parent items in nested `map` and `filter` scopes via compile-time lexical scope stack.
9. **Basic Aggregations:** 5 pure, typed aggregations (`sum`, `any`, `all`, `min`, `max`) with documented empty-collection identities.
10. **Recipe Version Migration:** The compiler emits version `2`. Restored version `1` recipes are verified under v1 grammar and preserved semantically.

---

## 2. The Authoritative 39-Operator Algebra Table

| Category | Operators | Inputs | Output | Empty / Special Semantics |
| :--- | :--- | :--- | :--- | :--- |
| **1. Access & Literal** *(4)* | `value`<br/>`ref`<br/>`item`<br/>`outer` | Literal JSON value<br/>Source name + path<br/>Innermost item path<br/>Enclosing item path (`levels=1`) | Inferred schema<br/>Projected type<br/>Projected item type<br/>Projected outer type | Detached literal; source projection; innermost map/filter item; statically verified parent scope. |
| **2. Structural Construction** *(4)* | `text`<br/>`list`<br/>`dict`<br/>`map` | Nonnullable scalars<br/>Homogeneous items<br/>Named fields<br/>Sequence + Body | `Str`<br/>`List(T)`<br/>Closed `Dict({...})`<br/>`List(U)` | String concatenation; list creation; closed record creation; element-wise list transformation. |
| **3. Conditional & Fallback** *(2)* | `cond`<br/>`default` | `test: Bool, then: T, else: U`<br/>`value: Nullable(T), fallback: T` | `Common(T, U)`<br/>`T` | Short-circuiting ternary selection; null unwrapping with lazy fallback evaluation. |
| **4. Predicates & Logic** *(10)* | `eq`, `neq`<br/>`lt`, `lte`, `gt`, `gte`<br/>`and`, `or`<br/>`not`<br/>`in` | Structurally comparable $T, U$<br/>Same exact scalar: `Int`, `Float`, `Str`<br/>Boolean arguments<br/>Boolean argument<br/>`item: T, List(T)` or `Str, Map(T)\|Dict` | `Bool`<br/>`Bool`<br/>`Bool`<br/>`Bool`<br/>`Bool` | Structural equality; strict orderable comparisons; short-circuiting logic (`and` empty $\to$ `True`, `or` empty $\to$ `False`); negation; collection membership. |
| **5. Pure Arithmetic** *(6)* | `add`, `sub`, `mul`<br/>`div`<br/>`mod`<br/>`neg` | Same-kind `Int` or `Float` pair<br/>Same-kind `Int` or `Float` pair<br/>`Int, Int`<br/>`Int` or `Float` | Same numeric type<br/>`Float`<br/>`Int`<br/>Same numeric type | Exact integer arithmetic / finite float arithmetic; `div` yields `Float` (zero division $\to$ error); Python integer modulo; numeric negation. |
| **6. Sequence & Record Transforms** *(5)* | `size`<br/>`index`<br/>`slice`<br/>`filter`<br/>`merge` | `List`, `Map`, `Dict`, `Str`<br/>`List(T), Int`<br/>`List(T) \| Str, start: Int, end: Nullable(Int)`<br/>`List(T), predicate: Bool`<br/>Closed `Dict` arguments only | `Int`<br/>`Nullable(T)`<br/>`List(T)` or `Str`<br/>`List(T)`<br/>Combined closed `Dict` | Length / Unicode code-point count; Python negative indexing (out-of-bounds $\to$ `None`); Python half-open slice; predicate filtering; rightmost-wins closed dictionary merge. |
| **7. Explicit Casts** *(3)* | `to_str`<br/>`to_int`<br/>`to_float` | `Str`, `Int`, `Float`, `Bool`<br/>`Str`, `Float`, `Bool`<br/>`Str`, `Int` | `Str`<br/>`Int`<br/>`Float` | JSON scalar rendering; exact integral floats only (fractional $\to$ error), `Bool` $\to$ `0/1`, strict decimal strings; finite float coercion. |
| **8. Basic Aggregations** *(5)* | `sum`<br/>`any`<br/>`all`<br/>`min`<br/>`max` | `List(Int)` or `List(Float)`<br/>`List(Bool)`<br/>`List(Bool)`<br/>`List(Int)`, `List(Float)`, `List(Str)`<br/>Same as `min` | `Int` or `Float`<br/>`Bool`<br/>`Bool`<br/>`Nullable(T)`<br/>`Nullable(T)` | Typed zero (`0` or `0.0`); empty $\to$ `False`; empty $\to$ `True`; empty $\to$ `None`; empty $\to$ `None`. |

### 2.1 Canonical AST Representation (`fields` Dictionary)
In [`compiler.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/compiler.py), the `fields` dictionary validates the exact required JSON keys for each operator:
```python
fields = {
    # 1. Access & Literal (4)
    "value": {"value"},
    "ref": {"source", "path"},
    "item": {"path"},
    "outer": {"path", "levels"},
    # 2. Structural Construction (4)
    "text": {"parts"},
    "list": {"items"},
    "dict": {"fields"},
    "map": {"sequence", "body"},
    # 3. Conditional & Fallback (2)
    "cond": {"test", "then", "else"},
    "default": {"value", "fallback"},
    # 4. Predicates & Logic (10)
    "eq": {"left", "right"},
    "neq": {"left", "right"},
    "lt": {"left", "right"},
    "lte": {"left", "right"},
    "gt": {"left", "right"},
    "gte": {"left", "right"},
    "and": {"args"},
    "or": {"args"},
    "not": {"arg"},
    "in": {"item", "collection"},
    # 5. Pure Arithmetic (6)
    "add": {"left", "right"},
    "sub": {"left", "right"},
    "mul": {"left", "right"},
    "div": {"left", "right"},
    "mod": {"left", "right"},
    "neg": {"arg"},
    # 6. Sequence & Record Transforms (5)
    "size": {"value"},
    "index": {"sequence", "index"},
    "slice": {"sequence", "start", "end"},
    "filter": {"sequence", "predicate"},
    "merge": {"dicts"},
    # 7. Explicit Casts (3)
    "to_str": {"value"},
    "to_int": {"value"},
    "to_float": {"value"},
    # 8. Basic Aggregations (5)
    "sum": {"sequence"},
    "any": {"sequence"},
    "all": {"sequence"},
    "min": {"sequence"},
    "max": {"sequence"},
}
```

### 2.2 Error Codes for Runtime and Compilation
* Compilation errors (`CompilationError(code, path, expected, actual)`):
  - `outer_outside_map`: `D.outer` referenced without enclosing collection scope.
  - `invalid_outer_level`: `levels` exceeds available enclosing lexical scopes.
  - `incompatible_branches`: `cond` branch outputs cannot be unified via `reconcile_common_schema`.
  - `mixed_numeric_types`: `Int` and `Float` mixed without explicit `to_float`.
  - `merge_requires_dict`: `merge` passed open `Map` or non-`Dict` schema.
  - `incompatible_merge_key`: `merge` input dicts contain conflicting incompatible types on common keys.
  - `unsupported_aggregation`: `sum`, `min`, `max` called on non-orderable / non-numeric collection.
* Runtime errors (`RuntimeValueError(code, path, expected, actual)`):
  - `division_by_zero`: `div` or `mod` with divisor 0.
  - `nonfinite_float`: Float result is NaN or infinite.
  - `nonintegral_float`: `to_int` called on non-integral float (e.g. `3.7`).
  - `invalid_numeric_cast`: string cannot be parsed as decimal integer or float.

---

## 3. Scoping & Ergonomics: Canonical vs. Sugar

### 3.1 Canonical Python API
Canonical Python builders are strict and unambiguous:
```python
from bindings2bindingsTM import D, Dict, List, compile_binding

# Canonical Python expression
expr = D.dict({
    "approved": D.filter(
        D.ref("candidates"),
        D.gte(D.item("score"), 0.90)
    ),
    "total_score": D.sum(D.map(D.ref("candidates"), D.item("score"))),
    "best_score": D.default(D.max(D.map(D.ref("candidates"), D.item("score"))), 0.0)
})
```

### 3.2 Explicit Opt-in Sugar (`D.sugar`)
`D.sugar(e)` expands compact syntax into canonical AST nodes:
```python
# Authors or higher-level tools (like JSONfnchainTM) explicitly invoke D.sugar
plan_input = D.sugar({
    "$dict": {
        "title": "$draft.title",
        "is_ready": {"$gte": ["$item.score", 0.90]},
        "fallback_label": {"$default": ["$item.label", "Untitled"]}
    }
})
```
* **Escape:** `{"$value": "$draft.title"}` preserves literal strings starting with `$`.
* **Zero Breakage:** Without calling `D.sugar()`, `D.value("$literal")` and `D.text("$literal")` remain literal strings, preserving 100% backward compatibility for all existing v1 tests and programs.

### 3.3 Lexical Scope Stack (`D.item` & `D.outer`)
* `D.item(*path)`: Resolves against the innermost active collection item in a `map` body or `filter` predicate.
* `D.outer(*path, levels=1)`: Resolves against the immediately enclosing collection item. `levels=2` resolves against the grandparent scope, and so on.
* Scope depth is verified statically at compilation time. Referencing `D.outer` outside an enclosing collection fails closed.

---

## 4. Exact File Changes in `thinkument/tooling`

### 4.1 Source Modules in `thinkument/tooling/src/bindings2bindingsTM/`

#### 1. [`types.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/types.py)
* Implement `reconcile_common_schema(s1: Schema, s2: Schema, path: tuple) -> Schema`: Least upper bound calculation within existing schemas (no ad-hoc unions).
* Implement `merge_dict_schemas(*schemas: Schema, path: tuple = ()) -> Schema`: Validates all schemas are closed `Dict`s, verifies compatible key collisions, and returns merged closed `Dict` schema.
* Preserve `Schema` immutability and existing v1 compatibility rules.

#### 2. [`expressions.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/expressions.py)
* Add all 32 new builders to class `D`:
  - Scoping: `D.outer(*path, levels=1)`
  - Conditionals: `D.cond(test, then, else_)`, `D.default(value, fallback)`
  - Comparisons: `D.eq`, `D.neq`, `D.lt`, `D.lte`, `D.gt`, `D.gte`
  - Logic/Membership: `D.and_(*args)`, `D.or_(*args)`, `D.not_(arg)`, `D.in_(item, collection)`
  - Arithmetic: `D.add`, `D.sub`, `D.mul`, `D.div`, `D.mod`, `D.neg`
  - Transforms: `D.size`, `D.index`, `D.slice`, `D.filter`, `D.merge`
  - Casts: `D.to_str`, `D.to_int`, `D.to_float`
  - Aggregations: `D.sum`, `D.any`, `D.all`, `D.min`, `D.max`
* Implement `D.sugar(e)` public entry point and internal `desugar_node(e)` helper.
* Preserve literal string behavior in `node(e)`.

#### 3. [`compiler.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/compiler.py)
* Emit `VERSION = 2`, accept `VERSION in (1, 2)`.
* Implement lexical scope stack in `_check()` tracking `item` and enclosing `outer` levels for `map` and `filter`.
* Extend `fields` dictionary with canonical field definitions for all 39 operators.
* Implement static checking for all new operators, enforcing strict numeric types and lazy branch type validation.
* Freeze immutable instruction proxies and dependency paths.
* **Public Expression Type Inference (`infer_expression_type`):**
  Implement public function `infer_expression_type(source_types: dict[str, Schema], expression: Any, *, expected_type: Schema | None = None) -> Schema`.
  This allows higher-level libraries (such as `JSONfnchainTM`) to infer the schema of an expression (e.g. collection expressions in `map.over` or state initialization in `loop.init`) or verify expected types without reaching into private compiler internals.
* Re-export `infer_expression_type` in `__init__.py`.

#### 4. [`runtime.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/runtime.py)
* Implement pure execution handlers in `run()`:
  - Lazy evaluation for `cond`, `default`, `and_`, `or_`.
  - Python-style indexing with `None` out-of-range return.
  - Strict numeric guards: `division_by_zero`, `nonfinite_float`, `nonintegral_float`, `invalid_numeric_cast`.
  - Half-open slicing, filtering, and rightmost-precedence closed `Dict` merging.
  - Aggregations (`sum`, `any`, `all`, `min`, `max`) with typed empty identities.
  - Scope stack tracking for `outer` item lookups.

#### 5. [`about.MD`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/src/bindings2bindingsTM/about.MD)
* Complete v2 reference guide documenting the 39-operator algebra, typing rules, `D.sugar()` syntax, error details, and zero-scan boundaries.

### 4.2 Test Suite Updates in `thinkument/tooling/tests/`

#### 1. [`tests/unit/test_bindings2bindingsTM.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/tests/unit/test_bindings2bindingsTM.py)
* **Compatibility Correction:** Update existing `test_untrusted_recipe`:
  Change `lambda r: r.update(version=2)` to `lambda r: r.update(version=3)` so valid version 2 recipes are permitted while unsupported versions are rejected.
* Add comprehensive test functions:
  1. `test_conditional_short_circuiting`
  2. `test_default_nullable_unwrapping`
  3. `test_predicate_and_comparison_logic`
  4. `test_pure_arithmetic_precision_and_zero_division`
  5. `test_collection_size_index_slice_filter_merge`
  6. `test_scalar_type_casting`
  7. `test_version_1_recipe_backward_compatibility`
  8. `test_sugar_dot_paths_and_boxing`
  9. `test_sugar_compact_operators_and_escaping`
  10. `test_filter_with_item_scope`
  11. `test_outer_parent_scope_access`
  12. `test_aggregations_sum_any_all_min_max`
  13. `test_merge_with_compatible_key_collisions`
  14. `test_static_rejection_incompatible_branches`
  15. `test_static_rejection_mixed_numeric_types`

#### 2. [`tests/unit/test_bindings2bindingsTM_scaling.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/tooling/tests/unit/test_bindings2bindingsTM_scaling.py)
* Verify zero unrelated-source scanning, cached projection reuse, and bounded restoration cache limits across v2 operators.
