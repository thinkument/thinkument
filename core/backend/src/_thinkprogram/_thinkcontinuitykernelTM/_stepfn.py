# think-backend/src/thinkcontinuitykernelTM/_stepfn.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)

from ._constants import KERNEL_STEP_FN_NAME_V1
from ._history import resolve_kernel_history_queries_v1
from ._multiframespec import build_kernel_multiframespec_v1
from ._validation import validate_kernel_step_surface_v1


def think_kernel_step_fn_v1(
    state: Mapping[str, Any],
    *,
    kernel: Mapping[str, Any],
) -> Dict[str, Any]:
    k = validate_kernel_step_surface_v1(kernel)
    resolved = resolve_kernel_history_queries_v1(state, k)
    fs = build_kernel_multiframespec_v1(k, resolved)
    return {
        "multiframespec": fs,
        "kernel_last_step_id": str(k["step"]["id"]),
    }


def register_kernel_step_fn_v1() -> None:
    StepFnregistry.register(
        name=KERNEL_STEP_FN_NAME_V1,
        fn=think_kernel_step_fn_v1,
        required_args={"kernel"},
        optional_args=set(),
        overwrite=True,
    )