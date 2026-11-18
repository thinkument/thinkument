from __future__ import annotations

"""
ThinkProgramTM reference-language / kernel integration test sheet.

This sheet proves the intended highest ergonomic JSON language:

    think_program_v1

It treats thinkprogramTM as a higher JSON authoring surface above
the existing explicit kernel language:

    think_program_v1
        -> symbol-bound run object
        -> expanded logical widget appearances
        -> explicit list[think_kernel_step_v1]
        -> thinking_flow_explicit / app-table
        -> think.kernel.v1 runtime

The hard design law:

    App-flow developers do not author micros.

Therefore every widget admitted by think_program_v1 must be a pulled
thinkwidgetTM class widget whose kernel contract says:

    enforce_no_premount_shell == true

The lowerer still emits explicit kernel datums with:

    "micros": []

because the current explicit kernel surface requires it. That field is
compiler-owned machine output, never app-author input.
"""

import copy
import json
from typing import Any, Dict, Mapping

import pytest

from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    THINK_PROGRAM_KIND_V1,
    THINK_PROGRAM_SURFACE_VERSION_V1,
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
    _ALLOWED_FLOW_ITEM_KEYS_V1,
    _ALLOWED_OVERRIDE_KEYS_V1,
    _ALLOWED_PROGRAM_INFO_KEYS_V1,
    _ALLOWED_PROGRAM_KEYS_V1,
    _ALLOWED_TOP_LEVEL_KEYS_V1,
    _ALLOWED_WIDGET_DEF_KEYS_V1,
    _DEFAULT_KERNEL_FLAGS_V1,
    _DEFAULT_LIFECYCLE_V1,
    bind_think_program_symbols_v1,
    lower_think_program_to_kernel_program_v1,
    lower_think_program_v1,
    normalize_initial_parameter_overrides_v1,
    overlay_initial_parameter_overrides_onto_program_v1,
    register_think_program_language_v1,
)

from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    DatumLifecycleWidget,
    Reexplode,
    thinkwidgetTM_config,
)

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)

from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    is_program_language_registered,
    lower_program_to_app_table_bundle,
)

from _thinkprogram._thinkcontinuitykernelTM.api import (
    LANG_THINKING_FLOW_EXPLICIT_V1,
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
    validate_kernel_program_v1,
)

from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    kernel_widget_class_repr_v1,
    pull_thinkwidget_class_into_kernel_v1,
)

def _api():
    return get_concrete_session_api(enable_persistence=False)

# =============================================================================
# Test widgets
# =============================================================================


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


def _latest_lifecycle_state(
    api: Any,
    sid: str,
    form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    store = api._get(sid).state["_datum_lifecycle_v1"]
    return store["forms"][form_id]["datums"][datum_id]["state"]


TP_PROFILE_WIDGET = "test._thinkprogram.profile_source"
TP_RISK_WIDGET = "test._thinkprogram.risk_source"
TP_REVIEW_WIDGET = "test._thinkprogram.profile_review"
TP_APPROVAL_WIDGET = "test._thinkprogram.approval"
TP_LEGACY_MICROS_WIDGET = "test._thinkprogram.legacy_micros_widget"


@thinkwidgetTM_config(
    TP_PROFILE_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "seed": {"type": "str", "required": True},
        "threshold": {"type": "int", "required": False, "default": 7},
        "labels": {"type": "list[str]", "required": False, "default": ["default"]},
    },
    wires={},
)
class ThinkProgramProfileSourceWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            k: v for k, v in datum_args.items() if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "form_id": dict(kernel_args.get("form") or {}).get("id"),
            "frame_id": dict(kernel_args.get("frame") or {}).get("id"),
            "span_id": dict(kernel_args.get("span") or {}).get("id"),
            "system_flags": dict(kernel_args.get("system_flags") or {}),
            "authoritative": bool(kernel_args.get("authoritative", False)),
            "past_wires": dict(kernel_args.get("past_wires") or {}),
        }
        self.mount_root_pollution = {
            key: key in self._q
            for key in (
                "kernel",
                "step",
                "form",
                "frame",
                "span",
                "past_wires",
                "history_queries",
            )
        }

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = TP_PROFILE_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Profile shell generated by mount",
                "micros": [_text_micro("value")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"value": ""},
            prefill_hints={"value": "profile-prefill"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.final_value = dict(fill_data["current_fills"]).get("value")
        self.commit = {
            "datum_id": position["datum_id"],
            "value": self.final_value,
        }
        return True


@thinkwidgetTM_config(
    TP_RISK_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "seed": {"type": "str", "required": True},
        "score_floor": {"type": "float", "required": False, "default": 0.0},
    },
    wires={},
)
class ThinkProgramRiskSourceWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            k: v for k, v in datum_args.items() if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "system_flags": dict(kernel_args.get("system_flags") or {}),
        }

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = TP_RISK_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Risk shell generated by mount",
                "micros": [_text_micro("value")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"value": ""},
            prefill_hints={"value": "risk-prefill"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.final_value = dict(fill_data["current_fills"]).get("value")
        self.commit = {
            "datum_id": position["datum_id"],
            "value": self.final_value,
        }
        return True


@thinkwidgetTM_config(
    TP_REVIEW_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "local": {"type": "str", "required": True},
    },
    wires={
        "previous_profile": {"multiplicity": "one", "required": True},
        "profile_history": {"multiplicity": "many", "required": False},
        "risk_sources": {"multiplicity": "many", "required": False},
    },
)
class ThinkProgramReviewWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})

        prior_profile = dict(past_wires.get("previous_profile") or {})
        prior_profile_value = dict(prior_profile.get("value") or {})
        prior_profile_state = dict(prior_profile_value.get("state") or {})

        profile_history = list(past_wires.get("profile_history") or [])
        risk_sources = list(past_wires.get("risk_sources") or [])

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            k: v for k, v in datum_args.items() if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "form_id": dict(kernel_args.get("form") or {}).get("id"),
            "system_flags": dict(kernel_args.get("system_flags") or {}),
            "past_wire_keys": sorted(past_wires),
        }
        self.prior_profile_final_value_on_mount = prior_profile_state.get("final_value")
        self.profile_history_count_on_mount = len(profile_history)
        self.risk_sources_count_on_mount = len(risk_sources)
        self.mount_root_pollution = {
            key: key in self._q
            for key in (
                "kernel",
                "step",
                "form",
                "frame",
                "span",
                "past_wires",
                "history_queries",
            )
        }

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = TP_REVIEW_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Review shell generated by mount",
                "micros": [_text_micro("confirm")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"confirm": ""},
            prefill_hints={"confirm": "review-prefill"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.confirmed = dict(fill_data["current_fills"]).get("confirm")
        self.commit = {
            "datum_id": position["datum_id"],
            "confirmed": self.confirmed,
            "prior_profile": self.prior_profile_final_value_on_mount,
        }
        return True


@thinkwidgetTM_config(
    TP_APPROVAL_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "mode": {"type": "str", "required": True},
    },
    wires={
        "review": {"multiplicity": "one", "required": True},
        "all_sources": {"multiplicity": "many", "required": False},
        "self_previous": {"multiplicity": "one", "required": False},
    },
)
class ThinkProgramApprovalWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})

        review_row = dict(past_wires.get("review") or {})
        review_value = dict(review_row.get("value") or {})
        review_state = dict(review_value.get("state") or {})

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            k: v for k, v in datum_args.items() if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "system_flags": dict(kernel_args.get("system_flags") or {}),
            "authoritative": bool(kernel_args.get("authoritative", False)),
            "past_wire_keys": sorted(past_wires),
        }
        self.review_confirmed_on_mount = review_state.get("confirmed")
        self.all_sources_count_on_mount = len(list(past_wires.get("all_sources") or []))
        self.self_previous_present_on_mount = "self_previous" in past_wires

        self.previous_approval_mode_on_mount = None
        if "self_previous" in past_wires:
            prev = dict(past_wires.get("self_previous") or {})
            prev_value = dict(prev.get("value") or {})
            prev_state = dict(prev_value.get("state") or {})
            self.previous_approval_mode_on_mount = prev_state.get("approved_mode")

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = TP_APPROVAL_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Approval shell generated by mount",
                "micros": [_text_micro("decision")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"decision": ""},
            prefill_hints={"decision": "approve"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.decision = dict(fill_data["current_fills"]).get("decision")
        self.approved_mode = self.mount_seen_user_args["mode"]
        self.commit = {
            "datum_id": position["datum_id"],
            "decision": self.decision,
            "mode": self.approved_mode,
            "review_confirmed": self.review_confirmed_on_mount,
            "previous_approval_mode": self.previous_approval_mode_on_mount,
        }
        return True


@thinkwidgetTM_config(
    TP_LEGACY_MICROS_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=False,
    args={},
    wires={},
)
class ThinkProgramLegacyMicrosWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        return True

    def _on_fill(self, signal, position, fill_data, limits, stats):
        return True


# =============================================================================
# Fixtures / registration
# =============================================================================


def _register_thinkprogram_widgets_v1() -> None:
    for cls in [
        ThinkProgramProfileSourceWidget,
        ThinkProgramRiskSourceWidget,
        ThinkProgramReviewWidget,
        ThinkProgramApprovalWidget,
        ThinkProgramLegacyMicrosWidget,
    ]:
        receipt = pull_thinkwidget_class_into_kernel_v1(cls, overwrite=True)
        assert receipt["ok"] is True

    assert kernel_widget_class_repr_v1(TP_PROFILE_WIDGET)[
        "inferred_kernel_contract_spec"
    ]["enforce_no_premount_shell"] is True

    assert kernel_widget_class_repr_v1(TP_LEGACY_MICROS_WIDGET)[
        "inferred_kernel_contract_spec"
    ]["enforce_no_premount_shell"] is False


def _register_all_thinkprogram_test_integration_v1() -> None:
    _register_thinkprogram_widgets_v1()
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def _valid_think_program_v1() -> Dict[str, Any]:
    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "app.product": {
                "value": "Acme",
                "parametrize": True,
            },
            "app.env": {
                "value": "dev",
                "parametrize": True,
            },
            "debug.enabled": {
                "value": False,
                "parametrize": True,
            },
            "aesthetics.theme": {
                "value": {
                    "density": "comfortable",
                    "tone": "warm",
                },
                "parametrize": True,
            },
            "widget.profile.seed": {
                "value": "alpha-seed",
                "parametrize": True,
            },
            "widget.review.mode": {
                "value": "friendly",
                "parametrize": True,
            },
            "lifecycle.default": {
                "value": {
                    "max_reexplosions": 10,
                    "max_proc_notes": 0,
                    "max_messages": 8,
                },
            },
            "lifecycle.long": {
                "value": {
                    "max_reexplosions": 20,
                    "max_proc_notes": 0,
                    "max_messages": 12,
                },
            },
            "history.latest.required": {
                "value": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            },
            "history.latest.optional": {
                "value": {
                    "select": "latest",
                    "required": False,
                    "max_results": 20,
                },
            },
            "history.all.optional": {
                "value": {
                    "select": "all",
                    "required": False,
                    "max_results": 50,
                },
            },
        },
        "puppeteering": {
            "app.env": "prod",
            "debug.enabled": True,
            "widget.profile.seed": "prod-seed",
            "aesthetics.theme": {
                "density": "compact",
                "tone": "neutral",
            },
        },
        "run": {
            "program": {
                "info": {
                    "id": "onboarding",
                    "title": "Onboarding",
                    "description": "Example ThinkProgramTM flow.",
                    "args": {
                        "product": "$app.product",
                        "env": "$app.env",
                    },
                },
                "widgets": {
                    "profile": {
                        "widget": TP_PROFILE_WIDGET,
                        "title": "Profile",
                        "args": {
                            "seed": "$widget.profile.seed",
                            "threshold": 7,
                            "labels": ["default", "beta"],
                        },
                        "lifecycle": "$lifecycle.long",
                        "wires": {},
                        "tags": ["profile", "source"],
                        "system_flags": {
                            "ui_region": "main",
                        },
                        "authoritative": True,
                    },
                    "risk": {
                        "widget": TP_RISK_WIDGET,
                        "title": "Risk",
                        "args": {
                            "seed": "risk-seed",
                            "score_floor": 0.2,
                        },
                        "lifecycle": "$lifecycle.default",
                        "wires": {},
                        "tags": ["risk", "source"],
                        "system_flags": {
                            "ui_region": "side",
                        },
                        "authoritative": True,
                    },
                    "review": {
                        "widget": TP_REVIEW_WIDGET,
                        "title": "Review",
                        "args": {
                            "local": "$widget.review.mode",
                        },
                        "lifecycle": "$lifecycle.default",
                        "wires": {
                            "previous_profile": {
                                "from": "profile",
                                "history": "$history.latest.required",
                            },
                            "profile_history": {
                                "from": "profile",
                                "history": "$history.all.optional",
                            },
                            "risk_sources": {
                                "from": ["risk"],
                                "history": "$history.latest.optional",
                            },
                        },
                        "tags": ["review"],
                        "system_flags": {
                            "ui_region": "main",
                        },
                        "authoritative": True,
                    },
                    "approval": {
                        "widget": TP_APPROVAL_WIDGET,
                        "title": "Approval",
                        "args": {
                            "mode": "final",
                        },
                        "lifecycle": "$lifecycle.default",
                        "wires": {
                            "review": {
                                "from": "review",
                                "history": "$history.latest.required",
                            },
                            "all_sources": {
                                "from": ["profile", "risk"],
                                "history": "$history.latest.optional",
                            },
                            "self_previous": {
                                "from": {
                                    "self": "previous",
                                },
                                "history": "$history.latest.optional",
                            },
                        },
                        "tags": ["approval"],
                        "system_flags": {
                            "ui_region": "main",
                        },
                        "authoritative": True,
                    },
                },
                "flow": [
                    {
                        "id": "collect_profile",
                        "title": "Collect profile",
                        "widgets": ["profile"],
                        "authoritative": [True],
                        "overrides": {
                            "args": {
                                "profile": {
                                    "threshold": 9,
                                },
                            },
                            "lifecycle": {
                                "profile": {
                                    "max_messages": 10,
                                },
                            },
                            "tags": {
                                "profile": ["profile", "source", "first-step"],
                            },
                            "system_flags": {
                                "profile": {
                                    "frame_specific": True,
                                },
                            },
                        },
                    },
                    {
                        "id": "collect_risk",
                        "title": "Collect risk",
                        "widgets": ["risk"],
                        "authoritative": [True],
                        "overrides": {
                            "args": {
                                "risk": {
                                    "score_floor": 0.5,
                                },
                            },
                        },
                    },
                    {
                        "id": "review_profile",
                        "title": "Review profile",
                        "widgets": ["review"],
                        "authoritative": [True],
                        "overrides": {
                            "args": {
                                "review": {
                                    "local": "strict-review",
                                },
                            },
                        },
                    },
                    {
                        "id": "preapproval",
                        "title": "Preapproval",
                        "widgets": ["approval"],
                        "authoritative": [True],
                        "overrides": {
                            "args": {
                                "approval": {
                                    "mode": "preapproval",
                                },
                            },
                            "wires": {
                                "approval": {
                                    "self_previous": None,
                                },
                            },
                        },
                    },
                    {
                        "id": "final_approval",
                        "title": "Final approval",
                        "widgets": ["approval"],
                        "authoritative": [True],
                        "overrides": {
                            "args": {
                                "approval": {
                                    "mode": "final",
                                },
                            },
                            "wires": {
                                "approval": {
                                    "self_previous": {
                                        "from": {
                                            "self": "previous",
                                        },
                                        "history": "$history.latest.required",
                                    },
                                },
                            },
                        },
                    },
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                },
                "app": {
                    "slug": "onboarding",
                    "product": "$app.product",
                    "env": "$app.env",
                },
                "debug": {
                    "enabled": "$debug.enabled",
                },
            },
        },
    }


# =============================================================================
# Documentation / shape tests
# =============================================================================


def test_thinkprogram_language_design_laws_are_documented_by_reference_constants() -> None:
    assert LANG_THINK_PROGRAM_V1 == "think_program_v1"
    assert THINK_PROGRAM_KIND_V1 == "think_program_v1"
    assert THINK_PROGRAM_SURFACE_VERSION_V1 == "v1"

    assert PUPPETEERING_OVERLAY_KEY_V1 == (
        "__puppeteering_overrides_v1__"
    )
    assert PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1 == "merge_onto"
    assert PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1 == "take_over"

    assert _ALLOWED_TOP_LEVEL_KEYS_V1 == {
        "kind",
        "surface_version",
        "symbols",
        "puppeteering",
        "run",
    }

    assert _ALLOWED_PROGRAM_KEYS_V1 == {
        "info",
        "widgets",
        "flow",
    }

    assert _ALLOWED_PROGRAM_INFO_KEYS_V1 == {
        "id",
        "title",
        "description",
        "args",
    }

    assert _ALLOWED_WIDGET_DEF_KEYS_V1 == {
        "widget",
        "title",
        "args",
        "lifecycle",
        "wires",
        "roles",
        "tags",
        "system_flags",
        "authoritative",
    }

    assert _ALLOWED_FLOW_ITEM_KEYS_V1 == {
        "id",
        "title",
        "widgets",
        "roles",
        "authoritative",
        "overrides",
    }


    assert _ALLOWED_OVERRIDE_KEYS_V1 == {
        "args",
        "wires",
        "lifecycle",
        "roles",
        "tags",
        "system_flags",
        "title",
    }

    assert _DEFAULT_KERNEL_FLAGS_V1 == {
        "copy_form_frame_span_args_into_each_datum": True,
        "mount_explode_default": True,
    }

    assert _DEFAULT_LIFECYCLE_V1 == {
        "mount_explode": True,
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
    }


def test_register_think_program_language_registers_higher_language() -> None:
    _register_all_thinkprogram_test_integration_v1()

    assert is_program_language_registered(LANG_THINK_PROGRAM_V1)
    assert is_program_language_registered(LANG_THINKING_FLOW_EXPLICIT_V1)


def test_thinkprogram_final_design_contract_is_documented_as_executable_spec() -> None:
    """
    This is intentionally a high-level executable spec.
    """
    design_contract = {
        "language": LANG_THINK_PROGRAM_V1,
        "highest_surface": {
            "authors_write": [
                "symbols",
                "puppeteering",
                "run.program.info",
                "run.program.widgets",
                "run.program.flow",
                "overrides",
                "logical wires",
            ],
            "authors_do_not_write": [
                "micros",
                "kernel history aliases",
                "step functions",
                "multiframespecs",
                "explicit datums",
                "premount shells",
            ],
        },
        "one_flow_item_lowers_to": {
            "step": "program_id.flow_id",
            "form": "program_id.flow_id.form",
            "frame": "frame",
            "span": "span",
        },
        "widget_admission": {
            "must_be_kernel_registered": True,
            "must_enforce_no_premount_shell": True,
            "args_validated_by_widget_contract": True,
            "wires_validated_by_widget_contract": True,
        },
        "runtime_seam": {
            "kernel_packet_path": "q['datum']['args']['__kernel']",
            "root_q_pollution_allowed": False,
        },
        "starter_to_run_parameterization": {
            "input_name": "initial_parameter_overrides",
            "reserved_control_key": PUPPETEERING_OVERLAY_KEY_V1,
            "target_pocket": "program.puppeteering",
            "merge_modes": ["merge_onto", "take_over"],
            "strict_true_requires_declared_parametrized_symbols": True,
            "django_semantics": "pass-through; no extra runtime pocket",
            "dict_op": "shallow symbol-name assignment",
        },
        "lowering_chain": [
            LANG_THINK_PROGRAM_V1,
            LANG_THINKING_FLOW_EXPLICIT_V1,
            "app_table",
            "think.kernel.v1",
        ],
    }

    json.dumps(design_contract, sort_keys=True)

    assert design_contract["highest_surface"]["authors_do_not_write"] == [
        "micros",
        "kernel history aliases",
        "step functions",
        "multiframespecs",
        "explicit datums",
        "premount shells",
    ]
    assert design_contract["widget_admission"] == {
        "must_be_kernel_registered": True,
        "must_enforce_no_premount_shell": True,
        "args_validated_by_widget_contract": True,
        "wires_validated_by_widget_contract": True,
    }
    assert design_contract["runtime_seam"] == {
        "kernel_packet_path": "q['datum']['args']['__kernel']",
        "root_q_pollution_allowed": False,
    }


# =============================================================================
# Symbol / puppeteering tests
# =============================================================================


def test_symbols_resolve_only_inside_run_and_do_not_mutate_source() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    before = copy.deepcopy(source)

    run = bind_think_program_symbols_v1(source)

    assert source == before
    assert run["program"]["info"]["args"] == {
        "product": "Acme",
        "env": "prod",
    }
    assert run["config"]["app"]["env"] == "prod"
    assert run["config"]["debug"]["enabled"] is True

    profile_args = run["program"]["widgets"]["profile"]["args"]
    assert profile_args["seed"] == "prod-seed"


def _initial_parameter_overrides_v1(
    *,
    mode: str = PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    strict: bool = True,
    values: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    packet = {
        PUPPETEERING_OVERLAY_KEY_V1: {
            "mode": mode,
            "strict": strict,
        }
    }
    packet.update(dict(values or {}))
    return packet


def test_initial_parameter_overrides_normalize_to_overlay_control_and_values() -> None:
    normalized = normalize_initial_parameter_overrides_v1(
        _initial_parameter_overrides_v1(
            mode=PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
            strict=False,
            values={
                "app.env": "stage",
            },
        )
    )

    assert normalized == {
        "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
        "strict": False,
        "values": {
            "app.env": "stage",
        },
    }

    normalized = normalize_initial_parameter_overrides_v1(
        {
            "app.env": "stage",
        }
    )

    assert normalized == {
        "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        "strict": True,
        "values": {
            "app.env": "stage",
        },
    }


def test_initial_parameter_overrides_merge_onto_authored_puppeteering() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    before = copy.deepcopy(source)

    run = bind_think_program_symbols_v1(
        source,
        initial_parameter_overrides=_initial_parameter_overrides_v1(
            mode=PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
            strict=True,
            values={
                "app.env": "stage",
                "widget.profile.seed": "launch-seed",
            },
        ),
    )

    assert source == before
    assert source["puppeteering"]["app.env"] == "prod"
    assert source["puppeteering"]["widget.profile.seed"] == "prod-seed"

    assert run["config"]["app"]["env"] == "stage"
    assert run["config"]["debug"]["enabled"] is True
    assert run["program"]["widgets"]["profile"]["args"]["seed"] == "launch-seed"


def test_initial_parameter_overrides_take_over_replaces_authored_puppeteering() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    effective = overlay_initial_parameter_overrides_onto_program_v1(
        source,
        initial_parameter_overrides=_initial_parameter_overrides_v1(
            mode=PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
            strict=True,
            values={
                "app.env": "stage",
            },
        ),
    )

    assert source["puppeteering"]["app.env"] == "prod"
    assert effective["puppeteering"] == {
        "app.env": "stage",
    }

    run = bind_think_program_symbols_v1(effective)

    assert run["config"]["app"]["env"] == "stage"

    # Existing authored puppeteering melted entirely.
    assert run["config"]["debug"]["enabled"] is False
    assert run["program"]["widgets"]["profile"]["args"]["seed"] == "alpha-seed"


def test_initial_parameter_overrides_strict_mode_rejects_unknown_or_unparametrized_symbols() -> None:
    source = _valid_think_program_v1()

    with pytest.raises(ValueError, match="unknown symbol"):
        bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=_initial_parameter_overrides_v1(
                strict=True,
                values={
                    "does.not.exist": "x",
                },
            ),
        )

    with pytest.raises(ValueError, match="not parametrized"):
        bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=_initial_parameter_overrides_v1(
                strict=True,
                values={
                    "lifecycle.default": {
                        "max_reexplosions": 99,
                    },
                },
            ),
        )


def test_initial_parameter_overrides_nonstrict_mode_drops_unknown_or_unparametrized_symbols() -> None:
    source = _valid_think_program_v1()

    run = bind_think_program_symbols_v1(
        source,
        initial_parameter_overrides=_initial_parameter_overrides_v1(
            strict=False,
            values={
                "does.not.exist": "ignored",
                "lifecycle.default": {
                    "max_reexplosions": 99,
                },
                "app.env": "stage",
            },
        ),
    )

    assert run["config"]["app"]["env"] == "stage"
    assert run["program"]["widgets"]["review"]["lifecycle"] == {
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
    }


def test_initial_parameter_overrides_are_not_general_globals() -> None:
    """
    Task-B regression guard.

    ``initial_parameter_overrides`` keys are symbol names, not arbitrary global
    variables. A caller may only puppeteer names declared in ``symbols`` and,
    under strict mode, only those marked ``parametrize=true``.
    """

    source = _valid_think_program_v1()

    with pytest.raises(ValueError, match="unknown symbol"):
        overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides={
                PUPPETEERING_OVERLAY_KEY_V1: {
                    "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                    "strict": True,
                },
                "tenant": "acme",
            },
        )

    effective = overlay_initial_parameter_overrides_onto_program_v1(
        source,
        initial_parameter_overrides={
            PUPPETEERING_OVERLAY_KEY_V1: {
                "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                "strict": False,
            },
            "tenant": "ignored",
            "app.env": "stage",
        },
    )

    assert effective["puppeteering"]["app.env"] == "stage"
    assert "tenant" not in effective["puppeteering"]


def test_initial_parameter_overrides_are_consumed_by_thinkprogram_language_lowerer() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    before = copy.deepcopy(source)

    bundle = lower_think_program_v1(
        source,
        initial_parameter_overrides=_initial_parameter_overrides_v1(
            mode=PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
            values={
                "app.env": "qa",
            },
        ),
    )

    assert source == before
    assert bundle.provenance["source_program"] == before
    assert bundle.provenance["effective_source_program"]["puppeteering"] == {
        "app.env": "qa",
    }
    assert bundle.provenance["resolved_run"]["config"]["app"]["env"] == "qa"
    assert bundle.provenance["resolved_run"]["config"]["debug"]["enabled"] is False
    assert bundle.session_surface["run_config"]["app"]["env"] == "qa"


def test_program_language_registry_passes_initial_parameter_overrides_to_lowerer() -> None:
    _register_all_thinkprogram_test_integration_v1()

    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINK_PROGRAM_V1,
        program=_valid_think_program_v1(),
        initial_parameter_overrides=_initial_parameter_overrides_v1(
            values={
                "app.env": "registry-env",
            },
        ),
    )

    assert isinstance(bundle, ProgramLoweringBundle)
    assert bundle.session_surface["run_config"]["app"]["env"] == "registry-env"


def test_unparametrized_symbol_cannot_be_puppeteered() -> None:
    source = _valid_think_program_v1()
    source["puppeteering"]["history.latest.required"] = {
        "select": "all",
        "required": True,
        "max_results": 99,
    }

    with pytest.raises(ValueError, match="not parametrized"):
        bind_think_program_symbols_v1(source)


def test_unknown_symbol_reference_fails() -> None:
    source = _valid_think_program_v1()
    source["run"]["config"]["app"]["env"] = "$app.missing"

    with pytest.raises(ValueError, match="unresolved symbol reference"):
        bind_think_program_symbols_v1(source)


def test_partial_interpolation_is_rejected() -> None:
    source = _valid_think_program_v1()
    source["run"]["config"]["app"]["env"] = "env=${app.env}"

    with pytest.raises(ValueError, match="interpolation"):
        bind_think_program_symbols_v1(source)


def test_longest_symbol_match_supports_nested_lookup() -> None:
    source = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "a.b": {
                "value": {
                    "c": "from-a-b",
                },
            },
            "a.b.c": {
                "value": {
                    "d": "from-a-b-c",
                },
            },
        },
        "run": {
            "x": "$a.b.c.d",
            "y": "$a.b.c",
        },
    }

    run = bind_think_program_symbols_v1(source)

    assert run["x"] == "from-a-b-c"
    assert run["y"] == {
        "d": "from-a-b-c",
    }


def _assert_no_symbol_refs_remaining_v1(value: Any, *, path: str = "value") -> None:
    if isinstance(value, str):
        assert not value.startswith("$"), (path, value)
        assert "${" not in value, (path, value)
        return

    if isinstance(value, list):
        for i, child in enumerate(value):
            _assert_no_symbol_refs_remaining_v1(child, path=f"{path}[{i}]")
        return

    if isinstance(value, Mapping):
        for key, child in dict(value).items():
            _assert_no_symbol_refs_remaining_v1(child, path=f"{path}.{key}")


def test_bind_and_lower_are_pure_and_leave_no_symbol_refs_in_resolved_run() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    before = copy.deepcopy(source)

    run = bind_think_program_symbols_v1(source)
    kernel_program = lower_think_program_to_kernel_program_v1(source)
    bundle = lower_think_program_v1(source)

    assert source == before

    _assert_no_symbol_refs_remaining_v1(run, path="resolved_run")
    _assert_no_symbol_refs_remaining_v1(
        bundle.provenance["resolved_run"],
        path="bundle.provenance.resolved_run",
    )

    assert bundle.provenance["resolved_run"] == run
    assert bundle.provenance["explicit_kernel_program"] == kernel_program
    assert bundle.provenance["source_program"] == before


def test_symbols_are_not_resolved_inside_symbols_section_itself() -> None:
    source = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "a": {
                "value": "$b",
                "parametrize": True,
            },
            "b": {
                "value": "resolved-b",
            },
        },
        "puppeteering": {},
        "run": {
            "x": "$a",
            "y": "$b",
        },
    }

    run = bind_think_program_symbols_v1(source)

    # Symbols are copied as values. They are not recursively expanded while
    # building the effective symbol table.
    assert run["x"] == "$b"
    assert run["y"] == "resolved-b"


def test_symbol_reference_to_list_index_is_supported_by_longest_match() -> None:
    source = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "choices": {
                "value": [
                    {"name": "first"},
                    {"name": "second"},
                ],
            },
        },
        "run": {
            "picked": "$choices.1.name",
        },
    }

    run = bind_think_program_symbols_v1(source)

    assert run == {
        "picked": "second",
    }


def test_empty_symbol_reference_and_missing_nested_segment_fail() -> None:
    source = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "a": {
                "value": {
                    "b": "ok",
                },
            },
        },
        "run": {
            "x": "$",
        },
    }

    with pytest.raises(ValueError, match="empty symbol reference"):
        bind_think_program_symbols_v1(source)

    source = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "a": {
                "value": {
                    "b": "ok",
                },
            },
        },
        "run": {
            "x": "$a.c",
        },
    }

    with pytest.raises(ValueError, match="missing nested segment"):
        bind_think_program_symbols_v1(source)


# =============================================================================
# Static validation tests
# =============================================================================


def test_top_surface_rejects_authored_micros_anywhere_under_run_program() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["micros"] = [_text_micro("value")]

    with pytest.raises(ValueError, match="may not author 'micros'"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["overrides"]["micros"] = {
        "profile": [_text_micro("value")]
    }

    with pytest.raises(ValueError, match="may not author 'micros'"):
        lower_think_program_to_kernel_program_v1(source)


def test_top_surface_admits_only_empty_premount_mount_shelling_widgets() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["legacy"] = {
        "widget": TP_LEGACY_MICROS_WIDGET,
        "title": "Legacy",
        "args": {},
        "wires": {},
    }
    source["run"]["program"]["flow"][0]["widgets"] = ["legacy"]
    source["run"]["program"]["flow"][0]["authoritative"] = [True]

    with pytest.raises(ValueError, match="enforce_no_premount_shell=true"):
        lower_think_program_to_kernel_program_v1(source)


def test_widget_arg_contract_is_enforced_before_kernel_lowering() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["args"]["unknown"] = "nope"

    with pytest.raises(ValueError, match="unknown args"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    del source["run"]["program"]["widgets"]["profile"]["args"]["seed"]

    with pytest.raises(ValueError, match="missing required arg"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["args"]["threshold"] = "high"

    with pytest.raises(ValueError, match="must be int"):
        lower_think_program_to_kernel_program_v1(source)


def test_widget_wire_contract_is_enforced_before_kernel_lowering() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["review"]["wires"]["not_declared"] = {
        "from": "profile",
        "history": "$history.latest.required",
    }

    with pytest.raises(ValueError, match="unknown wires"):
        lower_think_program_to_kernel_program_v1(source)


def test_required_missing_history_source_fails_statically() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"] = [
        source["run"]["program"]["flow"][2],
    ]

    with pytest.raises(ValueError, match="required wire review.previous_profile"):
        lower_think_program_to_kernel_program_v1(source)


def test_optional_missing_history_source_is_omitted() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()

    # Keep only one approval step. Its "review" wire is required and has a
    # prior source. Its "self_previous" wire is optional and has no prior
    # approval appearance, so the ThinkProgram lowerer should omit it.
    source["run"]["program"]["flow"] = [
        source["run"]["program"]["flow"][0],  # collect_profile
        source["run"]["program"]["flow"][1],  # collect_risk
        source["run"]["program"]["flow"][2],  # review_profile
        {
            "id": "first_approval",
            "title": "First approval",
            "widgets": ["approval"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "approval": {
                        "mode": "first",
                    },
                },
                # Do not remove self_previous. Let the lowerer see that the
                # authored optional self wire has no prior approval source.
                "wires": {
                    "approval": {
                        "self_previous": {
                            "from": {
                                "self": "previous",
                            },
                            "history": "$history.latest.optional",
                        },
                    },
                },
            },
        },
    ]

    kernel_program = lower_think_program_to_kernel_program_v1(source)

    approval_step = kernel_program[3]
    approval = approval_step["datums"][0]

    assert approval_step["step"]["id"] == "onboarding.first_approval"
    assert approval["id"] == "approval"

    # Required wires with available prior sources remain.
    assert sorted(approval["past_wires"]) == [
        "all_sources",
        "review",
    ]

    # Optional missing prior self source is omitted.
    assert "self_previous" not in approval["past_wires"]

    rendered_queries = str(approval_step["history_queries"])
    assert "onboarding.review_profile" in rendered_queries
    assert "onboarding.collect_profile" in rendered_queries
    assert "onboarding.collect_risk" in rendered_queries
    assert "onboarding.first_approval" not in rendered_queries

    validate_kernel_program_v1(kernel_program)


def test_flow_validation_rejects_duplicates_unknowns_and_bad_authoritative_lengths() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][1]["id"] = "collect_profile"

    with pytest.raises(ValueError, match="duplicate flow id"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["widgets"] = ["profile", "profile"]

    with pytest.raises(ValueError, match="may not repeat"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["widgets"] = ["missing"]

    with pytest.raises(ValueError, match="unknown logical widget"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["authoritative"] = [True, False]

    with pytest.raises(ValueError, match="authoritative length"):
        lower_think_program_to_kernel_program_v1(source)


def test_single_widget_flow_cannot_lower_to_empty_authoritative_span_today() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"] = [
        {
            "id": "non_authoritative_only",
            "title": "Non-authoritative only",
            "widgets": ["profile"],
            "authoritative": [False],
        }
    ]

    with pytest.raises(ValueError, match="no authoritative datums"):
        lower_think_program_to_kernel_program_v1(source)


def test_thinkprogram_rejects_unknown_author_keys_at_all_strict_shape_layers() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["unexpected"] = True

    with pytest.raises(ValueError, match="program has unknown keys"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["unexpected"] = True

    with pytest.raises(ValueError, match="run\\.program has unknown keys"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["info"]["unexpected"] = True

    with pytest.raises(ValueError, match="run\\.program\\.info has unknown keys"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["unexpected"] = True

    with pytest.raises(
        ValueError,
        match=r"run\.program\.widgets\['profile'\] has unknown keys",
    ):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["unexpected"] = True

    with pytest.raises(ValueError, match=r"run\.program\.flow\[0\] has unknown keys"):
        lower_think_program_to_kernel_program_v1(source)


# =============================================================================
# Addendum: final ThinkProgramTM static validation matrix
# =============================================================================


def test_thinkprogram_rejects_bad_top_level_kind_and_surface_version() -> None:
    source = _valid_think_program_v1()
    source["kind"] = "not_think_program"

    with pytest.raises(ValueError, match="program.kind"):
        bind_think_program_symbols_v1(source)

    source = _valid_think_program_v1()
    source["surface_version"] = "v2"

    with pytest.raises(ValueError, match="surface_version"):
        bind_think_program_symbols_v1(source)


def test_thinkprogram_rejects_non_dead_json_symbol_values_and_puppeteering_values() -> None:
    source = _valid_think_program_v1()
    source["symbols"]["bad.callable"] = {
        "value": lambda: None,
        "parametrize": True,
    }

    with pytest.raises(ValueError, match="dead JSON"):
        bind_think_program_symbols_v1(source)

    source = _valid_think_program_v1()
    source["symbols"]["bad.param"] = {
        "value": "ok",
        "parametrize": True,
    }
    source["puppeteering"]["bad.param"] = lambda: None

    with pytest.raises(ValueError, match="dead JSON"):
        bind_think_program_symbols_v1(source)


def test_thinkprogram_rejects_unknown_puppeteering_symbol() -> None:
    source = _valid_think_program_v1()
    source["puppeteering"]["does.not.exist"] = "x"

    with pytest.raises(ValueError, match="unknown symbol"):
        bind_think_program_symbols_v1(source)


def test_flow_overrides_may_only_target_widgets_present_in_that_flow_item() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["overrides"]["args"]["risk"] = {
        "score_floor": 0.7,
    }

    with pytest.raises(ValueError, match="not present in this flow item"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["overrides"]["title"] = {
        "review": "Not here",
    }

    with pytest.raises(ValueError, match="not present in this flow item"):
        lower_think_program_to_kernel_program_v1(source)


def test_flow_overrides_reject_unknown_override_sections() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["overrides"]["micros_like_bad_section"] = {
        "profile": []
    }

    with pytest.raises(ValueError, match="unknown keys"):
        lower_think_program_to_kernel_program_v1(source)


def test_wire_history_and_source_forms_are_strict() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["symbols"]["history.invalid"] = {
        "value": {
            "select": "middle",
            "required": True,
            "max_results": 20,
        },
    }
    source["run"]["program"]["widgets"]["review"]["wires"]["previous_profile"] = {
        "from": "profile",
        "history": "$history.invalid",
    }

    with pytest.raises(ValueError, match="select must be latest\\|all"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["review"]["wires"]["previous_profile"] = {
        "from": [],
        "history": "$history.latest.required",
    }

    with pytest.raises(ValueError, match="non-empty list\\[str\\]"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["review"]["wires"]["previous_profile"] = {
        "from": {
            "widget": "profile",
            "occurrence": "first",
        },
        "history": "$history.latest.required",
    }

    with pytest.raises(ValueError, match="supports only 'previous'"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["review"]["wires"]["previous_profile"] = {
        "from": {
            "not_supported": "profile",
        },
        "history": "$history.latest.required",
    }

    with pytest.raises(ValueError, match="unsupported source form"):
        lower_think_program_to_kernel_program_v1(source)


def test_one_wire_rejects_multiple_resolved_aliases() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()

    source["run"]["program"]["widgets"]["review"]["wires"]["previous_profile"] = {
        "from": ["profile", "risk"],
        "history": "$history.latest.required",
    }

    with pytest.raises(ValueError, match="requires exactly one resolved alias"):
        lower_think_program_to_kernel_program_v1(source)


def test_required_contract_wire_cannot_be_removed_when_no_aliases_remain() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][2]["overrides"]["wires"] = {
        "review": {
            "previous_profile": None,
        }
    }

    with pytest.raises(ValueError, match="missing required wire|resolved no aliases"):
        lower_think_program_to_kernel_program_v1(source)


def test_reserved_kernel_arg_cannot_be_authored_at_top_surface() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["args"]["__kernel"] = {
        "bad": True,
    }

    with pytest.raises(ValueError, match="unknown args|reserved key"):
        lower_think_program_to_kernel_program_v1(source)


def test_title_tags_system_flags_and_authoritative_defaults_lower_exactly() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()

    del source["run"]["program"]["flow"][0]["authoritative"]
    source["run"]["program"]["flow"][0]["overrides"]["title"] = {
        "profile": "Profile title overridden in first frame",
    }
    source["run"]["program"]["flow"][0]["overrides"]["tags"] = {
        "profile": ["only", "these", "tags"],
    }
    source["run"]["program"]["flow"][0]["overrides"]["system_flags"] = {
        "profile": {
            "ui_region": "hero",
            "frame_specific": "profile-in-shared-frame",
            "local_flag": "present",
        },
    }

    kernel_program = lower_think_program_to_kernel_program_v1(source)
    profile = kernel_program[0]["datums"][0]

    assert profile["title"] == "Profile title overridden in first frame"

    # Tags are replacement semantics, not merge semantics.
    assert profile["tags"] == ["only", "these", "tags"]

    # System flags are deep-merge semantics with scalar replacement, plus the
    # compiler-owned logical_widget_id marker.
    assert profile["system_flags"] == {
        "ui_region": "hero",
        "frame_specific": "profile-in-shared-frame",
        "local_flag": "present",
        "logical_widget_id": "profile",
    }

    # flow.authoritative absent means the widget default is used.
    assert profile["authoritative"] is True

    validate_kernel_program_v1(kernel_program)
    

def test_all_generated_kernel_datums_satisfy_compiler_owned_machine_shape() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    kernel_program = lower_think_program_to_kernel_program_v1(source)

    assert kernel_program
    for step_index, k in enumerate(kernel_program):
        assert k["kind"] == "think_kernel_step_v1"
        assert k["kernel_args_surface_version"] == "v1"
        assert k["step"]["id"]
        assert k["form"]["id"] == f"{k['step']['id']}.form"
        assert k["frame"]["id"] == "frame"
        assert k["span"]["id"] == "span"

        assert k["kernel_flags"]["copy_form_frame_span_args_into_each_datum"] is True
        assert k["kernel_flags"]["mount_explode_default"] is True

        for datum_index, d in enumerate(k["datums"]):
            assert d["micros"] == [], (step_index, datum_index, d)
            assert d["lifecycle"]["mount_explode"] is True
            assert "logical_widget_id" in d["system_flags"]
            assert d["system_flags"]["logical_widget_id"] == d["id"]
            assert "__kernel" not in dict(d.get("args") or {})

    validate_kernel_program_v1(kernel_program)



def test_program_requires_run_program_info_widgets_and_flow() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    del source["run"]

    with pytest.raises(ValueError, match="program.run is required"):
        bind_think_program_symbols_v1(source)

    source = _valid_think_program_v1()
    del source["run"]["program"]

    with pytest.raises(ValueError, match="run.program must be mapping"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    del source["run"]["program"]["info"]

    with pytest.raises(ValueError, match="run.program.info must be mapping"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    del source["run"]["program"]["widgets"]

    with pytest.raises(ValueError, match="run.program.widgets must be mapping"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"] = []

    with pytest.raises(ValueError, match="flow must be non-empty list"):
        lower_think_program_to_kernel_program_v1(source)


def test_program_info_required_identity_fields_are_strict() -> None:
    _register_all_thinkprogram_test_integration_v1()

    for key, expected in [
        ("id", "run.program.info.id"),
        ("title", "run.program.info.title"),
    ]:
        source = _valid_think_program_v1()
        source["run"]["program"]["info"][key] = ""

        with pytest.raises(ValueError, match=expected):
            lower_think_program_to_kernel_program_v1(source)


def test_widget_definition_requires_registered_widget_name() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["widget"] = ""

    with pytest.raises(ValueError, match="widget"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["widget"] = (
        "test._thinkprogram.not_registered"
    )

    with pytest.raises(ValueError, match="unknown datum widget|no readable kernel contract"):
        lower_think_program_to_kernel_program_v1(source)


def test_flow_widgets_must_be_nonempty_list_of_known_strings() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["widgets"] = []

    with pytest.raises(ValueError, match="widgets must be non-empty list"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["widgets"] = "profile"

    with pytest.raises(ValueError, match="widgets must be non-empty list"):
        lower_think_program_to_kernel_program_v1(source)


def test_authoritative_items_must_be_bool_and_span_must_have_one_authoritative() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["authoritative"] = ["true"]

    with pytest.raises(ValueError, match="authoritative must be list\\[bool\\]"):
        lower_think_program_to_kernel_program_v1(source)

    source = _multi_widget_source_frame_think_program_v1()
    source["run"]["program"]["flow"][0]["authoritative"] = [False, True]

    kernel_program = lower_think_program_to_kernel_program_v1(source)
    collect = kernel_program[0]

    assert [d["authoritative"] for d in collect["datums"]] == [False, True]
    validate_kernel_program_v1(kernel_program)

    source = _multi_widget_source_frame_think_program_v1()
    source["run"]["program"]["flow"][0]["authoritative"] = [False, False]

    with pytest.raises(ValueError, match="no authoritative datums"):
        lower_think_program_to_kernel_program_v1(source)

def test_override_sections_must_be_mappings() -> None:
    _register_all_thinkprogram_test_integration_v1()

    for override_kind in sorted(_ALLOWED_OVERRIDE_KEYS_V1):
        source = _valid_think_program_v1()
        source["run"]["program"]["flow"][0]["overrides"][override_kind] = []

        with pytest.raises(ValueError, match=f"overrides.{override_kind} must be mapping"):
            lower_think_program_to_kernel_program_v1(source)



# =============================================================================
# Lowering correctness tests
# =============================================================================


def test_valid_program_lowers_to_exact_kernel_step_ids_and_empty_micros() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(_valid_think_program_v1())

    assert [k["step"]["id"] for k in kernel_program] == [
        "onboarding.collect_profile",
        "onboarding.collect_risk",
        "onboarding.review_profile",
        "onboarding.preapproval",
        "onboarding.final_approval",
    ]

    assert [k["form"]["id"] for k in kernel_program] == [
        "onboarding.collect_profile.form",
        "onboarding.collect_risk.form",
        "onboarding.review_profile.form",
        "onboarding.preapproval.form",
        "onboarding.final_approval.form",
    ]

    for k in kernel_program:
        assert k["frame"]["id"] == "frame"
        assert k["span"]["id"] == "span"
        for d in k["datums"]:
            assert d["micros"] == []
            assert d["lifecycle"]["mount_explode"] is True

    validate_kernel_program_v1(kernel_program)


def test_lowering_applies_symbols_puppeteering_overrides_and_authoritative() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(_valid_think_program_v1())

    collect_profile = kernel_program[0]
    profile = collect_profile["datums"][0]

    assert profile["args"] == {
        "seed": "prod-seed",
        "threshold": 9,
        "labels": ["default", "beta"],
    }
    assert profile["lifecycle"]["max_reexplosions"] == 20
    assert profile["lifecycle"]["max_messages"] == 10
    assert profile["tags"] == ["profile", "source", "first-step"]
    assert profile["system_flags"] == {
        "ui_region": "main",
        "frame_specific": True,
        "logical_widget_id": "profile",
    }
    assert profile["authoritative"] is True

    review = kernel_program[2]["datums"][0]
    assert review["args"] == {
        "local": "strict-review",
    }

    preapproval = kernel_program[3]["datums"][0]
    final_approval = kernel_program[4]["datums"][0]

    assert preapproval["args"] == {
        "mode": "preapproval",
    }
    assert preapproval["authoritative"] is True

    assert final_approval["args"] == {
        "mode": "final",
    }
    assert final_approval["authoritative"] is True


def test_lowering_resolves_logical_wires_into_history_queries_and_past_wires() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(_valid_think_program_v1())

    review_step = kernel_program[2]
    review = review_step["datums"][0]

    assert sorted(review["past_wires"]) == [
        "previous_profile",
        "profile_history",
        "risk_sources",
    ]

    assert len(review["past_wires"]["previous_profile"]) == 1
    previous_profile_alias = review["past_wires"]["previous_profile"][0]
    assert review_step["history_queries"][previous_profile_alias]["from_step"] == (
        "onboarding.collect_profile"
    )
    assert review_step["history_queries"][previous_profile_alias]["datum_id"] == "profile"
    assert review_step["history_queries"][previous_profile_alias]["select"] == "latest"
    assert review_step["history_queries"][previous_profile_alias]["required"] is True

    profile_history_alias = review["past_wires"]["profile_history"][0]
    assert review_step["history_queries"][profile_history_alias]["select"] == "all"

    risk_alias = review["past_wires"]["risk_sources"][0]
    assert review_step["history_queries"][risk_alias]["from_step"] == (
        "onboarding.collect_risk"
    )
    assert review_step["history_queries"][risk_alias]["datum_id"] == "risk"

    preapproval_step = kernel_program[3]
    preapproval = preapproval_step["datums"][0]

    assert sorted(preapproval["past_wires"]) == [
        "all_sources",
        "review",
    ]
    assert "self_previous" not in preapproval["past_wires"]

    final_step = kernel_program[4]
    final = final_step["datums"][0]

    assert sorted(final["past_wires"]) == [
        "all_sources",
        "review",
        "self_previous",
    ]

    self_alias = final["past_wires"]["self_previous"][0]
    assert final_step["history_queries"][self_alias]["from_step"] == (
        "onboarding.preapproval"
    )
    assert final_step["history_queries"][self_alias]["datum_id"] == "approval"
    assert final_step["history_queries"][self_alias]["required"] is True


def test_program_language_lowerer_returns_bundle_with_manifest_provenance_and_run_config() -> None:
    _register_all_thinkprogram_test_integration_v1()

    bundle = lower_think_program_v1(_valid_think_program_v1())

    assert isinstance(bundle, ProgramLoweringBundle)
    assert len(bundle.app_table_manifest) == 5

    assert [row["public_step_name"] for row in bundle.app_table_manifest] == [
        "onboarding.collect_profile",
        "onboarding.collect_risk",
        "onboarding.review_profile",
        "onboarding.preapproval",
        "onboarding.final_approval",
    ]

    assert all(row["step_fn"] == "think.kernel.v1" for row in bundle.app_table_manifest)
    assert all("kernel" in row["fn_args"] for row in bundle.app_table_manifest)

    assert bundle.provenance["source_program_language"] == LANG_THINK_PROGRAM_V1
    assert bundle.provenance["lowering_chain"] == [
        {
            "language": LANG_THINK_PROGRAM_V1,
            "artifact": "think_kernel_program_v1",
        },
        {
            "language": LANG_THINKING_FLOW_EXPLICIT_V1,
            "artifact": "app_table_manifest",
        },
    ]

    assert bundle.session_surface["run_config"]["app"] == {
        "slug": "onboarding",
        "product": "Acme",
        "env": "prod",
    }
    assert bundle.session_surface["run_config"]["debug"] == {
        "enabled": True,
    }



def test_public_headless_facade_can_create_session_from_highest_thinkprogram_language() -> None:
    _register_all_thinkprogram_test_integration_v1()

    from _thinkengine.runme_optimized_queryable.facade_base import (
        get_public_session_api,
    )

    public_api = get_public_session_api(raw_api=_api())

    created = public_api.create_session_from_program(
        program=_valid_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_public_facade_create",
        },
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"
    assert created["session_id"]

    report = public_api.current_report(str(created["session_id"]))
    assert report["ok"] is True
    assert report["session_id"] == str(created["session_id"])


def test_service_facade_can_create_core_session_from_highest_thinkprogram_language() -> None:
    _register_all_thinkprogram_test_integration_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        create_core_session_from_program,
    )

    created = create_core_session_from_program(
        program=_valid_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_service_facade_create",
        },
    )

    assert created["ok"] is True
    assert created["operation"] == "create_session_from_program"
    assert created["session_id"]




def _defaults_runtime_think_program_v1() -> Dict[str, Any]:
    source = _valid_think_program_v1()

    # Omit optional args at the ThinkProgram surface. The ThinkProgram lowerer
    # should not inject them. Kernel multiframespec construction applies widget
    # contract defaults at runtime.
    del source["run"]["program"]["widgets"]["profile"]["args"]["threshold"]
    del source["run"]["program"]["widgets"]["profile"]["args"]["labels"]
    del source["run"]["program"]["flow"][0]["overrides"]["args"]["profile"]["threshold"]

    source["run"]["program"]["flow"] = [
        source["run"]["program"]["flow"][0],
    ]

    return source


def test_optional_widget_arg_defaults_are_not_injected_by_thinkprogram_lowerer() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(
        _defaults_runtime_think_program_v1()
    )

    profile = kernel_program[0]["datums"][0]
    assert profile["args"] == {
        "seed": "prod-seed",
    }

    validate_kernel_program_v1(kernel_program)


def test_optional_widget_arg_defaults_are_applied_by_kernel_runtime_e2e() -> None:
    _register_all_thinkprogram_test_integration_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=_defaults_runtime_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_defaults_runtime_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widgets_on_this_span"] == ["profile"]

    profile_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_profile.form",
        "profile",
    )

    assert profile_mount_state["mount_seen_user_args"] == {
        "seed": "prod-seed",
        "threshold": 7,
        "labels": ["default"],
    }

    ctx = runner.step(fill={"profile": {"value": "profile-with-defaults"}})
    assert ctx["kind"] == "ATCOMPLETION"


def _copy_scope_off_think_program_v1() -> Dict[str, Any]:
    source = _valid_think_program_v1()
    source["run"]["program"]["flow"] = [
        {
            "id": "collect_profile",
            "title": "Collect profile",
            "widgets": ["profile"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "profile": {
                        "threshold": 9,
                    },
                },
            },
        }
    ]
    return source


def _repeated_profile_history_think_program_v1() -> Dict[str, Any]:
    source = _valid_think_program_v1()

    source["run"]["program"]["flow"] = [
        {
            "id": "profile_first",
            "title": "Profile first",
            "widgets": ["profile"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "profile": {
                        "threshold": 1,
                    },
                },
            },
        },
        {
            "id": "profile_second",
            "title": "Profile second",
            "widgets": ["profile"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "profile": {
                        "threshold": 2,
                    },
                },
            },
        },
        {
            "id": "collect_risk",
            "title": "Collect risk",
            "widgets": ["risk"],
            "authoritative": [True],
        },
        {
            "id": "review_all_profiles",
            "title": "Review all profiles",
            "widgets": ["review"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "review": {
                        "local": "history-review",
                    },
                },
            },
        },
    ]

    return source


def test_repeated_logical_widget_history_all_resolves_all_prior_appearances() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(
        _repeated_profile_history_think_program_v1()
    )

    review_step = kernel_program[3]
    review = review_step["datums"][0]

    assert review["id"] == "review"
    assert sorted(review["past_wires"]) == [
        "previous_profile",
        "profile_history",
        "risk_sources",
    ]

    assert len(review["past_wires"]["previous_profile"]) == 1
    latest_alias = review["past_wires"]["previous_profile"][0]
    assert review_step["history_queries"][latest_alias]["from_step"] == (
        "onboarding.profile_second"
    )
    assert review_step["history_queries"][latest_alias]["select"] == "latest"

    assert len(review["past_wires"]["profile_history"]) == 2
    history_from_steps = [
        review_step["history_queries"][alias]["from_step"]
        for alias in review["past_wires"]["profile_history"]
    ]
    assert history_from_steps == [
        "onboarding.profile_first",
        "onboarding.profile_second",
    ]

    validate_kernel_program_v1(kernel_program)


def test_repeated_logical_widget_history_all_materializes_all_prior_rows_e2e() -> None:
    _register_all_thinkprogram_test_integration_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=_repeated_profile_history_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_repeated_history_all_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["datum_widgets_on_this_span"] == ["profile"]

    ctx = runner.step(fill={"profile": {"value": "profile-first-value"}})
    assert ctx["datum_widgets_on_this_span"] == ["profile"]

    ctx = runner.step(fill={"profile": {"value": "profile-second-value"}})
    assert ctx["datum_widgets_on_this_span"] == ["risk"]

    ctx = runner.step(fill={"risk": {"value": "risk-value"}})
    assert ctx["datum_widgets_on_this_span"] == ["review"]

    review_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_all_profiles.form",
        "review",
    )

    assert review_mount_state["prior_profile_final_value_on_mount"] == (
        "profile-second-value"
    )
    assert review_mount_state["profile_history_count_on_mount"] >= 2
    assert review_mount_state["risk_sources_count_on_mount"] >= 1

    ctx = runner.step(fill={"review": {"confirm": "history-review-confirmed"}})
    assert ctx["kind"] == "ATCOMPLETION"

    review_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_all_profiles.form",
        "review",
    )

    assert review_done_state["commit"] == {
        "datum_id": "review",
        "confirmed": "history-review-confirmed",
        "prior_profile": "profile-second-value",
    }


def _explicit_widget_previous_occurrence_think_program_v1() -> Dict[str, Any]:
    source = _valid_think_program_v1()

    source["run"]["program"]["widgets"]["approval"]["wires"]["self_previous"] = {
        "from": {
            "widget": "approval",
            "occurrence": "previous",
        },
        "history": "$history.latest.optional",
    }

    source["run"]["program"]["flow"] = [
        source["run"]["program"]["flow"][0],
        source["run"]["program"]["flow"][1],
        source["run"]["program"]["flow"][2],
        source["run"]["program"]["flow"][3],
        source["run"]["program"]["flow"][4],
    ]

    source["run"]["program"]["flow"][3]["overrides"]["wires"]["approval"] = {
        "self_previous": None,
    }
    source["run"]["program"]["flow"][4]["overrides"]["wires"]["approval"] = {
        "self_previous": {
            "from": {
                "widget": "approval",
                "occurrence": "previous",
            },
            "history": "$history.latest.required",
        },
    }

    return source


def test_explicit_widget_previous_occurrence_source_form_lowers_like_self_previous() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(
        _explicit_widget_previous_occurrence_think_program_v1()
    )

    final_step = kernel_program[4]
    final = final_step["datums"][0]

    assert "self_previous" in final["past_wires"]
    alias = final["past_wires"]["self_previous"][0]
    assert final_step["history_queries"][alias]["from_step"] == (
        "onboarding.preapproval"
    )
    assert final_step["history_queries"][alias]["datum_id"] == "approval"
    assert final_step["history_queries"][alias]["required"] is True

    validate_kernel_program_v1(kernel_program)


def test_same_logical_widget_can_recur_across_flow_but_not_twice_in_one_flow_item() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"] = [
        source["run"]["program"]["flow"][3],
        source["run"]["program"]["flow"][4],
    ]

    # This particular cut still fails because approval.review has no prior review;
    # the point is not recurrence rejection. There should be no duplicate-flow-id
    # or repeated-logical-widget failure merely because "approval" appears across
    # different flow items.
    with pytest.raises(ValueError, match="required wire approval.review"):
        lower_think_program_to_kernel_program_v1(source)

    source = _valid_think_program_v1()
    source["run"]["program"]["flow"][0]["widgets"] = ["profile", "profile"]

    with pytest.raises(ValueError, match="may not repeat"):
        lower_think_program_to_kernel_program_v1(source)



# =============================================================================
# E2E integration test
# =============================================================================


def test_thinkruns_e2e_through_highest_language_to_kernel_runtime_behavior() -> None:
    _register_all_thinkprogram_test_integration_v1()

    program = _valid_think_program_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=program,
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_highest_to_kernel_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["profile"]
    assert "value" in str(ctx["datum_widget_decls"]["profile"])

    profile_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_profile.form",
        "profile",
    )
    assert profile_mount_state["mount_seen_initial_micros"] == []
    assert profile_mount_state["mount_seen_user_args"] == {
        "seed": "prod-seed",
        "threshold": 9,
        "labels": ["default", "beta"],
    }
    assert profile_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.collect_profile"
    )
    assert profile_mount_state["mount_seen_kernel"]["form_id"] == (
        "onboarding.collect_profile.form"
    )
    assert profile_mount_state["mount_seen_kernel"]["frame_id"] == "frame"
    assert profile_mount_state["mount_seen_kernel"]["span_id"] == "span"
    
    assert profile_mount_state["mount_seen_kernel"]["system_flags"] == {
        "ui_region": "main",
        "frame_specific": True,
        "logical_widget_id": "profile",
    }
    assert profile_mount_state["mount_seen_kernel"]["authoritative"] is True
    assert profile_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"profile": {"value": "profile-final"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["risk"]

    profile_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_profile.form",
        "profile",
    )
    assert profile_done_state["final_value"] == "profile-final"
    assert profile_done_state["commit"] == {
        "datum_id": "profile",
        "value": "profile-final",
    }
    assert profile_done_state["fill_seen_datum_args_after_reexplode"] == {}

    risk_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_risk.form",
        "risk",
    )
    assert risk_mount_state["mount_seen_initial_micros"] == []
    assert risk_mount_state["mount_seen_user_args"] == {
        "seed": "risk-seed",
        "score_floor": 0.5,
    }
    assert risk_mount_state["mount_seen_kernel"]["step_id"] == "onboarding.collect_risk"

    assert risk_mount_state["mount_seen_kernel"]["system_flags"] == {
        "ui_region": "side",
        "logical_widget_id": "risk",
    }

    ctx = runner.step(fill={"risk": {"value": "risk-final"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["review"]

    review_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_profile.form",
        "review",
    )
    assert review_mount_state["mount_seen_initial_micros"] == []
    assert review_mount_state["mount_seen_user_args"] == {
        "local": "strict-review",
    }
    assert review_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.review_profile"
    )
    assert review_mount_state["mount_seen_kernel"]["system_flags"] == {
        "ui_region": "main",
        "logical_widget_id": "review",
    }
    assert review_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "previous_profile",
        "profile_history",
        "risk_sources",
    ]
    assert review_mount_state["prior_profile_final_value_on_mount"] == "profile-final"
    assert review_mount_state["profile_history_count_on_mount"] >= 1
    assert review_mount_state["risk_sources_count_on_mount"] >= 1
    assert review_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"review": {"confirm": "review-confirmed"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["approval"]

    review_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_profile.form",
        "review",
    )
    assert review_done_state["confirmed"] == "review-confirmed"
    assert review_done_state["commit"] == {
        "datum_id": "review",
        "confirmed": "review-confirmed",
        "prior_profile": "profile-final",
    }

    preapproval_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.preapproval.form",
        "approval",
    )
    assert preapproval_mount_state["mount_seen_initial_micros"] == []
    assert preapproval_mount_state["mount_seen_user_args"] == {
        "mode": "preapproval",
    }
    assert preapproval_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.preapproval"
    )

    assert preapproval_mount_state["mount_seen_kernel"]["authoritative"] is True
    assert preapproval_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "all_sources",
        "review",
    ]
    assert preapproval_mount_state["self_previous_present_on_mount"] is False
    assert preapproval_mount_state["review_confirmed_on_mount"] == "review-confirmed"
    assert preapproval_mount_state["all_sources_count_on_mount"] >= 2

    ctx = runner.step(fill={"approval": {"decision": "preapprove"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["approval"]

    preapproval_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.preapproval.form",
        "approval",
    )
    assert preapproval_done_state["decision"] == "preapprove"
    assert preapproval_done_state["approved_mode"] == "preapproval"
    assert preapproval_done_state["commit"] == {
        "datum_id": "approval",
        "decision": "preapprove",
        "mode": "preapproval",
        "review_confirmed": "review-confirmed",
        "previous_approval_mode": None,
    }

    final_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.final_approval.form",
        "approval",
    )
    assert final_mount_state["mount_seen_initial_micros"] == []
    assert final_mount_state["mount_seen_user_args"] == {
        "mode": "final",
    }
    assert final_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.final_approval"
    )
    assert final_mount_state["mount_seen_kernel"]["authoritative"] is True
    assert final_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "all_sources",
        "review",
        "self_previous",
    ]
    assert final_mount_state["self_previous_present_on_mount"] is True
    assert final_mount_state["previous_approval_mode_on_mount"] == "preapproval"

    ctx = runner.step(fill={"approval": {"decision": "approve-final"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.final_approval.form",
        "approval",
    )
    assert final_done_state["decision"] == "approve-final"
    assert final_done_state["approved_mode"] == "final"
    assert final_done_state["commit"] == {
        "datum_id": "approval",
        "decision": "approve-final",
        "mode": "final",
        "review_confirmed": "review-confirmed",
        "previous_approval_mode": "preapproval",
    }

    state = api._get(sid).state
    writes = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 50,
        },
    )

    assert writes["ok"] is True
    rendered = str(writes)

    assert "onboarding.collect_profile.form" in rendered
    assert "onboarding.collect_risk.form" in rendered
    assert "onboarding.review_profile.form" in rendered
    assert "onboarding.preapproval.form" in rendered
    assert "onboarding.final_approval.form" in rendered

    assert "profile-final" in rendered
    assert "risk-final" in rendered
    assert "review-confirmed" in rendered
    assert "preapproval" in rendered
    assert "approve-final" in rendered




# =============================================================================
# Addendum: multi-widget-frame E2E induction case
# =============================================================================


def _multi_widget_source_frame_think_program_v1() -> Dict[str, Any]:
    source = _valid_think_program_v1()

    collect_sources = {
        "id": "collect_sources",
        "title": "Collect sources together",
        "widgets": ["profile", "risk"],
        "authoritative": [True, True],
        "overrides": {
            "args": {
                "profile": {
                    "threshold": 11,
                },
                "risk": {
                    "score_floor": 0.8,
                },
            },
            "system_flags": {
                "profile": {
                    "frame_specific": "profile-in-shared-frame",
                },
                "risk": {
                    "frame_specific": "risk-in-shared-frame",
                },
            },
        },
    }

    review_profile = copy.deepcopy(source["run"]["program"]["flow"][2])

    preapproval = copy.deepcopy(source["run"]["program"]["flow"][3])

    final_approval = copy.deepcopy(source["run"]["program"]["flow"][4])

    source["run"]["program"]["flow"] = [
        collect_sources,
        review_profile,
        preapproval,
        final_approval,
    ]

    return source


def test_multi_widget_frame_lowers_to_one_step_with_two_datums_and_downstream_wires() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(
        _multi_widget_source_frame_think_program_v1()
    )

    assert [k["step"]["id"] for k in kernel_program] == [
        "onboarding.collect_sources",
        "onboarding.review_profile",
        "onboarding.preapproval",
        "onboarding.final_approval",
    ]

    collect_sources = kernel_program[0]
    assert [d["id"] for d in collect_sources["datums"]] == ["profile", "risk"]
    assert collect_sources["datums"][0]["args"] == {
        "seed": "prod-seed",
        "threshold": 11,
        "labels": ["default", "beta"],
    }
    assert collect_sources["datums"][1]["args"] == {
        "seed": "risk-seed",
        "score_floor": 0.8,
    }

    review_step = kernel_program[1]
    review = review_step["datums"][0]

    assert sorted(review["past_wires"]) == [
        "previous_profile",
        "profile_history",
        "risk_sources",
    ]

    rendered_review_queries = str(review_step["history_queries"])
    assert "onboarding.collect_sources" in rendered_review_queries
    assert "profile" in rendered_review_queries
    assert "risk" in rendered_review_queries

    preapproval_step = kernel_program[2]
    preapproval = preapproval_step["datums"][0]
    assert sorted(preapproval["past_wires"]) == [
        "all_sources",
        "review",
    ]

    rendered_preapproval_queries = str(preapproval_step["history_queries"])
    assert "onboarding.collect_sources" in rendered_preapproval_queries
    assert "onboarding.review_profile" in rendered_preapproval_queries

    final_step = kernel_program[3]
    final = final_step["datums"][0]
    assert sorted(final["past_wires"]) == [
        "all_sources",
        "review",
        "self_previous",
    ]

    self_alias = final["past_wires"]["self_previous"][0]
    assert final_step["history_queries"][self_alias]["from_step"] == (
        "onboarding.preapproval"
    )

    validate_kernel_program_v1(kernel_program)


def test_multi_widget_frame_runs_e2e_from_top_json_to_runtime_witnesses() -> None:
    _register_all_thinkprogram_test_integration_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=_multi_widget_source_frame_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "thinkprogram_multi_widget_frame_highest_to_kernel_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["profile", "risk"]
    assert "value" in str(ctx["datum_widget_decls"]["profile"])
    assert "value" in str(ctx["datum_widget_decls"]["risk"])

    profile_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_sources.form",
        "profile",
    )
    risk_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_sources.form",
        "risk",
    )

    assert profile_mount_state["mount_seen_initial_micros"] == []
    assert risk_mount_state["mount_seen_initial_micros"] == []

    assert profile_mount_state["mount_seen_user_args"] == {
        "seed": "prod-seed",
        "threshold": 11,
        "labels": ["default", "beta"],
    }
    assert risk_mount_state["mount_seen_user_args"] == {
        "seed": "risk-seed",
        "score_floor": 0.8,
    }

    assert profile_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.collect_sources"
    )
    assert risk_mount_state["mount_seen_kernel"]["step_id"] == (
        "onboarding.collect_sources"
    )

    assert profile_mount_state["mount_seen_kernel"]["system_flags"] == {
        "ui_region": "main",
        "frame_specific": "profile-in-shared-frame",
        "logical_widget_id": "profile",
    }
    assert risk_mount_state["mount_seen_kernel"]["system_flags"] == {
        "ui_region": "side",
        "frame_specific": "risk-in-shared-frame",
        "logical_widget_id": "risk",
    }

    assert profile_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(
        fill={
            "profile": {
                "value": "profile-from-shared-frame",
            },
            "risk": {
                "value": "risk-from-shared-frame",
            },
        }
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "span"
    assert ctx["datum_widgets_on_this_span"] == ["review"]

    profile_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_sources.form",
        "profile",
    )
    risk_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_sources.form",
        "risk",
    )

    assert profile_done_state["final_value"] == "profile-from-shared-frame"
    assert risk_done_state["final_value"] == "risk-from-shared-frame"
    assert profile_done_state["fill_seen_datum_args_after_reexplode"] == {}
    assert risk_done_state["fill_seen_datum_args_after_reexplode"] == {}

    review_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_profile.form",
        "review",
    )

    assert review_mount_state["mount_seen_initial_micros"] == []
    assert review_mount_state["mount_seen_user_args"] == {
        "local": "strict-review",
    }
    assert review_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "previous_profile",
        "profile_history",
        "risk_sources",
    ]
    assert review_mount_state["prior_profile_final_value_on_mount"] == (
        "profile-from-shared-frame"
    )
    assert review_mount_state["profile_history_count_on_mount"] >= 1
    assert review_mount_state["risk_sources_count_on_mount"] >= 1

    ctx = runner.step(fill={"review": {"confirm": "review-from-shared-frame"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widgets_on_this_span"] == ["approval"]

    review_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.review_profile.form",
        "review",
    )
    assert review_done_state["confirmed"] == "review-from-shared-frame"
    assert review_done_state["commit"] == {
        "datum_id": "review",
        "confirmed": "review-from-shared-frame",
        "prior_profile": "profile-from-shared-frame",
    }

    preapproval_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.preapproval.form",
        "approval",
    )

    assert preapproval_mount_state["mount_seen_user_args"] == {
        "mode": "preapproval",
    }
    assert preapproval_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "all_sources",
        "review",
    ]
    assert preapproval_mount_state["self_previous_present_on_mount"] is False
    assert preapproval_mount_state["review_confirmed_on_mount"] == (
        "review-from-shared-frame"
    )
    assert preapproval_mount_state["all_sources_count_on_mount"] >= 2

    ctx = runner.step(fill={"approval": {"decision": "preapprove-shared"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widgets_on_this_span"] == ["approval"]

    preapproval_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.preapproval.form",
        "approval",
    )
    assert preapproval_done_state["approved_mode"] == "preapproval"
    assert preapproval_done_state["commit"] == {
        "datum_id": "approval",
        "decision": "preapprove-shared",
        "mode": "preapproval",
        "review_confirmed": "review-from-shared-frame",
        "previous_approval_mode": None,
    }

    final_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.final_approval.form",
        "approval",
    )

    assert final_mount_state["mount_seen_user_args"] == {
        "mode": "final",
    }
    assert final_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "all_sources",
        "review",
        "self_previous",
    ]
    assert final_mount_state["self_previous_present_on_mount"] is True
    assert final_mount_state["previous_approval_mode_on_mount"] == "preapproval"

    ctx = runner.step(fill={"approval": {"decision": "approve-shared-final"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.final_approval.form",
        "approval",
    )
    assert final_done_state["approved_mode"] == "final"
    assert final_done_state["commit"] == {
        "datum_id": "approval",
        "decision": "approve-shared-final",
        "mode": "final",
        "review_confirmed": "review-from-shared-frame",
        "previous_approval_mode": "preapproval",
    }

    state = api._get(sid).state
    writes = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 50,
        },
    )

    assert writes["ok"] is True
    rendered = str(writes)

    assert "onboarding.collect_sources.form" in rendered
    assert "onboarding.review_profile.form" in rendered
    assert "onboarding.preapproval.form" in rendered
    assert "onboarding.final_approval.form" in rendered

    assert "profile-from-shared-frame" in rendered
    assert "risk-from-shared-frame" in rendered
    assert "review-from-shared-frame" in rendered
    assert "preapprove-shared" in rendered
    assert "approve-shared-final" in rendered



def test_reexplode_preserves_pre_mount_role_metadata_but_not_author_args_e2e() -> None:
    """
    Regression guard for the role-modulation seam.

    ThinkProgramTM assigns roles before mount, when it lowers logical widgets
    into kernel datums. Class-widget mount reexplosion may replace the visual
    shell, but it must not erase controller-owned role metadata. Otherwise the
    role mismatch controller later sees an unguarded datum or incorrectly falls
    back to the span role.
    """
    _register_all_thinkprogram_test_integration_v1()

    api = _api()
    created = api.create_VM_session_from_program(
        program=_role_modulation_demo_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "roles": {
                "maker": {"label": "Maker"},
                "reviewer": {"label": "Reviewer"},
            },
            "role_mismatch_policy": {
                "default": "redacted",
            },
            "test": "thinkprogram_reexplode_preserves_roles",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    datums = {
        datum["id"]: datum
        for datum in ctx["multiframespec"]["datums"]
    }

    assert datums["profile"]["roles"] == ["maker"]
    assert datums["risk"].get("roles", []) == []

    # Existing contract remains: reexplode does not preserve pre-mount args into
    # the fill shell seen by _on_fill.
    ctx = runner.step(
        fill={
            "profile": {"value": "maker-profile"},
            "risk": {"value": "reviewer-risk"},
        }
    )
    assert ctx["kind"] == "ATCOMPLETION"

    profile_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_role_partitioned_sources.form",
        "profile",
    )
    risk_done_state = _latest_lifecycle_state(
        api,
        sid,
        "onboarding.collect_role_partitioned_sources.form",
        "risk",
    )

    assert profile_done_state["fill_seen_datum_args_after_reexplode"] == {}
    assert risk_done_state["fill_seen_datum_args_after_reexplode"] == {}


# =============================================================================
# Addendum: ThinkProgramTM roles -> kernel datums -> controller role modulation
# =============================================================================


def _role_modulation_demo_think_program_v1() -> Dict[str, Any]:
    """
    Highest-surface role demo.

    This authors roles only at the ThinkProgramTM ergonomic layer:

      - profile has widget-level datum role ["maker"]
      - risk has no datum role, so it inherits the flow/span role ["reviewer"]

    The role formalism is datum-first:

      - datum.roles wins when present
      - otherwise span.roles is the default role assignment

    Therefore:

      - maker sees/fills profile and sees risk redacted
      - reviewer sees/fills risk and sees profile redacted
    """
    source = _valid_think_program_v1()

    source["run"]["program"]["widgets"]["profile"]["title"] = "Maker-only Profile"
    source["run"]["program"]["widgets"]["profile"]["roles"] = ["maker"]

    source["run"]["program"]["widgets"]["risk"]["title"] = (
        "Reviewer span-default Risk"
    )
    source["run"]["program"]["widgets"]["risk"].pop("roles", None)

    source["run"]["program"]["flow"] = [
        {
            "id": "collect_role_partitioned_sources",
            "title": "Collect role-partitioned sources",
            "widgets": ["profile", "risk"],
            "roles": ["reviewer"],
            "authoritative": [True, True],
            "overrides": {
                "args": {
                    "profile": {
                        "threshold": 11,
                    },
                    "risk": {
                        "score_floor": 0.8,
                    },
                },
            },
        }
    ]

    return source


def test_thinkprogram_roles_lower_from_highest_json_to_kernel_datum_and_span_roles() -> None:
    _register_all_thinkprogram_test_integration_v1()

    kernel_program = lower_think_program_to_kernel_program_v1(
        _role_modulation_demo_think_program_v1()
    )

    assert len(kernel_program) == 1

    step = kernel_program[0]
    assert step["step"]["id"] == "onboarding.collect_role_partitioned_sources"

    span = step["span"]
    datums = {
        datum["id"]: datum
        for datum in step["datums"]
    }

    assert span["roles"] == ["reviewer"]

    # Datum-level role assignment: authored on run.program.widgets.profile.roles.
    assert datums["profile"]["roles"] == ["maker"]

    # No datum-level role assignment: risk inherits span.roles at runtime.
    assert datums["risk"]["roles"] == []

    validate_kernel_program_v1(kernel_program)


def test_thinkprogram_role_overrides_replace_widget_roles_before_kernel_lowering() -> None:
    _register_all_thinkprogram_test_integration_v1()

    source = _role_modulation_demo_think_program_v1()
    source["run"]["program"]["widgets"]["profile"]["roles"] = ["draft_author"]
    source["run"]["program"]["flow"][0]["overrides"] = dict(
        source["run"]["program"]["flow"][0].get("overrides") or {}
    )
    source["run"]["program"]["flow"][0]["overrides"]["roles"] = {
        "profile": ["maker"],
        "risk": ["reviewer"],
    }

    kernel_program = lower_think_program_to_kernel_program_v1(source)
    datums = {
        datum["id"]: datum
        for datum in kernel_program[0]["datums"]
    }

    assert datums["profile"]["roles"] == ["maker"]
    assert datums["risk"]["roles"] == ["reviewer"]

    validate_kernel_program_v1(kernel_program)


def test_highest_service_facade_modulates_rendered_ctx_from_thinkprogram_roles_e2e() -> None:
    _register_all_thinkprogram_test_integration_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        UserAction,
        create_core_session_from_program,
        dispatch_live_session_action,
        render_current_session_state,
    )

    created = create_core_session_from_program(
        program=_role_modulation_demo_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "roles": {
                "maker": {"label": "Maker"},
                "reviewer": {"label": "Reviewer"},
            },
            "role_mismatch_policy": {
                "default": "redacted",
                "role_modes": {
                    "maker": "redacted",
                    "reviewer": "redacted",
                },
            },
            "test": "thinkprogram_roles_service_facade_modulated_render_e2e",
        },
    )

    assert created["ok"] is True
    sid = str(created["session_id"])

    transition = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="maker",
    )

    assert isinstance(transition, dict)
    assert "ctx" not in transition

    maker_render = render_current_session_state(
        session_id=sid,
        role="maker",
        include_ctx=True,
    )
    reviewer_render = render_current_session_state(
        session_id=sid,
        role="reviewer",
        include_ctx=True,
    )

    maker_ctx = maker_render["ctx"]
    reviewer_ctx = reviewer_render["ctx"]

    assert maker_ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert reviewer_ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    maker_datums = {
        datum["id"]: datum
        for datum in maker_ctx["multiframespec"]["datums"]
    }
    reviewer_datums = {
        datum["id"]: datum
        for datum in reviewer_ctx["multiframespec"]["datums"]
    }

    # Regression guard: mount reexplosion must not erase role metadata assigned
    # before mount by ThinkProgramTM/kernel lowering.
    assert maker_datums["profile"]["roles"] == ["maker"]
    assert reviewer_datums["risk"].get("roles", []) == []

    # Maker gets the datum with explicit datum.roles=["maker"].
    # Risk has no datum roles, so it inherits span.roles=["reviewer"] and is
    # redacted from maker's editable membership vectors.
    assert maker_ctx["datum_widgets_on_this_span"] == ["profile"]
    assert maker_ctx["role_mismatch_modulation_info"]["role_viewing"] == "maker"
    assert maker_ctx["role_mismatch_modulation_info"]["mismatch_datum_ids"] == [
        "risk"
    ]

    maker_assignments = {
        row["datum_id"]: row
        for row in maker_ctx["role_mismatch_modulation_info"]["assignments"]
    }
    assert maker_assignments["profile"]["roles"] == ["maker"]
    assert maker_assignments["profile"]["role_source"] == "datum"
    assert maker_assignments["risk"]["roles"] == ["reviewer"]
    assert maker_assignments["risk"]["role_source"] == "span"

    # Reviewer gets risk via the flow/span role default and sees profile
    # redacted.
    assert reviewer_ctx["datum_widgets_on_this_span"] == ["risk"]
    assert reviewer_ctx["role_mismatch_modulation_info"]["role_viewing"] == "reviewer"
    assert reviewer_ctx["role_mismatch_modulation_info"]["mismatch_datum_ids"] == [
        "profile"
    ]

    reviewer_assignments = {
        row["datum_id"]: row
        for row in reviewer_ctx["role_mismatch_modulation_info"]["assignments"]
    }
    assert reviewer_assignments["profile"]["roles"] == ["maker"]
    assert reviewer_assignments["profile"]["role_source"] == "datum"
    assert reviewer_assignments["risk"]["roles"] == ["reviewer"]
    assert reviewer_assignments["risk"]["role_source"] == "span"

    rendered_for_maker = json.dumps(maker_ctx, sort_keys=True)
    rendered_for_reviewer = json.dumps(reviewer_ctx, sort_keys=True)

    assert "Maker-only Profile" in rendered_for_maker
    assert "Reviewer span-default Risk" not in rendered_for_maker

    assert "Reviewer span-default Risk" in rendered_for_reviewer
    assert "Maker-only Profile" not in rendered_for_reviewer


def test_highest_service_facade_blocks_mismatched_submission_from_thinkprogram_roles_e2e() -> None:
    _register_all_thinkprogram_test_integration_v1()

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        UserAction,
        create_core_session_from_program,
        dispatch_live_session_action,
    )

    created = create_core_session_from_program(
        program=_role_modulation_demo_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "roles": {
                "maker": {"label": "Maker"},
                "reviewer": {"label": "Reviewer"},
            },
            "role_mismatch_policy": {
                "default": "redacted",
            },
            "test": "thinkprogram_roles_service_facade_submission_guard_e2e",
        },
    )

    assert created["ok"] is True
    sid = str(created["session_id"])

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="reviewer",
    )

    with pytest.raises(PermissionError, match="profile"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            user_fill={
                "profile": {
                    "value": "reviewer-must-not-write-maker-profile",
                }
            },
            role="reviewer",
        )

    allowed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        user_fill={
            "risk": {
                "value": "reviewer-risk-ok",
            }
        },
        role="reviewer",
    )

    assert isinstance(allowed, dict)