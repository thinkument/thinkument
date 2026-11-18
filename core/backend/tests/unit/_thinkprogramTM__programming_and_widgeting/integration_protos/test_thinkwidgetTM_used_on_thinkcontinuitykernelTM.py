from __future__ import annotations

"""
Pulled class-widget / kernel integration tests.

This sheet proves the split-project static contract layer:

    thinkwidgetTM
        @thinkwidgetTM_config(..., args=..., wires=...)
        class Widget(DatumLifecycleWidget): ...

    thinkcontinuitykernelTM
        pull_thinkwidget_class_into_kernel_v1(Widget)
        -> reads static argspace/wire-space from class-widget metadata
        -> normalizes through the existing kernel grammar
        -> validates kernel program use-sites statically
        -> lowers to ordinary think.kernel.v1 rows
        -> runtime calls the unchanged base datum widget fn(q)

The kernel integration does not add q-root keys. Kernel data is delivered only at:

    q["datum"]["args"]["__kernel"]
"""

from typing import Any, Dict, Mapping

import pytest

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

from _thinkprogram._thinkcontinuitykernelTM.api import (
    LANG_THINKING_FLOW_EXPLICIT_V1,
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
    validate_kernel_program_v1,
)

from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    infer_thinkwidget_kernel_contract_spec_v1,
    kernel_widget_class_repr_v1,
    pull_thinkwidget_class_into_kernel_v1,
)


# =============================================================================
# Helpers
# =============================================================================


def _api():
    return get_concrete_session_api(enable_persistence=False)


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


# =============================================================================
# Pulled class widgets with decorator-owned kernel contracts
# =============================================================================


PULLED_KERNEL_CLASS_SOURCE_WIDGET = "test.adapter.kernel_pulled_class_source.static"
PULLED_KERNEL_CLASS_CONSUMER_WIDGET = "test.adapter.kernel_pulled_class_consumer.static"


@thinkwidgetTM_config(
    PULLED_KERNEL_CLASS_SOURCE_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "seed": {"type": "str", "required": True},
        "threshold": {"type": "int", "required": False, "default": 7},
        "labels": {"type": "list[str]", "required": False, "default": ["default"]},
    },
    wires={},
)
class PulledKernelClassSourceWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})

        self.mount_seen_user_args = {
            key: value
            for key, value in datum_args.items()
            if key != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "form_id": dict(kernel_args.get("form") or {}).get("id"),
            "frame_id": dict(kernel_args.get("frame") or {}).get("id"),
            "span_id": dict(kernel_args.get("span") or {}).get("id"),
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
        lifecycle["widget"] = PULLED_KERNEL_CLASS_SOURCE_WIDGET

        self.message("info", "source mounted with kernel args")

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Pulled source continuation without args",
                "micros": [_text_micro("value")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"value": ""},
            prefill_hints={"value": "alpha"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])

        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.fill_used_stowed_step_id = self.mount_seen_kernel["step_id"]
        self.final_value = dict(fill_data["current_fills"]).get("value")
        self.commit = {
            "datum_id": position["datum_id"],
            "value": self.final_value,
        }

        self.message("success", "source done from class widget")
        return True


@thinkwidgetTM_config(
    PULLED_KERNEL_CLASS_CONSUMER_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={
        "local": {"type": "str", "required": True},
    },
    wires={
        "previous_source": {
            "multiplicity": "one",
            "required": True,
        },
        "sources": {
            "multiplicity": "many",
            "required": False,
        },
    },
)
class PulledKernelClassConsumerWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})

        prior = dict(past_wires.get("previous_source") or {})
        prior_value = dict(prior.get("value") or {})
        prior_state = dict(prior_value.get("state") or {})

        self.mount_seen_user_args = {
            key: value
            for key, value in datum_args.items()
            if key != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel_args.get("step") or {}).get("id"),
            "form_id": dict(kernel_args.get("form") or {}).get("id"),
            "frame_id": dict(kernel_args.get("frame") or {}).get("id"),
            "span_id": dict(kernel_args.get("span") or {}).get("id"),
            "past_wire_keys": sorted(str(key) for key in past_wires.keys()),
        }
        self.prior_row_on_mount = prior
        self.prior_final_value_on_mount = prior_state.get("final_value")
        self.prior_commit_on_mount = prior_state.get("commit")
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
        lifecycle["widget"] = PULLED_KERNEL_CLASS_CONSUMER_WIDGET

        self.message("info", "consumer mounted with kernel past wire")

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Pulled consumer continuation without args",
                "micros": [_text_micro("confirm")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"confirm": ""},
            prefill_hints={"confirm": "yes"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])

        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.confirmed = dict(fill_data["current_fills"]).get("confirm")
        self.fill_used_stowed_kernel_step_id = self.mount_seen_kernel["step_id"]
        self.fill_used_stowed_prior_final_value = self.prior_final_value_on_mount
        self.forever_visible_kernel_snapshot = {
            "consumer_step_id": self.mount_seen_kernel["step_id"],
            "consumer_form_id": self.mount_seen_kernel["form_id"],
            "prior_final_value": self.prior_final_value_on_mount,
            "prior_commit": self.prior_commit_on_mount,
        }

        self.message("success", "consumer done from class widget")
        return True


# =============================================================================
# Program fixture
# =============================================================================


def _register_pulled_class_widgets_as_kernel_widgets_v1() -> None:
    source_receipt = pull_thinkwidget_class_into_kernel_v1(
        PulledKernelClassSourceWidget,
        overwrite=True,
    )
    assert source_receipt["ok"] is True
    assert source_receipt["kernel_contract"]["args"]["seed"]["type"] == "str"
    assert source_receipt["kernel_contract"]["args"]["threshold"]["default"] == 7
    assert source_receipt["kernel_contract"]["args"]["labels"]["default"] == ["default"]
    assert source_receipt["kernel_contract"]["past_wires"] == {}
    assert source_receipt["class_repr"]["is_class_authored"] is True
    assert (
        source_receipt["class_repr"]["class"]["qualname"]
        == "PulledKernelClassSourceWidget"
    )

    consumer_receipt = pull_thinkwidget_class_into_kernel_v1(
        PulledKernelClassConsumerWidget,
        overwrite=True,
    )
    assert consumer_receipt["ok"] is True
    assert consumer_receipt["kernel_contract"]["args"]["local"]["type"] == "str"
    assert consumer_receipt["kernel_contract"]["past_wires"]["previous_source"] == {
        "multiplicity": "one",
        "required": True,
    }
    assert consumer_receipt["kernel_contract"]["past_wires"]["sources"] == {
        "multiplicity": "many",
        "required": False,
    }
    assert consumer_receipt["class_repr"]["is_class_authored"] is True
    assert (
        consumer_receipt["class_repr"]["class"]["qualname"]
        == "PulledKernelClassConsumerWidget"
    )


def _pulled_kernel_class_program_v1() -> list[Dict[str, Any]]:
    return [
        {
            "kind": "think_kernel_step_v1",
            "kernel_args_surface_version": "v1",
            "step": {
                "id": "kernel.pulled_class.K1",
                "title": "Pulled Class K1",
            },
            "form": {
                "id": "kernel.pulled_class.K1.form",
                "title": "Pulled Class K1 Form",
            },
            "frame": {
                "id": "F",
                "title": "Frame",
            },
            "span": {
                "id": "S",
                "title": "Span",
            },
            "history_queries": {},
            "datums": [
                {
                    "id": "A",
                    "widget": PULLED_KERNEL_CLASS_SOURCE_WIDGET,
                    "title": "A source",
                    "micros": [_text_micro("value")],
                    "lifecycle": {
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 0,
                        "max_messages": 8,
                    },
                    "past_wires": {},
                    "args": {
                        "seed": "alpha-seed",
                    },
                }
            ],
            "kernel_flags": {
                "copy_form_frame_span_args_into_each_datum": True,
                "mount_explode_default": True,
            },
        },
        {
            "kind": "think_kernel_step_v1",
            "kernel_args_surface_version": "v1",
            "step": {
                "id": "kernel.pulled_class.K2",
                "title": "Pulled Class K2",
            },
            "form": {
                "id": "kernel.pulled_class.K2.form",
                "title": "Pulled Class K2 Form",
            },
            "frame": {
                "id": "F",
                "title": "Frame",
            },
            "span": {
                "id": "S",
                "title": "Span",
            },
            "history_queries": {
                "prior_A": {
                    "from_step": "kernel.pulled_class.K1",
                    "datum_id": "A",
                    "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                    "include_value": True,
                    "required": True,
                    "select": "latest",
                    "max_results": 20,
                }
            },
            "datums": [
                {
                    "id": "B",
                    "widget": PULLED_KERNEL_CLASS_CONSUMER_WIDGET,
                    "title": "B consumer",
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 0,
                        "max_messages": 8,
                    },
                    "past_wires": {
                        "previous_source": ["prior_A"],
                    },
                    "args": {
                        "local": "consumer-local",
                    },
                }
            ],
            "kernel_flags": {
                "copy_form_frame_span_args_into_each_datum": True,
                "mount_explode_default": True,
            },
        },
    ]


# =============================================================================
# Static contract tests
# =============================================================================


def test_pull_infers_kernel_contract_from_thinkwidget_decorator_config() -> None:
    inferred_source = infer_thinkwidget_kernel_contract_spec_v1(
        PulledKernelClassSourceWidget
    )

    assert inferred_source["args"] == {
        "seed": {"type": "str", "required": True},
        "threshold": {"type": "int", "required": False, "default": 7},
        "labels": {
            "type": "list[str]",
            "required": False,
            "default": ["default"],
        },
    }
    assert inferred_source["past_wires"] == {}
    assert inferred_source["enforce_no_premount_shell"] is False

    inferred_consumer = infer_thinkwidget_kernel_contract_spec_v1(
        PulledKernelClassConsumerWidget
    )

    assert inferred_consumer["args"] == {
        "local": {"type": "str", "required": True},
    }
    assert inferred_consumer["past_wires"] == {
        "previous_source": {
            "multiplicity": "one",
            "required": True,
        },
        "sources": {
            "multiplicity": "many",
            "required": False,
        },
    }
    assert inferred_consumer["enforce_no_premount_shell"] is False


def test_pulled_class_widgets_register_kernel_contract_without_reregistering_runtime_fn() -> None:
    _register_pulled_class_widgets_as_kernel_widgets_v1()

    source_repr = kernel_widget_class_repr_v1(PULLED_KERNEL_CLASS_SOURCE_WIDGET)
    consumer_repr = kernel_widget_class_repr_v1(PULLED_KERNEL_CLASS_CONSUMER_WIDGET)

    assert source_repr["widget_name"] == PULLED_KERNEL_CLASS_SOURCE_WIDGET
    assert source_repr["is_class_authored"] is True
    assert source_repr["class"]["qualname"] == "PulledKernelClassSourceWidget"
    assert source_repr["runtime_contract"] == (
        "ordinary DatumWidgetFnV1 called with ordinary q packet"
    )
    assert source_repr["inferred_kernel_contract_spec"]["args"]["seed"]["type"] == "str"

    assert consumer_repr["widget_name"] == PULLED_KERNEL_CLASS_CONSUMER_WIDGET
    assert consumer_repr["is_class_authored"] is True
    assert consumer_repr["class"]["qualname"] == "PulledKernelClassConsumerWidget"
    assert consumer_repr["kernel_runtime_seam"] == (
        "q['datum']['args'] and q['datum']['args']['__kernel']"
    )
    assert (
        consumer_repr["inferred_kernel_contract_spec"]["past_wires"]["previous_source"][
            "multiplicity"
        ]
        == "one"
    )

    validate_kernel_program_v1(_pulled_kernel_class_program_v1())


def test_pulled_class_widget_static_argspace_is_enforced_by_kernel_program_validator() -> None:
    _register_pulled_class_widgets_as_kernel_widgets_v1()

    validate_kernel_program_v1(_pulled_kernel_class_program_v1())

    unknown_arg = _pulled_kernel_class_program_v1()
    unknown_arg[0]["datums"][0]["args"] = {
        "seed": "alpha-seed",
        "extra": "not allowed",
    }
    with pytest.raises(ValueError, match="unknown args"):
        validate_kernel_program_v1(unknown_arg)

    missing_required = _pulled_kernel_class_program_v1()
    missing_required[0]["datums"][0]["args"] = {}
    with pytest.raises(ValueError, match="missing required arg"):
        validate_kernel_program_v1(missing_required)

    wrong_type = _pulled_kernel_class_program_v1()
    wrong_type[0]["datums"][0]["args"] = {
        "seed": 123,
    }
    with pytest.raises(ValueError, match="must be str"):
        validate_kernel_program_v1(wrong_type)

    bad_default_type_is_caught_at_pull_time_widget = (
        "test.adapter.kernel_pulled_class_bad_default"
    )

    @thinkwidgetTM_config(
        bad_default_type_is_caught_at_pull_time_widget,
        overwrite=True,
        args={
            "count": {
                "type": "int",
                "required": False,
                "default": "not-an-int",
            },
        },
        wires={},
    )
    class BadDefaultWidget(DatumLifecycleWidget):
        def _on_mount(self, position, fill_data, limits, stats):
            return True

        def _on_fill(self, signal, position, fill_data, limits, stats):
            return True

    with pytest.raises(ValueError, match="default for arg 'count' must be int"):
        pull_thinkwidget_class_into_kernel_v1(BadDefaultWidget, overwrite=True)


def test_pulled_class_widget_static_wirespace_is_enforced_by_kernel_program_validator() -> None:
    _register_pulled_class_widgets_as_kernel_widgets_v1()

    validate_kernel_program_v1(_pulled_kernel_class_program_v1())

    unknown_wire = _pulled_kernel_class_program_v1()
    unknown_wire[1]["datums"][0]["past_wires"] = {
        "not_declared": ["prior_A"],
    }
    with pytest.raises(ValueError, match="unknown wires"):
        validate_kernel_program_v1(unknown_wire)

    missing_required_wire = _pulled_kernel_class_program_v1()
    missing_required_wire[1]["datums"][0]["past_wires"] = {}
    with pytest.raises(ValueError, match="missing required wire"):
        validate_kernel_program_v1(missing_required_wire)

    too_many_for_one = _pulled_kernel_class_program_v1()
    too_many_for_one[1]["history_queries"]["prior_A_copy"] = dict(
        too_many_for_one[1]["history_queries"]["prior_A"]
    )
    too_many_for_one[1]["datums"][0]["past_wires"] = {
        "previous_source": ["prior_A", "prior_A_copy"],
    }
    with pytest.raises(ValueError, match="requires exactly one alias"):
        validate_kernel_program_v1(too_many_for_one)

    unknown_alias = _pulled_kernel_class_program_v1()
    unknown_alias[1]["datums"][0]["past_wires"] = {
        "previous_source": ["missing_alias"],
    }
    with pytest.raises(ValueError, match="unknown history queries"):
        validate_kernel_program_v1(unknown_alias)


def test_explicit_pull_contract_can_override_decorator_contract() -> None:
    receipt = pull_thinkwidget_class_into_kernel_v1(
        PulledKernelClassSourceWidget,
        args={
            "seed": {"type": "str", "required": True},
            "mode": {"type": "str", "required": False, "default": "explicit"},
        },
        wires={},
        overwrite=True,
    )

    assert receipt["kernel_contract"]["args"]["mode"] == {
        "type": "str",
        "required": False,
        "default": "explicit",
    }

    k = _pulled_kernel_class_program_v1()[0]
    k["datums"][0]["args"] = {
        "seed": "alpha",
        "mode": "explicit",
    }

    validate_kernel_program_v1([k])




# =============================================================================
# E2E integration test
# =============================================================================


def test_pulled_class_widgets_run_under_kernel_and_see_kernel_args_wires_then_state_forever() -> None:
    _register_pulled_class_widgets_as_kernel_widgets_v1()
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    program = validate_kernel_program_v1(_pulled_kernel_class_program_v1())

    api = _api()
    created = api.create_VM_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "pulled_class_widgets_kernel_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["datum_widgets_on_this_span"] == ["A"]

    source_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.pulled_class.K1.form",
        "A",
    )

    assert source_mount_state["mount_seen_user_args"] == {
        "seed": "alpha-seed",
        "threshold": 7,
        "labels": ["default"],
    }
    assert source_mount_state["mount_seen_kernel"]["step_id"] == "kernel.pulled_class.K1"
    assert (
        source_mount_state["mount_seen_kernel"]["form_id"]
        == "kernel.pulled_class.K1.form"
    )

    assert source_mount_state["mount_seen_kernel"]["past_wires"] == {}
    assert source_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"A": {"value": "alpha-final-from-class"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["datum_widgets_on_this_span"] == ["B"]

    source_done_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.pulled_class.K1.form",
        "A",
    )

    assert source_done_state["final_value"] == "alpha-final-from-class"
    assert source_done_state["commit"] == {
        "datum_id": "A",
        "value": "alpha-final-from-class",
    }
    assert source_done_state["fill_seen_datum_args_after_reexplode"] == {}
    assert source_done_state["fill_used_stowed_step_id"] == "kernel.pulled_class.K1"

    consumer_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.pulled_class.K2.form",
        "B",
    )

    assert consumer_mount_state["mount_seen_user_args"] == {
        "local": "consumer-local",
    }
    assert (
        consumer_mount_state["mount_seen_kernel"]["step_id"]
        == "kernel.pulled_class.K2"
    )
    assert (
        consumer_mount_state["mount_seen_kernel"]["form_id"]
        == "kernel.pulled_class.K2.form"
    )
    assert consumer_mount_state["mount_seen_kernel"]["past_wire_keys"] == [
        "previous_source",
    ]
    assert consumer_mount_state["prior_final_value_on_mount"] == (
        "alpha-final-from-class"
    )
    assert consumer_mount_state["prior_commit_on_mount"] == {
        "datum_id": "A",
        "value": "alpha-final-from-class",
    }
    assert consumer_mount_state["prior_row_on_mount"]["public_step_name"] == (
        "kernel.pulled_class.K1"
    )
    assert (
        consumer_mount_state["prior_row_on_mount"]["write_kind"]
        == WRITE_KIND_DATUM_LIFECYCLE
    )
    assert consumer_mount_state["prior_row_on_mount"]["key"] == "A"
    assert consumer_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"B": {"confirm": "consumer-confirmed"}})
    assert ctx["kind"] == "ATCOMPLETION"

    consumer_done_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.pulled_class.K2.form",
        "B",
    )

    assert consumer_done_state["confirmed"] == "consumer-confirmed"
    assert consumer_done_state["fill_seen_datum_args_after_reexplode"] == {}
    assert (
        consumer_done_state["fill_used_stowed_kernel_step_id"]
        == "kernel.pulled_class.K2"
    )
    assert consumer_done_state["fill_used_stowed_prior_final_value"] == (
        "alpha-final-from-class"
    )
    assert consumer_done_state["forever_visible_kernel_snapshot"] == {
        "consumer_step_id": "kernel.pulled_class.K2",
        "consumer_form_id": "kernel.pulled_class.K2.form",
        "prior_final_value": "alpha-final-from-class",
        "prior_commit": {
            "datum_id": "A",
            "value": "alpha-final-from-class",
        },
    }

    state = api._get(sid).state
    writes = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "include_values": True,
            "max_results": 20,
        },
    )

    assert writes["ok"] is True
    rendered = str(writes)

    assert "kernel.pulled_class.K1.form" in rendered
    assert "kernel.pulled_class.K2.form" in rendered
    assert "alpha-final-from-class" in rendered
    assert "consumer-confirmed" in rendered
    assert "forever_visible_kernel_snapshot" in rendered




# ---------------------------------------------------------------------------
# Addendum: kernel-integrated empty premount shell law
# ---------------------------------------------------------------------------


EMPTY_PREMOUNT_KERNEL_SOURCE_WIDGET = (
    "test.adapter.kernel_empty_premount_source.static"
)
EMPTY_PREMOUNT_KERNEL_CONSUMER_WIDGET = (
    "test.adapter.kernel_empty_premount_consumer.static"
)


@thinkwidgetTM_config(
    EMPTY_PREMOUNT_KERNEL_SOURCE_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "seed": {"type": "str", "required": True},
    },
    wires={},
)
class EmptyPremountKernelSourceWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            key: value
            for key, value in datum_args.items()
            if key != "__kernel"
        }
        self.mount_seen_kernel_step_id = dict(kernel_args.get("step") or {}).get("id")
        self.mount_seen_kernel_form_id = dict(kernel_args.get("form") or {}).get("id")
        self.mount_seen_past_wires = dict(kernel_args.get("past_wires") or {})
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
        lifecycle["widget"] = EMPTY_PREMOUNT_KERNEL_SOURCE_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Kernel source shell generated by mount",
                "micros": [_text_micro("value")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"value": ""},
            prefill_hints={"value": "source-created-by-mount"},
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
    EMPTY_PREMOUNT_KERNEL_CONSUMER_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    enforce_no_premount_shell=True,
    args={
        "local": {"type": "str", "required": True},
    },
    wires={
        "previous_source": {
            "multiplicity": "one",
            "required": True,
        },
    },
)
class EmptyPremountKernelConsumerWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel_args = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel_args.get("past_wires") or {})

        prior = dict(past_wires.get("previous_source") or {})
        prior_value = dict(prior.get("value") or {})
        prior_state = dict(prior_value.get("state") or {})

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            key: value
            for key, value in datum_args.items()
            if key != "__kernel"
        }
        self.mount_seen_kernel_step_id = dict(kernel_args.get("step") or {}).get("id")
        self.mount_seen_kernel_form_id = dict(kernel_args.get("form") or {}).get("id")
        self.prior_final_value_on_mount = prior_state.get("final_value")
        self.prior_commit_on_mount = prior_state.get("commit")
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
        lifecycle["widget"] = EMPTY_PREMOUNT_KERNEL_CONSUMER_WIDGET

        return Reexplode(
            next_fill_shell={
                "id": shell.get("id", position["datum_id"]),
                "title": "Kernel consumer shell generated by mount",
                "micros": [_text_micro("confirm")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"confirm": ""},
            prefill_hints={"confirm": "yes"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])

        self.fill_seen_datum_args_after_reexplode = dict(shell.get("args") or {})
        self.confirmed = dict(fill_data["current_fills"]).get("confirm")
        self.fill_used_prior_final_value = self.prior_final_value_on_mount
        return True


def _register_empty_premount_kernel_widgets_v1() -> None:
    source = pull_thinkwidget_class_into_kernel_v1(
        EmptyPremountKernelSourceWidget,
        overwrite=True,
    )
    assert source["ok"] is True
    assert source["kernel_contract"]["enforce_no_premount_shell"] is True
    assert source["kernel_contract"]["args"]["seed"] == {
        "type": "str",
        "required": True,
    }
    assert source["kernel_contract"]["past_wires"] == {}

    consumer = pull_thinkwidget_class_into_kernel_v1(
        EmptyPremountKernelConsumerWidget,
        overwrite=True,
    )
    assert consumer["ok"] is True
    assert consumer["kernel_contract"]["enforce_no_premount_shell"] is True
    assert consumer["kernel_contract"]["args"]["local"] == {
        "type": "str",
        "required": True,
    }
    assert consumer["kernel_contract"]["past_wires"]["previous_source"] == {
        "multiplicity": "one",
        "required": True,
    }


def _empty_premount_kernel_program_v1() -> list[Dict[str, Any]]:
    return [
        {
            "kind": "think_kernel_step_v1",
            "kernel_args_surface_version": "v1",
            "step": {
                "id": "kernel.empty_premount.K1",
                "title": "Empty Premount K1",
                "args": {},
            },
            "form": {
                "id": "kernel.empty_premount.K1.form",
                "title": "Empty Premount K1 Form",
                "args": {},
            },
            "frame": {
                "id": "F",
                "title": "Frame",
            },
            "span": {
                "id": "S",
                "title": "Span",
                "args": {"span_arg": "source-span"},
            },
            "history_queries": {},
            "datums": [
                {
                    "id": "A",
                    "widget": EMPTY_PREMOUNT_KERNEL_SOURCE_WIDGET,
                    "title": "A source",
                    "micros": [],
                    "lifecycle": {
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 0,
                        "max_messages": 8,
                    },
                    "past_wires": {},
                    "args": {
                        "seed": "alpha-seed",
                    },
                }
            ],
            "kernel_flags": {
                "copy_form_frame_span_args_into_each_datum": True,
                "mount_explode_default": True,
            },
        },
        {
            "kind": "think_kernel_step_v1",
            "kernel_args_surface_version": "v1",
            "step": {
                "id": "kernel.empty_premount.K2",
                "title": "Empty Premount K2",
                "args": {},
            },
            "form": {
                "id": "kernel.empty_premount.K2.form",
                "title": "Empty Premount K2 Form",
                "args": {},
            },
            "frame": {
                "id": "F",
                "title": "Frame",
            },
            "span": {
                "id": "S",
                "title": "Span",
                "args": {"span_arg": "consumer-span"},
            },
            "history_queries": {
                "prior_A": {
                    "from_step": "kernel.empty_premount.K1",
                    "datum_id": "A",
                    "write_kind": WRITE_KIND_DATUM_LIFECYCLE,
                    "include_value": True,
                    "required": True,
                    "select": "latest",
                    "max_results": 20,
                }
            },
            "datums": [
                {
                    "id": "B",
                    "widget": EMPTY_PREMOUNT_KERNEL_CONSUMER_WIDGET,
                    "title": "B consumer",
                    "micros": [],
                    "lifecycle": {
                        "mount_explode": True,
                        "max_reexplosions": 10,
                        "max_proc_notes": 0,
                        "max_messages": 8,
                    },
                    "past_wires": {
                        "previous_source": ["prior_A"],
                    },
                    "args": {
                        "local": "consumer-local",
                    },
                }
            ],
            "kernel_flags": {
                "copy_form_frame_span_args_into_each_datum": True,
                "mount_explode_default": True,
            },
        },
    ]


def test_kernel_pulled_widget_enforces_empty_premount_shell_statically() -> None:
    _register_empty_premount_kernel_widgets_v1()

    program = _empty_premount_kernel_program_v1()
    validate_kernel_program_v1(program)

    bad = _empty_premount_kernel_program_v1()
    bad[0]["datums"][0]["micros"] = [_text_micro("value")]

    with pytest.raises(ValueError, match="enforces no premount shell"):
        validate_kernel_program_v1(bad)


def test_kernel_pulled_widgets_with_empty_premount_shell_mount_generate_first_usable_shell_e2e() -> None:
    _register_empty_premount_kernel_widgets_v1()
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()

    program = validate_kernel_program_v1(_empty_premount_kernel_program_v1())

    api = _api()
    created = api.create_VM_session_from_program(
        program=program,
        program_language=LANG_THINKING_FLOW_EXPLICIT_V1,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "empty_premount_kernel_shelling_e2e",
        },
        get_map=False,
    )

    sid = str(created["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["datum_widgets_on_this_span"] == ["A"]
    assert "value" in str(ctx["datum_widget_decls"]["A"])

    source_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.empty_premount.K1.form",
        "A",
    )
    assert source_mount_state["mount_seen_initial_micros"] == []
    assert source_mount_state["mount_seen_user_args"] == {"seed": "alpha-seed"}
    assert source_mount_state["mount_seen_kernel_step_id"] == "kernel.empty_premount.K1"
    assert source_mount_state["mount_seen_kernel_form_id"] == (
        "kernel.empty_premount.K1.form"
    )
    assert source_mount_state["mount_seen_past_wires"] == {}
    assert source_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"A": {"value": "alpha-from-empty-premount"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["datum_widgets_on_this_span"] == ["B"]
    assert "confirm" in str(ctx["datum_widget_decls"]["B"])

    source_done_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.empty_premount.K1.form",
        "A",
    )
    assert source_done_state["final_value"] == "alpha-from-empty-premount"
    assert source_done_state["commit"] == {
        "datum_id": "A",
        "value": "alpha-from-empty-premount",
    }
    assert source_done_state["fill_seen_datum_args_after_reexplode"] == {}

    consumer_mount_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.empty_premount.K2.form",
        "B",
    )
    assert consumer_mount_state["mount_seen_initial_micros"] == []
    assert consumer_mount_state["mount_seen_user_args"] == {
        "local": "consumer-local",
    }
    assert consumer_mount_state["mount_seen_kernel_step_id"] == "kernel.empty_premount.K2"
    assert consumer_mount_state["mount_seen_kernel_form_id"] == (
        "kernel.empty_premount.K2.form"
    )
    assert consumer_mount_state["prior_final_value_on_mount"] == (
        "alpha-from-empty-premount"
    )
    assert consumer_mount_state["prior_commit_on_mount"] == {
        "datum_id": "A",
        "value": "alpha-from-empty-premount",
    }
    assert consumer_mount_state["mount_root_pollution"] == {
        "kernel": False,
        "step": False,
        "form": False,
        "frame": False,
        "span": False,
        "past_wires": False,
        "history_queries": False,
    }

    ctx = runner.step(fill={"B": {"confirm": "confirmed-empty-premount"}})
    assert ctx["kind"] == "ATCOMPLETION"

    consumer_done_state = _latest_lifecycle_state(
        api,
        sid,
        "kernel.empty_premount.K2.form",
        "B",
    )
    assert consumer_done_state["confirmed"] == "confirmed-empty-premount"
    assert consumer_done_state["fill_seen_datum_args_after_reexplode"] == {}
    assert consumer_done_state["fill_used_prior_final_value"] == (
        "alpha-from-empty-premount"
    )