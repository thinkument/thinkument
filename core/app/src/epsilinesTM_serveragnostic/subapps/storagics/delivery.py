"""One call plus its required assets is delivered before the customer is charged."""
from dataclasses import replace
from storagics.context import get_provider
from storagics.contracts import fingerprint, DeliveryInProgress, DeliveryFailed
from wallet_economics.usage import VendorResult, VendorReceipt, VendorOperationError


def execute_managed_delivery(widget, prepared, *, client, maximum_units, call_key, ttl_seconds, attribution, capability):
    storage = get_provider()
    identity = widget._economics_widget_identity_v1()
    key = fingerprint({"call_key": call_key, "widget": identity})
    state = storage.begin(call_key=key, request_fingerprint=prepared.descriptor.request_fingerprint,
                          forecast=capability.forecast_assets(), ttl_seconds=ttl_seconds)
    delivery_id = state["delivery_id"]
    if not state["created"]:
        if state["state"] == "complete":
            return VendorResult(state["result"], VendorReceipt.from_json(state["receipt"]))
        if state["state"] in ("failed", "cleanup"):
            raise DeliveryFailed(delivery_id=delivery_id)
        raise DeliveryInProgress(delivery_id=delivery_id)
    try:
        with widget.vendor_operation_v1(descriptor=prepared.descriptor, maximum_units=maximum_units,
                                        call_key=call_key, ttl_seconds=ttl_seconds, attribution=attribution) as operation:
            storage.attach_wallet(delivery_id, operation._reservation.receipt.reservation_id)
            storage.dispatched(delivery_id)
            result = prepared.execute(client=client)
            operation.record(result.receipt)
            if result.receipt.outcome != "success":
                raise VendorOperationError("operation_failed", result.receipt)
            forecast = capability.forecast_assets()
            payloads = capability.extract_assets(result.value, maximum_bytes=forecast.maximum_bytes)
            refs = storage.store(delivery_id, payloads)
            value = capability.replace_assets(result.value, refs)
            storage.ready(delivery_id, value, result.receipt.to_json())
            operation.charge(result.receipt)
            storage.complete(delivery_id)
            # The durable outbox remains authoritative if this optional inline
            # audit emission fails or the surrounding run transaction rolls back.
            try:
                widget.audit_event_v1(channel="audit-storage-usage", schema="thinkwidget.storage-usage.v1", event="storage-usage",
                                      body={"kind": "delivered", "delivery_id": delivery_id,
                                            "vendor_call_id": operation._reservation.receipt.reservation_id,
                                            "asset_ids": [ref.asset_id for ref in refs],
                                            "actual_bytes": sum(ref.size_bytes for ref in refs)})
            except Exception:
                pass
            return replace(result, value=value)
    except BaseException as exc:
        # Host checks durable wallet truth before permitting any object cleanup.
        # Unknown settlement leaves the delivery recoverable and its assets held.
        try:
            storage.fail(delivery_id)
        except Exception as cleanup:
            if hasattr(exc, "details") and isinstance(exc.details, dict):
                exc.details["storage_recovery_error"] = type(cleanup).__name__
                exc.details["delivery_id"] = delivery_id
        raise
