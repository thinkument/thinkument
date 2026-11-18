from __future__ import annotations

"""
authoring_funneling.c_one_JSONic_programming_language_widgets_inline_or_published_imported._program_language
=============================================================================================================

Canonical program-language lowering and registration for Unified Typed JSONic ThinkPrograms.
Extracts inline JSONic widgets, synthesizes content-addressed runtime classes,
compiles static D-expression bindings, and lowers through think_program_v1 to the
kernel and app table.
"""

from copy import deepcopy
from typing import Any

from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    is_program_language_registered,
    lower_program_to_app_table_bundle,
    register_program_language,
)
from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    overlay_initial_parameter_overrides_onto_program_v1,
    register_think_program_language_v1,
)
from ..a_typed_PSMCW_authoring._program_language import (
    LANG_TYPED_THINK_PROGRAM_V1,
    register_typed_think_program_language_v1,
)


LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1 = "unified_typed_jsonic_think_program_v1"


def lower_unified_typed_jsonic_think_program_v1(
    program: Any,
    *,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    """Compile Unified JSONic P with inline/published widgets and lower to App Table."""
    from .compiler import compile_unified_typed_jsonic_program

    effective_program = overlay_initial_parameter_overrides_onto_program_v1(
        program,
        initial_parameter_overrides=initial_parameter_overrides,
    )
    effective_program = deepcopy(effective_program)
    effective_program["kind"] = LANG_THINK_PROGRAM_V1

    # 1. Compile inline widgets and D-bindings down to ordinary think_program_v1
    lowered_p, extraction = compile_unified_typed_jsonic_program(
        effective_program,
        register_in_kernel=True,
    )

    # 2. Hand off to think_program_v1 lowerer (lowers to kernel -> app_table)
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()
    register_typed_think_program_language_v1()

    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINK_PROGRAM_V1,
        program=lowered_p,
        initial_parameter_overrides=initial_parameter_overrides,
    )

    # 3. Augment lowering chain provenance
    provenance = dict(bundle.provenance or {})
    chain = list(provenance.get("lowering_chain") or [])
    chain.insert(0, {
        "language": LANG_TYPED_THINK_PROGRAM_V1,
        "artifact": LANG_THINK_PROGRAM_V1,
    })
    chain.insert(0, {
        "language": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "artifact": LANG_TYPED_THINK_PROGRAM_V1,
    })
    provenance["lowering_chain"] = chain
    provenance["source_program_language"] = LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1
    provenance["source_program"] = deepcopy(program)
    provenance["unified_typed_jsonic_think_program_v1"] = deepcopy(program)
    provenance["inline_widgets"] = extraction.inline_metadata
    provenance["think_program_v1"] = lowered_p

    return ProgramLoweringBundle(
        app_table_manifest=bundle.app_table_manifest,
        provenance=provenance,
        session_surface=bundle.session_surface,
    )


def register_unified_typed_jsonic_think_program_language_v1() -> None:
    """Register unified_typed_jsonic_think_program_v1 into the runtime parser registry."""
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()
    register_typed_think_program_language_v1()

    if not is_program_language_registered(LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1):
        register_program_language(
            language=LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
            lower=lower_unified_typed_jsonic_think_program_v1,
            description="Unified Typed JSONic ThinkProgram with inline or published JSONic widgets compiled to think_program_v1.",
        )


__all__ = [
    "LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1",
    "lower_unified_typed_jsonic_think_program_v1",
    "register_unified_typed_jsonic_think_program_language_v1",
]
