"""Version-qualified process identities preserve source manifest fingerprints."""

from authoring_funneling import compile_strict_program
from authoring_funneling.b_typed_JSON_widget_declaration import (
    prepare_json_widget_v1,
    register_prepared_json_widget_v1,
)


def test_runtime_identity_override_does_not_change_source_fingerprint():
    manifest = {
        "kind": "json_widget_v1",
        "name": "tests.version_identity",
        "declaration": {"outputs": {"result": {"accepted": "bool"}}},
        "signals": {
            "mount": {"outputs": {"result": {"accepted": False}}, "reexplode": {"title": "Review", "micros": [{"name": "decision", "type": "text"}]}},
            "fill": {"outputs": {"result": {"accepted": True}}, "done": True},
        },
    }
    original = prepare_json_widget_v1(manifest)
    v1 = prepare_json_widget_v1(manifest, widget_id="tests.version_identity:v1_0_0")
    v2 = prepare_json_widget_v1(manifest, widget_id="tests.version_identity:v1_0_1")
    attributed = prepare_json_widget_v1(
        manifest,
        widget_id="tests.version_identity:v1_0_0",
        publisher_user_id="publisher-42",
    )

    assert original.widget_id == "tests.version_identity"
    assert v1.widget_id == "tests.version_identity:v1_0_0"
    assert v2.widget_id == "tests.version_identity:v1_0_1"
    assert original.fingerprint == v1.fingerprint == v2.fingerprint
    assert attributed.fingerprint == v1.fingerprint
    assert attributed.widget_class._published_widget_version_id_v1 == v1.widget_id
    assert attributed.widget_class._published_widget_publisher_user_id_v1 == "publisher-42"

    register_prepared_json_widget_v1(v1)
    program = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {},
        "puppeteering": {},
        "run": {
            "program": {
                "info": {"id": "versioned_runtime", "title": "Versioned runtime"},
                "widgets": {"review": {"widget": v1.widget_id, "bindings": {}}},
                "flow": [{"id": "review_step", "widgets": ["review"]}],
            },
            "config": {},
        },
    }
    lowered = compile_strict_program(program)
    assert lowered["run"]["program"]["widgets"]["review"]["widget"] == v1.widget_id

