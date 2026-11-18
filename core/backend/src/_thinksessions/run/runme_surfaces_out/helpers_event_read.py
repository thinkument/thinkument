from __future__ import annotations

"""Public runtime-event reading, validation, and extraction helpers."""

from datetime import datetime
from typing import Any, Iterable, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    SESSION_EVENT_KIND_V1,
    SESSION_EVENT_REQUIRED_KEYS_V1,
)

CONTROLLER_LOOP_EVENT_KIND_V1 = "controller_loop_event_v1"
EVENT_SEQ_KEY_V1 = "event_seq"


def event_seq_v1(event: Mapping[str, Any]) -> int:
    raw = event.get(EVENT_SEQ_KEY_V1)
    if type(raw) is not int or raw < 1:
        raise AssertionError("event_seq must be a positive integer")
    return raw


def controller_events_v1(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    ]


def informative_events_v1(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") != CONTROLLER_LOOP_EVENT_KIND_V1
    ]


def assert_strict_event_order_v1(events: Iterable[Mapping[str, Any]]) -> None:
    seqs = [event_seq_v1(event) for event in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))


def _assert_ui_context_contract_v1(U: Mapping[str, Any]) -> None:
    assert isinstance(U, Mapping)
    assert isinstance(U.get("kind"), str)
    if "last_error" in U:
        assert U["last_error"] is None or isinstance(U["last_error"], Mapping)
    for key in ("globals", "state", "session_metadata", "step", "multiframespec"):
        if key in U:
            assert isinstance(U[key], Mapping)
    if "role_mismatch_modulation_info" in U:
        assert U["role_mismatch_modulation_info"] is None or isinstance(
            U["role_mismatch_modulation_info"], Mapping
        )
    for key in (
        "role_assignments",
        "tags",
        "frames",
        "span_order",
        "datum_widgets_on_this_span",
        "datum_states_on_this_span",
    ):
        if key in U:
            assert isinstance(U[key], list)
    for key in ("span_to_datum_widgets", "datum_widget_decls", "datum_widget_fills"):
        if key in U:
            assert isinstance(U[key], Mapping)
    for key in (
        "session_id", "form_id", "app_form_id", "current_frame_id",
        "current_frame_name", "current_span_id", "current_span",
    ):
        if key in U:
            assert U[key] is None or isinstance(U[key], str)

    datum_states = U.get("datum_states_on_this_span")
    if isinstance(datum_states, list):
        for row in datum_states:
            assert isinstance(row, Mapping)
            assert isinstance(row.get("kind"), str)
            assert isinstance(row.get("datum_id"), str)

            if row.get("kind") == "universal_ui_datum_state_v1":
                for key in (
                    "shell",
                    "args",
                    "semantic_validation",
                    "lifecycle",
                    "originating_step",
                ):
                    assert isinstance(row.get(key), Mapping)
                assert isinstance(row.get("micros"), list)
                assert isinstance(row.get("micro_names"), list)
                assert isinstance(row.get("is_authoritative"), bool)
                assert isinstance(row.get("is_pending"), bool)

            if row.get("kind") == "role_mismatch_obfuscated_datum_v1":
                for forbidden_key in (
                    "shell",
                    "micros",
                    "args",
                    "fill",
                    "semantic_validation",
                    "lifecycle",
                    "originating_step",
                ):
                    assert forbidden_key not in row

    assert_dead_json(dict(U), path="controller_event.payload.U")


def assert_controller_loop_event_v1(event: Mapping[str, Any]) -> None:
    required = {
        "kind", "event_id", "dispatch_id", "dispatcher_identity_id",
        "dispatcher_role", "emitted_at", "source", "name", "phase",
        "session_id", "action", "payload",
    }
    missing = required - set(event)
    extra = set(event) - (required | {EVENT_SEQ_KEY_V1})
    assert not missing and not extra, f"controller event keys differ: missing={missing}, extra={extra}"
    if EVENT_SEQ_KEY_V1 in event:
        event_seq_v1(event)

    assert event["kind"] == CONTROLLER_LOOP_EVENT_KIND_V1
    assert event["source"] == "page_flow_controller"
    assert event["phase"] in {"start", "end"}
    assert event["name"] == f"controller.loop.{event['phase']}"
    for key in ("event_id", "emitted_at", "session_id", "action"):
        assert isinstance(event[key], str) and event[key]
    assert event["dispatch_id"] is None or isinstance(event["dispatch_id"], str)
    assert event["dispatcher_identity_id"] is None or isinstance(
        event["dispatcher_identity_id"], str
    )
    assert event["dispatcher_role"] is None or isinstance(event["dispatcher_role"], str)
    datetime.fromisoformat(str(event["emitted_at"]).replace("Z", "+00:00"))

    payload = event["payload"]
    assert isinstance(payload, Mapping)
    assert payload["timestamp"] == event["emitted_at"]
    assert isinstance(payload["U"], Mapping)
    _assert_ui_context_contract_v1(payload["U"])

    # Canonical packets currently carry A plus compatibility mirrors. Older
    # packets may expose only fill/signal; validators accept both during the
    # migration while requiring internal coherence when A is present.
    if "A" in payload:
        assert payload["A"] is None or isinstance(payload["A"], Mapping)
        if isinstance(payload["A"], Mapping):
            assert payload.get("fill") == payload["A"].get("fill")
            assert payload.get("signal") == payload["A"].get("signal")
    assert payload.get("fill") is None or isinstance(payload.get("fill"), Mapping)
    assert payload.get("signal") is None or isinstance(payload.get("signal"), Mapping)

    if event["phase"] == "start":
        assert "result" not in payload
        assert "system_error" not in payload
        assert "dispatch_context" not in payload
    else:
        assert payload.get("dispatch_context") is None or isinstance(
            payload.get("dispatch_context"),
            Mapping,
        )
        dispatch_context = payload.get("dispatch_context")
        if isinstance(dispatch_context, Mapping):
            filler_receipt = dispatch_context.get("filler_receipt")
            if isinstance(filler_receipt, Mapping):
                next_info = filler_receipt.get("next_U_funkability")
                if next_info is not None:
                    assert isinstance(next_info, Mapping)
                    assert next_info.get("kind") == (
                        "chainreactionTM_next_U_funkability_v1"
                    )
                    assert isinstance(
                        next_info.get("will_funk_next_dispatch"),
                        bool,
                    )
                    assert isinstance(next_info.get("reason"), str)
        outcome = str(payload.get("outcome") or "success")
        assert outcome in {"success", "system_error"}
        if outcome == "system_error":
            assert isinstance(payload.get("system_error"), Mapping)
        else:
            result = payload.get("result")
            assert isinstance(result, Mapping)
            assert isinstance(result.get("event_kind"), str)
            assert isinstance(result.get("ui_mode"), str)
            assert isinstance(result.get("finished"), bool)
            assert result.get("last_error") is None or isinstance(
                result.get("last_error"), Mapping
            )
            assert payload["U"].get("last_error") == result.get("last_error")
    assert_dead_json(dict(event), path="controller_event")


def assert_datum_lifecycle_event_v1(event: Mapping[str, Any]) -> None:
    required = set(SESSION_EVENT_REQUIRED_KEYS_V1)
    missing = required - set(event)
    extra = set(event) - (required | {EVENT_SEQ_KEY_V1})
    assert not missing and not extra, f"datum event keys differ: missing={missing}, extra={extra}"
    if EVENT_SEQ_KEY_V1 in event:
        event_seq_v1(event)
    assert event["kind"] == SESSION_EVENT_KIND_V1
    for key in (
        "event_id", "emitted_at", "source", "name", "form_id", "frame_id",
        "span_id", "datum_id", "signal_kind",
    ):
        assert isinstance(event[key], str)
    assert event["event_id"] and event["emitted_at"] and event["source"] and event["name"]
    assert isinstance(event["payload"], Mapping)
    assert_dead_json(dict(event), path="datum_event")


def assert_canonical_event_v1(event: Mapping[str, Any]) -> None:
    if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1:
        assert_controller_loop_event_v1(event)
    elif event.get("kind") == SESSION_EVENT_KIND_V1:
        assert_datum_lifecycle_event_v1(event)
    else:
        raise AssertionError(f"unknown canonical event kind: {event.get('kind')!r}")


__all__ = (
    "CONTROLLER_LOOP_EVENT_KIND_V1",
    "EVENT_SEQ_KEY_V1",
    "SESSION_EVENT_KIND_V1",
    "assert_canonical_event_v1",
    "assert_controller_loop_event_v1",
    "assert_datum_lifecycle_event_v1",
    "assert_strict_event_order_v1",
    "controller_events_v1",
    "event_seq_v1",
    "informative_events_v1",
)