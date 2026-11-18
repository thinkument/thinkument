from __future__ import annotations

import json
from pathlib import Path

from _thinkprogram._iomicrosTM.core.api_introspection import (
    CATALOG_SCHEMA,
    build_micro_publication_catalog,
    decode_python_example,
)
from _thinkprogram._iomicrosTM.core.micro_registry import list_public_micro_types
from _thinkprogram._iomicrosTM.core.micro_validator_registry import get_callable_by_path
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json


def test_publication_catalog_is_complete_deterministic_and_executable(tmp_path: Path) -> None:
    catalog_a = build_micro_publication_catalog()
    catalog_b = build_micro_publication_catalog()
    assert catalog_a == catalog_b
    assert catalog_a["schema"] == CATALOG_SCHEMA
    assert set(catalog_a["micros"]) == set(list_public_micro_types())
    assert len(catalog_a["micros"]) >= 20
    assert len(catalog_a["registered_validators"]) >= 20
    assert catalog_a["macro_validators"]
    assert_dead_json(catalog_a)

    registered = set(catalog_a["registered_validators"])
    for micro_name, record in catalog_a["micros"].items():
        assert record["name"] == micro_name
        assert record["python_types"]
        for destination in record["coerce_to_micro_types"]:
            assert destination in catalog_a["micros"]
        for policy in record["validators"]:
            assert policy["path"] in registered
            assert callable(get_callable_by_path(policy["path"]))

    for path, record in catalog_a["registered_validators"].items():
        validator = get_callable_by_path(path)
        guidance = get_callable_by_path(record["guidance_path"])
        for combo in record["argument_combinations"]:
            kwargs = dict(combo["args"])
            for encoded in combo["valid_examples"]:
                assert validator(decode_python_example(encoded), **kwargs) == (True, None)
            for encoded in combo["invalid_examples"]:
                ok, message = validator(decode_python_example(encoded), **kwargs)
                assert ok is False
                assert isinstance(message, str) and message.strip()
            assert guidance(**kwargs)["message"].strip()

    output = tmp_path / "micros.publication.json"
    encoded = json.dumps(catalog_a, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    output.write_text(encoded + "\n", encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8")) == catalog_a
    assert json.dumps(json.loads(encoded), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) == encoded


def test_example_encoding_does_not_reserve_keys_inside_real_json() -> None:
    from _thinkprogram._iomicrosTM.core.api_introspection import encode_python_example

    literal = {"$python": "this-is-user-data", "value": [1, 2, 3]}
    assert decode_python_example(encode_python_example(literal)) == literal
