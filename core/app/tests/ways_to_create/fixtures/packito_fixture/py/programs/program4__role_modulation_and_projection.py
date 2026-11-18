from __future__ import annotations

"""P4 — one canonical session, role-scoped writes, projected reads/receipts."""

from ._shared import base_sm, board_widget, choice_widget, program


ROLE_MAKER = "maker"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"

WIDGETS = {
    "maker_choice": choice_widget(
        title="Maker-owned choice",
        prompt="Maker decides first",
        roles=[ROLE_MAKER],
    ),
    "public_board": board_widget(
        title="Public background board",
        authoritative=False,
    ),
    "reviewer_choice": choice_widget(
        title="Reviewer-owned choice",
        prompt="Reviewer decides second",
        roles=[ROLE_REVIEWER],
        wires={
            "source": {
                "from": "maker_choice",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            }
        },
    ),
}

PROGRAM = program(
    program_id="packito_p4_role_modulation",
    title="Packito P4 — role modulation",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "maker",
            "title": "Maker-owned datum beside public datum",
            "widgets": ["maker_choice", "public_board"],
            "authoritative": [True, False],
        },
        {
            "id": "reviewer",
            "title": "Reviewer-owned completion datum",
            "widgets": ["reviewer_choice"],
            "authoritative": [True],
        },
    ],
)

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "role-modulated-reads-and-writes",
        "show_inspector": True,
    }
)
SESSION_METADATA.update(
    {
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
                ROLE_AUDITOR: "redacted-w-identity-ownership-activity-receipt",
            },
        },
    }
)
PUPPET = None

__all__ = [
    "PROGRAM",
    "PUPPET",
    "ROLE_AUDITOR",
    "ROLE_MAKER",
    "ROLE_REVIEWER",
    "SESSION_METADATA",
]
