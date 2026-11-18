What is proven is narrower and more useful than “everything always works”: for the modeled ThinkPrograms, ThinkWidgets, action packets, lifecycle transitions, history wiring, undo/redo behavior, and facade event polling, the observable contract is deterministic and validated end to end.

## 1. What we learned about authoring ThinkWidgets

A ThinkWidget is best treated as a small deterministic state machine.

It should own four things:

1. Its public lifecycle state.
2. Its accepted fill names.
3. Its signal handlers.
4. Its decision about whether the current dispatch completes, re-explodes, or remains manually fillable.

The widget should not inspect arbitrary nested history looking for values that “look right.” It should read known semantic paths.

For example:

```python
daily_number = history_row["value"]["state"]["representative_number"]
```

and:

```python
previous_target = history_row["value"]["state"]["target_number"]
previous_hint = history_row["value"]["state"]["hint"]
```

That gives each widget a stable wiring contract.

### Public widget state should be semantic

Good state:

```python
self.phase = 1
self.target_number = 20
self.hint = "previous result"
self.game_done = False
self.outcome = None
self.counted_failures = 0
self.last_guesses = []
```

Poor state:

```python
self.data = {...}
self.tmp = [...]
self.number = 20
```

The first version makes lifecycle history reusable by downstream widgets and inspectable by tests, pollers, debuggers, and future programs.

### Fill handling should be explicit

A widget should consume only the fills it owns:

```python
guesses = [
    fill_data["guess_1_1"],
    fill_data["guess_1_2"],
    fill_data["guess_1_3"],
]
```

or by a constrained prefix:

```python
guesses = [
    value
    for name, value in fill_data.items()
    if name.startswith(f"guess_{self.phase}_")
]
```

It should not recursively search an entire dispatch packet for integers. Packets may contain sequence numbers, epochs, counters, identifiers, and history metadata that happen to be numeric.

## 2. How different ThinkWidgets can behave

The tests establish several reusable widget patterns.

### A. Producer widget

A producer widget exposes a value that later widgets consume.

Example:

```python
self.representative_number = submitted_number
```

Its lifecycle state becomes part of program history.

Downstream widgets then consume that exact semantic field.

### B. Multi-explosion interactive widget

A guessing widget can span several explosions while remaining one logical widget experience.

Typical state progression:

```text
mount
  ↓
phase 1 fills exposed
  ↓ wrong
re-explode
  ↓
phase 2 fills exposed
  ↓ correct or exhausted
complete
```

The important design rule is that re-explosion is not a new unrelated widget. It is the same widget advancing its own state.

### C. Stateful accumulator widget

An accumulator can expose several independently named fills:

```text
new_1
new_2
new_3
```

It can validate the proposed update and preserve its previous state when the update is rejected.

For example:

```python
proposed_total = current_total + sum(new_values)

if proposed_total > maximum:
    emit_error(...)
    return MANUAL_FILL_NEEDED
```

Rejected input should not partially mutate durable state.

### D. Signal-aware widget

Signals are commands, not ordinary fills.

Examples include:

```text
adjust_min
do_not_count
restart
```

A signal can change how the next evaluation is interpreted without disguising itself as user field data.

A useful principle is:

```text
fills describe submitted values
signals describe requested behavior
```

## 3. How to author ThinkPrograms

A ThinkProgram composes widgets and defines their wiring.

The program should make dependencies explicit:

```text
Wb produces representative_number
Wa consumes Wb representative_number
Wa also consumes its own previous lifecycle result
Wc consumes or follows earlier program state
```

The program does not need to manually orchestrate every internal widget callback. It declares enough structure for the platform to mount the appropriate widget, deliver the dispatch packet, capture the resulting lifecycle state, and continue.

### Program history is an API

Once a widget completes or re-explodes, its lifecycle value is not just an implementation detail. It becomes program history.

That history should therefore contain stable semantic fields:

```python
{
    "state": {
        "representative_number": 9,
    }
}
```

or:

```python
{
    "state": {
        "target_number": 20,
        "hint": "derived from daily number",
        "phase": 2,
        "game_done": True,
        "outcome": "success",
    }
}
```

This lets later widgets wire themselves organically from earlier results.

## 4. The expected right-hand-side lifecycle

For each dispatch packet, the caller should observe one lifecycle result on the right-hand side.

The significant lifecycle outcomes are:

### `MANUALFILLNEEDEDSTEP`

The current widget remains active and expects more user input.

This occurs when:

* the widget has just mounted and exposed fills;
* submitted data is incomplete;
* submitted data is rejected but recoverable;
* the widget re-explodes into another interactive phase.

Conceptually:

```text
dispatch → widget processes packet → active widget still requires interaction
                                      ↓
                           MANUALFILLNEEDEDSTEP
```

### `ATCOMPLETION`

The active unit has reached its terminal successful or accepted state.

This means the dispatch caused the current widget or program step to complete.

Conceptually:

```text
dispatch → accepted terminal transition → ATCOMPLETION
```

### Re-explosion

Re-explosion is observable through lifecycle state and exposed fills, while the right-hand-side result remains interactive:

```text
wrong first-round guesses
    ↓
state.phase becomes 2
    ↓
second-round fills are exposed
    ↓
MANUALFILLNEEDEDSTEP
```

So re-explosion is not confused with completion.

### Undo

Undo restores the preceding durable lifecycle/program state.

Expected behavior:

```text
completed state
    ↓ UNDO packet
previous interactive or prior committed state restored
```

The undo dispatch has its own dispatch event group. It is not an invisible local mutation.

### Redo

Redo reapplies the state removed by undo.

Expected behavior:

```text
undone state
    ↓ REDO packet
previously completed state restored
```

Redo likewise produces its own complete dispatch event group.

## 5. Exact event-stream contract for pollers

For every dispatched packet, pollers should receive one bounded event group.

The expected outer sequence is:

```text
DISPATCH_STARTED
    ↓
zero or more internal/public domain events
    ↓
DISPATCH_ENDED
```

The start and end events bracket all events caused by that packet.

A typical successful interactive dispatch looks like:

```text
DISPATCH_STARTED
INFO / domain event
INFO / cumulative event
DISPATCH_ENDED
```

A completion dispatch might look like:

```text
DISPATCH_STARTED
SUCCESS / guessed correctly
DISPATCH_ENDED
```

A rejected but recoverable dispatch might look like:

```text
DISPATCH_STARTED
ERROR / validation or rule event
DISPATCH_ENDED
```

The dispatch can still end normally even when its domain outcome is an error. “Dispatch ended” means the platform processed the packet successfully; it does not mean the user action was accepted.

## 6. What the tested streams demonstrate

### Program 1

The important sequence is:

```text
mount program/widget
→ MANUALFILLNEEDEDSTEP
```

Then a daily-number submission produces its lifecycle value.

The guessing widget reads that semantic value from history.

Wrong guesses produce the expected informational “closest” event and leave the widget interactive:

```text
DISPATCH_STARTED
closest-result event
DISPATCH_ENDED
```

A correct guess produces the success event and completion:

```text
DISPATCH_STARTED
guessed-correctly event
DISPATCH_ENDED
```

### Program 2

The first wrong round, including the `do_not_count` signal, does not force completion.

It produces the expected domain events, advances the widget to phase 2, and returns:

```text
MANUALFILLNEEDEDSTEP
```

The next phase exposes new fill names, such as:

```text
guess_2_1
guess_2_2
```

A correct second-round dispatch produces success and:

```text
ATCOMPLETION
```

Undo and redo each emit separate, properly bounded dispatch event groups and restore the expected states.

### Program 3

The accumulator accepts only its declared fields:

```text
new_1
new_2
new_3
```

Accepted updates mutate its state and emit the expected events.

Rejected updates leave the prior committed state intact and expose another manually fillable step where appropriate.

## 7. Polling through the facade

The facade is the correct integration boundary for external pollers.

The expected usage is conceptually:

```python
cursor = facade.get_live_session_event_cursor(session_id)

facade.dispatch_packet(session_id, packet)

events, next_cursor = facade.get_live_session_events_since(
    session_id,
    cursor,
)
```

The returned suffix contains the events emitted after the supplied cursor.

The tests verify the important practical contract:

```text
capture cursor
→ dispatch one packet
→ poll since cursor
→ receive that packet's complete event group
→ advance to returned cursor
```

Repeating that process gives the poller a non-overlapping sequence of event groups.

```python
cursor = initial_cursor

for packet in packets:
    facade.dispatch_packet(session_id, packet)

    events, cursor = facade.get_live_session_events_since(
        session_id,
        cursor,
    )

    assert events[0].kind == DISPATCH_STARTED
    assert events[-1].kind == DISPATCH_ENDED
```

The poller does not need direct access to widget objects, program internals, lifecycle storage, or dispatch implementation details.

## 8. Event properties that are now confirmed

For the tested dispatch flows:

* Every packet has a start event.
* Every packet has an end event.
* Domain events appear between those boundaries.
* The event ordering matches the dispatch ordering.
* Polling from the previous cursor returns the newly produced suffix.
* The cursor advances after polling.
* Undo and redo are observable like normal dispatches.
* Recoverable domain failures still produce complete event groups.
* Completion and manual-interaction results are observable independently from domain event severity.
* Lifecycle state exposed in history is available to subsequent widgets.
* The facade is sufficient for an external event consumer.

## 9. Concurrency boundary

Because concurrency, ordering, session isolation, and dispatch serialization are handled above the widget layer, widget authors should not implement their own locking or polling protocol.

A widget should behave as though it is processing one accepted packet against one coherent lifecycle state:

```python
def process(packet, state):
    validate_owned_inputs()
    apply_deterministic_transition()
    emit_domain_events()
    return lifecycle_result
```

The higher-level runtime is responsible for:

```text
session routing
packet ordering
atomic state transition boundaries
event sequencing
cursor visibility
concurrent pollers
dispatch serialization or conflict handling
```

This separation is valuable: widget code remains ordinary deterministic domain code.

## 10. The practical authoring recipe

A new ThinkWidget should generally follow this shape:

```python
class ExampleWidget(ThinkWidgetTM):
    def __init__(self, ...):
        super().__init__(...)
        self.phase = 1
        self.done = False
        self.result = None

    def restart(self, history, args):
        self.phase = 1
        self.done = False
        self.result = None

        dependency = history[-1]["value"]["state"]["semantic_field"]
        self.configure_from(dependency, args)

    def expose(self):
        if self.phase == 1:
            return ["field_1", "field_2"]

        return ["field_3"]

    def on_fill(self, fill_data):
        values = self.read_owned_fields(fill_data)

        if self.is_complete(values):
            self.done = True
            self.result = "success"
            self.emit_success(...)
            return ATCOMPLETION

        self.phase += 1
        self.emit_info(...)
        return MANUALFILLNEEDEDSTEP

    def on_signal(self, signal):
        if signal.name == "some_command":
            self.apply_signal_semantics()
```

And its end-to-end test should verify, for every action:

```text
1. dispatch packet
2. assert right-hand-side lifecycle result
3. poll facade from prior cursor
4. assert dispatch start
5. assert exact expected domain events
6. assert dispatch end
7. assert lifecycle/history state
8. advance cursor
```

## Final conclusion

The passing flows demonstrate that ThinkPrograms and ThinkWidgets compose organically through explicit lifecycle history, deterministic fill and signal handling, re-explosion, completion, undo/redo, and facade-visible dispatch event groups.

The central contract is:

```text
one dispatched packet
→ one deterministic state transition
→ one RHS lifecycle result
→ one ordered, bounded, facade-pollable event group
```

That is the model authors, dispatchers, and external pollers can all rely on.