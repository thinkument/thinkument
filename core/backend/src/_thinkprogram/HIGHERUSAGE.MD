# thinkprogramTM / thinkwidgetTM FRONT SHEET v1

**Highest developer reference for forever-live widget app programs**

---

## MENTAL MODEL

A thinkprogramTM app is:

```text
logical thinkwidgetTM widgets
    placed into ordered flow frames
    with args, roles, tags, layout metadata, local overrides,
    and named wires to prior committed widget state.
```

The developer illusion is:

```text
"I am programming forever-live widgets."
```

The compiler reality is:

```text
think_program_v1
    -> generated thinkkernelTM steps
    -> app-table rows using step_fn = "think.kernel.v1"
    -> runtime forms/spans/widgets/fills/history
```

Highest app developers normally author only:

| Surface                 | Author writes? | Purpose                                     |
| ----------------------- | -------------: | ------------------------------------------- |
| thinkwidgetTM classes   |            YES | Define widget behavior, micros, validation  |
| micro catalogue entries |    YES/CONSULT | Define available micro types and validators |
| think_program_v1 JSON   |            YES | Define app flow using logical widgets       |
| thinkkernelTM objects   |             NO | Generated IR / runtime contract target      |
| app-table step rows     |             NO | Generated runtime manifest                  |
| explicit micros in app  |             NO | Widgets generate micros on mount            |

---

## 1. STACK MAP

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ HIGHEST AUTHORING                                                            │
│                                                                              │
│   think_program_v1 JSON                                                       │
│   - symbols                                                                   │
│   - puppeteering                                                              │
│   - program info                                                              │
│   - logical widgets                                                           │
│   - flow frames                                                               │
│   - wires                                                                     │
│   - overrides                                                                 │
│   - runtime config                                                            │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ lowers
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ GENERATED EXPLICIT KERNEL PROGRAM                                            │
│                                                                              │
│   list[think_kernel_step_v1]                                                  │
│   - one flow item -> one kernel step                                          │
│   - one generated frame: "frame"                                              │
│   - one generated span:  "span"                                               │
│   - datums have micros=[] before mount                                        │
│   - history_queries and past_wires are compiler-owned                         │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ lowers
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ APP TABLE MANIFEST                                                           │
│                                                                              │
│   [                                                                          │
│     {                                                                        │
│       "public_step_name": K.step.id,                                         │
│       "step_fn": "think.kernel.v1",                                          │
│       "fn_args": {"kernel": K}                                               │
│     },                                                                       │
│     ...                                                                      │
│   ]                                                                          │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ executes
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ RUNTIME                                                                      │
│                                                                              │
│   current span waits until authoritative widgets are satisfied                │
│   fills/signals target live datum widgets                                     │
│   widgets may reexplode into new shells or finish                             │
│   committed lifecycle state becomes readable by later wires                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. HIGHEST DESIGN LAWS

| Law                             | Rule                                                     |
| ------------------------------- | -------------------------------------------------------- |
| App authors do not write micros | No "micros" anywhere under run.program.                  |
| Widgets shell themselves        | Admitted widgets must mount-explode first visible shell. |
| Premount shell is empty         | Generated kernel datums have "micros": [].               |
| One flow item = one step        | Each flow item lowers to one thinkkernelTM step.         |
| One generated frame/span        | frame.id = "frame"; span.id = "span".                    |
| Logical widgets may recur       | Same logical widget may appear across flow items.        |
| No duplicate in one frame       | Same logical widget cannot repeat inside one flow item.  |
| Wires are historical            | Wires read prior committed lifecycle rows.               |
| History is backward-only        | Wires cannot read future flow items.                     |
| Kernel pocket is reserved       | "__kernel" is injected, never authored.                  |
| Widget runtime seam             | Read continuity at q["datum"]["args"]["__kernel"].       |
| Root q stays clean              | No q["kernel"], q["step"], q["past_wires"], etc.         |
| Roles are metadata              | Widgets stay role-agnostic; controller modulates roles.  |
| Validation before commit        | Bad fills never reach final widget commit.               |
| Lowering is pure                | Source program is not mutated.                           |

---

## 3. think_program_v1 TOP GRAMMAR

Top object:

```json
{
  "kind": "think_program_v1",
  "surface_version": "v1",
  "symbols": {...},
  "puppeteering": {...},
  "run": {
    "program": {
      "info": {...},
      "widgets": {...},
      "flow": [...]
    },
    "config": {...}
  }
}
```

Allowed top-level keys:

| Key             | Required | Meaning                                |
| --------------- | -------: | -------------------------------------- |
| kind            |      YES | Must be "think_program_v1".            |
| surface_version |      YES | Must be "v1".                          |
| symbols         |       NO | Dead JSON symbol table.                |
| puppeteering    |       NO | Run/persona/deploy symbol replacement. |
| run             |      YES | Only place symbols are resolved.       |

Allowed run.program keys:

| Key     | Required | Meaning                              |
| ------- | -------: | ------------------------------------ |
| widgets |      YES | Logical widget library.              |
| flow    |      YES | Ordered frame program.               |

Forbidden under run.program:

```text
micros
explicit kernel datums
explicit kernel history aliases
explicit kernel steps
app-table rows
premount visual shells
```

---

## 4. SYMBOLS + PUPPETEERING

Symbols are dead JSON values.

```json
{
  "symbols": {
    "app.env": {
      "value": "dev",
      "parametrize": true
    },
    "theme": {
      "value": {"density": "compact"}
    }
  },
  "puppeteering": {
    "app.env": "prod"
  }
}
```

Reference forms:

| Form              | Valid? | Meaning                         |
| ----------------- | -----: | ------------------------------- |
| "$app.env"        |    YES | Exact symbol reference.         |
| "$theme.density"  |    YES | Nested lookup.                  |
| "$choices.1.name" |    YES | List index lookup.              |
| "env=$app.env"    |     NO | Partial interpolation rejected. |
| "env=${app.env}"  |     NO | Partial interpolation rejected. |
| "$"               |     NO | Empty reference.                |

Symbol laws:

| Law                      | Rule                                                  |
| ------------------------ | ----------------------------------------------------- |
| Resolved only inside run | symbols section itself is not recursively resolved.   |
| Longest match wins       | "$a.b.c.d" prefers symbol "a.b.c" before "a.b".       |
| Source not mutated       | bind_think_program_symbols_v1 is pure.                |
| Puppeteering limited     | Only parametrize=true symbols may be replaced.        |
| Dead JSON only           | No callables, objects, live refs, or non-JSON values. |

---

## 5. PROGRAM INFO

`run.program.info`:

```json
{
  "id": "onboarding",
  "title": "Onboarding",
  "description": "Example flow.",
  "args": {
    "product": "$app.product",
    "env": "$app.env"
  }
}
```

| Field                 | Required | Meaning                                    |
| --------------------- | -------: | ------------------------------------------ |
| id                    |      YES | Namespace for generated step/form ids.     |
| title                 |      YES | Human title.                               |
| description           |       NO | Human description.                         |
| args                  |       NO | Program metadata after symbol binding.     |

Generated ids:

| Source                         | Generated                         |
| ------------------------------ | --------------------------------- |
| program.info.id = "onboarding" | namespace                         |
| flow.id = "collect_profile"    | flow local id                     |
| step.id                        | "onboarding.collect_profile"      |
| form.id                        | "onboarding.collect_profile.form" |
| frame.id                       | "frame"                           |
| span.id                        | "span"                            |

---

## 6. LOGICAL WIDGET DEFINITIONS

`run.program.widgets`:

```json
{
  "profile": {
    "widget": "acme.profile_source",
    "title": "Profile",
    "args": {...},
    "lifecycle": {...},
    "wires": {...},
    "roles": ["maker"],
    "tags": ["profile", "source"],
    "system_flags": {"ui_region": "main"},
    "authoritative": true
  }
}
```

| Field         | Required | Meaning                                        |
| ------------- | -------: | ---------------------------------------------- |
| widget        |      YES | Registered admitted thinkwidgetTM widget name. |
| title         |       NO | Default datum title.                           |
| args          |       NO | Public widget args, contract-checked.          |
| lifecycle     |       NO | Lifecycle patch; mount_explode forced true.    |
| wires         |       NO | Logical continuity inputs.                     |
| roles         |       NO | Datum-level role assignment.                   |
| tags          |       NO | Datum tags.                                    |
| system_flags  |       NO | Controller/runtime metadata.                   |
| authoritative |       NO | Whether this widget gates span advancement.    |

Widget admission rules:

| Rule                                         | Required |
| -------------------------------------------- | -------: |
| Must be a thinkwidgetTM class widget         |      YES |
| Must be pulled into kernel contract registry |      YES |
| Must enforce no premount shell               |      YES |
| Must declare public args contract            |      YES |
| Must declare public wires contract           |      YES |
| App author may not put "__kernel" in args    |      YES |
| App author may not write micros              |      YES |

---

## 7. FLOW ITEMS

`run.program.flow`:

```json
[
  {
    "id": "collect_profile",
    "title": "Collect profile",
    "widgets": ["profile"],
    "roles": ["maker"],
    "authoritative": [true],
    "overrides": {...}
  }
]
```

| Field         | Required | Meaning                                      |
| ------------- | -------: | -------------------------------------------- |
| id            |      YES | Unique local flow id.                        |
| title         |       NO | Flow/frame/span title.                       |
| widgets       |      YES | Non-empty list of logical widget ids.        |
| roles         |       NO | Span roles; datum roles win.                 |
| authoritative |       NO | Optional list[bool], same length as widgets. |
| overrides     |       NO | Per-appearance local patches.                |

Flow laws:

| Law                        | Rule                                          |
| -------------------------- | --------------------------------------------- |
| flow is ordered            | Later wires can read earlier appearances.     |
| flow ids unique            | Duplicate flow ids rejected.                  |
| widgets non-empty          | Empty widgets list rejected.                  |
| widget ids known           | Unknown logical widget rejected.              |
| no repeat in item          | ["profile", "profile"] rejected.              |
| recurrence allowed         | "approval" may appear in multiple flow items. |
| at least one authoritative | Empty authoritative span rejected today.      |

---


## 9. OVERRIDES

Flow-local overrides patch one widget appearance inside one flow item.

Allowed override sections:

```text
args
wires
lifecycle
roles
tags
system_flags
title
```

Override target law:

```text
every override target must be present in that flow item.
```

Semantics:

| Override section | Semantics                                |
| ---------------- | ---------------------------------------- |
| args             | Deep merge.                              |
| lifecycle        | Deep merge; mount_explode forced true.   |
| system_flags     | Deep merge + compiler logical_widget_id. |
| tags             | Replacement.                             |
| roles            | Replacement.                             |
| title            | Replacement.                             |
| wires            | Patch; null removes a wire.              |

Example:

```json
{
  "overrides": {
    "args": {
      "profile": {"threshold": 9}
    },
    "wires": {
      "approval": {
        "self_previous": null
      }
    },
    "system_flags": {
      "profile": {"frame_specific": true}
    }
  }
}
```

---

## 10. WIRES + HISTORICAL CONTINUITY

Wires let a widget read prior committed lifecycle rows.

Widget definition:

```json
{
  "review": {
    "wires": {
      "previous_profile": {
        "from": "profile",
        "history": {
          "select": "latest",
          "required": true,
          "max_results": 20
        }
      },
      "profile_history": {
        "from": "profile",
        "history": {
          "select": "all",
          "required": false,
          "max_results": 50
        }
      }
    }
  }
}
```

Source forms:

| Source form                                      | Meaning                                          |
| ------------------------------------------------ | ------------------------------------------------ |
| "profile"                                        | Prior appearances of logical widget "profile".   |
| ["profile", "risk"]                              | Prior appearances of multiple logical widgets.   |
| {"self": "previous"}                             | Previous appearance of this same logical widget. |
| {"widget": "approval", "occurrence": "previous"} | Previous appearance of named logical widget.     |

History forms:

| Field       | Values     | Meaning                       |
| ----------- | ---------- | ----------------------------- |
| select      | latest/all | Latest row or all prior rows. |
| required    | bool       | Missing source fails if true. |
| max_results | int >= 1   | Runtime query cap.            |

Wire contract multiplicity:

| Contract multiplicity | Requirement                                        |
| --------------------- | -------------------------------------------------- |
| one                   | Exactly one resolved alias.                        |
| many                  | Zero or more if optional; one or more if required. |

Wire lowering:

```text
┌──────────────────────────────┐
│ thinkprogramTM wire           │
│ "previous_profile" from profile│
└───────────────┬──────────────┘
                │ compiler generates
                ▼
┌──────────────────────────────┐
│ kernel history_queries        │
│ alias -> from_step/datum_id    │
└───────────────┬──────────────┘
                │ compiler binds
                ▼
┌──────────────────────────────┐
│ kernel datum past_wires        │
│ "previous_profile": [alias]    │
└───────────────┬──────────────┘
                │ runtime hydrates
                ▼
┌──────────────────────────────┐
│ q["datum"]["args"]["__kernel"] │
│ ["past_wires"]["previous_profile"] │
└──────────────────────────────┘
```

---

## 11. GENERATED KERNEL DATUM SHAPE

For each logical widget appearance, compiler emits:

```json
{
  "id": "logical_widget_id",
  "widget": "widget_name",
  "title": "effective_title",
  "micros": [],
  "args": "effective_author_args_without___kernel",
  "past_wires": "compiler_generated_alias_bindings",
  "lifecycle": "effective_lifecycle_with_mount_explode_true",
  "tags": "effective_tags",
  "roles": "effective_roles",
  "system_flags": {
    "...effective_system_flags": "...",
    "logical_widget_id": "logical_widget_id"
  },
  "authoritative": "effective_authoritative"
}
```

Generated datum laws:

| Field                          | Law                                   |
| ------------------------------ | ------------------------------------- |
| micros                         | Always [] at premount.                |
| args                           | Author args only; no "__kernel".      |
| lifecycle.mount_explode        | Always true.                          |
| system_flags.logical_widget_id | Compiler-owned and always present.    |
| past_wires                     | Compiler-generated aliases only.      |
| authoritative                  | From flow override or widget default. |

---

## 12. WIDGET RUNTIME KERNEL PACKET

Inside a thinkwidgetTM class widget, continuity/runtime metadata is available at:

```python
q["datum"]["args"]["__kernel"]
```

Packet shape:

```json
{
  "kernel_args_surface_version": "v1",
  "past_wires": {...},
  "history_queries": {...},
  "step": {...},
  "form": {...},
  "frame": {...},
  "span": {...},
  "system_flags": {...},
  "authoritative": true
}
```

Root q pollution forbidden:

| Root q key           | Should exist? |
| -------------------- | ------------: |
| q["kernel"]          |            NO |
| q["step"]            |            NO |
| q["form"]            |            NO |
| q["frame"]           |            NO |
| q["span"]            |            NO |
| q["past_wires"]      |            NO |
| q["history_queries"] |            NO |

Practical widget rule:

```text
Read __kernel during mount.
Store anything needed later on self.
Do not assume reexploded fill_shell args still carry author args.
```

---

## 13. thinkwidgetTM CLASS DESIGN

A thinkwidgetTM widget is a class surface that lowers to one runtime lifecycle fn.

Minimum class shape:

```python
@thinkwidgetTM_config(
    "acme.widget_name",
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
      "seed": {"type": "str", "required": true},
      "threshold": {"type": "int", "required": false, "default": 7}
    },
    wires={
      "previous_profile": {"multiplicity": "one", "required": true}
    }
)
class MyWidget(DatumLifecycleWidget):

    def _on_mount(self, position, fill_data, limits, stats):
        ...
        return Reexplode(
            next_fill_shell={... "micros": [...] ...},
            pre_computed_fills={...},
            prefill_hints={...}
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        ...
        return Reexplode(...)  # next surface
        # or
        return True            # done

    @signal_catcher("refresh")
    def refresh(self, signal, position, fill_data, limits, stats):
        ...
        return Reexplode(...)
```

Class handler contract:

| Handler               | Called when                      | Returns           |
| --------------------- | -------------------------------- | ----------------- |
| _on_mount             | first mount signal               | Reexplode or True |
| _on_fill              | ordinary fill or fallback signal | Reexplode or True |
| @signal_catcher(kind) | matching custom signal           | Reexplode or True |

Invalid class returns:

```python
{"status": "blocked"}
raw platform lifecycle packets
arbitrary dicts
```

Valid class returns:

```text
True
Reexplode(...)
```

State model:

| Surface                       | Meaning                                 |
| ----------------------------- | --------------------------------------- |
| self.foo = ...                | Stored into lifecycle state.            |
| getattr(self, "foo", default) | Reads prior lifecycle state.            |
| self.message(level, text)     | Emits message event and stores message. |
| Reexplode(...)                | Replaces current visible shell.         |
| return True                   | Marks widget done.                      |

Message levels:

```text
info
warning
success
error
```

Signal policy:

| Config                          | Unknown custom signal behavior         |
| ------------------------------- | -------------------------------------- |
| MISSING_SIGNAL_FALLBACK_TO_FILL | Calls _on_fill with signal preserved.  |
| MISSING_SIGNAL_RAISE            | Raises when no @signal_catcher exists. |

---

## 14. WIDGET INPUT PACKETS

Handler signature:

```python
(position, fill_data, limits, stats)
```

`position`:

| Key      | Meaning                  |
| -------- | ------------------------ |
| form_id  | Current form id.         |
| frame_id | Current frame id.        |
| span_id  | Current span id.         |
| datum_id | Current widget/datum id. |

`fill_data`:

| Key                      | Meaning                                      |
| ------------------------ | -------------------------------------------- |
| fill_shell               | Current effective shell.                     |
| current_fills            | Accepted canonical/coerced current fills.    |
| changed_fills            | Delta versus last adapter precomputed fills. |
| prefill_hints            | Current hints.                               |
| shell_satisfaction_check | Structural/semantic satisfaction check.      |

`signal`:

| Key  | Meaning                                  |
| ---- | ---------------------------------------- |
| kind | "mount", "fill", or custom signal kind.  |
| info | Controller/user/runtime signal metadata. |

Changed fills law:

```text
changed_fills is a value delta.
It is not source causality.
Same value submitted again may produce no changed_fills.
```

---

## 15. WIDGET OUTPUTS

Reexplode:

```python
Reexplode(
  next_fill_shell={
    "id": ...,
    "title": ...,
    "micros": [...],
    "macro_validation_lambdas": [...],
    "lifecycle": {...}
  },
  pre_computed_fills={...},
  prefill_hints={...}
)
```

| Output             | Meaning                            |
| ------------------ | ---------------------------------- |
| next_fill_shell    | Replacement current visible shell. |
| pre_computed_fills | Working fill overlay.              |
| prefill_hints      | UI/help hints.                     |

Return True:

| Effect                    | Meaning                                         |
| ------------------------- | ----------------------------------------------- |
| status done               | Widget satisfied.                               |
| final fill commits        | Accepted fill commits through normal path.      |
| lifecycle state persists  | self fields become later-readable state.        |
| history wires can read it | Later widgets consume committed lifecycle rows. |

Reexplode lifecycle:

```text
┌────────────┐
│ mount      │
└─────┬──────┘
      ▼
┌────────────┐
│ Reexplode  │ -> first visible micros
└─────┬──────┘
      ▼
┌────────────┐
│ fill       │ -> canonical current_fills
└─────┬──────┘
      ├──────────────▶ Reexplode -> next visible micros
      │
      └──────────────▶ True -> done/commit/history
```

---

## 16. MICROS CATALOGUE

Highest app-flow authors do not write micros.

Widget authors do write micros inside thinkwidgetTM mount/reexplode shells.

Micro shape:

```json
{
  "name": "score",
  "type": "rating_scale_e2e",
  "required": true,
  "args": {
    "minimum": 1,
    "maximum": 5,
    "stars": 5
  },
  "validators": [
    {
      "path": "rating_validators:rating_between",
      "args": {"minimum": 1, "maximum": 5}
    }
  ],
  "style": {
    "density": "compact",
    "visual": "stars"
  }
}
```

Micro laws proven by scaling tests:

| Law                              | Meaning                                                          |
| -------------------------------- | ---------------------------------------------------------------- |
| New micros are data-driven       | No ThinkProgram/ThinkKernel/ThinkWidget hardcoded switch needed. |
| Shell carries type               | Renderer sees the micro type, args, style, requiredness.         |
| Validators attach to micros      | Micro validators run before commit.                              |
| Macro validators attach to datum | Cross-field validators run before commit.                        |
| Raw validation is separate       | Raw accepted values may remain raw at validator layer.           |
| Coercion is separate             | Runtime canonicalizes accepted fills through MICRO_TYPES.        |
| Widgets see canonical fills      | fill_data["current_fills"] is coerced/canonical.                  |
| Bad fills do not commit          | Invalid micro/macro fill blocks before widget commit.            |
| History carries canonical state  | Later wires read committed canonical lifecycle state.            |

Adding a new micro type:

| Step | Action                                                    |
| ---: | --------------------------------------------------------- |
|    1 | Add MicroTypeDefinition to MICRO_TYPES.                   |
|    2 | Define python_types and coerce function.                  |
|    3 | Define validator policies.                                |
|    4 | Define casts/coerce_to_micro_types if needed.             |
|    5 | Author widget shells using the new micro type name.       |
|    6 | Attach validators by path.                                |
|    7 | Confirm renderer sees args/style/type.                    |
|    8 | Confirm raw bad values fail before commit.                |
|    9 | Confirm canonical values reach current_fills and history. |

Validator function contract:

```python
returns tuple[bool, str | None]
```

Examples:

```python
return True, None
return False, "rating must be between 1 and 5"
```

---

## 17. MICRO VALIDATION PIPELINE

```text
┌────────────────────────────┐
│ User/runtime raw fill       │
│ {"score": "4"}              │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ Raw semantic validation     │
│ validators see raw/candidate│
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ Accepted fill coercion      │
│ MICRO_TYPES coerce "4" -> 4 │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ Widget fill_data            │
│ current_fills["score"] = 4  │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ Widget returns True         │
│ commit canonical state      │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ Later history wire          │
│ reads canonical committed row│
└────────────────────────────┘
```

---

## 18. AUTHORITATIVE SPAN COMPLETION

A flow item produces one span.

The span advances only when its authoritative widgets are satisfied.

| Datum status                      | Effect                              |
| --------------------------------- | ----------------------------------- |
| authoritative + unsatisfied       | Blocks span advancement.            |
| authoritative + done              | Counts toward span completion.      |
| non-authoritative untouched       | Does not block advancement.         |
| non-authoritative touched invalid | Blocks submit until valid/resolved. |

Current rule:

```text
each generated span must have at least one authoritative datum.
```

---

## 19. ROLES

Roles are not widget logic.

Roles are datum/span metadata consumed by controller runs.

Role assignment priority:

| Source                   | Priority                                       |
| ------------------------ | ---------------------------------------------- |
| datum.roles / datum.role | First                                          |
| span.roles / span.role   | Fallback                                       |
| no datum or span roles   | Roleless/public according to controller policy |

thinkprogramTM sources:

| Source                  | Lowers to               |
| ----------------------- | ----------------------- |
| widget.roles            | datum.roles             |
| flow.roles              | span.roles              |
| overrides.roles[widget] | replacement datum.roles |

Role laws:

| Law                             | Meaning                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Datum roles win                 | If datum has roles, span roles do not override.                                                              |
| Roleless datum may inherit span | If datum roles absent/empty, span roles apply.                                                               |
| Controller owns modulation      | Widget class does not call role helpers.                                                                     |
| Read side redaction             | Mismatched datums are redacted/removed from public ctx.                                                      |
| Write side preflight            | Mismatched submissions raise PermissionError.                                                               |
| Event read/fanout filtering     | Datum lifecycle events stay raw in the queue but are released only to roles that can read the event datum.  |
| No invention                    | Controller modulates returned current ctx; it does not invent future matching datums.                        |
| Same-span preservation          | Matched same-span datums remain because they are already in ctx.                                             |

Same-span mixed role example:

```text
span.roles = ["maker"]
PROFILE.roles = ["maker"]
REVIEW.roles = ["reviewer"]
```

Maker view:

```text
PROFILE visible/fillable
REVIEW redacted/not fillable
```

Reviewer view:

```text
PROFILE redacted/not fillable
REVIEW preserved if already in same current span
```

---

## 20. PUBLIC FACADES

Create a session from highest program:

```python
public_api.create_session_from_program(
  program=THINK_PROGRAM,
  program_language="think_program_v1",
  initial_parameter_overrides={},
  session_metadata={
    "manual_io": {
      "persistence": "disabled",
      "include_forms_emitted_order_in_ctx": True
    }
  }
)
```

Headless/scripted stepping:

```python
runner.step_until_stop()

runner.step(
  fill={
    "profile": {"value": "profile-final"}
  }
)
```

Highest UI/controller stepping with role and signals:

```python
dispatch_ui_action(
  session_id,
  action=UserAction.STEP,
  role="maker",
  user_fill={
    "PROFILE.name": "Ada"
  },
  user_signal={
    "datum_id": "PROFILE",
    "kind": "refresh",
    "info": {"reason": "user"}
  },
  render=False
)
```

Controller signal normalization law:

```text
dispatch_ui_action enriches signal.info with:
  datum_id: target datum id
  source: "controller_action"
```

Direct lower API may preserve raw signal info more directly.

Highest facade owns controller provenance.

Live event role law:

```text
controller.loop events:
    queue stores canonical raw payload.U
    role reads/fanout project payload.U for the viewer role

datum lifecycle / reexplosion events:
    queue stores canonical raw event packets
    role reads/fanout drop the event unless the viewer role can read the
    event's datum by the same datum.roles-over-span.roles formalism
```

---

## 21. RUNTIME STATES A HIGHEST DEV SHOULD EXPECT

| Runtime ctx kind     | Meaning                               |
| -------------------- | ------------------------------------- |
| MANUALFILLNEEDEDSTEP | Current span needs fill/signal input. |
| ATCOMPLETION         | Program completed.                    |

At a pending span, highest dev drives the app by sending:

| Packet        | Meaning                                 |
| ------------- | --------------------------------------- |
| fill          | User/manual values for datum widgets.   |
| signal        | Controller/custom action for one datum. |
| fill + signal | Same transition can carry both.         |

Custom signal flow:

```text
┌──────────────────────────────┐
│ user_signal kind="refresh"    │
└───────────────┬──────────────┘
                ▼
┌──────────────────────────────┐
│ controller normalizes signal  │
└───────────────┬──────────────┘
                ▼
┌──────────────────────────────┐
│ widget @signal_catcher        │
└───────────────┬──────────────┘
                ├──▶ Reexplode current shell
                └──▶ True / done
```

---

## 22. LOWERING CHAIN CONTRACT

```python
lower_think_program_to_kernel_program_v1(program)
```

returns:

```python
list[think_kernel_step_v1]
```

```python
lower_think_program_v1(program)
```

returns bundle:

```json
{
  "app_table_manifest": [...],
  "provenance": {
    "source_program_language": "think_program_v1",
    "source_program": "original_source",
    "resolved_run": "symbol_bound_run",
    "explicit_kernel_program": "generated_kernel_program",
    "app_table_manifest": "generated_manifest",
    "lowering_chain": [
      {
        "language": "think_program_v1",
        "artifact": "think_kernel_program_v1"
      },
      {
        "language": "thinking_flow_explicit",
        "artifact": "app_table_manifest"
      }
    ]
  },
  "session_surface": {
    "v": 1,
    "source_program_language": "think_program_v1",
    "run_config": "resolved_run.config"
  }
}
```

App-table row shape:

```json
{
  "public_step_name": "K[\"step\"][\"id\"]",
  "step_fn": "think.kernel.v1",
  "fn_args": {"kernel": "K"}
}
```

---

## 23. STATIC VALIDATION MATRIX

### Top level

| Check            | Rule                              |
| ---------------- | --------------------------------- |
| kind             | must be "think_program_v1"        |
| surface_version  | must be "v1"                      |
| unknown top keys | rejected                          |
| run              | required                          |
| dead JSON        | required for symbols/puppeteering |

### Symbols

| Check                       | Rule                             |
| --------------------------- | -------------------------------- |
| symbol names                | non-empty, cannot start with "$" |
| value                       | required, dead JSON              |
| parametrize                 | defaults false                   |
| puppeteering unknown symbol | rejected                         |
| puppeteering unparametrized | rejected                         |
| exact refs only             | yes                              |
| partial interpolation       | rejected                         |

### run.program

| Check         | Rule                 |
| ------------- | -------------------- |
| required keys | info/widgets/flow    |
| unknown keys  | rejected             |
| micros        | rejected recursively |

### program.info

| Check                 | Rule                 |
| --------------------- | -------------------- |
| id                    | required non-empty   |
| title                 | required non-empty   |

### widgets

| Check                     | Rule                     |
| ------------------------- | ------------------------ |
| widget name               | required non-empty       |
| widget registered         | required                 |
| enforce_no_premount_shell | required true            |
| args                      | checked against contract |
| unknown args              | rejected                 |
| missing required args     | rejected                 |
| wrong arg types           | rejected                 |
| wires                     | checked against contract |
| unknown wires             | rejected                 |
| "__kernel"                | rejected/reserved        |

### flow

| Check                      | Rule                       |
| -------------------------- | -------------------------- |
| non-empty list             | required                   |
| flow ids                   | unique                     |
| widgets                    | non-empty list             |
| widget ids                 | known strings              |
| repeated widget in item    | rejected                   |
| same widget across items   | allowed                    |
| authoritative length       | matches widgets if present |
| authoritative values       | bool                       |
| at least one authoritative | required today             |
| overrides target           | must be in same flow item  |

### wires

| Check                   | Rule                          |
| ----------------------- | ----------------------------- |
| source must be prior    | yes                           |
| required missing source | fails                         |
| optional missing source | omitted                       |
| select                  | latest/all only               |
| max_results             | int >= 1                      |
| multiplicity one        | exactly one resolved alias    |
| multiplicity many       | many aliases allowed          |
| required wire removed   | rejected if no aliases remain |

### roles

| Check           | Rule                 |
| --------------- | -------------------- |
| widget roles    | lower to datum roles |
| flow roles      | lower to span roles  |
| overrides.roles | replace datum roles  |
| datum roles     | win over span roles  |
| controller      | owns role modulation |

### defaults

| Default                                          | Value |
| ------------------------------------------------ | ----- |
| kernel copy_form_frame_span_args_into_each_datum | true  |
| kernel mount_explode_default                     | true  |
| lifecycle mount_explode                          | true  |
| lifecycle max_reexplosions                       | 10    |
| lifecycle max_proc_notes                         | 0     |
| lifecycle max_messages                           | 8     |

### Optional widget arg defaults

| Layer                | Behavior                              |
| -------------------- | ------------------------------------- |
| thinkprogram lowerer | does not inject optional arg defaults |
| kernel runtime       | applies widget contract defaults      |

---

## 24. COMPACT PROGRAM TEMPLATE

```json
{
  "kind": "think_program_v1",
  "surface_version": "v1",

  "symbols": {
    "app.env": {"value": "dev", "parametrize": true},
    "theme": {
      "value": {"density": "compact", "tone": "neutral"},
      "parametrize": true
    },
    "lifecycle.default": {
      "value": {
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8
      }
    },
    "history.latest.required": {
      "value": {
        "select": "latest",
        "required": true,
        "max_results": 20
      }
    }
  },

  "puppeteering": {
    "app.env": "prod"
  },

  "run": {
    "program": {
      "info": {
        "id": "onboarding",
        "title": "Onboarding",
        "args": {
          "env": "$app.env"
        }
      },

      "widgets": {
        "profile": {
          "widget": "acme.profile_source",
          "title": "Profile",
          "args": {"seed": "prod-seed"},
          "lifecycle": "$lifecycle.default",
          "wires": {},
          "roles": ["maker"],
          "tags": ["profile", "source"],
          "system_flags": {"ui_region": "main"},
          "authoritative": true
        },

        "review": {
          "widget": "acme.profile_review",
          "title": "Review",
          "args": {"mode": "strict"},
          "lifecycle": "$lifecycle.default",
          "wires": {
            "previous_profile": {
              "from": "profile",
              "history": "$history.latest.required"
            }
          },
          "roles": ["reviewer"],
          "tags": ["review"],
          "system_flags": {"ui_region": "main"},
          "authoritative": true
        }
      },

      "flow": [
        {
          "id": "collect_profile",
          "title": "Collect profile",
          "widgets": ["profile"],
          "roles": ["maker"],
          "authoritative": [true],
        },

        {
          "id": "review_profile",
          "title": "Review profile",
          "widgets": ["review"],
          "roles": ["reviewer"],
          "authoritative": [true],
          "overrides": {
            "args": {
              "review": {"mode": "strict-review"}
            }
          }
        }
      ]
    },

    "config": {
      "manual_io": {
        "persistence": "disabled",
        "include_forms_emitted_order_in_ctx": true
      },
      "app": {
        "slug": "onboarding",
        "env": "$app.env"
      }
    }
  }
}
```

---

## 25. COMPACT WIDGET TEMPLATE

```python
@thinkwidgetTM_config(
  "acme.profile_source",
  overwrite=True,
  enforce_no_premount_shell=True,
  missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
  args={
    "seed": {"type": "str", "required": true},
    "threshold": {"type": "int", "required": false, "default": 7}
  },
  wires={}
)
class ProfileSourceWidget(DatumLifecycleWidget):

  def _on_mount(self, position, fill_data, limits, stats):
    shell = dict(fill_data["fill_shell"])
    datum_args = dict(shell.get("args") or {})
    kernel = dict(datum_args.get("__kernel") or {})

    self.step_id = dict(kernel.get("step") or {}).get("id")
    self.user_args_on_mount = {
      k: v for k, v in datum_args.items()
      if k != "__kernel"
    }

    lifecycle = dict(shell.get("lifecycle") or {})
    lifecycle["widget"] = "acme.profile_source"

    self.message("info", "profile mounted")

    return Reexplode(
      next_fill_shell={
        "id": shell.get("id", position["datum_id"]),
        "title": "Profile",
        "micros": [
          {
            "name": "value",
            "type": "text",
            "required": true
          }
        ],
        "lifecycle": lifecycle
      },
      pre_computed_fills={"value": ""},
      prefill_hints={"value": "profile-prefill"}
    )

  def _on_fill(self, signal, position, fill_data, limits, stats):
    current = dict(fill_data["current_fills"])
    self.final_value = current.get("value")
    self.commit = {
      "datum_id": position["datum_id"],
      "value": self.final_value
    }
    self.message("success", "profile complete")
    return True

  @signal_catcher("refresh")
  def refresh(self, signal, position, fill_data, limits, stats):
    self.message("info", "refreshed")
    return Reexplode(
      next_fill_shell=dict(fill_data["fill_shell"]),
      pre_computed_fills=dict(fill_data["current_fills"]),
      prefill_hints=dict(fill_data["prefill_hints"])
    )
```

---

## 26. DEVELOPER CHECKLIST

### To add a new app flow

* [ ] Register or reuse admitted thinkwidgetTM class widgets.
* [ ] Ensure each widget has enforce_no_premount_shell=True.
* [ ] Ensure each widget declares args and wires contracts.
* [ ] Pull each widget into kernel contract registry.
* [ ] Write think_program_v1 JSON.
* [ ] Put reusable defaults in run.program.widgets.
* [ ] Put ordered frame sequence in run.program.flow.
* [ ] Use wires for prior committed widget state.
* [ ] Use overrides for local per-frame differences.
* [ ] Use symbols for run/deploy parameters.
* [ ] Use puppeteering only for parametrized symbols.
* [ ] Create session with program_language="think_program_v1".
* [ ] Drive pending spans with fill and signal packets.
* [ ] Use role-aware service/controller facade when roles matter.

### To add a new widget

* [ ] Pick stable registered widget name.
* [ ] Define args contract.
* [ ] Define wires contract.
* [ ] Set enforce_no_premount_shell=True.
* [ ] Implement _on_mount.
* [ ] Generate first visible shell with Reexplode.
* [ ] Author micros in shell, not in app program.
* [ ] Attach micro validators and macro validators.
* [ ] Implement _on_fill.
* [ ] Return Reexplode for next phase or True for done.
* [ ] Store durable facts on self.
* [ ] Use self.message for user-facing lifecycle messages.
* [ ] Add @signal_catcher handlers for custom actions.
* [ ] Choose fallback or raise policy for unknown signals.
* [ ] Test invalid fills do not commit.
* [ ] Test committed state is readable through downstream wires.

### To add a new micro

* [ ] Add MICRO_TYPES entry.
* [ ] Define coercion.
* [ ] Define validator policy.
* [ ] Define optional casts/coerce targets.
* [ ] Use micro type name in widget-generated shell.
* [ ] Attach micro validators.
* [ ] Attach macro validators if cross-field validation is needed.
* [ ] Confirm renderer receives type/args/style.
* [ ] Confirm raw bad fill blocks before commit.
* [ ] Confirm widget sees canonical current_fills.
* [ ] Confirm history carries canonical committed state.

---

## 27. WHAT HIGHEST DEVS SHOULD NOT NEED

Highest app-flow developers should not need to know or author:

```text
explicit kernel datums
explicit kernel history alias names
explicit app-table rows
multiframespec construction
lower lifecycle packet details
low-level fillspan algorithms
renderer hydration internals
role obfuscation internals
runtime write storage internals
```

They should know:

```text
think_program_v1 JSON grammar
thinkwidgetTM class design
micro catalogue / validators
args and wires contracts
fill/signal driving through facades
q["datum"]["args"]["__kernel"] as the continuity seam
validation and role laws at the public behavior level
```

---

## 28. ONE-SCREEN MEMORY

Program:

```text
symbols + puppeteering + widgets + flow
```

Widget:

```text
class + args contract + wires contract + mount shell + fill phases + signals
```

Micros:

```text
generated by widget, data-driven by catalogue, validated/coerced before commit
```

Wires:

```text
logical names -> prior appearances -> compiler history queries -> __kernel.past_wires
```

Roles:

```text
datum roles first, span roles fallback, controller owns modulation
```

Runtime:

```text
pending span accepts fill/signal until authoritative widgets are done
```

Lowering:

```text
think_program_v1
  -> list[think_kernel_step_v1]
  -> app-table rows using think.kernel.v1
```

Core illusion:

```text
Forever-live logical widgets,
arranged into frames,
carrying memory through named historical wires.
```