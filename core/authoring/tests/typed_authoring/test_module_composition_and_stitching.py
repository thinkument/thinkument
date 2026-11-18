"""
Comprehensive unit tests for Thinkument Module Composition, (P x C) Publishing,
Hermetic Argument Scoping, and SM Stitching.

Verifies:
1. Module manifest validation and content fingerprinting.
2. Module catalog registration and versioned lookup.
3. Extensible SM Pocket Stitching Policy registry.
4. Single-step leaf module import into step widgets with role remapping and arg binding.
5. Multi-step sub-flow module import into outer flow with namespaced steps and scoped parameters.
6. Negative verification: cyclic imports, compound flow in step, missing args, unknown roles.
7. Full lowering via compile_unified_typed_jsonic_program.
"""

from copy import deepcopy
import pytest

from bindings2bindingsTM import CompilationError
from authoring_funneling import (
    LANG_THINK_MODULE_V1,
    LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
    ModuleCatalogRegistry,
    SMPocketStitchingPolicy,
    SMPocketStitchingRegistry,
    compile_unified_typed_jsonic_program,
    compute_module_fingerprint,
    normalize_think_module_v1,
    stitch_program_modules,
    validate_think_module_v1,
)


@pytest.fixture(autouse=True)
def clean_catalog():
    ModuleCatalogRegistry.clear()
    yield
    ModuleCatalogRegistry.clear()


def _make_sample_leaf_module(name="common/text_box", version="1.0.0"):
    return {
        "kind": LANG_THINK_MODULE_V1,
        "name": name,
        "version": version,
        "title": "Single Text Box Leaf Widget",
        "interface": {
            "inputs": {
                "placeholder": {"type": "str", "default": "Type here..."},
                "required_label": {"type": "str", "required": True},
            },
            "outputs": {
                "text_out": {
                    "kind": "dict",
                    "fields": {"value": {"kind": "str"}},
                }
            },
            "roles": {
                "writer": {"description": "Can input text"},
            },
        },
        "P": {
            "info": {"id": "text_box_prog"},
            "widgets": {
                "input_w": {
                    "widget": {
                        "kind": "json_widget_v1",
                        "name": "text_box_w",
                        "declaration": {
                            "inputs": {},
                            "outputs": {
                                "text_out": {
                                    "kind": "dict",
                                    "fields": {"value": {"kind": "str"}},
                                }
                            },
                            "args": {
                                "placeholder": {"type": "str"},
                                "required_label": {"type": "str"},
                            },
                            "fills": {"type": "map", "key": "str", "value": "str"},
                            "signal": {"type": "map", "key": "str", "value": "str"},
                        },
                        "signals": {
                            "mount": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {
                                    "reexplode": {
                                        "title": "$config.required_label",
                                        "micros": [{"id": "box", "kind": "text", "value": ""}],
                                    }
                                },
                            },
                            "fill": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {
                                    "done": True,
                                    "outputs": {
                                        "text_out": {"value": "$fills.box"}
                                    },
                                },
                            },
                        },
                    },
                    "roles": ["writer"],
                }
            },
            "flow": [{"id": "step_main", "widgets": ["input_w"]}],
        },
        "C": {
            "parameters": {
                "placeholder": "Default Placeholder",
            }
        },
        "SM": {
            "roles": {
                "writer": {"read_roles": []},
            }
        },
    }


def _make_sample_subflow_module(name="review/flow", version="1.0.0"):
    return {
        "kind": LANG_THINK_MODULE_V1,
        "name": name,
        "version": version,
        "title": "Two Step Subflow",
        "interface": {
            "inputs": {
                "topic": {"type": "str", "required": True},
            },
            "outputs": {
                "final_review": {"type": "dict"},
            },
            "roles": {
                "drafter": {"description": "Author"},
                "approver": {"description": "Lead"},
            },
        },
        "P": {
            "info": {"id": "subflow_p"},
            "widgets": {
                "draft_w": {
                    "widget": {
                        "kind": "json_widget_v1",
                        "name": "draft_w",
                        "declaration": {
                            "inputs": {},
                            "outputs": {"draft_doc": {"kind": "dict", "fields": {"body": {"kind": "str"}}}},
                            "args": {"topic": {"type": "str"}},
                            "fills": {"type": "map", "key": "str", "value": "str"},
                            "signal": {"type": "map", "key": "str", "value": "str"},
                        },
                        "signals": {
                            "mount": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {
                                    "reexplode": {
                                        "title": "$config.topic",
                                        "micros": [{"id": "body", "kind": "text", "value": ""}],
                                    }
                                },
                            },
                            "fill": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {"done": True, "outputs": {"draft_doc": {"body": "Drafted"}}},
                            },
                        },
                    },
                    "roles": ["drafter"],
                },
                "sign_w": {
                    "widget": {
                        "kind": "json_widget_v1",
                        "name": "sign_w",
                        "declaration": {
                            "inputs": {},
                            "outputs": {"final_review": {"kind": "dict", "fields": {"approved": {"kind": "bool"}}}},
                            "args": {},
                            "fills": {"type": "map", "key": "str", "value": "str"},
                            "signal": {"type": "map", "key": "str", "value": "str"},
                        },
                        "signals": {
                            "mount": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {
                                    "reexplode": {"title": "Approve", "micros": []}
                                },
                            },
                            "fill": {
                                "execution": "sync",
                                "steps": [],
                                "returns": {"done": True, "outputs": {"final_review": {"approved": True}}},
                            },
                        },
                    },
                    "roles": ["approver"],
                },
            },
            "flow": [
                {"id": "step_draft", "widgets": ["draft_w"]},
                {"id": "step_sign", "widgets": ["sign_w"]},
            ],
        },
        "C": {},
        "SM": {
            "roles": {
                "drafter": {"read_roles": []},
                "approver": {"read_roles": ["drafter"]},
            }
        },
    }


def test_module_manifest_validation_and_fingerprinting():
    raw = _make_sample_leaf_module()
    validated = validate_think_module_v1(raw)
    assert validated["name"] == "common/text_box"
    assert validated["version"] == "1.0.0"

    norm = normalize_think_module_v1(raw)
    assert norm["kind"] == LANG_THINK_MODULE_V1

    fp1 = compute_module_fingerprint(raw)
    fp2 = compute_module_fingerprint(norm)
    assert fp1 == fp2
    assert len(fp1) == 64


def test_module_catalog_registry():
    mod = _make_sample_leaf_module("acme/input", "2.1.0")
    ModuleCatalogRegistry.register_module(mod)

    # Lookup by full ref
    got = ModuleCatalogRegistry.get_module("acme/input@2.1.0")
    assert got["name"] == "acme/input"
    assert got["version"] == "2.1.0"

    # Lookup latest
    got_latest = ModuleCatalogRegistry.get_module("acme/input")
    assert got_latest["version"] == "2.1.0"

    # List modules
    listed = ModuleCatalogRegistry.list_modules("acme")
    assert len(listed) == 1
    assert listed[0]["name"] == "acme/input"

    # Retire
    assert ModuleCatalogRegistry.retire_module("acme/input@2.1.0") is True
    with pytest.raises(CompilationError) as exc:
        ModuleCatalogRegistry.get_module("acme/input")
    assert exc.value.details["code"] == "module_not_found"


def test_sm_pocket_stitching_registry():
    assert SMPocketStitchingRegistry.get_pocket_policy("session_storage") == SMPocketStitchingPolicy.HOST_SOVEREIGN
    assert SMPocketStitchingRegistry.get_pocket_policy("roles") == SMPocketStitchingPolicy.LEXICAL_ROLE_REMAP
    assert SMPocketStitchingRegistry.get_pocket_policy("paquete_aesthetics") == SMPocketStitchingPolicy.STEP_LOCAL_DELEGATE
    assert SMPocketStitchingRegistry.get_pocket_policy("custom_unknown_pocket") == SMPocketStitchingPolicy.DISJOINT_NAMESPACED


def test_stitch_leaf_widget_import_into_step_widgets():
    mod = _make_sample_leaf_module("common/text_box", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "outer_flow"},
                "widgets": {
                    "my_editor": {
                        "import": "common/text_box@1.0.0",
                        "args": {
                            "required_label": "Enter First Name",
                        },
                        "role_map": {
                            "writer": "customer",
                        },
                    }
                },
                "flow": [
                    {"id": "step_1", "widgets": ["my_editor"]}
                ],
            }
        },
    }

    stitched_p, stitched_sm = stitch_program_modules(outer_p)
    lowered_w = stitched_p["run"]["program"]["widgets"]["my_editor"]

    # Role must be mapped
    assert lowered_w["roles"] == ["customer"]
    # Required label must be populated in args
    assert lowered_w["args"]["required_label"] == "Enter First Name"
    # Placeholder must be populated with default
    assert lowered_w["args"]["placeholder"] == "Default Placeholder"


def test_stitch_multi_step_flow_module():
    mod = _make_sample_subflow_module("review/flow", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "master_app"},
                "widgets": {},
                "flow": [
                    {
                        "id": "review_phase",
                        "import": "review/flow@1.0.0",
                        "args": {
                            "topic": "Quantum Computing 101",
                        },
                        "role_map": {
                            "drafter": "intern",
                            "approver": "senior_lead",
                        },
                    }
                ],
            }
        },
    }

    stitched_p, stitched_sm = stitch_program_modules(outer_p)
    flow = stitched_p["run"]["program"]["flow"]
    widgets = stitched_p["run"]["program"]["widgets"]

    # Flow must have expanded into 2 namespaced steps
    assert len(flow) == 2
    assert flow[0]["id"] == "review_phase__step_draft"
    assert flow[1]["id"] == "review_phase__step_sign"

    # Widgets must be namespaced with remapped roles
    assert "review_phase__draft_w" in widgets
    assert "review_phase__sign_w" in widgets

    assert widgets["review_phase__draft_w"]["roles"] == ["intern"]
    assert widgets["review_phase__sign_w"]["roles"] == ["senior_lead"]
    assert widgets["review_phase__draft_w"]["args"]["topic"] == "Quantum Computing 101"


def test_negative_compound_flow_in_widget_step_rejected():
    # Multi-step module cannot be imported in widgets table
    mod = _make_sample_subflow_module("review/flow", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "invalid_app"},
                "widgets": {
                    "illegal_node": {
                        "import": "review/flow@1.0.0",
                    }
                },
                "flow": [{"id": "step_1", "widgets": ["illegal_node"]}],
            }
        },
    }

    with pytest.raises(CompilationError) as exc:
        stitch_program_modules(outer_p)
    assert exc.value.details["code"] == "compound_flow_in_step_error"


def test_negative_missing_required_argument_rejected():
    mod = _make_sample_leaf_module("common/text_box", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "bad_args"},
                "widgets": {
                    "node": {
                        "import": "common/text_box@1.0.0",
                        "args": {},  # missing required_label
                    }
                },
                "flow": [{"id": "step_1", "widgets": ["node"]}],
            }
        },
    }

    with pytest.raises(CompilationError) as exc:
        stitch_program_modules(outer_p)
    assert exc.value.details["code"] == "missing_required_argument"


def test_negative_unknown_source_role_rejected():
    mod = _make_sample_leaf_module("common/text_box", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "bad_role"},
                "widgets": {
                    "node": {
                        "import": "common/text_box@1.0.0",
                        "args": {"required_label": "Label"},
                        "role_map": {"non_existent_role": "admin"},
                    }
                },
                "flow": [{"id": "step_1", "widgets": ["node"]}],
            }
        },
    }

    with pytest.raises(CompilationError) as exc:
        stitch_program_modules(outer_p)
    assert exc.value.details["code"] == "unknown_source_role_error"


def test_end_to_end_compile_unified_program_with_module_stitching():
    mod = _make_sample_leaf_module("common/text_box", "1.0.0")
    ModuleCatalogRegistry.register_module(mod)

    outer_p = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "run": {
            "program": {
                "info": {"id": "e2e_app", "title": "End-to-End Program with Imported Module"},
                "widgets": {
                    "box": {
                        "import": "common/text_box@1.0.0",
                        "args": {
                            "required_label": "Enter Password",
                        },
                    }
                },
                "flow": [
                    {"id": "step_auth", "widgets": ["box"]}
                ],
            }
        },
    }

    compiled_p, extraction = compile_unified_typed_jsonic_program(outer_p)
    assert compiled_p["run"]["program"]["info"]["id"] == "e2e_app"
    assert "box" in compiled_p["run"]["program"]["widgets"]
    assert len(extraction.prepared_artifacts) == 1
