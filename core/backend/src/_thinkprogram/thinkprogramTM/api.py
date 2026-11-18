from __future__ import annotations

"""
Public ThinkProgramTM facade.

App authors and tests should import from this module, not from underscore
implementation modules.

Stable public surface:

    LANG_THINK_PROGRAM_V1
    THINK_PROGRAM_KIND_V1
    THINK_PROGRAM_SURFACE_VERSION_V1

    bind_think_program_symbols_v1(...)
    lower_think_program_to_kernel_program_v1(...)
    lower_think_program_v1(...)
    register_think_program_language_v1()
"""

from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
)

from ._constants import (
    LANG_THINK_PROGRAM_V1,
    THINK_PROGRAM_KIND_V1,
    THINK_PROGRAM_SURFACE_VERSION_V1,
    _ALLOWED_FLOW_ITEM_KEYS_V1,
    _ALLOWED_OVERRIDE_KEYS_V1,
    _ALLOWED_PROGRAM_INFO_KEYS_V1,
    _ALLOWED_PROGRAM_KEYS_V1,
    _ALLOWED_TOP_LEVEL_KEYS_V1,
    _ALLOWED_WIDGET_DEF_KEYS_V1,
    _DEFAULT_KERNEL_FLAGS_V1,
    _DEFAULT_LIFECYCLE_V1,
)
from ._helpers import (
    assert_dead_json,
    assert_list_of_strings,
    assert_mapping_or_empty,
    assert_no_key_recursively,
    deep_merge,
    deepcopy_json,
    kernel_arg_type_ok_v1,
    reject_unknown_keys_v1,
    require_mapping,
    require_nonempty_str,
)
from ._lower_to_kernel import (
    lower_think_program_to_kernel_program_v1,
)
from ._program_language import (
    lower_think_program_v1,
    register_think_program_language_v1,
)
from ._symbols import (
    bind_think_program_symbols_v1,
    effective_symbols_v1,
    lookup_symbol_path_v1,
    normalize_initial_parameter_overrides_v1,
    overlay_initial_parameter_overrides_onto_program_v1,
    resolve_symbols_in_run_v1,
)
from ._validation import (
    history_spec_v1,
    kernel_widget_contract_from_repr_v1,
    validate_args_against_contract_v1,
    validate_wire_names_against_contract_v1,
)
from ._wires import (
    AppearanceV1,
    safe_alias_v1,
    source_logical_widget_ids_v1,
    unique_alias_v1,
)

__all__ = [
    "LANG_THINK_PROGRAM_V1",
    "THINK_PROGRAM_KIND_V1",
    "THINK_PROGRAM_SURFACE_VERSION_V1",
    "PUPPETEERING_OVERLAY_KEY_V1",
    "PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1",
    "PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1",
    "_ALLOWED_TOP_LEVEL_KEYS_V1",
    "_ALLOWED_PROGRAM_KEYS_V1",
    "_ALLOWED_PROGRAM_INFO_KEYS_V1",
    "_ALLOWED_WIDGET_DEF_KEYS_V1",
    "_ALLOWED_FLOW_ITEM_KEYS_V1",
    "_ALLOWED_OVERRIDE_KEYS_V1",
    "_DEFAULT_KERNEL_FLAGS_V1",
    "_DEFAULT_LIFECYCLE_V1",
    "deepcopy_json",
    "assert_dead_json",
    "require_mapping",
    "require_nonempty_str",
    "reject_unknown_keys_v1",
    "deep_merge",
    "assert_no_key_recursively",
    "kernel_arg_type_ok_v1",
    "assert_list_of_strings",
    "assert_mapping_or_empty",
    "effective_symbols_v1",
    "lookup_symbol_path_v1",
    "resolve_symbols_in_run_v1",
    "normalize_initial_parameter_overrides_v1",
    "overlay_initial_parameter_overrides_onto_program_v1",
    "bind_think_program_symbols_v1",
    "kernel_widget_contract_from_repr_v1",
    "validate_args_against_contract_v1",
    "validate_wire_names_against_contract_v1",
    "history_spec_v1",
    "AppearanceV1",
    "source_logical_widget_ids_v1",
    "safe_alias_v1",
    "unique_alias_v1",
    "lower_think_program_to_kernel_program_v1",
    "lower_think_program_v1",
    "register_think_program_language_v1",
]
