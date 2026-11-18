from __future__ import annotations

from contextlib import contextmanager

from ..core.operations import (
    AccountedVendorOperation,
    ReservationScope,
)
from .economics import EconomicsWidgetMixin
from .analytics.template_thinkwidget_analytics_powered import (
    AnalyticaPoweredDatumLifecycleWidget,
)

# Preserve alias for backward compatibility and internal widget methods
_AccountedOperation = AccountedVendorOperation


class ServiceReadyWidget(
    EconomicsWidgetMixin, AnalyticaPoweredDatumLifecycleWidget
):
    @contextmanager
    def vendor_operation_v1(
        self, *, descriptor, maximum_units, call_key, ttl_seconds=900, attribution=None
    ):
        with self.reserve_vendor_usage_v1(
            descriptor=descriptor,
            maximum_units=maximum_units,
            call_key=call_key,
            ttl_seconds=ttl_seconds,
            attribution=attribution,
        ) as reservation:
            with self.audit_vendor_usage_v1(
                vendor=descriptor.vendor,
                operation=descriptor.operation,
                request=descriptor.to_json(),
                attributes={"vendor_call_id": reservation.receipt.reservation_id},
            ) as span:
                operation = _AccountedOperation(reservation, span)
                try:
                    yield operation
                except BaseException as exc:
                    receipt = getattr(exc, "receipt", None)
                    if receipt is not None and hasattr(receipt, "to_json"):
                        operation.record(receipt)
                    raise

    def execute_vendor_operation_v1(
        self,
        prepared,
        *,
        client,
        maximum_units,
        call_key,
        ttl_seconds=900,
        attribution=None,
    ):
        from storagics.context import enabled, get_provider
        if enabled():
            storage = get_provider()
            if hasattr(storage, "renew_work"):
                storage.renew_work(ttl_seconds)
        capability = getattr(prepared, "asset_capability", None)
        if capability is not None and capability.forecast_assets() is not None:
            from .storagics import execute_managed_delivery
            return execute_managed_delivery(self, prepared, client=client, maximum_units=maximum_units,
                                            call_key=call_key, ttl_seconds=ttl_seconds, attribution=attribution,
                                            capability=capability)
        with self.vendor_operation_v1(
            descriptor=prepared.descriptor,
            maximum_units=maximum_units,
            call_key=call_key,
            ttl_seconds=ttl_seconds,
            attribution=attribution,
        ) as operation:
            result = prepared.execute(client=client)
            operation.record(result.receipt)
            if result.receipt.outcome == "success":
                operation.charge(result.receipt)
            else:
                operation.platform_paid("operation_failed", result.receipt.to_json())
                from wallet_economics.usage import VendorOperationError

                raise VendorOperationError("operation_failed", result.receipt)
            return result
