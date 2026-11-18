from __future__ import annotations

"""
Session args role modulation surface
====================================

Role configuration and role mismatch policy normalization for session metadata.

Final law:
  - metadata is dead JSON only
  - live callables are rejected, not preserved in a side channel
  - executable layers are registry dot-path strings/directives
  - non-layer keys may carry declarative JSON-safe metadata
"""

from typing import Any, Dict, Mapping, Sequence

from _thinkprogram._iomicrosTM.tiny_helpers import _json_sanitize


ROLE_READ_ROLES_KEY = "read_roles"
ROLE_READ_ALIASES = ("read_roles", "can_read_roles", "can_read", "view_roles")
ROLE_MISMATCH_POLICY_DEFAULT_KEY = "default"
ROLE_MISMATCH_POLICY_ROLE_MODES_KEY = "role_modes"
DEFAULT_ROLE_MISMATCH_MODE = "redacted"
BUILTIN_ROLE_MISMATCH_MODES = (
    "redacted",
    "redacted-w-activity-receipt",
    "redacted-w-identity-receipt",
    "redacted-w-identity-ownership-receipt",
    "redacted-w-identity-ownership-activity-receipt",
)


def _reject_callables_deep(value: Any, *, path: str) -> None:
    """
    Keep session role metadata dead/declarative.

    JSON sanitation must not be the mechanism that hides live executable
    objects. If an app wants executable behavior, it must register that behavior
    by name in the relevant registry and store the registry string here.
    """
    if callable(value):
        raise TypeError(
            f"{path} is a live callable. Role modulation metadata must be "
            "dead JSON/declarative data only."
        )

    if isinstance(value, Mapping):
        for k, v in value.items():
            _reject_callables_deep(v, path=f"{path}.{k}")
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for i, v in enumerate(value):
            _reject_callables_deep(v, path=f"{path}[{i}]")


def _string_list(value: Any, *, path: str) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw = list(value)
    else:
        raw = [value]

    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text:
            raise ValueError(f"{path} contains an empty role name")
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def coerce_session_roles(raw: Any | None) -> Dict[str, Dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise TypeError("roles must be a mapping of role_name -> dict")

    out: Dict[str, Dict[str, Any]] = {}
    for rk, rv in dict(raw).items():
        role_name = str(rk or "").strip()
        if not role_name:
            raise ValueError("roles contains an empty role name")

        if rv is None:
            out[role_name] = {}
            continue

        if not isinstance(rv, Mapping):
            raise TypeError(f"roles[{role_name!r}] must be a mapping/dict")

        row = dict(rv)
        _reject_callables_deep(row, path=f"roles[{role_name!r}]")

        read_roles: list[str] = []
        for alias in ROLE_READ_ALIASES:
            if alias in row:
                read_roles.extend(
                    _string_list(
                        row.get(alias),
                        path=f"roles[{role_name!r}].{alias}",
                    )
                )

        if read_roles:
            seen: set[str] = set()
            canonical_read_roles: list[str] = []
            for read_role in read_roles:
                if read_role in seen:
                    continue
                seen.add(read_role)
                canonical_read_roles.append(read_role)
            row[ROLE_READ_ROLES_KEY] = canonical_read_roles

        for alias in ROLE_READ_ALIASES:
            if alias != ROLE_READ_ROLES_KEY:
                row.pop(alias, None)

        sanitized = _json_sanitize(row)
        if not isinstance(sanitized, dict):
            raise TypeError(f"roles[{role_name!r}] must sanitize to a dict")
        out[role_name] = sanitized  # type: ignore[assignment]

    return out


def sanitize_role_mismatch_policy_for_metadata(raw: Any | None) -> Dict[str, Any]:
    """
    Normalize persisted role mismatch policy.

    Final accepted shape:

        {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
            },
        }

    Rejected:

        {"on_mismatch": "error"}

    because final policy must be explicit and non-ambiguous.
    """
    if raw is None:
        return {
            ROLE_MISMATCH_POLICY_DEFAULT_KEY: DEFAULT_ROLE_MISMATCH_MODE,
            ROLE_MISMATCH_POLICY_ROLE_MODES_KEY: {},
        }
    if not isinstance(raw, Mapping):
        raise TypeError("role_mismatch_policy must be a mapping/dict")

    if "on_mismatch" in raw:
        raise ValueError(
            "role_mismatch_policy['on_mismatch'] is not part of the final "
            "role modulation formalism. Use "
            "{'default': 'redacted', 'role_modes': {role_name: mode_name}}."
        )

    out: Dict[str, Any] = {
        ROLE_MISMATCH_POLICY_DEFAULT_KEY: DEFAULT_ROLE_MISMATCH_MODE,
        ROLE_MISMATCH_POLICY_ROLE_MODES_KEY: {},
    }

    for k, v in dict(raw).items():
        ks = str(k)

        if callable(v):
            raise TypeError(
                f"role_mismatch_policy[{ks!r}] is a live callable. "
                "Register obfuscation behavior in obfuscation_modes.py and "
                "store its mode string instead."
            )

        if ks == ROLE_MISMATCH_POLICY_ROLE_MODES_KEY:
            if not isinstance(v, Mapping):
                raise TypeError("role_mismatch_policy.role_modes must be a mapping")
            role_modes: Dict[str, str] = {}
            for rk, rv in dict(v).items():
                role_name = str(rk or "").strip()
                if not role_name:
                    raise ValueError(
                        "role_mismatch_policy.role_modes has empty role name"
                    )
                if callable(rv):
                    raise TypeError(
                        "role_mismatch_policy.role_modes"
                        f"[{role_name!r}] is a live callable. Store a mode "
                        "string registered in obfuscation_modes.py instead."
                    )
                mode = str(rv or "").strip()
                if not mode:
                    raise ValueError(
                        f"role_mismatch_policy.role_modes[{role_name!r}] "
                        "must be a non-empty mode string"
                    )
                role_modes[role_name] = mode
            out[ROLE_MISMATCH_POLICY_ROLE_MODES_KEY] = role_modes
            continue

        if ks == ROLE_MISMATCH_POLICY_DEFAULT_KEY:
            mode = str(v or "").strip()
            if not mode:
                raise ValueError(
                    "role_mismatch_policy.default must be a non-empty mode string"
                )
            out[ROLE_MISMATCH_POLICY_DEFAULT_KEY] = mode
            continue

        raise KeyError(
            "unknown role_mismatch_policy key "
            f"{ks!r}; use only 'default' and 'role_modes'"
        )

    sanitized = _json_sanitize(out)
    if not isinstance(sanitized, dict):
        raise TypeError("role_mismatch_policy must sanitize to a dict")

    return sanitized  # type: ignore[return-value]


def role_mismatch_mode_for_viewer_role(
    role_mismatch_policy: Mapping[str, Any],
    *,
    role: str | None,
) -> str:
    """
    Return the declarative mismatch mode name for one viewer role.

    This only selects the mode string from canonical metadata. It intentionally
    does not import the obfuscation-mode registry, avoiding a surface/runtime
    dependency cycle.
    """
    policy = sanitize_role_mismatch_policy_for_metadata(role_mismatch_policy)
    role_key = str(role or "")
    role_modes = policy.get(ROLE_MISMATCH_POLICY_ROLE_MODES_KEY)

    if isinstance(role_modes, Mapping) and role_key in role_modes:
        return str(role_modes[role_key])

    return str(
        policy.get(ROLE_MISMATCH_POLICY_DEFAULT_KEY)
        or DEFAULT_ROLE_MISMATCH_MODE
    )


def effective_read_roles_for_role(
    roles: Mapping[str, Any],
    *,
    role: str | None,
) -> set[str]:
    """
    Return the roles whose guarded datum data may be read by viewer role.

    Law:
      - roleless viewer reads no guarded role data
      - a named role always reads itself
      - roles[role].read_roles adds adjacent readable roles
    """
    if role is None:
        return set()

    role_name = str(role or "").strip()
    if not role_name:
        return set()

    if role_name not in roles:
        raise KeyError(f"role_viewing {role_name!r} not found in session roles")

    row = roles.get(role_name)
    row = row if isinstance(row, Mapping) else {}

    return {
        role_name,
        *_string_list(
            row.get(ROLE_READ_ROLES_KEY),
            path=f"roles[{role_name!r}].{ROLE_READ_ROLES_KEY}",
        ),
    }


def role_can_read_required_roles(
    roles: Mapping[str, Any],
    *,
    role: str | None,
    required_roles: Sequence[str],
) -> bool:
    required = {
        str(value)
        for value in list(required_roles or [])
        if str(value or "").strip()
    }
    if not required:
        return True

    readable = effective_read_roles_for_role(roles, role=role)
    return bool(required.intersection(readable))


def role_can_write_required_roles(
    *,
    role: str | None,
    required_roles: Sequence[str],
) -> bool:
    required = {
        str(value)
        for value in list(required_roles or [])
        if str(value or "").strip()
    }
    if not required:
        return True
    if role is None:
        return False
    return str(role) in required


def validate_role_modulation_surface(
    *,
    roles: Mapping[str, Any],
    role_mismatch_policy: Mapping[str, Any],
) -> None:
    """
    Strict coherence gate for the finalized role modulation metadata surface.

    It validates references only. It does not execute obfuscation modes.
    """
    role_names = set(str(k) for k in roles.keys())

    for role_name, raw_row in roles.items():
        row = raw_row if isinstance(raw_row, Mapping) else {}
        for readable_role in _string_list(
            row.get(ROLE_READ_ROLES_KEY),
            path=f"roles[{role_name!r}].{ROLE_READ_ROLES_KEY}",
        ):
            if readable_role not in role_names:
                raise KeyError(
                    f"roles[{role_name!r}].read_roles references unknown role "
                    f"{readable_role!r}"
                )

    policy = sanitize_role_mismatch_policy_for_metadata(role_mismatch_policy)
    role_modes = policy.get(ROLE_MISMATCH_POLICY_ROLE_MODES_KEY)
    if isinstance(role_modes, Mapping):
        for role_name in role_modes.keys():
            if str(role_name) not in role_names:
                raise KeyError(
                    "role_mismatch_policy.role_modes references unknown role "
                    f"{role_name!r}"
                )


def role_modulation_surface_sheet_v1() -> Dict[str, Any]:
    """
    Documentation-as-data for the final session metadata role surface.
    """
    return {
        "v": 1,
        "metadata_keys": ["roles", "role_mismatch_policy"],
        "roles": {
            "<role_name>": {
                "label": "optional display label",
                "read_roles": [
                    "optional adjacent roles this role may read without write power"
                ],
                "...": "other app-owned JSON-safe role metadata",
            }
        },
        "role_mismatch_policy": {
            "default": DEFAULT_ROLE_MISMATCH_MODE,
            "role_modes": {
                "<viewer_role>": DEFAULT_ROLE_MISMATCH_MODE,
            },
        },
        "mode_resolution": {
            "law": (
                "A mismatch uses role_mismatch_policy.role_modes[viewer_role] "
                "when present, otherwise role_mismatch_policy.default."
            ),
            "note": (
                "Modes are declarative strings. Runtime resolves them through "
                "the obfuscation mode registry."
            ),
        },
        "built_in_modes": list(BUILTIN_ROLE_MISMATCH_MODES),
        "receipt": {
            "location": "U.role_mismatch_modulation_info.receipt",
            "default": None,
            "kind": "role_mismatch_activity_receipt_v1",
            "laws": [
                "redacted is the strict default and emits no custom receipt",
                "receipt disclosure is selected by the same single mode string",
                "receipt modes reuse the registered redaction transform",
                (
                    "activity receipts contain bounded structural facts, "
                    "never datum content"
                ),
                "new modes are added through the role modulation mode registry",
            ],
        },
        "event_release": {
            "controller_event_spine": {
                "stable": [
                    "kind",
                    "event_id",
                    "event_seq",
                    "emitted_at",
                    "source",
                    "name",
                    "phase",
                    "session_id",
                    "action",
                    "payload.timestamp",
                    "payload.outcome",
                    "payload.result",
                    "payload.system_error",
                ],
            },
            "controller_U": (
                "Project start U from the canonical pre-state and end U from "
                "the canonical post/recovered state independently."
            ),
            "controller_A": [
                "Canonical A is present on both start and end.",
                (
                    "A target roles are resolved against the matching "
                    "controller start U, because A describes the submitted "
                    "entry action."
                ),
                (
                    "The matching end U must not reinterpret A after a "
                    "frame/span transition or datum-id reuse."
                ),
                "Filter fill entries by target datum read authority.",
                "Retain signal only when its target datum is readable.",
                "payload.fill and payload.signal mirror projected A.",
                (
                    "When canonical A has targets and none survive, release A, "
                    "fill, signal, dispatch_id, dispatcher_identity_id, and "
                    "dispatcher_role as null."
                ),
                (
                    "When A has no targets or at least one target survives, "
                    "retain dispatch_id, dispatcher_identity_id, and "
                    "dispatcher_role."
                ),
            ],
            "datum_events": (
                "Release the whole datum lifecycle event iff the viewer can "
                "read the event datum; otherwise omit the whole packet."
            ),
        },
        "required_roles_resolution": [
            "datum.roles if present",
            "datum.role if datum.roles absent",
            "span.roles if datum has no role data",
            "span.role if span.roles absent",
            "[] means unguarded",
        ],
        "laws": [
            "roleless viewer cannot read guarded datum data",
            "a role can always read its own guarded datum data",
            "roles[R].read_roles grants read visibility over adjacent roles",
            "read visibility never grants write permission",
            "writes are allowed only for exact required datum/span role",
            "controller A target authority is interpreted in dispatch entry scope",
            "no read visibility means complete blackout via mismatch mode",
            (
                "one metadata-selected registered mode controls redaction and "
                "optional bounded receipt disclosure"
            ),
            "the default redacted mode emits no receipt",
            (
                "receipt construction never mutates canonical U or the "
                "canonical event queue"
            ),
            "the engine remains roleless; this is a ctx projection and submission guard",
        ],
    }


__all__ = [
    "BUILTIN_ROLE_MISMATCH_MODES",
    "DEFAULT_ROLE_MISMATCH_MODE",
    "ROLE_MISMATCH_POLICY_DEFAULT_KEY",
    "ROLE_MISMATCH_POLICY_ROLE_MODES_KEY",
    "ROLE_READ_ROLES_KEY",
    "coerce_session_roles",
    "effective_read_roles_for_role",
    "role_can_read_required_roles",
    "role_can_write_required_roles",
    "role_mismatch_mode_for_viewer_role",
    "role_modulation_surface_sheet_v1",
    "sanitize_role_mismatch_policy_for_metadata",
    "validate_role_modulation_surface",
]