"""Pinned company policy and exact credit conversion."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from wallet_economics.rate_cards import (
    PricingError,
    decimal_string,
    usd_storage,
    validate_cards,
    select_card,
    RateCard,
)
from wallet_economics.validation import (
    fingerprint,
    frozen_json,
    plain,
    MAX_INTEGER,
    identifier,
)

_VERSION_HASHES = {}


@dataclass(frozen=True)
class Policy:
    snapshot: object
    content_hash: str
    cards: tuple

    def pin(self, descriptor):
        card = select_card(self.cards, descriptor)
        expected = descriptor.request_summary.get("usage_schema")
        if expected and expected != card.data["usage_schema"]:
            raise PricingError("usage profile does not match card")
        return {
            "version": self.snapshot["version"],
            "content_hash": self.content_hash,
            "credit_policy": plain(self.snapshot["credit_policy"]),
            "rate_card": plain(card.data),
        }


def load_policy(data):
    if not isinstance(data, Mapping) or set(data) != {
        "version",
        "credit_policy",
        "rate_cards",
    }:
        raise PricingError("invalid policy fields")
    try:
        identifier(data["version"])
    except ValueError as exc:
        raise PricingError("invalid policy version") from exc
    credit = data["credit_policy"]
    if not isinstance(credit, Mapping) or set(credit) != {
        "usd_per_credit",
        "default_markup",
    }:
        raise PricingError("invalid credit policy")
    decimal_string(credit["usd_per_credit"], positive=True)
    from wallet_economics.validation import amount

    try:
        amount(credit["default_markup"])
    except ValueError as exc:
        raise PricingError(str(exc)) from exc
    if any("markup" in c for c in data["rate_cards"]):
        raise PricingError("per-card markup is forbidden; use global markup")
    cards = validate_cards(data["rate_cards"])
    snapshot = frozen_json(data, maximum=1048576)
    digest = fingerprint(snapshot)
    old = _VERSION_HASHES.setdefault(data["version"], digest)
    if old != digest:
        raise PricingError(
            "policy version reused with different content; reload workers"
        )
    return Policy(snapshot, digest, cards)


def calculate(snapshot, quantities):
    card = RateCard(snapshot["rate_card"])
    vendor = card.cost(quantities)
    credit = snapshot["credit_policy"]
    from wallet_economics.pricing import PricingSnapshot

    pricing = PricingSnapshot(
        snapshot["version"], credit["default_markup"], credit["usd_per_credit"]
    )
    customer, micro = pricing.calculate(str(vendor))
    return vendor, customer, micro
