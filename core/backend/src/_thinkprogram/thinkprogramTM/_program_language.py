from __future__ import annotations

from typing import Any

from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    lower_program_to_app_table_bundle,
    register_program_language,
)

from _thinkprogram._thinkcontinuitykernelTM.api import (
    LANG_THINKING_FLOW_EXPLICIT_V1,
    register_thinking_flow_explicit_language_v1,
)

from ._constants import LANG_THINK_PROGRAM_V1
from ._helpers import deepcopy_json
from ._lower_to_kernel import lower_think_program_to_kernel_program_v1
from ._symbols import (
    bind_think_program_symbols_v1,
    overlay_initial_parameter_overrides_onto_program_v1,
)


def lower_think_program_v1(
    program: Any,
    *,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    effective_program = overlay_initial_parameter_overrides_onto_program_v1(
        program,
        initial_parameter_overrides=initial_parameter_overrides,
    )
    kernel_program = lower_think_program_to_kernel_program_v1(effective_program)

    register_thinking_flow_explicit_language_v1()
    kernel_bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        program=kernel_program,
    )

    resolved_run = bind_think_program_symbols_v1(effective_program)
    run_config = dict(dict(resolved_run).get("config") or {})

    return ProgramLoweringBundle(
        app_table_manifest=kernel_bundle.app_table_manifest,
        provenance={
            "v": 1,
            "source_program_language": LANG_THINK_PROGRAM_V1,
            "source_program": deepcopy_json(program),
            "initial_parameter_overrides": deepcopy_json(
                initial_parameter_overrides or {}
            ),
            "effective_source_program": deepcopy_json(effective_program),
            "resolved_run": resolved_run,
            "explicit_kernel_program": kernel_program,
            "app_table_manifest": kernel_bundle.app_table_manifest,
            "lowering_chain": [
                {
                    "language": LANG_THINK_PROGRAM_V1,
                    "artifact": "think_kernel_program_v1",
                },
                {
                    "language": LANG_THINKING_FLOW_EXPLICIT_V1,
                    "artifact": "app_table_manifest",
                },
            ],
        },
        session_surface={
            "v": 1,
            "source_program_language": LANG_THINK_PROGRAM_V1,
            "run_config": run_config,
        },
    )


def register_think_program_language_v1() -> None:
    register_thinking_flow_explicit_language_v1()
    register_program_language(
        language=LANG_THINK_PROGRAM_V1,
        lower=lower_think_program_v1,
        description="ThinkProgramTM ergonomic app-flow JSON lowering to think.kernel.v1.",
    )