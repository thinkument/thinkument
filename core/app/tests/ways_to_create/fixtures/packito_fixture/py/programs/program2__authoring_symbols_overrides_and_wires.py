from __future__ import annotations

"""P2 — symbols/C, appearance overrides, repeated widgets, and history wires."""

from _thinkprogram.thinkprogramTM.api import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
)

from ._shared import base_sm, choice_widget, history_widget, program


WIDGETS = {
    "source_a": choice_widget(
        title="Source A",
        prompt="$choice.prompt",
    ),
    "source_b": choice_widget(
        title="Source B",
        prompt="Second source",
        wires={
            "source": {
                "from": "source_a",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            }
        },
    ),
    "observer": history_widget(),
}

PROGRAM = program(
    program_id="packito_p2_authoring",
    title="Packito P2 — symbols, overrides, and wires",
    symbols={
        "choice.prompt": {
            "value": "Default symbol-backed prompt",
            "parametrize": True,
        },
        "choice.prefix": {
            "value": "WHY:",
            "parametrize": True,
        },
        "observer.lesson": {
            "value": "default wire lesson",
            "parametrize": True,
        },
    },
    puppeteering={
        "choice.prompt": "Authored prompt before launch C",
        "observer.lesson": "authored wire lesson",
    },
    widgets=WIDGETS,
    flow=[
        {
            "id": "source_a",
            "title": "Launch-C-controlled source",
            "widgets": ["source_a"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "source_a": {
                        "required_note_prefix": "$choice.prefix",
                        "appearance_label": "appearance-a",
                    }
                },
                "tags": {
                    "source_a": ["packito", "p2", "appearance-override"],
                },
                "system_flags": {
                    "source_a": {
                        "appearance_only": True,
                        "nested": {"replacement": "appearance"},
                    }
                },
            },
        },
        {
            "id": "source_b",
            "title": "Second source consumes latest source A",
            "widgets": ["source_b"],
            "authoritative": [True],
        },
        {
            "id": "observer_first",
            "title": "Observe one/many wire containers",
            "widgets": ["observer"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "observer": {"lesson": "$observer.lesson"},
                }
            },
        },
        {
            "id": "observer_second",
            "title": "Observe self-previous on repeated appearance",
            "widgets": ["observer"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "observer": {"lesson": "second appearance sees self_previous"},
                }
            },
        },
    ],
)

PUPPET = {
    PUPPETEERING_OVERLAY_KEY_V1: {
        "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        "strict": True,
    },
    "choice.prompt": "Launch C replaced this prompt",
    "choice.prefix": "BECAUSE:",
    "observer.lesson": "Launch C wire lesson",
}

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "P/C/overrides/wires",
        "show_inspector": True,
    }
)

__all__ = ["PROGRAM", "PUPPET", "SESSION_METADATA"]
