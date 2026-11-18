from __future__ import annotations

"""Runtime registration owned by the Packito app pack."""

from typing import Any, Dict

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

from .funks import (
    PUZZLE_SEED_FUNK_V1,
    PUZZLE_SOLVER_FUNK_V1,
    register_packito_funked_fillers_v1,
)
from .widgets import (
    BOARD_WIDGET,
    CHOICE_WIDGET,
    HISTORY_WIDGET,
    PUZZLE_ANSWER_WIDGET,
    PUZZLE_SEED_WIDGET,
    ROLE_GATE_WIDGET,
    WIDGET_CLASSES,
)


APP_PACK_ID = "packito"
PACKITO_WIDGET_CLASSES = WIDGET_CLASSES
PACKITO_WIDGET_IDS = (
    CHOICE_WIDGET,
    BOARD_WIDGET,
    HISTORY_WIDGET,
    ROLE_GATE_WIDGET,
    PUZZLE_SEED_WIDGET,
    PUZZLE_ANSWER_WIDGET,
)
PACKITO_FUNK_IDS = (
    PUZZLE_SEED_FUNK_V1,
    PUZZLE_SOLVER_FUNK_V1,
)


def register_app_pack_v1() -> Dict[str, Any]:
    """Register every Python-side runtime dependency owned by Packito.

    The outer receipt deliberately carries the same ``app_pack`` identity used
    by the catalog/runtime activator. Detailed kernel receipts remain nested so
    activation is both machine-identifiable and diagnostically rich.
    """

    register_packito_funked_fillers_v1()

    widget_receipts: list[Dict[str, Any]] = []
    for widget_cls in PACKITO_WIDGET_CLASSES:
        receipt = pull_thinkwidget_class_into_kernel_v1(
            widget_cls,
            overwrite=True,
        )
        if receipt.get("ok") is not True:
            raise AssertionError(
                "failed to register Packito widget "
                f"{widget_cls.__name__}: {receipt!r}"
            )
        widget_receipts.append(dict(receipt))

    kernel_receipt = register_kernel_step_fn_v1()
    explicit_language_receipt = register_thinking_flow_explicit_language_v1()
    think_program_receipt = register_think_program_language_v1()

    return {
        "kind": "app_pack_mould_app_pack_registration_receipt_v1",
        "app_pack": APP_PACK_ID,
        "ok": True,
        "widgets": list(PACKITO_WIDGET_IDS),
        "funk_fillers": list(PACKITO_FUNK_IDS),
        "runtime_registration": {
            "widgets": widget_receipts,
            "kernel": kernel_receipt,
            "explicit_flow_language": explicit_language_receipt,
            "think_program_language": think_program_receipt,
        },
    }


__all__ = [
    "APP_PACK_ID",
    "PACKITO_FUNK_IDS",
    "PACKITO_WIDGET_CLASSES",
    "PACKITO_WIDGET_IDS",
    "register_app_pack_v1",
]
