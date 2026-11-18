from __future__ import annotations

from __future__ import annotations


DEMO_PROGRAM_ID = "eventspollable_full_surface_demo"


"""
Reusable ThinkProgramTM fixture.

The program demonstrates every authored surface that materially affects the
controller Markovian blanket and downstream event interpretation:

- public widget args;
- guarded and unguarded roles;
- authoritative and non-authoritative same-span widgets;
- tags and system flags;
- lifecycle controls;
- historical wires;
- per-appearance overrides;
- a manual human barrier;
- machine continuation before and after the barrier.
"""

from copy import deepcopy
from typing import Any, Dict


from _thinksessions.example_reused_test_flow_setups.widgets.test import (
    W_COMPLEX,
    W_RELEASE,
    W_REVIEW,
    W_SUPPORT,
)

def demo_think_program_v1() -> Dict[str, Any]:
    lifecycle = {
        "mount_explode": True,
        "max_reexplosions": 24,
        "max_messages": 16,
        "max_proc_notes": 8,
    }
    latest_required = {
        "select": "latest",
        "required": True,
        "max_results": 20,
    }

    program = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "complex.prompt": {
                "value": "Describe the complete event surface",
                "parametrize": True,
            },
            "lifecycle": {
                "value": lifecycle,
            },
            "history.latest.required": {
                "value": latest_required,
            },
            "app.theme": {
                "value": {
                    "density": "compact",
                    "layout": "single-column",
                }
            },
        },
        "run": {
            "program": {
                "info": {
                    "id": DEMO_PROGRAM_ID,
                    "title": "Full eventspollableTM surface demo",
                    "description": (
                        "Machine complex input plus a roleless optional support "
                        "widget, manual review, then machine release."
                    ),
                    "args": {
                        "program_custom_arg": "program-custom",
                    },
                },
                "widgets": {
                    "complex": {
                        "widget": W_COMPLEX,
                        "title": "Complex input",
                        "args": {
                            "prompt": "$complex.prompt",
                            "min_words": 3,
                            "datum_custom": {
                                "datum_arg": "complex-custom",
                                "nested": {
                                    "proof": True,
                                },
                            },
                        },
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        "roles": ["maker"],
                        "tags": [
                            "machine-before-human",
                            "custom-micros",
                        ],
                        "system_flags": {
                            "ui_region": "main",
                            "fixture": "eventspollable-e2e",
                        },
                        "authoritative": True,
                    },
                    "support": {
                        "widget": W_SUPPORT,
                        "title": "Optional support",
                        "args": {
                            "support_label": "roleless optional helper",
                        },
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        # Empty datum roles and no flow roles make this datum
                        # unguarded. It is visible to every receiver role.
                        "roles": [],
                        "tags": [
                            "same-span",
                            "non-authoritative",
                            "unguarded",
                        ],
                        "system_flags": {
                            "ui_region": "aside",
                            "fixture": "eventspollable-e2e",
                        },
                        "authoritative": False,
                    },
                    "review": {
                        "widget": W_REVIEW,
                        "title": "Manual review",
                        "args": {
                            "review_mode": "strict",
                        },
                        "lifecycle": "$lifecycle",
                        "wires": {
                            "complex_commit": {
                                "from": "complex",
                                "history": "$history.latest.required",
                            }
                        },
                        "roles": ["reviewer"],
                        "tags": [
                            "manual-human-barrier",
                        ],
                        "system_flags": {
                            "ui_region": "review",
                        },
                        "authoritative": True,
                    },
                    "release": {
                        "widget": W_RELEASE,
                        "title": "Release",
                        "args": {
                            "release_channel": "stable",
                        },
                        "lifecycle": "$lifecycle",
                        "wires": {
                            "review_commit": {
                                "from": "review",
                                "history": "$history.latest.required",
                            }
                        },
                        "roles": ["release_ai"],
                        "tags": [
                            "machine-after-human",
                        ],
                        "system_flags": {
                            "ui_region": "release",
                        },
                        "authoritative": True,
                    },
                },
                "flow": [
                    {
                        "id": "complex",
                        "title": "Complex input frame",
                        "widgets": [
                            "complex",
                            "support",
                        ],
                        "authoritative": [
                            True,
                            False,
                        ],
                        "overrides": {
                            "args": {
                                "complex": {
                                    "datum_custom": {
                                        "appearance_arg": (
                                            "complex-appearance"
                                        ),
                                    }
                                }
                            },
                            "tags": {
                                "complex": [
                                    "machine-before-human",
                                    "appearance-overridden",
                                ]
                            },
                        },
                    },
                    {
                        "id": "review",
                        "title": "Manual review frame",
                        "widgets": [
                            "review",
                        ],
                        "roles": [
                            "reviewer",
                        ],
                        "authoritative": [
                            True,
                        ],
                        "overrides": {},
                    },
                    {
                        "id": "release",
                        "title": "Release frame",
                        "widgets": [
                            "release",
                        ],
                        "roles": [
                            "release_ai",
                        ],
                        "authoritative": [
                            True,
                        ],
                        "overrides": {},
                    },
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                },
                "app": {
                    "fixture": "eventspollable-full-surface",
                },
            },
        },
    }

    return deepcopy(program)


__all__ = [
    "demo_think_program_v1",
]