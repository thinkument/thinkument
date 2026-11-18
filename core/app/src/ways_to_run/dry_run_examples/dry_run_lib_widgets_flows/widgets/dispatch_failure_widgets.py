from __future__ import annotations

"""
P7 dispatch-failure teaching widget.

The widget is deliberately ordinary on mount and on accepted fill, but exposes
two signal catchers:

touch
    Reexplodes successfully. This is used to advance the datum's write-conflict
    frontier without changing scope.

raise_runtime
    Raises RuntimeError from inside datum lifecycle execution. Because the
    controller start has already been recorded, the controller must convert the
    exception into one matching systematic-error end packet.

The widget emits no event before raising. Therefore an exact empty informative
middle proves that the only canonical packets for the failed dispatch are the
controller start and controller system-error end.
"""

from copy import deepcopy
from typing import Any, Mapping

from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.constants import MISSING_SIGNAL_RAISE
from _thinkprogram.thinkwidgetTM.decorators import (
    signal_catcher,
    thinkwidgetTM_config,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode


WG_WIDGET = "ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.dispatch_failure_probe.v1"


def _shell(prior: Mapping[str, Any]) -> dict[str, Any]:
    shell = deepcopy(dict(prior))
    shell["title"] = "Dispatch failure boundary probe"
    shell["micros"] = [
        {
            "name": "acknowledgement",
            "type": "text",
            "required": True,
        }
    ]
    return shell


@thinkwidgetTM_config(
    WG_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_RAISE,
    enforce_no_premount_shell=True,
    args={},
    wires={},
)
class DispatchFailureProbeWidget(DatumLifecycleWidget):
    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats
        self.touch_count = 0
        self.accepted_acknowledgement = None
        return Reexplode(
            next_fill_shell=_shell(fill_data["fill_shell"]),
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
        del signal, position, limits, stats
        current = dict(fill_data.get("current_fills") or {})
        acknowledgement = str(
            current.get("acknowledgement") or ""
        ).strip()
        if not acknowledgement:
            self.message("error", "acknowledgement is required")
            return Reexplode(
                next_fill_shell=_shell(fill_data["fill_shell"]),
                pre_computed_fills=current,
            )

        self.accepted_acknowledgement = acknowledgement
        self.message("success", "dispatch failure boundary understood")
        return True

    @signal_catcher("touch")
    def touch(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats
        self.touch_count = int(getattr(self, "touch_count", 0)) + 1
        self.message("info", f"touch accepted: {self.touch_count}")
        return Reexplode(
            next_fill_shell=_shell(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data.get("current_fills") or {}),
        )

    @signal_catcher("raise_runtime")
    def raise_runtime(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, fill_data, limits, stats
        raise RuntimeError(
            "intentional datum lifecycle failure after controller start"
        )


__all__ = [
    "DispatchFailureProbeWidget",
    "WG_WIDGET",
]
