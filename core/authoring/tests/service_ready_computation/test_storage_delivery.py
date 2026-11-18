import pytest
from storagics.context import bind_provider
from storagics.contracts import AssetForecast, AssetPayload, AssetReference
from wallet_economics.usage import VendorResult
from epsilinesTM_serveragnostic.subapps.economics import bind_provider_v1
from epsilinesTM_serveragnostic.subapps.base import ServiceReadyWidget
from .test_economics_widget_mould import Provider, widget, receipt
from .test_economics_pricing import DESCRIPTOR
from .test_accounted_widget_mould import run


class Capability:
    def forecast_assets(self): return AssetForecast(1, 10, 100)
    def extract_assets(self, value, *, maximum_bytes): return [AssetPayload(b"media", "image/png")]
    def replace_assets(self, value, references): return {"url": references[0].url}


class Prepared:
    descriptor = DESCRIPTOR
    asset_capability = Capability()
    def execute(self, *, client):
        client()
        return VendorResult({"base64": "raw"}, receipt())


class Storage:
    def __init__(self, wallet, *, fail=False):
        self.wallet, self.failure = wallet, fail
        self.calls = []
    def begin(self, **kwargs):
        self.calls.append("reserve")
        assert not self.wallet.calls
        return {"delivery_id": "delivery", "created": True}
    def attach_wallet(self, *args): self.calls.append("wallet")
    def dispatched(self, *args): self.calls.append("dispatch")
    def store(self, *args):
        self.calls.append("store")
        assert "charge" not in self.wallet.calls
        if self.failure: raise OSError("write failed")
        return [AssetReference("asset", "/private/asset", "image/png", 5)]
    def ready(self, *args):
        self.calls.append("ready")
        assert "charge" not in self.wallet.calls
    def complete(self, *args):
        assert "charge" in self.wallet.calls
        self.calls.append("complete")
    def fail(self, *args): self.calls.append("fail")


def test_assets_are_ready_before_customer_settlement():
    wallet = Provider()
    storage = Storage(wallet)
    events = []
    w = widget(ServiceReadyWidget, lambda payload, **kw: events.append(payload))
    with bind_provider_v1(wallet), bind_provider(storage):
        result = run(w, lambda: w.execute_vendor_operation_v1(Prepared(), client=lambda: None, maximum_units={"item": 10}, call_key="media"))
    assert result.value == {"url": "/private/asset"}
    assert storage.calls == ["reserve", "wallet", "dispatch", "store", "ready", "complete"]
    assert any(event["channel"] == "audit-storage-usage" for event in events)


def test_storage_failure_never_charges_customer():
    wallet = Provider()
    storage = Storage(wallet, fail=True)
    w = widget(ServiceReadyWidget)
    with bind_provider_v1(wallet), bind_provider(storage), pytest.raises(OSError):
        run(w, lambda: w.execute_vendor_operation_v1(Prepared(), client=lambda: None, maximum_units={"item": 10}, call_key="media"))
    assert "charge" not in wallet.calls
    assert storage.calls[-1] == "fail"


def test_media_cannot_fall_back_to_unstored_output():
    from storagics.contracts import StorageNotConfigured
    wallet = Provider()
    w = widget(ServiceReadyWidget)
    with bind_provider_v1(wallet), bind_provider(None, required=False), pytest.raises(StorageNotConfigured):
        run(w, lambda: w.execute_vendor_operation_v1(Prepared(), client=lambda: None, maximum_units={"item": 10}, call_key="media"))
    assert wallet.calls == []
