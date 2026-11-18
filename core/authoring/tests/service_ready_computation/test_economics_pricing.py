from copy import deepcopy
from decimal import Decimal
import pytest
from epsilinesTM_serveragnostic.subapps.economics.pricing import (
    load_policy,
    calculate,
)
from wallet_economics.usage import VendorCallDescriptor
from wallet_economics.rate_cards import PricingError

POLICY = {
    "version": "framework-test-1",
    "credit_policy": {"usd_per_credit": "0.01", "default_markup": "1.2"},
    "rate_cards": [
        {
            "id": "test",
            "vendor": "example",
            "operation": "example.work.v1",
            "usage_schema": "items.v1",
            "requested_model": None,
            "accepted_resolved_models": [None],
            "pricing_dimensions": {},
            "usd_per_unit": {"item": "0.000000000001"},
        }
    ],
}
DESCRIPTOR = VendorCallDescriptor(
    "1", "example.work.v1", "example", None, {}, "abc", {"usage_schema": "items.v1"}, {}
)


def test_round_once_and_pin():
    policy = load_policy(POLICY)
    pin = policy.pin(DESCRIPTOR)
    assert calculate(pin, {"item": 1}) == (
        Decimal("0.000000000001"),
        Decimal("0.0000000000012"),
        1,
    )
    changed = deepcopy(POLICY)
    changed["version"] = "framework-test-2"
    changed["credit_policy"]["default_markup"] = "2"
    load_policy(changed)
    assert calculate(pin, {"item": 1})[2] == 1


def test_same_version_different_hash():
    load_policy(POLICY)
    changed = deepcopy(POLICY)
    changed["credit_policy"]["default_markup"] = "2"
    with pytest.raises(PricingError):
        load_policy(changed)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("credit_policy", "usd_per_credit", "0"),
        ("credit_policy", "default_markup", "-1"),
        ("credit_policy", "usd_per_credit", 0.01),
    ],
)
def test_bad_credit_policy(section, key, value):
    changed = deepcopy(POLICY)
    changed[section][key] = value
    with pytest.raises(PricingError):
        load_policy(changed)


def test_overflow():
    changed = deepcopy(POLICY)
    changed["version"] = "framework-overflow"
    changed["rate_cards"][0]["usd_per_unit"]["item"] = "9999999999999999999"
    pin = load_policy(changed).pin(DESCRIPTOR)
    with pytest.raises(PricingError):
        calculate(pin, {"item": 100})


def test_global_markup_zero_and_no_card_overrides():
    changed=deepcopy(POLICY)
    changed["version"]="framework-zero-markup"
    changed["credit_policy"]["default_markup"]="0"
    assert calculate(load_policy(changed).pin(DESCRIPTOR),{"item":100})[2]==0
    changed["version"]="framework-forbidden-card-markup"
    changed["rate_cards"][0]["markup"]="1.4"
    with pytest.raises(PricingError): load_policy(changed)
