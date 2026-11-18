from __future__ import annotations

"""
P7 — complete dispatch-boundary characterization.

"P7: Was the request admitted? If admitted, did it end in success, semantic rejection, or system_error?"

This program distinguishes every app-facing outcome family relevant to an
ordinary downstream dispatcher:

1. admitted success;
2. eventless request-normalization exception;
3. eventless highest-facade cursor rejection;
4. admitted datum exception converted to system_error end;
5. admitted semantic/lifecycle rejection (covered by P6);
6. successful recovery after a system_error;
7. stale target conflict;
8. stale active-scope conflict.

Cursor references
-----------------

The dry-run runner stores canonical cursors by symbolic name. ``cursor="$name"``
means "submit the exact cursor captured after the action that saved name."

The sequence uses one successful ``touch`` signal to advance the target frontier
without changing scope. Reusing the older mount cursor against the same datum is
therefore ``stale_conflict``.

Completing step one mounts a second physical appearance in a new authored step.
Reusing the earlier same-scope cursor against the now-current datum is therefore
``stale_scope_changed``; scope invalidation intentionally has precedence over a
datum-id match.

The RuntimeError is raised by the datum signal catcher itself. The expected
canonical suffix is exactly:

    controller.loop.start
    controller.loop.end(outcome="system_error")

No datum event is emitted before the exception.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    PREFLIGHT_EXCEPTION,
    PREFLIGHT_REJECTION,
    STEP,
    message_event,
    program,
    system_error_trident,
    trident,
)
from ..widgets.dispatch_failure_widgets import WG_WIDGET


WIDGETS = {
    "failure_probe": {
        "widget": WG_WIDGET,
        "title": "Dispatch failure boundary probe",
        "args": {},
        "lifecycle": {
            "max_reexplosions": 16,
            "max_messages": 24,
            "max_proc_notes": 0,
            "exhausted_means_satisfied": False,
        },
        "wires": {},
        "tags": ["p7", "dispatch-boundary", "proof"],
        "system_flags": {"guide_surface": "P7"},
        "authoritative": True,
    }
}


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p7",
    title="Basic expose P7 — preflight versus started failure",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "first_failure_boundary",
            "title": "Same-scope preflight and execution outcomes",
            "widgets": ["failure_probe"],
            "authoritative": [True],
        },
        {
            "id": "second_failure_boundary",
            "title": "New-scope stale cursor proof",
            "widgets": ["failure_probe"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None


expected_unrolling = [
    STEP(
        expect=trident(
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
            exact_middle=True,
        ),
        save_cursor="mounted",
        note=(
            "Mount the first probe. Its mount emits no informative event, so "
            "the envelope is exactly controller start/end."
        ),
    ),
    PREFLIGHT_EXCEPTION(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": ["not", "a", "mapping"],
        },
        exception_type="InvalidExternalFillError",
        contains="Invalid fill for one or more fields",
        note=(
            "Malformed signal normalization raises before controller start. "
            "Canonical high-water and event suffix remain unchanged."
        ),
    ),
    PREFLIGHT_REJECTION(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": {},
        },
        cursor="not-an-int",
        rejection_kind="invalid_event_cursor",
        note=(
            "Malformed optimistic cursor is normalized to an eventless facade "
            "rejection packet rather than a Python exception."
        ),
    ),
    PREFLIGHT_REJECTION(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": {},
        },
        cursor={"future_of_current": 100},
        rejection_kind="future_event_cursor",
        note=(
            "A cursor above canonical high-water is rejected before controller "
            "entry and appends no event."
        ),
    ),
    STEP(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": {},
        },
        expect=trident(
            message_event(
                "failure_probe",
                level="info",
                contains="touch accepted",
            ),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        save_cursor="touched",
        note=(
            "A successful signal commits the same datum target and advances its "
            "staleness frontier while remaining on the same scope."
        ),
    ),
    PREFLIGHT_REJECTION(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": {},
        },
        cursor="$mounted",
        rejection_kind="stale_conflict",
        note=(
            "The old mount cursor targets a datum successfully touched later in "
            "the same scope, so it is rejected eventlessly as stale_conflict."
        ),
    ),
    STEP(
        signal={
            "datum_id": "failure_probe",
            "kind": "raise_runtime",
            "info": {},
        },
        expect=system_error_trident(
            exception_type="RuntimeError",
            contains="intentional datum lifecycle failure",
            exact_middle=True,
        ),
        note=(
            "The datum raises after controller start. The controller catches the "
            "ordinary Exception and emits one matching system_error end."
        ),
    ),
    STEP(
        fill={
            "failure_probe": {
                "acknowledgement": "first scope recovered",
            }
        },
        expect=trident(
            message_event(
                "failure_probe",
                level="success",
                contains="boundary understood",
            ),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        save_cursor="second_scope",
        note=(
            "A system_error does not poison the session. A later valid fill "
            "completes step one and mounts the second authored scope."
        ),
    ),
    PREFLIGHT_REJECTION(
        signal={
            "datum_id": "failure_probe",
            "kind": "touch",
            "info": {},
        },
        cursor="$touched",
        rejection_kind="stale_scope_changed",
        note=(
            "The caller cursor predates movement to the second step. Scope "
            "invalidation wins before target-conflict classification."
        ),
    ),
    STEP(
        fill={
            "failure_probe": {
                "acknowledgement": "second scope complete",
            }
        },
        expect=trident(
            message_event(
                "failure_probe",
                level="success",
                contains="boundary understood",
            ),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note="Complete the second scope and P7.",
    ),
]


__all__ = ["PROGRAM", "PUPPET", "expected_unrolling"]
