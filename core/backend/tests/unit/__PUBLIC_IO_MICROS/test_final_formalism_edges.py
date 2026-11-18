from __future__ import annotations

import _thinkprogram._iomicrosTM.validators  # noqa: F401

from _thinkprogram._iomicrosTM.core.api_introspection import build_micro_publication_catalog
from _thinkprogram._iomicrosTM.core.micro_validator_registry import registered_validator_paths
from _thinkprogram._iomicrosTM.validators.date import is_iso_time
from _thinkprogram._iomicrosTM.validators.datum import (
    fields_equal,
    require_field_if_equals,
    total_words_max,
)


def test_macro_only_validators_are_not_leaf_registered() -> None:
    registered = set(registered_validator_paths())
    assert "_thinkprogram._iomicrosTM.validators.text:total_words_max" not in registered
    assert "_thinkprogram._iomicrosTM.validators.datum:total_words_max" not in registered

    catalog = build_micro_publication_catalog()
    assert "_thinkprogram._iomicrosTM.validators.datum:total_words_max" in catalog["macro_validators"]
    assert catalog["macro_validators"][
        "_thinkprogram._iomicrosTM.validators.datum:total_words_max"
    ]["description"]


def test_macro_validators_compare_explicit_boxed_semantic_values() -> None:
    macro = {
        "a": {"__boxed__": True, "value": "same"},
        "b": "same",
        "mode": {"__boxed__": True, "value": "advanced"},
        "detail": {"__boxed__": True, "value": "present"},
    }
    assert fields_equal(macro, fields=["a", "b"]) == (True, None)
    assert require_field_if_equals(
        macro,
        when_field="mode",
        equals="advanced",
        required_field="detail",
    ) == (True, None)


def test_total_words_max_is_a_datum_rule() -> None:
    macro = {
        "title": {"__boxed__": True, "value": "one two"},
        "body": "three four",
        "count": 99,
    }
    assert total_words_max(macro, max_words=4) == (True, None)
    ok, message = total_words_max(macro, max_words=3)
    assert ok is False
    assert message == "total words must be <= 3"


def test_local_time_rejects_timezone_bearing_values() -> None:
    assert is_iso_time("09:30") == (True, None)
    assert is_iso_time("09:30:15.123") == (True, None)
    assert is_iso_time("09:30Z")[0] is False
    assert is_iso_time("09:30+01:00")[0] is False
