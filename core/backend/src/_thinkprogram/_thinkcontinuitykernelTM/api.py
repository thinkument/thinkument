# think-backend/src/thinkcontinuitykernelTM/api.py

from __future__ import annotations

"""
Public Think Kernel v1 facade.

App authors should import from this module, not from underscore modules.

The stable public surface is:

    register_kernel_widget_v1(...)
    register_kernel_step_fn_v1()
    register_kernel_program_language_v1()
    register_thinking_flow_explicit_language_v1()

    validate_kernel_step_surface_v1(K)
    validate_kernel_program_v1([K1, K2, ...])

    lower_kernel_program_v1(program)
    lower_thinking_flow_explicit_v1(program)
    manifest_from_kernel_program_v1(program)

    think_kernel_step_fn_v1(...)

Constants:
    KERNEL_STEP_FN_NAME_V1
    KERNEL_PROGRAM_LANGUAGE_V1
    LANG_THINKING_FLOW_EXPLICIT_V1
"""

from ._constants import (
    KERNEL_ARGS_SURFACE_VERSION_V1,
    KERNEL_HISTORY_QUERY_SELECT_ALL_V1,
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
    KERNEL_KIND_V1,
    KERNEL_PROGRAM_LANGUAGE_V1,
    KERNEL_RESERVED_ARG_KEY_V1,
    KERNEL_STEP_FN_NAME_V1,
    LANG_THINKING_FLOW_EXPLICIT_V1,
)
from ._contracts import (
    register_kernel_widget_v1,
)
from ._history import (
    build_kernel_past_wires_for_datum_v1,
    resolve_kernel_history_queries_v1,
)
from ._multiframespec import (
    build_kernel_multiframespec_v1,
)
from ._program_language import (
    lower_kernel_program_v1,
    lower_thinking_flow_explicit_v1,
    manifest_from_kernel_program_v1,
    register_kernel_program_language_v1,
    register_thinking_flow_explicit_language_v1,
)
from ._stepfn import (
    register_kernel_step_fn_v1,
    think_kernel_step_fn_v1,
)
from ._validation import (
    validate_kernel_program_v1,
    validate_kernel_step_surface_v1,
)

__all__ = [
    "KERNEL_ARGS_SURFACE_VERSION_V1",
    "KERNEL_HISTORY_QUERY_SELECT_ALL_V1",
    "KERNEL_HISTORY_QUERY_SELECT_LATEST_V1",
    "KERNEL_KIND_V1",
    "KERNEL_PROGRAM_LANGUAGE_V1",
    "KERNEL_RESERVED_ARG_KEY_V1",
    "KERNEL_STEP_FN_NAME_V1",
    "LANG_THINKING_FLOW_EXPLICIT_V1",
    "register_kernel_widget_v1",
    "register_kernel_step_fn_v1",
    "register_kernel_program_language_v1",
    "register_thinking_flow_explicit_language_v1",
    "validate_kernel_step_surface_v1",
    "validate_kernel_program_v1",
    "manifest_from_kernel_program_v1",
    "lower_kernel_program_v1",
    "lower_thinking_flow_explicit_v1",
    "think_kernel_step_fn_v1",
    "resolve_kernel_history_queries_v1",
    "build_kernel_past_wires_for_datum_v1",
    "build_kernel_multiframespec_v1",
]