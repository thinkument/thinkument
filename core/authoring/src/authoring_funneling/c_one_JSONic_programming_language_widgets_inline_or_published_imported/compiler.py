from __future__ import annotations

"""
authoring_funneling.c_one_JSONic_programming_language_widgets_inline_or_published_imported.compiler
====================================================================================================

Compiles a unified program containing inline and/or published JSONic widgets
into a strictly validated Level 2 Typed ThinkProgram.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from ..a_typed_PSMCW_authoring.program import compile_strict_program
from ..b_typed_JSON_widget_declaration.factory import (
    PreparedJsonWidgetV1,
    register_prepared_json_widget_v1,
)
from ..d_module_composition_and_stitching.stitcher import stitch_program_modules
from .extractor import InlineWidgetExtractionResult, extract_inline_widgets_v1


def compile_unified_typed_jsonic_program(
    program: Mapping[str, Any],
    *,
    prepared_json_widgets: Optional[Sequence[PreparedJsonWidgetV1]] = None,
    register_in_kernel: bool = True,
    vocab: Optional[Any] = None,
    vendor_bindings: Optional[Any] = None,
    catalog: Optional[Any] = None,
) -> Tuple[Dict[str, Any], InlineWidgetExtractionResult]:
    """Compile a unified program manifest with inline or published widgets.

    Steps performed:
    1. Stitches and lowers all imported (P x C) modules into flat steps/widgets.
    2. Extracts inline JSONic widget manifests via `extract_inline_widgets_v1`.
    3. Compiles in-memory classes for each unique manifest and generates
       content-addressed runtime IDs (`synthetic_inline_{sha256[:16]}`).
    4. Optionally registers prepared classes into the process continuity kernel.
    5. Combines extracted artifacts with any caller-supplied `prepared_json_widgets`.
    6. Hands off the rewritten program to `compile_strict_program`, which performs
       full static D-expression binding compilation, port schema verification, and
       wire typing symmetry checking.

    Returns:
        A tuple of (compiled_program_dict, extraction_result).
    """
    stitched_p, _ = stitch_program_modules(program, catalog=catalog)

    extraction = extract_inline_widgets_v1(
        stitched_p,
        register_in_kernel=register_in_kernel,
        vocab=vocab,
        vendor_bindings=vendor_bindings,
    )

    combined_artifacts: List[PreparedJsonWidgetV1] = list(extraction.prepared_artifacts)
    if prepared_json_widgets is not None:
        combined_artifacts.extend(prepared_json_widgets)

    if register_in_kernel:
        for artifact in combined_artifacts:
            register_prepared_json_widget_v1(artifact)

    program_for_strict = dict(extraction.program)
    program_for_strict["kind"] = LANG_THINK_PROGRAM_V1
    program_for_strict.setdefault("surface_version", "v1")

    compiled_p = compile_strict_program(
        program_for_strict,
        prepared_json_widgets=combined_artifacts,
    )

    return compiled_p, extraction


__all__ = [
    "compile_unified_typed_jsonic_program",
]
