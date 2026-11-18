import pytest
from wallet_economics.usage import VendorResult, VendorOperationError
from epsilinesTM_serveragnostic.subapps.base import (
    ServiceReadyWidget,
)
from epsilinesTM_serveragnostic.subapps.economics import bind_provider_v1
from .test_economics_widget_mould import Provider, widget, receipt
from .test_economics_pricing import DESCRIPTOR


class Prepared:
    descriptor = DESCRIPTOR

    def execute(self, *, client):
        client()
        return VendorResult({"secret_output": True}, receipt())


class Probe(ServiceReadyWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        return self.execute_vendor_operation_v1(
            Prepared(),
            client=lambda: None,
            maximum_units={"item": 10},
            call_key="answer",
        )


def run(w, fn):
    return w._run_analytica_operation_v1(
        trigger="mount",
        fill_data={"fill_shell": {}, "current_fills": {}},
        signal=None,
        invoke=fn,
    )


def test_correlated_single_event_and_settlement():
    events = []
    w = widget(Probe, lambda payload, **kwargs: events.append(payload))
    p = Provider()
    with bind_provider_v1(p):
        run(w, lambda: w._on_mount.__wrapped__(w, {}, {}, {}, {}))
    vendor = [e for e in events if e.get("event") == "vendor_usage"]
    assert len(vendor) == 1
    body = vendor[0]["body"]
    assert body["usage"]["vendor_call_id"] == "reservation"
    assert body["usage"]["charge"]["charge_id"] == "charge"
    assert "secret_output" not in str(body)


def test_failure_receipt_and_uncharged_release():
    events = []
    w = widget(
        ServiceReadyWidget, lambda payload, **kwargs: events.append(payload)
    )
    p = Provider()

    def execute():
        with w.vendor_operation_v1(
            descriptor=DESCRIPTOR, maximum_units={"item": 10}, call_key="answer"
        ):
            raise VendorOperationError("incomplete", receipt())

    with bind_provider_v1(p), pytest.raises(VendorOperationError):
        run(w, execute)
    assert p.calls == ["reserve", "release"]
    vendor = [e for e in events if e.get("event") == "vendor_usage"]
    assert len(vendor) == 1
    assert vendor[0]["body"]["usage"]["usage"]["completeness"] == "complete"
