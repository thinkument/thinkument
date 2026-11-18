from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .specs import (
    ArgsValidator,
    FunkTMRequest,
    FunkTMResult,
    RegisteredFillerFunktion,
    VersionFn,
)


_REGISTRY: Dict[str, RegisteredFillerFunktion] = {}


def register_chainreactiontm_version(
    *,
    name: str,
    run: VersionFn,
    validate_args: Optional[ArgsValidator] = None,
    replace: bool = False,
) -> RegisteredFillerFunktion:
    version = str(name or "").strip()
    if not version:
        raise ValueError("chainreactionTM version name must be non-empty")

    if version in _REGISTRY and not replace:
        raise KeyError(f"chainreactionTM version already registered: {version!r}")

    def _default_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(raw or {})

    spec = RegisteredFillerFunktion(
        name=version,
        run=run,
        validate_args=validate_args or _default_args,
    )
    _REGISTRY[version] = spec
    return spec


def get_chainreactiontm_version(name: str) -> RegisteredFillerFunktion:
    version = str(name or "").strip()
    if version not in _REGISTRY:
        raise KeyError(f"unknown chainreactionTM version: {version!r}")
    return _REGISTRY[version]


def registered_chainreactiontm_versions() -> list[str]:
    return sorted(_REGISTRY)


def clear_chainreactiontm_versions_for_tests() -> None:
    _REGISTRY.clear()