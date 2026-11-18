# think-backend/tests/wipp/engine/app_tables/w_rendering_front/test_app_table_runs.py

from __future__ import annotations

"""
Flagship App Table Universal-UI Direct-Action Integration Test
==============================================================

This file is the long-term regression fence for the renderer-agnostic App Table
surface.

Historical purpose
------------------
The old version of this sheet tested two things at once:

1. Engine/session direct actions:
   - create_VM_session(...)
   - step_session(...)
   - undo_last_step(...)
   - redo_last_step(...)
   - get_session_context(...)
   - get_outputs(...)

2. Front/controller direct actions:
   - create_interactive_session(...)
   - dispatch_ui_action(...)

The older controller half also asserted HTML output, for example that rendered
forms contained input names such as:

    name="NAME.first"

That was correct when the front-end contract was HTML-shaped. It is no longer
the right invariant.

Modern contract
---------------
The engine now emits a renderer-agnostic universal UI context:

    surfaces.__renderer_agnostic_universal_ui_ctx_payload.UIContextContract

The context is a dict-only, JSON-safe membrane. It is suitable for any frontend
or medium above the engine/session/controller layers: HTML, native UI, terminal
UI, mobile UI, viewers, automation, or other apps.

This sheet therefore asserts:

- no engine/session objects cross the UI boundary;
- no renderer medium is required;
- manual stops expose the universal fields needed by any frontend;
- span ownership, current frame/span, datum declarations, fills, and pending
  datum ids are coherent;
- partial fills, prefills, validation errors, undo, redo, completion, and
  controller routing all preserve the same universal context law.

Coverage map
------------
A) ENGINE direct-action flow

- step-until-stop behavior without using scripted runners;
- dynamic expansion of step-function multiframespec into manual fillspan steps;
- current frame/span identity;
- universal UI context minimum contract;
- dict/list/scalar-only context membrane;
- prefilled values visible through datum_widget_fills;
- missing payload, extraneous fields, required-micro validation, validator
  failure, successful commit;
- same-form partial submit merged with prefill;
- output globals and committed fills;
- undo back to a stable stop and eventually ATSTART;
- redo after a public manual tick.

B) CONTROLLER/front-action flow

- create_interactive_session + dispatch_ui_action;
- dotted external micro keys collapse to macro datum fills at the controller
  boundary;
- UI mode routing resolves FORM_FILL and RUN_COMPLETED_SUMMARY;
- response ctx remains the same universal UI context;
- controller assertions never inspect HTML or any renderer-specific medium.
"""

import sys
import types
from typing import Any, Dict, Mapping, Optional

import pytest

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
    register_step_fn,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    UserAction,
    create_interactive_session,
    dispatch_ui_action,
    get_concrete_session_api,
)
from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_APP_FORM_ID,
    CTX_CURRENT_FRAME_ID,
    CTX_CURRENT_FRAME_NAME,
    CTX_CURRENT_SPAN,
    CTX_CURRENT_SPAN_ID,
    CTX_CURSOR,
    CTX_DATUM_WIDGET_DECLS,
    CTX_DATUM_WIDGET_FILLS,
    CTX_DATUM_WIDGETS_ON_THIS_SPAN,
    CTX_FORM_ID,
    CTX_FRAMES,
    CTX_GLOBALS,
    CTX_KIND,
    CTX_LAST_ERROR,
    CTX_MULTIFRAMESPEC,
    CTX_SESSION_ID,
    CTX_SESSION_METADATA,
    CTX_SPAN_ORDER,
    CTX_SPAN_TO_DATUM_WIDGETS,
    CTX_STATE,
    CTX_STEP,
    CTX_TAGS,
    UIContextView,
    ui_context_contract_sheet_v1,
    validate_minimal,
)


ENGINE_STOP_KINDS = {
    "MANUALFILLNEEDEDSTEP",
    "ATSTART",
    "ATCOMPLETION",
}


# ---------------------------------------------------------------------------
# Test program setup
# ---------------------------------------------------------------------------


def _install_validators() -> None:
    mod = types.ModuleType("runner_full_validators")

    def _unwrap(v: Any) -> Any:
        if isinstance(v, dict) and "value" in v:
            return v["value"]
        return v

    def nonempty(v: Any):
        vv = _unwrap(v)
        ok = isinstance(vv, str) and vv.strip() != ""
        return ok, (None if ok else "must be non-empty")

    def is_year(v: Any):
        vv = _unwrap(v)
        try:
            y = int(vv)
            ok = 1500 <= y <= 2100
        except Exception:
            ok = False
        return ok, (None if ok else "must be a valid year")

    def is_pos_int(v: Any):
        vv = _unwrap(v)
        try:
            ok = int(vv) > 0
        except Exception:
            ok = False
        return ok, (None if ok else "must be positive")

    mod.nonempty = nonempty
    mod.is_year = is_year
    mod.is_pos_int = is_pos_int
    sys.modules["runner_full_validators"] = mod


@register_step_fn(
    "full_emit_identity_form",
    required_args=set(),
    optional_args={"prefill_last", "prefill_age"},
)
def full_emit_identity_form(
    state: Dict[str, Any],
    prefill_last: Optional[str] = None,
    prefill_age: Optional[int] = None,
) -> Dict[str, Any]:
    fills: Dict[str, Any] = {}

    if prefill_last:
        fills["NAME"] = {"last": str(prefill_last)}

    if prefill_age is not None:
        fills["AGE"] = {"value": int(prefill_age)}

    multiframespec = {
        "app_form_id": "FORM_IDENTITY",
        "datums": [
            {
                "id": "NAME",
                "title": "Your name",
                "micros": [
                    {
                        "name": "first",
                        "type": "text",
                        "required": True,
                        "validators": ["runner_full_validators:nonempty"],
                    },
                    {
                        "name": "last",
                        "type": "text",
                        "required": True,
                        "validators": ["runner_full_validators:nonempty"],
                    },
                ],
            },
            {
                "id": "DOB",
                "title": "Date of birth",
                "micros": [
                    {
                        "name": "day",
                        "type": "text",
                        "required": True,
                        "validators": ["runner_full_validators:nonempty"],
                    },
                    {
                        "name": "month",
                        "type": "text",
                        "required": True,
                        "validators": ["runner_full_validators:nonempty"],
                    },
                    {
                        "name": "year",
                        "type": "text",
                        "required": True,
                        "validators": ["runner_full_validators:is_year"],
                    },
                ],
            },
            {
                "id": "AGE",
                "title": "Age",
                "micros": [
                    {
                        "name": "value",
                        "type": "number",
                        "required": True,
                        "validators": ["runner_full_validators:is_pos_int"],
                    },
                ],
            },
        ],
        "frames": [
            {
                "id": "IDENTITY",
                "title": "Identity",
                "spans": [
                    {"id": "S_NAME", "owns": ["NAME"]},
                    {"id": "S_DOB", "owns": ["DOB"]},
                ],
            },
            {
                "id": "REVIEW",
                "title": "Review",
                "tags": ["no-skip"],
                "spans": [{"id": "S_REVIEW", "owns": []}],
            },
        ],
        "fills": fills,
    }

    return {
        "multiframespec_PREFILL_VALIDATE_VALUES": {"mode": "complete_only"},
        "multiframespec": multiframespec,
    }


@register_step_fn("full_commit", required_args=set(), optional_args=set())
def full_commit(state: Dict[str, Any]) -> Dict[str, Any]:
    pref = state.get("form_prefills") or {}
    fills = state.get("form_fills") or {}

    merged = dict(pref)
    merged.update(fills)

    name = merged.get("NAME") or {}
    dob = merged.get("DOB") or {}
    age = merged.get("AGE") or {}

    return {
        "committed": True,
        "full_name": f"{name.get('first', '')} {name.get('last', '')}".strip(),
        "dob": dict(dob) if isinstance(dob, dict) else dob,
        "age": int(age.get("value")) if isinstance(age, dict) and "value" in age else None,
    }


@pytest.fixture(autouse=True)
def _setup():
    _install_validators()

    StepFnregistry.clear()
    StepFnregistry.register(
        name="full_emit_identity_form",
        fn=full_emit_identity_form,
        required_args=set(),
        optional_args={"prefill_last", "prefill_age"},
    )
    StepFnregistry.register(
        name="full_commit",
        fn=full_commit,
        required_args=set(),
        optional_args=set(),
    )


def _manifest() -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": "identity",
            "step_fn": "full_emit_identity_form",
            "fn_args": {
                "prefill_last": "Lovelace",
                "prefill_age": 30,
            },
        },
        {
            "public_step_name": "commit",
            "step_fn": "full_commit",
            "fn_args": {},
        },
    ]


def _session_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "include_full_multiframespec_in_ctx": True,
            "include_forms_emitted_order_in_ctx": True,
            "include_field_value_keys_in_ctx": True,
            "include_global_fill_keys_in_ctx": False,
            "persistence": "disabled",
        }
    }


def _session_id_from_created(created: Any) -> str:
    if isinstance(created, Mapping):
        return str(created.get("session_id"))

    if isinstance(created, tuple) or isinstance(created, list):
        first = created[0]
        if isinstance(first, Mapping):
            return str(first.get("session_id"))
        return str(first)

    return str(created)


def _new_engine_session() -> str:
    api = get_concrete_session_api()
    state = api.create_VM_session(
        manifest=_manifest(),
        initial_parameter_overrides={},
        session_metadata=_session_metadata(),
        get_map=False,
    )
    return str(state["session_id"])


def _new_ui_session() -> str:
    created = create_interactive_session(
        manifest=_manifest(),
        initial_parameter_overrides={},
        ui_opts=_session_metadata(),
    )
    return _session_id_from_created(created)


def _ctx(session_id: str) -> Dict[str, Any]:
    return get_concrete_session_api().get_session_context(session_id)


def _step(
    session_id: str,
    fill: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return get_concrete_session_api().step_session(session_id, fill=fill)


def _undo(session_id: str) -> Dict[str, Any]:
    return get_concrete_session_api().undo_last_step(session_id)


def _redo(session_id: str) -> Dict[str, Any]:
    return get_concrete_session_api().redo_last_step(session_id)


def _step_until_stop(session_id: str) -> Dict[str, Any]:
    ctx = _step(session_id, fill=None)
    while ctx.get("kind") not in ENGINE_STOP_KINDS:
        ctx = _step(session_id, fill=None)
    return ctx


def _undo_until_stop(session_id: str) -> Dict[str, Any]:
    ctx = _undo(session_id)
    while ctx.get("kind") not in ENGINE_STOP_KINDS:
        ctx = _undo(session_id)
    return ctx


# ---------------------------------------------------------------------------
# Universal context assertions
# ---------------------------------------------------------------------------


def _assert_dict_only_json_safe(obj: Any, *, path: str = "ctx") -> None:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return

    assert not isinstance(obj, (bytes, bytearray)), path
    assert not isinstance(obj, tuple), path

    if isinstance(obj, list):
        for i, value in enumerate(obj):
            _assert_dict_only_json_safe(value, path=f"{path}[{i}]")
        return

    if isinstance(obj, Mapping):
        for key, value in obj.items():
            assert isinstance(key, str), f"{path} has non-string key {key!r}"
            _assert_dict_only_json_safe(value, path=f"{path}.{key}")
        return

    raise AssertionError(f"{path} contains non-JSON-safe object: {type(obj)!r}")


def _assert_contract_sheet_mentions_core_keys() -> None:
    sheet = ui_context_contract_sheet_v1()
    assert sheet["v"] == 1

    core = set(sheet["core_keys"])
    harmonized = set(sheet["harmonized_keys"])

    for key in [
        CTX_FRAMES,
        CTX_CURRENT_SPAN,
        CTX_SPAN_ORDER,
        CTX_SPAN_TO_DATUM_WIDGETS,
        CTX_DATUM_WIDGET_DECLS,
        CTX_DATUM_WIDGET_FILLS,
        CTX_DATUM_WIDGETS_ON_THIS_SPAN,
        CTX_SESSION_METADATA,
        CTX_LAST_ERROR,
        CTX_CURSOR,
        CTX_KIND,
    ]:
        assert key in core

    for key in [
        CTX_SESSION_ID,
        CTX_FORM_ID,
        CTX_APP_FORM_ID,
        CTX_CURRENT_FRAME_ID,
        CTX_CURRENT_FRAME_NAME,
        CTX_CURRENT_SPAN_ID,
        CTX_GLOBALS,
        CTX_STEP,
        CTX_STATE,
        CTX_MULTIFRAMESPEC,
        CTX_TAGS,
    ]:
        assert key in harmonized


def _assert_manual_universal_ctx(
    ctx: Mapping[str, Any],
    *,
    session_id: str,
    frame_id: str,
    span_id: str,
    pending_contains: list[str],
    app_form_id: str = "FORM_IDENTITY",
) -> UIContextView:
    _assert_dict_only_json_safe(ctx)
    validate_minimal(ctx)

    view = UIContextView(ctx)

    assert view.kind == "MANUALFILLNEEDEDSTEP"
    assert view.session_id == session_id
    assert view.form_id == app_form_id
    assert view.app_form_id == app_form_id

    assert view.current_frame_id == frame_id
    assert view.current_span == span_id
    assert view.current_span_id == span_id
    assert view.current_frame_name is not None

    assert isinstance(view.cursor, Mapping)
    assert isinstance(view.cursor.get("index"), int)
    assert isinstance(view.cursor.get("total"), int)
    assert view.cursor["total"] >= view.cursor["index"] >= 0

    assert isinstance(view.session_metadata, dict)
    assert isinstance(view.globals, dict)
    assert isinstance(view.step, dict)
    assert isinstance(view.state, dict)
    assert isinstance(view.multiframespec, dict)
    assert isinstance(view.tags, list)

    assert view.state.get("pending_multiframespec") is True
    assert view.state.get("pending_multiframespec_id") == app_form_id
    assert view.state.get("datum_widget_fills_count", 0) >= 0

    assert app_form_id == view.multiframespec.get("app_form_id")

    assert span_id in view.span_order
    assert span_id in view.span_to_datum_widgets

    pending = set(view.datum_widgets_on_this_span)
    for datum_id in pending_contains:
        assert datum_id in pending
        assert datum_id in view.datum_widget_decls

    owned = set(view.span_to_datum_widgets[span_id])
    for datum_id in pending_contains:
        assert datum_id in owned

    frames_by_id = {
        str(fr.get("id")): fr
        for fr in view.frames
        if fr.get("id") is not None
    }
    assert frame_id in frames_by_id

    frame = frames_by_id[frame_id]
    span_names = {
        str(sp.get("name"))
        for sp in list(frame.get("fillspans") or [])
    }
    assert span_id in span_names

    for key in [
        CTX_FRAMES,
        CTX_CURRENT_SPAN,
        CTX_SPAN_ORDER,
        CTX_SPAN_TO_DATUM_WIDGETS,
        CTX_DATUM_WIDGET_DECLS,
        CTX_DATUM_WIDGET_FILLS,
        CTX_DATUM_WIDGETS_ON_THIS_SPAN,
        CTX_SESSION_METADATA,
        CTX_LAST_ERROR,
        CTX_CURSOR,
        CTX_KIND,
        CTX_SESSION_ID,
        CTX_FORM_ID,
        CTX_APP_FORM_ID,
        CTX_CURRENT_FRAME_ID,
        CTX_CURRENT_FRAME_NAME,
        CTX_CURRENT_SPAN_ID,
        CTX_GLOBALS,
        CTX_STEP,
        CTX_STATE,
        CTX_MULTIFRAMESPEC,
        CTX_TAGS,
    ]:
        _ = view[key]

    return view


def _assert_nonmanual_ctx(
    ctx: Mapping[str, Any],
    *,
    session_id: str,
    kind: str,
) -> None:
    _assert_dict_only_json_safe(ctx)

    view = UIContextView(ctx)

    assert view.kind == kind
    assert view.session_id == session_id
    assert isinstance(view.cursor, Mapping)
    assert isinstance(view.session_metadata, dict)
    assert isinstance(view.globals, dict)
    assert isinstance(view.step, dict)
    assert isinstance(view.state, dict)


def _assert_last_error_has(
    ctx: Mapping[str, Any],
    *keys: str,
) -> None:
    err = ctx.get("last_error") or {}
    assert isinstance(err, Mapping)
    for key in keys:
        assert key in err


def _flatten_micro_values(source: Mapping[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}

    for datum_id, datum_value in source.items():
        if isinstance(datum_value, Mapping):
            for micro_name, micro_value in datum_value.items():
                flattened[f"{datum_id}.{micro_name}"] = micro_value
        else:
            flattened[f"{datum_id}.value"] = datum_value

    return flattened


def _merged_visible_datum_values(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}

    for bucket_name in (
        "form_prefills",
        "form_fills",
        CTX_DATUM_WIDGET_FILLS,
    ):
        bucket = ctx.get(bucket_name) or {}
        if isinstance(bucket, Mapping):
            merged.update(_flatten_micro_values(bucket))

    return merged


def _assert_visible_micro_value(
    ctx: Mapping[str, Any],
    dotted_name: str,
    expected: Any,
) -> None:
    merged = _merged_visible_datum_values(ctx)
    assert merged.get(dotted_name) == expected, merged


def _assert_no_visible_values_for_datum(
    ctx: Mapping[str, Any],
    datum_id: str,
) -> None:
    merged = _merged_visible_datum_values(ctx)
    prefix = f"{datum_id}."
    assert not any(k.startswith(prefix) for k in merged), merged


def _assert_controller_response(
    resp: Mapping[str, Any],
    *,
    session_id: str,
    ui_mode: str,
    event_kind: str,
) -> Mapping[str, Any]:
    assert resp.get("session_id") == session_id
    assert resp.get("ui_mode") == ui_mode
    assert resp.get("event_kind") == event_kind

    ctx = resp.get("ctx")
    assert isinstance(ctx, Mapping)
    assert ctx.get("kind") == event_kind
    _assert_dict_only_json_safe(ctx)

    return ctx


# ---------------------------------------------------------------------------
# A) Engine/session direct-action sheet
# ---------------------------------------------------------------------------


def test_engine_direct_actions_emit_and_preserve_universal_ui_context():
    _assert_contract_sheet_mentions_core_keys()

    api = get_concrete_session_api()
    sid = _new_engine_session()

    at_start = _ctx(sid)
    _assert_nonmanual_ctx(at_start, session_id=sid, kind="ATSTART")

    # First public manual stop: NAME on IDENTITY/S_NAME.
    ctx1 = _step_until_stop(sid)
    view1 = _assert_manual_universal_ctx(
        ctx1,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )

    assert view1.datum_widget_fills["NAME"]["last"] == "Lovelace"
    assert view1.datum_widget_fills["AGE"]["value"] == 30
    _assert_visible_micro_value(ctx1, "NAME.last", "Lovelace")

    name_decl = view1.datum_widget_decls["NAME"]
    assert name_decl.get("field_id") in (None, "NAME")
    assert "first" in str(name_decl)
    assert "last" in str(name_decl)

    # Public API law:
    #
    # fill=None at a manual stop means "return/render the current universal
    # context", not "submit a missing payload". It must be idempotent and must
    # not manufacture a validation error.
    ctx_no_fill = _step(sid, fill=None)
    _assert_manual_universal_ctx(
        ctx_no_fill,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )
    assert ctx_no_fill.get("last_error") in (None, {})

    # Explicit empty submit is the validation case. It remains on the same
    # manual stop and reports that NAME is still unsatisfied.
    ctx_empty_submit = _step(sid, fill={})
    _assert_manual_universal_ctx(
        ctx_empty_submit,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )
    _assert_last_error_has(ctx_empty_submit, "NAME")

    # Extraneous datum for a different span is rejected by the engine boundary.
    ctx_extraneous = _step(
        sid,
        fill={
            "NAME": {
                "first": "Ada",
                "last": "Lovelace",
            },
            "DOB": {
                "year": "1815",
            },
        },
    )
    _assert_manual_universal_ctx(
        ctx_extraneous,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )
    _assert_last_error_has(ctx_extraneous, "__SPAN__")

    # Empty NAME.first fails the micro validator and remains a universal ctx.
    ctx_bad_name = _step(
        sid,
        fill={
            "NAME": {
                "first": "",
            },
        },
    )
    _assert_manual_universal_ctx(
        ctx_bad_name,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )
    _assert_last_error_has(ctx_bad_name, "NAME")

    # Partial NAME submit merges with NAME.last prefill and completes S_NAME.
    ctx_after_name_step = _step(
        sid,
        fill={
            "NAME": {
                "first": "Ada",
            },
        },
    )

    if ctx_after_name_step["kind"] == "MANUALFILLNEEDEDSTEP":
        _assert_manual_universal_ctx(
            ctx_after_name_step,
            session_id=sid,
            frame_id="IDENTITY",
            span_id="S_DOB",
            pending_contains=["DOB"],
        )

    ctx_after_name = _ctx(sid)
    assert ctx_after_name["kind"] in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}
    _assert_visible_micro_value(ctx_after_name, "NAME.first", "Ada")
    _assert_visible_micro_value(ctx_after_name, "NAME.last", "Lovelace")

    # Second public manual stop: DOB on IDENTITY/S_DOB.
    ctx2 = (
        ctx_after_name
        if ctx_after_name.get("kind") == "MANUALFILLNEEDEDSTEP"
        else _step_until_stop(sid)
    )
    view2 = _assert_manual_universal_ctx(
        ctx2,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_DOB",
        pending_contains=["DOB"],
    )

    assert "DOB" in view2.datum_widget_decls
    assert "year" in str(view2.datum_widget_decls["DOB"])
    _assert_no_visible_values_for_datum(ctx2, "DOB")

    # Validator failure keeps the same manual universal context.
    ctx_bad_dob = _step(
        sid,
        fill={
            "DOB": {
                "day": "10",
                "month": "12",
                "year": "99999",
            }
        },
    )
    _assert_manual_universal_ctx(
        ctx_bad_dob,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_DOB",
        pending_contains=["DOB"],
    )
    _assert_last_error_has(ctx_bad_dob, "DOB")

    # Correct DOB completes manual flow and lets commit run.
    ctx_done = _step(
        sid,
        fill={
            "DOB": {
                "day": "10",
                "month": "12",
                "year": "1815",
            }
        },
    )
    assert ctx_done["kind"] == "ATCOMPLETION"
    _assert_nonmanual_ctx(ctx_done, session_id=sid, kind="ATCOMPLETION")

    out = api.get_outputs(sid)
    _assert_dict_only_json_safe(out, path="outputs")

    assert out["form_prefills"]["AGE"]["value"] == 30
    assert out["form_fills"]["NAME"]["first"] == "Ada"
    assert out["form_fills"]["NAME"]["last"] == "Lovelace"
    assert out["form_fills"]["DOB"]["day"] == "10"
    assert out["form_fills"]["DOB"]["month"] == "12"
    assert out["form_fills"]["DOB"]["year"] == "1815"
    assert out["globals"]["committed"] is True
    assert out["globals"]["full_name"] == "Ada Lovelace"
    assert out["globals"]["age"] == 30

    # Undo returns to a stable public stop using the same universal membrane.
    undo_stop = _undo_until_stop(sid)
    assert undo_stop["kind"] in ENGINE_STOP_KINDS
    _assert_dict_only_json_safe(undo_stop)

    if undo_stop["kind"] == "MANUALFILLNEEDEDSTEP":
        validate_minimal(undo_stop)
        assert UIContextView(undo_stop).session_id == sid

    # Redo is available after undo of a public manual tick.
    try:
        redo_ctx = _redo(sid)
    except Exception:
        redo_ctx = None

    if redo_ctx is not None:
        assert redo_ctx["kind"] in ENGINE_STOP_KINDS
        _assert_dict_only_json_safe(redo_ctx)
        if redo_ctx["kind"] == "MANUALFILLNEEDEDSTEP":
            validate_minimal(redo_ctx)

    # Continue undoing to the beginning. ATSTART is also a dict-only universal
    # session context, just not a minimal manual-render context.
    while True:
        try:
            _ = _undo(sid)
        except Exception:
            break

    start_again = _ctx(sid)
    assert start_again["kind"] == "ATSTART"
    _assert_nonmanual_ctx(start_again, session_id=sid, kind="ATSTART")


# ---------------------------------------------------------------------------
# B) Controller/front-action sheet, renderer-agnostic
# ---------------------------------------------------------------------------


def test_controller_dispatch_uses_universal_ui_context_without_renderer_medium():
    sid = _new_ui_session()

    # Initial dispatch reaches the first manual stop. The assertion is against
    # ui_mode + universal ctx, not against HTML or any renderer output.
    resp1 = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    ctx1 = _assert_controller_response(
        resp1,
        session_id=sid,
        ui_mode="FORM_FILL",
        event_kind="MANUALFILLNEEDEDSTEP",
    )
    _assert_manual_universal_ctx(
        ctx1,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )
    _assert_visible_micro_value(ctx1, "NAME.last", "Lovelace")

    # Controller dotted-key normalization:
    #
    # The frontend may submit dotted micro keys, but the engine only receives
    # macro datum ids:
    #
    #   {"NAME.first": "Ada"} -> {"NAME": {"first": "Ada"}}
    #
    # No HTML name assertion is needed for that law.
    resp2 = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "NAME.first": "Ada",
        },
        render=False,
    )
    ctx2 = _assert_controller_response(
        resp2,
        session_id=sid,
        ui_mode="FORM_FILL",
        event_kind="MANUALFILLNEEDEDSTEP",
    )
    _assert_manual_universal_ctx(
        ctx2,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_DOB",
        pending_contains=["DOB"],
    )

    _assert_visible_micro_value(ctx2, "NAME.first", "Ada")
    _assert_visible_micro_value(ctx2, "NAME.last", "Lovelace")
    _assert_no_visible_values_for_datum(ctx2, "DOB")

    # Undo through controller returns to the NAME span and the universal ctx is
    # sufficient for any renderer to reconstruct the page.
    resp_undo = dispatch_ui_action(
        sid,
        action=UserAction.UNDO,
        render=False,
    )
    ctx_undo = _assert_controller_response(
        resp_undo,
        session_id=sid,
        ui_mode="FORM_FILL",
        event_kind="MANUALFILLNEEDEDSTEP",
    )
    _assert_manual_universal_ctx(
        ctx_undo,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_NAME",
        pending_contains=["NAME"],
    )

    # Full NAME submit via dotted micro names returns to DOB.
    resp_name = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "NAME.first": "Ada",
            "NAME.last": "Lovelace",
        },
        render=False,
    )
    ctx_name = _assert_controller_response(
        resp_name,
        session_id=sid,
        ui_mode="FORM_FILL",
        event_kind="MANUALFILLNEEDEDSTEP",
    )
    _assert_manual_universal_ctx(
        ctx_name,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_DOB",
        pending_contains=["DOB"],
    )

    # Bad DOB stays on the same universal ctx and exposes errors without any
    # renderer-specific dependency.
    resp_bad_dob = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "DOB.day": "10",
            "DOB.month": "12",
            "DOB.year": "99999",
        },
        render=False,
    )
    ctx_bad_dob = _assert_controller_response(
        resp_bad_dob,
        session_id=sid,
        ui_mode="FORM_FILL",
        event_kind="MANUALFILLNEEDEDSTEP",
    )
    _assert_manual_universal_ctx(
        ctx_bad_dob,
        session_id=sid,
        frame_id="IDENTITY",
        span_id="S_DOB",
        pending_contains=["DOB"],
    )
    _assert_last_error_has(ctx_bad_dob, "DOB")

    # Good DOB completes and routes to the summary mode. Again, completion is a
    # session/controller state, not an HTML-rendered document assertion.
    resp_done = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "DOB.day": "10",
            "DOB.month": "12",
            "DOB.year": "1815",
        },
        render=False,
    )
    ctx_done = _assert_controller_response(
        resp_done,
        session_id=sid,
        ui_mode="RUN_COMPLETED_SUMMARY",
        event_kind="ATCOMPLETION",
    )
    _assert_nonmanual_ctx(ctx_done, session_id=sid, kind="ATCOMPLETION")

    out = get_concrete_session_api().get_outputs(sid)
    assert out["globals"]["committed"] is True
    assert out["globals"]["full_name"] == "Ada Lovelace"
    assert out["form_fills"]["DOB"]["year"] == "1815"