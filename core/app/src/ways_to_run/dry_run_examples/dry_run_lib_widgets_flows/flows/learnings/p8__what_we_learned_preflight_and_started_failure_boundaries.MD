# P8 — What we learned about dispatch failure boundaries

## The complete app-facing partition

A downstream app should classify a dispatch by **where processing stopped**.

```text
request construction
    -> highest-facade preflight
    -> controller start recorded
    -> datum/controller execution
    -> controller end recorded
```

There are three principal observable families.

### 1. Preflight exception or rejection: no envelope exists

Examples:

* malformed `signal.info`;
* unauthorized fill or signal;
* malformed optimistic event cursor;
* future cursor;
* stale target conflict;
* stale active scope.

The defining law is:

```text
no controller.loop.start
no datum lifecycle event
no controller.loop.end
canonical event high-water unchanged
```

Some preflight failures raise the established caller exception. Request
normalization and role denial are examples.

The highest authoring facade deliberately converts optimistic-cursor failures
into a structured rejection packet:

```python
{
    "ok": False,
    "applied": False,
    "rejected": True,
    "dispatch_outcome": "stale_rejected",
    "rejection_kind": (
        "invalid_event_cursor"
        | "future_event_cursor"
        | "stale_conflict"
        | "stale_scope_changed"
    ),
    "write_committed": False,
}
```

No event packet can be used to discover these failures because no controller
dispatch began. The dispatch caller must inspect the raised exception or return
receipt.

### 2. Admitted semantic rejection: successful controller envelope

Platform semantic validation can reject candidate data before the widget
handler runs. This still occurs **after controller start**.

```text
controller.loop.start
controller.loop.end
    payload.outcome = "success"
    payload.result.last_error = {...}
```

There may be zero informative events. P6 asserts exact emptiness for this case.

The highest facade reports:

```text
applied=True
rejected=False
dispatch_outcome="semantic_rejected"
write_committed=False
system_error=None
```

This is not a controller crash. The engine successfully evaluated the request
and returned a semantic result.

Lifecycle functional rejection is also admitted controller work, but the widget
did run. It may emit messages or custom events and may reexplode. Its domain
rejection is normally expressed through those events and its next shell/state,
not through the platform-owned `U.last_error` slot.

### 3. Started systematic failure: matching system-error end

P8 raises `RuntimeError` from a datum signal catcher. Controller start has
already been committed, so the controller catches the ordinary Python
`Exception` and attempts one matching end:

```text
controller.loop.start
controller.loop.end
    same dispatch_id
    payload.outcome = "system_error"
    payload.system_error.kind =
        "controller_dispatch_system_error_v1"
    payload.system_error.exception_type = "RuntimeError"
```

The highest facade reports:

```text
ok=False
applied=True
rejected=False
dispatch_outcome="system_error"
write_committed=False
```

The complete state for recovery is the `payload.U` on the system-error end. A
later valid dispatch can continue from that recovered state. P8 proves this by
successfully completing the same datum after the intentional exception.

## Why a datum exception lands on controller end

The controller execution body includes datum liaison execution. Once start is
recorded, ordinary `Exception` values from:

* routing;
* STEP/UNDO/REDO liaison calls;
* datum lifecycle handlers;
* context recovery;
* result construction

are normalized to the same bounded system-error packet family.

The controller then obtains the safest available recovery `U`:

1. current liaison context when readable and dead-JSON-safe;
2. otherwise the already accepted entry `U`.

That fallback ensures malformed recovery state does not create a second failure
while constructing the end packet.

An exception whose own `__str__` is broken is bounded to:

```text
"<exception message unavailable>"
```

## What is outside the closure guarantee

The law is intentionally about ordinary in-process Python `Exception`.

It does not promise a matching end after:

* `KeyboardInterrupt`;
* `SystemExit`;
* hard process death;
* machine loss;
* canonical event-sink failure.

The end sink is attempted exactly once. A sink may commit and then raise; retrying
could create a competing duplicate end packet.

A downstream projector may classify an older open envelope as interrupted when
a later controller start arrives. Merely reaching the current high-water while
an envelope is open does not prove that it will never close.

## Complete preflight characterization

### Request normalization before controller identity

These fail before `dispatch_id`, entry `U`, or start emission:

* action is not a `UserAction`;
* `user_fill` is not a dictionary at the controller boundary;
* action packet fill is not a mapping;
* signal is not a mapping;
* signal has no nonempty `datum_id`;
* signal has no nonempty `kind`;
* signal `info` is not a mapping;
* fill/signal packet is not dead JSON.

For non-STEP actions, supplied fill and signal are currently warned about and
normalized away rather than rejected.

### Liaison-owned authorization preflight

A role-aware liaison may reject fills/signals the role cannot write. The highest
facade performs the same role guard before canonical target resolution, and the
lower role-aware controller repeats it as defense in depth.

The result is an eventless `PermissionError`.

### Highest-facade optimistic cursor preflight

The exact cursor contract is `int | None`; booleans, strings, floats, and custom
integer-like objects are invalid.

```text
C omitted -> allow unchecked compatibility
C > A     -> future_event_cursor
C = A     -> allow at_high_water

C < A:
    scope moved after C  -> stale_scope_changed
    target changed after C -> stale_conflict
    otherwise -> allow stale_but_disjoint
```

Scope invalidation has precedence. Reusing a datum id on a later step does not
make an old surface safe.

P8 proves malformed, future, same-scope stale-target, and changed-scope
rejections are all eventless.

## What a poller can and cannot hear

A poller hears only canonical events. Therefore:

```text
preflight failure
    heard as: nothing
    learned from: dispatch call result/exception

semantic rejection
    heard as: controller successful end with last_error
    learned from: event stream and dispatch result

systematic failure
    heard as: controller system_error end
    learned from: event stream and dispatch result
```

This is why a dispatcher-poller has two input channels:

```text
synchronous dispatch receipt
canonical asynchronous event stream
```

The event stream remains the shared source of session evolution. The synchronous
receipt additionally communicates that a proposed mutation never entered that
evolution stream.

## Final creative model

For an app developer, the complete Markovian image is:

```text
dispatch grammar decides whether the request may enter
    -> no entry means no sound on the event stream

controller start announces admitted work
    -> widget/platform/controller semantics happen inside

controller end announces either
    -> success, including semantic rejection as result.last_error
    -> system_error, for an ordinary caught execution exception
```

That is sufficient to author widgets, dispatch safely, and interpret every
ordinary downstream-visible outcome without learning private engine structure.
