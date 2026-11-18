from __future__ import annotations

"""Copy/paste template: one backend + FormreactTM-ready ThinkWidget.

Edit only the app-specific names, micro grammar, state, and domain decisions.
The structure deliberately keeps canonical backend truth separate from
presentation-facing FormreactTM opinionation.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from _thinkprogram.thinkwidgetTM.constants import MISSING_SIGNAL_RAISE
from _thinkprogram.thinkwidgetTM.decorators import thinkwidgetTM_config
from _thinkprogram.thinkwidgetTM.types import Reexplode
from ..analytics.template_thinkwidget_analytics_powered import (
    AnalyticaPoweredDatumLifecycleWidget,
    analytica_signal_catcher,
)
from ..runtime_helpers import (
    authored_widget_args_v1,
    runtime_write_row_state_v1,
    wire_rows_v1,
)
from _vial_js_interactive.formreactPY.opinionations import (
    FORMREACTTM_RUNTIME_KEY_V1,
    FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1,
    formreacttm_runtime_state_v1,
)


WIDGET_ID: str = "my_app.widget.v1"
SIGNAL_REFRESH: str = "refresh"


def _mapping(value: Any) -> Dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _micros() -> list[Dict[str, Any]]:
    """Canonical semantic input grammar. FormreactTM renders this; backend owns it."""
    return [
        {
            "name": "choice",
            "type": "select",
            "label": "Choose one",
            "required": True,
            "options": ["alpha", "beta"],
            "validators": [
                {
                    "path": (
                        "_thinkprogram._iomicrosTM.validators.choice:in_allowed"
                    ),
                    "args": {"options": ["alpha", "beta"]},
                }
            ],
        }
    ]


def _next_shell(
    prior: Mapping[str, Any],
    *,
    title: str,
) -> Dict[str, Any]:
    """Build only the current lifecycle shell; do not depend on authored args surviving."""
    source = dict(prior or {})
    return {
        "id": source.get("id"),
        "title": str(title),
        "micros": _micros(),
        "lifecycle": deepcopy(dict(source.get("lifecycle") or {})),
    }


@thinkwidgetTM_config(
    WIDGET_ID,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    args={
        # Required for FormreactTM-ready authoring. The ThinkProgram supplies it.
        FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1: {
            "type": "dict",
            "required": True,
        },
        # Ordinary backend/domain configuration remains ordinary widget args.
        "backend_policy": {
            "type": "dict",
            "required": False,
            "default": {},
        },
    },
    wires={
        # Optional explicit program-history dependency.
        "source": {
            "multiplicity": "one",
            "required": False,
        },
    },
)
class MyFormreactReadyWidget(AnalyticaPoweredDatumLifecycleWidget):
    """Local semantic machine with Analytica wired in automatically."""

    def _publish_runtime(self, *, phase: str) -> None:
        runtime: Dict[str, Any] = formreacttm_runtime_state_v1(
            # Runtime may keep or intentionally switch the registered renderer.
            js_gen_name=self.renderer_id,
            js_gen_args={
                "phase": str(phase),
                "revision": int(self.revision),
            },
            active_signals=(
                {}
                if phase == "complete"
                else {
                    SIGNAL_REFRESH: {
                        "display_channel": "refresh",
                        "label": "Refresh",
                        "info_defaults": {"source": "formreactTM"},
                    }
                }
            ),
            semantic_hints=(
                []
                if phase == "complete"
                else [
                    {
                        "micro": "choice",
                        "type": "info",
                        "hint": "Select one of the current canonical options.",
                    }
                ]
            ),
            # Presentation consequences only; canonical semantic state remains on self.
            state_values={
                "phase": str(phase),
                "revision": int(self.revision),
                "accepted_choice": self.accepted_choice,
                "has_source": bool(self.source_state),
            },
        )
        setattr(self, FORMREACTTM_RUNTIME_KEY_V1, deepcopy(runtime))
        self.emit_live_unpersisted_v1(
            "formreactTM.widget_explosion",
            {"runtime": deepcopy(runtime)},
        )

    def _reexplode(
        self,
        fill_data: Mapping[str, Any],
        *,
        values: Mapping[str, Any] | None = None,
    ) -> Reexplode:
        return Reexplode(
            next_fill_shell=_next_shell(
                fill_data["fill_shell"],
                title="My interactive widget",
            ),
            pre_computed_fills=deepcopy(dict(values or {})),
            prefill_hints={"choice": "alpha or beta"},
        )

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats

        # Mount is the continuity-capture point for authored args.
        authored: Dict[str, Any] = authored_widget_args_v1(fill_data["fill_shell"])
        panel: Dict[str, Any] = _mapping(
            authored[FORMREACTTM_WIDGET_PANEL_ARG_KEY_V1]
        )
        entry: Dict[str, Any] = _mapping(panel.get("entry"))

        self.renderer_id = str(entry["js_gen_name"])
        self.backend_policy = _mapping(authored.get("backend_policy"))

        # Optional history arrives only through the authored wire name.
        source_rows: list[Dict[str, Any]] = wire_rows_v1(
            fill_data["fill_shell"],
            "source",
        )
        self.source_state = (
            runtime_write_row_state_v1(source_rows[0])
            if source_rows
            else {}
        )

        # Durable backend/domain state.
        self.revision = 1
        self.accepted_choice: str | None = None

        self._publish_runtime(phase="editing")
        self.message("info", "widget mounted")
        return self._reexplode(fill_data)

    @analytica_signal_catcher(SIGNAL_REFRESH)
    def refresh(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats
        self.revision = int(self.revision) + 1
        self._publish_runtime(phase="editing")
        return self._reexplode(
            fill_data,
            values=_mapping(fill_data.get("current_fills")),
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats

        # Platform semantic validators on the current micros have already run.
        current: Dict[str, Any] = _mapping(fill_data.get("current_fills"))
        self.accepted_choice = str(current["choice"])
        self.revision = int(self.revision) + 1

        # Any additional app/domain acceptance logic belongs here.
        self._publish_runtime(phase="complete")
        self.message("success", "widget accepted")
        return True


WIDGET_CLASSES: tuple[
    type[AnalyticaPoweredDatumLifecycleWidget],
    ...
] = (MyFormreactReadyWidget,)


__all__ = [
    "MyFormreactReadyWidget",
    "SIGNAL_REFRESH",
    "WIDGET_CLASSES",
    "WIDGET_ID",
]
