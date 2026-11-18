# P12 — What we learned about funked puzzle flows

Program 12 proves one app-level formalism across increasingly composed flows.

```text
current controller-end U
    -> inspect current writable pending datums
    -> select the earliest configured pending role
    -> build one role-projected FunkTMRequest
    -> return one scoped FunkTMResult
    -> dispatch the generated STEP
    -> hear the resulting controller trident
    -> repeat or stop
```

The dry-run architecture now adds one more important separation:

```text
P12 program/filler semantics
    are strategy-agnostic

how the outer and generated actions actually reach a running session
    belongs to BaseDryRunStrategy
```

The current backend-only proof uses `base-facade-strategy`, but the P12 case
catalog does not import or know `run_from_here`.

## 1. Start-to-finish generated execution

A one-widget program can mount, expose its active answer grammar, receive one
generated fill, and complete in the same outer chain call.

The filler does not know the private widget object. It receives only the current
role-projected shell and writable pending datum row.

The generic funked runner likewise does not know the filler implementation. It
asks the selected strategy to perform one chain-reaction dispatch and checks the
standard returned observations.

## 2. Semantic convergence on one widget

The solver can deliberately submit a platform-invalid answer first.

```text
attempt 1
    wrong answer
    -> controller end with U.last_error
    -> unchanged manual frontier

attempt 2
    request.last_error is present
    request.semantic_errors_in_row == 1
    -> correct answer
    -> completion
```

Retry policy remains owned by chainreactionTM. Validator semantics remain owned
by the current widget shell. The dry-run case stores only expectation needles
for the filler receipts and generated controller ends.

## 3. Generation and many role-specific answer widgets

The generator role writes a puzzle and answer key. Later answer widgets consume
that lifecycle state through ordinary ThinkProgram history wires.

Each solver role receives only its current writable datum and can independently
converge from a wrong answer to the right answer.

```text
generator
    -> solver_a wrong
    -> solver_a right
    -> solver_b wrong
    -> solver_b right
    -> completion
```

No filler bypasses the role-aware dispatch membrane.

## 4. Funked and non-funked collaboration

A non-funked role is an intentional barrier, not a failure.

```text
outer call 1
    generator runs
    human_reviewer becomes pending
    chain stops: next_pending_role_unchainreactioned

outer call 2
    human reviewer submits approval
    solver resumes automatically
    program completes
```

This remains the scalable collaboration model:

```text
machine continuation
    -> explicit human decision
    -> machine continuation
```

The outer calls are ordinary standard A packets. The chosen strategy decides
how those A packets are actually delivered.

## 5. Multiple human barriers and generated segments

The same law composes repeatedly without introducing a workflow-specific
runtime:

```text
outer call 1
    generator
    -> stop at human_reviewer_a

outer call 2
    human_reviewer_a approval
    -> solver_a wrong
    -> solver_a right
    -> stop at human_reviewer_b

outer call 3
    human_reviewer_b approval
    -> solver_b wrong
    -> solver_b right
    -> completion
```

Each generated controller-end receipt predicts only the immediate next
dispatch from that exact end-event U.

The generic funked runner proves for every generated end:

```text
next_U_funkability.evaluated_from
    == "controller.loop.end.payload.U"

next_U_funkability.U_kind
    == controller_end.payload.U.kind

next_U_funkability.span_id
    == controller_end.payload.U current span
```

## 6. Final ownership boundary

Program 12 now keeps five concerns separate.

```text
program12 flow sheet
    widgets, order, roles, wires, scenario metadata

funked_fill_widgets
    puzzle lifecycle and shell validators

funked_fillers
    generated behavior and retry policy

dry_run_cases_funked.py
    app-specific standard A and E/receipt needles

funked_live_session_dry_run_v1.py
    generic strategy-agnostic chain proof machinery
```

The selected strategy owns only the concrete run/read/write membrane.

For today's backend-only run:

```text
BaseFacadeBackendOnlyDryRunStrategy
    -> dispatch_live_session_action_with_chain_reaction
```

A future Flask, Django, or DOM strategy can supply another implementation while
reusing the same P12 program and case catalog.

## Final law

```text
one current shell grammar
    + one selected writable role
    + one bounded request
    + one scoped generated result
    + standard strategy-mediated dispatch
    = scalable generated participation in a normal ThinkProgram
```

And at the dry-run architecture level:

```text
same P12 P / SM / A / E catalog
    + another BaseDryRunStrategy
    = same proof through another execution layer
```
