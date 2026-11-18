"""Unit tests for Promise[T] schema kind, normalization, compatibility, and validation."""
import pytest
from bindings2bindingsTM import (
    Str, Int, Float, Dict, List, Map, Nullable, Promise, Schema,
    normalize, compatible, validate, reconcile_common_schema,
    RuntimeValueError, CompilationError
)


def test_promise_schema_creation_and_normalization():
    p = Promise(Dict({"title": Str, "count": Int}))
    assert p.kind == "promise"
    assert p.item.kind == "dict"
    assert p.item.field_type("title").kind == "str"
    assert p.item.field_type("count").kind == "int"

    # JSON serialization
    serialized = p.to_json()
    assert serialized == {
        "kind": "promise",
        "item": {
            "kind": "dict",
            "fields": {
                "count": {"kind": "int"},
                "title": {"kind": "str"}
            }
        }
    }

    # Normalization from raw dict
    restored = normalize(serialized)
    assert restored == p
    assert compatible(p, restored)


def test_promise_compatibility_subtyping():
    p_exact = Promise(Dict({"a": Str}))
    p_same = Promise(Dict({"a": Str}))
    p_diff = Promise(Dict({"a": Int}))
    p_other = Promise(Str)

    assert compatible(p_exact, p_same)
    assert not compatible(p_exact, p_diff)
    assert not compatible(p_exact, p_other)

    # Raw value is not compatible with Promise
    assert not compatible(Dict({"a": Str}), p_exact)
    assert not compatible(p_exact, Dict({"a": Str}))


def test_promise_validation():
    schema = Promise(Dict({"score": Float}))

    # 1. Valid object with ref attribute (like AsyncWorkHandle)
    class MockHandle:
        def __init__(self, ref):
            self.ref = ref
            self.status = "ongoing"

    validate(MockHandle("task_123"), schema)

    # 2. Valid dictionary descriptor
    validate({"ref": "task_abc", "status": "ongoing"}, schema)

    # 3. Valid completed promise descriptor with valid result payload
    validate({"ref": "task_abc", "status": "success", "result": {"score": 98.5}}, schema)

    # 4. Invalid promise - missing ref
    with pytest.raises(RuntimeValueError, match="invalid_promise"):
        validate({"status": "ongoing"}, schema)

    # 5. Invalid promise - invalid result payload type
    with pytest.raises(RuntimeValueError):
        validate({"ref": "task_abc", "status": "success", "result": {"score": "not_a_float"}}, schema)


def test_promise_reconcile():
    p1 = Promise(Dict({"x": Int}))
    p2 = Promise(Dict({"x": Int}))
    reconciled = reconcile_common_schema(p1, p2)
    assert reconciled == p1
