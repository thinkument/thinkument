# Metal

Metal owns shared typed widgets/rendering and generates `metal_standard` and `metal_compact`. Both are analytics/economics/managed-storage-ready through the common mould.

# Metal family — Creative Developer Sheet

**Build reusable typed widgets once. Publish each supported chrome as its own selectable pack.**

Metal owns the shared widget and rendering library and publishes `metal_standard` and `metal_compact` from one codebase. Both use the `authoring_funneling.a_typed_PSMCW_authoring` contracts over the same service-ready computation mould. Chrome selection changes presentation while preserving widget behavior and typed data flow.

The generation rule is **one shared widget/rendering library plus K chromeset
declarations produces K app packs**. Widgets and renderers are reused across
those K packs; Metal does not generate a pack for each widget/chrome pairing.
Each composed pack is finalized through the checked HAI `defineAppPackV1`
factory after Metal adapts its local slots.

## 1. The platform you are authoring against

Every chrome app pack combines:

**The shared widget library + the shared micro subtables + one aesthetic collection.**

Adding a widget or micro makes it available to every chrome variant. Adding an aesthetic collection publishes another selectable app pack using those same implementations.

| Contribution or surface | Owns |
|---|---|
| Python widget | Domain behavior, strict inputs and outputs, lifecycle transitions, emitted shells |
| Micro definition | Data semantics, coercion and declared validation capabilities |
| Micro JavaScript renderer | Editing/display mechanics for that micro's descriptor and value |
| Widget JavaScript renderer | Widget display mechanics and micro composition |
| Aesthetic collection | Fulfillment of the presentation slots |
| P | Widget appearances, execution order, bindings, parameters and appearance overrides |
| SM | Chrome selection, widget placement, visibility and ordinary session policies |
| C | Customization through declared ordinary symbols |
| Widget fill shell | The emitted micros and their placement inside the widget |

Presentation choices preserve execution order, data dependencies, validation, role restrictions and continuity behavior.

The two supplied chrome IDs are:

- `metal_standard` — the default.
- `metal_compact`.

These are ordinary app-pack IDs selected through `SM.app_pack_mould.app_pack`.

The central sheets are `THINKWIDGETS` in [shared_widgets/widgets.py](shared_widgets/widgets.py), `MICRO_TABLES` in [shared_widgets/micros.py](shared_widgets/micros.py), and `CHROMETABLES` in [per_pack_chromesets/declarations.py](per_pack_chromesets/declarations.py). Widgets and micro definitions have one implementation each; chrome variants share them rather than carrying library copies.

## 2. Start from the public authoring surface

```python
from authoring_funneling.examples.metal import (
    D,
    Str, Int, Float, Bool, Nullable, List, Dict, Map,
    LibraryWidget,
    strict_widget,
    analytica_signal_catcher,
    with_aesthetics,
    compile_tape,
)
```

Use the family's `LibraryWidget` and `strict_widget` when contributing to its central widget sheet. They supply strict authoring, the widget's mechanics selector, and emitted-shell admission.

Inspect the currently published contracts rather than guessing a widget's ports:

```python
from authoring_funnel.b_service_ready_typed_PSMCW_authoring.authoring import resolve_authoring_profile

profile = resolve_authoring_profile("metal_standard")

descriptor = profile.describe()
widgets = profile.describe_widgets()
```

The common profile interface is:

| Method | Purpose |
|---|---|
| `describe()` | Profile identity, partial discovery schemas, operations and restrictions |
| `describe_widgets()` | Available widget IDs, ports and configuration |
| `validate(draft)` | Compile and return a structured success receipt or the first failure |
| `compile(draft)` | Ordinary executable P/SM/C export |

A profile draft contains exactly `profile_id`, `W`, `P`, `SM`, and `C`. `W` lists the selected registered widget IDs. `compile_tape()` derives that selection from P for you.

All creativity publication rows require an explicit strict profile. Strict compilation is enforced at the authoring boundary; the lower platform launch protocol remains ordinary P/SM/C.

Descriptors do not constitute a complete P/SM/C validator. Use `validate` or `compile` against the registered implementations. Drafts carry no widget code, callables or arbitrary import paths.

## 3. Compose P with precise data contracts

### Higher-P grammar

Higher P is ordinary `think_program_v1` with `bindings` added to widget declarations and appearance overrides. Compilation removes those additions and generates ordinary args and history wires. The following are the authoring fields; `?` means optional. Unknown keys are rejected on the P envelope, program, info, widget, flow item and ordinary overrides. Strict bindings are checked for each effective appearance; unused widget declarations still require a registered strict contract and valid ordinary fields.

| Object | Required fields | Optional fields and defaults |
|---|---|---|
| P | `kind: "think_program_v1"`, `surface_version: "v1"`, `run` | `symbols: {}`, `puppeteering: {}` |
| `run` | `program` | `config: {}` (ordinary run configuration); this object is not a closed strict schema |
| `run.program` | `info`, `widgets: {logical_id: Widget}`, `flow: [Step, ...]` | None |
| `info` | `id`, `title` (nonempty) | `description`, `args` (ordinary info metadata) |
| Widget | `widget` (registered implementation ID) | `args: {}`, `bindings: {}`, `title` (logical ID), `lifecycle`, `tags: []`, `roles: []`, `system_flags: {}`, `authoritative: True`; empty `wires` only |
| Step | `id`, `widgets: [logical_id, ...]` | `title` (step ID), `roles: []`, `authoritative: [bool, ...]`, `overrides: {}` |
| `overrides` | None | `args`, `lifecycle`, `system_flags`, `tags`, `roles`, `title`, `bindings`: each `{logical_id: replacement_or_patch}`; empty `wires` only |
| Bindings | None | `sources: {alias: Source}`, `parameters: {name: Parameter}`, `inputs: {port: Expression}`; each defaults to `{}` |
| Source | Exactly `widget: logical_id` or `widget: {"self": "previous"}`, and `port: output_port` | None |
| Parameter | Exactly `type: Type`, `value: ordinary_authored_value` | None |

`flow` and each step's `widgets` must be nonempty. Flow IDs are unique; a step cannot repeat a logical widget. Each referenced widget must be declared; override targets must belong to that step. Logical widgets may recur in later steps. A step's optional `authoritative` list must match its widget count and contain booleans; every generated span needs at least one authoritative widget.

Widget `args` are configuration, validated against the registered ordinary argument contract for required fields, supplied value types and unknown arguments. Declared defaults belong to ordinary widget metadata; P lowering does not insert them into authored args. They are separate from typed input ports. Ordinary argument types have their own rules: for example, an ordinary `float` arg accepts an integer, while a strict `float` port does not.

`tags` and `roles` are string lists; `args`, `lifecycle` and `system_flags` are mappings. Ordinary titles use the framework's string normalization and widget `authoritative` uses boolean coercion; these fields do not acquire strict port semantics. `info.description` and `info.args` are accepted metadata but do not affect generated execution steps.

Ordinary `args`, `lifecycle` and `system_flags` overrides merge recursively; `tags`, `roles` and `title` overrides replace the corresponding value. Default lifecycle limits are `max_reexplosions=10`, `max_proc_notes=0`, `max_messages=8`; `mount_explode` is forced to `True`. Other lifecycle/flag admission remains the ordinary kernel's responsibility.

Do not author `micros` anywhere under `run.program`, including nested ordinary args or parameter values: the lower P parser rejects that key recursively. Widgets emit micro descriptors in lifecycle shells. Expression record keys live inside serialized recipes after compilation, so they are not ordinary P argument keys.

### Widget identities and appearances

A registered widget ID identifies an implementation. A logical widget name identifies its use in your program. A flow step identifies an appearance of one or more logical widgets.

```python
{
    "widgets": {
        "writer": {
            "widget": "metal.seed",
            "args": {"title": "Proposal", "count": 2},
            "bindings": {},
        }
    },
    "flow": [
        {"id": "write", "widgets": ["writer"]}
    ],
}
```

Program IDs, flow IDs and logical widget IDs must be nonempty literal strings, without dollar signs or surrounding whitespace.

A logical widget may appear again in a later step. Every appearance mounts with that step's effective configuration and bindings.

### Types

| Python declaration | Serialized Type (exact keys) | Meaning |
|---|---|---|
| `str` / `Str` | `{"kind": "str"}` | Exact string |
| `int` / `Int` | `{"kind": "int"}` | Exact integer |
| `float` / `Float` | `{"kind": "float"}` | Exact finite float |
| `bool` / `Bool` | `{"kind": "bool"}` | Exact boolean |
| `Nullable(T)` | `{"kind": "nullable", "item": Type}` | T or `None` |
| `List(T)` | `{"kind": "list", "item": Type}` | Homogeneous list |
| `Dict({"field": T, ...})` | `{"kind": "dict", "fields": {"field": Type, ...}}` | Closed record with precisely declared fields |
| `Map(T)` | `{"kind": "map", "item": Type}` | String-keyed map with values of T |

Every output port must be a closed `Dict` record. Inputs may use any supported type.

Exact types matter: `True` does not satisfy `int`, and an integer does not automatically satisfy `float`. Nullability must be declared. Schema nesting is bounded to 64; expression/JSON nesting is bounded to 128.

Compatibility allows T into `Nullable(T)` and a closed record into a map when every field fits the map's value type. Lists/maps compare their item types recursively; records require the same field set with compatible field types. A nullable source cannot satisfy a nonnullable target. There are no numeric casts or implicit defaults. Type field names are strings; port names must also be nonempty.

### Bindings

Each widget's `bindings` may contain:

```python
{
    "sources": {
        "draft": {"widget": "writer", "port": "result"},
    },
    "parameters": {
        "prefix": {"type": str, "value": "$copy.prefix"},
    },
    "inputs": {
        "title": D.text(
            D.ref("parameters", "prefix"),
            ": ",
            D.ref("draft", "title"),
        ),
    },
}
```

Effective bindings accept only `sources`, `parameters` and `inputs`. Bind exactly every declared input port at every appearance. Each expression must produce a type compatible with its input's declared target.

| Python expression | Serialized Expression (exact keys) | Capability |
|---|---|---|
| `D.value(value)` | `{"op": "value", "value": JSON}` | Literal JSON value |
| `D.ref(source, *path)` | `{"op": "ref", "source": alias, "path": [string, ...]}` | Select a whole source port or nested field |
| `D.item(*path)` | `{"op": "item", "path": [string, ...]}` | Select the current item inside a map/filter |
| `D.outer(*path, levels=1)` | `{"op": "outer", "path": [string, ...], "levels": int}` | Access parent collection item in nested map/filter |
| `D.text(*parts)` | `{"op": "text", "parts": [Expression, ...]}` | Concatenate nonnullable scalar values |
| `D.list(*items)` | `{"op": "list", "items": [Expression, ...]}` | Construct a homogeneous list |
| `D.dict(fields)` | `{"op": "dict", "fields": {string: Expression, ...}}` | Construct a record or compatible map |
| `D.map(sequence, body)` | `{"op": "map", "sequence": Expression, "body": Expression}` | Transform a nonnullable list |
| `D.filter(sequence, predicate)` | `{"op": "filter", "sequence": Expression, "predicate": Expression}` | Filter a list by boolean expression |
| `D.cond(test, then, else_)` | `{"op": "cond", "test": Expr, "then": Expr, "else": Expr}` | Short-circuiting ternary selection |
| `D.default(value, fallback)` | `{"op": "default", "value": Expr, "fallback": Expr}` | Null-coalescing with lazy fallback |
| `D.eq`, `D.neq`, `D.lt`, `D.lte`, `D.gt`, `D.gte` | `{"op": op, "left": Expr, "right": Expr}` | Strict typed comparisons |
| `D.and_`, `D.or_`, `D.not_`, `D.in_` | `{"op": op, ...}` | Boolean logic & membership |
| `D.add`, `D.sub`, `D.mul`, `D.div`, `D.mod`, `D.neg` | `{"op": op, ...}` | Pure arithmetic with numeric safety |
| `D.size`, `D.index`, `D.slice`, `D.merge` | `{"op": op, ...}` | Length, safe indexing, slicing, closed record merge |
| `D.to_str`, `D.to_int`, `D.to_float` | `{"op": op, "value": Expr}` | Explicit scalar type casting |
| `D.sum`, `D.any`, `D.all`, `D.min`, `D.max` | `{"op": op, "sequence": Expr}` | Typed collection aggregations |

With `bindings2bindingsTM` v2, authors can author bindings using either explicit canonical `D.*` builders or concise dollar notation (e.g. `"$draft.title"`, `{"$cond": [...]}`) lowered via `D.sugar`. Explicit `D.value` preserves literal strings starting with `$`.

Use an empty path to select the complete value. Paths traverse records/maps only; list indexing and traversal through nullable values are unsupported. Map keys may be structurally valid but missing at runtime, which rejects evaluation. `item` is valid only inside a map body and refers to the innermost map item. `text` renders numeric/boolean parts as JSON scalar text. `None` and empty lists need an applicable target-type hint; otherwise compilation rejects ambiguous literals.

The D helpers wrap raw child values as literals; a dict containing `op` is treated as an expression. Use `D.value` explicitly for a literal object containing that key. Serialized expression children must use the node forms above. Inputs also accept raw literals through the compiler's literal wrapping. Expressions must be finite inert JSON; nonfinite numbers, cycles and executable objects are rejected.

For example:

```python
D.map(
    D.ref("entries", "rows"),
    D.dict({
        "label": D.item("title"),
        "count": D.item("count"),
    }),
)
```

Binding expressions are inert data. Put domain computation—such as arithmetic, decisions, external calls or specialized transformations—in audited Python widget handlers, then expose the result through typed outputs.

### Sources and appearance overrides

A source selects the **latest earlier appearance** of its logical widget. Its values come from accepted typed outputs.

For a previous appearance of the receiving widget:

```python
{
    "sources": {
        "previous": {
            "widget": {"self": "previous"},
            "port": "result",
        }
    }
}
```

Sources must refer to earlier steps. Same-step and future references are rejected.

`parameters` is a reserved source alias; use `D.ref("parameters", name)` for a typed parameter. Every declared source is checked, even if unused. Only used sources generate wires; multiple ports from one appearance share a wire row. Source caps cover the entire source step's mounting rows. Source evaluation uses accepted outputs, while the receiving widget captures its inputs once on mount.

Appearance overrides replace named binding entries as whole entries:

```python
{
    "id": "review_again",
    "widgets": ["reviewer"],
    "overrides": {
        "bindings": {
            "reviewer": {
                "sources": {
                    "previous": {
                        "widget": {"self": "previous"},
                        "port": "result",
                    }
                },
                "inputs": {
                    "context": D.ref("previous"),
                },
            }
        }
    },
}
```

The compiler owns generated history wires and their caps. Keep the following fields reserved:

- `strict_binding_recipe_v1`
- `strict_binding_parameters_v1`
- `strict_sources_v1`
- `strict_ports_v1`
- `__kernel`

Use the supported binding and widget APIs rather than authoring or modifying these fields directly.

## 4. Author SM and C deliberately

### Chrome selection

Compile for the chrome you intend to launch:

```python
tape = compile_tape(
    P,
    SM,
    C,
    chrome="metal_compact",
)
```

The compiler fills an omitted SM app-pack selection. An explicit selection must agree with the selected chrome profile, including after C and ordinary SM symbol binding.

Switching profiles requires revalidation.

### Central aesthetics gateway

The family registers **`paquete_aesthetics`** through the backend's official `SessionMetadataSurfaceRegistry`. Chrome baseline CSS is loaded through `styleUrls`; SM supplies flow-specific refinements afterward. `SM.app_pack_mould.app_pack` remains the official chrome selector.

```python
SM = with_aesthetics(
    SM,
    widget_placements={
        "defaults": {"placement": "vertical", "visibility": "current_span"},
        "steps": [{"step": "proposal.review", "placement": "horizontal",
                   "visibility": "all_appearances"}],
    },
    css_injection=[{
        "target": {"step": "proposal.review", "widget": "reviewer",
                   "micro_type": "text", "part": "control"},
        "declarations": {"border-color": "#477650", "--review-accent": "#477650"},
        "pseudo_classes": ["focus-visible"],
        "media": "(min-width: 48rem)",
    }],
)
```

The helper copies SM, preserves existing sections, and writes these sections directly inside `paquete_aesthetics`. Ordinary SM symbols and C resolve before effective validation. Step IDs are fully qualified public IDs: `<program_id>.<flow_step_id>`.

The aesthetics pocket is closed: its only sections are optional `widget_placements` and `css_injection`. Placement has optional `defaults: {placement?, visibility?}` and `steps: [{step, placement?, visibility?}, ...]`. Each CSS rule has exactly required `target: {handle: string, ...}` and `declarations: {property: string, ...}`, plus optional `pseudo_classes: [string, ...]` and `media: string`. Target handles are listed below; `part` must be one of the declared parts. Other section/rule/target keys are rejected. Compilation checks schema shapes and targeted step IDs; native CSS condition syntax is checked in the browser.

CSS targets combine the following handles on shared rendered nodes under both chromes:

| Target field | DOM attribute | Meaning |
|---|---|---|
| `section` | `data-paquete-section` | Named page section, including `widgets`, `brand`, `status`, `history`, `latest_trident`, `stage`, `composer`, `notifications` |
| `step` | `data-paquete-step` | Fully qualified public step ID |
| `widget` | `data-paquete-widget` | Logical widget ID |
| `widget_type` | `data-paquete-widget-type` | Registered lifecycle widget implementation ID |
| `micro` | `data-paquete-micro` | Micro name within its widget |
| `micro_type` | `data-paquete-micro-type` | Registered micro type |
| `micro_table` | `data-paquete-micro-table` | Owning subtable |
| `part` | `data-paquete-part` | `page`, `section`, `step`, `widget`, `micros`, `micro`, `label`, `control` |

An empty target styles the mounted page. Rules use native CSS declarations, including custom properties and explicit `!important` values. Unsupported declarations follow browser behavior. Rule order breaks ties at equal specificity; normal CSS specificity still applies. Pseudo-class identifiers combine on the targeted node (for example `hover` and `focus-visible`). Functional selectors, full stylesheets, keyframes and font declarations belong in installed chrome CSS; SM selects their effects using declarations and variables.

Each mounted page owns one scoped stylesheet. Widget patches and heartbeats reuse it; changed CSS metadata updates it. Malformed conditional rules report `css_injection[index]` on `data-paquete-styling-error`, retain the previous valid stylesheet, and leave session execution running. Removing a mounted page removes its stylesheet. Historical appearances share logical handles while retaining separate patch IDs. Annotations come only from role-projected data: hidden widget types and micros are never recovered from authored sources.

Custom renderers receive the common `annotate(node, {ctx, widget, micro, part, section})` helper. Shared mechanics annotate standard frames, labels and controls, so chrome authors need no parallel attribute vocabulary.

| Choice | Behavior |
|---|---|
| `vertical` | Stack widgets vertically |
| `horizontal` | Arrange widgets horizontally, wrapping when needed |
| `current_span` | Show the viewed span's widgets |
| `all_appearances` | Show available retained step appearances through the viewed cursor |

Precedence is **family defaults → pocket defaults → matching step override**, applied field by field.

Defaults are vertical placement and current-span visibility. Override step IDs must be unique and must belong to the compiled program. Replacing `widget_placements` replaces that complete section; supply the defaults and overrides you intend to retain. Other aesthetic sections are preserved.

Earlier appearances are read-only and retain distinct card identities even when the same logical widget appears again. Historical viewing excludes future appearances. Retention and role projection remain authoritative.

### Customization

Declare ordinary symbols with defaults and explicit parametrization:

```python
P["symbols"] = {
    "copy.prefix": {
        "value": "Review",
        "parametrize": True,
    }
}

C = {"copy.prefix": "Please review"}
```

Connect a customizable value to a strict input through a typed parameter declaration.

Strings inside `D` expressions are literal—even strings containing `$`. Ordinary symbol references belong in ordinary symbol-aware surfaces, such as parameter declaration values.

P and SM share the symbol grammar: `symbols[name] = {"value": JSON, "parametrize": bool?}` (default `False`), and `puppeteering[name] = JSON` assigns a declared parametrized symbol. Names must be nonempty, cannot start with `$`, and cannot use the reserved `__puppeteering_overrides_v1__` name. Ordinary references are whole strings such as `$copy.prefix`, with optional nested record fields or numeric list indices; the longest declared symbol-name prefix wins. Embedded-dollar interpolation such as `"Hello $name"` is rejected on ordinary surfaces. Use `D.text` for typed text composition.

C is a symbol-value mapping or `None`. Its optional `__puppeteering_overrides_v1__` control accepts only `mode` (`merge_onto`, default, or `take_over`) and `strict` (boolean, default `True`). Merge overlays authored puppeteering by symbol name; take-over discards authored puppeteering first. Structured values replace whole symbol values. With strict routing, unknown or unparametrized assignments fail; `strict=False` ignores them. C routes jointly to parametrized names in P and SM, applying an assignment to every surface that exposes it.

Typed defaults must satisfy their declarations before C is checked. Revalidate changed P/SM/C combinations. An incompatible later customization may also fail during runtime mount.

## 5. A complete flow example

This example uses the supplied widgets and composes a typed review record:

```python
from authoring_funneling.examples.metal import (
    D, compile_tape, with_aesthetics,
)

P = {
    "kind": "think_program_v1",
    "surface_version": "v1",
    "symbols": {
        "copy.prefix": {"value": "Review", "parametrize": True},
    },
    "puppeteering": {},
    "run": {
        "program": {
            "info": {"id": "proposal", "title": "Proposal review"},
            "widgets": {
                "writer": {
                    "widget": "metal.seed",
                    "args": {"title": "Proposal", "count": 2},
                    "bindings": {},
                },
                "reviewer": {
                    "widget": "metal.consumer",
                    "bindings": {
                        "sources": {
                            "draft": {"widget": "writer", "port": "result"},
                            "entries": {"widget": "writer", "port": "entries"},
                        },
                        "parameters": {
                            "prefix": {"type": str, "value": "$copy.prefix"},
                        },
                        "inputs": {
                            "context": D.dict({
                                "heading": D.text(
                                    D.ref("parameters", "prefix"),
                                    ": ",
                                    D.ref("draft", "title"),
                                ),
                                "items": D.map(
                                    D.ref("entries", "rows"),
                                    D.dict({
                                        "label": D.item("title"),
                                        "count": D.item("count"),
                                    }),
                                ),
                                "note": D.ref("draft", "note"),
                            }),
                        },
                    },
                },
            },
            "flow": [
                {"id": "write", "widgets": ["writer"]},
                {"id": "review", "widgets": ["reviewer"]},
            ],
        },
        "config": {},
    },
}

SM = with_aesthetics(
    {"manual_io": {"persistence": "disabled"}},
    widget_placements={
        "defaults": {"placement": "vertical", "visibility": "current_span"},
        "steps": [{"step": "proposal.review", "placement": "horizontal",
                   "visibility": "all_appearances"}],
    },
)

C = {"copy.prefix": "Please review"}

tape = compile_tape(P, SM, C, chrome="metal_compact")
```

Launch **`tape["P"]`, `tape["SM"]`, and `tape["C"]`** through the ordinary P/SM/C API.

The export has exactly `profile_id`, `P`, `SM`, `C`, `widget_ids` and `contract_fingerprint`. P is ordinary executable P; SM/C retain their authored surfaces for ordinary launch-time binding. Runtime registration does not compile authoring lessons.

### Parse → validate → compile → launch

There is no separate typed source language parser: author a Python mapping or parse its JSON representation, then submit it to the profile. Python type constructors work in Python drafts; JSON drafts use the serialized Type and Expression forms in section 3. For example, the prefix declaration above is portable as `{"type": {"kind": "str"}, "value": "$copy.prefix"}`.

This continuation of the complete example exercises the JSON authoring path:

```python
from copy import deepcopy
import json
from authoring_funnel.b_service_ready_typed_PSMCW_authoring.authoring import resolve_authoring_profile

portable_P = deepcopy(P)
portable_P["run"]["program"]["widgets"]["reviewer"]["bindings"]["parameters"]["prefix"]["type"] = {"kind": "str"}
authored_P = json.loads(json.dumps(portable_P, allow_nan=False))
profile = resolve_authoring_profile("metal_compact")
draft = {
    "profile_id": profile.profile_id,
    "W": sorted({w["widget"] for w in authored_P["run"]["program"]["widgets"].values()}),
    "P": authored_P,
    "SM": SM,
    "C": C,
}
receipt = profile.validate(draft)
if not receipt["ok"]:
    raise ValueError(receipt["errors"])
tape = profile.compile(draft)
```

W must match the unique implementation IDs in all P widget declarations, including unused declarations, and every ID must belong to the profile's library. `validate` compiles without launching, returning `ok: True`, `profile_id`, `errors: []` and `contract_fingerprint` on success. Failure returns `ok: False`, `profile_id` and one error with `code`, `path`, `message`, and optional details; some inherited failures use the coarse path `["P"]`. It does not aggregate all errors. `compile` returns the export or raises; `compile_tape` is the convenience path that derives W and chooses the profile for you. Neither mutates the supplied P/SM/C.

JSON parsing checks syntax only. Profile compilation checks strict bindings and default parameter values, ordinary P lowering, joint P/SM/C routing, effective parameter values, library selection, chrome agreement and effective aesthetics. Launch `tape["P"]`, `tape["SM"]`, `tape["C"]` through the ordinary API; do not launch Higher P directly. The fingerprint covers profile identity and registered widget contracts/configuration, not authored P/SM/C or domain correctness. Revalidate changes to those surfaces, the selected profile or registered contracts.

## 6. Contribute widgets with complete transitions

Declare ordinary configuration args separately from typed inputs and closed output records. This complete implementation can be added to the central sheet:

The decorator normalizes port schemas into `strict_ports_v1` on the ordinary registered class and uses the public kernel registration path; there is no second widget registry. It requires a `StrictServiceWidget` subclass (here, `LibraryWidget`), mount-shelling, and audited signal catchers. Authored wire contracts and generated contract/recipe fields are reserved. Widget IDs must be unique unless you deliberately request `overwrite=True`.

```python
from authoring_funneling.examples.metal import (
    LibraryWidget, strict_widget, Dict, Nullable,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode

@strict_widget(
    "creative.review.v1",
    args={"prompt": {"type": "str", "default": "Your answer"}},
    inputs={"title": str},
    outputs={
        "result": Dict({
            "title": str,
            "answer": Nullable(str),
        })
    },
)
class Review(LibraryWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        title = self.mouth.read("title")
        self.outputs.write_port("result", {"title": title, "answer": None})
        return Reexplode(
            next_fill_shell=self.replacement_shell(
                fill_data["fill_shell"],
                title=title,
                micros=[{
                    "name": "answer", "type": "text", "required": True,
                    "label": self.configuration.get("prompt", "Your answer"),
                    "render_args": {"emphasis": "primary"},
                }],
                micro_placement="horizontal",
            ),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.outputs.keep("result", "title")
        self.outputs.write("result", "answer", fill_data["current_fills"]["answer"])
        return True
```

| Widget API | Use |
|---|---|
| `mouth.read(port)` | Read a captured typed input |
| `mouth.read_or(port, fallback)` | Supply a type-checked fallback for null |
| `configuration` | Read detached effective configuration |
| `outputs.write(port, key, value)` | Stage one validated output |
| `outputs.write_port(port, record)` | Stage a complete output record |
| `outputs.write_many(records)` | Stage a validated batch atomically |
| `outputs.read(port, key)` | Read a detached previously accepted value |
| `outputs.keep(...)`, `keep_port(...)` | Explicitly carry accepted values forward |
| `write_null`, `read_or`, `require_value` | Handle nullability precisely |

Every mount, fill and signal transition must:

1. Read through the supported APIs.
2. Write every declared output key.
3. Return `True` or `Reexplode`.

Mount has no previously accepted outputs. Inputs are captured on mount. Signals use `@analytica_signal_catcher(...)`.

A successful complete transition publishes staged outputs. A failed transition preserves the previous accepted strict output pockets. Execution remains inside the existing analytics operation.

Writes validate before staging; `write_many` validates its entire batch before staging anything. Repeated writes replace that staged key. Reads expose previously accepted values, not pending writes, and return detached copies. Input/configuration reads are also detached. A null fallback is checked only when used; false, zero and empty values remain values.

Keep durable semantic state in declared outputs. Public attribute assignment/deletion is rejected; private-state mutation lies outside the strict guarantee. Inherit wrapped handlers directly, or override them without calling another wrapped lifecycle handler from inside a handler.

### Emit and replace micros

A widget may add, remove, reorder or replace micros between explosions. Micro names must be unique and nonempty within the shell; each type must belong to an admitted micro subtable.

`replacement_shell` preserves lifecycle/presentation metadata while stripping the raw kernel packet and generated binding args. The family's audited transition checks each emitted `Reexplode` shell before accepting outputs: micros must be a list of inert JSON objects with unique nonempty names, admitted types, legal attached validators and an admitted shell placement. Other descriptor fields are preserved, not treated as typed ports or automatically enforced semantic constraints.

**`paquete_micro_placement` belongs once on the widget fill shell**, where it governs the contained micros. It has its own placement axis. Fresh shells default to vertical; omitting `micro_placement` during replacement preserves an existing shell choice.

Add the implementation and mechanics reference to `THINKWIDGETS`:

```python
WidgetRow(Review, "standardWidget")
```

`WidgetRow` is declared in `shared_widgets/widgets.py`. For specialized mechanics, export a named synchronous renderer in `js/widgets.js` and reference that function in the row. It receives `{documentRef, widget, ctx, api, aesthetics, renderMicro, annotate}` and returns a widget-card DOM node. Use `renderMicro` for admitted micro dispatch and preserve the card's HAI attributes and role-projected data. The family decorator and sheet own renderer selection; `hai_renderer` is supplied by the decorator.

## 7. Contribute micro tables and browser mechanics

A subtable contains:

```python
MicroTable(
    "your_table",
    (
        MicroRow(your_definition, "yourRenderer"),
    ),
)
```

`MicroTable` and `MicroRow` are declared in `shared_widgets/micros.py`; add your subtable to `MICRO_TABLES`. Each admitted micro type has exactly one owning subtable. Reference canonical built-in definitions directly with `get_micro_type_definition(name)` rather than copying them. Extensions use the platform's `MicroTypeDefinition`, with canonical lowercase names and explicit data semantics, coercion, validator capabilities and schema.

All admitted definitions flatten into the platform registry. Registration is atomic across the micro batch; identical repeat registrations are idempotent. Conflicting definitions and unknown coercion targets fail. Cross-subtable coercion targets are supported.

Export the named synchronous browser renderer from `js/micros.js` and reference its name in the row. Missing browser renderer references fail validation.

A renderer receives:

```javascript
renderMicro({
  documentRef,
  micro,
  value,
  widget,
  ctx,
  api,
  aesthetics,
  annotate,
})
```

`micro` is the complete emitted descriptor. Its options, validators and custom rendering arguments reach the renderer without being merged with widget configuration. Treat it as read-only. `value` carries the current fill separately.

Return a DOM node. Render synchronously and install event callbacks for later interaction. Dispatch and state mutations remain guarded during rendering.

When integrating an editor with the supplied composer, preserve its inclusion and serialized-value controls:

| Attribute | Meaning |
|---|---|
| `data-hai-micro-include` | Include this micro in the fill |
| `data-hai-micro-value` | Serialized JSON value |
| `data-datum-id` | Owning datum |
| `data-micro-name` | Micro name |

Preserve value types: integer controls emit numbers; select controls retain their options' JSON types.

Schemas and HTML control bounds describe capabilities and guide interaction. Implement semantic enforcement through platform coercion, attached validators and appropriate widget checks. Declaring a validator capability does not automatically attach it to every usage.

The supplied micro subtables admit `text`, `integer`, `select`, and the extension `creativity_bounded_integer`, whose coercion accepts integers from 0 through 100. A type registered globally but absent from this family's sheet is not admitted by its widgets.

## 8. Contribute aesthetics and placement members centrally

An aesthetic collection fulfills every required synchronous slot:

| Slot | Arguments and result |
|---|---|
| `widgetFrame` | `{documentRef, widget, ctx}` → widget card DOM node with HAI card/id attributes |
| `microFrame` | `{documentRef, micro, widget}` → row DOM node |
| `label` | `{documentRef, micro}` → label DOM node |
| `control` | `{documentRef, control, micro}` → decorate the existing control |
| `notification`, `widgetNotification` | HAI notification context → append presentation to `container` |
| `widgetsContainer` | HAI container context → append cards using `renderWidgetCard` |
| `page` | HAI page context → presentation plus `renderDefaultPage()` |
| `outers` | HAI outer context → presentation plus `renderDefaultOuters()` |
| `noReadWidget`, `noWriteWidget` | HAI widget context → restricted presentation DOM node |
| `brand` | HAI outer context → replace brand `container` contents |

Explicit reuse between collections is supported. Missing slots and asynchronous functions are rejected.

Preserve widget-card attributes, especially `data-hai-widget-card` and `data-hai-widget-id`. Use supplied callbacks to render cards and retain role restrictions. Keep traversal, fill serialization and placement mechanics in their shared implementations.

Publish a chromeset with `per_pack_chromesets/<name>/index.js`, `aesthetics.js`, `styles.css`, and one `ChromeRow(app_pack_id, chrome_id, label, aesthetics, browser_asset_root)` in `CHROMETABLES`. Keep the stable chrome ID separate from its app-pack ID. Follow the supplied entry modules for composition imports and the exported pack identity. Shared browser resources live in `shared_rendering/static`; Python helpers live in its parent. See the [browser publication contract](../../../../../framework/think-frontend/src/__staticfiles_mgmt/README.md) for mounting and collection.

Placement membership is declared in `PLACEMENT_AXES` in [aesthetics.py](shared_rendering/aesthetics.py), independently for widgets and micros. Add new members there and provide their shared JavaScript layout function and dispatch entry in `js/aesthetics.js`. `AESTHETICS_SECTIONS` owns section schemas, validators and browser behavior references; `SEMANTIC_TARGETS` and `RENDERABLE_PARTS` own the targeting vocabulary. Regenerate the browser catalogue after changing membership. Core framework enums and individual chrome sets do not need parallel placement declarations.

## 9. Export, verify and publish

After changing widget, micro or placement sheets:

```sh
python -m authoring_funneling.examples.metal.publication --export-browser
```

`js/catalogue.js` is generated from the Python sheets. Startup and tests reject a stale projection.

From the provisioned service environment:

```sh
cd thinkument/service-innovations
python run_sheet.py app_packs
python run_sheet.py ui_web_apps
npm test
```

Restart hosts after changing startup declarations.

For each contribution, verify its meaningful behavior: complete typed transitions, rejected values, reexplosion, descriptor preservation, role projection, repeated appearances, history and undo/redo. Verify browser mechanics under both chromes and installed asset behavior outside the source checkout.

Strict authoring guarantees structural types, complete writes and supported transition behavior. Domain correctness, termination and ordinary framework admission/exhaustion policies remain responsibilities of the implementation and its tests. It preserves the existing analytics, signals, role projection, retention, history and undo/redo machinery. Source lookup still scans framework history and analytics still snapshots state; typed projection does not remove those costs. Undo may first unwind subsequent automatic work before the preceding manual action becomes redoable.

Automatic-mount parameter failures can propagate a `RuntimeValueError` through later context preparation; an ordinary dispatch-error packet is not guaranteed. Service transactions retain their rollback behavior. Admission failures before handler execution are not promised to become widget audit errors.

Existing Python tests cover strict compilation/runtime, profile receipts, shared sheets, shell admission, effective chrome/C and aesthetics validation. JavaScript contracts cover shared presentation and placement behavior; browser tests cover both chromes, repeated appearances, history, native CSS and stylesheet lifecycle. Per-step layout overrides have Python/JavaScript coverage; dedicated browser coverage for that combination remains a separate gate. Installed-asset/wheel verification is a separate check, not a consequence of compilation.

Current sources: [library widget sheet](shared_widgets/widgets.py), [micro subtable sheet](shared_widgets/micros.py), [chrome declarations and browser export](per_pack_chromesets/declarations.py), [placement declarations and SM template](shared_rendering/aesthetics.py), and [typed compiler](../../authoring_funnel/b_service_ready_typed_PSMCW_authoring/program.py).

For the full strict-template contract, read [the typed authoring reference](../../authoring_funnel/b_service_ready_typed_PSMCW_authoring/README.md). For ordinary app-pack manifests, discovery, installation and UI applications, read [the creativity README](../../../../README.md).
