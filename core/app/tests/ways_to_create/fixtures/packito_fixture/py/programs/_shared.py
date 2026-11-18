from __future__ import annotations

"""Packito program-authoring helpers.

The teaching pack deliberately reuses the same already-proven ThinkProgram
constructor used by the correctness benchmark.  That keeps these examples
about *authoring choices* rather than duplicating the program-schema normalizer.
The resulting PROGRAM objects are ordinary P mappings and can be live-run,
dry-run, or DOM-scripted exactly like any other authored program.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    program,
)

from ..widgets import (
    BOARD_WIDGET,
    CHOICE_WIDGET,
    HISTORY_WIDGET,
    PUZZLE_ANSWER_WIDGET,
    PUZZLE_SEED_WIDGET,
    ROLE_GATE_WIDGET,
)


def lifecycle(
    *,
    max_reexplosions: int = 12,
    max_messages: int = 24,
    exhausted_means_satisfied: bool = False,
) -> Dict[str, Any]:
    return {
        "max_reexplosions": int(max_reexplosions),
        "max_messages": int(max_messages),
        "max_proc_notes": 0,
        "exhausted_means_satisfied": bool(exhausted_means_satisfied),
    }


def choice_widget(
    *,
    title: str,
    prompt: Any = "Choose deliberately",
    roles: list[str] | None = None,
    wires: Mapping[str, Any] | None = None,
    authoritative: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "widget": CHOICE_WIDGET,
        "title": str(title),
        "args": {
            "prompt": prompt,
            "option_a": "alpha",
            "option_b": "beta",
            "required_note_prefix": "WHY:",
            "appearance_label": "base",
        },
        "lifecycle": lifecycle(),
        "wires": deepcopy(dict(wires or {})),
        "tags": ["packito", "choice"],
        "system_flags": {"teaching_surface": "choice"},
        "authoritative": bool(authoritative),
    }
    if roles is not None:
        out["roles"] = list(roles)
    return out


def board_widget(
    *,
    title: str = "Live board",
    roles: list[str] | None = None,
    authoritative: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "widget": BOARD_WIDGET,
        "title": str(title),
        "args": {
            "label": str(title),
            "minimum": 0,
            "maximum": 100,
        },
        "lifecycle": lifecycle(max_reexplosions=50, max_messages=64),
        "wires": {},
        "tags": ["packito", "board", "reexploding"],
        "system_flags": {"teaching_surface": "board"},
        "authoritative": bool(authoritative),
    }
    if roles is not None:
        out["roles"] = list(roles)
    return out


def history_widget(*, title: str = "History observer") -> Dict[str, Any]:
    return {
        "widget": HISTORY_WIDGET,
        "title": str(title),
        "args": {"lesson": "runtime wire containers"},
        "lifecycle": lifecycle(max_reexplosions=8, max_messages=16),
        "wires": {
            "one_source": {
                "from": "source_a",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            },
            "many_sources": {
                "from": ["source_a", "source_b"],
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
        "tags": ["packito", "history", "wires"],
        "system_flags": {"teaching_surface": "history"},
        "authoritative": True,
    }


def role_gate_widget(*, title: str, role: str) -> Dict[str, Any]:
    return {
        "widget": ROLE_GATE_WIDGET,
        "title": str(title),
        "args": {"label": str(title)},
        "lifecycle": lifecycle(max_reexplosions=8, max_messages=16),
        "wires": {},
        "roles": [str(role)],
        "tags": ["packito", "role-gate"],
        "system_flags": {"teaching_surface": "role_gate"},
        "authoritative": True,
    }


def puzzle_seed_widget(*, role: str) -> Dict[str, Any]:
    return {
        "widget": PUZZLE_SEED_WIDGET,
        "title": "Generated puzzle seed",
        "args": {},
        "lifecycle": lifecycle(max_reexplosions=8, max_messages=16),
        "wires": {},
        "roles": [str(role)],
        "tags": ["packito", "funk", "seed"],
        "system_flags": {"teaching_surface": "funk_seed"},
        "authoritative": True,
    }


def puzzle_answer_widget(*, role: str, source: str) -> Dict[str, Any]:
    return {
        "widget": PUZZLE_ANSWER_WIDGET,
        "title": "Generated puzzle answer",
        "args": {"fallback_answer": 42},
        "lifecycle": lifecycle(max_reexplosions=12, max_messages=20),
        "wires": {
            "puzzle_source": {
                "from": str(source),
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            }
        },
        "roles": [str(role)],
        "tags": ["packito", "funk", "answer"],
        "system_flags": {"teaching_surface": "funk_answer"},
        "authoritative": True,
    }


def base_sm(*, app_args: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "app_pack_mould": {
            "app_pack": "packito",
            "app_args": deepcopy(dict(app_args or {})),
        },
        "manual_io": {
            "persistence": "disabled",
            "include_full_multiframespec_in_ctx": True,
            "include_forms_emitted_order_in_ctx": True,
        },
        "session_storage": {
            "events_snapshot_window": 128,
            "forms_emitted_snapshot_window": 32,
            "redo_max_depth": 8,
            "redo_action_max_payload_chars": 20_000,
        },
    }


__all__ = [
    "base_sm",
    "board_widget",
    "choice_widget",
    "history_widget",
    "lifecycle",
    "program",
    "puzzle_answer_widget",
    "puzzle_seed_widget",
    "role_gate_widget",
]
