from __future__ import annotations

"""Role-projected controller-event expectation helpers, version 1.

These helpers encode the current public projection packet family. They are
unopinionated with respect to application widgets, but intentionally versioned
because they know the v1 ``payload.U`` role-modulation fields.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

from .event_expectations_v1 import controller_envelope_v1


_ACTIVE_UNSET = object()


def ROLE_VIEW(
    role: str,
    *,
    expect: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "role": str(role),
        "E": deepcopy(dict(expect)),
    }


def projected_U_v1(
    *,
    role: str,
    active: list[str] | None,
    mismatch_ids: list[str],
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Build boundary-local projected ``payload.U`` needles.

    ``active=None`` means the active-membership key must be absent.
    ``active=[]`` means the key must exist and be an empty list.
    """
    out: Dict[str, Any] = {
        "payload.U.role_mismatch_modulation_info.kind": (
            "role_mismatch_modulation_info_v1"
        ),
        "payload.U.role_mismatch_modulation_info.role_viewing": str(role),
        (
            "payload.U.role_mismatch_modulation_info."
            "mismatch_datum_ids"
        ): list(mismatch_ids),
    }

    if kind is not None:
        out["payload.U.kind"] = str(kind)

    if active is None:
        out["payload.U.datum_widgets_on_this_span__absent"] = True
    else:
        out["payload.U.datum_widgets_on_this_span"] = list(active)

    return out


def role_projected_controller_envelope_v1(
    *middle: Mapping[str, Any],
    role: str,
    active: list[str] | None | object = _ACTIVE_UNSET,
    mismatch_ids: Optional[list[str]] = None,
    start_active: list[str] | None | object = _ACTIVE_UNSET,
    start_mismatch_ids: Optional[list[str]] = None,
    end_active: list[str] | None | object = _ACTIVE_UNSET,
    end_mismatch_ids: Optional[list[str]] = None,
    start_kind: Optional[str] = None,
    end_kind: Optional[str] = None,
    event_kind: Optional[str] = None,
    finished: Optional[bool] = None,
    exact_middle: bool = False,
) -> Dict[str, Any]:
    """Describe independently projected start and end boundary snapshots."""
    shared_active = active
    shared_mismatch_ids = list(mismatch_ids or [])

    resolved_start_active = (
        shared_active if start_active is _ACTIVE_UNSET else start_active
    )
    resolved_end_active = (
        shared_active if end_active is _ACTIVE_UNSET else end_active
    )

    if resolved_start_active is _ACTIVE_UNSET:
        raise TypeError(
            "role_projected_controller_envelope_v1 requires active=... or "
            "start_active=..."
        )
    if resolved_end_active is _ACTIVE_UNSET:
        raise TypeError(
            "role_projected_controller_envelope_v1 requires active=... or "
            "end_active=..."
        )

    resolved_start_mismatch_ids = (
        shared_mismatch_ids
        if start_mismatch_ids is None
        else list(start_mismatch_ids)
    )
    resolved_end_mismatch_ids = (
        shared_mismatch_ids
        if end_mismatch_ids is None
        else list(end_mismatch_ids)
    )

    expected = controller_envelope_v1(
        *middle,
        action="STEP",
        event_kind=event_kind,
        finished=finished,
        exact_middle=exact_middle,
    )
    expected["Estart"].update(
        projected_U_v1(
            role=role,
            kind=start_kind,
            active=resolved_start_active,  # type: ignore[arg-type]
            mismatch_ids=resolved_start_mismatch_ids,
        )
    )
    expected["Eend"].update(
        projected_U_v1(
            role=role,
            kind=end_kind,
            active=resolved_end_active,  # type: ignore[arg-type]
            mismatch_ids=resolved_end_mismatch_ids,
        )
    )
    return expected


# Compact compatibility aliases used by the executable guide flow modules.
projected_U = projected_U_v1
role_projected_trident = role_projected_controller_envelope_v1


__all__ = [
    "ROLE_VIEW",
    "projected_U",
    "projected_U_v1",
    "role_projected_controller_envelope_v1",
    "role_projected_trident",
]
