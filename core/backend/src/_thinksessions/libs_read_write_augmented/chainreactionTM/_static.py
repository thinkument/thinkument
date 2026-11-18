from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from _thinkprogram._iomicrosTM.tiny_helpers import _json_sanitize

from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    coerce_session_roles,
    sanitize_role_mismatch_policy_for_metadata,
    validate_role_modulation_surface,
)

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    get_chainreactiontm_version,
)
from _thinksessions.sesh_metadata.__sesh_meta_chainreactionTM_config_surface import (
    FUNKT_M_CONFIG_KEY,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._errors import (
    FunkConfigStaticError,
    FunkExtraneousRoleStaticError,
    FunkRoleConfigMissingStaticError,
    FunkRoleMissingStaticError,
    FunkVersionStaticError,
)


SUPPORTED_FUNKT_M_GLOBAL_VERSIONS = frozenset({"chainreaction1.0"})


DEFAULT_FUNKT_M_GLOBAL_CONFIG = {
    "version": "chainreaction1.0",
    "expect_all_roles_chainreactioned": False,
    "on_semantic_error": "retry_w_error_awareness",
    "max_semantic_errors_in_a_row": 2,
    "max_fills_on_a_span": 8,
    "max_fills_e2e": 64,
    "history_tail_cap": 4,
    "history_size_cap": 25000,
    "events_queue_length": 0,
}


@dataclass(frozen=True)
class NormalizedFunkTMConfig:
    enabled: bool
    version: str
    roles_ordered: list[tuple[str, ...]]
    flat_roles_ordered: list[str]
    expect_all_roles_chainreactioned: bool
    on_semantic_error: str
    max_semantic_errors_in_a_row: int
    max_fills_on_a_span: int
    max_fills_e2e: int
    history_tail_cap: int
    history_size_cap: int
    events_queue_length: int
    role_configs: Dict[str, Dict[str, Any] | None]


def _positive_int(value: Any, *, key: str, default: int) -> int:
    del default

    try:
        out = int(value)
    except Exception as exc:
        raise FunkConfigStaticError(f"{key} must be an integer") from exc

    if out <= 0:
        raise FunkConfigStaticError(f"{key} must be > 0")

    return out


def _non_negative_int(value: Any, *, key: str, default: int) -> int:
    del default

    try:
        out = int(value)
    except Exception as exc:
        raise FunkConfigStaticError(f"{key} must be an integer") from exc

    if out < 0:
        raise FunkConfigStaticError(f"{key} must be >= 0")

    return out


def _normalize_roles_ordered(value: Any) -> list[tuple[str, ...]]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise FunkConfigStaticError(
            "chainreactionTM_config.roles_ordered must be a list"
        )

    groups: list[tuple[str, ...]] = []
    seen: set[str] = set()

    for index, item in enumerate(value):
        if isinstance(item, str):
            raw_group = [item]
        elif isinstance(item, Sequence) and not isinstance(
            item,
            (bytes, bytearray, str),
        ):
            raw_group = list(item)
        else:
            raise FunkConfigStaticError(
                "chainreactionTM_config.roles_ordered"
                f"[{index}] must be a role string or list of role strings"
            )

        group: list[str] = []

        for raw_role in raw_group:
            role = str(raw_role or "").strip()
            if not role:
                raise FunkConfigStaticError("roles_ordered contains an empty role")
            if role in seen:
                raise FunkConfigStaticError(
                    f"roles_ordered repeats role {role!r}"
                )

            seen.add(role)
            group.append(role)

        if not group:
            raise FunkConfigStaticError("roles_ordered contains an empty group")

        groups.append(tuple(group))

    return groups


def _flatten(groups: Sequence[Sequence[str]]) -> list[str]:
    return [role for group in groups for role in group]


def _normalize_role_config(role: str, value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None

    if not isinstance(value, Mapping):
        raise FunkRoleConfigMissingStaticError(
            f"roles[{role!r}].chainreactionTM_config must be None or a mapping"
        )

    row = dict(value)
    unknown = set(row) - {"version", "args"}
    if unknown:
        raise FunkConfigStaticError(
            f"roles[{role!r}].chainreactionTM_config has unknown key(s): "
            f"{sorted(unknown)}"
        )

    version = str(row.get("version") or "").strip()
    if not version:
        raise FunkVersionStaticError(
            f"roles[{role!r}].chainreactionTM_config.version must be non-empty"
        )

    try:
        spec = get_chainreactiontm_version(version)
    except KeyError as exc:
        raise FunkVersionStaticError(str(exc)) from exc

    args_raw = row.get("args") or {}
    if not isinstance(args_raw, Mapping):
        raise FunkConfigStaticError(
            f"roles[{role!r}].chainreactionTM_config.args must be a mapping"
        )

    try:
        args = spec.validate_args(dict(args_raw))
    except Exception as exc:
        raise FunkConfigStaticError(
            f"invalid args for role {role!r}, version {version!r}: {exc}"
        ) from exc

    out = {
        "version": version,
        "args": args,
    }

    sanitized = _json_sanitize(out)
    if not isinstance(sanitized, dict):
        raise FunkConfigStaticError(
            f"roles[{role!r}].chainreactionTM_config must sanitize to dict"
        )

    return sanitized  # type: ignore[return-value]


def normalize_chainreactiontm_config_from_session_metadata(
    session_metadata: Mapping[str, Any],
    *,
    override: Mapping[str, Any] | None = None,
) -> NormalizedFunkTMConfig:
    meta = dict(session_metadata or {})

    roles = coerce_session_roles(meta.get("roles"))
    policy = sanitize_role_mismatch_policy_for_metadata(
        meta.get("role_mismatch_policy")
    )
    validate_role_modulation_surface(
        roles=roles,
        role_mismatch_policy=policy,
    )

    raw_config = override if override is not None else meta.get(FUNKT_M_CONFIG_KEY)

    if raw_config is None:
        return NormalizedFunkTMConfig(
            enabled=False,
            version="",
            roles_ordered=[],
            flat_roles_ordered=[],
            expect_all_roles_chainreactioned=False,
            on_semantic_error="retry_w_error_awareness",
            max_semantic_errors_in_a_row=0,
            max_fills_on_a_span=0,
            max_fills_e2e=0,
            history_tail_cap=0,
            history_size_cap=0,
            events_queue_length=0,
            role_configs={},
        )

    if not isinstance(raw_config, Mapping):
        raise FunkConfigStaticError(
            "session_metadata.chainreactionTM_config must be None or mapping"
        )

    config = {
        **DEFAULT_FUNKT_M_GLOBAL_CONFIG,
        **dict(raw_config),
    }

    allowed_global_keys = set(DEFAULT_FUNKT_M_GLOBAL_CONFIG) | {"roles_ordered"}
    unknown_global_keys = set(config) - allowed_global_keys
    if unknown_global_keys:
        raise FunkConfigStaticError(
            "session_metadata.chainreactionTM_config has unknown key(s): "
            f"{sorted(unknown_global_keys)}"
        )

    global_version = str(config.get("version") or "chainreaction1.0").strip()
    if global_version not in SUPPORTED_FUNKT_M_GLOBAL_VERSIONS:
        raise FunkVersionStaticError(
            "unsupported session_metadata.chainreactionTM_config.version "
            f"{global_version!r}; supported: "
            f"{sorted(SUPPORTED_FUNKT_M_GLOBAL_VERSIONS)}"
        )

    groups = _normalize_roles_ordered(config.get("roles_ordered"))
    flat = _flatten(groups)

    role_names = set(roles.keys())
    ordered_names = set(flat)

    missing = sorted(role_names - ordered_names)
    extra = sorted(ordered_names - role_names)

    if missing:
        raise FunkRoleMissingStaticError(
            "chainreactionTM_config.roles_ordered missing role(s): "
            + ", ".join(missing)
        )

    if extra:
        raise FunkExtraneousRoleStaticError(
            "chainreactionTM_config.roles_ordered has extraneous role(s): "
            + ", ".join(extra)
        )

    role_configs: Dict[str, Dict[str, Any] | None] = {}
    for role_name, role_row_raw in roles.items():
        role_row = role_row_raw if isinstance(role_row_raw, Mapping) else {}

        if "chainreactionTM_config" not in role_row:
            raise FunkRoleConfigMissingStaticError(
                f"roles[{role_name!r}] missing required chainreactionTM_config key"
            )

        role_configs[role_name] = _normalize_role_config(
            role_name,
            role_row.get("chainreactionTM_config"),
        )

    expect_all = bool(config.get("expect_all_roles_chainreactioned", False))
    if expect_all:
        unchainreactioned = sorted(
            role_name
            for role_name, role_config in role_configs.items()
            if role_config is None
        )
        if unchainreactioned:
            raise FunkRoleConfigMissingStaticError(
                "expect_all_roles_chainreactioned=True but role(s) are "
                "unchainreactioned: "
                + ", ".join(unchainreactioned)
            )

    on_semantic_error = str(
        config.get("on_semantic_error") or "retry_w_error_awareness"
    ).strip()
    if on_semantic_error not in {"retry_w_error_awareness", "raise"}:
        raise FunkConfigStaticError(
            "chainreactionTM_config.on_semantic_error must be "
            "'retry_w_error_awareness' or 'raise'"
        )

    return NormalizedFunkTMConfig(
        enabled=True,
        version=global_version,
        roles_ordered=groups,
        flat_roles_ordered=flat,
        expect_all_roles_chainreactioned=expect_all,
        on_semantic_error=on_semantic_error,
        max_semantic_errors_in_a_row=_positive_int(
            config.get("max_semantic_errors_in_a_row"),
            key="max_semantic_errors_in_a_row",
            default=2,
        ),
        max_fills_on_a_span=_positive_int(
            config.get("max_fills_on_a_span"),
            key="max_fills_on_a_span",
            default=8,
        ),
        max_fills_e2e=_positive_int(
            config.get("max_fills_e2e"),
            key="max_fills_e2e",
            default=64,
        ),
        history_tail_cap=_positive_int(
            config.get("history_tail_cap"),
            key="history_tail_cap",
            default=4,
        ),
        history_size_cap=_positive_int(
            config.get("history_size_cap"),
            key="history_size_cap",
            default=25000,
        ),
        events_queue_length=_non_negative_int(
            config.get("events_queue_length"),
            key="events_queue_length",
            default=0,
        ),
        role_configs=role_configs,
    )