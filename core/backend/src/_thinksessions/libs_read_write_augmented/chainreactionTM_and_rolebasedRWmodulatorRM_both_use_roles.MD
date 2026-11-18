
### `think-backend/src/_thinksessions/libs_read_write_augmented/chainreactionTM_and_rolebasedRWmodulatorRM_both_use_roles.MD`

```markdown
# Funked Dispatch vs. Role Modulation

```text
                         one canonical roleless session
                                      │
                                      ▼
                         one canonical controller runtime
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
          role modulation boundary               funk continuation layer
                    │                                   │
       controls what may enter and            decides whether and how the
       what may leave for a role              controller is invoked again
                    │                                   │
                    └──────────────┬────────────────────┘
                                   ▼
                         ordinary dispatch surface
                                   │
                                   ▼
                         canonical state and events
````

The two systems touch many of the same public surfaces, especially `role`, `U`, `A`, events, and dispatch identity. But they govern different questions:

```text
Role modulation:
    “What may this role write or observe?”

Funked dispatch:
    “Which role should act next, and what action should it submit?”
```

They are orthogonal in authority, but tightly intertwined in representation. Funk must consume and produce role-scoped information in a way that remains coherent with the role-modulation laws.

---

## 1. Core contrast

| Concern                | Role modulation                                    | Funked dispatch                                            |
| ---------------------- | -------------------------------------------------- | ---------------------------------------------------------- |
| Primary purpose        | Security and information-boundary enforcement      | Automated continuation and role-directed action generation |
| Architectural position | Public write-admission and read-release boundaries | Above ordinary dispatch, as a bounded continuation loop    |
| Canonical engine       | Does not alter it                                  | Does not replace it                                        |
| Role meaning           | Authority and visibility                           | Scheduling and filler selection                            |
| State ownership        | One canonical state                                | Uses the same canonical state                              |
| Event ownership        | One canonical event queue, projected on read       | Generated actions create ordinary canonical events         |
| Write decision         | Whether a submitted target is writable             | Which writable pending targets to offer to a role filler   |
| Read decision          | Which canonical information a role may observe     | Which projected context/history/events the filler receives |
| Action handling        | Authorizes and projects `A`                        | Produces `A` and submits it through ordinary dispatch      |
| Identity handling      | May hide identity during projected release         | Synthesizes a stable identity for generated actions        |
| Failure boundary       | Reject unauthorized input before controller entry  | Stops or raises on bounded continuation conditions         |

The important architectural law is:

> Funk is not a privileged alternate controller interface.

A funk-generated action should cross the same role-aware public dispatch boundary as a manual action. The filler may generate an action, but role modulation remains authoritative about whether that action may enter the engine.

---

# 2. Where they intersect

## 2.1 The `role` parameter has two simultaneous meanings

In role modulation, `role` means:

```text
the authority under which this dispatch or read is performed
```

In funked dispatch, `role` additionally means:

```text
the currently scheduled continuation role whose filler is being invoked
```

These meanings must coincide for a generated dispatch.

```text
scheduled funk role
        │
        ├── selects the role's filler configuration
        ├── selects the request projection
        ├── determines pending writable datums
        └── becomes dispatcher_role on generated dispatch
```

It would be incoherent for funk to invoke the `reviewer` filler using reviewer-projected context but submit the generated action as `maker`.

The invariant should be:

[
v_{\mathrm{scheduled}}
======================

# v_{\mathrm{request}}

v_{\mathrm{dispatch}}
]

where applicable:

```text
scheduled role
    == FunkTMRequest.role
    == role used to project ctx/history/events
    == role passed to ordinary generated dispatch
    == canonical event dispatcher_role
```

That equality is the main point where scheduling semantics and authority semantics meet.

---

## 2.2 `pending_datums` is both workflow state and an authority-filtered capability surface

For funk, `pending_datums` answers:

```text
“What work could this filler attempt now?”
```

For role modulation, it must also answer:

```text
“What work may this role actually write now?”
```

A raw global list of incomplete datums would be unsafe and misleading. It could reveal hidden datum identifiers and encourage the filler to generate unauthorized targets.

Therefore the correct relationship is:

[
P_v(U)
======

\left{
d
\mid
d\text{ is pending in }U
\land
\mathrm{Writable}(v,d,U)
\right}.
]

The request row may contain:

```python
{
    "datum_id": "...",
    "required_roles": [...],
    "decl": ...,
    "current_fill": ...,
}
```

Every field in that row is potentially datum-sensitive. Consequently, inclusion in `pending_datums` should itself require that the role is entitled to the supplied information.

In the common case, writability implies readability because a role is normally readable for its own guarded datums. But the implementation should not rely on that implication accidentally. It should construct each row through the same role-aware projection rules used elsewhere.

A useful capability interpretation is:

> Every datum listed in `pending_datums` is an offered write capability for this invocation.

That makes target validation straightforward:

[
T(A_{\mathrm{funk}})
\subseteq
{d\mid d\in P_v(U)}.
]

Funk's local target check narrows output to the offered pending set. Ordinary role authorization remains the final independent enforcement boundary.

---

## 2.3 `ctx` is not just convenient context; it is a projected security view

The funk request's `ctx` must be:

[
\Pi_U(U,v),
]

not the canonical unmodulated `U`.

That has several effects:

```text
The filler cannot inspect unreadable fills.
The filler cannot inspect hidden declarations.
The filler cannot infer hidden active membership.
The filler cannot inspect hidden validation errors.
The filler cannot recover hidden source or provenance copies.
```

The filler is therefore authored against the same visible world that an end-user role would receive.

This matters even when the filler runs inside trusted backend code. A backend-executed filler may still be logically untrusted with respect to other roles. Role modulation is not only a frontend rendering concern; it defines the semantic information boundary of the role-specific automation.

A coherent system should avoid this pattern:

```python
request.ctx = canonical_U
request.role = "reviewer"
```

That would name the role without enforcing its observational limits.

The coherent form is:

```python
request.ctx = project_U(canonical_U, role="reviewer")
request.role = "reviewer"
```

---

## 2.4 History and events are projected inputs, not canonical replay privileges

Funk may receive bounded `history` and optionally `events`. These surfaces overlap directly with role-modulated event release.

The filler should not receive the canonical queue merely because it is an internal continuation component. It should receive a role-readable view:

[
H_v = \Pi_H(H,v)
]

and, when events are supplied:

[
Q_v =
\left[
\Pi_E(E_i,v)
\mid
\Pi_E(E_i,v)\neq\bot
\right].
]

This entails the same laws as public event reads:

* Controller `U` is projected.
* Controller `A` is projected against the matching start `U`.
* Fully hidden targeted actions lose actor and dispatch correlation identifiers.
* Unreadable datum lifecycle events are omitted whole.
* Visible sequence numbers may contain gaps.
* Hidden canonical positions must not be mistaken for missing storage.

A filler should not infer from sequence gaps that an event was lost. If it needs cursor semantics, it should be given the same scanned-through cursor or visibility receipt concepts used by public polling.

Otherwise funk could accidentally treat role-hidden activity as transport failure or an incomplete history.

---

## 2.5 Generated `A` is governed twice, for different reasons

A funk-generated action packet undergoes two conceptually separate checks.

```text
Funk-local output validation
    │
    ├── valid dead-JSON shape
    ├── at most one signal
    ├── targets belong to pending_datums
    └── result is a valid FunkTMResult
    │
    ▼
Ordinary dispatch preflight
    │
    ├── normalize identity
    ├── normalize role
    ├── obtain canonical entry U
    ├── authorize every target
    ├── resolve exact target locations
    └── perform staleness validation
```

The first check enforces the continuation contract:

> The filler may act only on work explicitly offered to it.

The second enforces the public session contract:

> The submitted role must still be authorized in the actual canonical entry state.

Both are necessary because the state can change between request construction and dispatch, and because defense in depth prevents a malformed or malicious filler from bypassing session authority.

The local pending-target check is not a replacement for role authorization.

---

# 3. The shared action surface

Both systems reason about the same canonical action packet:

```python
A = {
    "fill": {
        "<datum-or-dotted-micro-key>": <dead-json value>,
    },
    "signal": None | {
        "datum_id": "<datum-id>",
        "kind": "<signal-kind>",
        "info": {...},
    },
}
```

Role modulation interprets `A` in two directions:

```text
On write:
    Is every macro datum target writable by dispatcher_role?

On read:
    Which targets of A are readable by viewer_role?
```

Funk interprets `A` as:

```text
The generated continuation proposal to submit next.
```

The shared target function is therefore central:

[
T(A)=T_F(A)\cup T_S(A).
]

For a generated result, coherence requires:

[
T(A)
\subseteq
P_v(U)
\subseteq
{d\mid \mathrm{Writable}(v,d,U)}.
]

Because ordinary dispatch re-evaluates authorization against its own canonical entry `U`, the effective law is stronger:

[
\forall d\in T(A):
\mathrm{Writable}(v,d,U_{\mathrm{generated\ dispatch\ entry}}).
]

This protects against span movement, reexplosion, refresh, or another transition changing the active role resolution after the filler request was formed.

---

# 4. Authoring-surface overlap

The two layers are most visibly intertwined in program sessions.

## 4.1 Datum and span roles define both authority and automation routing

An author writes:

```python
{
    "id": "PROJECT",
    "roles": ["maker"],
}
```

Role modulation interprets this as:

```text
maker may write PROJECT
maker and configured readers may read PROJECT
```

Funked dispatch interprets the same assignment as:

```text
PROJECT contributes pending work to the maker scheduling surface
```

Likewise:

```python
{
    "id": "SHARED_APPROVAL",
    "roles": ["reviewer", "release_ai"],
}
```

means both roles have write authority, and the datum may be offered to either role's filler when pending.

Thus one piece of authoring metadata drives two orthogonal effects:

| Role declaration effect | Role modulation                      | Funk                                         |
| ----------------------- | ------------------------------------ | -------------------------------------------- |
| Write ownership         | Determines admissible dispatch roles | Determines candidate continuation roles      |
| Read release            | Determines role visibility           | Determines what each filler sees             |
| Pending work            | Not itself a scheduling concept      | Used to construct role-specific pending sets |
| Shared roles            | Multiple roles may write             | Multiple fillers may be eligible             |
| Span fallback           | Supplies security ownership          | Supplies scheduling ownership                |

This is where authoring must be especially deliberate. A role annotation is not merely presentation metadata and not merely a workflow assignment. It establishes both authority and automated ownership.

---

## 4.2 `read_roles` affects filler perception, not filler write power

Given:

```python
"reviewer": {
    "read_roles": ["maker"],
}
```

the reviewer filler may see maker-readable information in its projected `ctx` and history.

But it still cannot write maker-only datums:

[
\mathrm{Readable}(\text{reviewer},d,U)
\nRightarrow
\mathrm{Writable}(\text{reviewer},d,U).
]

This enables a useful pattern:

```text
maker filler:
    produces proposal material

reviewer filler:
    reads proposal material
    writes reviewer-owned assessment

release filler:
    reads both
    writes release-owned decision
```

The role graph can therefore establish information flow without collapsing write ownership.

A filler author must not interpret every visible datum as an actionable datum. The authoritative actionable surface is `pending_datums`, not the full visible contents of `ctx`.

That distinction is crucial:

```text
ctx:
    what the role may know

pending_datums:
    what the current filler invocation may try to change
```

---

## 4.3 Role ordering adds workflow semantics not present in role modulation

Role modulation itself does not say which authorized role should act first. It only defines whether reads and writes are permitted.

Funk configuration adds ordering or grouped scheduling:

```python
roles_ordered = [
    "maker",
    ["reviewer", "review_ai"],
    "release_ai",
]
```

Conceptually:

```text
maker barrier
      │
      ▼
reviewer/review_ai group
      │
      ▼
release_ai barrier
```

Role modulation sees each role independently. Funk adds temporal policy:

* Find the earliest role group with pending work.
* Within that group, choose the first configured pending role with an available filler.
* Do not jump to later groups merely because an earlier active group lacks a filler.

This makes role ordering a workflow concern layered above authority.

A role may be fully authorized yet not scheduled because an earlier role barrier remains active.

Conversely, a role may be next in the schedule but unable to act because no writable pending datum is available to it.

---

## 4.4 Filler configuration must agree with authored role vocabulary

Role metadata and funk configuration use the same role names but have different structures:

```python
session_metadata = {
    "roles": {
        "maker": {...},
        "reviewer": {...},
    }
}
```

```python
funk_config = {
    "roles_ordered": ["maker", "reviewer"],
    "roles": {
        "maker": {
            "version": "funk_tm_v1",
            "args": {...},
        },
        "reviewer": None,
    },
}
```

They should be validated coherently.

Useful cross-layer checks include:

```text
Every funk-configured role exists in role metadata.
Every role named in roles_ordered is known.
Every filler role has at least a possible authored ownership surface,
    unless it is intentionally used only for unguarded datums.
Every read_roles reference names a known role.
No accidental spelling differences create unreachable workflow stages.
```

A funk role absent from the role-authoring vocabulary may otherwise become a scheduler entry that can never own guarded work.

A role that owns datums but is omitted from funk configuration may be intentionally manual, but that should be explicit.

---

# 5. Runtime intertwining

## 5.1 Manual dispatch establishes the canonical frontier

A chain begins with an ordinary dispatch:

```text
manual caller
    │
    ▼
role-aware write preflight
    │
    ▼
roleless controller
    │
    ▼
canonical U and events
```

Only after that dispatch completes does funk inspect the new frontier.

This preserves the role-modulation ordering:

```text
authorization before controller start
staleness after authorization
canonical events only after preflight succeeds
```

Funk must not pre-emit a generated controller start or bypass the eventless rejection semantics.

---

## 5.2 Each generated iteration reconstructs role-scoped reality

A coherent generated iteration is:

```text
1. Read canonical current state internally.
2. Resolve active pending datums and required roles.
3. Choose the next scheduled role.
4. Project U for that role.
5. Build that role's writable pending_datums.
6. Project bounded history/events for that role.
7. Invoke the role's filler.
8. Validate the result against the offered pending set.
9. Submit through ordinary dispatch using the same role.
10. Let canonical controller events be emitted normally.
11. Repeat from the new canonical state.
```

The projection should be rebuilt every iteration. It should not reuse a previous role's projection or a stale projected context.

This is particularly important after:

* a span refresh;
* reexplosion;
* frame movement;
* datum creation or retirement;
* changed active ownership;
* semantic rejection;
* a generated signal that alters the active scope.

Required-role resolution is scope-sensitive, so the same datum identifier may have a different relevant assignment after a transition.

---

## 5.3 Span refresh and reexplosion require recomputation, not patching

Suppose a signal causes an active span to reexplode.

Before:

```text
REVIEW_NOTE belongs to reviewer span
```

After:

```text
REVIEW_NOTE is retired
NEW_REVIEW_NOTE belongs to auditor span
```

The next funk iteration must not continue from a cached pending list.

It must recompute:

[
R(d,U_{\mathrm{new}})
]

and then derive new role-specific pending sets.

The role-modulation formalism already states that role resolution is frame- and span-sensitive. Funk must honor that same rule when scheduling.

Otherwise a continuation could:

* expose a retired datum to a filler;
* dispatch under a previous role assignment;
* write through an obsolete location;
* misclassify which role is blocking progress.

Ordinary target resolution and staleness checks provide a final safeguard, but correct funk behavior should avoid forming the invalid proposal in the first place.

---

## 5.4 Semantic rejection is visible through a projected role surface

A semantic rejection remains a successful controller execution with `last_error`.

Funk uses this to detect repeated semantic failure. But the error information supplied to the next filler must be role-coherent.

A raw canonical `last_error` might contain validation details for datums unreadable to the scheduled role. Therefore:

```text
request.last_error
```

should be derived from the role-projected error surface, just as controller event `payload.result.last_error` is derived from projected `U.last_error`.

The semantic-streak detector may internally compare canonical frontier signatures for chain control, but the filler-facing error payload should not reveal more than the scheduled role can read.

This separates:

```text
internal chain accounting:
    may inspect trusted canonical control facts

filler request:
    receives only role-permitted semantic details
```

---

## 5.5 Generated identities participate in canonical events and later projection

A generated dispatch may use an identity such as:

```text
funkedauto-{role}-{initial_identity}
```

Canonically, that identity is recorded on the controller event.

On release to another role, the role-modulation law still applies:

* If at least one action target remains visible, identity and dispatch correlation may remain.
* If all non-empty targets are hidden, `dispatch_id`, `dispatcher_identity_id`, and `dispatcher_role` are nulled.

Therefore a synthetic identity is not automatically public merely because it represents automation.

The distinction between a human and a funk actor belongs to canonical audit semantics. Its visibility still depends on the action projection law.

It may be useful for the identity to encode or accompany a machine-readable origin, but that origin must not become a side channel that defeats full-action hiding.

## 5.6 Generated-dispatch receipt transport

Every generated dispatch may attach one dead-JSON `dispatch_context` to its
controller end event. The context carries chainreaction origin, scheduled role,
filler version, global/per-span generated indexes, and the filler receipt. It
does not duplicate fill or signal, which remain authoritative in `payload.A`.

Because a filler receipt is app-authored and may mention datum-sensitive facts,
event projection treats it conservatively: full target visibility releases the
full receipt; partial target visibility nulls only the filler receipt; complete
target blackout nulls the complete dispatch context together with A and actor
correlation identity.

---

# 6. What each layer must not do

## Role modulation must not become a scheduler

It should not decide:

* which role acts next;
* whether a role has a configured filler;
* how many automated iterations may run;
* whether a noop stops the chain;
* which role group is a workflow barrier.

Those are funk concerns.

## Funk must not become an authority system

It should not decide:

* that a configured filler is trusted to write any datum;
* that visibility implies write authority;
* that an internal caller may use canonical `U`;
* that a scheduled role may bypass ordinary authorization;
* that hidden events should be exposed for better reasoning.

Those are role-modulation concerns.

## Neither should create a second execution universe

There should not be:

* a role-specific session;
* a funk-only controller history;
* a viewer-specific event queue;
* a projected state persisted as canonical state;
* generated writes applied outside the ordinary dispatch path.

Both layers should converge on the same roleless controller and canonical queue.

---

# 7. Surface-by-surface comparison

| Surface        | Role-modulation treatment                               | Funk treatment                                            | Required coherence                                                    |
| -------------- | ------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------- |
| `U`            | Project unreadable datum-owned addresses                | Supplies filler context and frontier information          | Funk receives `Π_U(U,v)`, not raw `U`                                 |
| `A` input      | Authorize all targets before controller entry           | Generated as fill plus optional signal                    | Generated `A` must pass both pending-scope and ordinary authorization |
| `A` event copy | Project targets; possibly null identity envelope        | Generated dispatch appears like any other dispatch        | No special release bypass for automation                              |
| Role           | Defines read/write authority                            | Selects filler and workflow turn                          | Same role must be used for projection and dispatch                    |
| Datum roles    | Define guards                                           | Define candidate role ownership                           | Scheduling derives from authoritative scoped role resolution          |
| Span roles     | Fallback authority                                      | Fallback automated ownership                              | Recompute after scope changes                                         |
| `read_roles`   | Expands visibility only                                 | Expands filler knowledge                                  | Must not expand `pending_datums` write capability                     |
| Events         | Controller fields projected; datum events whole-or-omit | Used as bounded filler history and generated output trace | Filler event input follows same projection law                        |
| Identity       | Canonically recorded; conditionally hidden on release   | Synthetic identity for generated actions                  | Synthetic identity is still subject to blackout                       |
| Cursor         | Scans canonical positions despite hidden events         | May support bounded continuation history                  | Funk must not mistake hidden sequence gaps for loss                   |
| Errors         | Datum-sensitive errors projected                        | Drive semantic retry/stopping behavior                    | Filler-facing errors projected; internal counters may remain trusted  |
| Staleness      | Checked after authorization                             | Can occur after filler request becomes obsolete           | Generated dispatch must use ordinary fresh preflight                  |
| Noop           | No special role meaning                                 | Normal chain stop                                         | Noop does not alter authority semantics                               |
| Caps           | No chain cap concern                                    | Bounds generated execution                                | Caps must not alter projection or authorization                       |

---

# 8. Important asymmetries

## Visibility is broader than actionability

A reviewer filler may see maker output due to `read_roles`, but only reviewer-owned pending datums should be offered for writing.

```text
visible in ctx              writable in pending_datums
──────────────              ──────────────────────────
maker proposal      yes     no
review note         yes     yes
public instructions yes     possibly, if pending and unguarded
```

## Scheduling eligibility is narrower than authorization

A role may legally write a datum but not be selected in the current role-order barrier.

## Canonical chain reasoning may be broader than filler knowledge

The chain implementation may need trusted canonical facts to:

* calculate global span versions;
* enforce end-to-end iteration caps;
* detect unchanged semantic frontiers;
* choose the earliest active role group.

But it must not place all those canonical facts into the filler request.

## Internal `role=None` is not a funk role

The unmodulated administrative event API meaning of `role=None` should not be repurposed as an automation role.

A roleless filler, where supported, should have an explicit semantic definition. It must not accidentally inherit administrative queue visibility.

For public projection:

[
\mathcal R(\varnothing)=\varnothing.
]

For internal canonical event access, `role=None` is a trusted administrative escape hatch. Those are intentionally different meanings and should remain separate APIs or call paths.

---

# 9. Recommended combined invariants

```text
1. One canonical session, controller, state, and event queue.

2. Every funk-generated action enters through the same highest
   role-aware dispatch facade as a manual action.

3. The role selected by the funk scheduler is the role used for:
       request projection,
       pending-datum construction,
       filler configuration,
       generated dispatch,
       canonical dispatcher_role.

4. pending_datums contains only currently pending targets writable
   by the scheduled role.

5. Visible context is not treated as writable capability.
   read_roles never expands pending write targets.

6. Filler ctx, history, events, and error details are role-projected.

7. A filler result is restricted to the invocation's offered
   pending datum set.

8. Ordinary dispatch re-authorizes every generated target against
   its own canonical entry U.

9. Role and target resolution are recomputed after every generated
   dispatch, refresh, reexplosion, or scope transition.

10. Generated controller and datum events use ordinary canonical
    event production and ordinary release projection.

11. Synthetic automation identity does not bypass identity blackout
    for fully hidden targeted actions.

12. Canonical information used for internal cap or progress control
    is not automatically exposed in the filler request.
```

---

# 10. Combined mental model

```text
AUTHORING
─────────
Datum/span role declarations
        │
        ├── define write ownership
        ├── define read projection
        └── define potential automated ownership
        │
Role metadata
        ├── defines readable adjacent roles
        └── does not grant writes
        │
Funk configuration
        ├── attaches fillers to roles
        └── orders when eligible roles act


RUNTIME
───────
Canonical U
    │
    ├── role modulation derives what role v may know
    │
    └── funk derives what pending work role v may attempt
             │
             ▼
       FunkTMRequest(v)
             │
             ▼
       FunkTMResult / A
             │
             ▼
       role-aware dispatch preflight
             │
             ▼
       roleless controller
             │
             ▼
       canonical U' and events
             │
             └── repeat with newly resolved role surfaces


RELEASE
───────
Canonical controller event
    └── stable spine + projected U + projected A

Canonical datum event
    └── release whole or omit whole

Generated and manual dispatches follow the same law.
```

# Final distinction

Role modulation is a **policy membrane** around canonical execution.

Funked dispatch is a **bounded autonomous caller** of that execution.

They overlap because the autonomous caller is role-addressed: it chooses a role, sees a role-shaped world, receives a role-specific work set, and submits an action under that role. They remain orthogonal because funk decides continuation while role modulation decides authority and disclosure.

The cleanest combined law is:

[
\boxed{
\text{Funk may choose who tries next and what they propose;}
\quad
\text{role modulation decides what they may know and whether the proposal may enter.}
}
]

```
```
