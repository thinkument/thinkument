from __future__ import annotations

"""P13 — frontend data-blanket substrate expected and proven in core.

This flow proves the complete backend-owned substrate consumed by ThinkumentJS
without requiring a Flask/Django transport or the request-progress store itself.

For every admitted action the dry runner observes:

* the highest-facade dispatch receipt;
* request-scoped live controller/datum packets emitted through the existing
  callback wire before dispatch returns;
* the canonical events-since page after dispatch;
* exact live/canonical packet equality after removing only ``event_seq``;
* role-projected canonical pages through the existing ``views`` mechanism; and
* post-dispatch roleless/named-role U reads.

The distinction is deliberate:

    core live callback packets -> server progress store -> ThinkumentJS epsilon
    canonical event queue      -> events-since       -> ThinkumentJS theta

The server owns only hosting concerns such as transaction-commit visibility,
durable request-id receipts, and progress-channel scoping. It does not define a
second event or U grammar.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    CONTEXT_VIEW,
    DATA_BLANKET,
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
# board remains unguarded, so every role can read and write it.


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p13",
    title="Basic expose P13 — frontend data blankets proven E2E",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "maker_blanket",
            "title": "Maker daily beside public board",
            "widgets": ["daily", "board"],
            "authoritative": [True, False],
        },
        {
            "id": "reviewer_blanket",
            "title": "Reviewer completion datum",
            "widgets": ["guess"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None


def _dispatch_needles(*, committed: bool, outcome: str) -> dict:
    return {
        "kind": "live_session_dispatch_result_v1",
        "ok": True,
        "applied": True,
        "rejected": False,
        "events_only": False,
        "dispatch_outcome": str(outcome),
        "write_committed": bool(committed),
        "dispatch_concurrency.kind": (
            "live_session_dispatch_concurrency_receipt_v1"
        ),
        "dispatch_concurrency.applied": True,
        "dispatch_concurrency.rejected": False,
        "dispatch_concurrency.guarding": (
            "per_session_serialized_highest_facade"
        ),
        "dispatch_staleness.kind": (
            "live_session_dispatch_staleness_receipt_v1"
        ),
        "dispatch_staleness.outcome": "allowed",
    }


def _canonical_page_needles() -> dict:
    return {
        "kind": "live_session_events_since_v1",
        "role": None,
        "canonical_gap_detected": False,
        "visibility_receipt.kind": (
            "live_session_event_visibility_receipt_v1"
        ),
        "visibility_receipt.hidden_event_count": 0,
        "visibility_receipt.reason": "none",
    }


expected_unrolling = [
    STEP(
        role=ROLE_MAKER,
        expect=trident(
            event_kind=ACTIVE_KIND,
            finished=False,
            exact_middle=True,
        ),
        blanket=DATA_BLANKET(
            eps=[],
            dispatch=_dispatch_needles(
                committed=False,
                outcome="applied",
            ),
            canonical_page=_canonical_page_needles(),
            contexts=[
                CONTEXT_VIEW(
                    expect={
                        "kind": ACTIVE_KIND,
                        "datum_widgets_on_this_span": ["daily", "board"],
                    }
                ),
                CONTEXT_VIEW(
                    role=ROLE_AUDITOR,
                    expect={
                        "kind": ACTIVE_KIND,
                        "datum_widgets_on_this_span": ["board"],
                        (
                            "role_mismatch_modulation_info."
                            "mismatch_datum_ids"
                        ): ["daily"],
                        (
                            "role_mismatch_modulation_info.receipt.kind"
                        ): "role_mismatch_activity_receipt_v1",
                    },
                ),
            ],
        ),
        views=[
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
            "Mount proves receipt, live controller wire, canonical page, exact "
            "live/canonical parity, projected page, and projected U together."
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
            message_event("board", level="info", contains="cumulative"),
            event_kind=ACTIVE_KIND,
            finished=False,
            exact_middle=True,
        ),
        blanket=DATA_BLANKET(
            eps=[
                {
                    "channel": "datum.message",
                    "datum_id": "board",
                }
            ],
            dispatch=_dispatch_needles(
                committed=True,
                outcome="applied",
            ),
            canonical_page=_canonical_page_needles(),
            contexts=[
                CONTEXT_VIEW(
                    role=ROLE_AUDITOR,
                    expect={
                        "datum_widgets_on_this_span": ["board"],
                        (
                            "role_mismatch_modulation_info."
                            "mismatch_datum_ids"
                        ): ["daily"],
                    },
                ),
            ],
        ),
        views=[
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
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "The datum.message is observed live without event_seq, then the "
            "same packet is observed canonically with event_seq."
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
            message_event("daily", level="success", contains="believe"),
            message_event("guess", level="info", contains="started"),
            message_event("guess", level="info", contains="hint"),
            event_kind=ACTIVE_KIND,
            finished=False,
            exact_middle=True,
        ),
        blanket=DATA_BLANKET(
            eps=[
                {
                    "channel": "datum.message",
                    "datum_id": "daily",
                },
                {
                    "channel": "datum.message",
                    "datum_id": "guess",
                },
                {
                    "channel": "datum.message",
                    "datum_id": "guess",
                },
            ],
            dispatch=_dispatch_needles(
                committed=True,
                outcome="applied",
            ),
            canonical_page=_canonical_page_needles(),
            contexts=[
                CONTEXT_VIEW(
                    role=ROLE_MAKER,
                    expect={
                        "kind": ACTIVE_KIND,
                        "datum_widgets_on_this_span": [],
                        (
                            "role_mismatch_modulation_info."
                            "mismatch_datum_ids"
                        ): ["guess"],
                    },
                ),
                CONTEXT_VIEW(
                    role=ROLE_REVIEWER,
                    expect={
                        "kind": ACTIVE_KIND,
                        "datum_widgets_on_this_span": ["guess"],
                        (
                            "role_mismatch_modulation_info."
                            "mismatch_datum_ids"
                        ): [],
                    },
                ),
            ],
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
                    start_active=["daily", "board"],
                    start_mismatch_ids=[],
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
                    start_active=["board"],
                    start_mismatch_ids=["daily"],
                    end_active=[],
                    end_mismatch_ids=["guess"],
                    event_kind=ACTIVE_KIND,
                    finished=False,
                    exact_middle=True,
                ),
            ),
        ],
        note=(
            "One dispatch produces live old-scope success plus new-scope mount "
            "messages. The exact packets later receive canonical sequence "
            "numbers and role-filter independently."
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
            message_event("guess", level="success", contains="correct"),
            event_kind="ATCOMPLETION",
            finished=True,
            exact_middle=True,
        ),
        blanket=DATA_BLANKET(
            eps=[
                {
                    "channel": "datum.message",
                    "datum_id": "guess",
                }
            ],
            dispatch=_dispatch_needles(
                committed=True,
                outcome="applied",
            ),
            canonical_page=_canonical_page_needles(),
            contexts=[
                CONTEXT_VIEW(
                    expect={
                        "kind": "ATCOMPLETION",
                        "datum_widgets_on_this_span__absent": True,
                    }
                ),
                CONTEXT_VIEW(
                    role=ROLE_AUDITOR,
                    expect={
                        "kind": "ATCOMPLETION",
                        "datum_widgets_on_this_span__absent": True,
                    },
                ),
            ],
        ),
        views=[
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
            "Completion proves the same live/canonical bridge at S -> N and "
            "retains role projection and receipt assertions."
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
