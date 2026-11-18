from __future__ import annotations

"""
thinksession._higher_lang_grammars._langs_registrations
==============================================================

Concrete program-language lowerers and default registrations.

Core registry is in:
    thinksession._higher_lang_grammars._langs_core

Dependency direction:
    engine core must not import VM language packages from this bootstrap module.

This module intentionally registers only the already-lowered App Table runtime
language. Higher/VM languages must be registered by their own packages or by an
explicit integration layer outside this core engine bootstrap.
"""

from collections.abc import Mapping
from typing import Any

from _thinkprogram._iomicrosTM.tiny_helpers import DeadJSONError, assert_dead_json
from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    is_program_language_registered,
    register_program_language,
)


def _has_initial_parameter_overrides(value: Any) -> bool:
    return value is not None and not (
        isinstance(value, Mapping)
        and not value
    )


def _lower_app_table(
    program: Any,
    *,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    if _has_initial_parameter_overrides(initial_parameter_overrides):
        raise ValueError("app_table does not support initial_parameter_overrides")

    try:
        assert_dead_json(program, path="program(app_table)")
    except DeadJSONError as e:
        raise ValueError(str(e)) from e

    return ProgramLoweringBundle(
        app_table_manifest=program,
        provenance={
            "v": 1,
            "source_program_language": "app_table",
            "source_program": program,
            "highest_manifest": program,
            "app_table_manifest": program,
            "lowering_chain": [
                {"language": "app_table", "artifact": "app_table_manifest"},
            ],
        },
        session_surface={},
    )


def ensure_default_program_languages_registered() -> None:
    """
    Register core default program languages.

    This core bootstrap registers only the engine machine-code language:
    ``app_table``.
    """

    # engine machine-code language:
    if not is_program_language_registered("app_table"):
        register_program_language(
            language="app_table",
            lower=_lower_app_table,
            description="Already-lowered App Table manifest/runtime language.",
        )


__all__ = [
    "ensure_default_program_languages_registered",
]