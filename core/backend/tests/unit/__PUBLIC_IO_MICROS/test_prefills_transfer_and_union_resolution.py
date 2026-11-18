from __future__ import annotations

import pytest

from _thinkprogram._iomicrosTM.core.api_prefills import (
    FormFillsAPIError,
    FormFillsBundleV1,
    transfer_values_by_ref_map,
)


def _box(value, micro_type: str) -> dict:
    return {"__boxed__": True, "value": value, "micro_type": micro_type}


def test_union_resolver_requires_box_for_ambiguous_string() -> None:
    resolver = lambda _sink, _micro: ("integer", "text")
    with pytest.raises(FormFillsAPIError, match="ambiguous micro type"):
        FormFillsBundleV1.from_any(fills={"S": "12"}, micro_resolver=resolver)

    bundle = FormFillsBundleV1.from_any(
        fills={"S": _box("12", "integer")},
        micro_resolver=resolver,
    )
    assert bundle.fills.get_value("S") == 12
    assert bundle.fills.get_box("S")["micro_type"] == "integer"
    assert bundle.fills.get_box("S")["__boxed__"] is True


def test_explicit_box_can_self_describe_without_resolver() -> None:
    bundle = FormFillsBundleV1.from_any(
        fills={"S": _box("12", "integer")},
    )
    assert bundle.fills.get_value("S") == 12
    assert bundle.fills.get_box("S")["micro_type"] == "integer"


def test_untyped_input_without_resolver_is_canonical_text() -> None:
    bundle = FormFillsBundleV1.from_any(fills={"S": 12})
    assert bundle.fills.get_value("S") == "12"
    assert bundle.fills.get_box("S")["micro_type"] == "text"


def test_typed_scalar_can_disambiguate_union() -> None:
    resolver = lambda _sink, _micro: ("boolean", "text")
    bundle = FormFillsBundleV1.from_any(fills={"S": True}, micro_resolver=resolver)
    assert bundle.fills.get_box("S")["micro_type"] == "boolean"


def test_transfer_can_use_declared_micro_coercion_when_destination_type_differs() -> None:
    src_resolver = lambda _sink, _micro: "integer"
    dst_resolver = lambda _sink, _micro: "number"
    src = FormFillsBundleV1.from_any(fills={"A": 12}, micro_resolver=src_resolver)
    dst = FormFillsBundleV1.from_any(micro_resolver=dst_resolver)

    transfer_values_by_ref_map(
        src=src,
        dst=dst,
        ref_map={"B.value": "A.value"},
        src_resolver=src_resolver,
        dst_resolver=dst_resolver,
    )
    assert dst.fills.get_value("B") == 12
    assert dst.fills.get_box("B")["micro_type"] == "number"


def test_transfer_rejects_undeclared_type_conversion() -> None:
    src_resolver = lambda _sink, _micro: "json_object"
    dst_resolver = lambda _sink, _micro: "integer"
    src = FormFillsBundleV1.from_any(
        fills={"A": _box({"x": 1}, "json_object")},
        micro_resolver=src_resolver,
    )
    dst = FormFillsBundleV1.from_any(micro_resolver=dst_resolver)
    with pytest.raises(FormFillsAPIError, match="cannot transfer"):
        transfer_values_by_ref_map(
            src=src,
            dst=dst,
            ref_map={"B.value": "A.value"},
            src_resolver=src_resolver,
            dst_resolver=dst_resolver,
        )
