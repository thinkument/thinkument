from dataclasses import replace

import pytest

from wallet_economics.usage import VendorUsage, VendorResult
from epsilinesTM_serveragnostic.subapps.economics import bind_provider_v1
from epsilinesTM_serveragnostic.subapps.economics.contracts import VendorUsageUnavailable
from epsilinesTM_serveragnostic.subapps.base import ServiceReadyWidget
from .test_economics_widget_mould import Provider, widget, receipt
from .test_economics_pricing import DESCRIPTOR


def pending(*, resolver=True):
    details = (
        {"resolver_reference": {"generation_id": "gen_123"}}
        if resolver
        else {}
    )
    return replace(
        receipt(),
        usage=VendorUsage("items.v1", {}, "unknown", details),
    )


def test_pending_receipt_is_charged_without_inline_resolution():
    executions = []

    class Prepared:
        descriptor = DESCRIPTOR

        def execute(self, *, client):
            executions.append("execute")
            return VendorResult("output", pending())

    provider = Provider()
    target = widget(ServiceReadyWidget)
    with bind_provider_v1(provider):
        from .test_accounted_widget_mould import run

        result = run(
            target,
            lambda: target.execute_vendor_operation_v1(
                Prepared(),
                client=None,
                maximum_units={"item": 10},
                call_key="pending-cost",
            ),
        )

    assert result.value == "output"
    assert executions == ["execute"]
    assert provider.calls == ["reserve", "charge"]


def test_incomplete_receipt_without_resolver_is_rejected():
    class Prepared:
        descriptor = DESCRIPTOR

        def execute(self, *, client):
            return VendorResult("output", pending(resolver=False))

    provider = Provider()
    target = widget(ServiceReadyWidget)
    with bind_provider_v1(provider), pytest.raises(VendorUsageUnavailable):
        from .test_accounted_widget_mould import run

        run(
            target,
            lambda: target.execute_vendor_operation_v1(
                Prepared(),
                client=None,
                maximum_units={"item": 10},
                call_key="missing-resolver",
            ),
        )
    assert provider.calls == ["reserve", "release"]


def test_failed_result_never_returns_success_or_charges():
    from wallet_economics.usage import VendorOperationError
    from .test_accounted_widget_mould import run

    class Prepared:
        descriptor = DESCRIPTOR

        def execute(self, *, client):
            return VendorResult(None, replace(receipt(), outcome="refused"))

    provider = Provider()
    target = widget(ServiceReadyWidget)
    with bind_provider_v1(provider), pytest.raises(VendorOperationError):
        run(
            target,
            lambda: target.execute_vendor_operation_v1(
                Prepared(), client=None, maximum_units={"item": 10}, call_key="refused"
            ),
        )
    assert "charge" not in provider.calls
