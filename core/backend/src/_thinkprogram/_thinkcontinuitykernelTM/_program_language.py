# think-backend/src/thinkcontinuitykernelTM/_program_language.py

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict, List

from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    register_program_language,
)
from _thinkengine._parsing._higher_lang_grammars._langs_registrations import (
    ensure_default_program_languages_registered,
)

from ._constants import (
    KERNEL_PROGRAM_LANGUAGE_V1,
    KERNEL_STEP_FN_NAME_V1,
    LANG_THINKING_FLOW_EXPLICIT_V1,
)
from ._validation import validate_kernel_program_v1


def manifest_from_kernel_program_v1(
    program: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": str(k["step"]["id"]),
            "step_fn": KERNEL_STEP_FN_NAME_V1,
            "fn_args": {"kernel": dict(k)},
        }
        for k in program
    ]


def lower_kernel_program_v1(program: Any) -> ProgramLoweringBundle:
    validated = validate_kernel_program_v1(program)
    manifest = manifest_from_kernel_program_v1(validated)

    return ProgramLoweringBundle(
        app_table_manifest=manifest,
        provenance={
            "v": 1,
            "source_program_language": KERNEL_PROGRAM_LANGUAGE_V1,
            "source_program": validated,
            "app_table_manifest": manifest,
            "lowering_chain": [
                {
                    "language": KERNEL_PROGRAM_LANGUAGE_V1,
                    "artifact": "app_table_manifest",
                },
            ],
        },
        session_surface={},
    )


def register_kernel_program_language_v1() -> None:
    ensure_default_program_languages_registered()
    register_program_language(
        language=KERNEL_PROGRAM_LANGUAGE_V1,
        lower=lower_kernel_program_v1,
        description="Think Kernel v1 list[K] higher program lowering.",
    )


def lower_thinking_flow_explicit_v1(program: Any) -> ProgramLoweringBundle:
    """
    Higher-language lowerer for:

        [K1, K2, ..., KN]

    Design law:
      - validate once;
      - lower deterministically to ordinary app-table rows;
      - never place a ProgramLoweringBundle inside app_table_manifest;
      - do not mutate registries during lowering;
      - runtime executes only the universal kernel step fn.
    """
    validated = validate_kernel_program_v1(program)
    app_table_manifest = manifest_from_kernel_program_v1(validated)

    json.dumps(
        {
            "program": validated,
            "app_table_manifest": app_table_manifest,
        },
        sort_keys=True,
    )

    return ProgramLoweringBundle(
        app_table_manifest=app_table_manifest,
        provenance={
            "v": 1,
            "source_program_language": LANG_THINKING_FLOW_EXPLICIT_V1,
            "source_program": validated,
            "highest_manifest": validated,
            "app_table_manifest": app_table_manifest,
            "lowering_chain": [
                {
                    "language": LANG_THINKING_FLOW_EXPLICIT_V1,
                    "artifact": "kernel_program_v1",
                },
                {
                    "language": "app_table",
                    "artifact": "app_table_manifest",
                },
            ],
        },
        session_surface={
            "v": 1,
            "source_program_language": LANG_THINKING_FLOW_EXPLICIT_V1,
        },
    )


def register_thinking_flow_explicit_language_v1() -> None:
    """
    Integration registration.

    Core default language registration should remain minimal:
        app_table only.

    This higher language is intentionally registered by the integration surface
    that owns the kernel semantics.
    """
    ensure_default_program_languages_registered()
    register_program_language(
        language=LANG_THINKING_FLOW_EXPLICIT_V1,
        lower=lower_thinking_flow_explicit_v1,
        description=(
            "Explicit Thinkument thinking-flow language: "
            "list[K] lowered deterministically to App Table via think.kernel.v1."
        ),
    )