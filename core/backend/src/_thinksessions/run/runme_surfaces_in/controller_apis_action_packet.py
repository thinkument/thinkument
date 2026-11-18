from __future__ import annotations

"""
Controller action packet surface
================================

This is the canonical highest-controller input contract for manual UI/session
actions that may carry both:

    - fill data, addressed by datum id;
    - at most one datum-targeted signal.

The controller and every higher facade should normalize through this surface
before delegating to the lower session API. This makes the shape documented
here the real input contract, not only prose documentation.

Canonical packet
----------------

    {
        "fill": {
            "D": {"value": "x"}
        },
        "signal": {
            "datum_id": "D",
            "kind": "refresh",
            "info": {"reason": "external-change"}
        }
    }

Laws
----

- ``fill`` is optional. ``None`` normalizes to ``{}`` at the controller action
  boundary.
- ``fill`` must be a mapping when supplied.
- fill keys are datum ids. Dotted micro keys are still normalized by the
  controller's existing fill normalizer before this surface is applied.
- ``signal`` is optional.
- exactly zero or one signal may be present.
- a signal must target exactly one datum id with ``signal["datum_id"]``.
- ``signal["kind"]`` is a non-empty string. It is intentionally open-ended:
  datum widgets already understand q["signal"]["kind"] as a string.
- ``signal["info"]`` is an optional mapping and normalizes to ``{}``.
- The packet must be dead JSON. The callable datum-widget ``emit`` path remains
  internal and is not part of this controller action packet.

Engine interpretation
---------------------

For the targeted datum only, the engine invokes the lifecycle widget with:

    q["signal"] == {"kind": signal.kind, "info": signal.info}

All other touched datums in the same fill packet see the ordinary fill signal:

    q["signal"] == {"kind": "fill", "info": {}}

Signal-only packets are legal. They evaluate the targeted lifecycle datum using
its current working/existing fill as the candidate fill.
"""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    assert_dead_json,
)

from __exceptions.engine import InvalidExternalFillError


CONTROLLER_ACTION_PACKET_KIND_V1 = "controller_action_packet_v1"
CONTROLLER_DATUM_SIGNAL_KIND_V1 = "controller_datum_signal_v1"


@dataclass(frozen=True, slots=True)
class ControllerDatumSignalV1:
    datum_id: str
    kind: str
    info: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ControllerActionPacketV1:
    fill: Dict[str, Any]
    signal: Optional[ControllerDatumSignalV1] = None


def controller_action_packet_to_dict_v1(
    packet: ControllerActionPacketV1,
) -> Dict[str, Any]:
    """Return the canonical dead-JSON event/public representation of ``A``."""
    if not isinstance(packet, ControllerActionPacketV1):
        raise TypeError("packet must be ControllerActionPacketV1")

    return {
        "fill": dict(packet.fill),
        "signal": (
            None
            if packet.signal is None
            else {
                "datum_id": packet.signal.datum_id,
                "kind": packet.signal.kind,
                "info": dict(packet.signal.info),
            }
        ),
    }


def normalize_controller_datum_signal_v1(
    signal: Optional[Mapping[str, Any]],
) -> Optional[ControllerDatumSignalV1]:
    if signal is None:
        return None

    if not isinstance(signal, Mapping):
        raise InvalidExternalFillError("controller signal must be a mapping")

    raw = dict(signal)

    datum_id = str(raw.get("datum_id") or raw.get("target") or "").strip()
    if not datum_id:
        raise InvalidExternalFillError(
            "controller signal must include non-empty datum_id"
        )

    kind = str(raw.get("kind") or "").strip()
    if not kind:
        raise InvalidExternalFillError(
            "controller signal must include non-empty kind"
        )

    info_raw = raw.get("info")
    if info_raw is None:
        info: Dict[str, Any] = {}
    elif isinstance(info_raw, Mapping):
        info = dict(info_raw)
    else:
        raise InvalidExternalFillError("controller signal.info must be a mapping")

    packet = {
        "kind": CONTROLLER_DATUM_SIGNAL_KIND_V1,
        "datum_id": datum_id,
        "signal_kind": kind,
        "info": info,
    }

    try:
        assert_dead_json(packet, path="controller_action.signal")
    except DeadJSONError as exc:
        raise InvalidExternalFillError(str(exc)) from exc

    return ControllerDatumSignalV1(
        datum_id=datum_id,
        kind=kind,
        info=info,
    )


def normalize_controller_action_packet_v1(
    *,
    fill: Optional[Mapping[str, Any]] = None,
    signal: Optional[Mapping[str, Any]] = None,
) -> ControllerActionPacketV1:
    if fill is None:
        fill_out: Dict[str, Any] = {}
    elif isinstance(fill, Mapping):
        fill_out = dict(fill)
    else:
        raise InvalidExternalFillError("controller action fill must be a mapping")

    signal_out = normalize_controller_datum_signal_v1(signal)

    packet = {
        "kind": CONTROLLER_ACTION_PACKET_KIND_V1,
        "fill": fill_out,
        "signal": (
            None
            if signal_out is None
            else {
                "datum_id": signal_out.datum_id,
                "kind": signal_out.kind,
                "info": signal_out.info,
            }
        ),
    }

    try:
        assert_dead_json(packet, path="controller_action_packet")
    except DeadJSONError as exc:
        raise InvalidExternalFillError(str(exc)) from exc

    return ControllerActionPacketV1(
        fill=fill_out,
        signal=signal_out,
    )


def controller_signal_to_engine_dict_v1(
    signal: Optional[ControllerDatumSignalV1],
) -> Optional[Dict[str, Any]]:
    if signal is None:
        return None

    return {
        "datum_id": signal.datum_id,
        "kind": signal.kind,
        "info": dict(signal.info),
    }


__all__ = [
    "CONTROLLER_ACTION_PACKET_KIND_V1",
    "CONTROLLER_DATUM_SIGNAL_KIND_V1",
    "ControllerActionPacketV1",
    "ControllerDatumSignalV1",
    "controller_action_packet_to_dict_v1",
    "controller_signal_to_engine_dict_v1",
    "normalize_controller_action_packet_v1",
    "normalize_controller_datum_signal_v1",
]