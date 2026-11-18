"""
P10 — What we learned: dispatch start/end snapshots and projection asymmetry
=============================================================================

The controller envelope has two independently meaningful state boundaries:

    controller.loop.start
        payload.U describes the state immediately before admitted execution.

    controller.loop.end
        payload.U describes the state after admitted execution finishes,
        semantically rejects, or systematically fails.

The two packets are not decorative brackets around one shared state object.

Formal law
----------

For one canonical action interval and one viewing role r:

    Estart.payload.U = project(pre_state, r)
    Eend.payload.U   = project(post_state, r)

Projection is evaluated independently for the two boundary states.

This gives the downstream application both sides of the transition:

    source state
        from controller start

    destination or recovered state
        from controller end

The controller boundary and the informative middle answer different questions.

    controller boundaries
        What state existed before and after this admitted action?

    datum lifecycle events
        What widget-level messages and custom events occurred while processing
        the action?

Neither can be reconstructed completely from the other.

Relationship to P8 and P9
-------------------------

P8 answers:

    Was the request admitted?

    Was a failure eventless or inside controller execution?

    Once start exists, is there one matching end?

    Did admitted work end successfully, semantically, or systematically?

P9 answers:

    Which datum lifecycle events were emitted inside the controller envelope?

    Which of those events are visible to each role?

P10 answers:

    What does start.payload.U describe?

    What does end.payload.U describe?

    Did the action stay on one authored span, move to another, or complete?

    How is each boundary independently projected for one viewing role?

Keeping the three lessons separate prevents one large taxonomy from conflating:

    admission
    controller outcome
    lifecycle movement
    middle-event emission
    role projection

Complete attempt taxonomy
-------------------------

Every attempted action belongs to one of these families:

    preflight exception
        Observable event suffix:
            none

        Caller result:
            Python exception

    preflight rejection
        Observable event suffix:
            none

        Caller result:
            structured rejection packet

    admitted success
        Observable event suffix:
            controller start
            zero or more datum events
            controller end

        End result:
            payload.outcome == "success"
            no submitted-target semantic error

    admitted semantic rejection
        Observable event suffix:
            controller start
            zero or more datum events
            controller end

        End result:
            payload.outcome == "success"
            payload.result.last_error is populated

    admitted systematic failure
        Observable event suffix:
            controller start
            zero or more already-emitted datum events
            controller end

        End result:
            payload.outcome == "system_error"

The fundamental ordinary in-process invariant is:

    every successfully recorded controller start is paired with exactly one
    matching controller end attempt

Therefore an ordinary eventless failure belongs to preflight.

Lifecycle-boundary taxonomy
---------------------------

Let:

    N
        no active authored span is exposed

    S
        one active authored span is exposed

The complete lifecycle relation set is:

    N -> S
        Initial entry.

        Start:
            kind == "ATSTART"
            datum_widgets_on_this_span absent

        End:
            first mounted active span

    S -> S
        Same-scope interaction.

        Examples:
            board update
            wrong guess
            signal-driven reexplosion
            semantic retry that remains on the span

        Start and end refer to the same canonical active span, although datum
        shells, fills, messages, errors, or status may differ.

    S1 -> S2
        Authored-scope transition.

        The action satisfies the old authoritative datums and the controller
        continues until the next manual stop is mounted.

        Start:
            old active span

        End:
            new active span

    S -> N
        Terminal transition.

        Start:
            final active span

        End:
            kind == "ATCOMPLETION"
            datum_widgets_on_this_span absent

Systematic failure is not a fifth lifecycle class.

It overlays one of these relations according to the recovered state. For
example, a caught exception before scope progress commits normally appears as:

    S -> S

with:

    Eend.payload.outcome == "system_error"

Boundary-local role projection
------------------------------

Thinkument executes one canonical roleless state machine and stores one
canonical event queue.

Named roles affect release, not canonical execution.

For each controller boundary:

    canonical U at that event
        -> role_modulation.modulate(U, role=r)
        -> projected event payload.U

The start packet and end packet carry different canonical source states, so
their projections must be computed separately.

This matters in four especially visible cases.

Initial mount
~~~~~~~~~~~~~

    start:
        ATSTART
        no active span

    end:
        first active span

Copying one active list to both packets would fabricate an active span at
ATSTART.

Cross-span transition
~~~~~~~~~~~~~~~~~~~~~

    start:
        old span

    end:
        new span

A role may read the old span and not the new one, or vice versa.

Terminal transition
~~~~~~~~~~~~~~~~~~~

    start:
        final active span

    end:
        ATCOMPLETION
        no active span

Copying the start membership onto the end would fabricate editable fields after
completion.

Systematic recovery
~~~~~~~~~~~~~~~~~~~

    start:
        pre-execution state

    end:
        safest recovered state

The recovery state may equal the start state, but that equality is an observed
runtime result, not a helper assumption.

Absence is not emptiness
------------------------

These two public observations have different meanings.

Field absent:

    "datum_widgets_on_this_span" not in U

This means the lifecycle state does not expose an active authored span. The
important examples are:

    ATSTART
    ATCOMPLETION

Field present with an empty list:

    U["datum_widgets_on_this_span"] == []

This means a canonical active span exists, but role projection removed every
guarded active datum from editable membership for this viewer.

P10 proves both.

For maker at the reviewer-owned guess span:

    U.kind == "MANUALFILLNEEDEDSTEP"
    U["datum_widgets_on_this_span"] == []
    mismatch_datum_ids == ["guess"]

The active span exists; maker simply cannot read its datum.

For maker at completion:

    U.kind == "ATCOMPLETION"
    "datum_widgets_on_this_span" not in U

There is no active span to project.

The dry-run needle grammar therefore treats:

    active=[]

as an exact equality assertion and:

    active=None

as an exact field-absence assertion.

Controller event spine and action-envelope projection
-----------------------------------------------------

Role projection must preserve the canonical temporal spine.

For every visible projected controller packet:

    event_id
        equals the canonical event_id

    event_seq
        equals the canonical event_seq

    phase
        equals the canonical phase

    action
        equals the canonical action

    emitted_at
        equals the canonical emitted_at

    payload.timestamp
        equals the canonical payload.timestamp

    payload.outcome/result/system_error
        equal the canonical controller outcome data

Three vectors are projected independently:

    payload.U
        boundary-local datum-bearing UI context

    payload.A
        canonical normalized action packet, filtered by target datum readability

    datum lifecycle packet E
        whole-packet release filter by source datum readability

Both controller phases carry the same canonical A before release projection.
The compatibility fields obey:

    payload.fill == payload.A.fill
    payload.signal == payload.A.signal

when projected A is present.

For each target datum d in A:

    readable(r, d)
        -> retain that datum's fill and/or signal component

    not readable(r, d)
        -> omit that datum's fill and/or signal component

The actor/correlation envelope is conditional:

    no target datums in canonical A
        -> retain dispatch_id, dispatcher_identity_id, dispatcher_role

    at least one target survives projected A
        -> retain dispatch_id, dispatcher_identity_id, dispatcher_role

    canonical A has targets and none survive
        -> payload.A = null
        -> payload.fill = null
        -> payload.signal = null
        -> dispatch_id = null
        -> dispatcher_identity_id = null
        -> dispatcher_role = null

This prevents the controller envelope from leaking activity on fully hidden
datums while preserving event_id/event_seq as the common temporal spine.

Datum-event release remains independent
---------------------------------------

The middle of one canonical controller interval may contain zero or more datum
lifecycle events.

For one viewing role:

    controller start
        always visible for a valid named role

    each datum lifecycle event
        independently visible or omitted according to datum read authority

    controller end
        always visible for a valid named role

A viewer can therefore hear:

    start at event_seq 41
    readable datum event at event_seq 42
    end at event_seq 45

while canonical events 43 and 44 were hidden.

Those positions are not lost. The projected polling receipt acknowledges them.

Correct projected polling
-------------------------

A role-projected poller must advance with:

    page["next_after_event_seq"]

It must not derive its cursor from the final visible event alone.

The page receipt describes the scanned canonical interval:

    visibility_receipt.hidden_event_count
    visibility_receipt.hidden_event_seq_ranges
    scanned_through_event_seq
    next_after_event_seq

P10's runner checks that the hidden ranges exactly equal:

    canonical event_seq values
        minus
    projected visible event_seq values

It also checks that no controller event is hidden.

P10 executable flow
-------------------

P10 uses two authored spans.

First span:

    daily
        maker-owned
        authoritative

    board
        unguarded
        non-authoritative

Second span:

    guess
        reviewer-owned
        authoritative

The viewing roles are:

    maker
        reads maker
        writes maker

    reviewer
        reads reviewer
        reads maker through read_roles
        writes reviewer

    auditor
        reads neither guarded role

Action 1: N -> S
~~~~~~~~~~~~~~~~

A maker STEP enters the program.

Canonical transition:

    ATSTART
        ->
    active daily/board span

Projected end memberships:

    maker:
        ["daily", "board"]

    reviewer:
        ["daily", "board"]

    auditor:
        ["board"]

The start active-membership field is absent for all roles.

Action 2: S -> S
~~~~~~~~~~~~~~~~

Maker fills only the public board.

The board emits one cumulative-progress event and reexplodes.

The same span remains active.

Projected memberships are equal at start and end for each role:

    maker:
        ["daily", "board"] -> ["daily", "board"]

    reviewer:
        ["daily", "board"] -> ["daily", "board"]

    auditor:
        ["board"] -> ["board"]

Action 3: S1 -> S2
~~~~~~~~~~~~~~~~~~

Maker completes daily.

The controller continues within the same admitted dispatch and mounts guess.

Canonical middle:

    daily success
    guess started
    guess hint

Boundary projections:

    maker:
        start active = ["daily", "board"]
        end active = []
        end mismatch = ["guess"]

    reviewer:
        start active = ["daily", "board"]
        end active = ["guess"]

    auditor:
        start active = ["board"]
        start mismatch = ["daily"]
        end active = []
        end mismatch = ["guess"]

Middle-event projections remain independent:

    maker:
        hears daily success only

    reviewer:
        hears daily success, guess started, and guess hint

    auditor:
        hears none of the guarded datum events

Action 4: S -> N
~~~~~~~~~~~~~~~~

Reviewer correctly fills guess.

Canonical transition:

    active guess span
        ->
    ATCOMPLETION

Start projections:

    maker:
        active = []
        mismatch = ["guess"]

    reviewer:
        active = ["guess"]

    auditor:
        active = []
        mismatch = ["guess"]

End projections:

    kind = "ATCOMPLETION"
    active-membership field absent

for all three roles.

Exact app-developer model
-------------------------

A downstream creative developer can use this complete mental model:

    controller start
        tells me the projected state against which my admitted action began

    datum events
        tell me the readable widget-level reactions produced during execution

    controller end
        tells me the projected state after execution finished or recovered

The developer does not need to know private engine frames, physical widget
instances, lifecycle storage rows, or context-obfuscation implementation.

The stable abstraction is:

    admitted dispatch
        ->
    projected pre-state
        ->
    zero or more readable datum reactions
        ->
    projected post-state

Final P10 laws
--------------

1. Start U is a pre-execution snapshot.
2. End U is a post-execution or recovered snapshot.
3. Start and end projections are independently computed.
4. Controller event_id/event_seq remain canonical through projection.
5. N -> S, S -> S, S1 -> S2, and S -> N are ordinary controller envelopes.
6. ATSTART and ATCOMPLETION omit active-span membership.
7. An empty active list means active canonical span plus total role redaction.
8. Datum-event visibility is independent from controller-U projection.
9. Visible datum packets remain canonical packets, not rewritten copies.
10. Projected event IDs are a subset of canonical event IDs.
11. Projected controller event IDs equal canonical controller event IDs.
12. Projected cursors advance through hidden canonical positions.
13. Role write denial remains eventless and belongs to P8/P9 admission logic.
14. Systematic failure overlays a lifecycle relation rather than creating a new
    lifecycle state.
15. A is present canonically on both controller phases.
16. A is projected datum-by-datum using read authority.
17. Fully hidden targeted A nulls the dispatch/dispatcher envelope.
18. Partially visible A retains correlation and contains only readable targets.
"""