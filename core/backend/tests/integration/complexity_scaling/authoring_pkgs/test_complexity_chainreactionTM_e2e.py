from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinksessions.run.run_from_here import (
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_events,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM import (
    bootstrap_chainreactiontm_defaults,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


SPY_REQUESTS: list[FunkTMRequest] = []


def _api():
    return get_concrete_session_api()


def _text_micro(name: str = "value", *, typ: str = "text") -> Dict[str, Any]:
    return {"name": name, "type": typ, "required": True}


def _datum(
    datum_id: str,
    *,
    role: str,
    title: str | None = None,
) -> Dict[str, Any]:
    return {
        "id": str(datum_id),
        "title": title or str(datum_id),
        "roles": [str(role)],
        "micros": [_text_micro("value")],
    }


def _one_form_many_spans(
    *,
    app_form_id: str,
    datums: list[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "app_form_id": str(app_form_id),
        "datums": [dict(d) for d in datums],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": f"S_{dict(d)['id']}",
                        "owns": [str(dict(d)["id"])],
                    }
                    for d in datums
                ],
            }
        ],
    }


def _register_step(
    step_name: str,
    multiframespec: Mapping[str, Any],
) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=step_name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _role_chainreaction(
    version: str,
    args: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "version": str(version),
        "args": dict(args or {}),
    }


def _chain_metadata(
    *,
    roles_ordered: list[Any],
    maker_chainreaction: Mapping[str, Any] | None,
    reviewer_chainreaction: Mapping[str, Any] | None,
    max_fills_e2e: int = 128,
    max_fills_on_a_span: int = 4,
    history_tail_cap: int = 4,
    history_size_cap: int = 25_000,
    events_queue_length: int = 0,
) -> Dict[str, Any]:
    return {
        "roles": {
            "reviewer": {
                "label": "Reviewer",
                "chainreactionTM_config": (
                    dict(reviewer_chainreaction)
                    if reviewer_chainreaction is not None
                    else None
                ),
            },
            "maker": {
                "label": "Maker",
                "read_roles": ["reviewer"],
                "chainreactionTM_config": (
                    dict(maker_chainreaction)
                    if maker_chainreaction is not None
                    else None
                ),
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "reviewer": "redacted",
                "maker": "redacted",
            },
        },
        "chainreactionTM_config": {
            "version": "chainreaction1.0",
            "roles_ordered": list(roles_ordered),
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": int(max_fills_on_a_span),
            "max_fills_e2e": int(max_fills_e2e),
            "history_tail_cap": int(history_tail_cap),
            "history_size_cap": int(history_size_cap),
            "events_queue_length": int(events_queue_length),
        },
    }


def _create_session(
    *,
    step_name: str,
    multiframespec: Mapping[str, Any],
    session_metadata: Mapping[str, Any],
) -> str:
    bootstrap_chainreactiontm_defaults()
    _register_step(step_name, multiframespec)

    st = _api().create_VM_session(
        manifest=[
            {
                "public_step_name": step_name,
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
        initial_parameter_overrides={},
        session_metadata=dict(session_metadata),
    )
    return str(st["session_id"])


def _dispatch_chain(session_id: str) -> Dict[str, Any]:
    return dispatch_live_session_action_with_chain_reaction(
        session_id=str(session_id),
        action="STEP",
    )


def _json_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            default=repr,
        )
    )


def _controller_events(events: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == "controller_loop_event_v1"
    ]


def _controller_ends(events: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == "controller_loop_event_v1"
        and event.get("phase") == "end"
    ]


def _role_viewing_from_controller_event(
    event: Mapping[str, Any],
) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None

    U = payload.get("U")
    if not isinstance(U, Mapping):
        return None

    info = U.get("role_mismatch_modulation_info")
    if not isinstance(info, Mapping):
        return None

    role = info.get("role_viewing")
    return str(role) if role is not None else None


def _register_large_payload_version(
    name: str = "test_large_payload_v1",
) -> None:
    def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {"payload_chars": int(raw.get("payload_chars", 8_000))}

    def run(request: FunkTMRequest) -> FunkTMResult:
        payload = "X" * int(request.args["payload_chars"])
        fill = {
            str(row["datum_id"]): {"value": payload}
            for row in request.pending_datums
        }
        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": f"{name}_receipt",
                "filled_count": len(fill),
                "payload_chars": int(request.args["payload_chars"]),
            },
        )

    register_chainreactiontm_version(
        name=name,
        run=run,
        validate_args=validate_args,
        replace=True,
    )


def _register_spy_version(name: str = "test_spy_history_v1") -> None:
    SPY_REQUESTS.clear()

    def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {"value": str(raw.get("value", "spy-ok"))}

    def run(request: FunkTMRequest) -> FunkTMResult:
        SPY_REQUESTS.append(request)
        fill = {
            str(row["datum_id"]): {"value": request.args["value"]}
            for row in request.pending_datums
        }
        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": f"{name}_receipt",
                "history_size": _json_size(request.history),
                "history_rows": len(request.history.get("rows") or []),
                "history_last_k_invocations": request.history.get(
                    "last_k_invocations"
                ),
                "events_seen": len(request.events),
            },
        )

    register_chainreactiontm_version(
        name=name,
        run=run,
        validate_args=validate_args,
        replace=True,
    )


def test_history_tail_and_size_caps_bound_large_prior_values() -> None:
    _register_large_payload_version()
    _register_spy_version()

    reviewer_count = 9
    payload_chars = 8_000
    history_size_cap = 2_500
    history_tail_cap = 3

    datums = [
        _datum(f"R{i}", role="reviewer", title=f"Reviewer datum {i}")
        for i in range(reviewer_count)
    ]
    datums.append(_datum("M", role="maker", title="Maker spy"))

    sid = _create_session(
        step_name="test.chainreactiontm.complexity.history_size.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.complexity.history_size",
            datums=datums,
        ),
        session_metadata=_chain_metadata(
            roles_ordered=["reviewer", "maker"],
            reviewer_chainreaction=_role_chainreaction(
                "test_large_payload_v1",
                {"payload_chars": payload_chars},
            ),
            maker_chainreaction=_role_chainreaction("test_spy_history_v1"),
            max_fills_e2e=reviewer_count + 2,
            history_tail_cap=history_tail_cap,
            history_size_cap=history_size_cap,
        ),
    )

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert SPY_REQUESTS

    history = SPY_REQUESTS[-1].history
    assert _json_size(history) <= history_size_cap
    assert len(history.get("rows") or []) <= history_tail_cap * 2


def test_recent_history_window_prefers_latest_writes_under_long_sessions() -> None:
    _register_spy_version()

    reviewer_count = 40
    latest_id = f"R{reviewer_count - 1}"

    datums = [
        _datum(f"R{i}", role="reviewer", title=f"Reviewer datum {i}")
        for i in range(reviewer_count)
    ]
    datums.append(_datum("M", role="maker", title="Maker spy"))

    sid = _create_session(
        step_name="test.chainreactiontm.complexity.recent_window.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.complexity.recent_window",
            datums=datums,
        ),
        session_metadata=_chain_metadata(
            roles_ordered=["reviewer", "maker"],
            reviewer_chainreaction=_role_chainreaction("title_semantic_v1"),
            maker_chainreaction=_role_chainreaction("test_spy_history_v1"),
            max_fills_e2e=reviewer_count + 2,
            history_tail_cap=1,
            history_size_cap=25_000,
        ),
    )

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert SPY_REQUESTS

    rows = SPY_REQUESTS[-1].history.get("rows") or []
    assert any(row.get("datum_id") == latest_id for row in rows), rows
    assert not any(row.get("datum_id") == "R0" for row in rows), rows


def test_events_tail_cap_is_independent_of_long_generated_history() -> None:
    """
    FunkTM event history is a bounded projected queue tail, not an unbounded
    transcript.

    Important timing law:
    request.events is captured before the Funk-generated dispatch is applied.
    Therefore it should not equal the final queue suffix after chain completion,
    because the spy fill itself appends newer controller start/end events.
    """
    _register_spy_version("test_spy_events_tail_v1")

    reviewer_count = 12
    events_queue_length = 3

    datums = [
        _datum(f"R{i}", role="reviewer", title=f"Reviewer datum {i}")
        for i in range(reviewer_count)
    ]
    datums.append(_datum("M", role="maker", title="Maker spy"))

    sid = _create_session(
        step_name="test.chainreactiontm.complexity.events_tail.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.complexity.events_tail",
            datums=datums,
        ),
        session_metadata=_chain_metadata(
            roles_ordered=["reviewer", "maker"],
            reviewer_chainreaction=_role_chainreaction("title_semantic_v1"),
            maker_chainreaction=_role_chainreaction(
                "test_spy_events_tail_v1",
                {"value": "spy-ok"},
            ),
            max_fills_e2e=reviewer_count + 2,
            history_tail_cap=2,
            history_size_cap=25_000,
            events_queue_length=events_queue_length,
        ),
    )

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert SPY_REQUESTS

    request = SPY_REQUESTS[-1]
    assert 0 < len(request.events) <= events_queue_length

    raw_queue = get_live_session_events(session_id=sid, role=None)
    projected_queue = get_live_session_events(session_id=sid, role="maker")

    assert len(raw_queue) > len(request.events)
    assert len(projected_queue) > len(request.events)

    request_event_ids = [str(event["event_id"]) for event in request.events]
    projected_event_ids = [str(event["event_id"]) for event in projected_queue]
    raw_event_ids = [str(event["event_id"]) for event in raw_queue]

    assert request_event_ids
    assert request_event_ids == raw_event_ids[
        raw_event_ids.index(request_event_ids[0]):
        raw_event_ids.index(request_event_ids[0]) + len(request_event_ids)
    ]

    assert request_event_ids == projected_event_ids[
        projected_event_ids.index(request_event_ids[0]):
        projected_event_ids.index(request_event_ids[0]) + len(request_event_ids)
    ]

    # The request tail was captured before the maker spy dispatch. The final
    # queue now contains newer events appended by that dispatch.
    assert projected_event_ids[-len(request_event_ids):] != request_event_ids

    tail_size = _json_size(request.events)
    raw_queue_size = _json_size(raw_queue)

    assert tail_size < raw_queue_size

    request_controller_events = _controller_events(request.events)
    assert request_controller_events

    assert any(
        _role_viewing_from_controller_event(event) == "maker"
        for event in request_controller_events
    )

    raw_again = get_live_session_events(session_id=sid, role=None)
    assert raw_again == raw_queue

    raw_controller_ends = _controller_ends(raw_queue)
    assert raw_controller_ends

    raw_end_U = raw_controller_ends[-1]["payload"]["U"]
    assert raw_end_U.get("role_mismatch_modulation_info") is None

def test_receipt_dispatch_rows_are_bounded_even_for_many_generated_fills() -> None:
    span_count = 14
    datums = [
        _datum(f"M{i}", role="maker", title=f"Maker datum {i}")
        for i in range(span_count)
    ]

    sid = _create_session(
        step_name="test.chainreactiontm.complexity.receipt_bounded.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.complexity.receipt_bounded",
            datums=datums,
        ),
        session_metadata=_chain_metadata(
            roles_ordered=["maker", "reviewer"],
            reviewer_chainreaction=None,
            maker_chainreaction=_role_chainreaction("title_semantic_v1"),
            max_fills_e2e=span_count + 2,
            history_tail_cap=2,
            history_size_cap=25_000,
        ),
    )

    packet = _dispatch_chain(sid)
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "ATCOMPLETION"
    assert receipt["generated_fills_e2e"] == span_count
    assert receipt["dispatch_count"] == span_count
    assert len(receipt["dispatch_receipts"]) == 8


def test_grouped_roles_are_deterministic_and_do_not_scan_unrelated_later_roles() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.complexity.grouped_roles.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.complexity.grouped_roles",
            datums=[
                _datum("M", role="maker", title="Maker datum"),
            ],
        ),
        session_metadata=_chain_metadata(
            roles_ordered=[["maker", "reviewer"]],
            maker_chainreaction=_role_chainreaction("title_semantic_v1"),
            reviewer_chainreaction=None,
            max_fills_e2e=4,
        ),
    )

    packet = _dispatch_chain(sid)
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "ATCOMPLETION"
    assert receipt["roles_used"] == ["maker"]