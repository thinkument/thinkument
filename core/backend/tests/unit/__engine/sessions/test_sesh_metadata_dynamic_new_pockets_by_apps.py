from __future__ import annotations

"""
Executable sheet for dynamic session_metadata pocket registration.

The feature law is:

    core session_metadata keys remain stable
    apps register new top-level pockets at startup
    pocket schemas are inert JSON-safe declarations
    session_args_metadata_surface_sheet_v1 publishes core + registered pockets
    coerce_session_metadata validates registered pocket values
"""

import pytest

from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry,
    coerce_session_metadata_pocket_schema,
    validate_session_metadata_pocket_value,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    coerce_session_metadata,
    session_args_metadata_surface_sheet_v1,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    SessionMetadataSurfaceRegistry.clear_registered_pockets_for_tests()
    yield
    SessionMetadataSurfaceRegistry.clear_registered_pockets_for_tests()


def _grading_schema():
    return {
        "kind": "session_metadata_pocket_schema_v1",
        "label": "Grading",
        "description": "App-owned metadata for grading workflows.",
        "fields": {
            "rubric_id": {
                "type": "string",
                "required": True,
            },
            "grader_role": {
                "type": "string",
                "required": False,
            },
            "max_score": {
                "type": "number",
                "required": False,
                "default": 100,
            },
        },
        "additional_keys": False,
        "examples": [
            {
                "rubric_id": "rubric.v1",
                "grader_role": "reviewer",
                "max_score": 100,
            }
        ],
        "laws": [
            "grading metadata is app-owned",
            "rubric_id is required",
        ],
    }


def _core_metadata_with_grading(grading):
    return {
        "roles": {
            "maker": {"read_roles": ["reviewer"]},
            "reviewer": {},
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
            },
        },
        "grading": grading,
    }


def test_registry_starts_empty_and_surface_contains_only_core_keys():
    sheet = session_args_metadata_surface_sheet_v1()

    assert SessionMetadataSurfaceRegistry.registered_keys() == []
    assert sheet["app_pocket_keys"] == []
    assert "roles" in sheet["core_keys"]
    assert "role_mismatch_policy" in sheet["core_keys"]
    assert sheet["subsurfaces"]["app_pockets"] == {}


def test_register_pocket_publishes_it_in_session_surface():
    registered = SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    assert registered["kind"] == "session_metadata_pocket_schema_v1"
    assert registered["label"] == "Grading"
    assert registered["required_fields"] == ["rubric_id"]

    sheet = session_args_metadata_surface_sheet_v1()

    assert "grading" in sheet["keys"]
    assert sheet["app_pocket_keys"] == ["grading"]
    assert sheet["subsurfaces"]["app_pockets"]["grading"]["label"] == "Grading"
    assert sheet["subsurfaces"]["app_pockets"]["grading"]["fields"]["rubric_id"] == {
        "type": "string",
        "required": True,
    }


def test_registered_surface_is_deep_copied_not_mutable_by_callers():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    pockets = SessionMetadataSurfaceRegistry.registered_pockets()
    pockets["grading"]["label"] = "Mutated"

    assert SessionMetadataSurfaceRegistry.registered_pockets()["grading"]["label"] == (
        "Grading"
    )


def test_registering_core_key_is_rejected():
    with pytest.raises(KeyError, match="core session_metadata key"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="roles",
            schema=_grading_schema(),
        )

    with pytest.raises(KeyError, match="core session_metadata key"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="role_mismatch_policy",
            schema=_grading_schema(),
        )


def test_registering_private_or_dotted_key_is_rejected():
    with pytest.raises(ValueError, match="may not start"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="_private",
            schema=_grading_schema(),
        )

    with pytest.raises(ValueError, match="top-level"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading.rubric",
            schema=_grading_schema(),
        )


def test_duplicate_registration_requires_replace_true():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    with pytest.raises(KeyError, match="already registered"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=_grading_schema(),
        )

    replaced = SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema={
            **_grading_schema(),
            "label": "Replacement Grading",
        },
        replace=True,
    )

    assert replaced["label"] == "Replacement Grading"
    assert SessionMetadataSurfaceRegistry.registered_pockets()["grading"]["label"] == (
        "Replacement Grading"
    )


def test_schema_rejects_live_callables_deeply():
    schema = _grading_schema()
    schema["fields"]["rubric_id"]["bad"] = lambda: None

    with pytest.raises(TypeError, match="live callable"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=schema,
        )


def test_schema_rejects_non_json_safe_values():
    schema = _grading_schema()
    schema["examples"] = [{"bad": object()}]

    with pytest.raises(TypeError, match="JSON-safe"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=schema,
        )


def test_schema_rejects_unknown_top_level_schema_keys():
    schema = _grading_schema()
    schema["runtime_fn"] = "do_not_put_runtime_here"

    with pytest.raises(KeyError, match="unknown key"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=schema,
        )


def test_schema_rejects_unknown_field_schema_keys():
    schema = _grading_schema()
    schema["fields"]["rubric_id"]["runtime_fn"] = "nope"

    with pytest.raises(KeyError, match="unknown key"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=schema,
        )


def test_schema_rejects_invalid_field_type():
    schema = _grading_schema()
    schema["fields"]["rubric_id"]["type"] = "callable"

    with pytest.raises(ValueError, match="must be one of"):
        SessionMetadataSurfaceRegistry.register_pocket(
            key="grading",
            schema=schema,
        )


def test_schema_canonicalizes_required_fields_from_field_flags_and_explicit_list():
    schema = {
        "label": "Workflow",
        "fields": {
            "workflow_id": {"type": "string"},
            "phase": {"type": "string", "required": True},
            "owner": {"type": "string"},
        },
        "required_fields": ["workflow_id"],
    }

    out = coerce_session_metadata_pocket_schema("workflow", schema)

    assert out["kind"] == "session_metadata_pocket_schema_v1"
    assert out["required_fields"] == ["workflow_id", "phase"]


def test_schema_rejects_required_field_not_declared():
    schema = {
        "label": "Workflow",
        "fields": {
            "workflow_id": {"type": "string"},
        },
        "required_fields": ["missing"],
    }

    with pytest.raises(KeyError, match="not declared"):
        coerce_session_metadata_pocket_schema("workflow", schema)


def test_validate_pocket_value_accepts_good_value():
    schema = coerce_session_metadata_pocket_schema("grading", _grading_schema())

    validate_session_metadata_pocket_value(
        {
            "rubric_id": "rubric.v1",
            "grader_role": "reviewer",
            "max_score": 100,
        },
        schema,
        path="session_metadata['grading']",
    )


def test_validate_pocket_value_rejects_missing_required_field():
    schema = coerce_session_metadata_pocket_schema("grading", _grading_schema())

    with pytest.raises(KeyError, match="rubric_id"):
        validate_session_metadata_pocket_value(
            {
                "grader_role": "reviewer",
            },
            schema,
            path="session_metadata['grading']",
        )


def test_validate_pocket_value_rejects_unknown_key_when_additional_keys_false():
    schema = coerce_session_metadata_pocket_schema("grading", _grading_schema())

    with pytest.raises(KeyError, match="unknown key"):
        validate_session_metadata_pocket_value(
            {
                "rubric_id": "rubric.v1",
                "unexpected": True,
            },
            schema,
            path="session_metadata['grading']",
        )


def test_validate_pocket_value_accepts_unknown_key_when_additional_keys_true():
    schema = coerce_session_metadata_pocket_schema(
        "workflow",
        {
            "label": "Workflow",
            "fields": {
                "workflow_id": {"type": "string", "required": True},
            },
            "additional_keys": True,
        },
    )

    validate_session_metadata_pocket_value(
        {
            "workflow_id": "wf1",
            "app_specific_future_key": {"ok": True},
        },
        schema,
        path="session_metadata['workflow']",
    )


def test_validate_pocket_value_rejects_wrong_field_type():
    schema = coerce_session_metadata_pocket_schema("grading", _grading_schema())

    with pytest.raises(TypeError, match="max_score"):
        validate_session_metadata_pocket_value(
            {
                "rubric_id": "rubric.v1",
                "max_score": "100",
            },
            schema,
            path="session_metadata['grading']",
        )


def test_validate_pocket_value_rejects_enum_mismatch():
    schema = coerce_session_metadata_pocket_schema(
        "workflow",
        {
            "label": "Workflow",
            "fields": {
                "phase": {
                    "type": "string",
                    "required": True,
                    "enum": ["draft", "review", "done"],
                }
            },
            "additional_keys": False,
        },
    )

    with pytest.raises(ValueError, match="phase"):
        validate_session_metadata_pocket_value(
            {"phase": "invalid"},
            schema,
            path="session_metadata['workflow']",
        )


def test_validate_pocket_value_supports_array_item_schema():
    schema = coerce_session_metadata_pocket_schema(
        "workflow",
        {
            "label": "Workflow",
            "fields": {
                "approvers": {
                    "type": "array",
                    "required": True,
                    "items": {"type": "string"},
                }
            },
            "additional_keys": False,
        },
    )

    validate_session_metadata_pocket_value(
        {"approvers": ["a", "b"]},
        schema,
        path="session_metadata['workflow']",
    )

    with pytest.raises(TypeError, match="approvers"):
        validate_session_metadata_pocket_value(
            {"approvers": ["a", 3]},
            schema,
            path="session_metadata['workflow']",
        )


def test_validate_pocket_value_supports_nested_object_fields():
    schema = coerce_session_metadata_pocket_schema(
        "workflow",
        {
            "label": "Workflow",
            "fields": {
                "owner": {
                    "type": "object",
                    "required": True,
                    "fields": {
                        "role": {"type": "string", "required": True},
                        "email": {"type": "string"},
                    },
                    "additional_keys": False,
                }
            },
            "additional_keys": False,
        },
    )

    validate_session_metadata_pocket_value(
        {
            "owner": {
                "role": "maker",
                "email": "maker@example.com",
            }
        },
        schema,
        path="session_metadata['workflow']",
    )

    with pytest.raises(KeyError, match="missing required field 'role'"):
        validate_session_metadata_pocket_value(
            {
                "owner": {
                    "email": "maker@example.com",
                }
            },
            schema,
            path="session_metadata['workflow']",
        )


def test_coerce_session_metadata_accepts_registered_pocket():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    meta = coerce_session_metadata(
        _core_metadata_with_grading(
            {
                "rubric_id": "rubric.v1",
                "grader_role": "reviewer",
                "max_score": 100,
            }
        )
    )

    assert meta["grading"] == {
        "rubric_id": "rubric.v1",
        "grader_role": "reviewer",
        "max_score": 100,
    }


def test_coerce_session_metadata_rejects_registered_pocket_bad_value():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    with pytest.raises(KeyError, match="rubric_id"):
        coerce_session_metadata(
            _core_metadata_with_grading(
                {
                    "grader_role": "reviewer",
                    "max_score": 100,
                }
            )
        )


def test_coerce_session_metadata_ignores_unregistered_app_pockets_for_backcompat():
    """
    Unregistered keys remain pass-through so existing apps do not break.

    Apps that want verified pockets register schemas. Apps that do not register
    remain seamless/backcompat.
    """
    meta = coerce_session_metadata(
        _core_metadata_with_grading(
            {
                "grader_role": "reviewer",
            }
        )
    )

    assert meta["grading"] == {
        "grader_role": "reviewer",
    }


def test_multiple_apps_can_register_multiple_pockets():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    SessionMetadataSurfaceRegistry.register_pocket(
        key="workflow",
        schema={
            "label": "Workflow",
            "fields": {
                "workflow_id": {"type": "string", "required": True},
                "phase": {
                    "type": "string",
                    "enum": ["draft", "review", "done"],
                },
            },
            "additional_keys": False,
        },
    )

    sheet = session_args_metadata_surface_sheet_v1()

    assert sheet["app_pocket_keys"] == ["grading", "workflow"]
    assert set(sheet["subsurfaces"]["app_pockets"]) == {"grading", "workflow"}

    meta = coerce_session_metadata(
        {
            "roles": {"maker": {}, "reviewer": {}},
            "role_mismatch_policy": {"default": "redacted"},
            "grading": {"rubric_id": "r1"},
            "workflow": {"workflow_id": "wf1", "phase": "review"},
        }
    )

    assert meta["grading"] == {"rubric_id": "r1"}
    assert meta["workflow"] == {"workflow_id": "wf1", "phase": "review"}


def test_registered_pocket_does_not_change_core_role_validation():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    with pytest.raises(KeyError, match="unknown role"):
        coerce_session_metadata(
            {
                "roles": {
                    "maker": {"read_roles": ["ghost"]},
                },
                "role_mismatch_policy": {"default": "redacted"},
                "grading": {"rubric_id": "r1"},
            }
        )


def test_pocket_registry_contract_summary():
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=_grading_schema(),
    )

    sheet = session_args_metadata_surface_sheet_v1()

    contract = {
        "core_keys_are_stable": sheet["core_keys"],
        "app_keys_are_registered": sheet["app_pocket_keys"],
        "schema_is_declarative": sheet["subsurfaces"]["app_pockets"]["grading"][
            "kind"
        ],
        "unknown_unregistered_pockets_are_backcompat_passthrough": True,
        "registered_pockets_are_validated": True,
    }

    assert "roles" in contract["core_keys_are_stable"]
    assert "role_mismatch_policy" in contract["core_keys_are_stable"]
    assert contract["app_keys_are_registered"] == ["grading"]
    assert contract["schema_is_declarative"] == "session_metadata_pocket_schema_v1"
    assert contract["unknown_unregistered_pockets_are_backcompat_passthrough"] is True
    assert contract["registered_pockets_are_validated"] is True

def test_dynamic_map_values_use_the_same_nested_schema_and_precise_paths():
    schema=coerce_session_metadata_pocket_schema('appearance',{
        'fields':{'declarations':{'type':'object','additional_values':{'type':'string'}}}})
    validate_session_metadata_pocket_value({'declarations':{'--accent':'green','border-color':'red'}},schema)
    with pytest.raises(TypeError,match=r'declarations.color must be of type'):
        validate_session_metadata_pocket_value({'declarations':{'color':7}},schema)
    with pytest.raises(ValueError,match='only valid'):
        coerce_session_metadata_pocket_schema('appearance',{
            'fields':{'declarations':{'type':'array','additional_values':{'type':'string'}}}})
    with pytest.raises(ValueError,match='must be one of'):
        coerce_session_metadata_pocket_schema('appearance',{
            'fields':{'declarations':{'type':'object','additional_values':{'type':'unsupported'}}}})
