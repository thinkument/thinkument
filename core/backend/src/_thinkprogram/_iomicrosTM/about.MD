# _iomicrosTM — public input/data-atom contract

## Status

This layer is the stable basis for public user-input atoms, typed fill transport,
coercion, reusable semantic validation, cross-field validation, and machine-readable
introspection.

The intended finality claim is **final formalism, open vocabulary**:

- the core rules below should stay small and stable;
- new renderers normally reuse an existing micro type;
- new reusable constraints become validators;
- new cross-field rules become datum validators;
- a new micro type is justified only when canonical value/coercion/interchange
  semantics actually differ.

No finite table can literally enumerate every future domain concept. The point of
this layer is that future concepts usually do **not** require changing the core.

---

## 1. The model in one picture

```text
ThinkWidget / API authors one current-effective datum shell

  datum
  ├── id / title / presentation
  ├── micros[]
  │   ├── name
  │   ├── type  ────────────────┐
  │   ├── required              │
  │   └── validators[]          │
  └── macro_validation_lambdas  │
                                 v
                         _iomicrosTM
                    ┌─────────────────────────┐
                    │ micro capability table  │
                    │ validator registry      │
                    │ coercion graph          │
                    │ datum validators        │
                    │ dead-JSON membrane      │
                    │ publication catalog     │
                    └─────────────────────────┘
                                 │
                                 v
raw candidate
  -> requiredness / blank semantics
  -> activated leaf validators
  -> activated datum validators
  -> canonical coercion
  -> revalidation
  -> strict dead JSON
  -> admitted canonical fill
```

At runtime, a ThinkWidget may then apply later stateful/lifecycle rules to the
platform-admitted candidate. Platform validators answer **“may this data enter?”**;
lifecycle code answers **“what does admitted data mean now?”**

---

## 2. Five things that must not be conflated

| Thing | Owns | Does not own |
|---|---|---|
| **Micro type** | canonical Python value family, JSON schema hint, modality, legal/projectable validator capabilities, coercion/cast edges | every domain rule |
| **Micro instance** | name, type, requiredness, the validators activated for this shell | global registration |
| **Leaf validator** | one micro value + authored args -> `(bool, str | None)` | cross-field state |
| **Datum validator** | a complete macro mapping + authored args -> `(bool, str | None)` | leaf-registry projection metadata |
| **Renderer/widget** | presentation and interaction behavior | redefining canonical value semantics |

The micro table is therefore a **capability sheet**, not a hidden auto-validation
engine. A validator listed on a micro type is legal/projectable for that type;
it executes only when the concrete datum shell activates it.

`ValidatorPolicy.mandatory_enforced` means “hard/projectable when activated.” It
does **not** mean “silently attach this validator to every instance.”

---

## 3. Canonical micro types

The table intentionally contains a few modality variants that share one canonical
value family. That is useful when a form shell needs to preserve input intent while
keeping transport values ordinary JSON.

| Micro type(s) | Canonical Python value | Primary meaning |
|---|---|---|
| `text`, `textarea`, `slug` | `str` | free text / multiline text / authored identifier format |
| `email` | `str` | email-shaped text when its validator is activated |
| `url`, `file_url`, `image_url` | `str` | HTTP(S) references; image URL has image-specific validators |
| `file_filepath`, `image_filepath` | `str` | local path references; existence is outside this layer |
| `date`, `time`, `datetime` | `str` | ISO-style temporal strings |
| `code`, `latex_math` | `str` | code / math fragments; language parsing is external |
| `select` | `str` | one authored option |
| `integer` | `int` | whole number; `bool` excluded |
| `number` | `int | float` | finite JSON number; `bool` excluded |
| `boolean`, `checkbox`, `hidden-pause` | `bool` | boolean semantics; the latter two carry distinct UI/lifecycle intent |
| `multi_select` | `list[str]` | zero or more string options |
| `json_array` | `list` | strict dead-JSON array |
| `json_object` | `dict` | strict dead-JSON object with string keys |
| `object-json` | JSON scalar / `list` / `dict` | any strict dead-JSON value |

### Do not create a new micro type just because a UI control is new

Examples:

| Future input | Prefer |
|---|---|
| phone number | `text` + phone validator |
| color | `text` + pattern/choice validator |
| currency amount | `number` + currency micro/select in the same datum |
| password/secret | `text` plus a secure renderer/persistence policy outside this atom layer |
| rich-text editor | usually `textarea` or a deliberate `json_object` document format |
| coordinates | two `number` micros or a `json_object` |
| audio/video upload | file transport outside this layer; store a `file_url`/`file_filepath` plus metadata |
| domain enum | `select` or `multi_select` + allowed-option validator |

Add a new atom only when its **canonical data contract** deserves a new coercion,
interchange, or capability identity.

---

## 4. The canonical datum shell

A datum is a macro composed of named micros.

```python
datum = {
    "id": "quantity",
    "title": "Quantity",
    "micros": [
        {
            "name": "amount",
            "type": "number",
            "required": True,
            "validators": [
                {
                    "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                    "args": {"min_value": 0},
                },
                {
                    "path": "_thinkprogram._iomicrosTM.validators.number:max_number",
                    "args": {"max_value": 1000},
                },
            ],
        },
        {
            "name": "units",
            "type": "select",
            "required": True,
            "validators": [
                {
                    "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
                    "args": {"options": ["kg", "lb"]},
                }
            ],
        },
    ],
}
```

The canonical full wall is:

```python
from _thinkprogram._iomicrosTM.core.api_fills import parse_validate_and_coerce_macro_fill

canonical = parse_validate_and_coerce_macro_fill(
    datum=datum,
    raw={"amount": "12.5", "units": "kg"},
)

assert canonical == {"amount": 12.5, "units": "kg"}
```

The important order is:

```text
shape + requiredness
  -> activated validators on supplied values
  -> coercion by each micro type
  -> the same semantic validators again
  -> strict dead-JSON assertion
```

Revalidation matters because raw values may be coercible strings while the stored
value must be canonical.

---

## 5. Requiredness and blank semantics

`is_blank_value` is the single platform definition:

```text
blank:
  None
  whitespace-only string
  empty list / tuple / dict
  an explicit box containing one of the above

present:
  0
  False
  nonblank string
  nonempty container
```

Requiredness means **required and nonblank**, not merely “the key exists.”

If a domain must accept an empty JSON object/array as a meaningful value, make
that micro optional at the structural layer. If the *presence of the key itself* must
also be mandatory even when its container is empty, use an explicit datum rule that
checks key membership rather than nonblank requiredness. This keeps one platform
blank definition instead of making requiredness type-dependent.

---

## 6. Boxes are explicit; plain JSON is always data

Transport envelopes must never be inferred merely because an object contains a
`value` key.

### Plain user data

```python
{"value": 1}
```

This is an ordinary JSON object. It stays an ordinary JSON object.

### Explicit leaf box

```python
{
    "__boxed__": True,
    "value": "12",
    "micro_type": "integer",
}
```

### Canonical fill-wire box

```python
{
    "__boxed__": True,
    "value": 12,
    "micro_type": "integer",
    "kind": "fill",
}
```

The canonical layer is:

```python
{
    "values": {
        "sink_id": {
            "micro_name": {
                "__boxed__": True,
                "value": 12,
                "micro_type": "integer",
                "kind": "fill",
            }
        }
    }
}
```

This explicit marker is a control key at the envelope boundary. Do not build new
heuristics such as “a one-key mapping named `value` must be a box.” Such heuristics
make arbitrary JSON-object atoms impossible to represent safely.

---

## 7. Prefills, fills, unions, and transfer

### Prefills and fills

```python
from _thinkprogram._iomicrosTM.core.api_prefills import FormFillsBundleV1

resolver = lambda sink, micro: "integer"

bundle = FormFillsBundleV1.from_any(
    prefills={"count": 2},
    fills={"count": "5"},
    micro_resolver=resolver,
)

assert bundle.get_effective_value("count") == 5
```

Fills overlay prefills by sink + micro.

### No resolver

Untyped convenience input defaults to `text` **and is canonicalized as text**:

```python
bundle = FormFillsBundleV1.from_any(fills={"x": 12})
assert bundle.fills.get_value("x") == "12"
```

An explicit box can self-describe without a resolver:

```python
bundle = FormFillsBundleV1.from_any(
    fills={
        "x": {
            "__boxed__": True,
            "value": "12",
            "micro_type": "integer",
        }
    }
)
assert bundle.fills.get_value("x") == 12
```

### Union resolver

A string is intentionally not guessed when more than one destination type could
own it:

```python
resolver = lambda sink, micro: ("integer", "text")
```

`"12"` is ambiguous. Supply an explicit box with `micro_type`.

Typed scalars may disambiguate only when exactly one allowed micro type matches.

### Transfer

```text
source box type
  -> destination allowed type(s)
  -> exact type if available
  -> otherwise exactly one declared coercion edge
  -> otherwise reject
```

Transfer never invents an undeclared conversion.

---

## 8. Built-in leaf validators

Every registered built-in validator has:

```text
stable import path
+ strict `(bool, str | None)` return contract
+ description
+ one or more argument/example matrices
+ same-module guidance function
```

### Families

| Module | Validators |
|---|---|
| `boolean` | `is_boolean` |
| `choice` | `in_allowed`, `all_in_allowed` |
| `code` | `is_nonempty_code`, `min_code_lines`, `max_code_lines` |
| `collection` | `min_items`, `max_items`, `unique_items` |
| `date` | `is_iso_date`, `is_iso_time`, `is_iso_datetime`, `min_date`, `max_date` |
| `email` | `is_basic_email` |
| `file` | `local_filepath`, `filepath_has_allowed_extension` |
| `image` | `image_url`, `image_url_has_allowed_extension`, `image_filepath` |
| `latex_math` | `is_nonempty_latex` |
| `number` | `is_finite_number`, `is_integer`, `is_positive_int`, `min_number`, `max_number` |
| `object_json` | `is_dead_json`, `is_json_object`, `is_json_array` |
| `text` | `is_nonempty_str`, `min_words`, `max_words`, `min_length`, `max_length`, `pattern` |
| `url` | `is_http_url` |

`time` means local clock time and therefore rejects timezone-bearing forms such as
`09:30Z` or `09:30+01:00`; use `datetime` when an offset belongs in the value.

### Validator helper specs

Helpers such as:

```python
min_number_validator_spec(10)
max_number_validator_spec(20)
pattern_validator_spec(pattern=r"^[A-Z]{3}\d{3}$")
```

are only authoring conveniences. They emit the same canonical spec:

```python
{"path": "module:function", "args": {...}}
```

---

## 9. Datum validators: cross-field rules belong here

Cross-field rules are deliberately **not** leaf-registered.

Built-ins:

| Validator | Meaning |
|---|---|
| `min_words_in_field` | one named text field has at least N words |
| `total_words_max` | total words across selected/all top-level text fields <= N |
| `require_all_or_none` | all named fields are present or all are blank |
| `require_at_least_k` | at least K named fields are nonblank |
| `require_exactly_k` | exactly K named fields are nonblank |
| `fields_equal` | semantic leaf values match |
| `require_field_if_equals` | conditional requiredness based on another semantic value |

Example:

```python
datum = {
    "id": "contact",
    "micros": [
        {"name": "email", "type": "email", "required": False},
        {"name": "phone", "type": "text", "required": False},
    ],
    "macro_validation_lambdas": [
        {
            "path": "_thinkprogram._iomicrosTM.validators.datum:require_at_least_k",
            "args": {"fields": ["email", "phone"], "k": 1},
        }
    ],
}
```

Datum validators use the same explicit semantic-leaf unboxing as leaf validators,
so transport boxes do not change equality or conditional semantics.

---

## 10. Application-owned validators remain open

Built-ins under `_thinkprogram._iomicrosTM.validators.*` must appear in the micro capability
sheet before they can be activated on that micro type.

Application validators are intentionally open:

```python
def project_rule(value, *, prefix: str):
    ok = isinstance(value, str) and value.startswith(prefix)
    return ok, None if ok else f"must start with {prefix!r}"
```

A concrete shell may attach its stable import path without central registration.
That keeps domain code decentralized.

Trade-off: an opaque app validator is executable but does not automatically gain
the platform publication metadata/guidance of a registered built-in validator.
If a rule should become reusable, inspectable, and UI-projectable across apps,
promote it to a built-in validator with full metadata.

---

## 11. Platform validation versus lifecycle validation

Use the earliest layer that has enough information.

```text
stable fact about submitted data?
    yes -> shell/platform validator
    no
state/history/signal/progression dependent?
    yes -> lifecycle/widget rule
```

### Platform validators are for

- numeric bounds;
- formats and regexes;
- allowed choices;
- collection cardinality;
- strict JSON shape;
- stable cross-field invariants.

### Lifecycle rules are for

- attempt counts;
- history-dependent acceptance;
- signal-sensitive behavior;
- contextual coaching;
- dynamic next-shell design;
- progression/accumulation rules.

This is why a signal is a command rather than a micro value. A platform-invalid
fill can be rejected before the widget handler runs; a platform-valid candidate can
later be rejected by lifecycle logic with widget-authored events and re-explosion.

---

## 12. Dead JSON is the public membrane

Accepted public data must satisfy:

```text
scalars: null, string, bool, int, finite float
arrays:  list only
objects: dict only, string keys only
```

Rejected at the membrane:

```text
NaN / ±Infinity
tuples
dataclass instances
non-string object keys
arbitrary Python objects
```

Object normalization is explicit through `coerce_object_json`. Tagged object
reconstruction in `api_object_json` is deny-by-default and requires an explicit
class registry or exact allow surface; never turn user-controlled class names into
an unrestricted import primitive.

---

## 13. Coercion is a declared graph, not “try everything”

`MicroTypeDefinition.coerce_to_micro_types` declares permitted micro-to-micro
edges. `can_coerce_micro` answers graph legality; `coerce_micro_value` still may
reject a particular value.

Example:

```text
text -> integer      declared edge
"12" -> 12          valid value
"twelve" -> error   edge exists, value is not coercible
```

Python casts are separately declared in `python_casts`. A cast must produce the
requested Python type and still pass the dead-JSON membrane.

Do not add fallback conversion chains or silent guessing. Ambiguity is an API fact,
not something to hide.

---

## 14. Introspection is part of the contract

```python
from _thinkprogram._iomicrosTM.core.api_introspection import build_micro_publication_catalog

catalog = build_micro_publication_catalog()
```

The deterministic catalog publishes:

```text
schema id
all public micro definitions
JSON-schema hints
modalities
validator policies and arg maps
canonical Python type paths
coercer paths
micro coercion edges
Python cast paths
registered leaf validators
validator signatures / descriptions / examples / guidance
public datum validators
```

This catalog is the preferred source for generated docs, renderer capability
projection, developer tooling, compatibility checks, and automated validator
matrices. Do not maintain a second hand-written machine registry.

---

## 15. How to grow the system without growing hair

### A. Add a reusable leaf constraint

1. Put it in the narrowest validator module.
2. Signature: `fn(value, *, authored_args...) -> (bool, str | None)`.
3. Use canonical `unwrap`/`unbox_leaf` semantics.
4. Add `@validator` metadata with representative valid and invalid examples.
5. Add same-module `@guidance_for` guidance.
6. Add a `ValidatorPolicy` only to compatible micro types.
7. Let the automatic matrix execute every published example.

Do **not** add a cross-field rule to the leaf registry.

### B. Add a cross-field rule

1. Put it in `validators/datum.py`.
2. Accept the complete macro mapping plus keyword args.
3. Read semantic leaves with `unbox_leaf`.
4. Return `(bool, str | None)`.
5. Give it a docstring so introspection publishes useful meaning.
6. Test boxed and unboxed semantic equivalence where relevant.

### C. Add a new micro type

Only after proving existing types + validators cannot express the canonical data
contract.

Then add, in one change:

```text
MicroTypeDefinition
JSON-schema hint
canonical Python types
coercer
legal/projectable validator policies
coerce_to_micro_types edges
python_casts
identity/coercion matrix sample
registry-integrity assertions
publication-catalog coverage
front-facing docs row
```

A new type with no coercion/interchange story is probably a renderer concern, not
a data atom.

### D. Add a new renderer

Prefer no core change. Renderer selection should be many-to-one over micro types.
If presentation needs extra metadata, keep it in shell presentation/system flags
rather than forking canonical value semantics.

---

## 16. Non-negotiable invariants

```text
1. Plain JSON mappings are data; boxes are explicit.
2. Every canonical fill box carries a known micro_type.
3. Boxed values are canonicalized to that micro type.
4. bool is never silently a number/integer.
5. public floats are finite.
6. malformed nonblank numeric text never becomes missing data.
7. transfer uses only declared coercion edges.
8. ambiguous unions require explicit type information.
9. built-in leaf validators have metadata + guidance + example matrices.
10. cross-field validators do not live in the leaf registry.
11. validators return exactly `(bool, str | None)`.
12. accepted public values cross the strict dead-JSON membrane.
13. app-owned validators stay executable without central enumeration.
14. current-effective shell validators are the active rules; old shells do not
    accumulate into the new shell.
15. lifecycle/stateful semantics stay later than the platform admission wall.
```

If a proposed feature violates one of these, change the feature design rather than
adding an exception to the core.

---

## 17. Test obligations

The durable test shape is matrix-based rather than anecdotal.

### Every built-in leaf validator

```text
description exists
guidance exists
stable import path resolves
all declared valid examples pass
all declared invalid examples fail with a message
return contract is enforced
```

### Every micro type

```text
name/key agree
description exists
modality exists
JSON schema record exists
canonical Python types exist
all coercion destinations exist
validator policies are unique and registered
identity coercion works
all declared coercion edges are exercised
undeclared edges reject
all declared Python casts are exercised
undeclared casts reject
```

### Fill transport

```text
prefill < fill overlay
explicit boxes preserve type
no-resolver values are still type-consistent
union ambiguity rejects
transfer follows only declared edges
plain JSON objects with a `value` key survive unchanged
```

### Security/data membrane

```text
nonfinite numbers reject
non-string JSON keys reject
tuples/dataclasses reject as dead JSON
tagged object reconstruction is deny-by-default
```

---

## 18. Practical authoring recipes

### Required bounded integer

```python
{
    "name": "age",
    "type": "integer",
    "required": True,
    "validators": [
        {
            "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
            "args": {"min_value": 0},
        },
        {
            "path": "_thinkprogram._iomicrosTM.validators.number:max_number",
            "args": {"max_value": 130},
        },
    ],
}
```

### Optional email that is validated when supplied

```python
{
    "name": "email",
    "type": "email",
    "required": False,
    "validators": [
        "_thinkprogram._iomicrosTM.validators.email:is_basic_email",
    ],
}
```

### Required multi-select

```python
{
    "name": "tags",
    "type": "multi_select",
    "required": True,
    "validators": [
        {
            "path": "_thinkprogram._iomicrosTM.validators.choice:all_in_allowed",
            "args": {"options": ["a", "b", "c"]},
        },
        {
            "path": "_thinkprogram._iomicrosTM.validators.collection:min_items",
            "args": {"min_items": 1},
        },
        "_thinkprogram._iomicrosTM.validators.collection:unique_items",
    ],
}
```

### Arbitrary JSON object, including a literal `value` key

```python
datum = {
    "id": "payload",
    "micros": [
        {
            "name": "payload",
            "type": "json_object",
            "required": True,
            "validators": [
                "_thinkprogram._iomicrosTM.validators.object_json:is_json_object"
            ],
        }
    ],
}

raw = {"payload": {"value": 1}}
```

The inner `{"value": 1}` is data, not an envelope.

---

## Final rule of thumb

```text
canonical value shape?          -> micro type
stable local constraint?        -> leaf validator
stable cross-field constraint?  -> datum validator
state/history/workflow rule?    -> lifecycle code
presentation choice?            -> renderer/shell metadata
transport metadata?             -> explicit box
external Python object?         -> normalize to dead JSON
```

Keeping those boundaries intact is what makes the layer scalable. The table can
grow, but the formalism should not.
