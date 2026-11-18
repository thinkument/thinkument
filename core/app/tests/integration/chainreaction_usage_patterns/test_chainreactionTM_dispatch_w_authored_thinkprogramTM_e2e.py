from __future__ import annotations

"""
ThinkProgramTM × ThinkWidgetTM × FunkedSessionTM × Live Event Queue
Highest-Seam Executable Integration and Pedagogy Sheet
=======================================================

This sheet is intentionally three artifacts at once:

1. an executable pytest E2E suite;
2. a top-down formalism for the highest authoring + dispatch + event seams;
3. a usage guide for downstream apps that live from dispatch returns, live
   event callbacks, session event queue inspection, or any combination of them.

The sheet proves the intended app-facing composition:

    ThinkWidgetTM class
        -> registered datum lifecycle automaton
        -> ThinkProgramTM JSON program
        -> one generated span/frame per program step
        -> role-aware session launch
        -> dispatch_live_session_action(...)
        -> dispatch_live_session_action_with_chain_reaction(...)
        -> controller loop events + datum lifecycle events
        -> callback board and session event queue agree
        -> bounded high-facade queue inspection

===============================================================================
I. TOP-DOWN FORMALISM
===============================================================================

1. Program

    P = T_1 ; T_2 ; ... ; T_n

Each ThinkProgramTM flow item lowers to one kernel step T_i. Under the current
authoring contract, one T_i emits one frame containing one active span S_i.

2. Span

    S_i = (D_i^1, D_i^2, ... D_i^k)

Each D_i^j is a datum lifecycle automaton. A datum can be authoritative or
supporting. The span advances exactly when every authoritative datum is in its
done sink.

    sat(S_i) iff for all authoritative D in S_i: status(D) = done

3. Datum lifecycle / ThinkWidgetTM

At logical time t, a pending datum exposes an observable shell O_D^t:

    O_D^t = (
        datum declaration,
        active micros,
        current values,
        lifecycle state,
        status,
        role assignment
    )

An action F_D^(t+1) is admissible only against the active micros in O_D^t.

The class handler returns exactly one of:

    Reexplode(next_fill_shell=...)
        The datum remains pending, but O_D changes.

    True
        The datum enters its done sink.

Therefore a ThinkWidgetTM datum appears "forever alive" across the program
surface while actually moving through a finite sequence of durable lifecycle
states and shells.

4. Controller dispatch

A public action enters the highest dispatch seam:

    dispatch_live_session_action(...)
        single controller dispatch only

    dispatch_live_session_action_with_chain_reaction(...)
        one caller dispatch, then zero or more generated dispatches

Every successful controller dispatch emits:

    controller.loop.start
        emitted when the controller enters the loop.

    datum_lifecycle_event_v1 packets
        emitted inside datum mount/fill/reexplode work when a widget decides to
        emit.

    controller.loop.end
        emitted when the controller resolves the loop to a durable public stop.

The controller start/end events share dispatch_id and have distinct event_id.

5. Event delivery

Every live event packet is delivered to:

    1. the session-local bounded transient event queue;
    2. the dispatch callback, if supplied.

The queue is not durable state. It is not in snapshots, outputs, runtime writes,
or lifecycle rows.

A downstream app board can therefore live in either style:

    A. callback-first app:
        dispatch once, receive events immediately on callbacks.

    B. queue-first app:
        dispatch once, inspect the event queue after the fact.

    C. hybrid app:
        dispatch once, use callbacks for live UI and queue view for audit,
        reconciliation, or tests.

This sheet uses a board object that installs both callback types:

    controller_events_callback(event)
    explosion_events_callback(event)

The callback type tells the downstream app whether a packet came from the
controller boundary or from within datum lifecycle processing.

6. Role modulation and controller event payloads

The underlying engine remains roleless.

Controller event payload.U must be canonical unmodulated ctx when it is recorded
into the queue or delivered to the controller callback. This prevents role-
specific LiveTable/audit storage.

The high queue-view facade may then project event payload.U for a caller role:

    get_live_session_events(session_id=sid, role=None)
        returns the unmodulated queue view.

    get_live_session_events(session_id=sid, role="reviewer")
        returns the same events, but controller payload.U is role-modulated for
        reviewer.

The queue is not mutated by this projection.

7. FunkedSessionTM configuration

The global pocket controls generated chain reaction scheduling and hard bounds:

    session_metadata["chainreactionTM_config"] = {
        "version": "chainreaction1.0",
        "roles_ordered": ["maker", "reviewer", "release_ai"],
        "expect_all_roles_chainreactioned": False,
        "on_semantic_error": "retry_w_error_awareness",
        "max_semantic_errors_in_a_row": 2,
        "max_fills_on_a_span": 8,
        "max_fills_e2e": 32,
        "history_tail_cap": 4,
        "history_size_cap": 25000,
        "events_queue_length": 0,
    }

Each role row explicitly declares a generated filler or None:

    session_metadata["roles"][r]["chainreactionTM_config"] = (
        None
        or {
            "version": "<registered chainreactiontm version>",
            "args": {...validated version args...},
        }
    )

If the global pocket is absent, dispatch_live_session_action_with_chain_reaction
still performs the caller dispatch but chain reaction is disabled.

8. Generated transition

For selected role r:

    U_t^r = role_modulate(U_t, r)

    H_t^r = bounded_history(
        roles=readable(r),
        tail_per_role=history_tail_cap,
        total_json_bytes<=history_size_cap
    )

    request = FunkTMRequest(
        session_id,
        role=r,
        args=validated_role_args,
        ctx=U_t^r,
        pending_datums=writable pending datum rows,
        history=H_t^r,
        last_error=owned generated semantic error or None,
        semantic_errors_in_row=e_t,
        events=latest role-projected queue tail when enabled,
    )

    result = chainreaction_version(request)

The mutation is always performed through the same role-aware dispatch seam:

    dispatch_live_session_action(
        action=STEP,
        user_fill=result.fill,
        user_signal=result.signal,
        role=r,
    )

No lower mutation path is duplicated.

===============================================================================
II. WHAT THIS SHEET PROVES
===============================================================================

- authored ThinkWidgetTM mount shell and reexplosion;
- active-shell grammar routing;
- ThinkProgramTM flow and lifecycle history wires;
- single dispatch without chain reaction;
- chain reaction dispatch with machine-before-human;
- human barrier followed by machine continuation;
- pure-machine completion;
- explicit disabled chain reaction when no global chainreactionTM_config exists;
- controller events are queued, callback-delivered, and correlated;
- datum lifecycle events are callback-delivered and queued when widgets emit;
- board callback stream matches the high-facade session event queue;
- high-facade queue limit returns latest k events;
- high-facade queue role projection modulates controller payload.U without
  mutating the underlying queue;
- FunkTM event tails are disabled by default and role-projected when enabled;
- semantic retry cap and productive reexplosion cap;
- static per-role config completeness before mutation;
- service packets do not expose raw runtime state by accident.
"""

import json
from typing import Any, Dict, Mapping, Optional

import pytest

# Registration side effects for MICRO_TYPES.
import _thinkprogram._iomicrosTM.table_micros  # noqa: F401

from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
)
from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
    UserAction,
    create_core_session_from_program,
    dispatch_live_session_action,
    get_live_session_context,
    get_live_session_events,
)
from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    DatumLifecycleWidget,
    Reexplode,
    thinkwidgetTM_config,
)
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    register_think_program_language_v1,
)
from _thinksessions.run.run_from_here import (
    dispatch_live_session_action_with_chain_reaction,
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
    FunkMaxFillsOnSpanExceeded,
    FunkMaxSemanticErrorsExceeded,
    FunkRoleConfigMissingStaticError,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._runtime import (
    _generated_dispatch_had_fresh_semantic_error,
)


# =============================================================================
# Stable test names
# =============================================================================

W_COLLECT = "test.highest_events.collect.v1"
W_REVIEW = "test.highest_events.review.v1"
W_RELEASE = "test.highest_events.release.v1"

PROGRAM_ID = "highest_events_program"

FUNK_SMART = "test.highest_events.smart.v1"
FUNK_BAD = "test.highest_events.bad.v1"
FUNK_HISTORY = "test.highest_events.history.v1"

HISTORY_REQUESTS: list[FunkTMRequest] = []


# =============================================================================
# Live downstream app board
# =============================================================================

class AppBoard:
    """
    Tiny downstream app surface used by the tests.

    A real higher app might update a LiveTable, append to an audit stream,
    publish over websockets, run local routing logic, or all of the above.

    This board deliberately separates callback types so tests and readers can
    see the source membrane:

        controller_events_callback
            controller.loop.start / controller.loop.end

        explosion_events_callback
            datum lifecycle packets from mount/fill/reexplode work
    """

    def __init__(self) -> None:
        self.controller_events: list[Dict[str, Any]] = []
        self.explosion_events: list[Dict[str, Any]] = []
        self.all_events: list[Dict[str, Any]] = []

    def controller_events_callback(self, event: Mapping[str, Any]) -> None:
        ev = dict(event)
        self.controller_events.append(ev)
        self.all_events.append(ev)

    def explosion_events_callback(self, event: Mapping[str, Any]) -> None:
        ev = dict(event)
        self.explosion_events.append(ev)
        self.all_events.append(ev)

    def callbacks(self) -> Dict[str, Any]:
        return {
            CONTROLLER_EVENTS_CALLBACK_KEY: self.controller_events_callback,
            EXPLOSION_EVENTS_CALLBACK_KEY: self.explosion_events_callback,
        }


def _event_ids(events: list[Mapping[str, Any]]) -> list[str]:
    return [str(event["event_id"]) for event in events]


def _events_named(
    events: list[Mapping[str, Any]],
    name: str,
) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("name") == name]


def _assert_controller_pairs(events: list[Mapping[str, Any]]) -> None:
    controller = [
        event
        for event in events
        if event.get("kind") == "controller_loop_event_v1"
    ]

    assert len(controller) >= 2
    assert len(controller) % 2 == 0

    for i in range(0, len(controller), 2):
        start = controller[i]
        end = controller[i + 1]

        assert start["name"] == "controller.loop.start"
        assert end["name"] == "controller.loop.end"
        assert start["phase"] == "start"
        assert end["phase"] == "end"
        assert start["dispatch_id"] == end["dispatch_id"]
        assert start["event_id"] != end["event_id"]
        assert start["payload"]["timestamp"] == start["emitted_at"]
        assert end["payload"]["timestamp"] == end["emitted_at"]
        assert isinstance(start["payload"]["U"], dict)
        assert isinstance(end["payload"]["U"], dict)


def _assert_board_matches_unmodulated_queue(
    *,
    sid: str,
    board: AppBoard,
) -> list[Dict[str, Any]]:
    queue = get_live_session_events(
        session_id=sid,
        role=None,
    )

    assert _event_ids(queue) == _event_ids(board.all_events)
    return queue


# =============================================================================
# Active-shell grammar helpers
# =============================================================================

def _active_micro_rows(decl: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """
    Return the structured micros for the current shell.

    Generated fillers must route from the active input grammar, never from
    incidental title text, stale metadata, tags, or history.
    """
    datum_args = (
        decl.get("datum_args")
        if isinstance(decl.get("datum_args"), Mapping)
        else {}
    )

    candidates = (
        datum_args.get("micro_input_fields"),
        datum_args.get("micros"),
        decl.get("micro_input_fields"),
        decl.get("micros"),
    )

    for candidate in candidates:
        if not isinstance(candidate, list):
            continue

        rows = [
            dict(row)
            for row in candidate
            if isinstance(row, Mapping)
        ]
        if rows:
            return rows

    return []


def _active_micro_names(decl: Mapping[str, Any]) -> set[str]:
    names = {
        str(row.get("name") or "").strip()
        for row in _active_micro_rows(decl)
    }
    names.discard("")
    return names


# =============================================================================
# Micro, lifecycle, and optional event-declaration helpers
# =============================================================================

def _text(name: str, *, min_words: int | None = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": name,
        "type": "text",
        "required": True,
    }
    if min_words is not None:
        out["validators"] = [{
            "path": "_thinkprogram._iomicrosTM.validators.text:min_words",
            "args": {"min_words": int(min_words)},
        }]
    return out


def _select(name: str, options: list[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "select",
        "required": True,
        "validators": [{
            "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
            "args": {"options": list(options)},
        }],
    }


def _lifecycle(
    fill_data: Mapping[str, Any],
    *,
    widget: str,
) -> Dict[str, Any]:
    out = dict(dict(fill_data["fill_shell"]).get("lifecycle") or {})
    out["widget"] = widget
    out["mount_explode"] = True
    out["max_reexplosions"] = 100
    out["max_messages"] = 8
    out["max_proc_notes"] = 0
    return out


def _event_decl(
    name: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "name": name,
        "channel": "ui",
        "audience": "app-board",
        "payload": dict(payload),
    }


def _reexplode(
    *,
    next_fill_shell: Mapping[str, Any],
    pre_computed_fills: Mapping[str, Any],
    prefill_hints: Optional[Mapping[str, Any]] = None,
    events: Optional[list[Mapping[str, Any]]] = None,
) -> Reexplode:
    """
    Compatibility helper for eventful Reexplode returns.

    Current ThinkWidgetTM wrappers may carry returned event declarations from
    Reexplode. The helper uses the keyword form when available and falls back to
    attaching an events attribute for older dataclass-style implementations.
    """
    kwargs = {
        "next_fill_shell": dict(next_fill_shell),
        "pre_computed_fills": dict(pre_computed_fills),
    }
    if prefill_hints is not None:
        kwargs["prefill_hints"] = dict(prefill_hints)

    event_rows = [dict(event) for event in list(events or [])]

    try:
        return Reexplode(
            **kwargs,
            events=event_rows,
        )
    except TypeError:
        out = Reexplode(**kwargs)
        try:
            setattr(out, "events", event_rows)
        except Exception:
            pass
        return out


# =============================================================================
# ThinkWidgetTM classes
# =============================================================================

@thinkwidgetTM_config(
    W_COLLECT,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={},
)
class CollectWidget(DatumLifecycleWidget):
    """
    Maker-owned two-phase datum.

        mount
          -> requirement shell
          -> generated requirement fill
          -> confirmation shell
          -> generated decision fill
          -> done

    This datum therefore needs two generated dispatches despite appearing only
    once on one ThinkProgramTM span.
    """

    def _on_mount(self, position, fill_data, limits, stats):
        self.phase = "requirements"

        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Write a complete implementation requirement",
                "micros": [_text("requirement", min_words=3)],
                "lifecycle": _lifecycle(fill_data, widget=W_COLLECT),
            },
            pre_computed_fills={"requirement": ""},
            prefill_hints={
                "requirement": (
                    "Implement deterministic bounded chain reactions"
                ),
            },
            events=[
                _event_decl(
                    "collect.mount.requirement_shell",
                    {
                        "widget": W_COLLECT,
                        "phase": "requirements",
                    },
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        current = dict(fill_data["current_fills"])

        if self.phase == "requirements":
            self.requirement = current["requirement"]
            self.phase = "confirm"

            return _reexplode(
                next_fill_shell={
                    "id": position["datum_id"],
                    # Deliberately contains "requirement". A bad filler that
                    # scans title text instead of active micros will misroute.
                    "title": "Confirm requirement",
                    "micros": [_select("decision", ["yes", "revise"])],
                    "lifecycle": _lifecycle(fill_data, widget=W_COLLECT),
                },
                pre_computed_fills={"decision": ""},
                prefill_hints={"decision": "yes"},
                events=[
                    _event_decl(
                        "collect.reexplode.confirm_shell",
                        {
                            "widget": W_COLLECT,
                            "phase": "confirm",
                        },
                    )
                ],
            )

        if self.phase == "confirm":
            decision = current["decision"]

            if decision == "revise":
                self.phase = "requirements"
                return _reexplode(
                    next_fill_shell={
                        "id": position["datum_id"],
                        "title": "Rewrite a complete implementation requirement",
                        "micros": [_text("requirement", min_words=3)],
                        "lifecycle": _lifecycle(fill_data, widget=W_COLLECT),
                    },
                    pre_computed_fills={
                        "requirement": self.requirement,
                    },
                    events=[
                        _event_decl(
                            "collect.reexplode.revise_shell",
                            {
                                "widget": W_COLLECT,
                                "phase": "requirements",
                            },
                        )
                    ],
                )

            self.commit = {
                "requirement": self.requirement,
                "decision": decision,
            }
            self.phase = "done"
            return True

        raise AssertionError(f"unexpected collect phase: {self.phase!r}")


@thinkwidgetTM_config(
    W_REVIEW,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={
        "prior_requirement": {
            "multiplicity": "one",
            "required": True,
        },
    },
)
class ReviewWidget(DatumLifecycleWidget):
    """
    Human reviewer datum.

    On mount it consumes the maker's committed lifecycle state through a
    ThinkProgramTM history wire.
    """

    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        kernel = dict(args.get("__kernel") or {})
        past_wires = dict(kernel.get("past_wires") or {})

        prior = dict(past_wires.get("prior_requirement") or {})
        value = dict(prior.get("value") or {})
        state = dict(value.get("state") or {})

        self.requirement_seen = state.get("requirement")

        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Human correctness review",
                "micros": [_select("approval", ["approve", "reject"])],
                "lifecycle": _lifecycle(fill_data, widget=W_REVIEW),
            },
            pre_computed_fills={"approval": ""},
            prefill_hints={"approval": "approve"},
            events=[
                _event_decl(
                    "review.mount.approval_shell",
                    {
                        "widget": W_REVIEW,
                        "saw_requirement": bool(self.requirement_seen),
                    },
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.approval = dict(fill_data["current_fills"])["approval"]
        self.commit = {
            "approval": self.approval,
            "requirement_seen": self.requirement_seen,
        }
        return True


@thinkwidgetTM_config(
    W_RELEASE,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={
        "prior_review": {
            "multiplicity": "one",
            "required": True,
        },
    },
)
class ReleaseWidget(DatumLifecycleWidget):
    """
    Machine release datum after the human barrier.

    It consumes the review lifecycle row and proves that generated execution can
    resume automatically after one manual fill in the same outer dispatch.
    """

    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])
        args = dict(shell.get("args") or {})
        kernel = dict(args.get("__kernel") or {})
        past_wires = dict(kernel.get("past_wires") or {})

        prior = dict(past_wires.get("prior_review") or {})
        value = dict(prior.get("value") or {})
        state = dict(value.get("state") or {})

        self.review_approval_seen = state.get("approval")

        return _reexplode(
            next_fill_shell={
                "id": position["datum_id"],
                "title": "Release status",
                "micros": [_select("status", ["released", "blocked"])],
                "lifecycle": _lifecycle(fill_data, widget=W_RELEASE),
            },
            pre_computed_fills={"status": ""},
            prefill_hints={"status": "released"},
            events=[
                _event_decl(
                    "release.mount.status_shell",
                    {
                        "widget": W_RELEASE,
                        "saw_review": bool(self.review_approval_seen),
                    },
                )
            ],
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.status = dict(fill_data["current_fills"])["status"]
        self.commit = {
            "status": self.status,
            "review_approval_seen": self.review_approval_seen,
        }
        return True


# =============================================================================
# FunkTM versions
# =============================================================================

def _register_chainreaction_versions() -> None:
    def validate_smart(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "requirement": str(
                raw.get(
                    "requirement",
                    "Implement deterministic bounded chain reactions",
                )
            ),
        }

    def smart(request: FunkTMRequest) -> FunkTMResult:
        fill: Dict[str, Any] = {}

        for pending in request.pending_datums:
            datum_id = str(pending["datum_id"])
            decl = (
                pending.get("decl")
                if isinstance(pending.get("decl"), Mapping)
                else {}
            )
            names = _active_micro_names(decl)

            if "decision" in names:
                fill[datum_id] = {"decision": "yes"}
            elif "approval" in names:
                fill[datum_id] = {"approval": "approve"}
            elif "status" in names:
                fill[datum_id] = {"status": "released"}
            elif "requirement" in names:
                fill[datum_id] = {
                    "requirement": request.args["requirement"],
                }
            else:
                fill[datum_id] = {"value": "semantically filled"}

        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": "smart_receipt",
                "role": request.role,
                "datum_ids": sorted(fill),
                "semantic_errors_seen": request.semantic_errors_in_row,
                "had_owned_last_error": bool(request.last_error),
            },
        )

    def validate_bad(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "value": str(raw.get("value", "x")),
        }

    def bad(request: FunkTMRequest) -> FunkTMResult:
        fill: Dict[str, Any] = {}

        for pending in request.pending_datums:
            datum_id = str(pending["datum_id"])
            decl = (
                pending.get("decl")
                if isinstance(pending.get("decl"), Mapping)
                else {}
            )
            names = _active_micro_names(decl)

            if "requirement" in names:
                fill[datum_id] = {
                    "requirement": request.args["value"],
                }
            elif "decision" in names:
                fill[datum_id] = {
                    "decision": request.args["value"],
                }
            else:
                fill[datum_id] = {
                    "value": request.args["value"],
                }

        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": "bad_receipt",
                "semantic_errors_seen": request.semantic_errors_in_row,
                "had_owned_last_error": bool(request.last_error),
            },
        )

    def history(request: FunkTMRequest) -> FunkTMResult:
        HISTORY_REQUESTS.append(request)

        fill = {
            str(pending["datum_id"]): {"status": "released"}
            for pending in request.pending_datums
        }

        return FunkTMResult(
            fill=fill,
            signal=None,
            receipt={
                "kind": "history_receipt",
                "history_rows": len(request.history.get("rows") or []),
                "readable_roles": list(
                    request.history.get("readable_roles") or []
                ),
            },
        )

    register_chainreactiontm_version(
        name=FUNK_SMART,
        run=smart,
        validate_args=validate_smart,
        replace=True,
    )
    register_chainreactiontm_version(
        name=FUNK_BAD,
        run=bad,
        validate_args=validate_bad,
        replace=True,
    )
    register_chainreactiontm_version(
        name=FUNK_HISTORY,
        run=history,
        validate_args=lambda raw: {},
        replace=True,
    )


# =============================================================================
# Registration, program, metadata, launch, dispatch
# =============================================================================

def _register_authoring_surface() -> None:
    bootstrap_chainreactiontm_defaults()
    _register_chainreaction_versions()

    for cls in (CollectWidget, ReviewWidget, ReleaseWidget):
        receipt = pull_thinkwidget_class_into_kernel_v1(
            cls,
            overwrite=True,
        )
        assert receipt["ok"] is True

    empty_object = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def _program() -> Dict[str, Any]:
    lifecycle = {
        "mount_explode": True,
        "max_reexplosions": 100,
        "max_messages": 8,
        "max_proc_notes": 0,
    }

    latest_required = {
        "select": "latest",
        "required": True,
        "max_results": 20,
    }

    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "lifecycle": {"value": lifecycle},
            "latest_required": {"value": latest_required},
        },
        "puppeteering": {},
        "run": {
            "program": {
                "info": {
                    "id": PROGRAM_ID,
                    "title": "Highest eventful FunkedSession integration",
                    "description": (
                        "Machine requirement, human review, machine release."
                    ),
                    "args": {},
                },
                "widgets": {
                    "collect": {
                        "widget": W_COLLECT,
                        "title": "Collect",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        "roles": ["maker"],
                        "authoritative": True,
                        "tags": ["machine-before-human"],
                        "system_flags": {},
                    },
                    "review": {
                        "widget": W_REVIEW,
                        "title": "Review",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {
                            "prior_requirement": {
                                "from": "collect",
                                "history": "$latest_required",
                            },
                        },
                        "roles": ["reviewer"],
                        "authoritative": True,
                        "tags": ["manual-barrier"],
                        "system_flags": {},
                    },
                    "release": {
                        "widget": W_RELEASE,
                        "title": "Release",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {
                            "prior_review": {
                                "from": "review",
                                "history": "$latest_required",
                            },
                        },
                        "roles": ["release_ai"],
                        "authoritative": True,
                        "tags": ["machine-after-human"],
                        "system_flags": {},
                    },
                },
                "flow": [
                    {
                        "id": "collect",
                        "title": "Collect requirement",
                        "widgets": ["collect"],
                        "authoritative": [True],
                        "overrides": {},
                    },
                    {
                        "id": "review",
                        "title": "Review requirement",
                        "widgets": ["review"],
                        "authoritative": [True],
                        "overrides": {},
                    },
                    {
                        "id": "release",
                        "title": "Release",
                        "widgets": ["release"],
                        "authoritative": [True],
                        "overrides": {},
                    },
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                },
            },
        },
    }


def _metadata(
    *,
    maker_version: str | None = FUNK_SMART,
    reviewer_version: str | None = None,
    release_version: str | None = FUNK_HISTORY,
    include_global_chainreactiontm_config: bool = True,
    max_semantic_errors_in_a_row: int = 2,
    max_fills_on_a_span: int = 8,
    max_fills_e2e: int = 32,
    events_queue_length: int = 0,
) -> Dict[str, Any]:
    def role(
        label: str,
        version: str | None,
        *,
        read_roles: tuple[str, ...] = (),
    ) -> Dict[str, Any]:
        return {
            "label": label,
            "read_roles": list(read_roles),
            "chainreactionTM_config": (
                {
                    "version": version,
                    "args": {},
                }
                if version is not None
                else None
            ),
        }

    meta: Dict[str, Any] = {
        "roles": {
            "maker": role(
                "Maker",
                maker_version,
            ),
            "reviewer": role(
                "Reviewer",
                reviewer_version,
                read_roles=("maker",),
            ),
            "release_ai": role(
                "Release AI",
                release_version,
                read_roles=("maker", "reviewer"),
            ),
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
                "release_ai": "redacted",
            },
        },
    }

    if include_global_chainreactiontm_config:
        meta["chainreactionTM_config"] = {
            "version": "chainreaction1.0",
            "roles_ordered": [
                "maker",
                "reviewer",
                "release_ai",
            ],
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": (
                max_semantic_errors_in_a_row
            ),
            "max_fills_on_a_span": max_fills_on_a_span,
            "max_fills_e2e": max_fills_e2e,
            "history_tail_cap": 4,
            "history_size_cap": 25_000,
            "events_queue_length": int(events_queue_length),
        }

    return meta


def _launch(metadata: Mapping[str, Any]) -> str:
    _register_authoring_surface()

    created = create_core_session_from_program(
        program=_program(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata=dict(metadata),
    )

    assert created["ok"] is True
    return str(created["session_id"])


def _dispatch_chain(
    sid: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    return dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        **kwargs,
    )


# =============================================================================
# Documentation-as-data tests
# =============================================================================

def test_contract_matrix_is_dead_json_and_covers_the_complete_highest_seam() -> None:
    matrix = {
        "widget_automaton": [
            "mount creates first shell",
            "active micros define admissible action",
            "fill may reexplode",
            "True enters done sink",
            "self state becomes wire-readable lifecycle history",
            "widget may emit live datum lifecycle events",
        ],
        "program": [
            "one flow item lowers to one step",
            "one current span per step",
            "authoritative datums gate advancement",
            "roles attach to datum appearances",
            "wires consume prior lifecycle rows",
        ],
        "dispatch": [
            "single dispatch",
            "single dispatch plus chain reaction dispatches",
            "controller start/end per dispatch",
            "event callback board",
            "bounded session event queue",
            "high-facade queue inspection",
        ],
        "chainreactioned_session": [
            "static role coherence",
            "ordered role scheduling",
            "manual barrier",
            "generated role-bound dispatch",
            "semantic feedback",
            "span and e2e caps",
            "bounded readable history",
            "bounded role-projected event tail",
        ],
        "applications": [
            "callback-first app",
            "queue-first app",
            "dispatch-return-first app",
            "hybrid callback and return app",
            "machine human machine",
        ],
        "membrane": [
            "service-safe response",
            "bounded receipt",
            "no raw runtime state",
            "explicit queue endpoint for event inspection",
        ],
    }

    json.dumps(matrix, sort_keys=True)

    assert "widget may emit live datum lifecycle events" in matrix["widget_automaton"]
    assert "high-facade queue inspection" in matrix["dispatch"]
    assert "machine human machine" in matrix["applications"]


def test_active_shell_grammar_helper_never_routes_from_incidental_title_text() -> None:
    confirmation_decl = {
        "title": "Confirm requirement",
        "datum_args": {
            "micro_input_fields": [
                {
                    "name": "decision",
                    "type": "select",
                }
            ]
        },
    }

    assert _active_micro_names(confirmation_decl) == {"decision"}
    assert "requirement" in confirmation_decl["title"].lower()

    nested_wins = {
        "micros": [{"name": "stale_outer"}],
        "datum_args": {
            "micro_input_fields": [
                {"name": "approval", "type": "select"},
            ],
        },
    }
    assert _active_micro_names(nested_wins) == {"approval"}

    compatibility_fallback = {
        "micros": [
            {"name": "status", "type": "select"},
        ],
    }
    assert _active_micro_names(compatibility_fallback) == {"status"}


# =============================================================================
# Semantic ownership regression
# =============================================================================

def test_semantic_error_classifier_ignores_retained_error_after_progress() -> None:
    before = {
        "kind": "MANUALFILLNEEDEDSTEP",
        "current_span": "span",
        "datum_widgets_on_this_span": ["collect"],
        "datum_widget_decls": {
            "collect": {"micros": [{"name": "requirement"}]},
        },
        "datum_widget_fills": {
            "collect": {"requirement": ""},
        },
        "state": {
            "datum_lifecycle_epoch": 1,
        },
        "last_error": {
            "collect": "old error",
        },
    }

    after_progress = {
        **before,
        "datum_widget_decls": {
            "collect": {"micros": [{"name": "decision"}]},
        },
        "datum_widget_fills": {
            "collect": {"decision": ""},
        },
        "state": {
            "datum_lifecycle_epoch": 2,
        },
        "last_error": {
            "collect": "old error",
        },
    }

    after_no_progress = {
        **before,
        "last_error": {
            "collect": "requirement must contain at least 3 words",
        },
    }

    assert _generated_dispatch_had_fresh_semantic_error(
        before_ctx=before,
        after_ctx=after_progress,
    ) is False

    assert _generated_dispatch_had_fresh_semantic_error(
        before_ctx=before,
        after_ctx=after_no_progress,
    ) is True


# =============================================================================
# Main event and dispatch E2E flows
# =============================================================================

def test_single_dispatch_live_events_and_queue_without_chain_reaction() -> None:
    """
    Single-dispatch usage.

    This is the higher-app shape for code that wants only:

        dispatch_live_session_action(...)

    and then uses either callback events, queue events, or the dispatch return.
    """
    sid = _launch(
        _metadata(
            include_global_chainreactiontm_config=False,
            maker_version=None,
            reviewer_version=None,
            release_version=None,
        )
    )
    board = AppBoard()

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=None,
        threaded_callbacks=board.callbacks(),
    )

    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert packet["finished"] is False

    assert [event["name"] for event in board.controller_events] == [
        "controller.loop.start",
        "controller.loop.end",
    ]

    _assert_controller_pairs(board.all_events)

    queue = _assert_board_matches_unmodulated_queue(
        sid=sid,
        board=board,
    )
    assert _event_ids(queue[-2:]) == _event_ids(board.all_events[-2:])

    latest_two = get_live_session_events(
        session_id=sid,
        role=None,
        limit=2,
    )
    assert _event_ids(latest_two) == _event_ids(queue[-2:])


def test_chain_reaction_events_board_and_queue_match_machine_human_machine() -> None:
    """
    Outer dispatch 1:
        - initial caller dispatch reaches collect;
        - maker performs requirement fill;
        - collect reexplodes;
        - maker performs decision fill;
        - chain stops at manual reviewer.

    Outer dispatch 2:
        - reviewer submits manual approval;
        - release_ai resumes automatically;
        - program completes.

    Both dispatch waves prove that the live callback board and the high-facade
    queue view agree exactly by event_id.
    """
    HISTORY_REQUESTS.clear()
    sid = _launch(_metadata())

    board1 = AppBoard()
    first = _dispatch_chain(
        sid,
        threaded_callbacks=board1.callbacks(),
    )
    receipt1 = first["chainreactionTM_receipt"]

    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert receipt1["generated_fills_e2e"] == 2
    assert receipt1["roles_used"] == ["maker", "maker"]
    assert receipt1["stopped_reason"] == "next_pending_role_unchainreactioned"

    _assert_controller_pairs(board1.all_events)
    queue1 = _assert_board_matches_unmodulated_queue(
        sid=sid,
        board=board1,
    )

    assert len(_events_named(queue1, "controller.loop.start")) == 3
    assert len(_events_named(queue1, "controller.loop.end")) == 3

    # The sheet intentionally demonstrates widget-side lifecycle emissions, but
    # older ThinkWidgetTM wrappers may ignore returned event declarations. When
    # the wrapper supports returned declarations, these events prove datum-level
    # events are interleaved between controller start/end packets.
    datum_event_names = [
        str(event.get("name"))
        for event in queue1
        if event.get("kind") == "datum_lifecycle_event_v1"
    ]
    if datum_event_names:
        assert "collect.mount.requirement_shell" in datum_event_names
        assert "collect.reexplode.confirm_shell" in datum_event_names

    reviewer_ctx = get_live_session_context(
        session_id=sid,
        role="reviewer",
    )
    assert reviewer_ctx["datum_widgets_on_this_span"] == ["review"]

    assignments = {
        row["datum_id"]: row
        for row in reviewer_ctx[
            "role_mismatch_modulation_info"
        ]["assignments"]
    }
    assert assignments["review"]["roles"] == ["reviewer"]

    board2 = AppBoard()
    second = _dispatch_chain(
        sid,
        role="reviewer",
        user_fill={
            "review.approval": "approve",
        },
        threaded_callbacks=board2.callbacks(),
    )
    receipt2 = second["chainreactionTM_receipt"]

    assert second["event_kind"] == "ATCOMPLETION"
    assert receipt2["roles_used"] == ["release_ai"]
    assert receipt2["generated_fills_e2e"] == 1

    queue_all = get_live_session_events(
        session_id=sid,
        role=None,
    )
    assert _event_ids(queue_all[-len(board2.all_events):]) == _event_ids(
        board2.all_events
    )
    _assert_controller_pairs(board2.all_events)

    assert HISTORY_REQUESTS
    release_request = HISTORY_REQUESTS[-1]

    assert set(release_request.history["readable_roles"]) == {
        "maker",
        "reviewer",
        "release_ai",
    }
    assert any(
        row.get("role") == "reviewer"
        for row in release_request.history.get("rows") or []
    )
    assert release_request.events == []


def test_chain_reaction_funk_events_tail_is_role_projected_for_filler_role() -> None:
    HISTORY_REQUESTS.clear()
    sid = _launch(_metadata(events_queue_length=4))

    _dispatch_chain(sid)
    second = _dispatch_chain(
        sid,
        role="reviewer",
        user_fill={"review.approval": "approve"},
    )

    assert second["event_kind"] == "ATCOMPLETION"
    request = HISTORY_REQUESTS[-1]
    assert 0 < len(request.events) <= 4
    assert (
        request.events[-1]["payload"]["U"]
        ["role_mismatch_modulation_info"]["role_viewing"]
        == "release_ai"
    )


def test_chain_reaction_endpoint_without_global_config_performs_only_initial_dispatch() -> None:
    """
    If the session metadata has no global chainreactionTM_config, the chain
    endpoint remains legal but generated chain reaction is disabled.
    """
    sid = _launch(
        _metadata(
            include_global_chainreactiontm_config=False,
            maker_version=FUNK_SMART,
            reviewer_version=None,
            release_version=FUNK_HISTORY,
        )
    )
    board = AppBoard()

    packet = _dispatch_chain(
        sid,
        threaded_callbacks=board.callbacks(),
    )
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert receipt["enabled"] is False

    # Only the caller dispatch ran. No generated maker fill happened.
    assert [event["name"] for event in board.controller_events] == [
        "controller.loop.start",
        "controller.loop.end",
    ]

    queue = _assert_board_matches_unmodulated_queue(
        sid=sid,
        board=board,
    )
    assert len(_events_named(queue, "controller.loop.start")) == 1
    assert len(_events_named(queue, "controller.loop.end")) == 1


def test_call_level_chainreactiontm_config_none_disables_chain_reaction_for_that_call() -> None:
    """
    Even when session metadata has a global chain-reaction pocket, a caller may
    disable generated continuation for one call.
    """
    sid = _launch(_metadata())
    board = AppBoard()

    packet = _dispatch_chain(
        sid,
        chainreactionTM_config=None,
        threaded_callbacks=board.callbacks(),
    )
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert receipt["enabled"] is False

    assert [event["name"] for event in board.controller_events] == [
        "controller.loop.start",
        "controller.loop.end",
    ]

    queue = _assert_board_matches_unmodulated_queue(
        sid=sid,
        board=board,
    )
    assert len(_events_named(queue, "controller.loop.start")) == 1
    assert len(_events_named(queue, "controller.loop.end")) == 1


def test_all_roles_chainreactioned_is_pure_machine_e2e_with_event_queue() -> None:
    sid = _launch(
        _metadata(
            reviewer_version=FUNK_SMART,
            release_version=FUNK_SMART,
        )
    )
    board = AppBoard()

    packet = _dispatch_chain(
        sid,
        threaded_callbacks=board.callbacks(),
    )
    receipt = packet["chainreactionTM_receipt"]

    assert packet["event_kind"] == "ATCOMPLETION"
    assert receipt["roles_used"] == [
        "maker",
        "maker",
        "reviewer",
        "release_ai",
    ]
    assert receipt["generated_fills_e2e"] == 4
    assert receipt["stopped_reason"] == "program_complete_or_not_manual"

    _assert_controller_pairs(board.all_events)

    queue = _assert_board_matches_unmodulated_queue(
        sid=sid,
        board=board,
    )
    assert len(_events_named(queue, "controller.loop.start")) == 5
    assert len(_events_named(queue, "controller.loop.end")) == 5


def test_event_queue_role_projection_modulates_controller_payload_U_without_mutating_queue() -> None:
    """
    Controller events are stored unmodulated.

    The high queue endpoint can project controller payload.U for a role-specific
    caller. The event ids stay identical; only the returned view of payload.U is
    role projected.
    """
    sid = _launch(_metadata())
    board = AppBoard()

    _dispatch_chain(
        sid,
        threaded_callbacks=board.callbacks(),
    )

    raw_queue = get_live_session_events(
        session_id=sid,
        role=None,
    )
    reviewer_queue = get_live_session_events(
        session_id=sid,
        role="reviewer",
    )
    raw_queue_again = get_live_session_events(
        session_id=sid,
        role=None,
    )

    assert _event_ids(raw_queue) == _event_ids(reviewer_queue)
    assert _event_ids(raw_queue) == _event_ids(raw_queue_again)

    raw_controller_end = [
        event
        for event in raw_queue
        if event.get("kind") == "controller_loop_event_v1"
        and event.get("name") == "controller.loop.end"
    ][-1]
    reviewer_controller_end = [
        event
        for event in reviewer_queue
        if event.get("kind") == "controller_loop_event_v1"
        and event.get("name") == "controller.loop.end"
    ][-1]

    raw_U = raw_controller_end["payload"]["U"]
    reviewer_U = reviewer_controller_end["payload"]["U"]

    assert raw_U.get("role_mismatch_modulation_info") is None
    assert (
        reviewer_U["role_mismatch_modulation_info"]["role_viewing"]
        == "reviewer"
    )

    # The raw queue view was not mutated by the role-projected read.
    raw_u_payload = raw_queue_again[
        raw_queue.index(raw_controller_end)
    ]["payload"]["U"]

    assert raw_u_payload.get("role_mismatch_modulation_info") is None


# =============================================================================
# Error and cap behavior
# =============================================================================

def test_bad_chainreaction_receives_owned_last_error_then_hits_semantic_cap() -> None:
    metadata = _metadata(
        maker_version=FUNK_BAD,
        reviewer_version=None,
        release_version=None,
        max_semantic_errors_in_a_row=1,
        max_fills_on_a_span=8,
    )
    metadata["roles"]["maker"]["chainreactionTM_config"]["args"] = {
        "value": "x",
    }

    sid = _launch(metadata)

    with pytest.raises(FunkMaxSemanticErrorsExceeded):
        _dispatch_chain(sid)


def test_valid_reexplosion_is_bounded_by_span_cap() -> None:
    """
    CollectWidget requires two valid generated fills on one span. A cap of one
    proves max_fills_on_a_span bounds productive reexplosion loops too.
    """
    sid = _launch(
        _metadata(
            max_fills_on_a_span=1,
            max_fills_e2e=16,
        )
    )

    with pytest.raises(FunkMaxFillsOnSpanExceeded):
        _dispatch_chain(sid)


def test_missing_per_role_config_is_static_and_pre_mutation() -> None:
    metadata = _metadata()
    del metadata["roles"]["reviewer"]["chainreactionTM_config"]

    sid = _launch(metadata)

    before = get_live_session_context(
        session_id=sid,
        role="maker",
    )

    with pytest.raises(FunkRoleConfigMissingStaticError):
        _dispatch_chain(sid)

    after = get_live_session_context(
        session_id=sid,
        role="maker",
    )

    # Validation happens before the initial action is dispatched.
    assert after.get("kind") == before.get("kind")
    assert after.get("current_span") == before.get("current_span")
    assert after.get("cursor") == before.get("cursor")


# =============================================================================
# Service membrane
# =============================================================================

def test_service_packet_never_exposes_raw_context_or_state() -> None:
    sid = _launch(
        _metadata(
            reviewer_version=FUNK_SMART,
            release_version=FUNK_SMART,
        )
    )

    packet = _dispatch_chain(sid)

    # Round-trip through JSON to prove the returned artifact is dead-data-like.
    packet = json.loads(
        json.dumps(packet, sort_keys=True, default=str)
    )

    forbidden_keys = {
        "ctx",
        "raw_ctx",
        "context",
        "raw_context",
        "snapshot",
        "program_map",
        "state",
        "raw_state",
        "globals",
        "history",
        "datum_widget_decls",
        "datum_widget_fills",
    }

    def assert_safe(
        value: Any,
        *,
        parent_key: str | None = None,
        path: tuple[str, ...] = (),
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = (*path, key)

                if key in forbidden_keys:
                    safe_count = (
                        parent_key == "counts"
                        and (
                            child is None
                            or (
                                isinstance(child, int)
                                and not isinstance(child, bool)
                            )
                        )
                    )
                    safe_readable_roles = (
                        key == "history"
                        and isinstance(child, (str, int, bool, type(None)))
                    )
                    assert safe_count or safe_readable_roles, (
                        "Service packet exposed forbidden runtime field at "
                        f"{'.'.join(child_path)}"
                    )

                assert_safe(
                    child,
                    parent_key=key,
                    path=child_path,
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                assert_safe(
                    child,
                    parent_key=parent_key,
                    path=(*path, str(index)),
                )

    assert_safe(packet)


def test_high_facade_event_queue_is_explicitly_not_the_service_packet() -> None:
    """
    Event queue inspection is deliberately a separate high-facade read endpoint.

    Dispatch returns stay service-safe and small. Apps that intentionally want
    controller payload.U and datum event packets call get_live_session_events.
    """
    sid = _launch(_metadata())
    board = AppBoard()

    packet = _dispatch_chain(
        sid,
        threaded_callbacks=board.callbacks(),
    )
    events = get_live_session_events(
        session_id=sid,
        role=None,
    )

    assert "ctx" not in packet
    assert "snapshot" not in packet
    assert events
    assert any(
        event.get("kind") == "controller_loop_event_v1"
        for event in events
    )