from __future__ import annotations

"""Copy/paste template: one backend + FormreactTM-ready ThinkProgram.

The ThinkProgram grammar itself does not change for frontend readiness.
Frontend readiness enters only through each widget's normal authored args,
principally the formreactTM_widget_panel declaration.
"""

from typing import Any, Dict

try:
    from _vial_js_interactive.formreactPY.opinionations import (
        FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1,
        formreacttm_aesthetics_v1,
        formreacttm_widget_panel_v1,
    )
except ImportError:
    FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1 = "formreactTM_widget_panel"

    def formreacttm_aesthetics_v1(*, css_classes=None, slot=None):
        return {"css_classes": css_classes or [], "slot": slot}

    def formreacttm_widget_panel_v1(*, js_gen_name="", js_gen_args=None, aesthetics=None, signal_button_defaults=None):
        return {
            "js_gen_name": js_gen_name,
            "js_gen_args": js_gen_args or {},
            "aesthetics": aesthetics or {},
            "signal_button_defaults": signal_button_defaults or {},
        }


EDITOR_WIDGET_V1: str = "my_app.editor.v1"       # must be registered at startup
REVIEW_WIDGET_V1: str = "my_app.review.v1"       # must be registered at startup


WIDGETS: Dict[str, Any] = {
    "editor": {
        "widget": EDITOR_WIDGET_V1,
        "title": "Edit",
        "args": {
            "backend_policy": "$app.backend_policy",
            FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1: formreacttm_widget_panel_v1(
                js_gen_name="form_basic",  # registered renderportfolio ID
                js_gen_args={"variant": "$ui.variant"},
                aesthetics=formreacttm_aesthetics_v1(
                    css_classes=["my-editor-host"],
                    slot="main",
                ),
                signal_button_defaults={
                    "refresh": "refresh",
                },
            ),
        },
        "lifecycle": {
            "max_reexplosions": 16,
            "max_messages": 24,
        },
        "wires": {},
        "tags": ["editor"],
        "system_flags": {},
        # Add "roles": ["maker"] only when this datum is role-guarded.
        "authoritative": True,
    },
    "review": {
        "widget": REVIEW_WIDGET_V1,
        "title": "Review",
        "args": {
            FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1: formreacttm_widget_panel_v1(
                js_gen_name="form_confirmation",
                js_gen_args={},
                aesthetics=formreacttm_aesthetics_v1(
                    css_classes=["my-review-host"],
                    slot="main",
                ),
                signal_button_defaults={
                    "request_summary": "info",
                },
            ),
        },
        "lifecycle": {
            "max_reexplosions": 8,
            "max_messages": 16,
        },
        "wires": {
            "editor_result": {
                "from": "editor",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 4,
                },
            },
            "self_previous": {
                "from": {"self": "previous"},
                "history": {
                    "select": "latest",
                    "required": False,
                    "max_results": 4,
                },
            },
        },
        "tags": ["review", "history-consumer"],
        "system_flags": {},
        "authoritative": True,
    },
}


# P: static program topology + default parameterization.
PROGRAM: Dict[str, Any] = {
    "program_id": "my_app_program",
    "title": "My app program",
    "symbols": {
        "app.backend_policy": {
            "value": {"mode": "standard"},
            "parametrize": True,
        },
        "ui.variant": {
            "value": "default",
            "parametrize": True,
        },
    },
    "puppeteering": {},
    "widgets": WIDGETS,
    "flow": [
        {
            "id": "edit",
            "title": "Edit",
            "widgets": ["editor"],
            "authoritative": [True],
        },
        {
            "id": "review_first",
            "title": "Review",
            "widgets": ["review"],
            "authoritative": [True],
        },
        {
            "id": "review_again",
            "title": "Final review",
            "widgets": ["review"],
            "authoritative": [True],
            "overrides": {
                "title": {
                    "review": "Final review",
                },
                "tags": {
                    "review": ["review", "second-appearance"],
                },
                "lifecycle": {
                    "review": {"max_messages": 24},
                },
            },
        },
    ],
}


__all__ = [
    "EDITOR_WIDGET_V1",
    "PROGRAM",
    "REVIEW_WIDGET_V1",
    "WIDGETS",
]
