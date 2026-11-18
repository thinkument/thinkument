# Thinkument Authoring Templates — Absolute Backend + FormreactTM Readiness

> **Audience:** app authors who want to create ThinkWidgets, ThinkPrograms, session metadata, and FunkTM fillers without reading engine or frontend implementation code.

These templates are the shortest supported path from the formalism sheets to production authoring.
They intentionally preserve the full backend grammar while adding the stricter FormreactTM contracts only where frontend readiness actually adds rules.

This directory is the foundational framework template set. For the higher
service-innovations facets that add service tracking, strict typed ports,
approved JSON widget declarations, and Metal/Crystal publication examples, see
the [public authoring templates](../../../../service-innovations/src/authoring_funneling_templates/README.md).
Those templates compose these framework contracts; they do not replace them.

## 1. The one mental model

```text
AUTHORED STATIC SURFACES                      RUNTIME SURFACES
──────────────────────────────────────       ──────────────────────────────────
ThinkWidget class + decorator contract  ───► lifecycle invocation
ThinkProgram P                         ───► active step/vector + history wires
puppeteering C                         ───► resolved authored values
session metadata SM                    ───► run policy / role projection / UI
FunkTM version registration            ───► FunkTMRequest -> FunkTMResult

FormreactTM additions:
widget panel in authored widget args    ───► formreactTM_config_runtime
session metadata["formreactTM"]         ───► page/host/static aesthetics
```

The backend-ready grammar is the base grammar. FormreactTM readiness is **backend readiness plus a few dead-JSON contracts**; it does not reduce the expressivity of ThinkWidget or ThinkProgram.

## 2. Where frontend readiness is stricter

```text
BACKEND READY
    valid ThinkWidget lifecycle
    valid ThinkProgram grammar
    valid session metadata
    valid registered FunkTM behavior

FRONTEND + BACKEND READY
    all of the above
    + static widget panel names a registered JS generator
    + runtime widget state publishes current renderer/action opinionation
    + all Python→browser opinionation is dead JSON
    + active_signals names exactly the browser-visible legal signal set
    + canonical micros/fills remain semantic truth
    + FormreactTM session metadata uses the registered "formreactTM" pocket
```

No template lets JS become a second backend. The frontend always renders canonical/projected `U` and returns legal `user_fill` / `user_signal` intent through the FormreactTM action membrane.

## 3. Template map

| File | Copy it when you need | Static contract | Runtime contract |
| --- | --- | --- | --- |
| `template_thinkwidget.py` | a new FormreactTM-ready ThinkWidget | widget ID, decorator args/wires, required `formreactTM_widget_panel` arg | mount/fill/signal catchers, `Reexplode`/`True`, `formreactTM_config_runtime` |
| `template_thinkprogram.py` | a new program `P` | symbols, widgets `W`, flow subsets `Wstep`, wires, authority, frontend panels | ordinary ThinkProgram progression; no special frontend runtime grammar |
| `template_thinkprogram_puppeteering.py` | launch-time `C` | parameter overlay mapping | resolved symbol values only; topology unchanged |
| `template_thinkprogram_SM_rolemod.py` | role-modulated reads/writes | roles + mismatch policy | write guard + role-projected reads/events |
| `template_thinkprogram_SM_system.py` | bounded session transport/storage | `manual_io` + `session_storage` | bounded context, event snapshots, redo retention |
| `template_funked_filler.py` | a new registered automated filler | version name + args validator + registration | current `FunkTMRequest` -> bounded `FunkTMResult` |
| `template_thinkprogram_SM_funked.py` | enable chainreactionTM for a run | per-role filler config + global chain config | bounded sequence of ordinary role-authorized STEP dispatches |
| 
## 4. Recommended authoring order

```text
1. ThinkWidget
      define local semantic state machine
      define shell micros and validators
      publish FormreactTM runtime opinionation

2. ThinkProgram P
      place logical widgets into ordered step vectors
      wire committed history explicitly
      choose authoritative datums
      supply each FormreactTM widget panel

3. Puppeteering C
      vary declared parameter symbols without changing topology

4. Session metadata SM
      role modulation if needed
      system/storage caps
      FormreactTM session pocket when using the browser frontend
      chainreactionTM when generated continuation is wanted

5. FunkTM filler
      register executable behavior by version name
      let SM refer only to that version name and inert args
```

## 5. The two widget contracts you must never merge

### Static panel — authored in `P.widgets[widget].args`

```text
formreactTM_widget_panel
    renderer default (`js_gen_name`)
    renderer-specific default args
    host aesthetics
    signal-button presentation defaults
```

### Runtime state — emitted by the widget on every relevant explosion

```text
formreactTM_config_runtime
    current renderer identity / args
    current active_signals
    current semantic_hints
    current presentation-facing state_values
    current runtime aesthetics
```

The static panel is not fill state. Runtime `state_values` is not a duplicate backend database. Canonical shell micros and canonical fills remain the input/output grammar.

## 6. ThinkWidget runtime law

Every handler works from the current invocation plus durable `self` state captured earlier:

```text
mount
    capture authored args + __kernel/wires needed for continuity
    initialize durable semantic state on self
    publish current FormreactTM runtime state
    Reexplode(current shell)

fill/signal
    read current_fills / changed_fills / signal
    update semantic self state
    publish current FormreactTM runtime state
    Reexplode(...) OR True
```

Platform semantic validators on current micros may reject a candidate before the lifecycle catcher runs.

## 7. ThinkProgram law

A program remains purely declarative:

```text
P
├── symbols
├── puppeteering defaults
├── W = logical widget catalog
└── flow
     ├── Wstep1 ⊆ W + authoritative vector + appearance overrides
     ├── Wstep2 ⊆ W + authoritative vector + appearance overrides
     └── ...
```

Frontend readiness does not add a second program language. A step simply contains widgets whose static panel and runtime behavior already satisfy the FormreactTM contract.

The template uses a plain mapping for `PROGRAM`. The supplied reference corpus proves the declarative mapping grammar and runtime consumption, but does **not** establish a canonical external import path for the tutorial convenience `program(...)` builder. This avoids inventing an API dependency.

## 8. Wires are explicit APIs

A consumer reads only authored wire names. Runtime source lifecycle state is found at the documented row state pocket:

```text
fill_shell.args.__kernel.past_wires[wire_name]
    -> row or rows
    -> row["value"]["state"]
```

Prefer the public helpers shown in `template_thinkwidget.py`. Treat producer lifecycle-state keys as a documented semantic API.

## 9. Role modulation law

Given required datum roles `R(d)` and viewing role `r`:

```text
Read(r) = {r} ∪ roles[r].read_roles

write(r,d)
    iff R(d)=[] or r∈R(d)

read(r,d)
    iff R(d)=[] or R(d)∩Read(r)≠[]
```

`read_roles` grants visibility only. It never grants write power.

## 10. FunkTM law

A filler does not mutate the session directly.

```text
current role-projected U
    + exact writable request.pending_datums
    + bounded readable history/events
        ↓
registered filler version
        ↓
FunkTMResult(fill, signal, receipt)
        ↓
ordinary role-authorized STEP
```

Always route writes from `request.pending_datums`. Never infer write authority from arbitrary visible `ctx` contents.

## 11. Session metadata composition

All SM is inert JSON. Compose the fragments you need into one mapping before launch:

```python
SESSION_METADATA = {
    **SESSION_METADATA_SYSTEM,
    **SESSION_METADATA_ROLEMOD,
    # or use the complete SESSION_METADATA_FUNKED when chainreactionTM is enabled
    # plus the registered "formreactTM" pocket for browser aesthetics
}
```

When chainreactionTM is enabled, its role rows are the authoritative role rows because every role must explicitly carry `chainreactionTM_config`.

## 12. Registration checklist

Before launch, the app startup path must register the capabilities it references:

```text
[ ] every ThinkWidget class
[ ] ThinkProgram language/kernel dependencies used by your host app
[ ] FormreactTM session-metadata pocket when using FormreactTM
[ ] every FunkTM version referenced from SM
[ ] renderer portfolio already contains every js_gen_name used by panels/runtime
```

Registration belongs to app startup, not hidden import-time side effects in each program file.

## 13. What to edit first in each copied template

```text
template_thinkwidget.py
    WIDGET_ID
    signal names
    decorator args/wires
    _micros()
    durable self state
    _runtime()
    fill/signal decisions

template_thinkprogram.py
    widget implementation IDs
    widget args/panels
    roles (if guarded)
    wires
    flow vectors and authority
    symbols

template_thinkprogram_puppeteering.py
    only declared parameterizable symbol names

template_thinkprogram_SM_*.py
    roles/policies/caps/version names/args

template_funked_filler.py
    version name
    args validator
    current-micro routing and generated semantic values
```

## 14. Aesthetics status

`template_thinkprogram_SM_aesthetics.py` is intentionally **not** presented as a complete authoring template yet. The supplied material proves the current FormreactTM opinionation helpers and one complete demo, but this template set should not pretend that the final aesthetics authoring grammar has already been frozen. Until that follow-up sheet exists, use the established `formreactTM` metadata pocket and the dedicated aesthetics documentation/demo rather than treating the placeholder as normative.

## 15. Forever rules

```text
□ Backend semantics stay canonical.
□ FormreactTM opinionation is dead JSON.
□ Renderer IDs are registered names, not Python/JS function pointers.
□ Static panel and runtime state are different surfaces.
□ Runtime active_signals is the exact browser-visible signal set.
□ Reexplode/True remains the widget decision algebra.
□ ThinkProgram owns composition/progression, not DOM behavior.
□ Wires own history dependencies; widgets do not scan global history.
□ SM owns orthogonal run policy; it does not define another program.
□ Roles project/guard one canonical session; they do not create role-specific sessions.
□ FunkTM generates ordinary STEP dispatches; it has no mutation side door.
□ request.pending_datums is the generated-write authority.
□ Human barriers are roles with chainreactionTM_config=None.
□ Renderer-local state may never become secret backend authority.
□ Aesthetics template is deferred until its dedicated formalism is finalized.
```
