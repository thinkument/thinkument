# 3 — ThinkWidgets with Analytica wired in

## The rule

Application widgets authored in `framework-4-services/` and above should inherit:

```python
from authoring_funnel.a_service_tracked_widget_computation.analytics import (
    AnalyticaPoweredDatumLifecycleWidget,
)
```

instead of inheriting `DatumLifecycleWidget` directly.

Signals use:

```python
from authoring_funnel.a_service_tracked_widget_computation.analytics import (
    analytica_signal_catcher,
)
```

instead of the lower-level `signal_catcher`.

That is the complete opt-in.

The widget author does **not** manually emit input, output, or error records.

---

# Why

A normal ThinkWidget lifecycle operation is one of:

```text
mount
fill
signal:<catcher-name>
```

Analytica turns one such invocation into one correlated semantic event stream:

```text
audit-ins
    |
    +-- audit-vendor-usage *
    +-- audit-warning *
    +-- custom audit-* *
    |
audit-outs | audit-error
```

Every Analytica event carries:

```text
protocol
schema
channel
event
operation_id
event_index
widget_class
body
```

For one operation:

```text
operation_id = constant
event_index  = 0, 1, 2, ...
```

The only legal lifecycle is:

```text
input
    -> zero or more middle events
    -> output OR error
```

Illegal:

```text
output/error without input
second input
event-index gap
event after output/error
completed host transaction with an open input
```

Malformed Analytica traffic is a bad widget/run. It is not silently repaired.

---

# `audit-ins`

The mould emits it automatically before the lifecycle handler executes.

Example:

```json
{
  "protocol": "thinkument.analytica.v1",
  "schema": "thinkument.analytica.audit-ins.v1",
  "channel": "audit-ins",
  "event": "input",
  "operation_id": "...",
  "event_index": 0,
  "widget_class": "my_pack.widgets:MyWidget",
  "body": {
    "trigger": "fill",
    "authored_args": {
      "model": "example"
    },
    "history_wires": {
      "source": [
        {
          "accepted": true
        }
      ]
    },
    "current_fills": {
      "answer": "yes"
    },
    "signal": null
  }
}
```

`authored_args` excludes `args.__kernel`.

`history_wires` comes specifically from:

```text
fill_shell
    .args
    .__kernel
    .past_wires
```

Every wire is normalized to:

```text
wire-name -> list[prior public runtime-state]
```

so one/many wire container differences do not leak into the audit contract.

`current_fills` is exactly the fill surface delivered to the running widget.

`signal` is the signal packet for a signal operation and otherwise `null`.

The following framework execution context is intentionally absent:

```text
position
limits
stats
controller context
UI context
arbitrary engine internals
```

---

# `audit-outs`

The mould emits exactly one successful terminal record after the lifecycle
handler returns.

It records two things.

## Lifecycle outcome

Recognized outcomes are:

```text
reexplode
satisfied
unsatisfied
none
other
```

`other` also records the Python type and, when possible, the dead-JSON return
value.

## Public semantic-state delta

The mould snapshots public instance attributes before and after execution.

Public means:

```text
attribute name does not begin with "_"
```

It then emits:

```json
{
  "state_writes": {
    "answer": 42,
    "items": [1, 2, 3]
  },
  "state_deleted": [
    "temporary_public_value"
  ]
}
```

This is deliberately independent of a state-write helper.

All of these are therefore captured:

```python
self.answer = 42

self.items.append("new")

del self.old_value
```

No `write_state_v1()` instrumentation is required.

Private framework/mould attributes beginning with `_` are not semantic state.

Public state must be dead JSON. A public runtime attribute that cannot be
durably represented as dead JSON is an authoring error.

---

# `audit-error`

If the lifecycle handler raises after its `audit-ins` was accepted, the mould
emits exactly one terminal:

```text
audit-error
```

with:

```json
{
  "message": "human-readable exception message",
  "exception_type": "module.ExceptionClass",
  "details": null
}
```

If an exception exposes dead-JSON `details` or `receipt`, it is preserved.

The original exception is then re-raised.

Do not write:

```python
self.audit_error(...)
raise ...
```

There is no such developer API by design.

Just raise.

The mould owns terminal-error correctness.

---

# Vendor operations

Use the timed context manager:

```python
with self.audit_vendor_usage_v1(
    vendor="openai",
    operation="responses.create",
    request={
        "model": model,
        "purpose": "classification",
    },
    attributes={
        "feature": "research",
    },
) as usage:
    response = vendor_call()

    usage.set_usage({
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost_usd_micros": cost,
    })
```

Analytica emits:

```text
audit-vendor-usage
```

with:

```text
vendor
operation
status
elapsed_ms
request
usage
attributes
error
```

If the vendor call raises:

```text
audit-ins
audit-vendor-usage(status=error)
audit-error
```

The exception still propagates.

A one-call sugar is also available:

```python
result = self.audit_vendor_call_v1(
    vendor="vendor",
    operation="operation",
    request={"x": 1},
    call=lambda: client.run(...),
    usage_from=lambda result: {
        "units": result.units,
    },
)
```

Only put sanitized semantic request information in `request`.
Do not place credentials or secrets in analytics.

---

# Warnings

A non-terminal noteworthy condition is:

```python
self.audit_warning_v1(
    "fallback model selected",
    details={
        "requested": requested,
        "selected": selected,
    },
)
```

This produces:

```text
audit-warning
```

A warning does not alter the lifecycle outcome.

---

# Domain-specific analytics

Analytica is extensible without editing Django.

Any channel matching:

```text
audit-*
```

is an Analytica channel.

A custom channel must supply an explicit schema and event:

```python
self.audit_event_v1(
    channel="audit-research-citation",
    schema="research.audit-citation.v1",
    event="citation",
    body={
        "source_id": source_id,
        "accepted": True,
    },
)
```

Its `body` may contain arbitrary dead JSON.

Custom channels may not impersonate the reserved lifecycle event names:

```text
input
output
error
```

Those semantics belong exclusively to:

```text
audit-ins
audit-outs
audit-error
```

---

# Run-level epsilon: governed by `eps_sheet.py`

UI/progress/telemetry/in-the-moment messages should use:

```python
self.emit_eps_v1(
    "my_pack.thinking",
    {
        "text": "Searching source 3...",
    },
)
```

Every channel emitted via `emit_eps_v1(channel, payload)` must be registered on `framework-4-services/src/service_tracked_eps_palette/eps_sheet.py` (`EPS_CHANNEL_SHEET_V1`).

This channel stream travels through the decoupled run-level `eps` channel (`GET /run/<access_id>/eps/`):

```text
ThinkumentJS / HAI / pollers see it on the continuous eps stream
Role modulation (owner-only, all-no-modulation, all-with-modulation) is enforced
Service persistence and post/pre hooks are governed by service_eps_handling_sheet.py
Emissions bypass theta's 32-slot session snapshot ring buffer
```

`emit_live_unpersisted_v1()` remains available as a backward-compatible alias delegating to `emit_eps_v1()`.

---

# No JSON-string heuristic

Never do:

```python
self._emit(
    '{"foo": "bar"}',
    name="audit-something",
)
```

Analytica does not ask:

> "does this string happen to parse as JSON?"

That creates ambiguous contracts.

Instead:

```python
self.audit_event_v1(
    channel="audit-something",
    schema="example.audit-something.v1",
    event="something",
    body={
        "value": "the string if a string is what matters"
    },
)
```

The service receives a native dead-JSON envelope or the widget is invalid.

---

# Minimal widget

```python
from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    Reexplode,
    thinkwidgetTM_config,
)

from authoring_funnel.a_service_tracked_widget_computation.analytics import (
    AnalyticaPoweredDatumLifecycleWidget,
    analytica_signal_catcher,
)


WIDGET = "example.widget.v1"


@thinkwidgetTM_config(
    WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "model": {
            "type": "str",
            "required": False,
            "default": "example",
        },
    },
    wires={},
)
class ExampleWidget(
    AnalyticaPoweredDatumLifecycleWidget
):
    def _on_mount(
        self,
        position,
        fill_data,
        limits,
        stats,
    ):
        del limits, stats

        return Reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Answer",
                "micros": [
                    {
                        "name": "answer",
                        "type": "text",
                        "required": True,
                    }
                ],
                "lifecycle": dict(
                    fill_data["fill_shell"].get(
                        "lifecycle"
                    )
                    or {}
                ),
            },
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        del signal, position, limits, stats

        self.answer = str(
            fill_data["current_fills"]["answer"]
        )
        self.commit = {
            "answer": self.answer,
        }
        return True

    @analytica_signal_catcher("refresh")
    def refresh(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        ...
```

There are no manual input/output/error audit calls.

---

# Django persistence boundary

The service receives all epsilon traffic exactly as before.

Its rule is now:

```text
channel does not match audit-*
    -> never durable

channel matches audit-*
    -> validate Analytica envelope
    -> validate operation ordering
    -> persist append-only
```

This means a UI message cannot crowd the audit database merely because it was
useful live.

It also means an app pack does not need a Django-specific registration step for
a new custom analytics idea.

The protocol itself is the artery.

---

# Querying

The service endpoint accepts:

```text
scope
owner_id
run_kind
run_id
channel
from
to
after_id
limit
group_by_run
```

Normal authenticated user:

```text
scope=mine
```

is implicit and owner sealed.

Staff/admin may explicitly use:

```text
scope=all
```

and optionally:

```text
owner_id=<owner>
```

Examples:

```text
all analytics for my runs
all audit-vendor-usage for me
all messages for one run
all messages on one channel in a time range
all messages for one owner in a time range, as admin
```

The raw append-only table remains the source of truth. Business-specific
aggregation interprets a channel's explicit schema only after indexed
run/owner/channel/time filtering.

---

# Mental model

Analytica is not:

```text
a Django feature
an app-pack feature
a HAI feature
a vendor-cost-only feature
a string logging convention
```

It is:

```text
a strict semantic epsilon protocol
        +
an automatic ThinkWidget lifecycle mould
        +
a service persistence/query destination
```

App packs may use it.

Django may persist it.

Neither defines it.

For optional durable credit accounting composed with these existing events, see
[Economics widget authoring](economics.md). Analytics-only
widgets remain valid with accounting disabled or enabled.
