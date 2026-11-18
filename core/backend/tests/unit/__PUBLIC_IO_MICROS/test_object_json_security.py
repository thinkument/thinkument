from __future__ import annotations

from dataclasses import dataclass

import pytest

from _thinkprogram._iomicrosTM.core.api_object_json import dump_object_json, load_object_json


@dataclass
class Example:
    x: int

    @classmethod
    def from_json(cls, data):
        return cls(x=int(data["x"]))


def test_untagged_payload_is_pass_through() -> None:
    payload = {"x": 1}
    assert load_object_json(payload) is payload


def test_tagged_payload_is_deny_by_default() -> None:
    payload = dump_object_json(Example(3), tag_class=True)
    with pytest.raises(ValueError, match="deny-by-default"):
        load_object_json(payload)


def test_class_registry_reconstruction_does_not_need_dynamic_import() -> None:
    payload = dump_object_json(Example(3), tag_class=True)
    class_path = payload["__class__"]
    out = load_object_json(payload, class_registry={class_path: Example})
    assert out == Example(3)


def test_tagged_payload_rejects_extra_control_keys() -> None:
    payload = dump_object_json(Example(3), tag_class=True)
    payload["extra"] = True
    with pytest.raises(ValueError, match="may contain only"):
        load_object_json(payload, class_registry={payload["__class__"]: Example})
