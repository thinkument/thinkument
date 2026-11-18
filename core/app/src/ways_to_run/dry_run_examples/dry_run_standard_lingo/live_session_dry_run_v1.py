from __future__ import annotations

"""Strategy-agnostic live-session dry-run machinery, version 1.

P / SM / C / A / E are the stable dry-run language.  This module owns the
language execution law and expectation law, but it does not know how a run is
hosted.  All concrete run/read/write operations go through ``BaseDryRunStrategy``.

Execution law
-------------

* One case stops at its first failing action.
* A suite still executes every case.
* Every started run is closed in ``finally``.
* Ordinary actions are asserted through one canonical controller envelope.
* Preflight exception/rejection attempts are asserted to be eventless.
* Optional named-role views scan the same committed canonical interval.
* Optional data blankets compare live epsilon packets, dispatch receipts,
  committed theta pages, and role-projected Q/U reads.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunRunHandleV1,
)

from .action_specs_v1 import (
    DRY_RUN_ACTION_KIND_ORDINARY_V1,
    DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1,
    DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1,
)
from .data_blanket_expectations_v1 import (
    DATA_BLANKET_CONTEXT_VIEW_KIND_V1,
    DATA_BLANKET_EXPECTATION_KIND_V1,
)
from .expectation_matching_v1 import (
    assert_needle_v1,
    assert_ordered_subsequence_v1,
)
from .protocol_v1 import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    SESSION_EVENT_KIND_V1,
    assert_standard_event_v1,
    assert_strict_canonical_event_order_v1,
)


DRY_RUN_CASE_KIND_V1 = "live_session_dry_run_case_v1"
DRY_RUN_CASE_RECEIPT_KIND_V1 = "live_session_dry_run_case_receipt_v1"
DRY_RUN_SUITE_RECEIPT_KIND_V1 = "live_session_dry_run_suite_receipt_v1"


@dataclass(frozen=True, slots=True)
class DryRunCaseV1:
    name: str
    program: Mapping[str, Any]
    actions: Sequence[Mapping[str, Any]]
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None
    session_metadata: Optional[Mapping[str, Any]] = None

    @property
    def kind(self) -> str:
        return DRY_RUN_CASE_KIND_V1


@dataclass(frozen=True, slots=True)
class DryRunCaseReceiptV1:
    name: str
    ok: bool
    completed_actions: int
    latest_event_seq: int
    failed_action_index: Optional[int] = None
    failed_action_note: Optional[str] = None
    exception_type: Optional[str] = None
    error: Optional[str] = None

    @property
    def kind(self) -> str:
        return DRY_RUN_CASE_RECEIPT_KIND_V1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "ok": self.ok,
            "completed_actions": self.completed_actions,
            "latest_event_seq": self.latest_event_seq,
            "failed_action_index": self.failed_action_index,
            "failed_action_note": self.failed_action_note,
            "exception_type": self.exception_type,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class DryRunSuiteReceiptV1:
    cases: tuple[DryRunCaseReceiptV1, ...]
    strategy_name: str

    @property
    def kind(self) -> str:
        return DRY_RUN_SUITE_RECEIPT_KIND_V1

    @property
    def failures(self) -> tuple[DryRunCaseReceiptV1, ...]:
        return tuple(case for case in self.cases if not case.ok)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "ok": self.ok,
            "strategy_name": self.strategy_name,
            "cases": [case.to_dict() for case in self.cases],
        }


def _require_strategy(strategy: BaseDryRunStrategy) -> BaseDryRunStrategy:
    if not isinstance(strategy, BaseDryRunStrategy):
        raise TypeError("strategy must inherit BaseDryRunStrategy")
    if not str(strategy.strategy_name or "").strip():
        raise ValueError("strategy.strategy_name must be non-empty")
    return strategy


def validate_dry_run_case_v1(case: DryRunCaseV1) -> None:
    if not isinstance(case, DryRunCaseV1):
        raise TypeError("case must be DryRunCaseV1")
    if not str(case.name or "").strip():
        raise ValueError("dry-run case name must be non-empty")
    if not isinstance(case.program, Mapping):
        raise TypeError("dry-run case program must be a mapping")
    if case.initial_parameter_overrides is not None and not isinstance(
        case.initial_parameter_overrides, Mapping
    ):
        raise TypeError("initial_parameter_overrides must be a mapping or None")
    if case.session_metadata is not None and not isinstance(
        case.session_metadata, Mapping
    ):
        raise TypeError("session_metadata must be a mapping or None")
    if isinstance(case.actions, (str, bytes, bytearray)):
        raise TypeError("dry-run case actions must be a sequence of mappings")

    allowed = {
        DRY_RUN_ACTION_KIND_ORDINARY_V1,
        DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1,
        DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1,
    }
    for index, raw_action in enumerate(case.actions, start=1):
        if not isinstance(raw_action, Mapping):
            raise TypeError(f"action {index} must be a mapping")
        action_kind = str(raw_action.get("kind") or "")
        if action_kind not in allowed:
            raise ValueError(
                f"action {index} has unknown dry-run kind {action_kind!r}"
            )
        if not isinstance(raw_action.get("A"), Mapping):
            raise TypeError(f"action {index}.A must be a mapping")

        if action_kind == DRY_RUN_ACTION_KIND_ORDINARY_V1:
            if not isinstance(raw_action.get("E"), Mapping):
                raise TypeError(f"action {index}.E must be a mapping")
            views = raw_action.get("views", [])
            if not isinstance(views, list):
                raise TypeError(f"action {index}.views must be a list")
            blanket = raw_action.get("blanket", {})
            if not isinstance(blanket, Mapping):
                raise TypeError(f"action {index}.blanket must be a mapping")
            if blanket:
                if blanket.get("kind") != DATA_BLANKET_EXPECTATION_KIND_V1:
                    raise ValueError(
                        f"action {index}.blanket has unknown kind "
                        f"{blanket.get('kind')!r}"
                    )
                for key in ("dispatch", "canonical_page"):
                    if not isinstance(blanket.get(key, {}), Mapping):
                        raise TypeError(
                            f"action {index}.blanket.{key} must be a mapping"
                        )
                live = blanket.get("live")
                if live is not None and not isinstance(live, Mapping):
                    raise TypeError(
                        f"action {index}.blanket.live must be a mapping or None"
                    )
                contexts = blanket.get("contexts", [])
                if not isinstance(contexts, list):
                    raise TypeError(
                        f"action {index}.blanket.contexts must be a list"
                    )
                for context_index, context in enumerate(contexts, start=1):
                    if not isinstance(context, Mapping):
                        raise TypeError(
                            f"action {index}.blanket.contexts"
                            f"[{context_index}] must be a mapping"
                        )
                    if context.get("kind") != DATA_BLANKET_CONTEXT_VIEW_KIND_V1:
                        raise ValueError(
                            f"action {index}.blanket.contexts"
                            f"[{context_index}] has unknown kind"
                        )
                    if not isinstance(context.get("U"), Mapping):
                        raise TypeError(
                            f"action {index}.blanket.contexts"
                            f"[{context_index}].U must be a mapping"
                        )
        elif action_kind == DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1:
            expected_exception = raw_action.get("exception")
            if not isinstance(expected_exception, Mapping):
                raise TypeError(f"action {index}.exception must be a mapping")
            if not str(expected_exception.get("type") or "").strip():
                raise ValueError(f"action {index}.exception.type is required")
        else:
            if not str(raw_action.get("rejection_kind") or "").strip():
                raise ValueError(f"action {index}.rejection_kind is required")


def _resolve_cursor(
    raw: Any,
    *,
    cursors: Mapping[str, int],
    current: int,
) -> Any:
    if isinstance(raw, str) and raw.startswith("$"):
        name = raw[1:]
        if name not in cursors:
            raise KeyError(f"unknown saved cursor: {name!r}")
        return int(cursors[name])
    if isinstance(raw, Mapping) and "future_of_current" in raw:
        return current + int(raw["future_of_current"])
    return raw


def _dispatch_identity_v1(
    *,
    case_name: str,
    action_index: int,
    A: Mapping[str, Any],
    prefix: str,
) -> str:
    explicit = str(A.get("identity_id") or "").strip()
    if explicit:
        return explicit
    return f"{prefix}.{case_name}.action-{action_index}"


def _resolved_A_v1(
    *,
    case_name: str,
    action_index: int,
    A: Mapping[str, Any],
    cursor_value: Any,
    dispatcher_identity_prefix: str,
) -> Dict[str, Any]:
    out = deepcopy(dict(A))
    out["identity_id"] = _dispatch_identity_v1(
        case_name=case_name,
        action_index=action_index,
        A=A,
        prefix=dispatcher_identity_prefix,
    )
    out["my_current_event_seq_number"] = deepcopy(cursor_value)
    return out


def _assert_action_event_group(
    events: list[Mapping[str, Any]],
    expected: Mapping[str, Any],
    *,
    require_contiguous_canonical_interval: bool = True,
) -> None:
    if len(events) < 2:
        raise AssertionError(
            "an admitted action must emit controller start and end; "
            f"actual={events!r}"
        )

    if require_contiguous_canonical_interval:
        assert_strict_canonical_event_order_v1(events, contiguous=True)
    else:
        assert_strict_canonical_event_order_v1(events, contiguous=False)

    start = events[0]
    end = events[-1]
    middle = events[1:-1]

    if start.get("kind") != CONTROLLER_LOOP_EVENT_KIND_V1:
        raise AssertionError(f"first event is not controller start: {start!r}")
    if end.get("kind") != CONTROLLER_LOOP_EVENT_KIND_V1:
        raise AssertionError(f"last event is not controller end: {end!r}")

    assert_needle_v1(
        start,
        dict(expected.get("Estart") or {}),
        label="Estart",
    )
    assert_needle_v1(
        end,
        dict(expected.get("Eend") or {}),
        label="Eend",
    )

    assert start["phase"] == "start"
    assert end["phase"] == "end"
    assert start["dispatch_id"] == end["dispatch_id"]
    assert start["event_id"] != end["event_id"]
    assert start["action"] == end["action"]

    for event in middle:
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1:
            raise AssertionError(
                "another controller packet appeared inside one envelope: "
                f"{dict(event)!r}"
            )
        if (
            "dispatch_id" in event
            and event["dispatch_id"] != start["dispatch_id"]
        ):
            raise AssertionError(
                "informative packet has a different dispatch_id: "
                f"{dict(event)!r}"
            )
        if event.get("kind") == SESSION_EVENT_KIND_V1:
            assert_standard_event_v1(event, canonical=True)

    datum_needles = [
        dict(needle)
        for needle in list(expected.get("Edatums") or [])
        if isinstance(needle, Mapping)
    ]
    if expected.get("Edatums_exact") is True:
        if len(middle) != len(datum_needles):
            raise AssertionError(
                "exact informative-event count mismatch: "
                f"expected={len(datum_needles)}, actual={len(middle)}; "
                f"middle={middle!r}"
            )
        for index, (event, needle) in enumerate(zip(middle, datum_needles)):
            assert_needle_v1(event, needle, label=f"Edatums[{index}]")
    else:
        assert_ordered_subsequence_v1(
            middle,
            datum_needles,
            label="Edatums",
        )


def _assert_live_action_event_group_v1(
    events: list[Mapping[str, Any]],
    expected: Mapping[str, Any],
) -> None:
    if len(events) < 2:
        raise AssertionError(
            "an admitted live action must emit controller start and end; "
            f"actual={events!r}"
        )
    for event in events:
        assert_standard_event_v1(event, canonical=False)

    start = events[0]
    end = events[-1]
    middle = events[1:-1]
    assert start.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    assert start.get("phase") == "start"
    assert end.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    assert end.get("phase") == "end"
    assert start.get("dispatch_id") == end.get("dispatch_id")
    assert start.get("event_id") != end.get("event_id")
    assert start.get("action") == end.get("action")

    assert_needle_v1(
        start,
        dict(expected.get("Estart") or {}),
        label="live.Estart",
    )
    assert_needle_v1(
        end,
        dict(expected.get("Eend") or {}),
        label="live.Eend",
    )

    for event in middle:
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1:
            raise AssertionError(
                "another controller packet appeared inside one live envelope: "
                f"{dict(event)!r}"
            )

    needles = [
        dict(needle)
        for needle in list(expected.get("Edatums") or [])
        if isinstance(needle, Mapping)
    ]
    if expected.get("Edatums_exact") is True:
        if len(middle) != len(needles):
            raise AssertionError(
                "exact live informative-event count mismatch: "
                f"expected={len(needles)}, actual={len(middle)}; "
                f"middle={middle!r}"
            )
        for index, (event, needle) in enumerate(zip(middle, needles)):
            assert_needle_v1(event, needle, label=f"live.Edatums[{index}]")
    else:
        assert_ordered_subsequence_v1(
            middle,
            needles,
            label="live.Edatums",
        )


def _controller_event_spine_rows(
    events: Iterable[Mapping[str, Any]],
) -> list[tuple[str, int, str, str]]:
    return [
        (
            str(event["event_id"]),
            int(event["event_seq"]),
            str(event["phase"]),
            str(event["action"]),
        )
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    ]


def _event_seq_set(events: Iterable[Mapping[str, Any]]) -> set[int]:
    return {int(event["event_seq"]) for event in events}


def _expand_seq_ranges_v1(raw_ranges: Any) -> set[int]:
    expanded: set[int] = set()
    for raw_range in list(raw_ranges or []):
        if not isinstance(raw_range, Mapping):
            raise AssertionError(
                "v1 hidden event-sequence range must be a mapping: "
                f"{raw_range!r}"
            )
        start = int(raw_range["from_event_seq"])
        end = int(raw_range["to_event_seq"])
        if end < start:
            raise AssertionError(
                f"hidden event-sequence range is reversed: {start}..{end}"
            )
        expanded.update(range(start, end + 1))
    return expanded


def _action_target_ids_v1(A: Any) -> list[str]:
    if not isinstance(A, Mapping):
        return []
    out: list[str] = []
    seen: set[str] = set()
    fill = A.get("fill")
    if isinstance(fill, Mapping):
        for raw_key in fill:
            datum_id = str(raw_key or "").split(".", 1)[0].strip()
            if datum_id and datum_id not in seen:
                seen.add(datum_id)
                out.append(datum_id)
    signal = A.get("signal")
    if isinstance(signal, Mapping):
        datum_id = str(signal.get("datum_id") or "").strip()
        if datum_id and datum_id not in seen:
            seen.add(datum_id)
            out.append(datum_id)
    return out


def _assert_projected_controller_packet_v1(
    *,
    canonical: Mapping[str, Any],
    projected: Mapping[str, Any],
    role: str,
) -> None:
    canonical_payload = canonical.get("payload")
    projected_payload = projected.get("payload")
    if not isinstance(canonical_payload, Mapping):
        raise AssertionError(f"canonical controller payload invalid: {canonical!r}")
    if not isinstance(projected_payload, Mapping):
        raise AssertionError(f"projected controller payload invalid: {projected!r}")
    if not isinstance(projected_payload.get("U"), Mapping):
        raise AssertionError(
            f"projected controller payload.U must be mapping for {role!r}"
        )

    for key in (
        "kind",
        "event_id",
        "event_seq",
        "emitted_at",
        "source",
        "name",
        "phase",
        "session_id",
        "action",
    ):
        assert projected.get(key) == canonical.get(key), (
            "controller projection changed stable event spine: "
            f"role={role!r}, key={key!r}"
        )

    assert projected_payload.get("timestamp") == canonical_payload.get("timestamp")
    for outcome_key in ("outcome", "result", "system_error"):
        assert projected_payload.get(outcome_key) == canonical_payload.get(
            outcome_key
        )

    canonical_A = canonical_payload.get("A")
    projected_A = projected_payload.get("A")
    canonical_targets = _action_target_ids_v1(canonical_A)

    if projected_A is None:
        assert canonical_targets, (
            "targetless controller action must not be blacked out: "
            f"role={role!r}"
        )
        assert projected_payload.get("fill") is None
        assert projected_payload.get("signal") is None
        assert projected.get("dispatch_id") is None
        assert projected.get("dispatcher_identity_id") is None
        assert projected.get("dispatcher_role") is None
        return

    if not isinstance(canonical_A, Mapping) or not isinstance(projected_A, Mapping):
        raise AssertionError(
            "controller A must be mapping or fully hidden null: "
            f"role={role!r}, canonical_A={canonical_A!r}, "
            f"projected_A={projected_A!r}"
        )

    canonical_fill = canonical_A.get("fill")
    projected_fill = projected_A.get("fill")
    assert isinstance(canonical_fill, Mapping)
    assert isinstance(projected_fill, Mapping)
    assert set(projected_fill).issubset(set(canonical_fill))
    for key, value in projected_fill.items():
        assert value == canonical_fill[key]

    canonical_signal = canonical_A.get("signal")
    projected_signal = projected_A.get("signal")
    assert projected_signal is None or projected_signal == canonical_signal
    assert projected_payload.get("fill") == dict(projected_fill)
    assert projected_payload.get("signal") == projected_signal

    visible_targets = _action_target_ids_v1(projected_A)
    assert set(visible_targets).issubset(set(canonical_targets))
    assert not canonical_targets or visible_targets
    for key in ("dispatch_id", "dispatcher_identity_id", "dispatcher_role"):
        assert projected.get(key) == canonical.get(key), (
            "controller actor/correlation envelope changed despite visible "
            f"target: role={role!r}, key={key!r}"
        )


def _assert_projected_packet_integrity(
    *,
    canonical_events: list[Mapping[str, Any]],
    projected_events: list[Mapping[str, Any]],
    role: str,
) -> None:
    canonical_by_id = {
        str(event["event_id"]): dict(event) for event in canonical_events
    }
    for projected in projected_events:
        event_id = str(projected["event_id"])
        if event_id not in canonical_by_id:
            raise AssertionError(
                f"role {role!r} received non-canonical event id {event_id!r}"
            )
        canonical = canonical_by_id[event_id]
        if projected.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1:
            if canonical.get("kind") != CONTROLLER_LOOP_EVENT_KIND_V1:
                raise AssertionError(
                    "projected controller id resolves to non-controller packet"
                )
            _assert_projected_controller_packet_v1(
                canonical=canonical,
                projected=projected,
                role=role,
            )
        else:
            assert dict(projected) == canonical, (
                "visible non-controller packet must remain canonical: "
                f"role={role!r}, event_id={event_id!r}"
            )


def _assert_visibility_receipt_v1(
    *,
    role: str,
    before_cursor: int,
    canonical_events: list[dict[str, Any]],
    projected_events: list[dict[str, Any]],
    projected_page: Mapping[str, Any],
) -> None:
    canonical_event_seqs = _event_seq_set(canonical_events)
    projected_event_seqs = _event_seq_set(projected_events)
    expected_hidden = canonical_event_seqs - projected_event_seqs

    receipt = projected_page.get("visibility_receipt")
    if not isinstance(receipt, Mapping):
        raise AssertionError("v1 projected page must include visibility_receipt")
    assert receipt.get("kind") == "live_session_event_visibility_receipt_v1"
    assert receipt.get("role") == role
    assert int(receipt["scanned_from_event_seq_exclusive"]) == int(before_cursor)
    assert int(receipt["scanned_through_event_seq"]) == int(
        projected_page["scanned_through_event_seq"]
    )

    actual_hidden = _expand_seq_ranges_v1(receipt.get("hidden_event_seq_ranges"))
    assert actual_hidden == expected_hidden, (
        "visibility receipt does not describe exactly the filtered positions: "
        f"role={role!r}, expected={sorted(expected_hidden)!r}, "
        f"actual={sorted(actual_hidden)!r}"
    )
    assert int(receipt["hidden_event_count"]) == len(expected_hidden)
    assert receipt.get("reason") == (
        "role_projection" if expected_hidden else "none"
    )

    canonical_controller_seqs = {
        int(event["event_seq"])
        for event in canonical_events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    }
    assert not canonical_controller_seqs.intersection(actual_hidden)


def _assert_projected_views(
    *,
    strategy: BaseDryRunStrategy,
    run: DryRunRunHandleV1,
    case_name: str,
    action_index: int,
    before_cursor: int,
    canonical_page: Mapping[str, Any],
    views: Iterable[Mapping[str, Any]],
) -> None:
    canonical_events = [
        dict(event) for event in list(canonical_page.get("events") or [])
    ]
    canonical_ids = {str(event["event_id"]) for event in canonical_events}
    canonical_controller_spine = _controller_event_spine_rows(canonical_events)
    canonical_next = int(canonical_page["next_after_event_seq"])
    assert int(canonical_page["scanned_through_event_seq"]) == canonical_next

    for view_index, raw_view in enumerate(views, start=1):
        view = dict(raw_view)
        role = str(view["role"])
        expected = dict(view.get("E") or {})
        page = strategy.poll_committed_events_v1(
            run=run,
            role=role,
            identity_id=(
                f"{case_name}.action-{action_index}.view-{view_index}.{role}"
            ),
            after_event_seq=before_cursor,
            limit=None,
        )
        projected = [dict(event) for event in list(page.get("events") or [])]

        assert int(page["next_after_event_seq"]) == canonical_next
        assert int(page["scanned_through_event_seq"]) == canonical_next
        assert {str(event["event_id"]) for event in projected}.issubset(canonical_ids)
        assert _controller_event_spine_rows(projected) == canonical_controller_spine

        _assert_projected_packet_integrity(
            canonical_events=canonical_events,
            projected_events=projected,
            role=role,
        )
        _assert_visibility_receipt_v1(
            role=role,
            before_cursor=before_cursor,
            canonical_events=canonical_events,
            projected_events=projected,
            projected_page=page,
        )
        _assert_action_event_group(
            projected,
            expected,
            require_contiguous_canonical_interval=False,
        )


def _without_event_seq_v1(event: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


def _assert_data_blanket_v1(
    *,
    strategy: BaseDryRunStrategy,
    run: DryRunRunHandleV1,
    blanket: Mapping[str, Any],
    packet: Mapping[str, Any],
    canonical_page: Mapping[str, Any],
    live_events: list[Mapping[str, Any]],
) -> None:
    dispatch_needle = dict(blanket.get("dispatch") or {})
    if dispatch_needle:
        assert_needle_v1(packet, dispatch_needle, label="blanket.dispatch")

    page_needle = dict(blanket.get("canonical_page") or {})
    if page_needle:
        assert_needle_v1(
            canonical_page,
            page_needle,
            label="blanket.canonical_page",
        )

    eps_expected = blanket.get("eps")
    if eps_expected is not None:
        actual_rows = [
            row for row in live_events
            if row.get("kind") != "controller_loop_event_v1"
        ]
        if len(actual_rows) < len(eps_expected):
            raise AssertionError(
                f"expected at least {len(eps_expected)} eps rows; actual={actual_rows!r}"
            )
        for idx, needle in enumerate(eps_expected):
            assert_needle_v1(actual_rows[idx], dict(needle), label=f"blanket.eps[{idx}]")

    live_expected = blanket.get("live")
    if isinstance(live_expected, Mapping):
        _assert_live_action_event_group_v1(list(live_events), live_expected)

    if blanket.get("exact_live_canonical_wire") is True:
        canonical_events = [
            _without_event_seq_v1(event)
            for event in list(canonical_page.get("events") or [])
            if isinstance(event, Mapping)
        ]
        actual_live = [deepcopy(dict(event)) for event in live_events]
        assert actual_live == canonical_events, (
            "live epsilon packets must equal committed theta packets after "
            "removing only event_seq; "
            f"live={actual_live!r}; canonical={canonical_events!r}"
        )

    for index, raw_context in enumerate(
        list(blanket.get("contexts") or []), start=1
    ):
        context = dict(raw_context)
        role = context.get("role")
        U = strategy.read_context_v1(
            run=run,
            role=None if role is None else str(role),
        )
        assert_needle_v1(
            U,
            dict(context.get("U") or {}),
            label=f"blanket.contexts[{index}]",
        )


def _assert_eventless_unchanged(
    *,
    strategy: BaseDryRunStrategy,
    run: DryRunRunHandleV1,
    before_seq: int,
    before_events: list[Mapping[str, Any]],
    identity_id: str,
) -> None:
    after_seq = strategy.latest_committed_event_seq_v1(run=run)
    after_events = strategy.committed_events_v1(run=run, role=None)
    assert after_seq == before_seq
    assert [dict(event) for event in after_events] == [
        dict(event) for event in before_events
    ]

    page = strategy.poll_committed_events_v1(
        run=run,
        role=None,
        identity_id=identity_id,
        after_event_seq=before_seq,
        limit=None,
    )
    assert page["events"] == []
    assert int(page["next_after_event_seq"]) == before_seq


def run_dry_run_case_v1(
    case: DryRunCaseV1,
    *,
    strategy: BaseDryRunStrategy,
    dispatcher_identity_prefix: str = "dry-run",
) -> DryRunCaseReceiptV1:
    strategy = _require_strategy(strategy)
    run: Optional[DryRunRunHandleV1] = None
    cursor = 0
    saved_cursors: Dict[str, int] = {}
    completed_actions = 0
    current_note = ""

    try:
        validate_dry_run_case_v1(case)
        run = strategy.start_run_v1(
            program=case.program,
            initial_parameter_overrides=(
                case.initial_parameter_overrides or {}
            ),
            session_metadata=case.session_metadata or {},
        )

        for index, raw_item in enumerate(case.actions, start=1):
            item = dict(raw_item)
            item_kind = str(item.get("kind") or "")
            A = dict(item.get("A") or {})
            E = dict(item.get("E") or {})
            current_note = str(item.get("note") or "")

            current_high_water = strategy.latest_committed_event_seq_v1(run=run)
            cursor_value = _resolve_cursor(
                A.get("my_current_event_seq_number"),
                cursors=saved_cursors,
                current=current_high_water,
            )
            resolved_A = _resolved_A_v1(
                case_name=case.name,
                action_index=index,
                A=A,
                cursor_value=cursor_value,
                dispatcher_identity_prefix=dispatcher_identity_prefix,
            )

            if item_kind == DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1:
                before_events = deepcopy(
                    [
                        dict(event)
                        for event in strategy.committed_events_v1(
                            run=run,
                            role=None,
                        )
                    ]
                )
                expected_exc = dict(item.get("exception") or {})
                caught: Optional[Exception] = None
                try:
                    strategy.dispatch_action_v1(run=run, A=resolved_A)
                except Exception as exc:  # expected family under test
                    caught = exc

                if caught is None:
                    raise AssertionError(
                        f"expected {expected_exc.get('type')} but no exception raised"
                    )
                assert type(caught).__name__ == expected_exc["type"]
                assert str(expected_exc.get("contains") or "") in str(caught)
                _assert_eventless_unchanged(
                    strategy=strategy,
                    run=run,
                    before_seq=current_high_water,
                    before_events=before_events,
                    identity_id=(
                        f"{case.name}.action-{index}.eventless-exception"
                    ),
                )
                completed_actions = index
                continue

            if item_kind == DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1:
                before_events = deepcopy(
                    [
                        dict(event)
                        for event in strategy.committed_events_v1(
                            run=run,
                            role=None,
                        )
                    ]
                )
                packet = strategy.dispatch_action_v1(run=run, A=resolved_A)
                assert packet["ok"] is False
                assert packet["applied"] is False
                assert packet["rejected"] is True
                assert packet["dispatch_outcome"] == "stale_rejected"
                assert packet["write_committed"] is False
                assert packet["rejection_kind"] == item["rejection_kind"]
                assert (
                    packet["dispatch_staleness"]["reason"]
                    == item["rejection_kind"]
                )
                _assert_eventless_unchanged(
                    strategy=strategy,
                    run=run,
                    before_seq=current_high_water,
                    before_events=before_events,
                    identity_id=(
                        f"{case.name}.action-{index}.eventless-rejection"
                    ),
                )
                completed_actions = index
                continue

            if item_kind != DRY_RUN_ACTION_KIND_ORDINARY_V1:
                raise ValueError(f"unknown dry-run item kind: {item_kind!r}")

            blanket = dict(item.get("blanket") or {})
            live_events: list[Dict[str, Any]] = []
            dispatch_open = {"value": True}

            def live_sink(event: Mapping[str, Any]) -> None:
                if dispatch_open.get("value") is not True:
                    raise AssertionError(
                        "live event arrived outside the strategy dispatch call"
                    )
                event_dict = deepcopy(dict(event))
                if event_dict.get("kind") not in ("thinkument_eps_row_v1", "eps_row_v1"):
                    assert_standard_event_v1(event_dict, canonical=False)
                live_events.append(event_dict)

            try:
                packet = strategy.dispatch_action_v1(
                    run=run,
                    A=resolved_A,
                    live_event_sink=live_sink if blanket else None,
                )
            finally:
                dispatch_open["value"] = False

            assert packet.get("rejected") is not True, packet

            page = strategy.poll_committed_events_v1(
                run=run,
                role=None,
                identity_id=f"{case.name}.action-{index}.canonical",
                after_event_seq=cursor,
                limit=None,
            )
            events = [dict(event) for event in list(page.get("events") or [])]
            _assert_action_event_group(events, E)

            if blanket:
                _assert_data_blanket_v1(
                    strategy=strategy,
                    run=run,
                    blanket=blanket,
                    packet=packet,
                    canonical_page=page,
                    live_events=live_events,
                )

            next_cursor = int(page["next_after_event_seq"])
            _assert_projected_views(
                strategy=strategy,
                run=run,
                case_name=case.name,
                action_index=index,
                before_cursor=cursor,
                canonical_page=page,
                views=[
                    dict(view)
                    for view in list(item.get("views") or [])
                    if isinstance(view, Mapping)
                ],
            )

            cursor = next_cursor
            save_cursor = item.get("save_cursor")
            if save_cursor:
                saved_cursors[str(save_cursor)] = cursor
            completed_actions = index

        return DryRunCaseReceiptV1(
            name=case.name,
            ok=True,
            completed_actions=completed_actions,
            latest_event_seq=cursor,
        )

    except Exception as exc:
        latest = cursor
        if run is not None:
            try:
                latest = strategy.latest_committed_event_seq_v1(run=run)
            except Exception:
                pass
        return DryRunCaseReceiptV1(
            name=case.name,
            ok=False,
            completed_actions=completed_actions,
            latest_event_seq=int(latest),
            failed_action_index=completed_actions + 1,
            failed_action_note=current_note or None,
            exception_type=type(exc).__name__,
            error=str(exc),
        )

    finally:
        if run is not None:
            strategy.close_run_v1(run=run)


def run_dry_run_suite_v1(
    cases: Iterable[DryRunCaseV1],
    *,
    strategy: BaseDryRunStrategy,
    prepare_runtime: Optional[Callable[[], None]] = None,
    dispatcher_identity_prefix: str = "dry-run",
) -> DryRunSuiteReceiptV1:
    strategy = _require_strategy(strategy)
    case_tuple = tuple(cases)

    if prepare_runtime is not None:
        try:
            prepare_runtime()
        except Exception as exc:
            return DryRunSuiteReceiptV1(
                strategy_name=strategy.strategy_name,
                cases=tuple(
                    DryRunCaseReceiptV1(
                        name=case.name,
                        ok=False,
                        completed_actions=0,
                        latest_event_seq=0,
                        failed_action_index=1,
                        failed_action_note="runtime preparation",
                        exception_type=type(exc).__name__,
                        error=str(exc),
                    )
                    for case in case_tuple
                ),
            )

    return DryRunSuiteReceiptV1(
        strategy_name=strategy.strategy_name,
        cases=tuple(
            run_dry_run_case_v1(
                case,
                strategy=strategy,
                dispatcher_identity_prefix=dispatcher_identity_prefix,
            )
            for case in case_tuple
        ),
    )


def assert_dry_run_suite_v1(receipt: DryRunSuiteReceiptV1) -> None:
    if not isinstance(receipt, DryRunSuiteReceiptV1):
        raise TypeError("receipt must be DryRunSuiteReceiptV1")
    if receipt.ok:
        return

    lines = [
        (
            "ThinkProgramTM dry-run failures under strategy "
            f"{receipt.strategy_name!r}:"
        ),
        *[
            (
                f"- {case.name}: action {case.failed_action_index} "
                f"({case.failed_action_note or 'no note'}) "
                f"{case.exception_type}: {case.error}"
            )
            for case in receipt.failures
        ],
        "",
        "All case receipts:",
        *[f"- {case.to_dict()!r}" for case in receipt.cases],
    ]
    raise AssertionError("\n".join(lines))


__all__ = [
    "DRY_RUN_CASE_KIND_V1",
    "DRY_RUN_CASE_RECEIPT_KIND_V1",
    "DRY_RUN_SUITE_RECEIPT_KIND_V1",
    "DryRunCaseReceiptV1",
    "DryRunCaseV1",
    "DryRunSuiteReceiptV1",
    "assert_dry_run_suite_v1",
    "run_dry_run_case_v1",
    "run_dry_run_suite_v1",
    "validate_dry_run_case_v1",
]
