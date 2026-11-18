from __future__ import annotations

import json
import sys
import types
from typing import Any, Dict, Mapping

import pytest

from __datomatonTM import register_datum_widget_v1
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
from _thinksessions.libs_read_write_augmented.chainreactionTM._errors import (
    FunkMaxFillsE2EExceeded,
    FunkMaxFillsOnSpanExceeded,
    FunkMaxSemanticErrorsExceeded,
    FunkRoleConfigMissingStaticError,
    FunkRoleMissingStaticError,
    FunkUnanticipatedDatumRoleRuntimeError,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._static import (
    normalize_chainreactiontm_config_from_session_metadata,
)


VALIDATOR_MODULE = "test_chainreactiontm_chain_reaction_validators"
validators_mod = types.ModuleType(VALIDATOR_MODULE)


def _leaf(value: Any) -> Any:
    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    return value


def min_len(value: Any, *, n: int) -> tuple[bool, str | None]:
    s = str(_leaf(value) or "")
    if len(s) >= int(n):
        return True, None
    return False, f"must have length >= {n}"


validators_mod.min_len = min_len
sys.modules[VALIDATOR_MODULE] = validators_mod


def _path(fn_name: str) -> str:
    return f"{VALIDATOR_MODULE}:{fn_name}"


SPY_REQUESTS: list[FunkTMRequest] = []


def _api():
    return get_concrete_session_api()


def _role_chainreaction(
    version: str,
    args: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {"version": str(version), "args": dict(args or {})}


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
    ):
        if value is True:
            return _role_chainreaction(default_version)
        if value is False:
            return None
        if value is None:
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
    validators: Any = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": name,
        "type": typ,
        "required": required,
    }
    if validators is not None:
        out["validators"] = validators
    return out


def _datum(
    datum_id: str,
    *,
    role: str,
    title: str | None = None,
    micros: list[Mapping[str, Any]] | None = None,
    lifecycle: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": str(datum_id),
        "title": title or str(datum_id),
        "roles": [str(role)],
        "micros": [
            dict(m)
            for m in (micros or [_text_micro("value")])
        ],
    }
    if lifecycle is not None:
        out["lifecycle"] = dict(lifecycle)
    return out


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


def _dispatch_chain(
    session_id: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    return dispatch_live_session_action_with_chain_reaction(
        session_id=str(session_id),
        action="STEP",
        **kwargs,
    )


def _last_error_text(session_id: str) -> str:
    ctx = _api().get_session_context(str(session_id))
    return json.dumps(
        ctx.get("last_error") or {},
        sort_keys=True,
        default=repr,
    )


def _assert_no_forbidden_raw_keys(value: Any) -> None:
    forbidden = {
        "ctx",
        "raw_ctx",
        "context",
        "snapshot",
        "program_map",
        "state",
        "globals",
        "history",
        "datum_widget_fills",
        "datum_widget_decls",
    }

    def is_allowed_metadata_scalar(
        parent_key: str | None,
        key: str,
        child: Any,
    ) -> bool:
        if parent_key == "counts":
            return isinstance(
                child,
                (int, float, bool, str, type(None)),
            )
        if parent_key == "keys":
            return (
                isinstance(child, list)
                and all(isinstance(x, str) for x in child)
            )
        if parent_key == "ctx_report" and key == "last_error":
            return child in ({}, None) or isinstance(child, Mapping)
        return False

    stack = [(None, value)]
    seen: set[int] = set()

    while stack:
        parent_key, cur = stack.pop()
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            for key, child in cur.items():
                key_s = str(key)
                if key_s in forbidden:
                    assert is_allowed_metadata_scalar(
                        parent_key,
                        key_s,
                        child,
                    ), (
                        "raw forbidden key leaked at "
                        f"parent={parent_key!r}, key={key_s!r}"
                    )
                    continue
                stack.append((key_s, child))
        elif isinstance(cur, list):
            stack.extend((parent_key, item) for item in cur)


def _register_spy_version(name: str = "spy_capture_v1") -> None:
    SPY_REQUESTS.clear()

    def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {"text": str(raw.get("text", "spy-ok"))}

    def run(request: FunkTMRequest) -> FunkTMResult:
        SPY_REQUESTS.append(request)
        fill = {
            str(row["datum_id"]): {"value": request.args["text"]}
            for row in request.pending_datums
        }
        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": f"{name}_receipt",
                "pending_datums": sorted(fill),
                "history_row_count": len(
                    request.history.get("rows") or []
                ),
                "history_readable_roles": list(
                    request.history.get("readable_roles") or []
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


def _metadata(
    *,
    maker_chainreaction=True,
    reviewer_chainreaction=False,
):
    return {
        "roles": {
            "maker": {
                "label": "Maker",
                "read_roles": ["reviewer"],
                "chainreactionTM_config": (
                    {"version": "title_semantic_v1", "args": {}}
                    if maker_chainreaction
                    else None
                ),
            },
            "reviewer": {
                "label": "Reviewer",
                "chainreactionTM_config": (
                    {"version": "basic_microtype_v1", "args": {}}
                    if reviewer_chainreaction
                    else None
                ),
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
            },
        },
        "chainreactionTM_config": {
            "version": "chainreaction1.0",
            "roles_ordered": ["maker", "reviewer"],
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": 4,
            "max_fills_e2e": 16,
            "history_tail_cap": 4,
            "history_size_cap": 25000,
            "events_queue_length": 0,
        },
    }


def test_static_accepts_exact_role_order_and_per_role_configs():
    bootstrap_chainreactiontm_defaults()

    cfg = normalize_chainreactiontm_config_from_session_metadata(
        _metadata()
    )

    assert cfg.enabled is True
    assert cfg.flat_roles_ordered == ["maker", "reviewer"]
    assert (
        cfg.role_configs["maker"]["version"]
        == "title_semantic_v1"
    )
    assert cfg.role_configs["reviewer"] is None


def test_static_rejects_missing_role_in_roles_ordered():
    bootstrap_chainreactiontm_defaults()

    meta = _metadata()
    meta["chainreactionTM_config"]["roles_ordered"] = ["maker"]

    with pytest.raises(FunkRoleMissingStaticError):
        normalize_chainreactiontm_config_from_session_metadata(meta)


def test_static_rejects_missing_per_role_chainreactiontm_key():
    bootstrap_chainreactiontm_defaults()

    meta = _metadata()
    del meta["roles"]["reviewer"]["chainreactionTM_config"]

    with pytest.raises(FunkRoleConfigMissingStaticError):
        normalize_chainreactiontm_config_from_session_metadata(meta)


def test_static_expect_all_roles_chainreactioned_rejects_none_role():
    bootstrap_chainreactiontm_defaults()

    meta = _metadata(
        maker_chainreaction=True,
        reviewer_chainreaction=False,
    )
    meta["chainreactionTM_config"][
        "expect_all_roles_chainreactioned"
    ] = True

    with pytest.raises(FunkRoleConfigMissingStaticError):
        normalize_chainreactiontm_config_from_session_metadata(meta)


def test_disabled_when_top_level_config_is_none():
    bootstrap_chainreactiontm_defaults()

    meta = _metadata()
    meta["chainreactionTM_config"] = None

    cfg = normalize_chainreactiontm_config_from_session_metadata(meta)

    assert cfg.enabled is False


def test_e2e_machine_then_manual_stop() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.machine_then_manual.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.machine_then_manual",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker text",
                ),
                _datum(
                    "R",
                    role="reviewer",
                    title="Reviewer text",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
            max_fills_e2e=8,
        ),
    )

    packet = _dispatch_chain(sid)
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert packet["ctx_report"]["span_id"] == "S_R"
    assert receipt["generated_fills_e2e"] == 1
    assert receipt["roles_used"] == ["maker"]
    assert (
        receipt["stopped_reason"]
        == "next_pending_role_unchainreactioned"
    )

    out = _api().get_outputs(sid)
    assert (
        out["form_fills"]["M"]["value"]
        == "semantically filled"
    )


def test_e2e_all_roles_chainreactioned_reaches_completion() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.all_roles.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.all_roles",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maximum score",
                    micros=[
                        _text_micro(
                            "max",
                            typ="integer",
                        )
                    ],
                ),
                _datum(
                    "R",
                    role="reviewer",
                    title="Word count from title",
                    micros=[
                        _text_micro(
                            "word_count",
                            typ="integer",
                        )
                    ],
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1",
                {"max_value": 777},
            ),
            reviewer_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            roles_ordered=["maker", "reviewer"],
            max_fills_e2e=8,
        ),
    )

    packet = _dispatch_chain(sid)
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "ATCOMPLETION"
    assert receipt["generated_fills_e2e"] == 2
    assert receipt["roles_used"] == ["maker", "reviewer"]
    assert (
        receipt["stopped_reason"]
        == "program_complete_or_not_manual"
    )

    out = _api().get_outputs(sid)
    assert out["form_fills"]["M"]["max"] == 777
    assert out["form_fills"]["R"]["word_count"] == 4


def test_e2e_basic_version_semantic_retries_then_cap() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.basic_semantic_retry.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.basic_semantic_retry",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Needs at least three chars",
                    micros=[
                        _text_micro(
                            "value",
                            validators=[
                                {
                                    "path": _path("min_len"),
                                    "args": {"n": 3},
                                },
                            ],
                        )
                    ],
                )
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "basic_microtype_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
            max_semantic_errors_in_a_row=1,
            max_fills_on_a_span=5,
            max_fills_e2e=5,
        ),
    )

    with pytest.raises(FunkMaxSemanticErrorsExceeded):
        _dispatch_chain(sid)

    assert "length >= 3" in _last_error_text(sid)


def test_e2e_title_semantic_version_passes_same_datum() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.title_semantic_passes.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.title_semantic_passes",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Needs at least three chars",
                    micros=[
                        _text_micro(
                            "value",
                            validators=[
                                {
                                    "path": _path("min_len"),
                                    "args": {"n": 3},
                                },
                            ],
                        )
                    ],
                )
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

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert packet["last_error"] in ({}, None)
    assert (
        _api().get_outputs(sid)["form_fills"]["M"]["value"]
        == "semantically filled"
    )


def test_e2e_reexploding_datum_hits_span_fill_cap() -> None:
    widget_name = "test.chainreactiontm.always_reexplode"

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Still reexploding",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "max_reexplosions": 100,
                },
            },
            "fill": {"value": ""},
            "state": {"still": "pending"},
            "message": {
                "level": "info",
                "text": "again",
            },
        }

    register_datum_widget_v1(
        widget_name,
        widget,
        overwrite=True,
    )

    sid = _create_session(
        step_name="test.chainreactiontm.reexplode_cap.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.reexplode_cap",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Reexploding",
                    lifecycle={
                        "widget": widget_name,
                        "max_reexplosions": 100,
                    },
                )
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
            max_fills_on_a_span=2,
            max_fills_e2e=10,
        ),
    )

    with pytest.raises(FunkMaxFillsOnSpanExceeded):
        _dispatch_chain(sid)


def test_e2e_global_program_fill_cap() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.global_cap.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.global_cap",
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
            max_fills_e2e=1,
            max_fills_on_a_span=5,
        ),
    )

    with pytest.raises(FunkMaxFillsE2EExceeded):
        _dispatch_chain(sid)


def test_e2e_unanticipated_runtime_datum_role() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.unanticipated_role.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.unanticipated_role",
            datums=[
                _datum(
                    "G",
                    role="ghost",
                    title="Ghost datum",
                )
            ],
        ),
        session_metadata={
            "roles": {
                "maker": {
                    "label": "Maker",
                    "chainreactionTM_config": _role_chainreaction(
                        "title_semantic_v1"
                    ),
                },
            },
            "role_mismatch_policy": {
                "default": "redacted",
                "role_modes": {
                    "maker": "redacted",
                },
            },
            "chainreactionTM_config": {
                "version": "chainreaction1.0",
                "roles_ordered": ["maker"],
                "expect_all_roles_chainreactioned": False,
                "on_semantic_error": "retry_w_error_awareness",
                "max_semantic_errors_in_a_row": 2,
                "max_fills_on_a_span": 4,
                "max_fills_e2e": 8,
                "history_tail_cap": 4,
                "history_size_cap": 25_000,
            },
        },
    )

    with pytest.raises(FunkUnanticipatedDatumRoleRuntimeError):
        _dispatch_chain(sid)


def test_e2e_history_respects_read_roles_not_write_roles() -> None:
    _register_spy_version()

    sid = _create_session(
        step_name="test.chainreactiontm.history_read_roles.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.history_read_roles",
            datums=[
                _datum(
                    "R",
                    role="reviewer",
                    title="Reviewer datum",
                ),
                _datum(
                    "M",
                    role="maker",
                    title="Maker datum",
                ),
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "spy_capture_v1",
                {"text": "maker-spy-fill"},
            ),
            reviewer_chainreaction=_role_chainreaction(
                "title_semantic_v1"
            ),
            roles_ordered=["reviewer", "maker"],
            max_fills_e2e=8,
            history_tail_cap=4,
        ),
    )

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert SPY_REQUESTS

    req = SPY_REQUESTS[-1]
    assert [
        row["datum_id"]
        for row in req.pending_datums
    ] == ["M"]
    assert sorted(req.history["readable_roles"]) == [
        "maker",
        "reviewer",
    ]
    assert any(
        row.get("role") == "reviewer"
        and row.get("datum_id") == "R"
        for row in req.history.get("rows") or []
    )
    assert (
        _api().get_outputs(sid)["form_fills"]["M"]["value"]
        == "maker-spy-fill"
    )


def test_e2e_funk_request_events_tail_defaults_empty_and_can_be_enabled() -> None:
    _register_spy_version("spy_events_v1")

    sid = _create_session(
        step_name="test.chainreactiontm.events_tail.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.events_tail",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker datum",
                )
            ],
        ),
        session_metadata=_chain_metadata(
            maker_chainreaction=_role_chainreaction(
                "spy_events_v1"
            ),
            reviewer_chainreaction=None,
            roles_ordered=["maker", "reviewer"],
            events_queue_length=2,
        ),
    )

    packet = _dispatch_chain(sid)

    assert packet["event_kind"] == "ATCOMPLETION"
    assert SPY_REQUESTS

    request = SPY_REQUESTS[-1]
    assert len(request.events) == 2
    assert all(
        event.get("kind") == "controller_loop_event_v1"
        for event in request.events
    )

    end = request.events[-1]
    U = end["payload"]["U"]
    assert (
        U["role_mismatch_modulation_info"]["role_viewing"]
        == "maker"
    )

    raw = get_live_session_events(
        session_id=sid,
        role=None,
    )
    assert (
        raw[-1]["payload"]["U"].get(
            "role_mismatch_modulation_info"
        )
        is None
    )


def test_e2e_no_raw_ctx_leaks_from_chain_packet() -> None:
    sid = _create_session(
        step_name="test.chainreactiontm.no_raw_ctx_leak.step",
        multiframespec=_one_form_many_spans(
            app_form_id="chainreactiontm.no_raw_ctx_leak",
            datums=[
                _datum(
                    "M",
                    role="maker",
                    title="Maker text",
                )
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

    packet = _dispatch_chain(sid)

    assert "ctx_report" in packet
    assert "chainreactionTM_receipt" in packet
    _assert_no_forbidden_raw_keys(packet)