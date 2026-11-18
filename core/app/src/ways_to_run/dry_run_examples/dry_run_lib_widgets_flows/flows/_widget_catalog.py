from __future__ import annotations

"""Opinionated logical-widget declarations for dry_run_lib_widgets_flows."""

from typing import Any, Dict

from ..widgets.base_widgets import (
    WA_WIDGET,
    WB_WIDGET,
    WC_WIDGET,
    WD_WIDGET,
    WP_WIDGET,
)


def fundamentals_base_widgets_v1() -> Dict[str, Any]:
    return {
        "guess": {
            "widget": WA_WIDGET,
            "title": "Number guess",
            "args": {
                "number": 17,
                "hint": "The target is between 1 and 30.",
            },
            "lifecycle": {
                "max_reexplosions": 12,
                "max_messages": 24,
            },
            "wires": {},
            "tags": ["game", "bounded"],
            "system_flags": {"guide_surface": "Wa"},
            "authoritative": True,
        },
        "daily": {
            "widget": WB_WIDGET,
            "title": "Daily number",
            "args": {
                "response_mode": "checkbox",
                "min_number_accepted": 1,
                "paragraph_must_contain": "",
                "adjust_min_seed": 11,
            },
            "lifecycle": {
                "max_reexplosions": 12,
                "max_messages": 24,
            },
            "wires": {},
            "tags": ["daily", "one-shot"],
            "system_flags": {"guide_surface": "Wb"},
            "authoritative": True,
        },
        "board": {
            "widget": WC_WIDGET,
            "title": "Cumulative board",
            "args": {
                "sum_should_not_exceed": 40,
            },
            "lifecycle": {
                "max_reexplosions": 50,
                "max_messages": 32,
                "exhausted_means_satisfied": False,
            },
            "wires": {},
            "tags": ["board", "unbounded"],
            "system_flags": {"guide_surface": "Wc"},
            "authoritative": False,
        },
    }


def fundamentals_wiring_observer_widget_v1() -> Dict[str, Any]:
    return {
        "widget": WD_WIDGET,
        "title": "Wiring observer",
        "args": {
            "lesson_label": "exact-wiring-runtime-view",
            "expected_many_count": 2,
        },
        "lifecycle": {
            "max_reexplosions": 8,
            "max_messages": 16,
        },
        "wires": {
            "one_source": {
                "from": "daily",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            },
            "many_sources": {
                "from": ["daily", "guess"],
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            },
            "self_previous": {
                "from": {"self": "previous"},
                "history": {
                    "select": "latest",
                    "required": False,
                    "max_results": 20,
                },
            },
        },
        "tags": ["wiring", "proof"],
        "system_flags": {"guide_surface": "Wd"},
        "authoritative": True,
    }


def fundamentals_program_authoring_probe_widget_v1() -> Dict[str, Any]:
    return {
        "widget": WP_WIDGET,
        "title": "Program authoring probe",
        "args": {
            "lesson_label": "$probe.label",
            "structured_payload": "$probe.payload",
            "first_choice": "$probe.choices.0",
            "effective_minimum": "$daily.minimum",
        },
        "lifecycle": {
            "max_reexplosions": 8,
            "max_messages": 16,
        },
        "wires": {},
        "tags": ["program", "authoring", "base"],
        "system_flags": {
            "guide_surface": "Wp",
            "base_only": True,
            "nested": {
                "base": True,
                "replace_me": "base",
            },
        },
        "authoritative": True,
    }


__all__ = [
    "fundamentals_base_widgets_v1",
    "fundamentals_program_authoring_probe_widget_v1",
    "fundamentals_wiring_observer_widget_v1",
]
