"""
authoring_funneling
===================
The canonical authoring funnel engine for ThinkWidgets and ThinkPrograms.

Subpackages:
  - a_typed_PSMCW_authoring: Typed ports, strict state, and strict P compiler.
  - b_typed_JSON_widget_declaration: Pure JSON declarative widget engine.
  - examples: Reference packs and shared widgets (metal, crystal).
"""

from epsilinesTM_serveragnostic.subapps.base import ServiceReadyWidget
from epsilinesTM_serveragnostic.subapps.analytics import (
    AnalyticaPoweredDatumLifecycleWidget,
    analytica_signal_catcher,
)
from epsilinesTM_serveragnostic.subapps.economics import EconomicsWidgetMixin

_LAYER_A_NAMES = {
    "ServiceReadyWidget",
    "AnalyticaPoweredDatumLifecycleWidget",
    "EconomicsWidgetMixin",
}

_LAYER_B_NAMES = {
    "StrictServiceWidget",
    "strict_widget",
    "compile_strict_program",
    "compile_strict_tape",
    "TypedAuthoringProfile",
    "AuthoringError",
    "D",
    "Str",
    "Int",
    "Float",
    "Bool",
    "Dict",
    "List",
    "Map",
    "Nullable",
    "analytica_signal_catcher",
    "LANG_TYPED_THINK_PROGRAM_V1",
    "register_typed_think_program_language_v1",
}

_LAYER_C_NAMES = {
    "create_gateway_vendor_binding",
    "JsonDefinedLibraryWidget",
    "prepare_json_widget_v1",
    "register_prepared_json_widget_v1",
    "PreparedJsonWidgetV1",
    "THINKUMENT_GLOBAL_VOCAB",
    "WidgetEconomicFlowInterceptor",
    "VendorBinding",
    "normalize_manifest_v1",
    "validate_manifest_grammar_v1",
}

_LAYER_UNIFIED_NAMES = {
    "LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1",
    "lower_unified_typed_jsonic_think_program_v1",
    "register_unified_typed_jsonic_think_program_language_v1",
    "compile_unified_typed_jsonic_program",
    "InlineWidgetExtractionResult",
    "compute_inline_widget_synthetic_id",
    "extract_inline_widgets_v1",
}

_LAYER_MODULE_NAMES = {
    "LANG_THINK_MODULE_V1",
    "MAX_IMPORT_DEPTH",
    "ModuleCatalogRegistry",
    "SMPocketStitchingPolicy",
    "SMPocketStitchingRegistry",
    "compute_module_fingerprint",
    "normalize_think_module_v1",
    "parse_module_reference",
    "stitch_program_modules",
    "validate_think_module_v1",
}

def __getattr__(name: str):
    if name in _LAYER_MODULE_NAMES:
        from . import d_module_composition_and_stitching as _m
        return getattr(_m, name)
    if name in _LAYER_UNIFIED_NAMES:
        from . import c_one_JSONic_programming_language_widgets_inline_or_published_imported as _u
        return getattr(_u, name)
    if name in _LAYER_C_NAMES:
        from . import b_typed_JSON_widget_declaration as _c
        return getattr(_c, name)
    if name in _LAYER_B_NAMES:
        from . import a_typed_PSMCW_authoring as _b
        return getattr(_b, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = sorted(_LAYER_A_NAMES | _LAYER_B_NAMES | _LAYER_C_NAMES | _LAYER_UNIFIED_NAMES | _LAYER_MODULE_NAMES)
