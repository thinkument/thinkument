from __future__ import annotations

"""
Universal U / F Human Input Loop E2E Sheet
==========================================

Target project path:
    think-backend/tests/unit/sessions/
        test_run_from_here__UFU_formalism_of_core_and_higher_thinkprograms.py

This file is intentionally a single executable sheet.

It proves the shared human-input-loop state machine at two levels:

    PART A. App-table / exploding-datum level
        step function -> multiframespec -> span product vector -> Uprev
        Uprev -> F(fill/signal) -> Unext
        exercised through:
            - roleless raw session API
            - live controller action packet
            - offline scripted runner

    PART B. ThinkProgramTM / ThinkWidgetTM level
        think_program_v1 JSON -> kernel program -> app-table manifest
        -> span product vector of ThinkWidgetTM widgets -> Uprev
        Uprev -> F(fill/signal) -> Unext
        exercised through:
            - live controller action packet
            - offline scripted runner
            - role-modulated controller read/write filtering

The sheet does not try to enumerate infinitely many concrete strings or numbers.
It enumerates the finite equivalence classes that determine the universal UI
context family U and the next action family F.

This sheet proves U/F transition semantics. Controller start/end envelope
assembly and frontend event projection are proved by the adjacent
test_run_from_here__session_events_queue_heard_to_fronstate.py sheet.

Universal context family U
--------------------------
Every public context in this sheet is asserted to be in the same renderer-
agnostic family:

    U = {
        frames,
        current_span,
        span_order,
        span_to_datum_widgets,
        datum_widget_decls,
        datum_widget_fills,
        datum_widgets_on_this_span,
        session_metadata,
        last_error,
        cursor,
        kind,
        session_id,
        form_id/app_form_id,
        current_frame_id/current_frame_name/current_span_id,
        globals,
        step,
        state,
        multiframespec,
        tags,
    }

For manual stops, U is validated through:

    _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload.validate_minimal
    UIContextView

Fill/signal space F
-------------------
For a manual U, the legal next sparse action space is:

    F | U = {
        fill:   partial mapping from pending datum ids to current micro names,
        signal: optional one datum-targeted signal whose target is pending,
    }

This sheet asserts both:

    1. U -> F can be read from datum_widget_decls + datum_widget_fills
       + datum_widgets_on_this_span.

    2. F + Uprev produces only another U in the same universal ctx family:
       same span with last_error, same span with reexploded declarations,
       next span, role-filtered U, or ATCOMPLETION.

Equivalence classes covered
---------------------------
The matrix below is executable documentation for what this file covers.
If a new class of U or F is added to the engine/controller contract, add it here
first, then add a row/assertion in the relevant tests.
"""

import copy
import json
from typing import Any, Dict, Iterable, Mapping, Optional

import pytest

# Importing the table has registration side effects for MICRO_TYPES.
import _thinkprogram._iomicrosTM.table_micros  # noqa: F401

from __datomatonTM import register_datum_widget_v1

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    UserAction,
    dispatch_ui_action,
    get_concrete_session_api,
    get_current_ui_state,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
)
from _thinksessions.run.runme_surfaces_in.controller_apis_action_packet import (
    CONTROLLER_ACTION_PACKET_KIND_V1,
    CONTROLLER_DATUM_SIGNAL_KIND_V1,
    normalize_controller_action_packet_v1,
    normalize_controller_datum_signal_v1,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    SESSION_EVENT_KIND_V1,
    build_session_event,
    session_event_packet_shape_v1,
)
from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    UIContextView,
    ui_context_contract_sheet_v1,
    validate_minimal,
)

from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
    validate_kernel_program_v1,
)
from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    DatumLifecycleWidget,
    Reexplode,
    signal_catcher,
    thinkwidgetTM_config,
)
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    lower_think_program_to_kernel_program_v1,
    lower_think_program_v1,
    register_think_program_language_v1,
)
from _thinksessions.run.run_from_here import (
    get_live_session_events,
    get_live_session_latest_event_seq,
)

from ._fixtures_facade_run import assert_strict_canonical_event_order_v1


# =============================================================================
# Executable documentation matrix
# =============================================================================

U_SPACE_EQUIVALENCE_CLASSES = [
    {
        "u_class": "manual.source_shell",
        "meaning": "Initial public manual U after mount explosions create visible micros.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.same_shell_error",
        "meaning": "Bad F leaves caller on same manual span with last_error.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.reexploded_confirm_shell",
        "meaning": "Good first-phase F causes datum output Reexplode(confirm), so next F changes.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.reexploded_signal_shell",
        "meaning": "Signal-only F causes targeted datum to reexplode to signal-specific micros.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.reexploded_signal_plus_fill_shell",
        "meaning": "One F packet carrying fill+signal branches differently than the same fill alone.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.next_program_span",
        "meaning": "Authoritative satisfaction advances to the next span/flow item.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "manual.role_modulated_projection",
        "meaning": "Role-aware facade returns a filtered U projection and narrows F.",
        "expected_kind": "MANUALFILLNEEDEDSTEP",
    },
    {
        "u_class": "terminal.completion",
        "meaning": "All authoritative spans are satisfied; U is an ATCOMPLETION ctx.",
        "expected_kind": "ATCOMPLETION",
    },
]

F_SPACE_EQUIVALENCE_CLASSES = [
    {
        "f_class": "empty_step_to_first_stop",
        "shape": {"fill": {}, "signal": None},
        "meaning": "Controller/raw stepping with no submitted fill reaches the first manual U.",
    },
    {
        "f_class": "good_sparse_macro_fill",
        "shape": {"fill": {"D": {"micro": "value"}}, "signal": None},
        "meaning": "A valid datum-addressed macro fill advances or reexplodes.",
    },
    {
        "f_class": "good_dotted_controller_fill",
        "shape": {"fill": {"D.micro": "value"}, "signal": None},
        "meaning": "Controller dotted keys collapse into macro datum fills before the engine.",
    },
    {
        "f_class": "semantic_block",
        "shape": {"fill": {"D": {"micro": "blocked-value"}}, "signal": None},
        "meaning": "Widget-level semantic rejection yields same U with last_error.",
    },
    {
        "f_class": "validator_reject",
        "shape": {"fill": {"D": {"email": "not-an-email"}}, "signal": None},
        "meaning": "Micro validators reject before durable commit; same U with last_error.",
    },
    {
        "f_class": "stale_or_non_current_datum",
        "shape": {"fill": {"old_D": {"micro": "value"}}, "signal": None},
        "meaning": "After a datum leaves Pending(S,t), attempts to fill it are invalid.",
    },
    {
        "f_class": "signal_only",
        "shape": {
            "fill": {},
            "signal": {"datum_id": "D", "kind": "refresh", "info": {}},
        },
        "meaning": "A lifecycle datum may be evaluated from signal alone.",
    },
    {
        "f_class": "signal_plus_fill",
        "shape": {
            "fill": {"D": {"micro": "value"}},
            "signal": {"datum_id": "D", "kind": "refresh_and_fill"},
        },
        "meaning": "Fill and targeted signal travel together as one controller action packet.",
    },
    {
        "f_class": "role_forbidden_fill",
        "shape": {"fill": {"mismatched_D": {"micro": "value"}}, "signal": None},
        "meaning": "Role-aware facade rejects mismatched submissions before roleless backend mutation.",
    },
]


# =============================================================================
# Generic helpers: U validation and F extraction
# =============================================================================


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _json_roundtripable(obj: Any) -> None:
    json.dumps(obj, sort_keys=True, default=str)


def _text_micro(
    name: str,
    *,
    required: bool = True,
    min_words: int | None = None,
) -> Dict[str, Any]:
    micro: Dict[str, Any] = {
        "name": name,
        "type": "text",
        "required": required,
    }
    if min_words is not None:
        micro["validators"] = [
            {
                "path": "_thinkprogram._iomicrosTM.validators.text:min_words",
                "args": {"min_words": int(min_words)},
            }
        ]
    return micro


def _email_micro(name: str, *, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "email",
        "required": required,
        "validators": [
            "_thinkprogram._iomicrosTM.validators.email:is_basic_email"
        ],
    }


def _bounded_number_micro(
    name: str,
    *,
    required: bool = True,
    minimum: int = 1,
    maximum: int = 10,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "number",
        "required": required,
        "validators": [
            "_thinkprogram._iomicrosTM.validators.number:is_positive_int",
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                "args": {"min_value": int(minimum)},
            },
            {
                "path": "_thinkprogram._iomicrosTM.validators.number:max_number",
                "args": {"max_value": int(maximum)},
            },
        ],
    }


def _select_micro(
    name: str,
    *,
    required: bool = True,
    options: list[str],
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "select",
        "required": required,
        "validators": [
            {
                "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
                "args": {"options": list(options)},
            }
        ],
    }


def _decl_micro_names(decl: Mapping[str, Any] | Any) -> list[str]:
    if not isinstance(decl, Mapping):
        return []

    raw = decl.get("micros") or decl.get("micro_names") or []
    out: list[str] = []

    if isinstance(raw, Mapping):
        raw_iter: Iterable[Any] = raw.values()
    elif isinstance(raw, list):
        raw_iter = raw
    else:
        raw_iter = []

    for row in raw_iter:
        if isinstance(row, Mapping):
            name = row.get("name") or row.get("field") or row.get("id")
            if name is not None:
                out.append(str(name))
        elif isinstance(row, str):
            out.append(row)

    # Some UI decls expose a parallel micro_names list even if micros is rich.
    raw_names = decl.get("micro_names")
    if isinstance(raw_names, list):
        for name in raw_names:
            if str(name) not in out:
                out.append(str(name))

    return out


def _ctx_signature(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    decls = ctx.get("datum_widget_decls") or {}
    return {
        "kind": ctx.get("kind"),
        "current_span": ctx.get("current_span") or ctx.get("current_span_id"),
        "pending": list(ctx.get("datum_widgets_on_this_span") or []),
        "decl_micros": {
            str(datum_id): _decl_micro_names(decl)
            for datum_id, decl in dict(decls).items()
        }
        if isinstance(decls, Mapping)
        else {},
        "has_error": bool(ctx.get("last_error")),
    }


def _assert_is_U(
    ctx: Mapping[str, Any],
    *,
    manual: bool = True,
) -> UIContextView:
    assert isinstance(ctx, Mapping)
    _json_roundtripable(ctx)

    view = UIContextView(ctx)
    assert view.kind == ctx.get("kind")

    if manual:
        assert ctx.get("kind") == "MANUALFILLNEEDEDSTEP", _ctx_signature(ctx)
        validate_minimal(ctx)
        assert (
            view.current_span_id == ctx.get("current_span")
            or view.current_span_id == ctx.get("current_span_id")
        )
        assert isinstance(view.datum_widget_decls, dict)
        assert isinstance(view.datum_widget_fills, dict)
        assert isinstance(view.datum_widgets_on_this_span, list)
        assert set(view.datum_widgets_on_this_span).issubset(
            set(view.datum_widget_decls)
        )

    return view


def _assert_completion_U(ctx: Mapping[str, Any]) -> None:
    assert isinstance(ctx, Mapping)
    _json_roundtripable(ctx)
    assert ctx.get("kind") in {
        "ATCOMPLETION",
        "ATCOMPLETE",
    }, _ctx_signature(ctx)


def _fill_space_from_U(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Compute the caller-facing sparse F family from a manual U.

    This is not a full validator. It is the public contract projection:
    pending datum ids and each current declaration's micro names define the
    legal target grammar for the next controller/raw/offline action packet.
    """
    view = _assert_is_U(ctx, manual=True)
    pending = list(view.datum_widgets_on_this_span)

    return {
        "kind": "F_space_from_U_v1",
        "current_span": view.current_span_id,
        "pending_datums": pending,
        "macro_fill_keys": {
            datum_id: _decl_micro_names(
                view.datum_widget_decls.get(datum_id) or {}
            )
            for datum_id in pending
        },
        "dotted_controller_keys": [
            f"{datum_id}.{micro}"
            for datum_id in pending
            for micro in _decl_micro_names(
                view.datum_widget_decls.get(datum_id) or {}
            )
        ],
        "signal_targets": list(pending),
        "signal_cardinality": "zero_or_one",
    }


def _assert_F_mentions(
    ctx: Mapping[str, Any],
    datum_id: str,
    *micros: str,
) -> None:
    f_space = _fill_space_from_U(ctx)
    assert datum_id in f_space["pending_datums"], f_space
    for micro in micros:
        assert micro in f_space["macro_fill_keys"].get(datum_id, []), f_space


def _assert_error_same_U_family(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    _assert_is_U(after, manual=True)
    assert after.get("current_span") == before.get("current_span")
    assert after.get("datum_widgets_on_this_span") == before.get(
        "datum_widgets_on_this_span"
    )
    assert after.get("last_error"), _ctx_signature(after)


def _assert_decl_mentions(
    ctx: Mapping[str, Any],
    datum_id: str,
    *needles: str,
) -> None:
    decl = dict((ctx.get("datum_widget_decls") or {}).get(datum_id) or {})
    rendered = json.dumps(decl, sort_keys=True, default=str)
    for needle in needles:
        assert needle in rendered, (datum_id, needle, rendered)


# =============================================================================
# PART A: app-table / exploding-datum surface
# =============================================================================

APP_TABLE_WIDGET = "test.ufspace.app_table_probe.v1"
APP_TABLE_STEP = "test.ufspace.app_table_probe.step"
APP_TABLE_FORM = "ufspace.app_table.form"


def _register_app_table_probe_widget(
    widget_name: str = APP_TABLE_WIDGET,
) -> None:
    """
    Raw datum lifecycle widget used by the app-table half.

    Output classes intentionally cover:
        mount -> reexplode source shell
        semantic blocked -> same U + last_error
        fill -> reexplode confirm shell
        refresh signal -> reexplode signal_value shell
        refresh_and_fill signal -> reexplode signal_confirm shell
        confirm/signal_confirm/signal_value -> done
        revise -> reexplode source shell again
    """

    def _base_lifecycle(datum: Mapping[str, Any]) -> Dict[str, Any]:
        lifecycle = dict(datum.get("lifecycle") or {})
        lifecycle["widget"] = widget_name
        lifecycle["mount_explode"] = True
        lifecycle["max_reexplosions"] = 20
        lifecycle["max_messages"] = 8
        lifecycle["max_proc_notes"] = 8
        return lifecycle

    def _source_shell(datum: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(datum),
            "title": "Probe source shell",
            "micros": [
                _text_micro("value", required=True),
                _select_micro(
                    "route",
                    required=True,
                    options=["ordinary", "revise"],
                ),
            ],
            "lifecycle": _base_lifecycle(datum),
        }

    def _confirm_shell(datum: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(datum),
            "title": "Probe confirm shell",
            "micros": [
                _select_micro(
                    "confirm",
                    required=True,
                    options=["yes", "revise"],
                ),
            ],
            "lifecycle": _base_lifecycle(datum),
        }

    def _signal_value_shell(datum: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(datum),
            "title": "Probe signal-only shell",
            "micros": [_text_micro("signal_value", required=True)],
            "lifecycle": _base_lifecycle(datum),
        }

    def _signal_confirm_shell(datum: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(datum),
            "title": "Probe signal+fill shell",
            "micros": [_text_micro("signal_confirm", required=True)],
            "lifecycle": _base_lifecycle(datum),
        }

    def _next_state(
        q: Mapping[str, Any],
        *,
        branch: str,
        extra: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        previous = dict(q.get("state") or {})
        signal = dict(q.get("signal") or {})
        partial = dict(q.get("partial_fill") or {})
        info = dict(signal.get("info") or {})
        trail = list(previous.get("trail") or [])
        trail.append(
            {
                "branch": branch,
                "signal_kind": str(
                    signal.get("kind") or q.get("signal_kind") or ""
                ),
                "partial_keys": sorted(str(k) for k in partial),
                "info": info,
            }
        )
        state = {
            "branch": branch,
            "trail": trail,
            "last_signal_kind": str(
                signal.get("kind") or q.get("signal_kind") or ""
            ),
            "last_partial": partial,
            "last_info": info,
        }
        if extra:
            state.update(dict(extra))
        return state

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        signal = dict(q.get("signal") or {})
        signal_kind = str(
            signal.get("kind") or q.get("signal_kind") or "fill"
        )
        partial = dict(q.get("partial_fill") or {})
        info = dict(signal.get("info") or {})

        if signal_kind == "mount":
            span_id = str(info.get("span_id") or q.get("span_id") or "")
            return {
                "status": "reexplode",
                "datum": _source_shell(datum),
                "fill": {"value": "", "route": "ordinary"},
                "prefill": {"value": "alpha", "route": "ordinary"},
                "state": _next_state(
                    q,
                    branch="mount_to_source",
                    extra={"mounted_span": span_id},
                ),
                "message": {
                    "level": "info",
                    "text": "mounted source shell",
                },
                "proc_notes": {"u_class": "manual.source_shell"},
            }

        if signal_kind == "refresh":
            return {
                "status": "reexplode",
                "datum": _signal_value_shell(datum),
                "fill": {"signal_value": ""},
                "prefill": {
                    "signal_value": str(
                        info.get("suggested") or "from-signal"
                    )
                },
                "state": _next_state(
                    q,
                    branch="signal_only_to_signal_value",
                ),
                "message": {
                    "level": "info",
                    "text": "signal-only shell",
                },
                "proc_notes": {
                    "u_class": "manual.reexploded_signal_shell"
                },
            }

        if signal_kind == "refresh_and_fill":
            return {
                "status": "reexplode",
                "datum": _signal_confirm_shell(datum),
                "fill": {"signal_confirm": ""},
                "prefill": {
                    "signal_confirm": str(
                        partial.get("value") or "confirm"
                    )
                },
                "state": _next_state(
                    q,
                    branch="signal_plus_fill_to_signal_confirm",
                    extra={
                        "accepted_fill_during_signal": partial.get("value")
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "signal+fill shell",
                },
                "proc_notes": {
                    "u_class": "manual.reexploded_signal_plus_fill_shell"
                },
            }

        if "value" in partial:
            value = str(partial.get("value") or "")
            if value == "block":
                return {
                    "status": "blocked",
                    "state": _next_state(
                        q,
                        branch="blocked_semantic_value",
                    ),
                    "message": {
                        "level": "error",
                        "text": "semantic block requested",
                    },
                }
            return {
                "status": "reexplode",
                "datum": _confirm_shell(datum),
                "fill": {"confirm": ""},
                "prefill": {"confirm": "yes"},
                "state": _next_state(
                    q,
                    branch="ordinary_value_to_confirm",
                    extra={
                        "accepted_value": value,
                        "accepted_route": partial.get("route"),
                    },
                ),
                "message": {
                    "level": "info",
                    "text": "ordinary confirm shell",
                },
                "proc_notes": {
                    "u_class": "manual.reexploded_confirm_shell"
                },
            }

        if "confirm" in partial:
            if partial.get("confirm") == "revise":
                return {
                    "status": "reexplode",
                    "datum": _source_shell(datum),
                    "fill": {"value": "", "route": "revise"},
                    "prefill": {
                        "value": "revise",
                        "route": "revise",
                    },
                    "state": _next_state(
                        q,
                        branch="confirm_revise_to_source",
                    ),
                    "message": {
                        "level": "warning",
                        "text": "revision requested",
                    },
                }
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="ordinary_confirm_done",
                    extra={"final_value": partial.get("confirm")},
                ),
                "message": {
                    "level": "success",
                    "text": "ordinary done",
                },
            }

        if "signal_value" in partial:
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="signal_value_done",
                    extra={"final_value": partial.get("signal_value")},
                ),
                "message": {
                    "level": "success",
                    "text": "signal-only done",
                },
            }

        if "signal_confirm" in partial:
            return {
                "status": "done",
                "state": _next_state(
                    q,
                    branch="signal_confirm_done",
                    extra={"final_value": partial.get("signal_confirm")},
                ),
                "message": {
                    "level": "success",
                    "text": "signal+fill done",
                },
            }

        return {
            "status": "blocked",
            "state": _next_state(
                q,
                branch="blocked_unknown_surface",
            ),
            "message": {
                "level": "error",
                "text": "unknown app-table probe surface",
            },
        }

    register_datum_widget_v1(
        widget_name,
        widget,
        overwrite=True,
    )


def _app_table_multiframespec(
    widget_name: str = APP_TABLE_WIDGET,
    app_form_id: str = APP_TABLE_FORM,
) -> Dict[str, Any]:
    return {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": "A",
                "title": "Plain A",
                "micros": [_text_micro("value")],
            },
            {
                "id": "Q",
                "title": "Lifecycle Q",
                "micros": [],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 8,
                },
            },
            {
                "id": "B",
                "title": "Plain B",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "frame",
                "spans": [
                    {
                        "id": "span",
                        "owns": ["A", "Q", "B"],
                    }
                ],
            }
        ],
    }


def _register_app_table_step(
    step_name: str = APP_TABLE_STEP,
    widget_name: str = APP_TABLE_WIDGET,
) -> None:
    _register_app_table_probe_widget(widget_name)

    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "multiframespec": _app_table_multiframespec(
                widget_name=widget_name
            )
        }

    StepFnregistry.register(
        name=step_name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _app_table_manifest(
    step_name: str = APP_TABLE_STEP,
) -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": "ufspace_app_table",
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


def _create_app_table_session() -> str:
    _register_app_table_step()
    created = _api().create_VM_session(
        manifest=_app_table_manifest(),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "test": "ufspace_app_table",
        },
    )
    return str(dict(created)["session_id"])


def _app_state_for(
    api: Any,
    sid: str,
    datum_id: str = "Q",
) -> Mapping[str, Any]:
    row = (
        api._get(sid)
        .state["_datum_lifecycle_v1"]
        .get("forms", {})
        .get(APP_TABLE_FORM, {})
        .get("datums", {})
        .get(datum_id, {})
    )
    assert isinstance(row, Mapping) and row
    return dict(row.get("state") or {})


# =============================================================================
# PART A tests
# =============================================================================


def test_file_header_matrix_and_public_packet_surfaces_are_dead_json_contracts() -> None:
    """
    The matrix at the top of this file is itself part of the test sheet.
    It declares the finite U/F equivalence classes this E2E covers.
    """
    _json_roundtripable(U_SPACE_EQUIVALENCE_CLASSES)
    _json_roundtripable(F_SPACE_EQUIVALENCE_CLASSES)

    assert {row["u_class"] for row in U_SPACE_EQUIVALENCE_CLASSES} >= {
        "manual.source_shell",
        "manual.same_shell_error",
        "manual.reexploded_confirm_shell",
        "manual.reexploded_signal_shell",
        "manual.reexploded_signal_plus_fill_shell",
        "terminal.completion",
    }
    assert {row["f_class"] for row in F_SPACE_EQUIVALENCE_CLASSES} >= {
        "good_sparse_macro_fill",
        "good_dotted_controller_fill",
        "semantic_block",
        "validator_reject",
        "stale_or_non_current_datum",
        "signal_only",
        "signal_plus_fill",
    }

    packet = normalize_controller_action_packet_v1(
        fill={"Q": {"value": "alpha"}},
        signal={
            "datum_id": "Q",
            "kind": "refresh_and_fill",
            "info": {"reason": "matrix"},
        },
    )
    assert packet.fill == {"Q": {"value": "alpha"}}
    assert packet.signal is not None
    assert packet.signal.datum_id == "Q"
    assert packet.signal.kind == "refresh_and_fill"

    signal = normalize_controller_datum_signal_v1(
        {"target": "Q", "kind": "refresh"}
    )
    assert signal is not None
    assert signal.datum_id == "Q"
    assert signal.kind == "refresh"

    rendered_packet_doc = {
        "kind": CONTROLLER_ACTION_PACKET_KIND_V1,
        "signal_kind": CONTROLLER_DATUM_SIGNAL_KIND_V1,
        "fill": packet.fill,
        "signal": {
            "datum_id": packet.signal.datum_id,
            "kind": packet.signal.kind,
            "info": packet.signal.info,
        },
    }
    _json_roundtripable(rendered_packet_doc)

    ev_shape = session_event_packet_shape_v1()
    assert ev_shape["kind"] == SESSION_EVENT_KIND_V1
    ev = build_session_event(
        form_id="F",
        frame_id="frame",
        span_id="span",
        datum_id="Q",
        signal_kind="refresh",
        name="ufspace.event",
        payload={"ok": True},
    )
    assert ev["kind"] == SESSION_EVENT_KIND_V1
    _json_roundtripable(ev)

    ctx_sheet = ui_context_contract_sheet_v1()
    assert "datum_widget_decls" in ctx_sheet["core_keys"]
    assert "datum_widgets_on_this_span" in ctx_sheet["core_keys"]

    with pytest.raises(Exception, match="Invalid fill"):
        normalize_controller_action_packet_v1(
            fill=["not", "a", "mapping"]  # type: ignore[arg-type]
        )

    with pytest.raises(Exception, match="Invalid fill"):
        normalize_controller_action_packet_v1(
            signal={"kind": "missing-datum"}
        )


def test_app_table_controller_path_covers_Uprev_F_Unext_good_bad_signal_and_completion() -> None:
    # ------------------------------------------------------------------
    # U0: controller reaches first manual U. Q has mounted and reexploded
    # into the source shell, so U0 determines F0.
    # ------------------------------------------------------------------
    sid = _create_app_table_session()
    first_packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    u0 = first_packet["ctx"]
    _assert_is_U(u0, manual=True)
    assert u0["current_span"] == "span"
    assert u0["span_to_datum_widgets"]["span"] == ["A", "Q", "B"]
    _assert_F_mentions(u0, "Q", "value", "route")
    assert set(_fill_space_from_U(u0)["pending_datums"]) == {
        "A",
        "Q",
        "B",
    }

    # ------------------------------------------------------------------
    # Bad F: semantic widget block. Same U family, same span, last_error.
    # ------------------------------------------------------------------
    sid_bad = _create_app_table_session()
    u_bad_0 = dispatch_ui_action(
        sid_bad,
        action=UserAction.STEP,
        render=False,
    )["ctx"]
    bad_packet = dispatch_ui_action(
        sid_bad,
        action=UserAction.STEP,
        user_fill={
            "Q.value": "block",
            "Q.route": "ordinary",
        },
        render=False,
    )
    _assert_error_same_U_family(u_bad_0, bad_packet["ctx"])
    assert "Q" in str(bad_packet["ctx"].get("last_error"))

    # ------------------------------------------------------------------
    # Good ordinary F: same span, but Q declaration changes from value/route
    # to confirm. This proves O_Q^t -> F_Q^(t+1).
    # ------------------------------------------------------------------
    sid_reexplode = _create_app_table_session()
    dispatch_ui_action(
        sid_reexplode,
        action=UserAction.STEP,
        render=False,
    )
    ordinary_packet = dispatch_ui_action(
        sid_reexplode,
        action=UserAction.STEP,
        user_fill={
            "A.value": "plain-a",
            "Q.value": "alpha",
            "Q.route": "ordinary",
            "B.value": "plain-b",
        },
        render=False,
    )
    u1 = ordinary_packet["ctx"]
    _assert_is_U(u1, manual=True)
    assert u1["current_span"] == "span"
    _assert_F_mentions(u1, "Q", "confirm")
    assert "value" not in _decl_micro_names(
        u1["datum_widget_decls"]["Q"]
    )
    q_state = _app_state_for(_api(), sid_reexplode)
    assert q_state["branch"] == "ordinary_value_to_confirm"
    assert q_state["accepted_value"] == "alpha"

    done_packet = dispatch_ui_action(
        sid_reexplode,
        action=UserAction.STEP,
        user_fill={"Q.confirm": "yes"},
        render=False,
    )
    assert done_packet["event_kind"] == "ATCOMPLETION"
    _assert_completion_U(done_packet["ctx"])
    outputs = _api().get_outputs(sid_reexplode)
    assert outputs["form_fills"]["A"]["value"] == "plain-a"
    assert outputs["form_fills"]["Q"]["confirm"] == "yes"
    assert outputs["form_fills"]["B"]["value"] == "plain-b"

    # ------------------------------------------------------------------
    # Signal-only F: no new fill, one target signal. Same U family, new
    # signal_value shell, then completion after filling the signal shell.
    # ------------------------------------------------------------------
    sid_signal = _create_app_table_session()
    dispatch_ui_action(
        sid_signal,
        action=UserAction.STEP,
        render=False,
    )
    signal_packet = dispatch_ui_action(
        sid_signal,
        action=UserAction.STEP,
        user_signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {
                "reason": "signal-only",
                "suggested": "from-controller",
            },
        },
        render=False,
    )
    u_signal = signal_packet["ctx"]
    _assert_is_U(u_signal, manual=True)
    _assert_F_mentions(u_signal, "Q", "signal_value")
    q_signal_state = _app_state_for(_api(), sid_signal)
    assert q_signal_state["branch"] == "signal_only_to_signal_value"
    assert q_signal_state["last_info"]["source"] == "controller_action"
    assert q_signal_state["last_info"]["datum_id"] == "Q"

    signal_done = dispatch_ui_action(
        sid_signal,
        action=UserAction.STEP,
        user_fill={
            "A.value": "plain-a",
            "Q.signal_value": "signal-complete",
            "B.value": "plain-b",
        },
        render=False,
    )
    assert signal_done["event_kind"] == "ATCOMPLETION"

    # ------------------------------------------------------------------
    # Fill+signal F: same submitted Q.value can branch to signal_confirm
    # instead of ordinary confirm because signal is a real datum input.
    # ------------------------------------------------------------------
    sid_signal_fill = _create_app_table_session()
    dispatch_ui_action(
        sid_signal_fill,
        action=UserAction.STEP,
        render=False,
    )
    signal_fill_packet = dispatch_ui_action(
        sid_signal_fill,
        action=UserAction.STEP,
        user_fill={
            "A.value": "plain-a",
            "Q.value": "alpha",
            "Q.route": "ordinary",
            "B.value": "plain-b",
        },
        user_signal={
            "datum_id": "Q",
            "kind": "refresh_and_fill",
            "info": {"reason": "same-action"},
        },
        render=False,
    )
    u_signal_fill = signal_fill_packet["ctx"]
    _assert_is_U(u_signal_fill, manual=True)
    _assert_F_mentions(u_signal_fill, "Q", "signal_confirm")
    assert "confirm" not in _decl_micro_names(
        u_signal_fill["datum_widget_decls"]["Q"]
    )
    q_signal_fill_state = _app_state_for(_api(), sid_signal_fill)
    assert (
        q_signal_fill_state["branch"]
        == "signal_plus_fill_to_signal_confirm"
    )
    assert q_signal_fill_state["accepted_fill_during_signal"] == "alpha"

    final_signal_fill = dispatch_ui_action(
        sid_signal_fill,
        action=UserAction.STEP,
        user_fill={"Q.signal_confirm": "signal-confirmed"},
        render=False,
    )
    assert final_signal_fill["event_kind"] == "ATCOMPLETION"


def test_app_table_raw_api_and_offline_script_use_same_U_F_space() -> None:
    # Raw roleless API path.
    sid = _create_app_table_session()
    api = _api()
    u0 = api.step_session(sid)
    _assert_is_U(u0, manual=True)
    _assert_F_mentions(u0, "Q", "value", "route")

    u1 = api.step_session(
        sid,
        fill={
            "A": {"value": "plain-a"},
            "Q": {
                "value": "raw-alpha",
                "route": "ordinary",
            },
            "B": {"value": "plain-b"},
        },
    )
    _assert_is_U(u1, manual=True)
    _assert_F_mentions(u1, "Q", "confirm")

    done = api.step_session(
        sid,
        fill={"Q": {"confirm": "yes"}},
    )
    _assert_completion_U(done)

    # Offline script path, including bad F followed by good F.
    sid_script = _create_app_table_session()
    runner = SessionProgramScriptedHeadlessRunner(
        sid_script,
        api=api,
    )

    su0 = runner.step_until_stop()
    _assert_is_U(su0, manual=True)
    _assert_F_mentions(su0, "Q", "value", "route")

    bad = runner.step(
        fill={
            "Q": {
                "value": "block",
                "route": "ordinary",
            }
        }
    )
    _assert_error_same_U_family(su0, bad)

    su1 = runner.step(
        fill={
            "A": {"value": "script-a"},
            "Q": {
                "value": "script-alpha",
                "route": "ordinary",
            },
            "B": {"value": "script-b"},
        }
    )
    _assert_is_U(su1, manual=True)
    _assert_F_mentions(su1, "Q", "confirm")

    sdone = runner.step(
        fill={"Q": {"confirm": "yes"}}
    )
    _assert_completion_U(sdone)

    assert runner.history
    for row in runner.history:
        _json_roundtripable(row)


# =============================================================================
# PART B: ThinkProgramTM / ThinkWidgetTM surface
# =============================================================================

TP_IDENTITY_WIDGET = "test.ufspace.thinkwidget.identity.v1"
TP_SUPPORT_WIDGET = "test.ufspace.thinkwidget.support.v1"
TP_REVIEW_WIDGET = "test.ufspace.thinkwidget.review.v1"
TP_PROGRAM_ID = "ufspace_hil"


@thinkwidgetTM_config(
    TP_IDENTITY_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={"seed": {"type": "str", "required": True}},
    wires={},
)
class UFSpaceIdentityWidget(DatumLifecycleWidget):
    """
    Highest-surface authoritative widget.

    mount -> identity shell -> confirm shell -> done, with:
        validator rejection through email/number/select micros,
        refresh signal reexploding the same shell,
        revise returning to the prior shell,
        durable self state for downstream wires.
    """

    def _lifecycle(
        self,
        fill_data: Mapping[str, Any],
    ) -> Dict[str, Any]:
        lifecycle = dict(
            dict(fill_data["fill_shell"]).get("lifecycle") or {}
        )
        lifecycle["widget"] = TP_IDENTITY_WIDGET
        lifecycle["mount_explode"] = True
        lifecycle["max_reexplosions"] = 20
        lifecycle["max_messages"] = 8
        lifecycle["max_proc_notes"] = 0
        return lifecycle

    def _identity_shell(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "id": position["datum_id"],
            "title": "UF identity source",
            "micros": [
                _text_micro(
                    "full_name",
                    required=True,
                    min_words=2,
                ),
                _email_micro(
                    "contact_email",
                    required=True,
                ),
                _bounded_number_micro(
                    "lucky_number",
                    required=True,
                    minimum=3,
                    maximum=10,
                ),
            ],
            "lifecycle": self._lifecycle(fill_data),
        }

    def _confirm_shell(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "id": position["datum_id"],
            "title": "UF identity confirm",
            "micros": [
                _select_micro(
                    "decision",
                    required=True,
                    options=["yes", "revise"],
                )
            ],
            "lifecycle": self._lifecycle(fill_data),
        }

    def _on_mount(
        self,
        position,
        fill_data,
        limits,
        stats,
    ):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel = dict(datum_args.get("__kernel") or {})

        self.phase = "identity"
        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_seen_user_args = {
            k: v
            for k, v in datum_args.items()
            if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel.get("step") or {}).get("id"),
            "form_id": dict(kernel.get("form") or {}).get("id"),
            "frame_id": dict(kernel.get("frame") or {}).get("id"),
            "span_id": dict(kernel.get("span") or {}).get("id"),
            "authoritative": bool(
                kernel.get("authoritative", False)
            ),
        }

        return Reexplode(
            next_fill_shell=self._identity_shell(
                position,
                fill_data,
            ),
            pre_computed_fills={
                "full_name": "",
                "contact_email": "",
                "lucky_number": "",
            },
            prefill_hints={
                "full_name": "Ada Lovelace",
                "contact_email": "ada@example.com",
                "lucky_number": "7",
            },
        )

    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        self.last_signal_seen = dict(signal)
        current = dict(fill_data["current_fills"])

        if getattr(self, "phase", None) == "identity":
            self.phase = "confirm"
            self.identity_full_name = current["full_name"]
            self.identity_contact_email = current["contact_email"]
            self.identity_lucky_number = current["lucky_number"]
            self.identity_changed_fills = dict(
                fill_data["changed_fills"]
            )
            return Reexplode(
                next_fill_shell=self._confirm_shell(
                    position,
                    fill_data,
                ),
                pre_computed_fills={"decision": ""},
                prefill_hints={"decision": "yes"},
            )

        if getattr(self, "phase", None) == "confirm":
            decision = current.get("decision")
            self.confirm_decision = decision
            if decision == "revise":
                self.phase = "identity"
                return Reexplode(
                    next_fill_shell=self._identity_shell(
                        position,
                        fill_data,
                    ),
                    pre_computed_fills={
                        "full_name": getattr(
                            self,
                            "identity_full_name",
                            "",
                        ),
                        "contact_email": getattr(
                            self,
                            "identity_contact_email",
                            "",
                        ),
                        "lucky_number": getattr(
                            self,
                            "identity_lucky_number",
                            "",
                        ),
                    },
                    prefill_hints={
                        "full_name": "revise name",
                        "contact_email": "revise@example.com",
                        "lucky_number": "8",
                    },
                )

            self.phase = "done"
            self.commit = {
                "datum_id": position["datum_id"],
                "full_name": self.identity_full_name,
                "contact_email": self.identity_contact_email,
                "lucky_number": self.identity_lucky_number,
                "decision": decision,
            }
            return True

        raise ValueError(
            f"unexpected phase: {getattr(self, 'phase', None)!r}"
        )

    @signal_catcher("refresh")
    def refresh(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        self.refresh_count = int(
            getattr(self, "refresh_count", 0) or 0
        ) + 1
        self.refresh_signal_seen = dict(signal)
        self.refresh_current_fills_seen = dict(
            fill_data["current_fills"]
        )
        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )


@thinkwidgetTM_config(
    TP_SUPPORT_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={},
)
class UFSpaceSupportWidget(DatumLifecycleWidget):
    """Non-authoritative product-vector member."""

    def _on_mount(
        self,
        position,
        fill_data,
        limits,
        stats,
    ):
        lifecycle = dict(
            dict(fill_data["fill_shell"]).get("lifecycle") or {}
        )
        lifecycle["widget"] = TP_SUPPORT_WIDGET
        lifecycle["mount_explode"] = True
        self.phase = "optional"
        return Reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "UF support note",
                "micros": [
                    _text_micro(
                        "note",
                        required=False,
                    )
                ],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"note": ""},
            prefill_hints={"note": "optional"},
        )

    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        self.phase = "done"
        self.note = dict(
            fill_data["current_fills"]
        ).get("note")
        self.commit = {
            "datum_id": position["datum_id"],
            "note": self.note,
        }
        return True


@thinkwidgetTM_config(
    TP_REVIEW_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={"mode": {"type": "str", "required": True}},
    wires={
        "previous_identity": {
            "multiplicity": "one",
            "required": True,
        },
        "identity_history": {
            "multiplicity": "many",
            "required": False,
        },
    },
)
class UFSpaceReviewWidget(DatumLifecycleWidget):
    """Downstream authoritative wire consumer."""

    def _on_mount(
        self,
        position,
        fill_data,
        limits,
        stats,
    ):
        shell = dict(fill_data["fill_shell"])
        datum_args = dict(shell.get("args") or {})
        kernel = dict(datum_args.get("__kernel") or {})
        past_wires = dict(kernel.get("past_wires") or {})

        previous = dict(
            past_wires.get("previous_identity") or {}
        )
        previous_value = dict(previous.get("value") or {})
        previous_state = dict(
            previous_value.get("state") or {}
        )
        identity_history = list(
            past_wires.get("identity_history") or []
        )

        self.prior_identity_full_name_on_mount = (
            previous_state.get("identity_full_name")
        )
        self.prior_identity_email_on_mount = (
            previous_state.get("identity_contact_email")
        )
        self.identity_history_count_on_mount = len(
            identity_history
        )
        self.mount_seen_user_args = {
            k: v
            for k, v in datum_args.items()
            if k != "__kernel"
        }
        self.mount_seen_kernel = {
            "step_id": dict(kernel.get("step") or {}).get("id"),
            "past_wire_keys": sorted(past_wires),
            "authoritative": bool(
                kernel.get("authoritative", False)
            ),
        }

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = TP_REVIEW_WIDGET
        lifecycle["mount_explode"] = True

        return Reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "UF review identity",
                "micros": [
                    _select_micro(
                        "approval",
                        required=True,
                        options=["approve", "reject"],
                    )
                ],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"approval": ""},
            prefill_hints={"approval": "approve"},
        )

    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        current = dict(fill_data["current_fills"])
        self.approval = current["approval"]
        self.commit = {
            "datum_id": position["datum_id"],
            "approval": self.approval,
            "reviewed_full_name": (
                self.prior_identity_full_name_on_mount
            ),
            "reviewed_email": (
                self.prior_identity_email_on_mount
            ),
        }
        return True


def _register_thinkprogram_surface() -> None:
    for cls in [
        UFSpaceIdentityWidget,
        UFSpaceSupportWidget,
        UFSpaceReviewWidget,
    ]:
        receipt = pull_thinkwidget_class_into_kernel_v1(
            cls,
            overwrite=True,
        )
        assert receipt["ok"] is True

    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def _thinkprogram_v1(
    *,
    role_partitioned: bool = False,
) -> Dict[str, Any]:
    program: Dict[str, Any] = {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "theme": {
                "value": "teaching",
                "parametrize": True,
            },
            "density": {
                "value": "compact",
                "parametrize": True,
            },
            "identity.seed": {
                "value": "seed-dev",
                "parametrize": True,
            },
            "lifecycle.default": {
                "value": {
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                }
            },
            "history.latest.required": {
                "value": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                }
            },
            "history.all.optional": {
                "value": {
                    "select": "all",
                    "required": False,
                    "max_results": 20,
                }
            },
        },
        "puppeteering": {
            "identity.seed": "seed-prod",
            "density": "compact",
        },
        "run": {
            "program": {
                "info": {
                    "id": TP_PROGRAM_ID,
                    "title": "UFSpace human input loop",
                    "args": {"theme": "$theme"},
                },
                "widgets": {
                    "identity": {
                        "widget": TP_IDENTITY_WIDGET,
                        "title": "Identity",
                        "args": {"seed": "$identity.seed"},
                        "lifecycle": "$lifecycle.default",
                        "wires": {},
                        "authoritative": True,
                        "tags": [
                            "source",
                            "authoritative",
                        ],
                        "system_flags": {
                            "ui_region": "main"
                        },
                    },
                    "support_note": {
                        "widget": TP_SUPPORT_WIDGET,
                        "title": "Support note",
                        "args": {},
                        "lifecycle": "$lifecycle.default",
                        "wires": {},
                        "authoritative": False,
                        "tags": [
                            "support",
                            "non-authoritative",
                        ],
                        "system_flags": {
                            "ui_region": "side"
                        },
                    },
                    "review": {
                        "widget": TP_REVIEW_WIDGET,
                        "title": "Review",
                        "args": {"mode": "strict"},
                        "lifecycle": "$lifecycle.default",
                        "wires": {
                            "previous_identity": {
                                "from": "identity",
                                "history": "$history.latest.required",
                            },
                            "identity_history": {
                                "from": "identity",
                                "history": "$history.all.optional",
                            },
                        },
                        "authoritative": True,
                        "tags": [
                            "consumer",
                            "wire-reader",
                        ],
                        "system_flags": {
                            "ui_region": "main"
                        },
                    },
                },
                "flow": [
                    {
                        "id": "collect_identity",
                        "title": "Collect identity",
                        "widgets": [
                            "identity",
                            "support_note",
                        ],
                        "authoritative": [
                            True,
                            False,
                        ],
                    },
                    {
                        "id": "review_identity",
                        "title": "Review identity",
                        "widgets": ["review"],
                        "authoritative": [True],
                    },
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                },
                "app": {
                    "slug": "ufspace-hil",
                    "theme": "$theme",
                },
            },
        },
    }

    if role_partitioned:
        program["run"]["program"]["widgets"]["identity"]["roles"] = [
            "maker"
        ]
        program["run"]["program"]["flow"][0]["roles"] = [
            "reviewer"
        ]
        # Keep first flow only so the role test is strictly about one
        # product-vector span.
        program["run"]["program"]["flow"] = [
            program["run"]["program"]["flow"][0]
        ]

    return program


def _create_thinkprogram_session(
    *,
    role_partitioned: bool = False,
) -> str:
    _register_thinkprogram_surface()
    created = _api().create_VM_session_from_program(
        program=_thinkprogram_v1(
            role_partitioned=role_partitioned
        ),
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
            "test": "ufspace_thinkprogram",
        },
        get_map=False,
    )
    return str(dict(created)["session_id"])


def _tp_form_id(flow_id: str) -> str:
    return f"{TP_PROGRAM_ID}.{flow_id}.form"


def _latest_tp_lifecycle_state(
    api: Any,
    sid: str,
    form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    store = api._get(sid).state["_datum_lifecycle_v1"]
    state = store["forms"][form_id]["datums"][datum_id]["state"]
    assert isinstance(state, Mapping)
    return state


# =============================================================================
# PART B tests
# =============================================================================


def test_thinkprogram_static_json_lowers_to_expected_app_table_U_sources() -> None:
    _register_thinkprogram_surface()
    source = _thinkprogram_v1()
    before = copy.deepcopy(source)

    kernel_program = lower_think_program_to_kernel_program_v1(
        source
    )
    assert source == before
    assert [k["step"]["id"] for k in kernel_program] == [
        "ufspace_hil.collect_identity",
        "ufspace_hil.review_identity",
    ]
    assert [k["form"]["id"] for k in kernel_program] == [
        "ufspace_hil.collect_identity.form",
        "ufspace_hil.review_identity.form",
    ]

    collect = kernel_program[0]
    assert collect["frame"]["id"] == "frame"
    assert collect["span"]["id"] == "span"
    datums = {
        datum["id"]: datum
        for datum in collect["datums"]
    }
    assert list(datums) == [
        "identity",
        "support_note",
    ]
    assert datums["identity"]["micros"] == []
    assert datums["support_note"]["micros"] == []
    assert datums["identity"]["authoritative"] is True
    assert datums["support_note"]["authoritative"] is False
    assert "__kernel" not in datums["identity"]["args"]

    review = kernel_program[1]["datums"][0]
    assert sorted(review["past_wires"]) == [
        "identity_history",
        "previous_identity",
    ]
    validate_kernel_program_v1(kernel_program)

    bundle = lower_think_program_v1(_thinkprogram_v1())
    assert [
        row["public_step_name"]
        for row in bundle.app_table_manifest
    ] == [
        "ufspace_hil.collect_identity",
        "ufspace_hil.review_identity",
    ]
    assert (
        bundle.provenance["source_program_language"]
        == LANG_THINK_PROGRAM_V1
    )


def test_thinkprogram_controller_path_covers_Uprev_F_Unext_for_all_core_classes() -> None:
    sid = _create_thinkprogram_session()
    api = _api()

    # U0: first ThinkProgram flow item. Both widgets mounted; only identity
    # is authoritative.
    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    u0 = first["ctx"]
    _assert_is_U(u0, manual=True)
    assert u0["span_to_datum_widgets"]["span"] == [
        "identity",
        "support_note",
    ]
    assert u0["datum_widgets_on_this_span"] == [
        "identity",
        "support_note",
    ]
    _assert_F_mentions(
        u0,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )
    _assert_F_mentions(
        u0,
        "support_note",
        "note",
    )

    identity_mount = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    assert identity_mount["phase"] == "identity"
    assert identity_mount["mount_seen_initial_micros"] == []
    assert identity_mount["mount_seen_user_args"] == {
        "seed": "seed-prod"
    }
    assert (
        identity_mount["mount_seen_kernel"]["authoritative"]
        is True
    )

    # Bad validator F: same U family with last_error.
    bad_email = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.contact_email": "not-an-email"
        },
        render=False,
    )
    _assert_error_same_U_family(u0, bad_email["ctx"])
    assert "identity" in str(
        bad_email["ctx"].get("last_error")
    )

    # Signal-only F: same identity shell reexplodes, signal reaches widget.
    refreshed = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_signal={
            "datum_id": "identity",
            "kind": "refresh",
            "info": {
                "reason": "thinkprogram-signal-only"
            },
        },
        render=False,
    )
    u_refresh = refreshed["ctx"]
    _assert_is_U(u_refresh, manual=True)
    _assert_F_mentions(
        u_refresh,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )
    identity_after_refresh = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    assert identity_after_refresh["refresh_count"] == 1
    assert identity_after_refresh["refresh_signal_seen"] == {
        "kind": "refresh",
        "info": {
            "reason": "thinkprogram-signal-only",
            "datum_id": "identity",
            "source": "controller_action",
        },
    }

    # Fill+signal F: packet remains one action; refresh handler keeps shell
    # pending.
    fill_plus_signal = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.full_name": "Alan Turing"
        },
        user_signal={
            "datum_id": "identity",
            "kind": "refresh",
            "info": {
                "reason": "fill-plus-signal"
            },
        },
        render=False,
    )
    u_fill_signal = fill_plus_signal["ctx"]
    _assert_is_U(u_fill_signal, manual=True)
    _assert_F_mentions(
        u_fill_signal,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )
    identity_after_fill_signal = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    assert identity_after_fill_signal["refresh_count"] == 2
    assert identity_after_fill_signal["phase"] == "identity"

    # Good source fill: reexplode to confirm shell.
    confirmed = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.full_name": "Ada Lovelace",
            "identity.contact_email": "ada@example.com",
            "identity.lucky_number": "7",
        },
        render=False,
    )
    u1 = confirmed["ctx"]
    _assert_is_U(u1, manual=True)
    _assert_F_mentions(
        u1,
        "identity",
        "decision",
    )
    assert "full_name" not in _decl_micro_names(
        u1["datum_widget_decls"]["identity"]
    )
    identity_confirm = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    assert identity_confirm["phase"] == "confirm"
    assert identity_confirm["identity_lucky_number"] == 7

    # Bad decision: same confirm U with last_error.
    bad_decision = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.decision": "maybe"
        },
        render=False,
    )
    _assert_error_same_U_family(
        u1,
        bad_decision["ctx"],
    )

    # Stubborn revise: reexplode back to source shell before done.
    revise = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.decision": "revise"
        },
        render=False,
    )
    u2 = revise["ctx"]
    _assert_is_U(u2, manual=True)
    _assert_F_mentions(
        u2,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )
    identity_revised = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    assert identity_revised["phase"] == "identity"
    assert (
        identity_revised["confirm_decision"]
        == "revise"
    )

    # Good revised source -> confirm -> yes. Because support_note is
    # non-authoritative, the program advances to the review flow item even
    # though support_note is untouched.
    confirm_again = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.full_name": "Ada Byron Lovelace",
            "identity.contact_email": "ada.byron@example.com",
            "identity.lucky_number": 8,
        },
        render=False,
    )
    u3 = confirm_again["ctx"]
    _assert_is_U(u3, manual=True)
    _assert_F_mentions(
        u3,
        "identity",
        "decision",
    )

    review_packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.decision": "yes"
        },
        render=False,
    )
    u4 = review_packet["ctx"]
    _assert_is_U(u4, manual=True)
    assert u4["datum_widgets_on_this_span"] == [
        "review"
    ]
    _assert_F_mentions(
        u4,
        "review",
        "approval",
    )

    review_mount = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("review_identity"),
        "review",
    )
    assert (
        review_mount["prior_identity_full_name_on_mount"]
        == "Ada Byron Lovelace"
    )
    assert (
        review_mount["prior_identity_email_on_mount"]
        == "ada.byron@example.com"
    )
    assert (
        review_mount["identity_history_count_on_mount"]
        >= 1
    )

    # Stale/non-current F: identity has left Pending(S,t), so it is
    # inadmissible.
    stale_identity = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "identity.decision": "yes"
        },
        render=False,
    )
    assert (
        stale_identity["ctx"]["kind"]
        == "MANUALFILLNEEDEDSTEP"
    )
    assert stale_identity["ctx"][
        "datum_widgets_on_this_span"
    ] == ["review"]
    assert stale_identity["ctx"].get("last_error")

    done = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "review.approval": "approve"
        },
        render=False,
    )
    assert done["event_kind"] == "ATCOMPLETION"
    _assert_completion_U(done["ctx"])

    review_done = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("review_identity"),
        "review",
    )
    assert review_done["commit"] == {
        "datum_id": "review",
        "approval": "approve",
        "reviewed_full_name": "Ada Byron Lovelace",
        "reviewed_email": "ada.byron@example.com",
    }

    writes = query_runtime_writes_v1(
        api._get(sid).state,
        {
            "write_kinds": [
                WRITE_KIND_DATUM_LIFECYCLE
            ],
            "include_values": True,
            "max_results": 100,
        },
    )
    assert writes["ok"] is True
    rendered = json.dumps(
        writes,
        sort_keys=True,
        default=str,
    )
    assert "ufspace_hil.collect_identity.form" in rendered
    assert "ufspace_hil.review_identity.form" in rendered
    assert "Ada Byron Lovelace" in rendered
    assert "approve" in rendered


def test_thinkprogram_offline_script_replays_same_Uprev_F_Unext_space() -> None:
    sid = _create_thinkprogram_session()
    api = _api()
    runner = SessionProgramScriptedHeadlessRunner(
        sid,
        api=api,
    )

    u0 = runner.step_until_stop()
    _assert_is_U(u0, manual=True)
    _assert_F_mentions(
        u0,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )

    bad = runner.step(
        fill={
            "identity": {
                "contact_email": "not-an-email"
            }
        }
    )
    _assert_error_same_U_family(u0, bad)

    u1 = runner.step(
        fill={
            "identity": {
                "full_name": "Grace Hopper",
                "contact_email": "grace@example.com",
                "lucky_number": 8,
            }
        }
    )
    _assert_is_U(u1, manual=True)
    _assert_F_mentions(
        u1,
        "identity",
        "decision",
    )

    u2 = runner.step(
        fill={
            "identity": {
                "decision": "yes"
            }
        }
    )
    _assert_is_U(u2, manual=True)
    assert u2["datum_widgets_on_this_span"] == [
        "review"
    ]
    _assert_F_mentions(
        u2,
        "review",
        "approval",
    )

    review_mount = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("review_identity"),
        "review",
    )
    assert (
        review_mount["prior_identity_full_name_on_mount"]
        == "Grace Hopper"
    )
    assert (
        review_mount["prior_identity_email_on_mount"]
        == "grace@example.com"
    )

    done = runner.step(
        fill={
            "review": {
                "approval": "approve"
            }
        }
    )
    _assert_completion_U(done)

    identity_done = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("collect_identity"),
        "identity",
    )
    review_done = _latest_tp_lifecycle_state(
        api,
        sid,
        _tp_form_id("review_identity"),
        "review",
    )
    assert (
        identity_done["commit"]["full_name"]
        == "Grace Hopper"
    )
    assert (
        review_done["commit"]["reviewed_full_name"]
        == "Grace Hopper"
    )

    for row in runner.history:
        _json_roundtripable(row)


def test_role_modulated_controller_U_is_projection_and_F_is_narrowed() -> None:
    """
    Roles are not a new engine state machine; they are a facade projection of U
    and a preflight narrowing of F. This test keeps one product-vector span:

        identity     roles = [maker]
        support_note roles = inherited from span [reviewer]
    """
    sid = _create_thinkprogram_session(
        role_partitioned=True
    )

    maker_start = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="maker",
        render=False,
    )
    maker_u = maker_start["ctx"]
    _assert_is_U(maker_u, manual=True)
    assert maker_u["datum_widgets_on_this_span"] == [
        "identity"
    ]
    _assert_F_mentions(
        maker_u,
        "identity",
        "full_name",
        "contact_email",
        "lucky_number",
    )

    reviewer_u = get_current_ui_state(
        sid,
        role="reviewer",
    )
    _assert_is_U(reviewer_u, manual=True)
    assert reviewer_u["datum_widgets_on_this_span"] == [
        "support_note"
    ]
    _assert_F_mentions(
        reviewer_u,
        "support_note",
        "note",
    )

    maker_assignments = {
        row["datum_id"]: row
        for row in maker_u[
            "role_mismatch_modulation_info"
        ]["assignments"]
    }
    reviewer_assignments = {
        row["datum_id"]: row
        for row in reviewer_u[
            "role_mismatch_modulation_info"
        ]["assignments"]
    }

    assert maker_assignments["identity"]["roles"] == [
        "maker"
    ]
    assert (
        maker_assignments["identity"]["role_source"]
        == "datum"
    )
    assert maker_assignments["support_note"]["roles"] == [
        "reviewer"
    ]
    assert (
        maker_assignments["support_note"]["role_source"]
        == "span"
    )
    assert reviewer_assignments["identity"]["roles"] == [
        "maker"
    ]
    assert reviewer_assignments["support_note"]["roles"] == [
        "reviewer"
    ]

    before_denial_seq = get_live_session_latest_event_seq(
        session_id=sid
    )
    before_denial_events = copy.deepcopy(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )
    assert_strict_canonical_event_order_v1(before_denial_events)

    with pytest.raises(
        PermissionError,
        match="identity",
    ):
        dispatch_ui_action(
            sid,
            action=UserAction.STEP,
            role="reviewer",
            user_fill={
                "identity.full_name": (
                    "Reviewer Must Not Write"
                )
            },
            render=False,
        )

    assert get_live_session_latest_event_seq(
        session_id=sid
    ) == before_denial_seq
    assert get_live_session_events(
        session_id=sid,
        role=None,
    ) == before_denial_events

    reviewer_allowed = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="reviewer",
        user_fill={
            "support_note.note": "reviewer support note"
        },
        render=False,
    )
    assert isinstance(reviewer_allowed, dict)
    assert (
        reviewer_allowed["ctx"]["kind"]
        == "MANUALFILLNEEDEDSTEP"
    )