from __future__ import annotations

"""
authoring_funnel.b_service_ready_typed_PSMCW_authoring._program_language
============================================================================

Canonical program-language lowering and registration for Typed ThinkPrograms.
Compiles Higher P (with static D bindings and typed ports) directly into ordinary
think_program_v1, which lowers to the continuity kernel and app table.
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

LANG_TYPED_THINK_PROGRAM_V1 = "typed_think_program_v1"


def lower_typed_think_program_v1(
    program: Any,
    *,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    """Compile Higher-P with D-bindings and lower through the standard pipeline."""
    from .program import compile_strict_program

    effective_program = overlay_initial_parameter_overrides_onto_program_v1(
        program,
        initial_parameter_overrides=initial_parameter_overrides,
    )
    effective_program = deepcopy(effective_program)
    effective_program["kind"] = LANG_THINK_PROGRAM_V1

    # 1. Compile Higher-P down to ordinary think_program_v1
    lowered_p = compile_strict_program(effective_program)

    # 2. Hand off to think_program_v1 lowerer (lowers to kernel -> app_table)
    register_think_program_language_v1()
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
    provenance["lowering_chain"] = chain
    provenance["source_program_language"] = LANG_TYPED_THINK_PROGRAM_V1
    provenance["source_program"] = deepcopy(program)
    provenance["typed_think_program_v1"] = deepcopy(program)
    provenance["think_program_v1"] = lowered_p

    return ProgramLoweringBundle(
        app_table_manifest=bundle.app_table_manifest,
        provenance=provenance,
        session_surface=bundle.session_surface,
    )


def register_typed_think_program_language_v1() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()
    if not is_program_language_registered(LANG_TYPED_THINK_PROGRAM_V1):
        register_program_language(
            language=LANG_TYPED_THINK_PROGRAM_V1,
            lower=lower_typed_think_program_v1,
            description="Typed ThinkProgramTM with static D-expression bindings compiled to think_program_v1.",
        )


__all__ = [
    "LANG_TYPED_THINK_PROGRAM_V1",
    "lower_typed_think_program_v1",
    "register_typed_think_program_language_v1",
]
