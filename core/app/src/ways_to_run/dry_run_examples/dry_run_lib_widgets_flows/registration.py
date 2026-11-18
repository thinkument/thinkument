from __future__ import annotations

"""Runtime registration owned by the ``dry_run_lib_widgets_flows`` app pack."""

from copy import deepcopy
from dataclasses import replace
from typing import Any, Dict

import _thinkprogram._iomicrosTM.table_micros  # noqa: F401
from _thinkprogram._iomicrosTM.table_micros import MICRO_TYPES, ValidatorPolicy
from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    register_think_program_language_v1,
)

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.funks import (
    register_program12_funked_fillers_v1,
)

from .widgets.base_widgets import dry_run_lib_widgets_flows_WIDGET_CLASSES
from .widgets.dispatch_failure_widgets import DispatchFailureProbeWidget
from .widgets.funked_fill_widgets import PROGRAM12_WIDGET_CLASSES
from .widgets.semantic_validation_widgets import SemanticValidationLayersWidget



def register_dry_run_lib_widgets_flows_v1() -> Dict[str, Any]:
    """Register every class/language dependency required by the pack."""
    register_program12_funked_fillers_v1()


    widget_receipts = []
    for widget_cls in (
        *dry_run_lib_widgets_flows_WIDGET_CLASSES,
        SemanticValidationLayersWidget,
        DispatchFailureProbeWidget,
        *PROGRAM12_WIDGET_CLASSES,
    ):
        receipt = pull_thinkwidget_class_into_kernel_v1(
            widget_cls,
            overwrite=True,
        )
        if receipt.get("ok") is not True:
            raise AssertionError(
                f"failed to register widget {widget_cls.__name__}: {receipt!r}"
            )
        widget_receipts.append(dict(receipt))

    kernel_receipt = register_kernel_step_fn_v1()
    explicit_language_receipt = register_thinking_flow_explicit_language_v1()
    think_program_receipt = register_think_program_language_v1()

    return {
        "kind": "dry_run_lib_widgets_flows_registration_receipt_v1",
        "ok": True,
        "widgets": widget_receipts,
        "kernel": kernel_receipt,
        "explicit_flow_language": explicit_language_receipt,
        "think_program_language": think_program_receipt,
    }


__all__ = ["register_dry_run_lib_widgets_flows_v1"]