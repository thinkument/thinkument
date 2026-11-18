# Engine App Table Interactive Flow Formalism: Datum Automata, Span Product Vectors, Human Input Loop, and Facade Impact

## 0. Scope

This document formalizes the fixed inner “human input loop” that every interactive App Table program ultimately uses, regardless of whether the caller enters through raw session APIs, controller APIs, role-modulated UI APIs, Flask/Django facades, or an offline scripted runner.

The core claim is:

> A submitted App Table program is a list of step-function invocations, but every interactive program flow eventually reduces to a deterministic runtime artery:
>
> step function emits multiframespec
> multiframespec expands into manual fillspan steps
> each span is a product vector of datum state machines
> the engine stops on a span until its authoritative datums are satisfied
> callers advance the span only by submitting datum-addressed fill data and optional datum-addressed signals
> the current datum outputs determine the next legal input space and the public UI context.

This document is intentionally about the main state-machine grammar and dataflow, not about any particular frontend renderer.

---

# 1. Top-down runtime objects

## 1.1 Program

Let an App Table program be:

[
P = [p_1,\ldots,p_n]
]

where each user-authored program step is a step-function invocation:

[
p_i = (\text{public_step_name}_i,\ \text{step_fn}_i,\ \text{fn_args}_i)
]

The engine lowers this into an internal runtime program:

[
R = [\text{ATSTART},\ \text{STEPFN}_1,\ \text{FORMEXPAND}_1,\ldots,\text{STEPFN}_n,\ \text{FORMEXPAND}_n,\ \text{ATCOMPLETE}]
]

During execution, `FORMEXPAND_i` may insert zero or more `MANUAL` fillspan steps immediately after itself.

So the runtime program is not fixed-length after initialization. It grows when a step function emits a multiframespec and may also grow when a span reexplodes or remains incomplete.

---

## 1.2 Step-function output

A step function may emit a pending multiframespec:

[
M_i
]

A multiframespec contains:

[
M = (\text{app_form_id},\ D,\ F,\ \text{fills})
]

where:

* (D) is the finite set of datum declarations.
* (F) is the finite ordered set of frames.
* Each frame contains ordered spans.
* Each span owns one or more datum ids.
* Each span may declare an authoritative subset.
* If a span does not explicitly declare authoritative datums, all owned datums are authoritative.

The runtime validates and coerces the multiframespec, then plans it into manual fillspan steps.

---

## 1.3 Fillspan step

A manual runtime step is:

[
s = (\text{form_id},\ \text{frame_id},\ \text{span_id},\ B_s,\ A_s)
]

where:

* (B_s) is the static owned datum vector for the span.
* (A_s \subseteq B_s) is the authoritative datum subset.
* If (A_s) is omitted or empty, (A_s = B_s).
* (B_s) determines the full product vector of datum state machines on this span.
* (A_s) determines span completion.

The span is satisfied exactly when every authoritative datum in (A_s) is satisfied.

[
\operatorname{SatSpan}(s,t) \iff \forall d \in A_s,\ \operatorname{SatDatum}(d,s,t)
]

---

# 2. The main compact table

| Aspect                     | Why higher layers need to know                                                                                                                                                              | What must be known                                                                                                                                                              | How it determines top-down behavior                                                                                                                                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Span satisfaction          | Program flow cannot move from a span until the span is complete. Since step functions are sequenced through generated spans, span satisfaction controls the whole app’s perceived progress. | (B_s), (A_s), and each datum’s current satisfaction predicate.                                                                                                                  | The engine advances past a `MANUAL` step only when all authoritative datums are satisfied. Already-satisfied manual steps can be auto-skipped.                                                                                   |
| Span transition inputs     | Every UI, controller, script, or API submit must target the current span. Inputs outside the current span are invalid.                                                                      | Current public pending subset, current datum shells, accepted fill grammar, optional signal target.                                                                             | Callers submit (F_s^{t+1}), a span-level action packet containing datum-addressed fills and optionally one datum-addressed signal. The engine gates the packet before any datum lifecycle runs.                                  |
| Datum satisfaction         | Widget authors must know how a datum declares that it is finished; program authors must know why the app remains stopped.                                                                   | For plain datums: structural satisfaction of required micros. For lifecycle datums: satisfied sink state, with span-local mount rules.                                          | A datum being satisfied removes it from the public pending/editable subset. Authoritative datum satisfaction contributes to span completion.                                                                                     |
| Datum inputs               | Widget authors need to know what their lifecycle function receives, and frontend/controller authors need to know what is legal to send.                                                     | Current effective datum shell, raw candidate fill, canonical partial fill, prefill, structural satisfaction boolean, previous lifecycle state, signal kind/info, event emitter. | The datum lifecycle function branches on this input packet and chooses blocked, reexplode, or done.                                                                                                                              |
| Datum outputs              | Widget authors need a precise output grammar; higher layers need to know how outputs reshape the next input space.                                                                          | Status, replacement datum shell, working fill, prefill, lifecycle state, message, proc notes, events.                                                                           | A reexplode output changes the current effective datum shell and therefore changes the next allowed fill grammar. A done output moves the datum into the satisfied sink. A blocked output leaves the span pending with an error. |
| Datum function body powers | Widgets are not merely validators; they may emit live session events.                                                                                                                       | Event packet shape, event transience, callback/drain behavior.                                                                                                                  | Events are delivered live and drainable but do not mutate durable engine state, outputs, snapshots, lifecycle rows, or runtime write indexes.                                                                                    |
| Span transition outputs    | Every outer app consumes the same renderer-agnostic state of the current stop.                                                                                                              | Universal UI context keys: current frame/span, datum declarations, fills, pending datum ids, cursor, state summary, errors, globals, metadata.                                  | All renderers and facades receive the same normalized current-frame/current-span contract. Higher facades may render or role-modulate it, but the core context is the same.                                                      |

---

# 3. Current-effective datum model

## 3.1 Datum identity

Let a datum id be:

[
d \in D
]

A datum is unique within the emitted form. It may appear on one span or multiple spans. If the same datum id appears on a later span and has `mount_explode=True`, mounting is span-local, so the datum may receive a fresh mount signal for the later span.

---

## 3.2 Static shell and current-effective shell

Let the static datum declaration from the multiframespec be:

[
\delta_d^0
]

A lifecycle datum may later reexplode and replace its own effective shell. Therefore the current-effective datum shell at time (t) is:

[
\delta_d^t = \operatorname{Hydrate}(\delta_d^0,\ L_d^t)
]

where (L_d^t) is the current lifecycle memory row for the datum.

The current-effective shell contains the micros that define the current fill grammar.

---

## 3.3 Datum lifecycle state

For a lifecycle datum, define its runtime state as:

[
X_d^t =
(
\delta_d^t,
w_d^t,
x_d^t,
q_d^t,
m_d^t
)
]

where:

* (\delta_d^t) is the current-effective datum shell.
* (w_d^t) is the current working fill overlay for this span/form/frame.
* (x_d^t) is the widget-authored lifecycle state.
* (q_d^t) is the lifecycle status class: blocked, reexplode, done, or not-yet-done.
* (m_d^t) records span-local mount facts, especially which spans have received mount.

For a plain non-lifecycle datum, the state can be reduced to:

[
X_d^t = (\delta_d^t, v_d^t)
]

where (v_d^t) is its current fill value from prefills, working overlays, or committed fills.

---

# 4. Fill grammar

## 4.1 Macro fill

Every external fill reaches the engine as a mapping:

[
\phi: \text{DatumId} \to \text{MacroFill}
]

A macro fill for datum (d) is a mapping from micro name to submitted value:

[
\phi_d: \text{MicroName} \to \text{JSONValue}
]

Controller-level dotted keys such as:

```python
{
    "person.first": "Ada",
    "person.last": "Lovelace"
}
```

normalize before the engine boundary to:

```python
{
    "person": {
        "first": "Ada",
        "last": "Lovelace"
    }
}
```

The engine proper sees datum ids at the top level.

---

## 4.2 Signal grammar

An action may also carry at most one datum-targeted signal:

[
\sigma =
\begin{cases}
\varnothing \
(\text{datum_id},\ \text{kind},\ \text{info})
\end{cases}
]

Canonical shape:

```python
{
    "datum_id": "D",
    "kind": "refresh",
    "info": {
        "reason": "external-change"
    }
}
```

Rules:

* `datum_id` is required when a signal is present.
* `kind` is required and non-empty.
* `info` is optional and normalizes to `{}`.
* Signal packets must be dead JSON.
* Signal-only packets are legal for lifecycle datums.
* A signal targets exactly one datum.

---

## 4.3 Span action packet

A public span transition input is:

[
a_s^{t+1} = (\phi_s^{t+1},\ \sigma_s^{t+1})
]

where:

* (\phi_s^{t+1}) is a datum-addressed fill mapping.
* (\sigma_s^{t+1}) is absent or targets one datum on the current span.
* The packet must target only datums on the current span.
* Fill values must validate against the current-effective datum shell.
* The caller-facing legal target set is the current pending/editable set exposed in UI context.

---

# 5. Datum input pipeline

For each touched datum (d), the transition algorithm computes:

## 5.1 Existing fill base

[
e_d^t
]

This is derived from the render/cache view and current working overlays.

---

## 5.2 Candidate fill

Given submitted fill (\phi_d^{t+1}), the raw candidate is:

[
c_d^{t+1}
=========

\operatorname{Merge}(e_d^t,\ \phi_d^{t+1})
]

Merge law:

* If the datum was omitted, use existing value.
* If existing and submitted values are both mappings, shallow-merge submitted over existing.
* Otherwise, submitted replaces existing.

This candidate remains raw user data.

---

## 5.3 Partial validation

Partial validation tolerates missing required micros but still validates provided nonblank micros and macro rules:

[
p_{d,\text{raw}}^{t+1}
======================

\operatorname{ValidatePartial}(\delta_d^t,\ c_d^{t+1})
]

The validator enforces:

* micro validators;
* macro validators;
* provided-value semantics;
* dead-JSON compatibility.

It does not by itself own generic micro-type coercion.

---

## 5.4 Accepted-fill coercion

Accepted partial values are then canonicalized through the datum’s micros and the micro-type registry:

[
p_d^{t+1}
=========

\operatorname{CoerceAccepted}(\delta_d^t,\ p_{d,\text{raw}}^{t+1})
]

This is what lifecycle widgets should treat as canonical partial fill.

Thus:

* `raw_fill` is raw merged candidate data.
* `partial_fill` is validator-accepted and micro-type-canonicalized data.

---

## 5.5 Structural satisfaction

The engine computes:

[
\operatorname{StructSat}(\delta_d^t,\ p_d^{t+1})
]

This means the current-effective microshell has been structurally satisfied, especially required micros.

Structural satisfaction is not the same as lifecycle satisfaction. It is an input to the lifecycle function.

---

# 6. Datum lifecycle input packet

For a lifecycle datum, the widget receives a packet conceptually shaped as:

[
I_d^{t+1}
=========

(
\delta_d^t,
c_d^{t+1},
p_d^{t+1},
\operatorname{prefill}_d^t,
\operatorname{StructSat}_d^{t+1},
x_d^t,
\operatorname{signal}_d^{t+1},
\operatorname{emit}
)
]

In implementation terms, this is the `q` packet passed to the datum widget.

Important fields include:

* `q["datum"]`: current-effective datum shell.
* `q["raw_fill"]`: raw merged candidate.
* `q["partial_fill"]`: accepted and canonicalized partial fill.
* `q["prefill"]`: current prefill surface for the datum.
* `q["structurally_satisfied"]`: required-micro structural completeness.
* `q["state"]`: previous current lifecycle state.
* `q["signal"]` / `q["signal_kind"]`: mount, fill, or controller-origin custom signal.
* `q["emit"]`: live session event emitter.

The widget is therefore not merely a validator. It is a small current-effective state machine.

---

# 7. Datum lifecycle output grammar

A lifecycle widget returns exactly one semantic next-state class.

Let:

[
O_d^{t+1} \in \mathcal{O}_D
]

where (\mathcal{O}_D) is the datum lifecycle output grammar.

The key status values are:

[
\text{status} \in {\text{blocked},\ \text{reexplode},\ \text{done}}
]

## 7.1 Blocked

```python
{
    "status": "blocked",
    "state": {...},
    "message": {
        "level": "error",
        "text": "..."
    }
}
```

Meaning:

* The datum remains unsatisfied.
* No durable fill is committed for this datum.
* The current span remains active.
* `last_error[datum_id]` is populated.
* The same public stop is returned.

Use blocked when the submitted fill is understandable but not yet acceptable.

---

## 7.2 Reexplode

```python
{
    "status": "reexplode",
    "datum": {...replacement current-effective shell...},
    "fill": {...working fill...},
    "prefill": {...optional prefill...},
    "state": {...next lifecycle state...},
    "message": {
        "level": "info",
        "text": "..."
    },
    "proc_notes": {...},
    "events": [...]
}
```

Meaning:

* The datum replaces its current-effective shell.
* The replacement shell becomes the next rendered datum declaration.
* The next legal fill space changes because the micros changed.
* Working fill may be preserved for this datum and siblings.
* The same manual span is reinserted after the current runtime step.
* The span remains pending unless later satisfied.

Reexplode is how widgets dynamically reshape their own future input grammar.

---

## 7.3 Done

```python
{
    "status": "done",
    "state": {...next lifecycle state...},
    "message": {
        "level": "success",
        "text": "..."
    },
    "events": [...]
}
```

Meaning:

* The datum transitions into the satisfied sink state.
* Unless forced done, final commit validation requires all required micros and semantic validators to pass.
* The canonical fill is durably committed into form fills.
* The datum no longer appears in the public pending/editable set for this span.

---

## 7.4 Event declarations and inline emission

A widget may emit live session events either inline through `q["emit"]` or through returned event declarations.

Canonical event packet:

```python
{
    "kind": "datum_lifecycle_event_v1",
    "event_id": "...",
    "emitted_at": "...",
    "source": "datum_widget | datum_widget_result | external",
    "name": "...",
    "channel": "...",
    "audience": "...",
    "form_id": "...",
    "frame_id": "...",
    "span_id": "...",
    "datum_id": "...",
    "signal_kind": "...",
    "payload": {...}
}
```

Event law:

* Events are dead JSON.
* Events are transient.
* Events are drainable.
* Events may be callback-delivered.
* Events are session-local.
* Events are not written to durable engine state.
* Events are not written to snapshots.
* Events are not written to outputs.
* Events are not written to datum lifecycle rows.
* Events are not written to runtime write indexes.

---

# 8. Datum satisfaction

## 8.1 Plain datum satisfaction

For a non-lifecycle datum:

[
\operatorname{SatDatum}(d,s,t)
\iff
\operatorname{StructSat}(\delta_d^t,\ v_d^t)
]

That is, the current-effective microshell is satisfied by the current fill value.

---

## 8.2 Lifecycle datum satisfaction

For a lifecycle datum:

[
\operatorname{SatDatum}(d,s,t)
\iff
\neg \operatorname{NeedsMount}(d,s,t)
\land
\operatorname{InSatisfiedSink}(d,t)
]

Important ordering:

1. If the datum wants mount and has not mounted on this span, it is not satisfied.
2. Otherwise, if it is in the satisfied sink state, it is satisfied.
3. Otherwise, it is not satisfied.

This ordering is what makes same-datum reuse on later spans work. Even if the datum was done earlier, a fresh span-local mount can make it pending again.

---

## 8.3 Monotonicity

Within a forward execution branch, excluding undo/redo rollback, datum satisfaction is monotonic in the following practical sense:

* Once a datum is in the satisfied sink for the current span and does not require a fresh mount, it remains satisfied.
* The engine does not ask callers to refill already satisfied authoritative datums for the same active span.
* Span progression only moves forward when authoritative satisfaction holds.
* Undo may deliberately revert state.
* Reusing the same datum id on a later span with span-local mount may create a new mount obligation, so the monotonicity claim is span-local, not globally absolute over all future spans.

---

# 9. Span state machine

## 9.1 Span as product vector

A span is a product vector:

[
S_s^t = (X_{d_1}^t,\ldots,X_{d_k}^t)
]

where:

[
B_s = [d_1,\ldots,d_k]
]

The authoritative subvector is:

[
A_s \subseteq B_s
]

The span’s current public pending set is:

[
P_s^t
=====

{d \in B_s \mid \neg \operatorname{SatDatum}(d,s,t)}
]

The UI context exposes this dynamic pending/editable set as:

```python
ctx["datum_widgets_on_this_span"]
```

The static span ownership vector remains available through the frame/span declaration surfaces.

---

## 9.2 Span satisfaction

[
\operatorname{SatSpan}(s,t)
\iff
\forall d \in A_s,\ \operatorname{SatDatum}(d,s,t)
]

If the span owns no datums, it is vacuously satisfied.

---

## 9.3 Span transition input space

The caller-facing legal next input space is:

[
\mathcal{F}_s^{t+1}
===================

\prod_{d \in P_s^t} \mathcal{F}_d^{t+1 \mid O_d^t}
]

plus at most one signal targeting a datum in the current pending span surface.

For each datum:

[
\mathcal{F}_d^{t+1 \mid O_d^t}
]

is determined by the current-effective datum shell (\delta_d^t), which itself was determined by the previous lifecycle output (O_d^t).

Thus the essential conditional chain is:

[
O_d^t
\Rightarrow
\delta_d^t
\Rightarrow
\mathcal{F}_d^{t+1}
\Rightarrow
I_d^{t+1}
\Rightarrow
O_d^{t+1}
]

Zoomed out to the whole span:

[
(O_{d_1}^t,\ldots,O_{d_k}^t)
\Rightarrow
(\mathcal{F}*{d_1}^{t+1},\ldots,\mathcal{F}*{d_k}^{t+1})
\Rightarrow
\mathcal{F}_s^{t+1}
\Rightarrow
S_s^{t+1}
]

This is the living grammar of the human input loop.

---

## 9.4 Span transition algorithm

Given a span action:

[
a_s^{t+1} = (\phi_s^{t+1},\sigma_s^{t+1})
]

the engine performs:

1. Hydrate the current span and current-effective multiframespec.
2. Deliver mount explosions for datums that need span-local mount.
3. Compile manual IO cache and validators from current-effective datum shells.
4. Logistically gate the packet:

   * fill must be a mapping;
   * payload must be dead JSON;
   * payload must respect size limits;
   * datum ids must be on the current span;
   * signal target must be on the current span;
   * signal target must be pending/dirty for this tick.
5. Compute touched datum ids.
6. For each touched datum:

   * compute candidate fill;
   * partially validate;
   * canonicalize accepted values;
   * compute structural satisfaction;
   * run plain or lifecycle path.
7. If any datum blocks, reject the transition and return the same span with errors.
8. If any lifecycle datum reexplodes:

   * commit replacement current-effective shells;
   * preserve working fills;
   * clear stale manual IO cache;
   * record lifecycle write;
   * reinsert the same manual span.
9. If no datum reexplodes:

   * commit done lifecycle state;
   * commit validated fills;
   * test span satisfaction;
   * if incomplete, reinsert the same manual span;
   * if complete, advance the runtime cursor.

---

## 9.5 Reexplode branch and sibling fills

If a product-vector span owns:

[
S = A \times Q \times B
]

and the same submit touches all three datums, but lifecycle datum (Q) reexplodes, then the engine does not yet treat the whole span as durably complete.

Instead:

* (Q)’s replacement shell becomes current-effective.
* Accepted sibling fills for (A) and (B) may be preserved as working fills.
* Durable final `form_fills` are committed when the span completes.
* The same span remains active, now with (Q)’s new shell.

This avoids committing a partial product vector as final while one authoritative member still needs more interaction.

---

# 10. Universal UI context output

When the engine is on a manual span, `get_context()` produces a renderer-agnostic universal UI context.

Conceptually:

[
U_s^t = \operatorname{RenderCtx}(S_s^t)
]

Important keys include:

```python
{
    "frames": [...],
    "current_span": "...",
    "span_order": [...],
    "span_to_datum_widgets": {...},
    "datum_widget_decls": {...},
    "datum_widget_fills": {...},
    "datum_widgets_on_this_span": [...],
    "session_metadata": {...},
    "last_error": {...} | None,
    "cursor": {...},
    "kind": "MANUALFILLNEEDEDSTEP",
    "session_id": "...",
    "form_id": "...",
    "app_form_id": "...",
    "current_frame_id": "...",
    "current_frame_name": "...",
    "current_span_id": "...",
    "globals": {...},
    "step": {...},
    "state": {...},
    "multiframespec": {...},
    "tags": [...]
}
```

Core law:

> The public interactive context is current-frame/current-span scoped. It must not expose future frames, future spans, or future datum surfaces as active editable surfaces.

`datum_widget_fills` is the authoritative merged value surface.

`datum_widgets_on_this_span` is the dynamic pending/editable subset.

---

# 11. Main engine loop

## 11.1 Raw engine cursor law

The engine cursor points to the current runtime step.

If the current step is non-manual, `step()` executes it and continues.

If the current step is manual, `step(fill, signal)` attempts a span transition.

Pseudo-code:

```python
def engine_step(fill=None, signal=None):
    cur = program[cursor]

    if cur.kind == ATCOMPLETE:
        raise ProgramEndReachedError

    if cur.kind == MANUAL:
        ok = transition_fillspan_on_incoming_filldata(
            cur,
            fill=fill,
            signal=signal,
        )

        if not ok:
            return get_context()

        cursor += 1
        advance_over_satisfied_manual_steps()
        maybe_execute_next_nonmanual_step()
        return get_context()

    cursor += 1
    execute_nonmanual_step_if_needed()
    advance_over_satisfied_manual_steps()
    return get_context()
```

---

## 11.2 Step function execution

When the engine reaches a `STEPFN` step:

1. It calls the registered step function.
2. It passes state and function args.
3. If the function accepts the reserved runtime context kwarg, a slim or full context may be injected.
4. It routes the return value.
5. If a multiframespec is emitted, it becomes the pending form.

---

## 11.3 Form expansion

When the engine reaches a `FORMEXPAND` step:

1. It reads the pending multiframespec.
2. It validates the multiframespec.
3. It plans fillspan steps from frames/spans/datums.
4. It inserts those manual steps into the runtime program.

Thus a single user-authored step function may expand into many manual stops.

---

## 11.4 Manual auto-skip

After each successful step, the engine may skip manual steps that are already satisfied.

This matters for prefills, previously committed fills, and lifecycle sink states.

The skip law is:

```python
while current step is MANUAL and span is satisfied:
    mark no-op exec record
    cursor += 1
```

---

# 12. Controller loop

The page-flow controller is the high-level interactive loop above the raw session API.

It accepts:

```python
dispatch_page_flow_controller_automaton(
    session_id,
    action=STEP | UNDO | REDO,
    user_fill={...},
    user_signal={...},
    session_ops=...
)
```

It returns a packet:

```python
{
    "session_id": "...",
    "ui_mode": "FORM_FILL | RUN_COMPLETED_SUMMARY",
    "ui_config": {...},
    "ctx": {...},
    "event_kind": "...",
    "finished": bool,
    "last_error": {...} | None
}
```

The controller routes by event kind.

Important event kinds:

```python
ATSTART
STEPFNSTEP
FORMEXPANSIONSTEP
MANUALFILLNEEDEDSTEP
ATCOMPLETION
```

Important UI modes:

```python
FORM_FILL
RUN_COMPLETED_SUMMARY
```

Default route for `STEP`:

```python
ATSTART              -> KEEP_STEPPING
STEPFNSTEP           -> KEEP_STEPPING
FORMEXPANSIONSTEP    -> KEEP_STEPPING
MANUALFILLNEEDEDSTEP -> FORM_FILL
ATCOMPLETION         -> RUN_COMPLETED_SUMMARY
```

So from above, the interactive user does not normally see every internal engine step. The controller keeps stepping until it reaches a durable UI stop.

---

# 13. Role-aware façade

The role-aware interactive façade does not make the engine role-aware.

Instead:

1. The base session API remains roleless.
2. The interactive façade captures the viewer role.
3. It builds a role-bound liaison with roleless-looking methods.
4. The page-flow controller calls that liaison.
5. The liaison:

   * performs write-side role preflight before `STEP`;
   * calls the roleless base session API;
   * applies read-side role modulation to returned ctx.

Thus role awareness lives at the interactive boundary, not inside the datum/span state machines.

The core span/datum formalism remains unchanged.

---

# 14. Offline/scripted runner

The offline runner uses the same engine and span transition machinery.

Difference:

* Interactive runs wait for live caller actions.
* Offline runs consume a premade script of fill/signal actions.
* The script runner auto-advances through internal steps and stops according to durable stop kinds.
* It has safeguards against no progress and budget exhaustion.

The formal action packet and datum/span state machines are the same.

---

# 15. Developer-facing consequences

## 15.1 For datum widget authors

A datum widget author is designing a state machine:

[
I_d^t \to O_d^t
]

The widget must be explicit about:

1. What current shell it expects.
2. What partial fill it consumes.
3. What signal kinds it handles.
4. When it blocks.
5. When it reexplodes.
6. When it is done.
7. What state it carries forward.
8. What events it emits.
9. What replacement shell it returns.
10. What working fill and prefill it wants preserved.

The key design law:

> A widget should carry forward only the compact current-effective state it needs for the next transition.

Current-only lifecycle storage does not retain an implicit history. If the widget wants history, it must intentionally encode that history in its current state. That is allowed, but it creates state growth.

Good pattern:

```python
state = {
    "phase": phase + 1,
    "summary": {
        "last_value": value,
        "count": count + 1
    }
}
```

Bad pattern:

```python
state = {
    "all_previous_large_payloads": [
        ...old_payloads,
        new_very_large_payload
    ]
}
```

---

## 15.2 How to choose datum outputs

At each explosion, the widget should choose the smallest output that correctly describes the next machine state.

### Choose `blocked` when

* The current input is invalid for semantic reasons.
* The shell should not change.
* The caller should stay on the same surface.
* The user needs an error message.

### Choose `reexplode` when

* The next required input surface differs from the current shell.
* The widget needs to ask for different micros.
* The widget wants to introduce, remove, or modify micros.
* The widget wants to preserve working fill while changing the shell.

### Choose `done` when

* The datum is semantically complete.
* The current fill should be committed.
* The datum should no longer block authoritative span completion.

---

## 15.3 How output determines next fill space

If a widget returns:

```python
{
    "status": "reexplode",
    "datum": {
        "id": "Q",
        "micros": [
            {"name": "confirm", "type": "text", "required": True}
        ]
    },
    "fill": {"confirm": ""}
}
```

then the next public legal fill space for `Q` is no longer the old microshell. It is now:

[
\mathcal{F}_Q^{t+1}
===================

{\text{macro fills satisfying the `confirm` microshell}}
]

So the output grammar controls the next input grammar.

This is the central datum automaton law:

[
O_D^t \Rightarrow \mathcal{F}_D^{t+1}
]

---

## 15.4 For app-table program authors

A program author writes:

```python
[
    {"public_step_name": "step_1", "step_fn": "...", "fn_args": {...}},
    {"public_step_name": "step_2", "step_fn": "...", "fn_args": {...}},
]
```

But at runtime, each step function may emit a multiframespec that expands into many frames and spans.

The author’s perceived flow is:

```text
step function
  -> frame
    -> span
      -> human input loop
    -> next span
  -> next frame
-> next step function
```

The author must understand:

* The app does not move from one span to the next until the current span is satisfied.
* The app does not move from one step function to the next until all manual spans generated by the current step function are satisfied.
* Authoritative datums determine completion.
* Non-authoritative datums can exist in the product vector but do not block span completion.
* Lifecycle datums may reexplode and reshape the current stop.
* The UI context is always a projection of the current span state.

---

# 16. The human input loop, fully formalized

At public time (t), suppose the session is stopped at manual span (s).

The engine exposes:

[
U_s^t
]

which contains:

* current frame id;
* current span id;
* current datum declarations;
* current merged fills;
* current pending datum ids;
* last errors;
* cursor and metadata.

From that context, the caller can infer:

[
\mathcal{F}_s^{t+1}
]

the allowed span-level fill/signal space.

The caller submits:

[
a_s^{t+1} = (\phi_s^{t+1},\sigma_s^{t+1})
\in
\mathcal{F}_s^{t+1}
]

The engine computes dirty/touched datums:

[
T_s^{t+1}
\subseteq
B_s
]

For each touched datum:

[
I_d^{t+1}
=========

\operatorname{BuildDatumInput}(
X_d^t,
\phi_d^{t+1},
\sigma_d^{t+1}
)
]

Then:

[
O_d^{t+1}
=========

\operatorname{ExplodeDatum}(I_d^{t+1})
]

The datum output updates:

[
X_d^t \to X_d^{t+1}
]

The span product vector updates:

[
S_s^t \to S_s^{t+1}
]

Then the engine tests:

[
\operatorname{SatSpan}(s,t+1)
]

If false:

[
\text{return } U_s^{t+1}
]

If true:

[
\text{advance to next span/frame/step and return next durable UI context}
]

This is the whole human input loop.

---

# 17. Main pseudo-code: datum transition

```python
def transition_one_datum(datum_id, datum, existing, submitted, signal):
    candidate = merge(existing[datum_id], submitted.get(datum_id))

    partial_raw = validator(datum).parse_and_validate_fill(
        raw=candidate,
        enforce_required_micros=False,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )

    partial = coerce_accepted_macro_fill_for_datum(
        datum=datum,
        accepted=partial_raw,
    )

    partial = validator(datum).parse_and_validate_fill(
        raw=partial,
        enforce_required_micros=False,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )

    structurally_satisfied = datum_fill_data_meets_its_structural_micros_shell(
        datum,
        partial,
    )

    if not has_lifecycle(datum):
        if not structurally_satisfied:
            return Error("required fields missing")

        committed = final_commit_validate(datum, partial)
        return PlainCommitted(committed)

    event = explode_datum_widget(
        datum=datum,
        raw_fill=candidate,
        partial_fill=partial,
        structurally_satisfied=structurally_satisfied,
        signal=signal or {"kind": "fill", "info": {}},
    )

    if event.status == "blocked":
        return Blocked(event.message)

    if event.status == "reexplode":
        return Reexploded(
            replacement_datum=event.datum,
            working_fill=event.working_fill or partial,
            state=event.state,
        )

    if event.status == "done":
        if event.forced_done:
            committed = partial
        else:
            committed = final_commit_validate(datum, partial)

        return Done(committed=committed, state=event.state)

    return Error("unknown lifecycle status")
```

---

# 18. Main pseudo-code: span transition

```python
def transition_span(span, fill, signal):
    hydrated = hydrate_current_effective_multiframespec(span)

    mount_record = mount_datums_needing_mounting_on_the_span(span)

    cache = compile_manual_io_cache(hydrated)
    datums_by_id = cache.datums_by_id
    existing = cache.current_fills + latest_working_overlays

    touched = dirty_subset(span.owns, fill, signal)

    if not logistical_gate(fill, signal, span.owns, touched):
        return SameSpanWithError

    committed = {}
    working_fills = {}
    reexploded = []
    errors = {}

    for datum_id in touched:
        result = transition_one_datum(
            datum_id,
            datums_by_id[datum_id],
            existing,
            fill,
            signal if signal.targets(datum_id) else None,
        )

        match result:
            case Error:
                errors[datum_id] = result.message

            case PlainCommitted:
                committed[datum_id] = result.fill
                working_fills[datum_id] = result.fill

            case Blocked:
                errors[datum_id] = result.message

            case Reexploded:
                reexploded.append(result)
                working_fills[datum_id] = result.working_fill

            case Done:
                committed[datum_id] = result.committed
                working_fills[datum_id] = result.committed

    if errors:
        last_error = errors
        return SameSpanWithError

    if reexploded:
        apply_reexplode_batch(reexploded, working_fills)
        reinsert_same_manual_span()
        return SameSpanAdvancedInternally

    span_complete = span_satisfied_after_attempt(
        authoritative=span.authoritative,
        datums=datums_by_id,
        fills=existing + committed,
    )

    if span_complete:
        force_commit_coherent_plain_completion_fills()
        persist_committed_fills()
        return AdvancePastSpan

    persist_committed_fills()
    reinsert_same_manual_span()
    return SameSpanPartialProgress
```

---

# 19. Main pseudo-code: controller dispatch

```python
def dispatch_ui_action(action, user_fill, user_signal):
    if action != STEP:
        ignore_fill_and_signal_as_needed()

    user_fill = normalize_repeated_values(user_fill)
    user_fill = collapse_dotted_micro_keys(user_fill)

    packet = normalize_controller_action_packet(
        fill=user_fill,
        signal=user_signal,
    )

    next_action = action

    while True:
        if next_action == STEP:
            ctx = session_ops.step_session(
                session_id,
                fill=packet.fill,
                signal=packet.signal,
            )

        elif next_action == UNDO:
            ctx = session_ops.undo_last_step(session_id)

        elif next_action == REDO:
            ctx = session_ops.redo_last_step(session_id)

        elif next_action == KEEP_STEPPING:
            ctx = session_ops.step_session(
                session_id,
                fill=None,
                signal=None,
            )

        elif next_action == KEEP_UNDOING:
            ctx = session_ops.undo_last_step(session_id)

        routed = routing_map[entry_action][event_kind(ctx)]

        if routed is UIMode:
            return {
                "ui_mode": routed,
                "ctx": ctx,
                "event_kind": ctx["kind"],
                "finished": ctx["kind"] == "ATCOMPLETION",
            }

        next_action = routed
        packet.fill = {}
        packet.signal = None
```

---

# 20. Practical design rules

## 20.1 Widget design rules

1. Treat `q["partial_fill"]` as canonical accepted data.
2. Treat `q["raw_fill"]` as raw candidate data.
3. Use `q["structurally_satisfied"]` to decide whether required micros are complete.
4. Return `blocked` for same-shell errors.
5. Return `reexplode` to change the next input shell.
6. Return `done` only when the datum should stop blocking span completion.
7. Carry compact Markovian state forward.
8. Use events for live observations, not durable state.
9. Do not rely on event packets being in snapshots or outputs.
10. Make signal handling explicit.

---

## 20.2 Program author rules

1. A step function is not the unit of human interaction; a span is.
2. A multiframespec can generate multiple manual stops.
3. A span is a product vector of datums.
4. Authoritative datums block span completion.
5. Non-authoritative datums may be rendered or preserved but do not block completion.
6. Same datum id on later span can remount if lifecycle opts into mount.
7. Reexplosion means the same span remains active with a new datum shell.
8. The UI context tells the caller what is currently editable.
9. The submit packet should only target datums exposed as pending/editable.
10. Final program outputs come from committed fills, not transient working fills.

---

## 20.3 Facade author rules

1. Do not invent a separate input grammar above the controller.
2. Normalize to the controller action packet.
3. Preserve datum-addressed fill shape.
4. Collapse dotted micro keys before the engine boundary.
5. Pass at most one datum-targeted signal.
6. Treat the universal UI context as the renderer-agnostic source of truth.
7. Renderers may transform (U) into custom JSON or HTML, but should not change the underlying transition grammar.
8. Role modulation belongs above the roleless engine.
9. Persistence should snapshot engine state, not live event queues.
10. Offline scripts should use the same fill/signal packet grammar as live runs.

---

# 21. The core theorem

The whole platform’s interactive behavior can be summarized by this conditional chain:

[
P
\Rightarrow
M_i
\Rightarrow
[s_1,\ldots,s_m]
\Rightarrow
S_s^t=(X_{d_1}^t,\ldots,X_{d_k}^t)
\Rightarrow
U_s^t
\Rightarrow
\mathcal{F}*s^{t+1}
\Rightarrow
a_s^{t+1}
\Rightarrow
(I*{d_j}^{t+1})*{d_j \in T}
\Rightarrow
(O*{d_j}^{t+1})_{d_j \in T}
\Rightarrow
S_s^{t+1}
\Rightarrow
\operatorname{SatSpan}(s,t+1)
]

Where:

* (P) is the submitted App Table program.
* (M_i) is a step-function-emitted multiframespec.
* (s_j) are planned manual fillspan steps.
* (S_s^t) is the span product vector.
* (U_s^t) is the universal UI context.
* (\mathcal{F}_s^{t+1}) is the next legal fill/signal action space.
* (a_s^{t+1}) is the submitted action packet.
* (I_d^{t+1}) is the datum lifecycle input packet.
* (O_d^{t+1}) is the datum lifecycle output.
* (\operatorname{SatSpan}) determines whether the app advances.

This is the fixed main artery that every higher run surface ultimately touches.

---

# 22. Short final mental model

A program author writes step functions.

A step function emits a multiframespec.

A multiframespec becomes frames and spans.

A span is a product vector of datum automata.

A datum automaton exposes a current microshell.

That microshell determines the next legal fill space.

A fill/signal packet targets datums on the current span.

Each touched datum receives raw fill, canonical partial fill, structural satisfaction, previous lifecycle state, and signal.

Each lifecycle datum returns blocked, reexplode, or done.

Reexplode changes the next microshell.

Done satisfies the datum.

The span advances when all authoritative datums are satisfied.

Everything above the engine—controller, role façade, renderer, Flask, Django, offline runner—is just a different way of feeding this same span action grammar and consuming the same universal context output.
