from __future__ import annotations

"""
thinksession._higher_lang_grammars._langs_core
======================================

Program-language lowering registry for session creation.

This module is **pure core**:
- Owns the registry + dispatch (`register`, `list`, `lower`).
- Is intentionally unaware of *which* languages exist (no concrete lowerers here).
- Is intentionally unaware of validation rules (e.g. dead-json) or compilers/SDKs.

Concrete languages (and any validation / compiler bootstraps) live in:
    thinksession._higher_lang_grammars._langs_registrations
"""

from dataclasses import dataclass, field
import inspect
from typing import Any, Callable, Dict, Mapping, Optional, Sequence


def _norm_lang(lang: str) -> str:
    """
    Normalize language keys for stable lookup.

    Core does *not* know concrete languages, but it provides a single normalization
    policy so callers/registrations can be consistent.
    """
    s = str(lang or "").strip().lower()
    s = s.replace("-", "_").replace(" ", "_")
    return s


LowererFn = Callable[..., Any]


@dataclass(frozen=True)
class ProgramLowerer:
    """
    A registered lowering function for a specific program language.

    - `language` is the canonical normalized key (e.g. "app_table").
    - `lower(program, initial_parameter_overrides=...)` returns an App Table
      manifest or a ProgramLoweringBundle.
    """

    language: str
    lower: LowererFn
    description: str = ""


@dataclass(frozen=True)
class ProgramLoweringBundle:
    """
    Canonical lowering result.

    app_table_manifest:
        Final manifest consumed by the App Table runtime.

    provenance:
        Dead-JSON-ish metadata describing the lowering chain. This is intended
        to be copied into session_metadata so downstream UI/chrome/static
        rendering can inspect:
          - original source program
          - intermediate manifests
          - final lowered app table manifest
          - compiler artifacts

    session_surface:
        Optional dead-json session defaults carried by the source language.
        This is the clean seam for "dead manifest contains full session config"
        languages. The AbstractSessionAPI may merge these into explicit
        create_VM_session_from_program(...) arguments.
    """

    app_table_manifest: Any
    provenance: Dict[str, Any]
    session_surface: Dict[str, Any] = field(default_factory=dict)


_LOWERERS: Dict[str, ProgramLowerer] = {}


def register_program_language(
    *,
    language: str,
    lower: LowererFn,
    description: str = "",
) -> None:
    lang = _norm_lang(language)
    if not lang:
        raise ValueError("language cannot be empty")
    if not callable(lower):
        raise TypeError("lower must be callable")

    _LOWERERS[lang] = ProgramLowerer(
        language=lang,
        lower=lower,
        description=str(description or ""),
    )


def is_program_language_registered(language: str) -> bool:
    return _norm_lang(language) in _LOWERERS


def get_program_language(language: str) -> Optional[ProgramLowerer]:
    return _LOWERERS.get(_norm_lang(language))


def list_program_languages() -> Dict[str, str]:
    return {
        key: lowerer.description
        for key, lowerer in sorted(_LOWERERS.items(), key=lambda kv: kv[0])
    }


def _has_initial_parameter_overrides(value: Any) -> bool:
    return value is not None and not (
        isinstance(value, Mapping)
        and not value
    )


def _lowerer_accepts_initial_parameter_overrides(fn: LowererFn) -> bool:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return False

    if "initial_parameter_overrides" in signature.parameters:
        return True

    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True

    return False


def _invoke_lowerer(
    *,
    lowerer: ProgramLowerer,
    program: Any,
    initial_parameter_overrides: Any = None,
) -> Any:
    if _lowerer_accepts_initial_parameter_overrides(lowerer.lower):
        return lowerer.lower(
            program,
            initial_parameter_overrides=initial_parameter_overrides,
        )

    if _has_initial_parameter_overrides(initial_parameter_overrides):
        raise ValueError(
            f"program_language {lowerer.language!r} does not support "
            "initial_parameter_overrides"
        )

    return lowerer.lower(program)


def lower_program_to_app_table_manifest(
    *,
    program_language: str,
    program: Any,
    initial_parameter_overrides: Any = None,
) -> Any:
    lang = _norm_lang(program_language)
    lowerer = _LOWERERS.get(lang)
    if lowerer is None:
        known = ", ".join(sorted(_LOWERERS.keys()))
        raise ValueError(f"unknown program_language {program_language!r}. Known: {known}")

    lowered = _invoke_lowerer(
        lowerer=lowerer,
        program=program,
        initial_parameter_overrides=initial_parameter_overrides,
    )
    if isinstance(lowered, ProgramLoweringBundle):
        return lowered.app_table_manifest
    return lowered


def lower_program_to_app_table_bundle(
    *,
    program_language: str,
    program: Any,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    lang = _norm_lang(program_language)
    lowerer = _LOWERERS.get(lang)
    if lowerer is None:
        known = ", ".join(sorted(_LOWERERS.keys()))
        raise ValueError(f"unknown program_language {program_language!r}. Known: {known}")

    lowered = _invoke_lowerer(
        lowerer=lowerer,
        program=program,
        initial_parameter_overrides=initial_parameter_overrides,
    )
    if isinstance(lowered, ProgramLoweringBundle):
        return lowered

    return ProgramLoweringBundle(
        app_table_manifest=lowered,
        provenance={
            "v": 1,
            "source_program_language": lang,
            "source_program": program,
            "app_table_manifest": lowered,
            "lowering_chain": [
                {"language": lang, "artifact": "app_table_manifest"},
            ],
        },
        session_surface={},
    )