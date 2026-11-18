# P9 — What we learned: role-modulated reads and writes

## One run, not one run per role

The engine executes one canonical roleless state machine:

```text
one session
one program tape
one active form/frame/span
one datum lifecycle state per physical appearance
one canonical bounded event queue
```

Roles do not fork the session and do not create parallel event histories.

They act at two public membranes:

```text
dispatch admission
event/context release
```

## Role metadata

P9 creates the session with:

```python
{
    "roles": {
        "maker": {
            "read_roles": [],
        },
        "reviewer": {
            "read_roles": ["maker"],
        },
        "auditor": {
            "read_roles": [],
        },
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            "maker": "redacted",
            "reviewer": "redacted",
            "auditor": "redacted",
        },
    },
}
```

A role row may contain additional app-owned dead-JSON metadata. The engine-owned
role law uses `read_roles`.

## Datum role assignment

The logical widget declaration may carry:

```python
WIDGETS["daily"]["roles"] = ["maker"]
WIDGETS["guess"]["roles"] = ["reviewer"]
```

The effective required roles for a datum are resolved in this order:

```text
datum.roles
datum.role
span.roles
span.role
[]
```

An empty role set means unguarded.

P9 leaves `board` unguarded.

## Formal read/write law

For datum `d` and role `r`, let `R(d)` be the datum's effective required roles.

Let:

```text
Read(r) = {r} union roles[r].read_roles
```

Then:

```text
write_allowed(r, d)
    iff R(d) is empty
    or r is in R(d)
```

and:

```text
read_allowed(r, d)
    iff R(d) is empty
    or R(d) intersects Read(r)
```

The asymmetry is deliberate:

```text
read_roles grants read visibility
read_roles never grants write permission
```

## Dispatch grammar

An action carries its dispatch role beside the ordinary action packet:

```python
STEP(
    role="maker",
    fill={
        "daily": {
            "representative_number": 9,
            "good_day": True,
        }
    },
)
```

The role is not embedded in widget fill data and is not a signal.

The highest facade performs authorization before:

```text
canonical target resolution
optimistic cursor classification
controller start
datum execution
```

The lower role-aware liaison repeats the guard as defense in depth.

## Unauthorized write outcome

When reviewer tries to write maker-owned `daily`:

```text
PermissionError
no controller.loop.start
no datum event
no controller.loop.end
canonical high-water unchanged
```

This is a preflight failure, not a semantic rejection.

The same law holds when maker tries to write reviewer-owned `guess`.

## Canonical event storage

Canonical reads use:

```python
get_live_session_events(
    session_id=sid,
    role=None,
)
```

These packets are unmodulated.

Role projection never rewrites canonical storage and repeated projected reads
never move the canonical high-water.

## Projected event release

Named viewers use:

```python
get_live_session_events_since(
    session_id=sid,
    role="reviewer",
    after_event_seq=cursor,
)
```

### Controller events

Controller packets remain visible for every valid named role.

Their stable event spine remains canonical:

```text
event_id unchanged
event_seq unchanged
phase unchanged
action unchanged
name/source/session_id/emitted_at unchanged
payload.timestamp unchanged
```

Their `payload.U` is projected for the viewer.

Both start and end also carry the same canonical action packet:

```text
payload.A = {"fill": ..., "signal": ...}
```

For each target datum in `A`, the target is retained only when the viewer can
read that datum. `payload.fill` and `payload.signal` are exact compatibility
mirrors of projected `payload.A`.

The correlation/actor envelope follows this rule:

```text
A has no datum targets
    -> dispatch_id, dispatcher_identity_id, dispatcher_role remain canonical

projected A retains at least one readable datum target
    -> dispatch_id, dispatcher_identity_id, dispatcher_role remain canonical

canonical A has targets but projected A retains none
    -> payload.A = null
    -> payload.fill = null
    -> payload.signal = null
    -> dispatch_id = null
    -> dispatcher_identity_id = null
    -> dispatcher_role = null
```

`event_id` and `event_seq` are never hidden by this action projection. They
preserve the shared temporal spine without leaking who acted on which fully
unreadable datum.

### Datum lifecycle events

A guarded datum lifecycle event is released only when the viewer can read the
datum.

Unreadable datum events remain in canonical storage but are omitted from that
viewer page.

Unguarded datum events remain visible to all roles.

## Why projected event sequences may have gaps

Suppose the canonical interval is:

```text
41 controller start
42 daily success
43 guess started
44 guess hint
45 controller end
```

A maker who cannot read reviewer-owned guess may see:

```text
41 controller start
42 daily success
45 controller end
```

Those are not lost packets. The visibility receipt acknowledges the hidden
canonical positions.

Therefore a role-projected poller must advance with:

```python
cursor = page["next_after_event_seq"]
```

It must not use:

```python
cursor = page["events"][-1]["event_seq"]
```

because a page may end after hidden canonical positions or may contain no visible
datum event between controller packets.

## Public projected `U`

A projected controller `payload.U` carries:

```python
U["role_mismatch_modulation_info"]
```

including:

```text
role_viewing
read_role_names
assignments
mismatches
mismatch_datum_ids
role_mismatch_policy
```

Readable datums retain their normal shells and metadata.

Unreadable datums are removed from editable membership vectors and replaced by
an inert redacted declaration such as:

```python
{
    "kind": "role_mismatch_obfuscated_datum_v1",
    "role_mismatch_obfuscated": True,
    ...
}
```

Aggregate datum-addressed `last_error` is projected by the same read law.

## P9 transition proof

The strongest action in P9 closes maker-owned daily and mounts reviewer-owned
guess in one dispatch.

Canonical middle:

```text
daily success
guess started
guess hint
```

Maker view:

```text
daily success
```

Reviewer view:

```text
daily success
guess started
guess hint
```

because reviewer owns guess and has `read_roles=["maker"]`.

Auditor view:

```text
no guarded datum events
```

All three views receive the same controller start/end event ids and event
sequences. The auditor receives a blacked-out action and actor/correlation
envelope for the maker-only `daily` dispatch.

That is the exact downstream experience of one roleless run under projected
release.

## Creative cognitive image

A higher app developer may think:

```text
the current span exposes a set of datum sinks

my dispatch role may write only sinks assigned to me
my viewing role hears only sinks I may read

the engine still advances one shared span state machine
controller events keep the shared temporal spine
datum events are released according to my read projection
```

No deeper engine structure is required.

## Complete practical recipe

1. Author datum/span roles in the ThinkProgram.
2. Create the session with `roles` and `role_mismatch_policy`.
3. Dispatch through `run_from_here` with one explicit role.
4. Treat `PermissionError` as eventless preflight denial.
5. Poll with one explicit viewing role.
6. Apply visible events in order.
7. Advance from `next_after_event_seq`.
8. Use controller `payload.U` as the latest complete projected UI state.
9. Never treat `read_roles` as write delegation.
10. Use `role=None` only for trusted canonical/internal reads.

That is the complete P9 formalism.