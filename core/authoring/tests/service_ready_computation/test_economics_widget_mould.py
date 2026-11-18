from types import SimpleNamespace
import pytest
from wallet_economics.usage import VendorUsage, VendorReceipt
from epsilinesTM_serveragnostic.subapps.economics import bind_provider_v1
from epsilinesTM_serveragnostic.subapps.economics.contracts import *
from epsilinesTM_serveragnostic.subapps.economics.template_thinkwidget_economics_powered import (
    EconomicsPoweredDatumLifecycleWidget,
)
from .test_economics_pricing import DESCRIPTOR


class Provider:
    def __init__(self, status="held", created=True):
        self.status = status
        self.created = created
        self.calls = []
        self.settled = False

    def reserve(self, request):
        self.calls.append("reserve")
        return ReservationReceipt(
            "reservation", self.status, 100, "policy", "hash", {}, self.created
        )

    def charge(self, rid, usage):
        self.calls.append("charge")
        self.settled = True
        return ChargeReceipt(
            charge_id="charge",
            reservation_id=rid,
            settlement_status="pending_reconciliation",
            estimated_microcredits=10,
            calculated_microcredits=None,
            charged_microcredits=10,
            refunded_microcredits=0,
            excess_microcredits=0,
            estimated_vendor_cost_usd="0.01",
            calculated_vendor_cost_usd=None,
            customer_price_usd="0.012",
            policy_version="policy",
            policy_hash="hash",
            correlation={},
        )

    def release(self, rid):
        self.calls.append("release")


def widget(cls=EconomicsPoweredDatumLifecycleWidget, emit=None):
    return cls(
        q={"form_id": "f", "frame_id": "fr", "span_id": "s", "datum_id": "d"},
        emit=emit or (lambda *args, **kwargs: None),
    )


def receipt(completeness="complete"):
    return VendorReceipt(
        "1",
        "example",
        "example.work.v1",
        None,
        None,
        {},
        {},
        None,
        "success",
        VendorUsage(
            "items.v1",
            {"item": 1} if completeness == "complete" else {},
            completeness,
            {},
        ),
        1,
    )


def scope(w):
    return w.reserve_vendor_usage_v1(
        descriptor=DESCRIPTOR, maximum_units={"item": 10}, call_key="answer"
    )


def test_scopes_commit_before_body_cleanup_and_private_state():
    p = Provider()
    w = widget()
    with bind_provider_v1(p):
        with scope(w) as reservation:
            assert p.calls == ["reserve"]
            reservation.charge(receipt())
    assert p.calls == ["reserve", "charge"]
    assert p.settled
    assert "reservation" not in w._state


def test_disabled_and_unknown_usage():
    with pytest.raises(EconomicsNotConfigured):
        with scope(widget()):
            pass
    p = Provider()
    with bind_provider_v1(p):
        with pytest.raises(VendorUsageUnavailable):
            with scope(widget()) as r:
                r.charge(receipt("unknown"))
    assert p.calls == ["reserve", "release"]


@pytest.mark.parametrize(
    "status,error",
    [
        ("held", OperationInProgress),
        ("charged", AlreadyCharged),
        ("released", ReservationClosed),
        ("expired", ReservationClosed),
    ],
)
def test_reentry_refuses_body(status, error):
    p = Provider(status, False)
    with bind_provider_v1(p), pytest.raises(error):
        with scope(widget()):
            raise AssertionError("must not execute")
    assert p.calls == ["reserve"]


def test_cleanup_preserves_original():
    p = Provider()

    def fail(rid):
        raise RuntimeError("cleanup")

    p.release = fail
    original = ValueError("body")
    with bind_provider_v1(p), pytest.raises(ValueError) as caught:
        with scope(widget()):
            raise original
    assert caught.value is original
    assert original.economics_cleanup_details == {"cleanup_error": "RuntimeError"}
