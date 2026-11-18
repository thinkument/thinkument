from __future__ import annotations

"""
Session args metadata surface
=============================

Canonical SessionArgs dataclass plus metadata coercion, validation, defaults,
merge behavior, and app-owned metadata pocket extension.

This module orchestrates the orthogonal core surfaces:
  - __sesh_meta_rolebasedRWmodulatorTM_config_surface.py
  - __sesh_meta_session_storage_caps_surface.py

It also publishes the dynamic session metadata pocket registry. Apps may call
SessionMetadataSurfaceRegistry.register_pocket(...) once at startup to add
verified app-owned top-level metadata pockets without mutating core keys.

Core law
--------

The engine-owned metadata keys remain stable:

    roles
    role_mismatch_policy
    manual_io
    session_storage

App-owned keys are optional top-level pockets registered by name:

    grading
    workflow
    experiment
    my_app

Registered pockets are declarative JSON-safe schemas. They may describe app
metadata shape, examples, defaults, and laws. They may not contain live callables
or executable behavior.

Forever quick prototyping law 
--------------

Unknown/unregistered app metadata keys remain pass-through during full metadata
coercion so existing apps stay seamless.

Partial update law
------------------

Partial updates are stricter than full coercion. They may update core keys and
registered pocket keys. Unknown unregistered keys are rejected in partial updates
because update calls are control-plane mutations and should be shape-checked.
"""

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Dict, Mapping, Optional

from _thinkprogram._iomicrosTM.tiny_helpers import (
    _deep_merge_jsonish_mappings,
    _json_sanitize,
    _to_dict,
)

from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    coerce_session_roles,
    role_modulation_surface_sheet_v1,
    sanitize_role_mismatch_policy_for_metadata,
    validate_role_modulation_surface,
)
from _thinksessions.sesh_metadata.__sesh_meta_session_storage_caps_surface import (
    sanitize_manual_io_policy,
    sanitize_session_storage_policy,
)
from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry,
)


@dataclass(frozen=True, slots=True)
class SessionArgs:
    """
    Canonical engine-owned session metadata surface.

    This dataclass intentionally includes only core engine-owned keys. App-owned
    dynamic pockets live outside the dataclass and are handled by
    SessionMetadataSurfaceRegistry.
    """

    roles: Dict[str, Dict[str, Any]]
    role_mismatch_policy: Dict[str, Any]

    manual_io: Dict[str, Any]
    session_storage: Dict[str, Any]

    @classmethod
    def from_any(cls, obj: Mapping[str, Any] | Any | None) -> "SessionArgs":
        d: Dict[str, Any] = {}

        if obj is None:
            d = {}
        elif isinstance(obj, Mapping):
            d = dict(obj)
        elif is_dataclass(obj):
            d = asdict(obj)
        else:
            for k in dir(obj):
                if k.startswith("_"):
                    continue
                try:
                    v = getattr(obj, k)
                except Exception:
                    continue
                if callable(v):
                    continue
                d[k] = v

        return cls(
            roles=coerce_session_roles(d.get("roles")),
            role_mismatch_policy=sanitize_role_mismatch_policy_for_metadata(
                d.get("role_mismatch_policy")
            ),
            manual_io=(
                dict(d.get("manual_io") or {})
                if isinstance(d.get("manual_io"), Mapping)
                else {}
            ),
            session_storage=(
                dict(d.get("session_storage") or {})
                if isinstance(d.get("session_storage"), Mapping)
                else {}
            ),
        )

    def to_metadata(self) -> Dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


def session_args_surface_defaults() -> Dict[str, Any]:
    """
    Defaults for core engine-owned session metadata keys.

    Dynamic app pockets are intentionally not included here because they are not
    fields on SessionArgs. They are published through
    session_args_metadata_surface_sheet_v1().
    """
    return SessionArgs.from_any({}).to_metadata()


def session_args_surface_keys() -> set[str]:
    """
    Core engine-owned metadata keys.
    """
    return set(session_args_surface_defaults().keys())


def session_args_registered_pocket_keys() -> set[str]:
    """
    Currently registered app-owned metadata pocket keys.
    """
    return set(SessionMetadataSurfaceRegistry.registered_keys())


def session_args_known_update_keys() -> set[str]:
    """
    Keys accepted by partial metadata updates.

    Full coercion remains permissive for unregistered app pockets, but updates
    are stricter: they may mutate core keys and registered app pockets only.
    """
    return session_args_surface_keys() | session_args_registered_pocket_keys()


def session_args_metadata_surface_sheet_v1() -> Dict[str, Any]:
    """
    Documentation-as-data for the full session metadata surface.

    This is the top-level metadata sheet. Orthogonal sub-surfaces remain owned
    by their dedicated modules, but are published here so callers/tests can
    validate the whole session metadata contract from one central import.

    The returned surface is:

        core engine-owned surface + registered app-owned pockets
    """
    defaults = session_args_surface_defaults()
    core_keys = sorted(defaults.keys())

    registered_pockets = SessionMetadataSurfaceRegistry.registered_pockets()
    app_pocket_keys = sorted(registered_pockets.keys())

    return {
        "v": 1,
        "kind": "session_args_metadata_surface_v1",
        "keys": [*core_keys, *app_pocket_keys],
        "core_keys": core_keys,
        "app_pocket_keys": app_pocket_keys,
        "defaults": defaults,
        "subsurfaces": {
            "role_modulation": role_modulation_surface_sheet_v1(),
            "manual_io": {
                "owner": "__sesh_meta_session_storage_caps_surface.py",
                "key": "manual_io",
            },
            "session_storage": {
                "owner": "__sesh_meta_session_storage_caps_surface.py",
                "key": "session_storage",
            },
            "app_pockets": registered_pockets,
        },
        "laws": [
            "session metadata is dead JSON after coercion",
            "core top-level keys are constrained to SessionArgs keys",
            "registered app pockets extend the published surface without changing core keys",
            "registered app pocket schemas are declarative JSON-safe metadata",
            "registered app pocket schemas may not contain live callables",
            "full metadata coercion preserves unknown unregistered app keys for backcompat",
            "partial metadata updates accept core keys and registered app pocket keys",
            "role modulation metadata is validated through __sesh_meta_rolebasedRWmodulatorTM_config_surface.py",
            "manual_io and session_storage are sanitized through __sesh_meta_session_storage_caps_surface.py",
            "partial updates are shape-validated first and fully re-coerced after merge",
        ],
    }


def _coerce_value_by_default_type(key: str, value: Any, default: Any) -> Any:
    if value is None:
        return None

    if isinstance(default, bool):
        return bool(value)

    if isinstance(default, int) and not isinstance(default, bool):
        try:
            iv = int(value)
        except Exception as e:
            raise ValueError(f"{key}: must be int; got {type(value).__name__}") from e
        return iv

    if isinstance(default, float):
        try:
            return float(value)
        except Exception as e:
            raise ValueError(f"{key}: must be float; got {type(value).__name__}") from e

    if isinstance(default, str):
        try:
            return str(value)
        except Exception as e:
            raise ValueError(
                f"{key}: must be string-coercible; got {type(value).__name__}"
            ) from e

    if isinstance(default, dict):
        if not isinstance(value, Mapping):
            raise ValueError(
                f"{key}: must be a mapping/dict; got {type(value).__name__}"
            )

        if key == "manual_io":
            return sanitize_manual_io_policy(value)

        if key == "session_storage":
            return sanitize_session_storage_policy(value)

        if key == "role_mismatch_policy":
            return sanitize_role_mismatch_policy_for_metadata(value)

        if key == "roles":
            return coerce_session_roles(value)

        return dict(value)

    return value


def coerce_session_metadata(ui_session_opts: Any | None) -> Dict[str, Any]:
    """
    Coerce full session metadata.

    Core keys are coerced and validated by their dedicated surfaces.

    Registered app pockets are validated through the central pocket registry.

    Unknown unregistered app-owned keys are preserved for backward compatibility.
    Apps that want verified metadata should register a pocket schema at startup.
    """
    raw = _to_dict(ui_session_opts)
    known = SessionArgs.from_any(raw).to_metadata()

    merged: Dict[str, Any] = dict(raw)

    for k, v in known.items():
        if k not in merged or merged.get(k) is None:
            merged[k] = v

    merged.setdefault("manual_io", {})
    merged.setdefault("session_storage", {})

    merged["roles"] = coerce_session_roles(merged.get("roles"))
    merged["role_mismatch_policy"] = sanitize_role_mismatch_policy_for_metadata(
        merged.get("role_mismatch_policy")
    )
    validate_role_modulation_surface(
        roles=merged["roles"],
        role_mismatch_policy=merged["role_mismatch_policy"],
    )

    merged["manual_io"] = sanitize_manual_io_policy(merged.get("manual_io"))
    merged["session_storage"] = sanitize_session_storage_policy(
        merged.get("session_storage")
    )

    SessionMetadataSurfaceRegistry.validate_registered_session_metadata(merged)

    sanitized = _json_sanitize(merged)
    assert isinstance(sanitized, dict), "session metadata must sanitize to a dict"
    return sanitized  # type: ignore[return-value]


def coerce_and_validate_session_metadata_update(update: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Validate a partial session metadata update.

    Accepted top-level keys are:

        core SessionArgs keys
        currently registered app pocket keys

    Unknown unregistered keys are rejected in updates. Full metadata coercion is
    intentionally more permissive for backward compatibility.
    """
    if not isinstance(update, Mapping):
        raise TypeError("session_metadata_update must be a mapping")

    defaults = session_args_surface_defaults()
    registered_pockets = SessionMetadataSurfaceRegistry.registered_pockets()
    known_keys = set(defaults.keys()) | set(registered_pockets.keys())

    out: Dict[str, Any] = {}

    for k, v in dict(update).items():
        ks = str(k)

        if ks not in known_keys:
            raise KeyError(f"unknown session metadata key: {ks!r}")

        if ks in defaults:
            out[ks] = _coerce_value_by_default_type(ks, v, defaults.get(ks))
            continue

        if not isinstance(v, Mapping):
            raise ValueError(
                f"{ks}: registered session metadata pocket update must be a mapping; "
                f"got {type(v).__name__}"
            )

        # Validate the patch-shaped value itself. The final merged value is
        # validated again by coerce_session_metadata(...). This keeps update
        # calls typed while still allowing partial deep-merge patches.
        SessionMetadataSurfaceRegistry.validate_registered_session_metadata({ks: v})
        out[ks] = dict(v)

    sanitized = _json_sanitize(out)
    if not isinstance(sanitized, dict):
        raise TypeError("session_metadata_update must sanitize to a dict")
    return sanitized  # type: ignore[return-value]


def merge_session_metadata(
    base: Mapping[str, Any] | Any | None,
    update: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Merge a validated partial session metadata update into current session metadata.

    Semantics:
      - core top-level keys are constrained by the canonical SessionArgs surface
      - registered app pocket keys may also be updated
      - unknown unregistered keys are rejected in updates
      - nested mappings are deep-merged
      - the result is re-coerced through the full canonical surface
      - registered app pockets are validated after merge
    """
    if not isinstance(update, Mapping):
        raise TypeError("update must be a mapping")

    base_meta = coerce_session_metadata(base)
    validated_update = coerce_and_validate_session_metadata_update(update)
    merged = _deep_merge_jsonish_mappings(base_meta, validated_update)
    return coerce_session_metadata(merged)


def build_interactive_session_metadata(
    ui_opts: Mapping[str, Any] | Any,
    *,
    roles: Optional[Mapping[str, Any]],
    role_mismatch_policy: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Translate interactive role grammar into generic session metadata.

    This is role-aware creation logic only. The returned metadata is still
    ordinary session metadata consumed by the roleless session backend.

    Registered app-owned metadata pockets are preserved and validated by
    coerce_session_metadata(...).
    """
    metadata = coerce_session_metadata(ui_opts)

    metadata["roles"] = coerce_session_roles(
        roles if roles is not None else metadata.get("roles")
    )
    metadata["role_mismatch_policy"] = sanitize_role_mismatch_policy_for_metadata(
        (
            role_mismatch_policy
            if role_mismatch_policy is not None
            else metadata.get("role_mismatch_policy")
        )
    )
    validate_role_modulation_surface(
        roles=metadata["roles"],
        role_mismatch_policy=metadata["role_mismatch_policy"],
    )

    SessionMetadataSurfaceRegistry.validate_registered_session_metadata(metadata)

    sanitized = _json_sanitize(metadata)
    assert isinstance(sanitized, dict), "session metadata must sanitize to a dict"
    return sanitized  # type: ignore[return-value]


__all__ = [
    "SessionArgs",
    "SessionMetadataSurfaceRegistry",
    "build_interactive_session_metadata",
    "coerce_session_metadata",
    "coerce_and_validate_session_metadata_update",
    "merge_session_metadata",
    "session_args_known_update_keys",
    "session_args_metadata_surface_sheet_v1",
    "session_args_registered_pocket_keys",
    "session_args_surface_defaults",
    "session_args_surface_keys",
]