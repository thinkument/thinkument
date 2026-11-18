# P7 — What we learned: session metadata is the activation/modulation head

## The creative model

A ThinkProgram defines **what the application does**:

```text
logical widgets
flow steps
authoritative datums
wires
symbols
puppeteering
```

Session metadata defines **how this one live run is activated and released**:

```text
manual I/O policy
bounded storage policy
role modulation
registered app-owned pockets
future specialized activation pockets
```

The useful formal split is:

```text
ThinkProgram P
    + session metadata M
    + initial parameter overrides Θ
    -> one live session S
```

`M` does not create another semantic program. It parameterizes orthogonal
runtime policies around the same compiled/unrolled program.

## Highest authoring surface

The app-facing creation call is:

```python
created = create_live_session_from_program(
    program=PROGRAM,
    program_language=LANG_THINK_PROGRAM_V1,
    initial_parameter_overrides=PUPPET or {},
    session_metadata=SESSION_METADATA,
)
```

The dry-run row therefore owns four independent authoring inputs:

```python
DryRunRow(
    name=...,
    program=...,
    puppet=...,
    session_metadata=...,
    unrolling=...,
)
```

That placement is important. Session metadata is not hidden in the test runner,
not inserted into widget args, and not encoded as a fake flow step.

## Canonical metadata surface

The engine-owned top-level keys are:

```text
roles
role_mismatch_policy
manual_io
session_storage
```

Applications may also contribute dead-JSON top-level pockets. Registered pockets
receive schema validation. Unknown pockets remain pass-through during full
session creation for compatibility.

P7 demonstrates an inert app pocket:

```python
{
    "dry_run_lib_widgets_flows_activation": {
        "kind": "dry_run_lib_widgets_flows_activation_v1",
        "lesson": "session metadata is an orthogonal activation head",
        "features": [...],
        "enabled": True,
    }
}
```

The pocket is data, not behavior. Executable behavior belongs in a registry and
metadata may select it by stable string/version name.

## Dead-JSON law

Session metadata crossing the public membrane is declarative:

```text
dict
list
str
int
float
bool
None
```

Live callables do not belong in metadata.

This matters because metadata is copied into public context, controller events,
snapshots, server payloads, and downstream poller state.

## `manual_io`

`manual_io` controls the shape and cost of the interactive context membrane.

P7 activates:

```python
{
    "persistence": "disabled",
    "profile": True,
    "include_full_multiframespec_in_ctx": True,
    "include_global_fill_keys_in_ctx": False,
    "include_field_value_keys_in_ctx": False,
    "include_forms_emitted_order_in_ctx": True,
    "max_fields_per_submit": 64,
    "max_payload_chars": 100_000,
}
```

These are runtime I/O policies. They do not change Wa/Wb/Wc domain semantics.

## `session_storage`

`session_storage` bounds duplicated live/durable session material:

```python
{
    "events_snapshot_window": 64,
    "forms_emitted_snapshot_window": 7,
    "redo_max_depth": 4,
    "redo_action_max_payload_chars": 20_000,
}
```

The event queue is intentionally bounded. It is a live synchronization stream,
not permanent infinite audit history.

A downstream poller must therefore use canonical cursor receipts and detect a
retained-window gap when it falls behind.

## Public proof through controller events

Every admitted dispatch still has:

```text
controller.loop.start
    zero or more datum/external events
controller.loop.end
```

Both controller packets carry complete `payload.U`.

P7 asserts the effective metadata at:

```python
event["payload"]["U"]["session_metadata"]
```

on both start and end for every action.

This proves that the activation head is part of the public Markov state heard by
downstream listeners. A poller does not need private session objects to know the
effective runtime policy.

## Orthogonality proof

P7 then runs ordinary Wb and Wa behavior:

```text
mount daily
fill daily
mount guess
fill guess
complete
```

The same widget messages and lifecycle transitions occur as in earlier programs.

Therefore:

```text
session metadata modulates the run
session metadata does not replace the run
```

## Why P7 precedes P9

Role modulation is one specialized sub-surface of session metadata.

P7 establishes the general box:

```text
session metadata = scalable activation/modulation head
```

P9 then zooms into:

```text
roles
role_mismatch_policy
dispatch write admission
context/event read release
```

FunkTM and chainreactionTM are other app-owned metadata pockets and should keep
their own specialized executable sheets.

## Exact app-developer takeaway

For a creative app developer:

```text
author the ThinkProgram for semantic flow
author ThinkWidgets for datum state machines
supply session metadata for orthogonal runtime policy
dispatch only through the highest facade
hear resulting evolution through the canonical event queue
```

That is the complete top-down model required for P7.