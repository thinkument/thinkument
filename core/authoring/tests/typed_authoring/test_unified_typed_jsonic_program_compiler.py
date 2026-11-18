"""
Unit tests for the Level 3 Unified Typed JSONic Program Compiler and Lowering Pipeline.

Verifies:
1. Pure inline JSONic widget program compilation and lowering.
2. Hybrid compilation (inline widget wired to published widget).
3. Wire typing symmetry across static D-expression bindings.
4. Content-addressed synthetic ID calculation and idempotent kernel registration.
5. Negative grammar and type validation errors with precise path reporting.
6. Full lowering provenance tracking chain.
"""

from copy import deepcopy
import pytest

from bindings2bindingsTM import CompilationError, D
from authoring_funneling import (
    LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
    compile_unified_typed_jsonic_program,
    extract_inline_widgets_v1,
    lower_unified_typed_jsonic_think_program_v1,
    register_unified_typed_jsonic_think_program_language_v1,
    prepare_json_widget_v1,
    register_prepared_json_widget_v1,
)


def _sample_inline_generator(name="generator_v1"):
    return {
        "kind": "json_widget_v1",
        "name": name,
        "declaration": {
            "inputs": {},
            "outputs": {
                "article": {
                    "kind": "dict",
                    "fields": {
                        "headline": {"kind": "str"},
                        "content": {"kind": "str"},
                    },
                }
            },
            "args": {"category": {"type": "str"}},
            "fills": {"type": "map", "key": "str", "value": "str"},
            "signal": {"type": "map", "key": "str", "value": "str"},
        },
        "signals": {
            "mount": {
                "execution": "sync",
                "steps": [
                    {
                        "id": "banner",
                        "fn": "text.template",
                        "args": {
                            "template": "Drafting: {{cat}}",
                            "vars": {"cat": "$config.category"},
                        },
                    }
                ],
                "returns": {
                    "reexplode": {
                        "title": "$banner.text",
                        "micros": [
                            {"id": "title_in", "kind": "text", "value": ""},
                            {"id": "body_in", "kind": "text", "value": ""},
                        ],
                    }
                },
            },
            "fill": {
                "execution": "sync",
                "steps": [
                    {
                        "id": "fmt_title",
                        "fn": "text.concat",
                        "args": {
                            "parts": ["[$config.category]", "$fills.title_in"],
                            "sep": " ",
                        },
                    }
                ],
                "returns": {
                    "done": True,
                    "outputs": {
                        "article": {
                            "headline": "$fmt_title.text",
                            "content": "$fills.body_in",
                        }
                    },
                },
            },
        },
    }


def _sample_inline_reviewer(name="reviewer_v1"):
    return {
        "kind": "json_widget_v1",
        "name": name,
        "declaration": {
            "inputs": {
                "in_headline": {"kind": "str"},
                "in_content": {"kind": "str"},
            },
            "outputs": {
                "reviewed": {
                    "kind": "dict",
                    "fields": {
                        "final_headline": {"kind": "str"},
                        "stamp": {"kind": "str"},
                    },
                }
            },
            "args": {"reviewer_name": {"type": "str"}},
            "fills": {"type": "map", "key": "str", "value": "str"},
            "signal": {"type": "map", "key": "str", "value": "str"},
        },
        "signals": {
            "mount": {
                "execution": "sync",
                "steps": [
                    {
                        "id": "mount_title",
                        "fn": "text.template",
                        "args": {
                            "template": "Reviewing: {{hl}}",
                            "vars": {"hl": "$mouth.in_headline"},
                        },
                    }
                ],
                "returns": {
                    "reexplode": {
                        "title": "$mount_title.text",
                        "micros": [
                            {"id": "feedback", "kind": "text", "value": ""},
                        ],
                    }
                },
            },
            "fill": {
                "execution": "sync",
                "steps": [
                    {
                        "id": "sign",
                        "fn": "text.concat",
                        "args": {
                            "parts": ["APPROVED BY", "$config.reviewer_name"],
                            "sep": " ",
                        },
                    }
                ],
                "returns": {
                    "done": True,
                    "outputs": {
                        "reviewed": {
                            "final_headline": "$mouth.in_headline",
                            "stamp": "$sign.text",
                        }
                    },
                },
            },
        },
    }


def _build_two_step_program(w1_def, w2_def):
    return {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "surface_version": "v1",
        "run": {
            "info": {"id": "two_step_pipeline", "title": "Two Step Editorial Flow"},
            "program": {
                "info": {"id": "two_step_pipeline", "title": "Two Step Editorial Flow"},
                "widgets": {
                    "generator": {
                        "widget": w1_def,
                        "bindings": {
                            "parameters": {
                                "category": {"type": {"kind": "str"}, "value": "SCIENCE"}
                            },
                            "inputs": {},
                        },
                    },
                    "reviewer": {
                        "widget": w2_def,
                        "bindings": {
                            "sources": {
                                "gen_src": {"widget": "generator", "port": "article"}
                            },
                            "parameters": {
                                "reviewer_name": {"type": {"kind": "str"}, "value": "EDITOR_IN_CHIEF"}
                            },
                            "inputs": {
                                "in_headline": "$gen_src.headline",
                                "in_content": "$gen_src.content",
                            },
                        },
                    },
                },
                "flow": [
                    {"id": "step_1", "widgets": ["generator"]},
                    {"id": "step_2", "widgets": ["reviewer"]},
                ],
            },
        },
    }


def test_pure_inline_widget_program_compilation_and_lowering():
    register_unified_typed_jsonic_think_program_language_v1()
    gen = _sample_inline_generator()
    rev = _sample_inline_reviewer()
    prog = _build_two_step_program(gen, rev)

    compiled_p, extraction = compile_unified_typed_jsonic_program(prog)

    # 1. Extraction checks
    assert len(extraction.prepared_artifacts) == 2
    assert "generator" in extraction.inline_metadata
    assert "reviewer" in extraction.inline_metadata
    gen_synthetic = extraction.inline_metadata["generator"]["synthetic_id"]
    rev_synthetic = extraction.inline_metadata["reviewer"]["synthetic_id"]
    assert gen_synthetic.startswith("synthetic_inline_")
    assert rev_synthetic.startswith("synthetic_inline_")

    # 2. Program rewriting checks
    widgets = compiled_p["run"]["program"]["widgets"]
    assert widgets["generator"]["widget"] == gen_synthetic
    assert widgets["reviewer"]["widget"] == rev_synthetic

    # 3. Lowering all the way to Kernel App Table
    bundle = lower_unified_typed_jsonic_think_program_v1(prog)
    assert len(bundle.app_table_manifest) == 2
    assert bundle.provenance["source_program_language"] == LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1
    assert "generator" in bundle.provenance["inline_widgets"]
    assert "reviewer" in bundle.provenance["inline_widgets"]

    # 4. Lowering chain provenance
    chain = bundle.provenance["lowering_chain"]
    assert chain[0]["language"] == LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1
    assert chain[0]["artifact"] == "typed_think_program_v1"
    assert chain[1]["language"] == "typed_think_program_v1"
    assert chain[1]["artifact"] == "think_program_v1"


def test_hybrid_inline_and_published_widgets():
    register_unified_typed_jsonic_think_program_language_v1()

    # Pre-publish the generator as a standalone catalog widget
    gen_raw = _sample_inline_generator("published_gen_case_1")
    gen_artifact = prepare_json_widget_v1(gen_raw, widget_id="published_gen_case_1")
    register_prepared_json_widget_v1(gen_artifact)

    # Step 1 references published widget by shorthand string; Step 2 is inline
    rev_raw = _sample_inline_reviewer("inline_rev_case_1")
    prog = _build_two_step_program("published_gen_case_1", rev_raw)

    compiled_p, extraction = compile_unified_typed_jsonic_program(prog)

    # Only reviewer should be in inline extraction
    assert len(extraction.prepared_artifacts) == 1
    assert "reviewer" in extraction.inline_metadata
    assert "generator" not in extraction.inline_metadata

    widgets = compiled_p["run"]["program"]["widgets"]
    assert widgets["generator"]["widget"] == "published_gen_case_1"
    assert widgets["reviewer"]["widget"].startswith("synthetic_inline_")

    bundle = lower_unified_typed_jsonic_think_program_v1(prog)
    assert len(bundle.app_table_manifest) == 2


def test_content_addressed_synthetic_id_idempotency():
    gen1 = _sample_inline_generator("identical_name")
    gen2 = _sample_inline_generator("identical_name")

    prog = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "surface_version": "v1",
        "run": {
            "info": {"id": "dedup_p", "title": "Dedup Test"},
            "program": {
                "info": {"id": "dedup_p", "title": "Dedup Test"},
                "widgets": {
                    "w1": {
                        "widget": gen1,
                        "bindings": {
                            "parameters": {"category": {"type": {"kind": "str"}, "value": "A"}},
                            "inputs": {},
                        },
                    },
                    "w2": {
                        "widget": gen2,
                        "bindings": {
                            "parameters": {"category": {"type": {"kind": "str"}, "value": "B"}},
                            "inputs": {},
                        },
                    },
                },
                "flow": [
                    {"id": "step_1", "widgets": ["w1", "w2"]},
                ],
            },
        },
    }

    compiled_p, extraction = compile_unified_typed_jsonic_program(prog)

    # Both widgets share the exact same manifest -> exact same synthetic ID
    id1 = extraction.inline_metadata["w1"]["synthetic_id"]
    id2 = extraction.inline_metadata["w2"]["synthetic_id"]
    assert id1 == id2
    # Only 1 unique artifact prepared and registered
    assert len(extraction.prepared_artifacts) == 1


def test_inline_widget_negative_validation_errors():
    register_unified_typed_jsonic_think_program_language_v1()

    # 1. Invalid widget kind
    bad_kind = _sample_inline_generator()
    bad_kind["kind"] = "unsupported_v99"
    prog = _build_two_step_program(bad_kind, _sample_inline_reviewer())
    with pytest.raises(CompilationError) as exc_info:
        compile_unified_typed_jsonic_program(prog)
    assert "unsupported_inline_widget_kind" in str(exc_info.value)

    # 2. Non-closed output port type (primitives directly in outputs are rejected)
    bad_output = _sample_inline_generator()
    bad_output["declaration"]["outputs"]["article"] = "str"  # Not a closed record dict
    prog = _build_two_step_program(bad_output, _sample_inline_reviewer())
    with pytest.raises(CompilationError):
        compile_unified_typed_jsonic_program(prog)

    # 3. Missing wire source port mismatch
    gen = _sample_inline_generator()
    rev = _sample_inline_reviewer()
    prog = _build_two_step_program(gen, rev)
    # Target nonexistent port on generator
    prog["run"]["program"]["widgets"]["reviewer"]["bindings"]["sources"]["gen_src"]["port"] = "nonexistent_port"
    with pytest.raises(CompilationError) as exc_info:
        compile_unified_typed_jsonic_program(prog)
    assert "unknown_source_port" in str(exc_info.value)


def test_wire_typing_symmetry_promises_to_raw_type():
    """Verify Law of Wire Typing Symmetry: Upstream Promise[T] unwraps to T across static wires."""
    register_unified_typed_jsonic_think_program_language_v1()

    # Async generator emitting a Promise[dict]
    async_gen = {
        "kind": "json_widget_v1",
        "name": "async_gen_v1",
        "declaration": {
            "inputs": {},
            "outputs": {
                "async_article": {
                    "kind": "promise",
                    "item": {
                        "kind": "dict",
                        "fields": {
                            "headline": {"kind": "str"},
                            "content": {"kind": "str"},
                        },
                    },
                }
            },
            "args": {"category": {"type": "str"}},
            "fills": {"type": "map", "key": "str", "value": "str"},
            "signal": {"type": "map", "key": "str", "value": "str"},
        },
        "signals": {
            "mount": {
                "execution": "sync",
                "steps": [],
                "returns": {
                    "reexplode": {
                        "title": "$config.category",
                        "micros": [{"id": "t", "kind": "text", "value": ""}],
                    }
                },
            },
            "fill": {
                "execution": "sync",
                "steps": [],
                "returns": {
                    "done": True,
                    "outputs": {
                        "async_article": {
                            "headline": "Async Breaking News",
                            "content": "Async Body Content",
                        }
                    },
                },
            },
        },
    }

    # Consumer expecting ordinary raw type 'str' across wire
    rev = _sample_inline_reviewer("rev_for_async_v1")

    prog = {
        "kind": LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1,
        "surface_version": "v1",
        "run": {
            "info": {"id": "async_wire_pipeline", "title": "Async Wire Flow"},
            "program": {
                "info": {"id": "async_wire_pipeline", "title": "Async Wire Flow"},
                "widgets": {
                    "gen": {
                        "widget": async_gen,
                        "bindings": {
                            "parameters": {"category": {"type": {"kind": "str"}, "value": "TECH"}},
                            "inputs": {},
                        },
                    },
                    "rev": {
                        "widget": rev,
                        "bindings": {
                            "sources": {
                                "async_src": {"widget": "gen", "port": "async_article"}
                            },
                            "parameters": {
                                "reviewer_name": {"type": {"kind": "str"}, "value": "CHIEF_EDITOR"}
                            },
                            "inputs": {
                                # Static D-expression safely unwraps Promise[dict] -> dict -> field str
                                "in_headline": "$async_src.headline",
                                "in_content": "$async_src.content",
                            },
                        },
                    },
                },
                "flow": [
                    {"id": "step_1", "widgets": ["gen"]},
                    {"id": "step_2", "widgets": ["rev"]},
                ],
            },
        },
    }

    compiled_p, extraction = compile_unified_typed_jsonic_program(prog)
    assert len(extraction.prepared_artifacts) == 2

    bundle = lower_unified_typed_jsonic_think_program_v1(prog)
    assert len(bundle.app_table_manifest) == 2


def test_authoring_funneling_toplevel_exports():
    import authoring_funneling as af

    assert hasattr(af, "LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1")
    assert hasattr(af, "lower_unified_typed_jsonic_think_program_v1")
    assert hasattr(af, "register_unified_typed_jsonic_think_program_language_v1")
    assert hasattr(af, "compile_unified_typed_jsonic_program")
    assert hasattr(af, "extract_inline_widgets_v1")
    assert hasattr(af, "compute_inline_widget_synthetic_id")
    assert hasattr(af, "InlineWidgetExtractionResult")
