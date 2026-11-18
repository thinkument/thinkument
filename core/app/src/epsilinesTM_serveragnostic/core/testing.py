from __future__ import annotations

"""Test helpers and test fakes for epsilinesTM_serveragnostic."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping
from uuid import uuid4


@dataclass(frozen=True)
class FakeReservationReceipt:
    reservation_id: str
    status: str
    reserved_microcredits: int
    policy_version: str
    policy_hash: str
    correlation: Mapping[str, Any]
    created: bool

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FakeChargeReceipt:
    charge_id: str
    reservation_id: str
    settlement_status: str
    estimated_microcredits: int
    calculated_microcredits: int | None
    charged_microcredits: int
    refunded_microcredits: int
    excess_microcredits: int
    estimated_vendor_cost_usd: str
    calculated_vendor_cost_usd: str | None
    customer_price_usd: str
    policy_version: str
    policy_hash: str
    correlation: Mapping[str, Any]
    status: str = "charged"

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


class FakeEconomicsProvider:
    """In-memory EconomicsProvider implementation for unit tests."""

    def __init__(self, *, default_balance: int = 10_000_000_000_000) -> None:
        self.balance = default_balance
        self.reservations: Dict[str, Any] = {}
        self.charges: Dict[str, Any] = {}
        self.releases: List[str] = []
        self.incidents: List[Dict[str, Any]] = []

    def reserve(self, request: Any) -> FakeReservationReceipt:
        res_id = f"res-{uuid4().hex[:12]}"
        receipt = FakeReservationReceipt(
            reservation_id=res_id,
            status="held",
            reserved_microcredits=100_000_000,
            policy_version="v1",
            policy_hash="test-hash",
            correlation=dict(request.attribution) if hasattr(request, "attribution") else {},
            created=True,
        )
        self.reservations[res_id] = {
            "request": request,
            "receipt": receipt,
            "status": "held",
        }
        return receipt

    def charge(self, reservation_id: str, usage: Any) -> FakeChargeReceipt:
        charge_id = f"chg-{uuid4().hex[:12]}"
        actual = getattr(usage, "actual_cost_microcredits", None) or 50_000_000
        held = self.reservations[reservation_id]["receipt"].reserved_microcredits
        charged = min(held, actual)
        excess = max(0, actual - held)
        refunded = held - charged
        receipt = FakeChargeReceipt(
            charge_id=charge_id,
            reservation_id=reservation_id,
            settlement_status="settled",
            estimated_microcredits=held,
            calculated_microcredits=actual,
            charged_microcredits=charged,
            refunded_microcredits=refunded,
            excess_microcredits=excess,
            estimated_vendor_cost_usd="0.1",
            calculated_vendor_cost_usd="0.050000",
            customer_price_usd="0.050000",
            policy_version="v1",
            policy_hash="test-hash",
            correlation={},
            status="charged",
        )
        self.charges[charge_id] = receipt
        self.reservations[reservation_id]["status"] = "charged"
        return receipt

    def release(self, reservation_id: str) -> FakeReservationReceipt:
        self.releases.append(reservation_id)
        if reservation_id in self.reservations:
            self.reservations[reservation_id]["status"] = "released"
        return FakeReservationReceipt(
            reservation_id=reservation_id,
            status="released",
            reserved_microcredits=0,
            policy_version="v1",
            policy_hash="test-hash",
            correlation={},
            created=False,
        )

    def platform_paid(self, reservation_id: str, reason: str, evidence: Any = None) -> FakeReservationReceipt:
        self.incidents.append({
            "reservation_id": reservation_id,
            "reason": reason,
            "evidence": deepcopy(evidence),
        })
        return self.release(reservation_id)

    def settlement_state(self, reservation_id: str, *, release: bool = False) -> str:
        if reservation_id not in self.reservations:
            return "unknown"
        state = self.reservations[reservation_id]["status"]
        if release and state == "held":
            self.release(reservation_id)
        return state


class RecordingEmitter:
    """Callable sink collecting emitted epsilon channels and envelopes."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def __call__(
        self,
        channel: str,
        envelope: Mapping[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "channel": str(channel),
            "envelope": deepcopy(dict(envelope)),
        }
        if kwargs:
            entry["meta"] = deepcopy(dict(kwargs))
        self.events.append(entry)
        return entry

    def by_channel(self, channel: str) -> List[Dict[str, Any]]:
        return [e["envelope"] for e in self.events if e["channel"] == channel]


__all__ = [
    "FakeChargeReceipt",
    "FakeEconomicsProvider",
    "FakeReservationReceipt",
    "RecordingEmitter",
]
