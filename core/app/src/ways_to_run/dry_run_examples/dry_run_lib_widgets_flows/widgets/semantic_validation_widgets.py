from __future__ import annotations

"""
P6 semantic-validation teaching widget
======================================

This pack isolates two validation layers that are intentionally different:

platform semantic validation
    Validators attached to the current-effective micro shell. The engine runs
    them before invoking the datum lifecycle widget for a manual transition.

lifecycle functional validation
    Ordinary domain decisions implemented inside the widget handler after the
    platform has admitted the candidate fill.

The public evidence is deliberately observable:

* platform rejection:
    - no ``semantic_validation.lifecycle_observed`` datum event;
    - controller end carries ``payload.result.last_error``;
    - widget lifecycle state and re-explosion count do not advance.

* lifecycle rejection:
    - widget handler emits ``semantic_validation.lifecycle_observed``;
    - a ``datum.message`` error is emitted;
    - controller end has no platform semantic error for this datum;
    - the widget returns ``Reexplode`` and therefore consumes lifecycle budget.

Signals are commands, not micro values. A signal-only action can reach a signal
catcher while required micros are still blank because partial validation does
not enforce requiredness. A signal combined with semantically invalid fill is
still stopped by the platform before the catcher runs.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.constants import MISSING_SIGNAL_RAISE
from _thinkprogram.thinkwidgetTM.decorators import (
    signal_catcher,
    thinkwidgetTM_config,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode
from _thinkprogram._iomicrosTM.validators.number import (
    max_number_validator_spec,
    min_number_validator_spec,
)


WF_WIDGET = "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.semantic_validation_layers.v1"


def _args(fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    return dict(raw or {}) if isinstance(raw, Mapping) else {}


def _semantic_shell(prior: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Return the current-effective shell.

    The number micros carry platform validators. ``lifecycle_code`` deliberately
    has no platform validator: its equivalent semantic rule is implemented in
    the lifecycle handler so the two layers can be contrasted E2E.
    """
    shell = deepcopy(dict(prior))
    args = _args(prior)
    minimum = int(args.get("platform_minimum", 10))
    maximum = int(args.get("platform_maximum", 20))

    shell["title"] = "Platform validation versus lifecycle validation"
    shell["micros"] = [
        {
            "name": "platform_number",
            "type": "integer",
            "required": True,
            "validators": [
                min_number_validator_spec(minimum),
                max_number_validator_spec(maximum),
            ],
        },
        {
            "name": "lifecycle_code",
            "type": "text",
            "required": True,
        },
    ]
    return shell


@thinkwidgetTM_config(
    WF_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={
        "platform_minimum": {
            "type": "int",
            "required": False,
            "default": 10,
        },
        "platform_maximum": {
            "type": "int",
            "required": False,
            "default": 20,
        },
        "lifecycle_prefix": {
            "type": "str",
            "required": False,
            "default": "LIFE-",
        },
    },
    wires={},
)
class SemanticValidationLayersWidget(DatumLifecycleWidget):
    """Executable contrast between platform and in-lifecycle validation."""

    def _emit_observation(
        self,
        *,
        branch: str,
        signal_kind: str,
        changed_fills: Mapping[str, Any],
    ) -> None:
        self._emit(
            {
                "proof": {
                    "branch": str(branch),
                    "signal_kind": str(signal_kind),
                    "changed_fill_names": sorted(
                        str(name) for name in dict(changed_fills)
                    ),
                    "handler_invocation": int(
                        getattr(self, "handler_invocations", 0)
                    ),
                }
            },
            name="semantic_validation.lifecycle_observed",
        )

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats
        self.handler_invocations = 0
        self.lifecycle_rejections = 0
        self.signal_observations = 0
        self.accepted_number = None
        self.accepted_code = None

        self.message(
            "info",
            "mounted a shell whose number micro is platform-validated",
        )
        return Reexplode(
            next_fill_shell=_semantic_shell(fill_data["fill_shell"]),
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats
        changed = dict(fill_data.get("changed_fills") or {})
        self.handler_invocations = (
            int(getattr(self, "handler_invocations", 0)) + 1
        )
        self._emit_observation(
            branch="fill_handler",
            signal_kind=str(signal.get("kind") or "fill"),
            changed_fills=changed,
        )

        code = str(
            dict(fill_data.get("current_fills") or {}).get(
                "lifecycle_code"
            )
            or ""
        )
        prefix = str(
            _args(fill_data["fill_shell"]).get(
                "lifecycle_prefix",
                "LIFE-",
            )
        )

        if not code.startswith(prefix):
            self.lifecycle_rejections = (
                int(getattr(self, "lifecycle_rejections", 0)) + 1
            )
            self.message(
                "error",
                f"lifecycle_code must start with {prefix!r}",
            )
            return Reexplode(
                next_fill_shell=_semantic_shell(fill_data["fill_shell"]),
                pre_computed_fills=dict(
                    fill_data.get("current_fills") or {}
                ),
            )

        current = dict(fill_data.get("current_fills") or {})
        self.accepted_number = int(current["platform_number"])
        self.accepted_code = code
        self.message(
            "success",
            "both platform and lifecycle validation accepted the submission",
        )
        return True

    @signal_catcher("explain")
    def explain(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats
        self.handler_invocations = (
            int(getattr(self, "handler_invocations", 0)) + 1
        )
        self.signal_observations = (
            int(getattr(self, "signal_observations", 0)) + 1
        )
        self._emit_observation(
            branch="signal_catcher",
            signal_kind=str(signal.get("kind") or ""),
            changed_fills=dict(fill_data.get("changed_fills") or {}),
        )
        self.message(
            "info",
            "signal reached the widget; signals themselves are not micro values",
        )
        return Reexplode(
            next_fill_shell=_semantic_shell(fill_data["fill_shell"]),
            pre_computed_fills=dict(
                fill_data.get("current_fills") or {}
            ),
        )


__all__ = [
    "SemanticValidationLayersWidget",
    "WF_WIDGET",
]
