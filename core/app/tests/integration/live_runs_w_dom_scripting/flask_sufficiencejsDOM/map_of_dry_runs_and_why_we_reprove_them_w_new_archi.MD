# Map of the dry-run programs and why we re-prove them through the new DOM architecture

## Delivery plan

This directory is a second, deliberately independent proof membrane over the same robust authored widgets and flows.

1. Keep the authored application material as the only shared semantic source: `P`, `SM`, `C`, widget registrations, and the real `sufficience.js` opinionation.
2. Do **not** import `DRY_RUN_CASES`, `FUNKED_DRY_RUN_CASES`, `expected_unrolling`, the dry-run runner, strategy adapters, or A/E matchers in the new scripts.
3. Launch the normal Flask live-run stack through `ways_to_run.live_run_DOMscripted_atelier`, with `start_on_create=False`, so the browser script owns the first `STEP` exactly like a real user-facing client can.
4. Drive only public rendered controls (micro editors, signal controls, funk toggle, STEP/UNDO/REDO) and public ThinkumentJS browser/loopback read seams.
5. Synchronize causally: dispatch result -> canonical `after_event_seq` -> every browser page `syncTo(high_water)` -> rendered sufficience cursor reaches the same high-water -> semantic assertion.
6. For P13, additionally capture the rendered normalized inbound packet stream and prove epsilon/theta reconciliation through the actual opinionation DOM.
7. Keep P9 and P12 from Task A unchanged; they are already successful proofs of role-modulated DOM IO and funked/human collaboration respectively.

The only new shared helper, `_flask_test_support.py`, is a DOM/ThinkumentJS convenience layer. It is not a dry-run adapter and contains no P/SM/C/A/E case language.

---

## The system that these programs are exercising

### 1. A thinkwidget is the reusable functional cube

A logical thinkwidget declaration has two distinct lives.

**Static/authored life**

A ThinkProgram declaration chooses a registered widget implementation and gives it authored configuration such as:

- logical datum/widget id;
- widget implementation/version string;
- title/presentation metadata;
- static `args`;
- lifecycle/system execution caps (`max_reexplosions`, `max_messages`, `max_proc_notes`, exhaustion policy, etc.);
- authored `wires` and history selection rules;
- write-owner `roles` where guarded;
- tags and system flags;
- authoritativeness, either from the logical declaration or the effective step appearance.

The declaration is not the mutable runtime instance. It is the recipe from which the engine mounts the widget when a step requires it.

**Runtime life on one active step/span**

When the widget mounts, it sees its effective authored args plus kernel information, its resolved past-wire rows, its own prior writes where relevant, and its current lifecycle limits/state. It then either:

- declares itself satisfied; or
- returns/re-explodes with a current micro shell to be filled again.

The current shell describes the input micros available *now*. A later re-explosion may expose a different shell. A dispatch may target the widget with fill data and/or a signal. Platform micro validation happens before widget lifecycle code. If platform validation admits the candidate, the fill handler or signal catcher runs, may write runtime state, emit informative events/messages, and either satisfy or re-explode.

Satisfaction is monotonic for that widget appearance on that span: once satisfied during forward stepping, it is not made unsatisfied by another ordinary STEP on the same span.

The important separation is therefore:

```text
logical widget declaration
        |
        v
step appearance + effective overrides + C-resolved values
        |
        v
mounted runtime widget
        |
        +-- current micro shell
        +-- runtime state writes
        +-- resolved wire/history rows
        +-- emitted informative events
        +-- satisfied OR re-explode with next shell
```

P1, P3, P4, and P6 isolate different parts of this cube lifecycle.

---

### 2. A ThinkProgram `P` is the organizer of the widget superset over time

`P` is not another widget. It is the static flow graph / ordered step organizer.

The shown program grammar has the shape:

```text
P
├── symbols
├── authored puppeteering/default symbol assignments
├── widgets: W = {logical widget declarations}
└── flow
    ├── step 1: W1 subset W + authoritative vector + appearance overrides
    ├── step 2: W2 subset W + authoritative vector + appearance overrides
    └── ...
```

A step is a data sink. It remains the current span until every authoritative widget appearance on that span is satisfied. Non-authoritative widgets may remain open/re-explodable without preventing progression.

The program owns composition rules such as:

- which subset of `W` appears on each step;
- per-appearance arg overrides;
- per-appearance lifecycle overrides;
- per-appearance title/tag/system-flag overrides;
- wire assignments and wire/history behavior;
- the explicit authoritative vector;
- symbols reused throughout those authored surfaces.

P1 proves the most intuitive composition/progression picture. P2 proves the broader authoring language. P3 proves lifecycle override behavior. P4 proves the exact runtime meaning of wires/history.

---

### 3. Puppeteering `C` is launch-time parameterization over both `P` and `SM`

The current live scripted launcher correctly treats launch C as a joint parameter overlay over the two symbol-bearing authored surfaces:

```text
Param(P) union Param(SM)
        ^
        |
        C
```

The Flask local launch spec is an older seam that accepts an already-effective program and already-separated session metadata. The scripted Flask launcher therefore performs the canonical routing once before crossing that seam:

1. route `C` over `{program: P, session_metadata: SM}`;
2. bind/resolve symbolic SM;
3. split effective SM into metadata / roles / mismatch policy for the Flask session surface;
4. hand the effective P + effective SM to the existing server/session machinery.

It does **not** invent a second overlay language.

P2 is the executable proof of the P side of this authoring formalism. It uses both launch overlay modes:

- `merge_onto`: supplied C assignments override authored puppeteering while unspecified authored assignments survive;
- `take_over`: supplied C becomes the puppeteering pocket and unspecified symbols fall back to declared symbol defaults.

The same joint routing mechanism is available when symbols live in SM.

---

### 4. Session metadata `SM` is the orthogonal runtime activation/modulation head

`SM` surrounds one program run with runtime policy; it does not create a second program/state machine.

The shown closed surface includes the major pockets:

- `manual_io` and related session behavior/configuration;
- `session_storage` bounds/caps;
- role declarations and `read_roles` relationships;
- role mismatch/read projection policy and its receipt modes;
- funked chain-reaction configuration, role schedule, filler versions and retry/cap behavior;
- app-owned dead-JSON metadata pockets that should survive normalization.

P8 (the source file is historically named `program7__...`) proves ordinary SM activation metadata. P9 proves role-modulated reads/writes. P12 proves chain-reaction/funked SM.

---

### 5. A thinksession is one suspended run of `(P, SM, C)`

The conceptual tape is:

```text
(P, SM, C)
    |
    v
session at one current step/span
    |
    +-- STEP(data and/or signal)
    +-- UNDO(no data/signal)
    +-- REDO(no data/signal)
```

Dispatch is the mutation boundary. A public dispatch is screened against the current state, including action shape, active/pending targets, role authority, visible shell/micro shape, and canonical cursor ownership.

A processed dispatch creates a controller envelope/trident:

```text
A
|
+-- controller start event (U_before)
+-- zero or more informative datum/widget events
+-- controller end event   (U_after)
```

The canonical queue is contiguous. Consecutive committed controller boundaries obey the continuity law:

```text
T_i.end.payload.U == T_(i+1).start.payload.U
```

Two observation channels matter to the frontend:

- **epsilon**: request-scoped provisional dispatch progress while the dispatch is in flight, without canonical `event_seq` on provisional events;
- **theta**: canonical committed queue advancement, including pages where the role projection hides all visible middle events but the canonical cursor still advances.

P13 is the direct frontend blanket proof of those two channels. P9 is the direct role-projection proof. P12 proves that a funked dispatch is still a chain of normal dispatch envelopes whose continuation is decided from SM/filler state.

---

## What ThinkumentJS + `sufficience.js` expose to the higher frontend

ThinkumentJS owns the transport/client kernel. Higher app code gets a much smaller, stable surface.

### Canonical/read-only `Q` and opinionated writable `X`

- `Q` is ThinkumentJS-owned canonical client state: cursor, committed/open tridents, latest projected U, etc.
- `X` is persisted opinionated frontend state owned/persisted by ThinkumentJS but writable by higher app code through loopback.

### Inbound: theta and epsilon become one normalized packet shape

`inbound.js` normalizes both channels into:

```text
thinkument_information_inbound_v1
├── trigger
│   ├── kind: theta | epsilon
│   ├── canonical
│   └── provisional
├── context
│   ├── session_id
│   ├── identity_id
│   ├── role
│   ├── Q
│   └── X
└── information
    └── trigger-specific theta/epsilon data
```

The opinionation's `drink(packet, loopback)` receives the same normalized outer grammar for both heartbeats.

### Womb: ergonomic semantic reads over the same blanket

`womb.js` adds higher-level read sugars without owning new truth. Among the shown helpers are:

- current U / runtime kind / scope / step;
- all widgets on span, readable widgets, active widgets;
- authored widget args, shell/micros, fill, runtime state;
- session metadata and provenance;
- role modulation info/receipt/read projection;
- per-widget access probes through the public dispatch validator;
- committed tridents, action packets, dispatch timeline and boundary continuity;
- semantic errors;
- funk contexts, filler receipts, next-funkability and funk sequence;
- theta old/new Q and new canonical events;
- epsilon provisional rows/events and dispatch-progress packet.

### Outbound: the higher app cannot forge transport ownership

The public loopback surface is:

```text
readQ()
readX()
writeX(...)
validateDispatch(publicA)
dispatch(publicA)
```

The public A surface accepts only higher-app fields (`action`, `userFill`, `userSignal`, `funked`, optional `requestId`). Identity, role and canonical cursor are ThinkumentJS-owned.

`outbound_guard.js` screens what can be proven locally from the latest Q/U:

- action is STEP/UNDO/REDO;
- non-STEP cannot carry fill/signal;
- STEP target is on the current span and still pending/enabled/editable;
- current role has write authority;
- targeted micros are in the visible current shell and have compatible known primitive type;
- dispatch is blocked while a canonical envelope is open;
- semantic validator presence is identified but validator truth remains backend-owned.

That last point is why P6's platform-invalid numeric value is still a legitimate DOM integration test: the action shape and type are valid, so it reaches backend semantic validation.

### `sufficience.js` is the minimal complete diagnostic opinionation

It renders:

- a summary (`trigger`, cursor, role, runtime kind, active ids);
- the lossless current normalized inbound packet;
- one fieldset per readable active datum;
- one include checkbox + dead-JSON editor per current micro;
- optional signal controls;
- funked chain-reaction checkbox;
- optional request id;
- STEP / UNDO / REDO buttons;
- a secondary exact-**public**-A diagnostic composer;
- local validation receipt and server dispatch result.

It deliberately does **not** expose identity, role or canonical cursor forgery controls.

Therefore it is close to the theoretical minimal sufficient DOM station for all *valid public* next actions, while also exposing enough current blanket information to inspect the run.

---

## Why DOMScriptrTM is a separate useful proof layer

DOMScriptrTM is application-agnostic browser scripting infrastructure:

```text
Engine (one reusable Playwright Browser)
  -> Run (optional pluggable server starter + URL map)
      -> Client A (isolated BrowserContext identity)
      -> Client B
      -> ...
```

It does not know Thinkument. The scripted live-run adapter supplies a Thinkument Flask server starter; the test script then uses raw Playwright/DOMScriptr operations.

This gives a different failure membrane than the standard dry-run framework:

- the standard dry-run suite proves the canonical P/SM/C/A/E formalism across strategies;
- the DOM scripted suite proves that a concrete server + ThinkumentJS + chosen opinionation actually renders the needed information and can originate the intended public actions through real browser behavior.

That independence is exactly why re-proving the robust flows is useful rather than redundant.

---

## Program map and coverage

| Program | Core question | Nitty-gritty ground covered | DOM-script status |
|---|---|---|---|
| **P1** | Can widgets compose and progress as a real multi-step program? | mount -> fill -> re-explode -> satisfy; repeated logical widget usage; cross-step history wire; mixed authoritative/non-authoritative span; step transition mounting next widget in same dispatch | **New:** `flask_sufficienceDOM_dryrun1.py` |
| **P2** | Is ThinkProgram an executable authoring language rather than a hard-coded flow? | symbols; whole-value/nested symbol lookup; authored puppeteering; C `merge_onto` and `take_over`; per-appearance title/tag/system-flag/lifecycle/arg overrides; repeated widget; signal-only STEP; fill+signal; multi-datum vector fill; cross-widget wire; UNDO/REDO | **New:** `flask_sufficienceDOM_dryrun2.py`, two independent sessions |
| **P3** | Do lifecycle/system execution flags change runtime behavior exactly at the widget boundary? | generous vs tight re-explosion caps; non-authoritative open re-exploder; authoritative gate; exhaustion with `exhausted_means_satisfied=True` forcing completion | **New:** `flask_sufficienceDOM_dryrun3.py` |
| **P4** | What is the exact runtime meaning of args, wires, history, and self-previous? | authored args separate from `__kernel.past_wires`; multiplicity one vs many; latest history; optional wire absence; `from={self: previous}` becoming an ordinary runtime wire row; mount-time proof event | **New:** `flask_sufficienceDOM_dryrun4.py` |
| **P5** | — | No P5 case exists in the shown current catalog. | **No case to port** |
| **P6** | Where is the boundary between platform semantic validation and widget functional validation? | signal-only with blank required micros; platform min/max rejection before handler/catcher and exact-empty middle; lifecycle rejection after platform admission with ordinary error event/re-explosion; final accepted completion | **New:** `flask_sufficienceDOM_dryrun6.py` |
| **P7** (`program8__events_heard__preflight...`) | What happens at adversarial dispatch/preflight failure boundaries? | shared case includes malformed/lower-wire fixtures and forged canonical cursor facts; these are intentionally below the human/public browser membrane | **Skipped by design** |
| **P8** (source file historically named `program7__...`) | Is SM really one orthogonal activation head around ordinary program semantics? | normalized `manual_io`; storage caps; app-owned metadata pocket; metadata stability across dispatch boundaries; ordinary widget/program progression under same SM | **New:** user-requested filename `flask_sufficienceDOM_dryrun7.py` |
| **P9** | Are write authority and read projection role-modulated correctly through a real browser UI? | named role pages/identities; `read_roles` does not imply write; public unguarded datum; projected active shells; obfuscated guarded datum; local write denial without canonical cursor advancement; final role-specific completion | **Already proven in Task A:** `test_flask_sufficienceDOM_dryrun9.py` |
| **P10** | Dispatch start/end projection asymmetries | This flow is referenced by the catalog but its source was intentionally not part of the supplied Task-B flow inputs or requested output set. | **Out of this delivery scope; not a claim of DOM impossibility** |
| **P11** | — | No P11 case exists in the shown current catalog. | **No case to port** |
| **P12** | Can SM-driven funked chain reaction automate segments, retry semantic errors, cycle roles, and stop at human barriers? | generated filler roles; semantic retry; many widgets/many roles; generated -> human barrier -> generated; multiple human/funked segments; funk checkbox and server chainreaction receipt through real DOM | **Already proven in Task A:** `test_flask_sufficienceDOM_dryrun12.py` |
| **P13** | Does the frontend receive the complete live/canonical blanket needed for a real app? | real normalized epsilon + theta packets rendered by opinionation; provisional/canonical event parity modulo `event_seq`; canonical cursor barriers; role-projected U; mismatch receipt; hidden-middle views still advance cursor; consecutive controller U continuity | **New:** `flask_sufficienceDOM_dryrun13.py` |

---

## Explicit skip decisions

### P7 / `program8__events_heard__preflight_invalidation...`: skip the full case

This is the principled browser-membrane exclusion already encoded in the real browser strategy.

The shared P7 case contains adversarial transport-boundary fixtures, including forged canonical cursor / malformed lower-wire shapes. A real browser opinionation must **not** give a human/higher app controls for those facts. ThinkumentJS owns identity, role and canonical cursor serialization.

Weakening `sufficience.js` merely to make those malformed fixtures expressible would make the integration test less faithful to the intended architecture.

Important distinction: ordinary public guard denials can still be tested through DOM (Task-A P9 does this), and backend micro semantic rejection can still be tested through DOM (new P6 does this). What is skipped is the part that requires forging transport-owned state.

### P10: leave outside this Task-B batch

P10 is named in `dry_run_cases.py`, but the actual P10 flow source was not among the Task-B pasted flow files and no `flask_sufficienceDOM_dryrun10.py` was requested. Therefore this delivery does not reconstruct it from the case name alone.

This is a scope/input decision, **not** a conclusion that the public DOM cannot express P10. If its authored flow is supplied later, its start/end projection asymmetries can be evaluated against the same rendered-Q machinery used by P9/P13.

---

## How the programs collectively cover the major system pillars

The useful way to read the suite is not "thirteen unrelated demos" but a set of orthogonal cuts through one machine:

```text
THINKWIDGET CUBE
  P1  composition + progression
  P3  lifecycle caps/exhaustion
  P4  args/wires/history
  P6  shell semantic validation vs lifecycle validation

THINKPROGRAM AUTHORING
  P1  W subsets + authoritativeness
  P2  symbols + C + appearance overrides + signals + undo/redo
  P4  authored wires materialized at runtime

SESSION METADATA / SESSION POLICY
  P8  general SM activation/storage/manual-IO pockets
  P9  role read/write modulation
  P12 funked chain-reaction schedule/fillers/retries/human barriers

FRONTEND / DISTRIBUTED CLIENT BLANKET
  P9  real role-sealed pages and public write guard
  P13 epsilon/theta + projected Q/U + cursor continuity

FULL INTEGRATION
  authored P/SM/C
      -> existing Flask server around run-from-here/session machinery
      -> ThinkumentJS Q/X + outbound guard + polling/progress
      -> sufficience opinionation
      -> DOMScriptr real Chromium clients
      -> DOM actions / DOM+JS expectations
```

Together, the new DOM scripts plus the already-passing P9/P12 scripts re-prove the main behavioral/integrative pillars from a membrane that is intentionally independent of the dry-run strategy framework.

---

## Files in this Task-B delivery

New shared direct-DOM support:

- `_flask_test_support.py`

New program repro scripts:

- `flask_sufficienceDOM_dryrun1.py`
- `flask_sufficienceDOM_dryrun2.py`
- `flask_sufficienceDOM_dryrun3.py`
- `flask_sufficienceDOM_dryrun4.py`
- `flask_sufficienceDOM_dryrun6.py`
- `flask_sufficienceDOM_dryrun7.py` (catalog P8 / historical `program7__...` source)
- `flask_sufficienceDOM_dryrun13.py`

Map/documentation:

- `map_of_dry_runs_and_why_we_reprove_them_w_new_archi.MD`

Existing Task-A proofs intentionally left unchanged:

- `test_flask_sufficienceDOM_dryrun9.py`
- `test_flask_sufficienceDOM_dryrun12.py`
