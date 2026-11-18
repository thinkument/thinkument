# Using Role-Modulated Thinkument Sessions

## Configure roles

```python
session_metadata = {
    "roles": {
        "maker": {
            "label": "Maker",
        },
        "reviewer": {
            "label": "Reviewer",
            "read_roles": ["maker"],
        },
        "auditor": {
            "label": "Auditor",
            "read_roles": ["maker", "reviewer"],
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

In this example:

* `maker` can read and write maker-owned datums.
* `reviewer` can read maker- and reviewer-owned datums.
* `reviewer` can write only reviewer-owned datums.
* `auditor` can read maker-, reviewer-, and auditor-owned datums.
* `auditor` can write only auditor-owned datums.

`read_roles` never grants write authority.

---

## Assign roles to datums

Prefer explicit datum roles:

```python
{
    "id": "PROJECT",
    "roles": ["maker"],
}
```

A datum may have multiple owning roles:

```python
{
    "id": "SHARED_APPROVAL",
    "roles": ["reviewer", "release_ai"],
}
```

When the datum has no role assignment, the active owning span supplies the fallback:

```python
{
    "id": "REVIEW_SPAN",
    "roles": ["reviewer"],
    "owns": ["REVIEW_NOTE"],
}
```

A datum with no datum or span roles is unguarded.

---

## Create a session

```python
from _thinksessions.run.run_from_here import create_live_session_from_program

created = create_live_session_from_program(
    program=program,
    program_language=program_language,
    session_metadata=session_metadata,
)

session_id = created["session_id"]
```

There is still only one underlying roleless session.

---

## Dispatch an action

```python
from _thinksessions.run.run_from_here import (
    UserAction,
    dispatch_live_session_action,
)

packet = dispatch_live_session_action(
    session_id=session_id,
    action=UserAction.STEP,
    identity_id="user-42",
    role="maker",
    user_fill={
        "PROJECT": {
            "name": "Apollo",
        },
    },
)
```

The caller supplies:

* `identity_id`: the higher application’s actor or client identity;
* `role`: the authority used for this dispatch;
* `user_fill`: zero or more datum-addressed values;
* `user_signal`: optionally one datum-targeted signal.

The role is not trusted merely because the frontend supplies it. The backend checks every submitted target before controller entry.

An unauthorized target raises `PermissionError` and emits no controller or datum events.

---

## Dispatch a signal

```python
packet = dispatch_live_session_action(
    session_id=session_id,
    action=UserAction.STEP,
    identity_id="user-42",
    role="maker",
    user_signal={
        "datum_id": "PROJECT",
        "kind": "refresh",
        "info": {
            "reason": "external change",
        },
    },
)
```

Signals use the same write guard as fills.

---

## Read current context

```python
from _thinksessions.run.run_from_here import get_live_session_context

maker_U = get_live_session_context(
    session_id=session_id,
    role="maker",
)

reviewer_U = get_live_session_context(
    session_id=session_id,
    role="reviewer",
)
```

Each returned context is a projection of the same canonical state.

Readable datum content is preserved.

Unreadable datum content is replaced or removed according to `role_mismatch_policy`.

Do not expose an unmodulated context directly to an end user.

### Read complete current datum state

Use:

```python
for Di in maker_U["datum_states_on_this_span"]:
    if Di["kind"] == "role_mismatch_obfuscated_datum_v1":
        continue

    datum_id = Di["datum_id"]
    latest_shell = Di["shell"]
    micros = Di["micros"]
    semantic_validation = Di["semantic_validation"]
    lifecycle = Di["lifecycle"]
    is_authoritative = Di["is_authoritative"]
    is_pending = Di["is_pending"]
    originating_step = Di["originating_step"]
```

The vector is in active span ownership order, not merely pending/editable
order.

Therefore:

```python
U["datum_widgets_on_this_span"]
```

remains the dynamic pending write-target vector, while:

```python
U["datum_states_on_this_span"]
```

is the complete static current-span datum observation vector.

After lifecycle reexplosion:

```python
Di["shell"]
```

is the latest effective replacement shell. It is not the stale authored shell.

The exact authored micro declaration remains available at:

```python
Di["semantic_validation"]["micros"][i]["spec"]
```

and extracted validation-bearing fields are available at:

```python
Di["semantic_validation"]["micros"][i]["validator_fields"]
```

Do not attempt to reconstruct this joined state by reading private engine
lifecycle memory, cache objects, or snapshots.

---

## Read canonical events internally

```python
from _thinksessions.run.run_from_here import get_live_session_events

canonical_events = get_live_session_events(
    session_id=session_id,
    role=None,
)
```

`role=None` here means the explicit unmodulated administrative queue view.

It exposes canonical packets and should remain inside trusted application or test boundaries.

---

## Read events for a role

```python
reviewer_events = get_live_session_events(
    session_id=session_id,
    role="reviewer",
)
```

For controller events:

* `payload.U` is role-projected.
* `payload.A` is role-projected.
* `payload.fill` and `payload.signal` mirror projected `A`.
* Actor and dispatch identity are nulled when every action target is hidden.

For datum events:

* readable datum event: complete packet returned;
* unreadable datum event: packet omitted.

---

## Poll incrementally

```python
from _thinksessions.run.run_from_here import get_live_session_events_since

cursor = 0

page = get_live_session_events_since(
    session_id=session_id,
    role="reviewer",
    identity_id="reviewer-tab-1",
    after_event_seq=cursor,
    limit=20,
)

for event in page["events"]:
    apply_event(event)

cursor = page["next_after_event_seq"]
```

Always advance with:

```python
page["next_after_event_seq"]
```

Do not advance only to the last visible event’s sequence number. The page may have scanned hidden canonical events after that visible event.

Inspect:

```python
page["visibility_receipt"]
```

to distinguish role-hidden positions from retained-window gaps.

---

## Interpret controller actions

Canonical start and end both contain the same action packet:

```python
event["payload"]["A"]
```

For a permitted mixed action, a viewer may receive only a subset:

```python
{
    "fill": {
        "VISIBLE_DATUM": {...},
    },
    "signal": None,
}
```

The hidden target is absent.

When every target is hidden:

```python
event["payload"]["A"] is None
event["payload"]["fill"] is None
event["payload"]["signal"] is None
event["dispatch_id"] is None
event["dispatcher_identity_id"] is None
event["dispatcher_role"] is None
```

The controller timeline event may remain visible, but it cannot identify the hidden target, dispatcher, or dispatch correlation envelope.

---

## Interpret datum events

A datum lifecycle event is indivisible.

Do not expect a redacted datum event shell.

The event is either present in full or absent from that role’s projected stream.

---

## Interpret dispatch results

Successful applied dispatch:

```python
packet["dispatch_outcome"] == "applied"
packet["write_committed"] is True
```

Semantic rejection:

```python
packet["dispatch_outcome"] == "semantic_rejected"
packet["write_committed"] is False
packet["last_error"] is not None
```

Systematic controller failure:

```python
packet["dispatch_outcome"] == "system_error"
packet["write_committed"] is False
packet["system_error"] is not None
```

Staleness rejection:

```python
packet["dispatch_outcome"] == "stale_rejected"
packet["applied"] is False
packet["rejected"] is True
```

Role authorization failure is raised as `PermissionError` before these controller result forms exist.

---

## Frontend state model

A frontend can maintain:

```text
canonical scanned-through cursor
latest controller U
currently open action envelope
completed action envelopes
orphan informative events
interruptions
orphan controller ends
```

Only controller events update the latest complete `U`.

Datum events are informative and need not contain `U`.

The latest event in the queue is therefore not necessarily a state snapshot.

---

## Security checklist

Use a backend-owned or authenticated role assignment. Do not let an untrusted client freely choose its authority.

Always provide a stable `identity_id`.

Use role-projected context and event APIs for end-user delivery.

Keep `role=None` event reads inside trusted administrative code.

Advance projected pollers with `next_after_event_seq`.

Treat unresolved guarded event role assignments as hidden.

Do not infer write authority from read visibility.

Do not persist projected packets as replacements for canonical history.