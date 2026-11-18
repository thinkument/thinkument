from __future__ import annotations

"""Packito's teaching widgets.

Each widget is intentionally small but each one proves a different part of the
higher-developer contract.  None sends HTML to the browser.  Presentation is
selected only by the stable ``hai_renderer`` static argument and the browser
pack registered under the same app-pack id.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.validators.number import (
    max_number_validator_spec,
    min_number_validator_spec,
)
from _thinkprogram.thinkwidgetTM.constants import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    MISSING_SIGNAL_RAISE,
)
from _thinkprogram.thinkwidgetTM.decorators import (
    thinkwidgetTM_config,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode
from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.decorators import signal_catcher

from .widget_runtime import (
    authored_args_v1,
    lifecycle_shell_v1,
    runtime_state_from_row_v1,
    wire_rows_v1,
    wire_state_index_v1,
)


CHOICE_WIDGET = "packito.widget.choice.v1"
BOARD_WIDGET = "packito.widget.board.v1"
HISTORY_WIDGET = "packito.widget.history.v1"
ROLE_GATE_WIDGET = "packito.widget.role_gate.v1"
PUZZLE_SEED_WIDGET = "packito.widget.puzzle_seed.v1"
PUZZLE_ANSWER_WIDGET = "packito.widget.puzzle_answer.v1"

CHOICE_RENDERER = "packito.choice.v1"
BOARD_RENDERER = "packito.board.v1"
HISTORY_RENDERER = "packito.history.v1"
ROLE_GATE_RENDERER = "packito.role_gate.v1"
PUZZLE_SEED_RENDERER = "packito.puzzle_seed.v1"
PUZZLE_ANSWER_RENDERER = "packito.puzzle_answer.v1"

SIGNAL_REFRESH = "refresh"


def _emit(
    widget: DatumLifecycleWidget,
    message_type: str,
    **payload: Any,
) -> None:
    widget._emit({"message_type": str(message_type), **deepcopy(payload)}, name=str(message_type))


def _choice_micros(*, option_a: str, option_b: str) -> list[Dict[str, Any]]:
    return [
        {
            "name": "choice",
            "type": "select",
            "label": "Choice",
            "required": True,
            "options": [option_a, option_b],
            "validators": [
                {
                    "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
                    "args": {"options": [option_a, option_b]},
                }
            ],
        },
        {
            "name": "note",
            "type": "text",
            "label": "Reason",
            "required": True,
        },
    ]


@thinkwidgetTM_config(
    CHOICE_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": CHOICE_RENDERER,
        },
        "prompt": {
            "type": "str",
            "required": False,
            "default": "Choose deliberately",
        },
        "option_a": {
            "type": "str",
            "required": False,
            "default": "alpha",
        },
        "option_b": {
            "type": "str",
            "required": False,
            "default": "beta",
        },
        "required_note_prefix": {
            "type": "str",
            "required": False,
            "default": "WHY:",
        },
        "appearance_label": {
            "type": "str",
            "required": False,
            "default": "default",
        },
    },
    wires={
        "source": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class ChoiceWidget(DatumLifecycleWidget):
    """Platform-valid choice + lifecycle-valid reason + signal reexplosion."""

    def _shell(self, fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
        return lifecycle_shell_v1(
            fill_shell,
            title=self.prompt,
            micros=_choice_micros(
                option_a=self.option_a,
                option_b=self.option_b,
            ),
        )

    def _reexplode(
        self,
        fill_data: Mapping[str, Any],
        *,
        values: Mapping[str, Any] | None = None,
    ) -> Reexplode:
        return Reexplode(
            next_fill_shell=self._shell(fill_data["fill_shell"]),
            pre_computed_fills=deepcopy(dict(values or {})),
            prefill_hints={
                "choice": f"{self.option_a} or {self.option_b}",
                "note": f"start with {self.required_note_prefix}",
            },
        )

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        args = authored_args_v1(fill_data["fill_shell"])
        self.prompt = str(args.get("prompt", "Choose deliberately"))
        self.option_a = str(args.get("option_a", "alpha"))
        self.option_b = str(args.get("option_b", "beta"))
        self.required_note_prefix = str(args.get("required_note_prefix", "WHY:"))
        self.appearance_label = str(args.get("appearance_label", "default"))

        rows = wire_rows_v1(fill_data["fill_shell"], "source")
        self.source_state = runtime_state_from_row_v1(rows[0]) if rows else {}
        self.revision = 1
        self.accepted_choice = None
        self.accepted_note = None
        self.domain_rejections = 0
        self.refresh_count = 0

        _emit(
            self,
            "packito.global_notice",
            phase="mount",
            appearance_label=self.appearance_label,
        )
        _emit(
            self,
            "packito.widget_notice",
            phase="mount",
            source_state=deepcopy(self.source_state),
        )
        return self._reexplode(fill_data)

    @signal_catcher(SIGNAL_REFRESH)
    def refresh(self, signal, position, fill_data, limits, stats):
        del position, limits, stats
        self.refresh_count = int(self.refresh_count) + 1
        self.revision = int(self.revision) + 1
        _emit(
            self,
            "packito.custom_notice",
            phase="signal",
            signal=deepcopy(dict(signal or {})),
            revision=self.revision,
        )
        return self._reexplode(
            fill_data,
            values=dict(fill_data.get("current_fills") or {}),
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        current = dict(fill_data.get("current_fills") or {})
        choice = str(current["choice"])
        note = str(current["note"])
        self.revision = int(self.revision) + 1

        if not note.startswith(self.required_note_prefix):
            self.domain_rejections = int(self.domain_rejections) + 1
            self.message(
                "error",
                f"note must start with {self.required_note_prefix!r}",
            )
            _emit(
                self,
                "packito.custom_notice",
                phase="domain_rejected",
                choice=choice,
                note=note,
                domain_rejections=self.domain_rejections,
            )
            return self._reexplode(fill_data, values=current)

        self.accepted_choice = choice
        self.accepted_note = note
        self.message("success", f"accepted {choice}")
        _emit(
            self,
            "packito.widget_notice",
            phase="accepted",
            choice=choice,
            revision=self.revision,
        )
        return True


@thinkwidgetTM_config(
    BOARD_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": BOARD_RENDERER,
        },
        "label": {
            "type": "str",
            "required": False,
            "default": "Live board",
        },
        "minimum": {"type": "int", "required": False, "default": 0},
        "maximum": {"type": "int", "required": False, "default": 100},
    },
    wires={},
)
class BoardWidget(DatumLifecycleWidget):
    """A deliberately reexploding accumulator for non-authoritative/limit demos."""

    def _shell(self, fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
        return lifecycle_shell_v1(
            fill_shell,
            title=self.label,
            micros=[
                {
                    "name": "delta",
                    "type": "integer",
                    "required": True,
                    "validators": [
                        min_number_validator_spec(self.minimum),
                        max_number_validator_spec(self.maximum),
                    ],
                }
            ],
        )

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        args = authored_args_v1(fill_data["fill_shell"])
        self.label = str(args.get("label", "Live board"))
        self.minimum = int(args.get("minimum", 0))
        self.maximum = int(args.get("maximum", 100))
        self.total = 0
        self.ticks = 0
        _emit(self, "packito.global_notice", phase="board_mount", total=0)
        return Reexplode(
            next_fill_shell=self._shell(fill_data["fill_shell"]),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        delta = int(dict(fill_data.get("current_fills") or {})["delta"])
        self.total = int(self.total) + delta
        self.ticks = int(self.ticks) + 1
        self.message("info", f"board total is {self.total}")
        _emit(
            self,
            "packito.silent_metric",
            phase="board_tick",
            total=self.total,
            ticks=self.ticks,
        )
        return Reexplode(
            next_fill_shell=self._shell(fill_data["fill_shell"]),
            pre_computed_fills={},
        )


@thinkwidgetTM_config(
    HISTORY_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": HISTORY_RENDERER,
        },
        "lesson": {
            "type": "str",
            "required": False,
            "default": "history",
        },
    },
    wires={
        "one_source": {"multiplicity": "one", "required": False},
        "many_sources": {"multiplicity": "many", "required": False},
        "self_previous": {"multiplicity": "one", "required": False},
    },
)
class HistoryWidget(DatumLifecycleWidget):
    """Expose the exact authored-wire -> runtime-history observation surface."""

    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        args = authored_args_v1(fill_data["fill_shell"])
        self.lesson = str(args.get("lesson", "history"))
        self.wire_index = wire_state_index_v1(fill_data["fill_shell"])
        self.acknowledgement = None
        _emit(
            self,
            "packito.global_notice",
            phase="history_observed",
            lesson=self.lesson,
            wire_index=deepcopy(self.wire_index),
        )
        return Reexplode(
            next_fill_shell=lifecycle_shell_v1(
                fill_data["fill_shell"],
                title="Inspect runtime history wires",
                micros=[
                    {
                        "name": "acknowledgement",
                        "type": "text",
                        "required": True,
                    }
                ],
            ),
            pre_computed_fills={},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        self.acknowledgement = str(
            dict(fill_data.get("current_fills") or {})["acknowledgement"]
        )
        self.message("success", "history observation acknowledged")
        return True


@thinkwidgetTM_config(
    ROLE_GATE_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": ROLE_GATE_RENDERER,
        },
        "label": {
            "type": "str",
            "required": False,
            "default": "Approval",
        },
    },
    wires={},
)
class RoleGateWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        args = authored_args_v1(fill_data["fill_shell"])
        self.label = str(args.get("label", "Approval"))
        self.approval = None
        _emit(self, "packito.widget_notice", phase="role_gate_mount")
        return Reexplode(
            next_fill_shell=lifecycle_shell_v1(
                fill_data["fill_shell"],
                title=self.label,
                micros=[
                    {
                        "name": "approval",
                        "type": "select",
                        "required": True,
                        "validators": [
                            {
                                "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
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
        _emit(
            self,
            "packito.custom_notice",
            phase="role_gate_approved",
            approval=self.approval,
        )
        self.message("success", "approved")
        return True


@thinkwidgetTM_config(
    PUZZLE_SEED_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": PUZZLE_SEED_RENDERER,
        },
    },
    wires={},
)
class PuzzleSeedWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        self.puzzle_text = None
        self.answer_key = None
        _emit(self, "packito.global_notice", phase="puzzle_seed_mount")
        return Reexplode(
            next_fill_shell=lifecycle_shell_v1(
                fill_data["fill_shell"],
                title="Generate a puzzle",
                micros=[
                    {"name": "puzzle_text", "type": "text", "required": True},
                    {"name": "answer_key", "type": "integer", "required": True},
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
        _emit(self, "packito.widget_notice", phase="puzzle_seed_committed")
        return True


@thinkwidgetTM_config(
    PUZZLE_ANSWER_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": PUZZLE_ANSWER_RENDERER,
        },
        "fallback_answer": {
            "type": "int",
            "required": False,
            "default": 42,
        },
    },
    wires={
        "puzzle_source": {"multiplicity": "one", "required": False},
    },
)
class PuzzleAnswerWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        del position, limits, stats
        args = authored_args_v1(fill_data["fill_shell"])
        rows = wire_rows_v1(fill_data["fill_shell"], "puzzle_source")
        source = runtime_state_from_row_v1(rows[0]) if rows else {}
        self.puzzle_text = str(source.get("puzzle_text") or "What is 6 x 7?")
        self.answer_key = int(
            source.get("answer_key")
            if source.get("answer_key") is not None
            else args.get("fallback_answer", 42)
        )
        self.submitted_answer = None
        self.correct = False
        expected = str(self.answer_key)
        _emit(
            self,
            "packito.widget_notice",
            phase="puzzle_answer_mount",
            puzzle_text=self.puzzle_text,
        )
        return Reexplode(
            next_fill_shell=lifecycle_shell_v1(
                fill_data["fill_shell"],
                title=self.puzzle_text,
                micros=[
                    {
                        "name": "answer",
                        "type": "select",
                        "required": True,
                        "validators": [
                            {
                                "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
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
        submitted = str(dict(fill_data.get("current_fills") or {})["answer"])
        self.submitted_answer = submitted
        self.correct = submitted == str(self.answer_key)
        self.commit = {
            "puzzle_text": self.puzzle_text,
            "answer_key": self.answer_key,
            "submitted_answer": submitted,
            "correct": self.correct,
        }
        _emit(
            self,
            "packito.global_notice",
            phase="puzzle_answer_committed",
            correct=self.correct,
        )
        return True


WIDGET_CLASSES = (
    ChoiceWidget,
    BoardWidget,
    HistoryWidget,
    RoleGateWidget,
    PuzzleSeedWidget,
    PuzzleAnswerWidget,
)


__all__ = [
    "BOARD_RENDERER",
    "BOARD_WIDGET",
    "BoardWidget",
    "CHOICE_RENDERER",
    "CHOICE_WIDGET",
    "ChoiceWidget",
    "HISTORY_RENDERER",
    "HISTORY_WIDGET",
    "HistoryWidget",
    "PUZZLE_ANSWER_RENDERER",
    "PUZZLE_ANSWER_WIDGET",
    "PUZZLE_SEED_RENDERER",
    "PUZZLE_SEED_WIDGET",
    "PuzzleAnswerWidget",
    "PuzzleSeedWidget",
    "ROLE_GATE_RENDERER",
    "ROLE_GATE_WIDGET",
    "RoleGateWidget",
    "SIGNAL_REFRESH",
    "WIDGET_CLASSES",
]
