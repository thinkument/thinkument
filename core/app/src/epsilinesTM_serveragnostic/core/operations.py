from __future__ import annotations

"""Universal accounted vendor operation runner."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Callable
from uuid import uuid4

from .context import get_provider_v1
from .contracts import (
    AlreadyCharged,
    OperationInProgress,
    ReservationClosed,
    ReservationRequest,
    VendorOperationError,
    VendorUsageUnavailable,
)
from .spans import VendorUsageSpan


class ReservationScope:
    """Manages the lifecycle of a held economics credit reservation."""

    def __init__(self, provider: Any, receipt: Any) -> None:
        self._provider = provider
        self.receipt = receipt
        self.charge_receipt = None
        self._settled = False

    def charge(
        self, receipt: Any, *, original_operation_id: str | None = None
    ) -> Any:
        outcome = getattr(receipt, "outcome", None)
        usage = getattr(receipt, "usage", None)
        completeness = getattr(usage, "completeness", None) if usage is not None else None
        provider_details = getattr(usage, "provider_details", None)
        resolver_reference = (
            provider_details.get("resolver_reference")
            if isinstance(provider_details, Mapping)
            else None
        )
        has_resolver_reference = (
            completeness in ("partial", "unknown")
            and isinstance(resolver_reference, Mapping)
            and bool(resolver_reference.get("generation_id"))
        )
        if outcome != "success" or usage is None or not (
            completeness == "complete" or has_resolver_reference
        ):
            self.platform_paid("cost_resolution_failed", {"error": "VendorUsageUnavailable"})
            raise VendorUsageUnavailable(
                "Receipt has neither complete usage nor a valid resolver_reference"
            )
        charge_receipt = receipt
        if original_operation_id and hasattr(receipt, "usage"):
            usage = receipt.usage
            provider_details = getattr(usage, "provider_details", None)
            if isinstance(provider_details, Mapping):
                details = dict(provider_details)
                details["original_operation_id"] = str(original_operation_id)
                try:
                    charge_receipt = replace(
                        receipt,
                        usage=replace(usage, provider_details=details),
                    )
                except TypeError:
                    charge_receipt = receipt
        self.charge_receipt = self._provider.charge(
            self.receipt.reservation_id, charge_receipt
        )
        self._settled = True
        return self.charge_receipt

    def platform_paid(self, reason: str, evidence: Any = None) -> Any:
        if self._settled:
            return None
        if hasattr(self._provider, "platform_paid"):
            self._settled = True
            return self._provider.platform_paid(
                self.receipt.reservation_id, reason, evidence
            )
        # Some minimal providers expose release only. Keep this fallback
        # idempotent while allowing release() to own the settled transition.
        return self.release()

    def release(self) -> Any:
        if self._settled:
            return None
        self._settled = True
        return self._provider.release(self.receipt.reservation_id)

    def __enter__(self) -> "ReservationScope":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        del exc_tb
        if not self._settled:
            if exc_type is not None:
                try:
                    self.platform_paid("operation_failed", {"error": getattr(exc_type, "__name__", str(exc_type))})
                except Exception:
                    pass
            else:
                self.release()
        return False


class AccountedVendorOperation:
    """Composite context combining an active ReservationScope and VendorUsageSpan."""

    def __init__(self, reservation: ReservationScope, span: VendorUsageSpan) -> None:
        self._reservation = reservation
        self._span = span
        self.receipt = None

    def record(self, receipt: Any) -> None:
        self.receipt = receipt
        data = receipt.to_json() if hasattr(receipt, "to_json") else dict(receipt)
        data["vendor_call_id"] = self._reservation.receipt.reservation_id
        if self._reservation.charge_receipt:
            charge_data = self._reservation.charge_receipt
            data["charge"] = charge_data.to_json() if hasattr(charge_data, "to_json") else dict(charge_data)
        self._span.set_usage(data)

    def charge(self, receipt: Any) -> Any:
        self.record(receipt)
        # The base telemetry span owns `_operation_id`; the framework-4-services adapter
        # supplies an equivalent `operation_id` property from its active
        # Analytica lifecycle.
        operation_id = getattr(self._span, "_operation_id", None)
        if operation_id is None:
            operation_id = getattr(self._span, "operation_id", None)
        charge = self._reservation.charge(
            receipt, original_operation_id=operation_id
        )
        self.record(receipt)
        return charge

    def platform_paid(self, reason: str, evidence: Any = None) -> Any:
        return self._reservation.platform_paid(reason, evidence)

    def release(self) -> Any:
        return self._reservation.release()


def _renew_storage_if_present(ttl_seconds: int) -> None:
    import importlib
    try:
        storagics_context = importlib.import_module("storagics.context")
        if storagics_context.enabled():
            storage = storagics_context.get_provider()
            if hasattr(storage, "renew_work"):
                storage.renew_work(ttl_seconds)
    except (ImportError, AttributeError):
        pass


def execute_accounted_vendor_operation(
    prepared: Any,
    *,
    client: Any,
    maximum_units: Mapping[str, int],
    call_key: str,
    ttl_seconds: int = 900,
    attribution: Mapping[str, Any] | None = None,
    emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
    caller_identity: str = "generic_caller",
    operation_id: str | None = None,
    storage_renew: bool = True,
) -> Any:
    """Executes a prepared vendor operation under full economics bounding and analytics telemetry.

    Compatible with ANY execution context:
    - DatumLifecycleWidget instances
    - General runtime plane callers (standalone functions, tasks)
    """
    if storage_renew:
        _renew_storage_if_present(ttl_seconds)

    descriptor = getattr(prepared, "descriptor", None)
    if descriptor is None:
        raise ValueError("prepared operation must possess a descriptor")

    provider = get_provider_v1()
    request = ReservationRequest(
        descriptor=descriptor,
        maximum_units=maximum_units,
        call_key=call_key,
        ttl_seconds=ttl_seconds,
        attribution=attribution,
    )
    receipt = provider.reserve(request)

    if not receipt.created:
        if receipt.status == "held":
            raise OperationInProgress("operation is already in progress")
        if receipt.status == "charged":
            raise AlreadyCharged("operation was already charged")
        raise ReservationClosed(f"reservation status '{receipt.status}' is finalized")

    reservation = ReservationScope(provider, receipt)
    op_id = operation_id or f"op-{uuid4().hex[:16]}"

    desc_dict = (
        descriptor.to_json()
        if hasattr(descriptor, "to_json")
        else dict(descriptor)
    )

    span = VendorUsageSpan(
        vendor=descriptor.vendor,
        operation=descriptor.operation,
        request=desc_dict,
        attributes={"vendor_call_id": receipt.reservation_id},
        emitter=emitter,
        caller_identity=caller_identity,
        operation_id=op_id,
    )

    with reservation:
        with span:
            op = AccountedVendorOperation(reservation, span)
            try:
                result = prepared.execute(client=client)
                op.record(result.receipt)
                if result.receipt.outcome == "success":
                    op.charge(result.receipt)
                    return result
                else:
                    rec_json = result.receipt.to_json() if hasattr(result.receipt, "to_json") else dict(result.receipt)
                    op.platform_paid("operation_failed", rec_json)
                    raise VendorOperationError("operation_failed", result.receipt)
            except BaseException as exc:
                err_receipt = getattr(exc, "receipt", None)
                if err_receipt is not None and hasattr(err_receipt, "to_json"):
                    op.record(err_receipt)
                raise


__all__ = [
    "AccountedVendorOperation",
    "ReservationScope",
    "execute_accounted_vendor_operation",
]
