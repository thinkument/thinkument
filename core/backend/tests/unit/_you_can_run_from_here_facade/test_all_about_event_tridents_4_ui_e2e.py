from __future__ import annotations

"""E2E proof of the exact trident data surface consumed by downstream UIs.

The fixture exercises ThinkProgram authoring, mount reexplosion,
custom micro args, semantic validation, fills, opaque errors, and ThinkWidget
``datum.message`` packets.  All interpretation is delegated to the adjacent
application-facing reader module.
"""

from dataclasses import replace
import json
import sys
import types
from typing import Any, Dict, Mapping

import pytest

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json
from _thinkprogram._iomicrosTM.validators.number import (
    min_number_validator_spec,
)
from _thinkprogram._iomicrosTM.table_micros import MICRO_TYPES, ValidatorPolicy
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
)
from _thinkprogram.thinkwidgetTM import (
    DatumLifecycleWidget,
    Reexplode,
    thinkwidgetTM_config,
)
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    dispatch_live_session_action,
    get_live_session_events,
)

from ._event_trident_downstream_readers import (
    active_span_U_v1,
    authoritative_datum_ids_v1,
    build_trident_log_v1,
    controller_A_v1,
    controller_U_v1,
    datum_fill_v1,
    datum_micro_specs_v1,
    datum_states_by_id_v1,
    effective_datum_shell_by_id_v1,
    frame_by_id_v1,
    freeze_json_v1,
    parse_versioned_json_error_v1,
    pending_datum_ids_v1,
    semantic_errors_v1,
    semantic_validator_specs_v1,
    span_datum_vector_v1,
    span_spec_v1,
    thaw_json_v1,
    thinkwidget_messages_v1,
)
from ._fixtures_facade_run import (
    W_NOTE,
    facade_session_metadata_v1,
    register_facade_run_fixture_v1,
)


WIDGET = "test.trident.ui.widget.v1"
VALIDATOR_MODULE = "test_trident_ui_surface_validators_v1"


def _dispatch(*, session_id: str, **kwargs: Any) -> dict[str, Any]:
    return dispatch_live_session_action(
        session_id=session_id,
        action=UserAction.STEP,
        identity_id="trident-ui-e2e",
        role="writer",
        **kwargs,
    )


def _last_trident(session_id: str):
    log = build_trident_log_v1(
        get_live_session_events(session_id=session_id, role=None)
    )
    assert log.ordered
    return log.ordered[-1]


# Dynamic dead-JSON-addressable validator used by the test-owned shell.
_validator_module = types.ModuleType(VALIDATOR_MODULE)


def min_code(value: Any, *, minimum: int) -> tuple[bool, str | None]:
    text = str(
        value.get("value")
        if isinstance(value, Mapping) and "value" in value
        else value or ""
    )
    if len(text) >= int(minimum):
        return True, None
    return False, json.dumps(
        {
            "v": 1,
            "code": "code_too_short",
            "message": f"Code must contain at least {int(minimum)} characters.",
            "details": {"minimum": int(minimum), "actual": len(text)},
        },
        separators=(",", ":"),
        sort_keys=True,
    )


_validator_module.min_code = min_code
sys.modules[VALIDATOR_MODULE] = _validator_module


def _validator_spec() -> Dict[str, Any]:
    return {
        "path": f"{VALIDATOR_MODULE}:min_code",
        "args": {"minimum": 3},
    }


def _register_validator_capability() -> None:
    """Register capability without auto-installing it on unrelated micros."""
    path = f"{VALIDATOR_MODULE}:min_code"
    text_def = MICRO_TYPES["text"]
    policies = tuple(text_def.validators or ())
    if any(str(policy.path) == path for policy in policies):
        return
    MICRO_TYPES["text"] = replace(
        text_def,
        validators=(
            *policies,
            ValidatorPolicy(
                path=path,
                mandatory_enforced=False,
                arg_map={"minimum": "minimum"},
                guidance_channel="local_guidance",
            ),
        ),
    )


@thinkwidgetTM_config(
    WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    args={},
    wires={},
)
class TridentUIWidget(DatumLifecycleWidget):
    @staticmethod
    def _mounted_shell(
        position: Mapping[str, Any], *, kernel_packet: Mapping[str, Any]
    ) -> Dict[str, Any]:
        return {
            "id": position["datum_id"],
            "title": "Claim details",
            "subtitle": "Exact current-effective UI shell",
            "help_text": "Enter a code and an amount.",
            "tags": ["task-c", "ui-surface"],
            "x_datum_app": {
                "component": "claim-editor",
                "contract_version": 1,
            },
            "args": {
                "x_widget_mode": "claim",
                "__kernel": dict(kernel_packet),
            },
            "micros": [
                {
                    "name": "code",
                    "type": "text",
                    "required": True,
                    "label": "Claim code",
                    "placeholder": "ABC",
                    "validators": [_validator_spec()],
                    "args": {
                        "analytics_key": "claim_code",
                        "input_mode": "uppercase",
                    },
                    "x_micro_app": {"control": "code-entry"},
                },
                {
                    "name": "amount",
                    "type": "number",
                    "required": True,
                    "label": "Claim amount",
                    "validators": [min_number_validator_spec(1)],
                    "args": {
                        "currency": "USD",
                        "decimals": 2,
                        "analytics_key": "claim_amount",
                    },
                    "x_micro_app": {"control": "money-entry"},
                },
            ],
            "macro_validation_lambdas": [],
            "lifecycle": {
                "widget": WIDGET,
                "mount_explode": True,
                "max_reexplosions": 2,
                "max_messages": 8,
                "max_proc_notes": 0,
            },
        }

    def _on_mount(self, position, fill_data, limits, stats):
        del limits, stats
        # The public callback contract carries the current shell directly in
        # fill_data["fill_shell"]; there is no fill_data["q"] pocket.
        fill_shell = fill_data["fill_shell"]
        kernel_packet = dict(fill_shell["args"]["__kernel"])
        self.message("info", "claim datum mounted")
        return Reexplode(
            next_fill_shell=self._mounted_shell(
                position, kernel_packet=kernel_packet
            ),
            pre_computed_fills={"code": "", "amount": None},
            prefill_hints={"code": "ABC", "amount": 1},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        del signal, position, limits, stats
        current = dict(fill_data["current_fills"])
        self.message("success", "claim datum accepted")
        self.code = current["code"]
        self.amount = current["amount"]
        return True


def program_v1() -> Dict[str, Any]:
    lifecycle = {
        "mount_explode": True,
        "max_reexplosions": 2,
        "max_messages": 8,
        "max_proc_notes": 0,
    }
    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {"lifecycle": {"value": lifecycle}},
        "puppeteering": {},
        "run": {
            "program": {
                "info": {
                    "id": "trident_ui_surface",
                    "title": "Trident UI surface",
                    "description": "Exact downstream UI data proof.",
                    "args": {},
                },
                "widgets": {
                    "claim": {
                        "widget": WIDGET,
                        "title": "Claim",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        "roles": ["writer"],
                        "authoritative": True,
                        "tags": ["task-c"],
                        "system_flags": {},
                    },
                    "optional_note": {
                        "widget": W_NOTE,
                        "title": "Optional note",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        "roles": ["writer"],
                        "authoritative": False,
                        "tags": ["task-c", "non-authoritative"],
                        "system_flags": {},
                    },
                },
                "flow": [
                    {
                        "id": "collect_claim",
                        "title": "Collect claim",
                        "widgets": ["claim", "optional_note"],
                        "authoritative": [True, False],
                        "overrides": {},
                    }
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                    "include_full_multiframespec_in_ctx": True,
                }
            },
        },
    }


def launch_session_v1() -> str:
    register_facade_run_fixture_v1()
    _register_validator_capability()
    receipt = pull_thinkwidget_class_into_kernel_v1(
        TridentUIWidget, overwrite=True
    )
    assert receipt["ok"] is True
    created = create_live_session_from_program(
        program=program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata=facade_session_metadata_v1(chainreactioned=False),
    )
    assert created["ok"] is True
    return str(created["session_id"])


# First render: D vector, authority, micros, frame, and rich spec ----


def test_01_first_end_U_is_complete_markovian_active_span_snapshot() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    trident = log.ordered[-1]
    U = controller_U_v1(trident.end)

    assert trident.transition == "N->S"
    assert U["kind"] == "MANUALFILLNEEDEDSTEP"
    rows = span_datum_vector_v1(U)
    assert [row["datum_id"] for row in rows] == ["claim", "optional_note"]
    assert authoritative_datum_ids_v1(U) == ("claim",)
    assert pending_datum_ids_v1(U) == ("claim", "optional_note")

    by_id = datum_states_by_id_v1(U)
    claim = by_id["claim"]
    note = by_id["optional_note"]
    assert claim["is_authoritative"] is True
    assert note["is_authoritative"] is False
    assert claim["is_pending"] is True
    assert note["is_pending"] is True
    assert claim["shell"]["title"] == "Claim details"
    assert claim["shell"]["x_datum_app"] == {
        "component": "claim-editor",
        "contract_version": 1,
    }
    assert claim["shell"] == effective_datum_shell_by_id_v1(U, "claim")

    micros = datum_micro_specs_v1(claim)
    assert [micro["name"] for micro in micros] == ["code", "amount"]
    assert [micro["type"] for micro in micros] == ["text", "number"]
    assert all(micro["required"] is True for micro in micros)
    assert micros[0]["args"] == {
        "analytics_key": "claim_code",
        "input_mode": "uppercase",
    }
    assert micros[0]["x_micro_app"] == {"control": "code-entry"}
    assert micros[1]["args"] == {
        "currency": "USD",
        "decimals": 2,
        "analytics_key": "claim_amount",
    }
    assert micros[1]["x_micro_app"] == {"control": "money-entry"}

    frame = frame_by_id_v1(U, U["current_frame_id"])
    assert frame["field_ids"] == ("claim", "optional_note")
    assert frame["fillspans"]
    span = span_spec_v1(
        U,
        frame_id=U["current_frame_id"],
        span_id=U["current_span_id"],
    )
    assert span["owns"] == ("claim", "optional_note")
    assert U["datum_widget_fills"]["claim"] == {"code": "", "amount": None}
    assert datum_fill_v1(claim) == (True, {"code": "", "amount": None})

    messages = thinkwidget_messages_v1(trident)
    assert any(
        event["datum_id"] == "claim"
        and event["signal_kind"] == "mount"
        and event["payload"]["message"]["text"] == "claim datum mounted"
        for event in messages
    )
    assert controller_A_v1(trident.start) == {"fill": {}, "signal": None}
    assert controller_A_v1(trident.end) == controller_A_v1(trident.start)


def test_03_validator_summary_matches_current_effective_shell() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    claim = datum_states_by_id_v1(controller_U_v1(_last_trident(sid).end))["claim"]
    shell_micros = {row["name"]: row for row in claim["shell"]["micros"]}
    summary = semantic_validator_specs_v1(claim)
    assert thaw_json_v1(shell_micros["code"]["validators"]) == [_validator_spec()]
    assert thaw_json_v1(shell_micros["amount"]["validators"]) == [
        min_number_validator_spec(1)
    ]
    assert {row["name"] for row in summary["micros"]} == {"code", "amount"}


# Semantic rejection: routing and app-owned JSON convention -----------------


def test_04_semantic_error_is_datum_keyed_and_json_is_app_owned() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    packet = _dispatch(
        session_id=sid,
        user_fill={"claim": {"code": "x", "amount": 5}},
    )
    assert packet["dispatch_outcome"] == "semantic_rejected"
    trident = _last_trident(sid)
    assert trident.transition == "S->S"
    assert trident.outcome == "semantic_rejected"
    errors = semantic_errors_v1(trident)
    assert set(errors) == {"claim"}
    parsed = parse_versioned_json_error_v1(
        errors["claim"], micro_name="code"
    )
    assert parsed is not None
    assert parsed["v"] == 1
    assert parsed["code"] == "code_too_short"
    assert parsed["details"] == {"minimum": 3, "actual": 1}
    assert parse_versioned_json_error_v1(errors["claim"]) is None
    U = controller_U_v1(trident.end)
    assert trident.end["payload"]["result"]["last_error"] == U["last_error"]
    assert pending_datum_ids_v1(U) == ("claim", "optional_note")
    assert datum_states_by_id_v1(U)["claim"]["fill"] == {
        "code": "",
        "amount": None,
    }


def test_05_multiple_errors_remain_independently_routable_and_opaque() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    packet = _dispatch(
        session_id=sid,
        user_fill={
            "claim": {"code": "x", "amount": 0},
            "optional_note": {"text": ""},
        },
    )
    assert packet["dispatch_outcome"] == "semantic_rejected"
    errors = semantic_errors_v1(_last_trident(sid))
    assert set(errors) == {"claim", "optional_note"}
    raw = errors["claim"]
    assert isinstance(raw, str)
    assert "code:" in raw
    assert "amount:" in raw
    assert parse_versioned_json_error_v1(raw) is None
    assert parse_versioned_json_error_v1(
        raw, micro_name="code"
    )["code"] == "code_too_short"
    assert parse_versioned_json_error_v1(raw, micro_name="amount") is None
    assert isinstance(errors["optional_note"], str)


# Valid fill, history, registry boundary, optional rich spec, immutability ---


def test_06_authoritative_fill_completes_despite_non_authoritative_D() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    packet = _dispatch(
        session_id=sid,
        user_fill={"claim": {"code": "ABC", "amount": "7"}},
    )
    assert packet["dispatch_outcome"] == "applied"
    assert packet["write_committed"] is True
    trident = _last_trident(sid)
    before = controller_U_v1(trident.start)
    after = controller_U_v1(trident.end)
    assert [row["datum_id"] for row in span_datum_vector_v1(before)] == [
        "claim", "optional_note",
    ]
    assert after["kind"] == "ATCOMPLETION"
    assert "datum_states_on_this_span" not in after
    assert controller_A_v1(trident.start)["fill"]["claim"] == {
        "code": "ABC",
        "amount": "7",
    }
    assert controller_A_v1(trident.end) == controller_A_v1(trident.start)
    assert any(
        event["datum_id"] == "claim"
        and event["payload"]["message"]["text"] == "claim datum accepted"
        for event in thinkwidget_messages_v1(trident)
    )


def test_07_each_end_U_is_a_self_contained_history_page() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    _dispatch(session_id=sid, user_fill={"claim": {"code": "x", "amount": 5}})
    _dispatch(session_id=sid, user_fill={"claim": {"code": "ABC", "amount": 7}})
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    pages = [controller_U_v1(trident.end) for trident in log.ordered]
    assert [page["kind"] for page in pages] == [
        "MANUALFILLNEEDEDSTEP",
        "MANUALFILLNEEDEDSTEP",
        "ATCOMPLETION",
    ]
    assert controller_U_v1(log.ordered[0].end) == controller_U_v1(
        log.ordered[1].start
    )
    assert controller_U_v1(log.ordered[1].end) == controller_U_v1(
        log.ordered[2].start
    )
    assert set(pages[1]["last_error"]) == {"claim"}
    assert effective_datum_shell_by_id_v1(pages[1], "claim")["title"] == (
        "Claim details"
    )


def test_08_trident_carries_current_micros_not_global_registry() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    U = controller_U_v1(_last_trident(sid).end)
    claim = datum_states_by_id_v1(U)["claim"]
    assert {micro["type"] for micro in datum_micro_specs_v1(claim)} == {
        "text", "number",
    }
    assert "MICRO_TYPES" not in U
    assert "micro_table" not in U
    assert "all_micros" not in U
    lowered = U["datum_widget_decls"]["claim"]["datum_args"]["micro_input_fields"]
    by_name = {row["name"]: row for row in lowered}
    assert by_name["code"]["args"] == {
        "analytics_key": "claim_code",
        "input_mode": "uppercase",
    }
    assert by_name["code"]["analytics_key"] == "claim_code"
    assert by_name["code"]["x_micro_app"] == {"control": "code-entry"}
    assert by_name["amount"]["currency"] == "USD"
    assert by_name["amount"]["decimals"] == 2


def test_09_effective_shell_reader_falls_back_when_multiframespec_is_absent() -> None:
    """Render-critical Di remains sufficient when rich spec inclusion is off."""
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    U = controller_U_v1(_last_trident(sid).end)
    mutable = thaw_json_v1(U)
    mutable.pop("multiframespec", None)
    frozen_without_spec = freeze_json_v1(mutable)
    assert effective_datum_shell_by_id_v1(
        frozen_without_spec, "claim"
    )["title"] == "Claim details"
    with pytest.raises(KeyError, match="multiframespec"):
        span_spec_v1(
            frozen_without_spec,
            frame_id=U["current_frame_id"],
            span_id=U["current_span_id"],
        )


def test_10_UI_relevant_pockets_are_dead_json_and_snapshot_immutable() -> None:
    sid = launch_session_v1()
    _dispatch(session_id=sid)
    trident = _last_trident(sid)
    U = controller_U_v1(trident.end)
    claim = datum_states_by_id_v1(U)["claim"]
    assert_dead_json(thaw_json_v1(U), path="task_c.U")
    assert_dead_json(thaw_json_v1(claim), path="task_c.Di")
    assert_dead_json(
        thaw_json_v1(semantic_validator_specs_v1(claim)),
        path="task_c.semantic_validation",
    )
    with pytest.raises(TypeError):
        claim["is_pending"] = False  # type: ignore[index]
