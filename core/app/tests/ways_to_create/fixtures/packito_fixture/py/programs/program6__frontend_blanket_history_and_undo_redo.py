from __future__ import annotations

"""P6 — compact tape for HAI X/history, action timeline, UNDO and REDO.

The second appearance deliberately selects an *unclaimed* ``hai_renderer``.
That is not an error: HAI falls back to the app pack's overridable ``widget``
callable. Packito uses this step to prove that the generic callable remains a
real, tested extension seam even when a pack also owns dedicated renderers.
"""

from ._shared import base_sm, choice_widget, program


PROGRAM = program(
    program_id="packito_p6_frontend_blanket",
    title="Packito P6 — frontend blanket, history, undo, redo",
    symbols={},
    puppeteering={},
    widgets={
        "first": choice_widget(
            title="First committed decision",
            prompt="Create history entry one",
        ),
        "second": choice_widget(
            title="Second committed decision",
            prompt="Create history entry two",
            wires={
                "source": {
                    "from": "first",
                    "history": {
                        "select": "latest",
                        "required": True,
                        "max_results": 20,
                    },
                }
            },
        ),
    },
    flow=[
        {
            "id": "first",
            "title": "First decision",
            "widgets": ["first"],
            "authoritative": [True],
        },
        {
            "id": "second",
            "title": "Second decision through the pack-level widget fallback",
            "widgets": ["second"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "second": {
                        # Intentionally not present in Packito.widgetRenderers.
                        # HAI therefore delegates to appPack.callables.widget.
                        "hai_renderer": "packito.unclaimed.fallback.v1",
                    }
                }
            },
        },
    ],
)

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "frontend-blanket-history-undo-redo",
        "show_inspector": True,
    }
)
PUPPET = None

__all__ = ["PROGRAM", "PUPPET", "SESSION_METADATA"]
