from __future__ import annotations

"""
P10 — complete controller snapshot-boundary matrix.

"P10: What lifecycle snapshot existed at Estart, and what snapshot existed at
Eend?"

P8 classifies admission and admitted outcomes.
P9 classifies middle datum-event emission and role-modulated release.
P10 classifies the two boundary-local payload.U snapshots of every admitted
controller envelope.

Formal model
------------

For one admitted action A and viewing role r:

    Estart(A).payload.U = project(pre_state(A), r)
    Eend(A).payload.U   = project(post_state(A), r)

Projection is evaluated twice. The two payload.U dictionaries are not aliases
and must not be generated from one shared active-datum expectation.

Canonical lifecycle-boundary classes
------------------------------------

Let N mean that no active authored span is exposed and S mean that an active
authored span is exposed.

N -> S
    Initial entry. Estart is ATSTART and omits
    datum_widgets_on_this_span. Eend is the newly mounted first span.

S -> S
    Same-scope interaction. Both boundaries refer to the same canonical span,
    though shells, fills, status, errors, and widget state may differ.

S1 -> S2
    One action satisfies the old span and mounts the next authored span.
    Estart describes S1 and Eend describes S2.

S -> N
    Terminal transition. Estart describes the final active span and Eend is
    ATCOMPLETION with datum_widgets_on_this_span absent.

Systematic failure is not another lifecycle class. It overlays one of these
relations according to the recovered post-state.

Projection law
--------------

For a named viewing role:

* unguarded datums remain public;
* readable guarded datums remain in active membership;
* unreadable guarded datums are removed from active membership and listed in
  role_mismatch_modulation_info.mismatch_datum_ids;
* absence of datum_widgets_on_this_span means no active authored span is
  exposed;
* datum_widgets_on_this_span == [] means an active canonical span exists but no
  active datum on it is readable to this viewer.

* Controller event identity remains canonical through projection.
* Controller action data is projected independently from both boundary U
  snapshots.
* The dispatch/dispatcher envelope remains canonical only when projected A has
  no datum targets or at least one readable target.
* Middle datum-event release is asserted independently of all three projections.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    ROLE_VIEW,
    STEP,
    base_widgets,
    message_event,
    program,
    role_projected_trident,
    trident,
)


ROLE_MAKER = "maker"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"

ACTIVE_KIND = "MANUALFILLNEEDEDSTEP"

SESSION_METADATA = {
    "roles": {
        ROLE_MAKER: {
            "label": "Maker",
            "read_roles": [],
        },
        ROLE_REVIEWER: {
            "label": "Reviewer",
            "read_roles": [ROLE_MAKER],
        },
        ROLE_AUDITOR: {
            "label": "Auditor",
            "read_roles": [],
        },
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            ROLE_MAKER: "redacted",
            ROLE_REVIEWER: "redacted",
            ROLE_AUDITOR: "redacted",
        },
    },
    "manual_io": {
        "persistence": "disabled",
        "include_full_multiframespec_in_ctx": True,
        "include_forms_emitted_order_in_ctx": True,
    },
    "session_storage": {
        "events_snapshot_window": 128,
        "forms_emitted_snapshot_window": 16,
        "redo_max_depth": 8,
        "redo_action_max_payload_chars": 20_000,
    },
}


WIDGETS = base_widgets()
WIDGETS["daily"]["roles"] = [ROLE_MAKER]
WIDGETS["guess"]["roles"] = [ROLE_REVIEWER]
# board deliberately remains unguarded/public.


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p10",
    title="Basic expose P10 — controller snapshot-boundary matrix",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "source_scope",
            "title": "Maker daily beside public board",
            "widgets": ["daily", "board"],
            "authoritative": [True, False],
        },
        {
            "id": "destination_scope",
            "title": "Reviewer guess completion scope",
            "widgets": ["guess"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None


expected_unrolling = [
    # ------------------------------------------------------------------
    # 1. N -> S
    # ------------------------------------------------------------------
    STEP(
        role=ROLE_MAKER,
        expect=trident(
            event_kind=ACTIVE_KIND,
            finished=False,
            exact_middle=True,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    role=ROLE_MAKER,
                    start_kind="ATSTART",
                    start_active=None,
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_REVIEWER,
                expect=role_projected_trident(
                    role=ROLE_REVIEWER,
                    start_kind="ATSTART",
                    start_active=None,
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    role=ROLE_AUDITOR,
                    start_kind="ATSTART",
                    start_active=None,
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["board"],
                    end_mismatch_ids=["daily"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "N -> S. The start snapshot is ATSTART and omits the active-span "
            "field; the end snapshot is the newly mounted source scope."
        ),
    ),

    # ------------------------------------------------------------------
    # 2. S -> S on the source scope
    # ------------------------------------------------------------------
    STEP(
        role=ROLE_MAKER,
        fill={
            "board": {
                "new_1": 1,
                "new_2": 3,
                "new_3": 5,
            }
        },
        expect=trident(
            message_event(
                "board",
                level="info",
                contains="cumulative",
            ),
            event_kind=ACTIVE_KIND,
            finished=False,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    message_event(
                        "board",
                        level="info",
                        contains="cumulative",
                    ),
                    role=ROLE_MAKER,
                    start_kind=ACTIVE_KIND,
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_REVIEWER,
                expect=role_projected_trident(
                    message_event(
                        "board",
                        level="info",
                        contains="cumulative",
                    ),
                    role=ROLE_REVIEWER,
                    start_kind=ACTIVE_KIND,
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    message_event(
                        "board",
                        level="info",
                        contains="cumulative",
                    ),
                    role=ROLE_AUDITOR,
                    start_kind=ACTIVE_KIND,
                    start_active=["board"],
                    start_mismatch_ids=["daily"],
                    end_kind=ACTIVE_KIND,
                    end_active=["board"],
                    end_mismatch_ids=["daily"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "S -> S. Both snapshots describe the same canonical source scope, "
            "while each role receives its own independently calculated "
            "projection."
        ),
    ),

    # ------------------------------------------------------------------
    # 3. S1 -> S2
    # ------------------------------------------------------------------
    STEP(
        role=ROLE_MAKER,
        fill={
            "daily": {
                "representative_number": 9,
                "good_day": True,
            }
        },
        expect=trident(
            message_event(
                "daily",
                level="success",
                contains="believe",
            ),
            message_event(
                "guess",
                level="info",
                contains="started",
            ),
            message_event(
                "guess",
                level="info",
                contains="hint",
            ),
            event_kind=ACTIVE_KIND,
            finished=False,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    message_event(
                        "daily",
                        level="success",
                        contains="believe",
                    ),
                    role=ROLE_MAKER,
                    start_kind=ACTIVE_KIND,
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_REVIEWER,
                expect=role_projected_trident(
                    message_event(
                        "daily",
                        level="success",
                        contains="believe",
                    ),
                    message_event(
                        "guess",
                        level="info",
                        contains="started",
                    ),
                    message_event(
                        "guess",
                        level="info",
                        contains="hint",
                    ),
                    role=ROLE_REVIEWER,
                    start_kind=ACTIVE_KIND,
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["guess"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    role=ROLE_AUDITOR,
                    start_kind=ACTIVE_KIND,
                    start_active=["board"],
                    start_mismatch_ids=["daily"],
                    end_kind=ACTIVE_KIND,
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "S1 -> S2. Estart projects the old daily/board scope; Eend "
            "projects the newly mounted guess scope. Middle datum visibility "
            "is filtered independently from both controller snapshots."
        ),
    ),

    # ------------------------------------------------------------------
    # 4. S -> S on the destination scope, proving [] versus absence.
    # ------------------------------------------------------------------
    STEP(
        role=ROLE_REVIEWER,
        fill={
            "guess": {
                "guess_1_1": 9,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
        expect=trident(
            message_event(
                "guess",
                level="info",
                contains="closest",
            ),
            event_kind=ACTIVE_KIND,
            finished=False,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    role=ROLE_MAKER,
                    start_kind=ACTIVE_KIND,
                    start_active=[],
                    start_mismatch_ids=["guess"],
                    end_kind=ACTIVE_KIND,
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_REVIEWER,
                expect=role_projected_trident(
                    message_event(
                        "guess",
                        level="info",
                        contains="closest",
                    ),
                    role=ROLE_REVIEWER,
                    start_kind=ACTIVE_KIND,
                    start_active=["guess"],
                    start_mismatch_ids=[],
                    end_kind=ACTIVE_KIND,
                    end_active=["guess"],
                    end_mismatch_ids=[],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    role=ROLE_AUDITOR,
                    start_kind=ACTIVE_KIND,
                    start_active=[],
                    start_mismatch_ids=["guess"],
                    end_kind=ACTIVE_KIND,
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "S -> S on the destination scope. An empty projected active list "
            "is a real field value: the canonical span exists, but every active "
            "datum is redacted for maker and auditor."
        ),
    ),

    # ------------------------------------------------------------------
    # 5. S -> N
    # ------------------------------------------------------------------
    STEP(
        role=ROLE_REVIEWER,
        fill={
            "guess": {
                "guess_2_1": 17,
                "guess_2_2": 3,
            }
        },
        expect=trident(
            message_event(
                "guess",
                level="success",
                contains="correct",
            ),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    role=ROLE_MAKER,
                    start_kind=ACTIVE_KIND,
                    start_active=[],
                    start_mismatch_ids=["guess"],
                    end_kind="ATCOMPLETION",
                    end_active=None,
                    end_mismatch_ids=[],
                    event_kind="ATCOMPLETION",
                    finished=True,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_REVIEWER,
                expect=role_projected_trident(
                    message_event(
                        "guess",
                        level="success",
                        contains="correct",
                    ),
                    role=ROLE_REVIEWER,
                    start_kind=ACTIVE_KIND,
                    start_active=["guess"],
                    start_mismatch_ids=[],
                    end_kind="ATCOMPLETION",
                    end_active=None,
                    end_mismatch_ids=[],
                    event_kind="ATCOMPLETION",
                    finished=True,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    role=ROLE_AUDITOR,
                    start_kind=ACTIVE_KIND,
                    start_active=[],
                    start_mismatch_ids=["guess"],
                    end_kind="ATCOMPLETION",
                    end_active=None,
                    end_mismatch_ids=[],
                    event_kind="ATCOMPLETION",
                    finished=True,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "S -> N. The final start snapshot still describes the guess scope; "
            "the ATCOMPLETION end snapshot omits "
            "datum_widgets_on_this_span."
        ),
    ),
]


__all__ = [
    "PROGRAM",
    "PUPPET",
    "ROLE_AUDITOR",
    "ROLE_MAKER",
    "ROLE_REVIEWER",
    "SESSION_METADATA",
    "expected_unrolling",
]