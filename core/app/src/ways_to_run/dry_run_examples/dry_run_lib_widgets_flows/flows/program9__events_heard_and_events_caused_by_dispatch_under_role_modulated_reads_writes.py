from __future__ import annotations

"""
P9 — role-modulated writes and projected event reads.

"P9: How are those snapshots and middle datum events projected for each role?"

There is one canonical roleless session run and one canonical bounded event
queue.

Roles act only at the public boundary:

write boundary
    A dispatch role may fill/signal a guarded datum only when that exact role is
    assigned to the datum (or inherited from its span).

read boundary
    A viewing role may read its own guarded data plus roles listed in its
    ``read_roles``.

event release
    Controller packets remain visible with stable event_id/dispatch_id and a
    projected payload.U when their action envelope retains at least one readable
    target. If every action target is unreadable, payload.A and the
    correlation/actor envelope are blacked out while event_id/event_seq remain
    stable. Unreadable datum lifecycle packets are omitted.

P9 uses the existing Wa/Wb/Wc pack:

* daily is maker-owned;
* guess is reviewer-owned;
* board is unguarded and therefore public.

The auditor additionally receives the explicitly selected bounded receipt:

    identity      which datum shells were obfuscated
    ownership     which exact roles retain write authority
    activity      non-content lifecycle/fill counts and status

The same single mode string selects redaction plus receipt disclosure.

The transition dispatch from daily to guess is especially useful:

    canonical middle:
        daily success
        guess started
        guess hint

    maker view:
        daily success only; reviewer-owned guess events are omitted

    reviewer view:
        all three; reviewer can read maker through read_roles and owns guess

    auditor view:
        guarded daily/guess events are omitted

All views still receive the same controller start/end event identities and
advance through the same canonical cursor interval. A viewer with no readable
action target receives null dispatch/dispatcher correlation fields.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    PREFLIGHT_EXCEPTION,
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
            ROLE_AUDITOR: (
                "redacted-w-identity-ownership-activity-receipt"
            ),
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
# board deliberately has no roles and remains public.


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p9",
    title="Basic expose P9 — role-modulated reads and writes",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "maker_daily_with_public_board",
            "title": "Maker-owned datum beside an unguarded public datum",
            "widgets": ["daily", "board"],
            "authoritative": [True, False],
        },
        {
            "id": "reviewer_guess",
            "title": "Reviewer-owned completion datum",
            "widgets": ["guess"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None


expected_unrolling = [
    STEP(
        role=ROLE_MAKER,
        expect=trident(
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        views=[
            ROLE_VIEW(
                ROLE_MAKER,
                expect=role_projected_trident(
                    role=ROLE_MAKER,
                    start_kind="ATSTART",
                    start_active=None,
                    start_mismatch_ids=[],
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind="MANUALFILLNEEDEDSTEP",
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
                    end_active=["daily", "board"],
                    end_mismatch_ids=[],
                    event_kind="MANUALFILLNEEDEDSTEP",
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
                    end_active=["board"],
                    end_mismatch_ids=["daily"],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "Mount maker-owned daily beside unguarded board. Controller identity "
            "is public; each payload.U is projected for its viewing role."
        ),
    ),
    PREFLIGHT_EXCEPTION(
        role=ROLE_REVIEWER,
        fill={
            "daily": {
                "representative_number": 9,
                "good_day": True,
            }
        },
        exception_type="PermissionError",
        contains="daily",
        note=(
            "Reviewer can read maker through read_roles, but read authority does "
            "not grant write authority. Denial occurs before controller start."
        ),
    ),
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
            event_kind="MANUALFILLNEEDEDSTEP",
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
                    active=["daily", "board"],
                    mismatch_ids=[],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
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
                    active=["daily", "board"],
                    mismatch_ids=[],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
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
                    active=["board"],
                    mismatch_ids=["daily"],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
                ),
            ),
        ],
        note=(
            "The unguarded board is writable and readable by every named role; "
            "its datum event remains visible in every projection."
        ),
    ),
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
            event_kind="MANUALFILLNEEDEDSTEP",
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
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind="MANUALFILLNEEDEDSTEP",
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
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
                    end_active=["guess"],
                    end_mismatch_ids=[],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
                    exact_middle=True,
                ),
            ),
            ROLE_VIEW(
                ROLE_AUDITOR,
                expect=role_projected_trident(
                    role=ROLE_AUDITOR,
                    start_active=["board"],
                    start_mismatch_ids=["daily"],
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind="MANUALFILLNEEDEDSTEP",
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "One canonical dispatch closes maker daily and mounts reviewer guess. "
            "Each viewer hears only readable datum events. Controller event ids "
            "remain canonical; the dispatch/dispatcher envelope is visible only "
            "to viewers for whom A retains at least one readable target. The "
            "auditor's selected mode also publishes the bounded identity, "
            "ownership, and activity receipt under "
            "role_mismatch_modulation_info."
        ),
    ),
    PREFLIGHT_EXCEPTION(
        role=ROLE_MAKER,
        fill={
            "guess": {
                "guess_1_1": 9,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
        exception_type="PermissionError",
        contains="guess",
        note=(
            "Maker does not own reviewer guess and cannot write it. The rejected "
            "request is eventless."
        ),
    ),
    STEP(
        role=ROLE_REVIEWER,
        fill={
            "guess": {
                "guess_1_1": 17,
                "guess_1_2": 3,
                "guess_1_3": 5,
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
            "Reviewer-owned success completes the one canonical run. Maker and "
            "auditor retain controller continuity but do not receive the guarded "
            "guess lifecycle event. The auditor's selected mode also publishes "
            "the bounded identity, ownership, and activity receipt under "
            "role_mismatch_modulation_info."
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