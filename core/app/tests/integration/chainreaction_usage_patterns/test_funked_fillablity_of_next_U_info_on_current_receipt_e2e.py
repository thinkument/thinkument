from __future__ import annotations

from typing import Any, Dict, Mapping

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM import (
    bootstrap_chainreactiontm_defaults,
)
from _thinksessions.run.run_from_here import (
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_events,
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
    maker_chainreaction: Mapping[str, Any] | None | bool = True,
    reviewer_chainreaction: Mapping[str, Any] | None | bool = False,
    roles_ordered: list[Any] | None = None,
    roles_extra: Mapping[str, Mapping[str, Any]] | None = None,
    expect_all_roles_chainreactioned: bool = False,
    on_semantic_error: str = "retry_w_error_awareness",
    max_semantic_errors_in_a_row: int = 2,
    max_fills_on_a_span: int = 4,
    max_fills_e2e: int = 16,
    history_tail_cap: int = 4,
    history_size_cap: int = 25_000,
    events_queue_length: int = 0,
) -> Dict[str, Any]:
    def normalize_chainreaction(
        value: Mapping[str, Any] | None | bool,
        default_version: str,
    ) -> Dict[str, Any] | None:
        if value is True:
            return _role_chainreaction(default_version)
        if value is False or value is None:
            return None
        return dict(value)

    roles: Dict[str, Dict[str, Any]] = {
        "maker": {
            "label": "Maker",
            "read_roles": ["reviewer"],
            "chainreactionTM_config": normalize_chainreaction(
                maker_chainreaction,
                "title_semantic_v1",
            ),
        },
        "reviewer": {
            "label": "Reviewer",
            "chainreactionTM_config": normalize_chainreaction(
                reviewer_chainreaction,
                "basic_microtype_v1",
            ),
        },
    }

    for role_name, row in dict(roles_extra or {}).items():
        roles[str(role_name)] = dict(row)

    if roles_ordered is None:
        roles_ordered = list(roles)

    return {
        "roles": roles,
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                role_name: "redacted"
                for role_name in roles
            },
        },
        "chainreactionTM_config": {
            "version": "chainreaction1.0",
            "roles_ordered": roles_ordered,
            "expect_all_roles_chainreactioned": bool(
                expect_all_roles_chainreactioned
            ),
            "on_semantic_error": on_semantic_error,
            "max_semantic_errors_in_a_row": int(
                max_semantic_errors_in_a_row
            ),
            "max_fills_on_a_span": int(max_fills_on_a_span),
            "max_fills_e2e": int(max_fills_e2e),
            "history_tail_cap": int(history_tail_cap),
            "history_size_cap": int(history_size_cap),
            "events_queue_length": int(events_queue_length),
        },
    }


def _text_micro(
    name: str = "value",
    *,
    typ: str = "text",
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": typ,
        "required": required,
    }


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
        "micros": [_text_micro()],
    }


def _one_form_many_spans(
    *,
    app_form_id: str,
    datums: list[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "app_form_id": str(app_form_id),
        "datums": [dict(datum) for datum in datums],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": f"S_{dict(datum)['id']}",
                        "owns": [str(dict(datum)["id"])],
                    }
                    for datum in datums
                ],
            }
        ],
    }


def _register_step(
    step_name: str,
    multiframespec: Mapping[str, Any],
) -> None:
    def step_fn(
        _state: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "multiframespec": dict(multiframespec),
        }

    StepFnregistry.register(
        name=step_name,
        fn=step_fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _create_session(
    *,
    step_name: str,
    multiframespec: Mapping[str, Any],
    session_metadata: Mapping[str, Any],
) -> str:
    bootstrap_chainreactiontm_defaults()
    _register_step(step_name, multiframespec)

    session = get_concrete_session_api().create_VM_session(
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

    return str(session["session_id"])


def _dispatch(
    session_id: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    return dispatch_live_session_action_with_chain_reaction(
        session_id=str(session_id),
        action="STEP",
        identity_id="next-U-funkability-e2e",
        **kwargs,
    )


def _generated_end_events(
    session_id: str,
) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in get_live_session_events(
            session_id=str(session_id),
            role=None,
        )
        if event.get("kind") == "controller_loop_event_v1"
        and event.get("phase") == "end"
        and isinstance(
            (event.get("payload") or {}).get(
                "dispatch_context"
            ),
            Mapping,
        )
    ]


def _next_info(
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    payload = dict(event["payload"])
    dispatch_context = dict(payload["dispatch_context"])
    filler_receipt = dict(
        dispatch_context["filler_receipt"]
    )
    return dict(
        filler_receipt["next_U_funkability"]
    )


def test_current_generated_end_receipt_says_next_dispatch_will_be_funked() -> None:
    sid = _create_session(
        step_name="test.next_U_funkability.continues.step",
        multiframespec=_one_form_many_spans(
            app_form_id="next_U_funkability.continues",
            datums=[
                _datum(
                    "M1",
                    role="maker",
                    title="Maker one",
                ),
                _datum(
                    "M2",
                    role="maker",
                    title="Maker two",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
        ),
    )

    packet = _dispatch(sid)
    assert packet["event_kind"] == "ATCOMPLETION"

    generated_ends = _generated_end_events(sid)
    assert len(generated_ends) == 2

    first = _next_info(generated_ends[0])
    assert first == {
        "kind": "chainreactionTM_next_U_funkability_v1",
        "evaluated_from": "controller.loop.end.payload.U",
        "U_kind": "MANUALFILLNEEDEDSTEP",
        "span_id": "S_M2",
        "will_funk_next_dispatch": True,
        "selected_role": "maker",
        "selected_version": "title_semantic_v1",
        "pending_roles": ["maker"],
        "reason": "next_dispatch_funkable",
        "writable_pending_datum_ids": ["M2"],
    }

    last = _next_info(generated_ends[1])
    assert last["will_funk_next_dispatch"] is False
    assert last["selected_role"] is None
    assert (
        last["reason"]
        == "program_complete_or_not_manual"
    )
    assert last["U_kind"] == "ATCOMPLETION"


def test_current_generated_end_receipt_says_next_dispatch_hits_human_barrier() -> None:
    sid = _create_session(
        step_name=(
            "test.next_U_funkability."
            "human_barrier.step"
        ),
        multiframespec=_one_form_many_spans(
            app_form_id=(
                "next_U_funkability.human_barrier"
            ),
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker",
                ),
                _datum(
                    "R",
                    role="reviewer",
                    title="Reviewer",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
        ),
    )

    packet = _dispatch(sid)
    assert (
        packet["event_kind"]
        == "MANUALFILLNEEDEDSTEP"
    )

    generated_ends = _generated_end_events(sid)
    assert len(generated_ends) == 1

    info = _next_info(generated_ends[0])

    assert info["U_kind"] == "MANUALFILLNEEDEDSTEP"
    assert info["span_id"] == "S_R"
    assert info["pending_roles"] == ["reviewer"]
    assert info["will_funk_next_dispatch"] is False
    assert info["selected_role"] is None
    assert info["selected_version"] is None
    assert (
        info["reason"]
        == "next_pending_role_unchainreactioned"
    )


def test_each_receipt_is_derived_from_that_same_end_event_U() -> None:
    sid = _create_session(
        step_name=(
            "test.next_U_funkability."
            "same_end_U.step"
        ),
        multiframespec=_one_form_many_spans(
            app_form_id=(
                "next_U_funkability.same_end_U"
            ),
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker",
                ),
                _datum(
                    "R",
                    role="reviewer",
                    title="Reviewer",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
        ),
    )

    _dispatch(sid)

    end = _generated_end_events(sid)[0]
    info = _next_info(end)
    end_U = end["payload"]["U"]

    assert (
        info["evaluated_from"]
        == "controller.loop.end.payload.U"
    )
    assert info["U_kind"] == end_U["kind"]
    assert info["span_id"] == (
        end_U.get("current_span")
        or end_U.get("current_span_id")
    )

    current = (
        get_concrete_session_api()
        .get_session_context(sid)
    )

    assert current["kind"] == end_U["kind"]
    assert (
        current.get("current_span")
        or current.get("current_span_id")
    ) == info["span_id"]


def test_role_projection_preserves_or_redacts_next_U_info_with_receipt_law() -> None:
    sid = _create_session(
        step_name=(
            "test.next_U_funkability."
            "projection.step"
        ),
        multiframespec=_one_form_many_spans(
            app_form_id=(
                "next_U_funkability.projection"
            ),
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker",
                ),
                _datum(
                    "R",
                    role="reviewer",
                    title="Reviewer",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
        ),
    )

    _dispatch(sid)

    canonical = _generated_end_events(sid)[0]

    maker_events = get_live_session_events(
        session_id=sid,
        role="maker",
    )
    maker = next(
        event
        for event in maker_events
        if event.get("event_id")
        == canonical["event_id"]
    )
    assert _next_info(maker) == _next_info(canonical)

    reviewer_events = get_live_session_events(
        session_id=sid,
        role="reviewer",
    )
    reviewer = next(
        event
        for event in reviewer_events
        if event.get("event_id")
        == canonical["event_id"]
    )
    assert (
        reviewer["payload"]["dispatch_context"]
        is None
    )