from __future__ import annotations

"""
Role mismatch obfuscation mode registry.

A mode is a pure ctx-vector modulation over a formal datum address set.

Mode signature:

    fn(ctx, *, datum_id, viewer_role, datum_roles, addresses, reason) -> ctx

The function may mutate and return ctx. It must only use the formal addresses
provided by obfuscation_formalism.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, MutableMapping, Sequence

from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_DATUM_STATES_ON_THIS_SPAN,
    CTX_DATUM_WIDGET_DECLS,
    CTX_DATUM_WIDGET_FILLS,
    CTX_LAST_ERROR,
    CTX_MULTIFRAMESPEC,
)

from ._obfuscation_formalism import (
    DatumCtxAddresses,
    remove_datum_from_membership_vectors,
)


ObfuscationModeFn = Callable[
    [
        MutableMapping[str, Any],
    ],
    MutableMapping[str, Any],
]


ROLE_MISMATCH_KIND_V1 = "role_mismatch_obfuscated_datum_v1"
DEFAULT_OBFUSCATION_MODE = "redacted"

RECEIPT_IDENTITY = "identity"
RECEIPT_OWNERSHIP = "ownership"
RECEIPT_ACTIVITY = "activity"
RECEIPT_FIELDS = frozenset(
    {
        RECEIPT_IDENTITY,
        RECEIPT_OWNERSHIP,
        RECEIPT_ACTIVITY,
    }
)


@dataclass(frozen=True, slots=True)
class ObfuscationModeSpec:
    name: str
    transform: Callable[..., MutableMapping[str, Any]]
    receipt_fields: FrozenSet[str] = frozenset()


def _normalize_receipt_fields(
    values: Sequence[str] | FrozenSet[str] | None,
) -> FrozenSet[str]:
    normalized = frozenset(
        str(value or "").strip()
        for value in list(values or ())
        if str(value or "").strip()
    )
    unknown = normalized.difference(RECEIPT_FIELDS)
    if unknown:
        raise ValueError(
            "unknown role mismatch receipt field(s): "
            + ", ".join(sorted(unknown))
        )
    if (
        RECEIPT_OWNERSHIP in normalized
        and RECEIPT_IDENTITY not in normalized
    ):
        raise ValueError(
            "ownership receipt requires identity receipt"
        )
    return normalized


def redacted_obfuscation_mode_v1(
    ctx: MutableMapping[str, Any],
    *,
    datum_id: str,
    viewer_role: str | None,
    datum_roles: Sequence[str],
    addresses: DatumCtxAddresses,
    reason: str = "role_mismatch",
) -> MutableMapping[str, Any]:
    """
    Default leak-preventing role mismatch modulation.

    It replaces datum declaration, fill, datum-state, and multiframespec
    information with inert redaction markers and removes the datum from all
    editable membership vectors.

    The static ``datum_states_on_this_span`` row remains in place so span
    ownership order and product-vector shape stay stable.
    """
    did = str(datum_id)

    datum_states = ctx.get(CTX_DATUM_STATES_ON_THIS_SPAN)
    if isinstance(datum_states, list):
        for i in addresses.datum_states_on_this_span_indices:
            if not (0 <= i < len(datum_states)):
                continue

            datum_states[i] = {
                "kind": ROLE_MISMATCH_KIND_V1,
                "datum_id": did,
                "role_mismatch_obfuscated": True,
                "obfuscated": True,
                "reason": reason,
                "viewer_role": viewer_role,
                "required_roles": list(datum_roles),
                "is_authoritative": None,
                "is_pending": False,
            }

    decls = ctx.get(CTX_DATUM_WIDGET_DECLS)
    if isinstance(decls, dict) and addresses.has_decl:
        decls[did] = {
            "field_id": did,
            "fillspan_name": None,
            "micros": [],
            "micro_names": [],
            "datum_args": {
                "id": did,
                "title": "Unavailable",
                "help_text": (
                    "This datum is hidden because of a role mismatch."
                ),
                "role_mismatch_obfuscated": True,
                "viewer_role": viewer_role,
                "required_roles": list(datum_roles),
                "kind": ROLE_MISMATCH_KIND_V1,
            },
            "role_mismatch_obfuscated": True,
            "kind": ROLE_MISMATCH_KIND_V1,
        }

    fills = ctx.get(CTX_DATUM_WIDGET_FILLS)
    if isinstance(fills, dict) and addresses.has_fill:
        fills[did] = {
            "kind": ROLE_MISMATCH_KIND_V1,
            "obfuscated": True,
            "reason": reason,
        }

    last_error = ctx.get(CTX_LAST_ERROR)
    if isinstance(last_error, dict) and addresses.has_last_error:
        last_error[did] = (
            "This datum is hidden because of a role mismatch."
        )

    fs = ctx.get(CTX_MULTIFRAMESPEC)
    if isinstance(fs, dict):
        datums = fs.get("datums")
        if isinstance(datums, list):
            for i in addresses.multiframespec_datum_indices:
                if 0 <= i < len(datums):
                    datums[i] = {
                        "id": did,
                        "title": "Unavailable",
                        "micros": [],
                        "tags": [],
                        "role_mismatch_obfuscated": True,
                        "viewer_role": viewer_role,
                        "required_roles": list(datum_roles),
                        "kind": ROLE_MISMATCH_KIND_V1,
                    }

        fills = fs.get("fills")
        if (
            isinstance(fills, dict)
            and addresses.multiframespec_fill_present
        ):
            fills[did] = {
                "kind": ROLE_MISMATCH_KIND_V1,
                "obfuscated": True,
                "reason": reason,
            }

        frames = fs.get("frames")
        if isinstance(frames, list):
            for (
                frame_i,
                span_i,
                _own_i,
            ) in addresses.multiframespec_frame_span_own_slots:
                if not (0 <= frame_i < len(frames)):
                    continue

                frame = frames[frame_i]
                if not isinstance(frame, dict):
                    continue

                spans = frame.get("spans")
                if (
                    not isinstance(spans, list)
                    or not (0 <= span_i < len(spans))
                ):
                    continue

                span = spans[span_i]
                if (
                    isinstance(span, dict)
                    and isinstance(span.get("owns"), list)
                ):
                    span["owns"] = [
                        x
                        for x in span["owns"]
                        if str(x) != did
                    ]

    remove_datum_from_membership_vectors(
        ctx,
        datum_id=did,
    )
    return ctx


_OBFUSCATION_MODES: Dict[str, ObfuscationModeSpec] = {
    DEFAULT_OBFUSCATION_MODE: ObfuscationModeSpec(
        name=DEFAULT_OBFUSCATION_MODE,
        transform=redacted_obfuscation_mode_v1,
    ),
    "readonly_redacted": ObfuscationModeSpec(
        name="readonly_redacted",
        transform=redacted_obfuscation_mode_v1,
    ),
    "redacted-w-activity-receipt": ObfuscationModeSpec(
        name="redacted-w-activity-receipt",
        transform=redacted_obfuscation_mode_v1,
        receipt_fields=frozenset(
            {
                RECEIPT_ACTIVITY,
            }
        ),
    ),
    "redacted-w-identity-receipt": ObfuscationModeSpec(
        name="redacted-w-identity-receipt",
        transform=redacted_obfuscation_mode_v1,
        receipt_fields=frozenset(
            {
                RECEIPT_IDENTITY,
            }
        ),
    ),
    "redacted-w-identity-ownership-receipt": ObfuscationModeSpec(
        name="redacted-w-identity-ownership-receipt",
        transform=redacted_obfuscation_mode_v1,
        receipt_fields=frozenset(
            {
                RECEIPT_IDENTITY,
                RECEIPT_OWNERSHIP,
            }
        ),
    ),
    "redacted-w-identity-ownership-activity-receipt": (
        ObfuscationModeSpec(
            name=(
                "redacted-w-identity-ownership-activity-receipt"
            ),
            transform=redacted_obfuscation_mode_v1,
            receipt_fields=frozenset(
                {
                    RECEIPT_IDENTITY,
                    RECEIPT_OWNERSHIP,
                    RECEIPT_ACTIVITY,
                }
            ),
        )
    ),
}


def register_obfuscation_mode(
    name: str,
    fn: Callable[..., MutableMapping[str, Any]] | None = None,
    *,
    base_mode: str = DEFAULT_OBFUSCATION_MODE,
    receipt_fields: Sequence[str] | FrozenSet[str] = (),
    overwrite: bool = False,
) -> None:
    mode = str(name or "").strip()
    if not mode:
        raise ValueError(
            "obfuscation mode name must be non-empty"
        )
    if fn is None:
        fn = resolve_obfuscation_mode_spec(base_mode).transform
    if not callable(fn):
        raise TypeError("obfuscation mode must be callable")
    if mode in _OBFUSCATION_MODES and not overwrite:
        raise ValueError(
            f"obfuscation mode already registered: {mode!r}"
        )
    _OBFUSCATION_MODES[mode] = ObfuscationModeSpec(
        name=mode,
        transform=fn,
        receipt_fields=_normalize_receipt_fields(
            receipt_fields
        ),
    )


def resolve_obfuscation_mode_spec(
    name: str | None,
) -> ObfuscationModeSpec:
    mode = (
        str(name or DEFAULT_OBFUSCATION_MODE).strip()
        or DEFAULT_OBFUSCATION_MODE
    )
    try:
        return _OBFUSCATION_MODES[mode]
    except KeyError as exc:
        raise KeyError(
            f"unknown role mismatch obfuscation mode: {mode!r}"
        ) from exc


def resolve_obfuscation_mode(
    name: str | None,
) -> Callable[..., MutableMapping[str, Any]]:
    return resolve_obfuscation_mode_spec(name).transform


def obfuscation_mode_names() -> list[str]:
    return sorted(_OBFUSCATION_MODES.keys())


def obfuscation_mode_sheet_v1() -> Dict[str, Any]:
    return {
        "kind": "role_mismatch_obfuscation_mode_registry_v1",
        "default": DEFAULT_OBFUSCATION_MODE,
        "receipt_fields": sorted(RECEIPT_FIELDS),
        "modes": [
            {
                "name": spec.name,
                "receipt_fields": sorted(
                    spec.receipt_fields
                ),
            }
            for spec in sorted(
                _OBFUSCATION_MODES.values(),
                key=lambda row: row.name,
            )
        ],
    }


__all__ = [
    "DEFAULT_OBFUSCATION_MODE",
    "ObfuscationModeSpec",
    "RECEIPT_ACTIVITY",
    "RECEIPT_FIELDS",
    "RECEIPT_IDENTITY",
    "RECEIPT_OWNERSHIP",
    "ROLE_MISMATCH_KIND_V1",
    "obfuscation_mode_names",
    "obfuscation_mode_sheet_v1",
    "redacted_obfuscation_mode_v1",
    "register_obfuscation_mode",
    "resolve_obfuscation_mode",
    "resolve_obfuscation_mode_spec",
]