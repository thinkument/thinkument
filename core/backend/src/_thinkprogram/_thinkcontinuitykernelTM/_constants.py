# think-backend/src/thinkcontinuitykernelTM/_constants.py

from __future__ import annotations

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
)

KERNEL_STEP_FN_NAME_V1 = "think.kernel.v1"

KERNEL_PROGRAM_LANGUAGE_V1 = "think_kernel_program_v1"
LANG_THINKING_FLOW_EXPLICIT_V1 = "thinking_flow_explicit"

KERNEL_RESERVED_ARG_KEY_V1 = "__kernel"

KERNEL_HISTORY_QUERY_SELECT_LATEST_V1 = "latest"
KERNEL_HISTORY_QUERY_SELECT_ALL_V1 = "all"

KERNEL_KIND_V1 = "think_kernel_step_v1"
KERNEL_ARGS_SURFACE_VERSION_V1 = "v1"

SUPPORTED_KERNEL_ARG_TYPES_V1 = {
    "json",
    "str",
    "int",
    "float",
    "bool",
    "dict",
    "list",
    "list[str]",
    "list[int]",
}

SUPPORTED_KERNEL_HISTORY_SELECTORS_V1 = {
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
    KERNEL_HISTORY_QUERY_SELECT_ALL_V1,
}

SUPPORTED_KERNEL_HISTORY_WRITE_KINDS_V1 = {
    WRITE_KIND_DATUM_LIFECYCLE,
}