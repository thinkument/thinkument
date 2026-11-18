from __future__ import annotations

"""Widget-agnostic economics and accounted execution contracts and exceptions."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Dict, Protocol

from .validation import frozen_json, identifier, integer, plain, units


class EconomicsError(RuntimeError):
    """Base error for economics and credit operations."""

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.details = plain(frozen_json(details or {"code": type(self).__name__}))
        super().__init__(message or type(self).__name__)


from .registry import (
    EpsChannelValidationError,
    InvalidEpsChannelSpecificationError,
)


class EconomicsNotConfigured(EconomicsError):
    """Raised when an economics operation is attempted without a bound provider."""
    pass


class InsufficientCredits(EconomicsError):
    """Raised when an owner account lacks sufficient credits for a hold."""
    pass


class ReservationExpired(EconomicsError):
    """Raised when an existing reservation hold has expired."""
    pass


class ReservationClosed(EconomicsError):
    """Raised when attempting to operate on an already finalized reservation."""
    pass


class OperationInProgress(EconomicsError):
    """Raised when an operation with the same idempotency key is already running."""
    pass


class AlreadyCharged(EconomicsError):
    """Raised when a reservation has already been settled and charged."""
    pass


class IdempotencyConflict(EconomicsError):
    """Raised when a request conflicts with an existing idempotent record."""
    pass


class VendorUsageUnavailable(EconomicsError):
    """Raised when vendor usage metrics cannot be extracted or resolved."""
    pass


class PricingError(EconomicsError):
    """Raised when rate card lookup or calculation fails."""
    pass


class CannotReadTransientEpsChannelError(RuntimeError):
    """Raised when attempting to read from an epsiline channel with mode=MODE_NONE."""
    pass


class EpsReadPermissionDeniedError(PermissionError):
    """Raised when attempting to read epsilines outside authorized tenant/ownership scope."""
    pass


class EpsReaderNotConfigured(RuntimeError):
    """Raised when `read_eps_v1` is invoked without an active ambient reader bound."""
    pass


class VendorOperationError(Exception):
    """Raised when a vendor invocation fails during accounted execution."""

    def __init__(self, reason: str, receipt: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.receipt = receipt


@dataclass(frozen=True)
class ReservationRequest:
    """Widget-agnostic reservation request specifying bounded resource limits."""

    descriptor: Any
    maximum_units: Mapping[str, int]
    call_key: str
    ttl_seconds: int = 900
    attribution: Mapping[str, Any] | None = None
    widget_identity: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.descriptor is None:
            raise ValueError("descriptor required")
        identifier(self.call_key)
        integer(self.ttl_seconds)
        if not 1 <= self.ttl_seconds <= 86400:
            raise ValueError("TTL must be 1..86400 seconds")
        object.__setattr__(self, "maximum_units", units(self.maximum_units))
        for k in ("attribution", "widget_identity"):
            val = getattr(self, k)
            if val is not None and not isinstance(val, Mapping):
                raise ValueError(f"{k} must be an object")
            object.__setattr__(self, k, frozen_json(val or {}, maximum=4096))

    def to_json(self) -> Dict[str, Any]:
        desc = (
            self.descriptor.to_json()
            if hasattr(self.descriptor, "to_json")
            else dict(self.descriptor)
        )
        return {
            "descriptor": desc,
            "maximum_units": dict(self.maximum_units),
            "call_key": self.call_key,
            "ttl_seconds": self.ttl_seconds,
            "attribution": dict(self.attribution) if self.attribution else {},
            "widget_identity": dict(self.widget_identity) if self.widget_identity else {},
        }


class EconomicsProvider(Protocol):
    """Protocol for provider engines performing reservations, charges, and releases."""

    def reserve(self, request: ReservationRequest) -> Any: ...
    def charge(self, reservation_id: str, usage: Any) -> Any: ...
    def release(self, reservation_id: str) -> Any: ...
    def settlement_state(self, reservation_id: str, *, release: bool = False) -> str: ...


__all__ = [
    "AlreadyCharged",
    "CannotReadTransientEpsChannelError",
    "EconomicsError",
    "EconomicsNotConfigured",
    "EconomicsProvider",
    "EpsChannelValidationError",
    "EpsReaderNotConfigured",
    "EpsReadPermissionDeniedError",
    "IdempotencyConflict",
    "InsufficientCredits",
    "InvalidEpsChannelSpecificationError",
    "OperationInProgress",
    "PricingError",
    "ReservationClosed",
    "ReservationExpired",
    "ReservationRequest",
    "VendorOperationError",
    "VendorUsageUnavailable",
]
