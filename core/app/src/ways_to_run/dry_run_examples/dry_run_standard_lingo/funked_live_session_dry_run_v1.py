from __future__ import annotations

"""Strategy-agnostic chain-reaction dry-run machinery.

The ordinary and funked runners share the same strategy interface.  A funked
outer dispatch differs only in the dispatch operator and in the expectations
that describe generated continuation receipts and generated controller ends.
No app-specific widget, filler, role, or puzzle concept is known here.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunRunHandleV1,
)

from .expectation_matching_v1 import (
    assert_needle_v1,
    assert_ordered_subsequence_v1,
)
from .protocol_v1 import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    assert_strict_canonical_event_order_v1,
)


FUNKED_DRY_RUN_CASE_KIND_V1 = "funked_live_session_dry_run_case_v1"
FUNKED_DRY_RUN_CASE_RECEIPT_KIND_V1 = (
    "funked_live_session_dry_run_case_receipt_v1"
)
FUNKED_DRY_RUN_SUITE_RECEIPT_KIND_V1 = (
    "funked_live_session_dry_run_suite_receipt_v1"
)


@dataclass(frozen=True, slots=True)
class FunkedDispatchExpectationV1:
    """One outer chain-reaction dispatch and its standard observations."""

    A: Mapping[str, Any]
    packet_expectation: Mapping[str, Any]
    filler_receipt_expectations: Sequence[Mapping[str, Any]] = ()
    generated_end_expectations: Sequence[Mapping[str, Any]] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class FunkedDryRunCaseV1:
    name: str
    program: Mapping[str, Any]
    session_metadata: Mapping[str, Any]
    dispatches: Sequence[FunkedDispatchExpectationV1]
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None

    @property
    def kind(self) -> str:
        return FUNKED_DRY_RUN_CASE_KIND_V1


@dataclass(frozen=True, slots=True)
class FunkedDryRunCaseReceiptV1:
    name: str
    ok: bool
    completed_dispatches: int
    latest_event_seq: int
    failed_dispatch_index: Optional[int] = None
    failed_dispatch_note: Optional[str] = None
    exception_type: Optional[str] = None
    error: Optional[str] = None

    @property
    def kind(self) -> str:
        return FUNKED_DRY_RUN_CASE_RECEIPT_KIND_V1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "ok": self.ok,
            "completed_dispatches": self.completed_dispatches,
            "latest_event_seq": self.latest_event_seq,
            "failed_dispatch_index": self.failed_dispatch_index,
            "failed_dispatch_note": self.failed_dispatch_note,
            "exception_type": self.exception_type,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class FunkedDryRunSuiteReceiptV1:
    cases: tuple[FunkedDryRunCaseReceiptV1, ...]
    strategy_name: str

    @property
    def kind(self) -> str:
        return FUNKED_DRY_RUN_SUITE_RECEIPT_KIND_V1

    @property
    def failures(self) -> tuple[FunkedDryRunCaseReceiptV1, ...]:
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
    return strategy


def validate_funked_dry_run_case_v1(case: FunkedDryRunCaseV1) -> None:
    if not isinstance(case, FunkedDryRunCaseV1):
        raise TypeError("case must be FunkedDryRunCaseV1")
    if not str(case.name or "").strip():
        raise ValueError("funked dry-run case name must be non-empty")
    if not isinstance(case.program, Mapping):
        raise TypeError("funked case program must be a mapping")
    if not isinstance(case.session_metadata, Mapping):
        raise TypeError("funked case session_metadata must be a mapping")
    if case.initial_parameter_overrides is not None and not isinstance(
        case.initial_parameter_overrides, Mapping
    ):
        raise TypeError("initial_parameter_overrides must be mapping or None")
    for index, dispatch in enumerate(case.dispatches, start=1):
        if not isinstance(dispatch, FunkedDispatchExpectationV1):
            raise TypeError(
                f"funked dispatch {index} must be FunkedDispatchExpectationV1"
            )
        if not isinstance(dispatch.A, Mapping):
            raise TypeError(f"funked dispatch {index}.A must be a mapping")
        if not isinstance(dispatch.packet_expectation, Mapping):
            raise TypeError(
                f"funked dispatch {index}.packet_expectation must be mapping"
            )


def _dispatch_identity_v1(
    *,
    case_name: str,
    dispatch_index: int,
    A: Mapping[str, Any],
    prefix: str,
) -> str:
    explicit = str(A.get("identity_id") or "").strip()
    if explicit:
        return explicit
    return f"{prefix}.{case_name}.dispatch-{dispatch_index}"


def _flatten_filler_receipts(packet: Mapping[str, Any]) -> list[Dict[str, Any]]:
    chain = packet.get("chainreactionTM_receipt")
    if not isinstance(chain, Mapping):
        return []
    out: list[Dict[str, Any]] = []
    for row in list(chain.get("dispatch_receipts") or []):
        if not isinstance(row, Mapping):
            continue
        receipt = row.get("receipt")
        if isinstance(receipt, Mapping):
            out.append(dict(receipt))
    return out


def _generated_end_events(
    events: Sequence[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and event.get("phase") == "end"
        and isinstance(
            (event.get("payload") or {}).get("dispatch_context"), Mapping
        )
    ]


def _assert_generated_end_internal_law(event: Mapping[str, Any]) -> None:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise AssertionError("generated controller end payload must be mapping")
    context = payload.get("dispatch_context")
    if not isinstance(context, Mapping):
        raise AssertionError("generated controller end needs dispatch_context")
    filler = context.get("filler_receipt")
    if not isinstance(filler, Mapping):
        raise AssertionError("generated dispatch_context needs filler_receipt")
    info = filler.get("next_U_funkability")
    if not isinstance(info, Mapping):
        raise AssertionError(
            "generated filler_receipt needs next_U_funkability"
        )
    U = payload.get("U")
    if not isinstance(U, Mapping):
        raise AssertionError("generated controller end payload.U must be mapping")

    assert info.get("evaluated_from") == "controller.loop.end.payload.U"
    assert info.get("U_kind") == U.get("kind")
    assert info.get("span_id") == (
        U.get("current_span") or U.get("current_span_id")
    )


def _assert_funked_dispatch_observations(
    *,
    expected: FunkedDispatchExpectationV1,
    packet: Mapping[str, Any],
    canonical_events: list[Mapping[str, Any]],
) -> None:
    assert_needle_v1(
        packet,
        expected.packet_expectation,
        label="funked.packet",
    )

    filler_receipts = _flatten_filler_receipts(packet)
    assert_ordered_subsequence_v1(
        filler_receipts,
        [dict(row) for row in expected.filler_receipt_expectations],
        label="funked.filler_receipts",
    )

    generated = _generated_end_events(canonical_events)
    expected_generated = [
        dict(row) for row in expected.generated_end_expectations
    ]
    if len(generated) != len(expected_generated):
        raise AssertionError(
            "generated controller-end count mismatch: "
            f"expected={len(expected_generated)}, actual={len(generated)}; "
            f"generated={generated!r}"
        )
    for index, (event, needle) in enumerate(zip(generated, expected_generated)):
        _assert_generated_end_internal_law(event)
        assert_needle_v1(
            event,
            needle,
            label=f"funked.generated_end[{index}]",
        )


def run_funked_dry_run_case_v1(
    case: FunkedDryRunCaseV1,
    *,
    strategy: BaseDryRunStrategy,
    dispatcher_identity_prefix: str = "dry-run-funked",
) -> FunkedDryRunCaseReceiptV1:
    strategy = _require_strategy(strategy)
    run: Optional[DryRunRunHandleV1] = None
    cursor = 0
    completed = 0
    current_note = ""

    try:
        validate_funked_dry_run_case_v1(case)
        run = strategy.start_run_v1(
            program=case.program,
            session_metadata=case.session_metadata,
            initial_parameter_overrides=(
                case.initial_parameter_overrides or {}
            ),
        )

        for index, expected in enumerate(case.dispatches, start=1):
            current_note = expected.note
            before = strategy.latest_committed_event_seq_v1(run=run)
            A = deepcopy(dict(expected.A))
            A["identity_id"] = _dispatch_identity_v1(
                case_name=case.name,
                dispatch_index=index,
                A=A,
                prefix=dispatcher_identity_prefix,
            )
            packet = strategy.dispatch_action_with_chain_reaction_v1(
                run=run,
                A=A,
            )
            page = strategy.poll_committed_events_v1(
                run=run,
                role=None,
                after_event_seq=before,
                identity_id=f"{case.name}.dispatch-{index}.canonical",
                limit=None,
            )
            events = [dict(event) for event in list(page.get("events") or [])]
            assert_strict_canonical_event_order_v1(events, contiguous=True)
            _assert_funked_dispatch_observations(
                expected=expected,
                packet=packet,
                canonical_events=events,
            )
            cursor = int(page["next_after_event_seq"])
            completed = index

        whole_queue = [
            dict(event)
            for event in strategy.committed_events_v1(run=run, role=None)
        ]
        assert whole_queue
        assert_strict_canonical_event_order_v1(whole_queue, contiguous=True)

        return FunkedDryRunCaseReceiptV1(
            name=case.name,
            ok=True,
            completed_dispatches=completed,
            latest_event_seq=cursor,
        )

    except Exception as exc:
        latest = cursor
        if run is not None:
            try:
                latest = strategy.latest_committed_event_seq_v1(run=run)
            except Exception:
                pass
        return FunkedDryRunCaseReceiptV1(
            name=case.name,
            ok=False,
            completed_dispatches=completed,
            latest_event_seq=int(latest),
            failed_dispatch_index=completed + 1,
            failed_dispatch_note=current_note or None,
            exception_type=type(exc).__name__,
            error=str(exc),
        )
    finally:
        if run is not None:
            strategy.close_run_v1(run=run)


def run_funked_dry_run_suite_v1(
    cases: Iterable[FunkedDryRunCaseV1],
    *,
    strategy: BaseDryRunStrategy,
    prepare_runtime: Optional[Callable[[], None]] = None,
    dispatcher_identity_prefix: str = "dry-run-funked",
) -> FunkedDryRunSuiteReceiptV1:
    strategy = _require_strategy(strategy)
    case_tuple = tuple(cases)

    if prepare_runtime is not None:
        try:
            prepare_runtime()
        except Exception as exc:
            return FunkedDryRunSuiteReceiptV1(
                strategy_name=strategy.strategy_name,
                cases=tuple(
                    FunkedDryRunCaseReceiptV1(
                        name=case.name,
                        ok=False,
                        completed_dispatches=0,
                        latest_event_seq=0,
                        failed_dispatch_index=1,
                        failed_dispatch_note="runtime preparation",
                        exception_type=type(exc).__name__,
                        error=str(exc),
                    )
                    for case in case_tuple
                ),
            )

    return FunkedDryRunSuiteReceiptV1(
        strategy_name=strategy.strategy_name,
        cases=tuple(
            run_funked_dry_run_case_v1(
                case,
                strategy=strategy,
                dispatcher_identity_prefix=dispatcher_identity_prefix,
            )
            for case in case_tuple
        ),
    )


def assert_funked_dry_run_suite_v1(
    receipt: FunkedDryRunSuiteReceiptV1,
) -> None:
    if not isinstance(receipt, FunkedDryRunSuiteReceiptV1):
        raise TypeError("receipt must be FunkedDryRunSuiteReceiptV1")
    if receipt.ok:
        return

    lines = [
        f"Funked dry-run failures under strategy {receipt.strategy_name!r}:",
        *[
            (
                f"- {case.name}: dispatch {case.failed_dispatch_index} "
                f"({case.failed_dispatch_note or 'no note'}) "
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
    "FUNKED_DRY_RUN_CASE_KIND_V1",
    "FUNKED_DRY_RUN_CASE_RECEIPT_KIND_V1",
    "FUNKED_DRY_RUN_SUITE_RECEIPT_KIND_V1",
    "FunkedDispatchExpectationV1",
    "FunkedDryRunCaseReceiptV1",
    "FunkedDryRunCaseV1",
    "FunkedDryRunSuiteReceiptV1",
    "assert_funked_dry_run_suite_v1",
    "run_funked_dry_run_case_v1",
    "run_funked_dry_run_suite_v1",
    "validate_funked_dry_run_case_v1",
]
