from __future__ import annotations

"""Program 12 widgets for generated puzzle creation and completion.

The widgets own only lifecycle semantics:

* the generator commits one puzzle plus answer key;
* answer widgets expose the current answer grammar and let platform semantic
  validation reject incorrect generated answers before lifecycle completion;
* checkpoint widgets create explicit human barriers.

Generated behavior remains in ``funks/funked_fillers.py``.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.constants import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
)
from _thinkprogram.thinkwidgetTM.decorators import thinkwidgetTM_config
from _thinkprogram.thinkwidgetTM.types import Reexplode


PUZZLE_GENERATOR_WIDGET = (
    "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.p12.puzzle_generator.v1"
)
PUZZLE_ANSWER_WIDGET = (
    "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.p12.puzzle_answer.v1"
)
PUZZLE_CHECKPOINT_WIDGET = (
    "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.p12.puzzle_checkpoint.v1"
)


def _args(fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    return dict(raw or {}) if isinstance(raw, Mapping) else {}


def _lifecycle_shell(
    prior: Mapping[str, Any],
    *,
    title: str,
    micros: list[Dict[str, Any]],
) -> Dict[str, Any]:
    shell = deepcopy(dict(prior))
    shell["title"] = str(title)
    shell["micros"] = deepcopy(micros)
    return shell


def _latest_wire_state(
    fill_shell: Mapping[str, Any],
    *,
    wire_name: str,
) -> Dict[str, Any]:
    args = _args(fill_shell)
    kernel = args.get("__kernel")
    kernel = kernel if isinstance(kernel, Mapping) else {}
    past_wires = kernel.get("past_wires")
    past_wires = past_wires if isinstance(past_wires, Mapping) else {}
    wire = past_wires.get(wire_name)
    wire = wire if isinstance(wire, Mapping) else {}
    value = wire.get("value")
    value = value if isinstance(value, Mapping) else {}
    state = value.get("state")
    return dict(state) if isinstance(state, Mapping) else {}


@thinkwidgetTM_config(
    PUZZLE_GENERATOR_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={},
)
class PuzzleGeneratorWidget(DatumLifecycleWidget):
    """One generated role authors a puzzle and its answer key."""

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        self.puzzle_text = None
        self.answer_key = None
        return Reexplode(
            next_fill_shell=_lifecycle_shell(
                fill_data["fill_shell"],
                title="Generate a compact arithmetic puzzle",
                micros=[
                    {
                        "name": "puzzle_text",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "name": "answer_key",
                        "type": "integer",
                        "required": True,
                    },
                ],
            ),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        current = dict(fill_data.get("current_fills") or {})
        self.puzzle_text = str(current["puzzle_text"])
        self.answer_key = int(current["answer_key"])
        self.commit = {
            "puzzle_text": self.puzzle_text,
            "answer_key": self.answer_key,
        }
        return True


@thinkwidgetTM_config(
    PUZZLE_ANSWER_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={
        "puzzle_source": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class PuzzleAnswerWidget(DatumLifecycleWidget):
    """Answer shell whose validator creates retry-aware semantic feedback."""

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        source = _latest_wire_state(
            fill_data["fill_shell"],
            wire_name="puzzle_source",
        )
        args = _args(fill_data["fill_shell"])

        self.puzzle_text = str(
            source.get("puzzle_text")
            or args.get("puzzle_text")
            or "What is 6 × 7?"
        )
        self.answer_key = int(
            source.get("answer_key")
            if source.get("answer_key") is not None
            else args.get("answer_key", 42)
        )

        expected = str(self.answer_key)
        self.submitted_answer = None
        self.correct = False

        return Reexplode(
            next_fill_shell=_lifecycle_shell(
                fill_data["fill_shell"],
                title=self.puzzle_text,
                micros=[
                    {
                        "name": "answer",
                        "type": "select",
                        "required": True,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM."
                                    "validators.choice:in_allowed"
                                ),
                                "args": {"options": [expected]},
                            }
                        ],
                    }
                ],
            ),
            pre_computed_fills={"answer": ""},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        submitted = str(
            dict(fill_data.get("current_fills") or {})["answer"]
        )
        self.submitted_answer = submitted
        self.correct = submitted == str(self.answer_key)
        self.commit = {
            "puzzle_text": self.puzzle_text,
            "answer_key": self.answer_key,
            "submitted_answer": submitted,
            "correct": self.correct,
        }
        return True


@thinkwidgetTM_config(
    PUZZLE_CHECKPOINT_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "checkpoint_label": {
            "type": "str",
            "required": False,
            "default": "Human checkpoint",
        },
    },
    wires={},
)
class PuzzleCheckpointWidget(DatumLifecycleWidget):
    """Explicit non-funked human barrier reusable across collaboration steps."""

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        self.checkpoint_label = str(
            _args(fill_data["fill_shell"]).get(
                "checkpoint_label",
                "Human checkpoint",
            )
        )
        self.approval = None
        return Reexplode(
            next_fill_shell=_lifecycle_shell(
                fill_data["fill_shell"],
                title=(
                    f"{self.checkpoint_label}: approve generated continuation"
                ),
                micros=[
                    {
                        "name": "approval",
                        "type": "select",
                        "required": True,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM."
                                    "validators.choice:in_allowed"
                                ),
                                "args": {"options": ["approve"]},
                            }
                        ],
                    }
                ],
            ),
            pre_computed_fills={"approval": ""},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        self.approval = str(
            dict(fill_data.get("current_fills") or {})["approval"]
        )
        self.commit = {
            "checkpoint_label": self.checkpoint_label,
            "approval": self.approval,
        }
        return True


PROGRAM12_WIDGET_CLASSES = (
    PuzzleGeneratorWidget,
    PuzzleAnswerWidget,
    PuzzleCheckpointWidget,
)


__all__ = [
    "PROGRAM12_WIDGET_CLASSES",
    "PUZZLE_ANSWER_WIDGET",
    "PUZZLE_CHECKPOINT_WIDGET",
    "PUZZLE_GENERATOR_WIDGET",
    "PuzzleAnswerWidget",
    "PuzzleCheckpointWidget",
    "PuzzleGeneratorWidget",
]