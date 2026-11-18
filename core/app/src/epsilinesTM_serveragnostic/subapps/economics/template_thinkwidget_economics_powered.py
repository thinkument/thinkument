from contextlib import contextmanager
from ...core.operations import ReservationScope
from .context import get_provider_v1
from .contracts import (
    ReservationRequest,
    AlreadyCharged,
    OperationInProgress,
    ReservationClosed,
    VendorUsageUnavailable,
)


class EconomicsWidgetMixin:
    def _economics_widget_identity_v1(self):
        from _thinkprogram.thinkwidgetTM.runtime import _adapter_inputs_from_q

        position, *_ = _adapter_inputs_from_q(self._q, self._state)
        return {
            "widget_class": f"{type(self).__module__}:{type(self).__qualname__}",
            "position": position,
        }

    @contextmanager
    def reserve_vendor_usage_v1(
        self, *, descriptor, maximum_units, call_key, ttl_seconds=900, attribution=None
    ):
        provider = get_provider_v1()
        request = ReservationRequest(
            descriptor,
            maximum_units,
            call_key,
            ttl_seconds,
            attribution,
            self._economics_widget_identity_v1(),
        )
        receipt = provider.reserve(request)
        if not receipt.created:
            if receipt.status == "held":
                raise OperationInProgress()
            if receipt.status == "charged":
                raise AlreadyCharged()
            raise ReservationClosed()
        scope = ReservationScope(provider, receipt)
        try:
            yield scope
        except BaseException as exc:
            try:
                scope.platform_paid("operation_failed", {"error": type(exc).__name__})
            except Exception as cleanup:
                details = {"cleanup_error": type(cleanup).__name__}
                if hasattr(exc, "details") and isinstance(exc.details, dict):
                    exc.details.update(details)
                else:
                    exc.economics_cleanup_details = details
            raise
        else:
            scope.release()


from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget


class EconomicsPoweredDatumLifecycleWidget(EconomicsWidgetMixin, DatumLifecycleWidget):
    pass
