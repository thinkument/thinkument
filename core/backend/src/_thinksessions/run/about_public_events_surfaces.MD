### `think-backend/src/_thinksessions/run/runme_surfaces_out/about_public_events_surfaces.MD`

````markdown
# Final boxed surface grammar sheet

## Atomic dispatch-trident heading

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ DISPATCH TRIDENT                                                           │
│                                                                             │
│     Estart  +  Emsgs*  +  Eend                                              │
│                                                                             │
│ Logical atomicity law:                                                      │
│     one accepted dispatch owns exactly one complete timeline                │
│                                                                             │
│     start(dispatch_id)                                                      │
│       followed by zero or more messages(dispatch_id/correlation scope)      │
│       followed by exactly one end(dispatch_id)                              │
│                                                                             │
│ No consumer should treat Estart alone as a completed dispatch.              │
│ Final U authority belongs to Eend.payload.U.                                │
└─────────────────────────────────────────────────────────────────────────────┘
````

The current canonical queue assigns events individually. Therefore this is presently **logical atomicity**, not durable storage atomicity. True durable atomicity would require the controller event-producing module and queue commit operation to append an entire dispatch batch under one transaction. That controller implementation file was not among the pasted files, so an exact safe code diff for batch commit cannot be supplied from this input alone.

A poller can nevertheless enforce logical atomicity by buffering a start event until its matching end event arrives.

---

## All pocket outlines

### `A` — dispatch action packet

```text
┌─ A: controller_action_packet_v1 ──────────────────────────────┐
│ fill                                                          │
│   <datum_id> -> datum fill                                    │
│ signal                                                        │
│   datum_id                                                    │
│   kind                                                        │
│   info                                                        │
└───────────────────────────────────────────────────────────────┘
```

### `Estart` — controller loop start event

```text
┌─ Estart: controller_loop_event_v1 / phase=start ──────────────┐
│ identity                                                      │
│   kind, event_id, event_seq, emitted_at                       │
│ correlation                                                   │
│   dispatch_id, dispatcher_identity_id, dispatcher_role        │
│ addressing                                                    │
│   session_id, action                                          │
│ payload                                                       │
│   timestamp                                                   │
│   A                                                           │
│   fill        compatibility mirror of A.fill                  │
│   signal      compatibility mirror of A.signal                │
│   U           canonical/projected dispatch-entry U             │
└───────────────────────────────────────────────────────────────┘
```

### `Emsgs*` — zero or more datum lifecycle events

```text
┌─ Emsg: datum_lifecycle_event_v1 ──────────────────────────────┐
│ identity                                                      │
│   kind, event_id, event_seq, emitted_at                       │
│ source                                                        │
│   source, name                                                │
│ addressing                                                    │
│   form_id, frame_id, span_id, datum_id                        │
│ signal                                                        │
│   signal_kind                                                 │
│ payload                                                       │
│   renderer-agnostic dead-JSON message/event content           │
└───────────────────────────────────────────────────────────────┘
```

### `Eend` — controller loop end event

```text
┌─ Eend: controller_loop_event_v1 / phase=end ──────────────────┐
│ identity and correlation                                      │
│   same outline as Estart                                      │
│ payload                                                       │
│   timestamp                                                   │
│   A, fill, signal                                             │
│   U           final post-dispatch/recovered U                  │
│   outcome     success | system_error                           │
│   result      on success                                      │
│   system_error on systematic failure                          │
│   dispatch_context on generated funk dispatches only           │
└───────────────────────────────────────────────────────────────┘
```

`payload.dispatch_context` is present only on `controller.loop.end` for a
chainreactionTM-generated dispatch. It carries the filler version, generated
dispatch indexes, scheduled role, and filler receipt. Generated fill/signal
remain solely in `payload.A`. Named-role projection nulls the whole context when
all targets are hidden and nulls only `filler_receipt` when target visibility is
partial.

### `U` — universal UI context

```text
┌─ U: renderer-agnostic universal UI context ───────────────────┐
│ runtime identity                                              │
│   session_id, form_id, app_form_id                            │
│   current_frame_id, current_frame_name                        │
│   current_span, current_span_id                               │
│ navigation                                                    │
│   frames, span_order, span_to_datum_widgets                   │
│ runtime                                                       │
│   kind, cursor, step, state, globals                          │
│ renderer datum surfaces                                      │
│   datum_widget_decls                                          │
│   datum_widget_fills                                          │
│   datum_widgets_on_this_span      dynamic pending subset       │
│   datum_states_on_this_span       static [D1, ..., Dk]          │
│ source/specification                                          │
│   multiframespec, tags, session_metadata                      │
│ errors and role projection                                   │
│   last_error                                                  │
│   role_assignments                                            │
│   role_mismatch_modulation_info                               │
└───────────────────────────────────────────────────────────────┘
```

### `Di` — current span-owned datum state

```text
┌─ Di: universal_ui_datum_state_v1 ─────────────────────────────┐
│ identity                                                      │
│   datum_id, form_id, frame_id, span_id                        │
│ current span status                                           │
│   is_authoritative, is_pending                                │
│ exact effective shell                                         │
│   shell                                                       │
│   micros, micro_names                                         │
│   args,                                                       │
│ value                                                         │
│   fill, has_fill                                              │
│ semantics                                                     │
│   semantic_validation.datum_validator_fields                  │
│   semantic_validation.micros[]                                │
│       name, spec, validator_fields                            │
│ lifecycle                                                     │
│   enabled, policy, runtime                                    │
│ provenance                                                    │
│   originating_step.public_step_name                           │
│   originating_step.source_step_fn                             │
│   originating_step.source_fn_args                             │
└───────────────────────────────────────────────────────────────┘
```

### Poll page `P`

```text
┌─ P: live_session_events_since_v1 ─────────────────────────────┐
│ request basis                                                 │
│   session_id, role, identity_id, after_event_seq              │
│ canonical window                                              │
│   session_earliest_event_seq                                  │
│   session_latest_event_seq                                    │
│   scanned_through_event_seq                                   │
│   next_after_event_seq                                        │
│   canonical_gap_detected                                      │
│ visibility                                                    │
│   visibility_receipt                                          │
│ events                                                        │
│   [Estart | Emsg | Eend, ...]                                 │
└───────────────────────────────────────────────────────────────┘
```

---

# Fully populated traversal example

## 1. Caller dispatches `A`

```python
A = {
    "fill": {
        "complex": {
            "description": "Complete deterministic role information layer proof",
            "long_description": (
                "Prove guarded writes projected reads and canonical queue storage"
            ),
            "slug": "role-information-layer-proof",
            "contact_email": "demo@example.com",
            "target_date": "2026-07-13",
            "snippet": "value = 1\nprint(value)",
            "formula": "x^2 + y^2",
            "hero_image_url": "https://example.com/image.png",
            "local_image_path": "./images/example.png",
            "count": "3",
            "confidence": "8",
            "metadata": {
                "task": "D",
                "proof": "role-layer",
            },
            "ready": True,
            "pause_ack": True,
        }
    },
    "signal": None,
}
```

Dispatch call:

```python
receipt = dispatch_live_session_action(
    session_id=session_id,
    action=UserAction.STEP,
    identity_id="maker-user",
    role="maker",
    user_fill=A["fill"],
    user_signal=A["signal"],
    my_current_event_seq_number=known_event_seq,
)
```

## 2. Poll receives `Estart`

```python
Estart = {
    "kind": "controller_loop_event_v1",
    "event_id": "start-event-uuid",
    "event_seq": 41,
    "dispatch_id": "dispatch-uuid",
    "dispatcher_identity_id": "maker-user",
    "dispatcher_role": "maker",
    "emitted_at": "2026-07-27T18:22:10.123456+00:00",
    "source": "page_flow_controller",
    "name": "controller.loop.start",
    "phase": "start",
    "session_id": "session-uuid",
    "action": "STEP",
    "payload": {
        "timestamp": "2026-07-27T18:22:10.123456+00:00",
        "A": A,
        "fill": A["fill"],
        "signal": None,
        "U": {
            "kind": "MANUALFILLNEEDEDSTEP",
            "session_id": "session-uuid",
            "form_id": "complex",
            "app_form_id": "complex",
            "current_frame_id": "complex.frame",
            "current_frame_name": "Complex",
            "current_span": "complex.span",
            "current_span_id": "complex.span",
            "datum_widgets_on_this_span": ["complex", "support"],
            "datum_states_on_this_span": [
                # D1 and D2 in exact span ownership order.
            ],
            "...": "other U pockets",
        },
    },
}
```

Interpretation:

```text
Estart.payload.U
    is the dispatch-entry observation.

Estart.payload.A
    is interpreted against this entry U for role projection.

A must not later be reinterpreted against Eend U after a span transition.
```

## 3. Poll receives `Emsg₁ … Emsgₙ`

```python
Emsg1 = {
    "kind": "datum_lifecycle_event_v1",
    "event_id": "datum-event-uuid-1",
    "event_seq": 42,
    "emitted_at": "2026-07-27T18:22:10.124000+00:00",
    "source": "datum_widget",
    "name": "datum.message",
    "form_id": "complex",
    "frame_id": "complex.frame",
    "span_id": "complex.span",
    "datum_id": "complex",
    "signal_kind": "fill",
    "payload": {
        "message": {
            "level": "info",
            "text": "Description accepted; exposing decision fields.",
        }
    },
}
```

```python
Emsg2 = {
    "kind": "datum_lifecycle_event_v1",
    "event_id": "datum-event-uuid-2",
    "event_seq": 43,
    "emitted_at": "2026-07-27T18:22:10.124500+00:00",
    "source": "datum_widget_result",
    "name": "datum.shell.reexploded",
    "form_id": "complex",
    "frame_id": "complex.frame",
    "span_id": "complex.span",
    "datum_id": "complex",
    "signal_kind": "fill",
    "payload": {
        "message_type": "shell_changed",
        "micro_names": ["decision", "publish"],
    },
}
```

Role law:

```text
viewer can read complex
    receives each entire packet unchanged

viewer cannot read complex
    receives neither packet

No field-level datum-event redaction is performed.
```

## 4. Poll receives `Eend`

```python
Eend = {
    "kind": "controller_loop_event_v1",
    "event_id": "end-event-uuid",
    "event_seq": 44,
    "dispatch_id": "dispatch-uuid",
    "dispatcher_identity_id": "maker-user",
    "dispatcher_role": "maker",
    "emitted_at": "2026-07-27T18:22:10.125000+00:00",
    "source": "page_flow_controller",
    "name": "controller.loop.end",
    "phase": "end",
    "session_id": "session-uuid",
    "action": "STEP",
    "payload": {
        "timestamp": "2026-07-27T18:22:10.125000+00:00",
        "A": A,
        "fill": A["fill"],
        "signal": None,
        "outcome": "success",
        "result": {
            "event_kind": "MANUALFILLNEEDEDSTEP",
            "ui_mode": "FORM_FILL",
            "finished": False,
            "last_error": None,
        },
        "U": {
            "kind": "MANUALFILLNEEDEDSTEP",
            "session_id": "session-uuid",
            "form_id": "complex",
            "app_form_id": "complex",
            "current_frame_id": "complex.frame",
            "current_frame_name": "Complex",
            "current_span": "complex.span",
            "current_span_id": "complex.span",
            "datum_widgets_on_this_span": ["complex"],
            "datum_states_on_this_span": [
                {
                    "kind": "universal_ui_datum_state_v1",
                    "datum_id": "complex",
                    "form_id": "complex",
                    "frame_id": "complex.frame",
                    "span_id": "complex.span",
                    "is_authoritative": True,
                    "is_pending": True,
                    "shell": {
                        "id": "complex",
                        "title": "Release decision",
                        "micros": [
                            {
                                "name": "decision",
                                "type": "choice",
                                "required": True,
                                "args": {
                                    "semantic_name": "release_decision",
                                },
                            },
                            {
                                "name": "publish",
                                "type": "boolean",
                                "required": True,
                                "args": {
                                    "semantic_name": "publish_confirmation",
                                },
                            },
                        ],
                        "lifecycle": {
                            "widget": "demo.semantic-shell.v1",
                            "mount_explode": False,
                            "max_reexplosions": 3,
                        },
                        "roles": ["maker"],
                        "authoritative": True,
                    },
                    "micros": [
                        {
                            "name": "decision",
                            "type": "choice",
                            "required": True,
                            "args": {
                                "semantic_name": "release_decision",
                            },
                        },
                        {
                            "name": "publish",
                            "type": "boolean",
                            "required": True,
                            "args": {
                                "semantic_name": "publish_confirmation",
                            },
                        },
                    ],
                    "micro_names": ["decision", "publish"],
                    "fill": {
                        "decision": None,
                        "publish": None,
                    },
                    "has_fill": True,
                    "semantic_validation": {
                        "datum_validator_fields": {},
                        "micros": [
                            {
                                "name": "decision",
                                "spec": {
                                    "name": "decision",
                                    "type": "choice",
                                    "required": True,
                                    "args": {
                                        "semantic_name": "release_decision",
                                    },
                                },
                                "validator_fields": {},
                            },
                            {
                                "name": "publish",
                                "spec": {
                                    "name": "publish",
                                    "type": "boolean",
                                    "required": True,
                                    "args": {
                                        "semantic_name": "publish_confirmation",
                                    },
                                },
                                "validator_fields": {},
                            },
                        ],
                    },
                    "lifecycle": {
                        "enabled": True,
                        "policy": {
                            "widget": "demo.semantic-shell.v1",
                            "initial_state": {},
                            "mount_explode": False,
                            "max_reexplosions": 3,
                            "exhausted_means_satisfied": True,
                            "max_proc_notes": 8,
                            "max_messages": 8,
                        },
                        "runtime": {
                            "status": "reexploded",
                            "reexplode_count": 1,
                            "state": {
                                "phase": "decision",
                            },
                            "messages": [
                                {
                                    "level": "info",
                                    "text": (
                                        "Description accepted; exposing "
                                        "decision fields."
                                    ),
                                }
                            ],
                            "proc_notes": [],
                        },
                    },
                    "originating_step": {
                        "public_step_name": "complex",
                        "source_step_fn": "demo.complex.step",
                        "source_fn_args": {
                            "flow_id": "complex",
                        },
                    },
                },
                {
                    "kind": "universal_ui_datum_state_v1",
                    "datum_id": "support",
                    "...": "second span-owned datum",
                },
            ],
            "...": "other U pockets",
        },
    },
}
```

The caller’s final working state is:

```python
final_U = Eend["payload"]["U"]

datum_states = {
    row["datum_id"]: row
    for row in final_U["datum_states_on_this_span"]
}

complex_Di = datum_states["complex"]

semantic_micro_specs = (
    complex_Di["semantic_validation"]["micros"]
)
is_authoritative = complex_Di["is_authoritative"]
current_shell = complex_Di["shell"]
```

No custom traversal through lifecycle memory, render cache, multiframespec overlays, step provenance, and role metadata is needed.

---

# Polling artery with trident buffering

```python
cursor = 0
open_dispatches = {}
completed_dispatches = []

while True:
    page = get_live_session_events_since(
        session_id=session_id,
        role="maker",
        identity_id="maker-ui",
        after_event_seq=cursor,
        limit=50,
    )

    cursor = page["next_after_event_seq"]

    for event in page["events"]:
        if event["kind"] == "controller_loop_event_v1":
            dispatch_id = event.get("dispatch_id")

            if event["phase"] == "start":
                open_dispatches[dispatch_id] = {
                    "start": event,
                    "messages": [],
                    "end": None,
                }
                continue

            if event["phase"] == "end":
                bundle = open_dispatches.setdefault(
                    dispatch_id,
                    {
                        "start": None,
                        "messages": [],
                        "end": None,
                    },
                )
                bundle["end"] = event
                completed_dispatches.append(bundle)
                open_dispatches.pop(dispatch_id, None)
                continue

        if event["kind"] == "datum_lifecycle_event_v1":
            # Current datum packets have no dispatch_id field. When strict
            # correlation is required, the controller queue layer should stamp
            # dispatch_id onto them or enqueue an atomic dispatch batch.
            #
            # Until then, events occurring between one start and its end can be
            # associated only when the controller serializes one dispatch at a
            # time.
            if len(open_dispatches) == 1:
                bundle = next(iter(open_dispatches.values()))
                bundle["messages"].append(event)

    for bundle in completed_dispatches:
        if bundle["start"] is None or bundle["end"] is None:
            continue

        final_U = bundle["end"]["payload"]["U"]
        consume(final_U)

    completed_dispatches.clear()
```

For a fully durable and unambiguous trident, the next event-protocol version should add `dispatch_id` to datum lifecycle events or wrap the complete dispatch timeline in one canonical batch packet. That requires the unprovided controller-event construction path, not a change to `Di` or U.

---

# Final surface rules

```text
┌─ U/Di final laws ───────────────────────────────────────────────────────────┐
│ U is a dead-JSON observation, not a second engine state authority.          │
│                                                                             │
│ U.datum_states_on_this_span is ordered exactly like current span_owns.      │
│ It contains all owned datums, not only pending datums.                       │
│                                                                             │
│ U.datum_widgets_on_this_span is the dynamic pending/editable subset.         │
│                                                                             │
│ Di.shell is the exact latest effective multiframespec datum shell.           │
│ A compiled renderer-cache shell must never replace it.                       │
│                                                                             │
│ Di.semantic_validation preserves authored validator fields/specifications;   │
│ it does not execute validators or become validation authority.               │
│                                                                             │
│ Di.lifecycle.runtime is a read-only copy of canonical lifecycle memory.      │
│                                                                             │
│ Di.originating_step carries MANUAL-step provenance and source function args. │
│                                                                             │
│ role=None returns canonical U. Named roles receive projected U.              │
│                                                                             │
│ An unreadable Di is replaced atomically by one inert marker.                  │
│ No shell, micros, args, validators, fills, lifecycle, or provenance leak.    │
│                                                                             │
│ Projection always operates on a detached copy and never mutates canonical U. │
└──────────────────────────────────────────────────────────────────────────────┘
```

````