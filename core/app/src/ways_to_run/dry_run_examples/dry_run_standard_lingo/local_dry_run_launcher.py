from __future__ import annotations

"""One-shot local P / SM / C + standard dry-run A / E launcher.

This is a thin CLI-facing composition over the already-owned dry-run language
and strategy membrane.  It intentionally owns no ThinkWidget, app-pack,
Flask/Django, persistence, or browser semantics.

Input contract
--------------
``--source`` resolves the normal authored tape::

    PROGRAM = P
    SESSION_METADATA = SM
    PUPPET = C  # or None

``--actions MODULE:ATTRIBUTE`` resolves a sequence produced by the standard
``action_specs_v1`` helpers (STEP / UNDO / REDO / PREFLIGHT_EXCEPTION /
PREFLIGHT_REJECTION).  Ordinary rows therefore carry the exact standard A and
E pockets used by the existing dry-run catalog.

Execution contract
------------------
The launcher drives ``BaseDryRunStrategy`` only:

    lambda -> gamma -> epsilon? -> theta / Q/U -> omega

The default strategy is the current in-process backend-only strategy.  The
matcher below understands only the public standard-lingo expectation grammar:
exact dotted-path needles, ``__contains`` needles, ``__absent`` needles,
controller tridents, role-projected views, and complete data blankets.

The point of this module is ergonomic local execution of arbitrary authored
P/SM/C + A/E.  It is not another application runtime and it does not translate
DOM actions into backend A/E.
"""

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence

from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (
    add_live_run_source_arguments_v1,
    live_run_tape_from_namespace_v1,
    prepare_runtime_refs_v1,
)
from ways_to_run.dry_run_examples.dry_run_adapter_strategies.BASE_CLASS import (
    BaseDryRunStrategy,
)
from ways_to_run.dry_run_examples.dry_run_adapter_strategies.base_facade_backend_only import (
    BaseFacadeBackendOnlyDryRunStrategy,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.action_specs_v1 import (
    DRY_RUN_ACTION_KIND_ORDINARY_V1,
    DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1,
    DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.data_blanket_expectations_v1 import (
    DATA_BLANKET_CONTEXT_VIEW_KIND_V1,
    DATA_BLANKET_EXPECTATION_KIND_V1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.protocol_v1 import (
    assert_standard_event_v1,
    assert_strict_canonical_event_order_v1,
)


MISSING = object()


@dataclass(frozen=True, slots=True)
class LocalDryRunReceiptV1:
    source: str
    strategy: str
    attempted_actions: int
    admitted_actions: int
    preflight_exceptions: int
    preflight_rejections: int
    final_event_seq: int
    saved_cursors: Mapping[str, int]

    @property
    def kind(self) -> str:
        return "thinkument_local_standard_dry_run_receipt_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "strategy": self.strategy,
            "attempted_actions": self.attempted_actions,
            "admitted_actions": self.admitted_actions,
            "preflight_exceptions": self.preflight_exceptions,
            "preflight_rejections": self.preflight_rejections,
            "final_event_seq": self.final_event_seq,
            "saved_cursors": dict(self.saved_cursors),
        }


def resolve_object_ref_v1(ref: str) -> Any:
    raw = str(ref or "").strip()
    module_name, separator, attr_path = raw.partition(":")
    if not separator or not module_name or not attr_path:
        raise ValueError("object reference must be 'python.module:attribute'")

    value: Any = import_module(module_name)
    for part in attr_path.split("."):
        if not part:
            raise ValueError(f"invalid empty attribute in object ref {raw!r}")
        value = getattr(value, part)
    return value


def resolve_action_rows_ref_v1(ref: str) -> tuple[Mapping[str, Any], ...]:
    value = resolve_object_ref_v1(ref)
    if callable(value):
        value = value()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("--actions must resolve to a sequence of standard action rows")

    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"--actions row {index} must be a mapping; got {type(row).__name__}"
            )
        rows.append(deepcopy(dict(row)))
    return tuple(rows)


def _path_parts_v1(path: str) -> tuple[str, ...]:
    return tuple(part for part in str(path).split(".") if part)


def _read_path_v1(value: Any, path: str) -> Any:
    current = value
    for part in _path_parts_v1(path):
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                return MISSING
            current = current[index]
            continue
        return MISSING
    return current


def _assert_needles_v1(
    actual: Any,
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    for raw_key, expected_value in expected.items():
        key = str(raw_key)
        if key.endswith("__contains"):
            path = key[: -len("__contains")]
            observed = _read_path_v1(actual, path)
            if observed is MISSING or str(expected_value) not in str(observed):
                raise AssertionError(
                    f"{label}: expected {path!r} to contain {expected_value!r}; "
                    f"actual={None if observed is MISSING else observed!r}"
                )
            continue

        if key.endswith("__absent"):
            path = key[: -len("__absent")]
            observed = _read_path_v1(actual, path)
            if bool(expected_value) and observed is not MISSING:
                raise AssertionError(
                    f"{label}: expected {path!r} to be absent; actual={observed!r}"
                )
            continue

        observed = _read_path_v1(actual, key)
        if observed is MISSING:
            raise AssertionError(f"{label}: missing expected path {key!r}")
        if observed != expected_value:
            raise AssertionError(
                f"{label}: {key!r} mismatch; "
                f"expected={expected_value!r}, actual={observed!r}"
            )


def _assert_event_envelope_v1(
    events: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Any],
    *,
    label: str,
    canonical: bool,
) -> None:
    rows = [dict(event) for event in events]
    if len(rows) < 2:
        raise AssertionError(f"{label}: expected controller start/end envelope; got {rows!r}")

    for event in rows:
        assert_standard_event_v1(event, canonical=canonical)

    start_expected = expected.get("Estart")
    end_expected = expected.get("Eend")
    middle_expected = expected.get("Edatums")
    exact_middle = bool(expected.get("Edatums_exact", False))

    if not isinstance(start_expected, Mapping):
        raise TypeError(f"{label}: E.Estart must be a mapping")
    if not isinstance(end_expected, Mapping):
        raise TypeError(f"{label}: E.Eend must be a mapping")
    if not isinstance(middle_expected, list):
        raise TypeError(f"{label}: E.Edatums must be a list")

    _assert_needles_v1(rows[0], start_expected, label=f"{label}.Estart")
    _assert_needles_v1(rows[-1], end_expected, label=f"{label}.Eend")

    middle = rows[1:-1]
    expected_middle = [dict(item) for item in middle_expected]
    if exact_middle:
        if len(middle) != len(expected_middle):
            raise AssertionError(
                f"{label}.Edatums exact length mismatch; "
                f"expected={len(expected_middle)}, actual={len(middle)}"
            )
        for index, (actual_event, event_expectation) in enumerate(
            zip(middle, expected_middle)
        ):
            _assert_needles_v1(
                actual_event,
                event_expectation,
                label=f"{label}.Edatums[{index}]",
            )
        return

    cursor = 0
    for expectation_index, event_expectation in enumerate(expected_middle):
        matched = False
        while cursor < len(middle):
            try:
                _assert_needles_v1(
                    middle[cursor],
                    event_expectation,
                    label=f"{label}.Edatums[{expectation_index}]",
                )
            except AssertionError:
                cursor += 1
                continue
            matched = True
            cursor += 1
            break
        if not matched:
            raise AssertionError(
                f"{label}: expected middle event {expectation_index} "
                "was not found in order"
            )


def _interval_events_v1(
    strategy: BaseDryRunStrategy,
    *,
    run: Any,
    role: Optional[str],
    after_event_seq: int,
    through_event_seq: int,
) -> list[Mapping[str, Any]]:
    rows = [
        dict(event)
        for event in strategy.committed_events_v1(run=run, role=role)
        if type(event.get("event_seq")) is int
        and int(event["event_seq"]) > int(after_event_seq)
        and int(event["event_seq"]) <= int(through_event_seq)
    ]
    assert_strict_canonical_event_order_v1(rows, contiguous=(role is None))
    return rows


def _resolve_cursor_v1(raw: Any, saved: Mapping[str, int]) -> Any:
    if not isinstance(raw, str):
        return raw
    key = raw[1:] if raw.startswith("$") else raw
    if key not in saved:
        raise KeyError(
            f"A.my_current_event_seq_number names unknown saved cursor {raw!r}; "
            f"known={sorted(saved)!r}"
        )
    return int(saved[key])


def _normalized_live_for_wire_v1(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        row = deepcopy(dict(event))
        row.pop("event_seq", None)
        out.append(row)
    return out


def _assert_data_blanket_v1(
    *,
    strategy: BaseDryRunStrategy,
    run: Any,
    blanket: Mapping[str, Any],
    live_events: Sequence[Mapping[str, Any]],
    dispatch_result: Mapping[str, Any],
    canonical_events: Sequence[Mapping[str, Any]],
    before_event_seq: int,
    action: Mapping[str, Any],
) -> None:
    if blanket.get("kind") != DATA_BLANKET_EXPECTATION_KIND_V1:
        raise TypeError(
            "blanket.kind must be live_session_data_blanket_expectation_v1"
        )

    live_expectation = blanket.get("live")
    if live_expectation is not None:
        if not isinstance(live_expectation, Mapping):
            raise TypeError("blanket.live must be a mapping or None")
        _assert_event_envelope_v1(
            live_events,
            live_expectation,
            label="blanket.live",
            canonical=False,
        )

    dispatch_expectation = blanket.get("dispatch") or {}
    if not isinstance(dispatch_expectation, Mapping):
        raise TypeError("blanket.dispatch must be a mapping")
    _assert_needles_v1(
        dispatch_result,
        dispatch_expectation,
        label="blanket.dispatch",
    )

    raw_role = action.get("role")
    role = None if raw_role is None else str(raw_role)
    identity_id = str(action.get("identity_id") or "local-dry-run")
    page = strategy.poll_committed_events_v1(
        run=run,
        role=role,
        after_event_seq=int(before_event_seq),
        identity_id=identity_id,
        limit=None,
    )
    canonical_page_expectation = blanket.get("canonical_page") or {}
    if not isinstance(canonical_page_expectation, Mapping):
        raise TypeError("blanket.canonical_page must be a mapping")
    _assert_needles_v1(
        page,
        canonical_page_expectation,
        label="blanket.canonical_page",
    )

    for index, raw_view in enumerate(blanket.get("contexts") or []):
        if not isinstance(raw_view, Mapping):
            raise TypeError(f"blanket.contexts[{index}] must be a mapping")
        if raw_view.get("kind") != DATA_BLANKET_CONTEXT_VIEW_KIND_V1:
            raise TypeError(
                f"blanket.contexts[{index}] has unsupported kind {raw_view.get('kind')!r}"
            )
        raw_view_role = raw_view.get("role")
        view_role = None if raw_view_role is None else str(raw_view_role)
        context = strategy.read_context_v1(run=run, role=view_role)
        expected_u = raw_view.get("U") or {}
        if not isinstance(expected_u, Mapping):
            raise TypeError(f"blanket.contexts[{index}].U must be a mapping")
        _assert_needles_v1(
            context,
            expected_u,
            label=f"blanket.contexts[{index}].U",
        )

    if bool(blanket.get("exact_live_canonical_wire", True)):
        normalized_canonical = _normalized_live_for_wire_v1(canonical_events)
        normalized_live = _normalized_live_for_wire_v1(live_events)
        if normalized_live != normalized_canonical:
            raise AssertionError(
                "blanket exact live/canonical bridge mismatch; "
                f"live={normalized_live!r}, canonical={normalized_canonical!r}"
            )


def _assert_rejection_kind_v1(result: Mapping[str, Any], rejection_kind: str) -> None:
    target = str(rejection_kind)
    observed_kind = _read_path_v1(result, "kind")
    if observed_kind == target:
        return
    payload = json.dumps(result, sort_keys=True, default=str)
    if target not in payload:
        raise AssertionError(
            f"expected structured preflight rejection {target!r}; result={result!r}"
        )


def run_standard_dry_run_v1(
    *,
    program: Mapping[str, Any],
    session_metadata: Mapping[str, Any] | None,
    initial_parameter_overrides: Mapping[str, Any] | None,
    actions: Sequence[Mapping[str, Any]],
    source: str = "local",
    strategy: Optional[BaseDryRunStrategy] = None,
) -> LocalDryRunReceiptV1:
    """Execute one arbitrary standard backend dry run and fail at first mismatch."""

    selected = strategy or BaseFacadeBackendOnlyDryRunStrategy()
    run = selected.start_run_v1(
        program=deepcopy(dict(program)),
        session_metadata=deepcopy(dict(session_metadata or {})),
        initial_parameter_overrides=deepcopy(dict(initial_parameter_overrides or {})),
    )

    saved_cursors: MutableMapping[str, int] = {}
    admitted = 0
    exceptions = 0
    rejections = 0

    try:
        for index, raw_row in enumerate(actions):
            if not isinstance(raw_row, Mapping):
                raise TypeError(f"action row {index} must be a mapping")
            row = deepcopy(dict(raw_row))
            kind = row.get("kind")
            raw_A = row.get("A")
            if not isinstance(raw_A, Mapping):
                raise TypeError(f"action row {index}.A must be a mapping")
            A = deepcopy(dict(raw_A))
            A["my_current_event_seq_number"] = _resolve_cursor_v1(
                A.get("my_current_event_seq_number"),
                saved_cursors,
            )

            before_seq = selected.latest_committed_event_seq_v1(run=run)

            if kind == DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1:
                expected_exception = row.get("exception")
                if not isinstance(expected_exception, Mapping):
                    raise TypeError(
                        f"action row {index}.exception must be a mapping"
                    )
                try:
                    selected.dispatch_action_v1(run=run, A=A)
                except BaseException as exc:
                    expected_type = str(expected_exception.get("type") or "")
                    expected_contains = str(expected_exception.get("contains") or "")
                    if type(exc).__name__ != expected_type:
                        raise AssertionError(
                            f"action row {index}: expected exception {expected_type!r}; "
                            f"got {type(exc).__name__!r}: {exc}"
                        ) from exc
                    if expected_contains not in str(exc):
                        raise AssertionError(
                            f"action row {index}: exception message did not contain "
                            f"{expected_contains!r}: {exc}"
                        ) from exc
                else:
                    raise AssertionError(
                        f"action row {index}: expected preflight exception but dispatch returned"
                    )
                after_seq = selected.latest_committed_event_seq_v1(run=run)
                if after_seq != before_seq:
                    raise AssertionError(
                        f"action row {index}: preflight exception must be eventless; "
                        f"before={before_seq}, after={after_seq}"
                    )
                exceptions += 1
                continue

            if kind == DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1:
                result = dict(selected.dispatch_action_v1(run=run, A=A) or {})
                _assert_rejection_kind_v1(
                    result,
                    str(row.get("rejection_kind") or ""),
                )
                after_seq = selected.latest_committed_event_seq_v1(run=run)
                if after_seq != before_seq:
                    raise AssertionError(
                        f"action row {index}: preflight rejection must be eventless; "
                        f"before={before_seq}, after={after_seq}"
                    )
                rejections += 1
                continue

            if kind != DRY_RUN_ACTION_KIND_ORDINARY_V1:
                raise ValueError(f"action row {index}: unsupported kind {kind!r}")

            live_events: list[Mapping[str, Any]] = []
            result = dict(
                selected.dispatch_action_v1(
                    run=run,
                    A=A,
                    live_event_sink=lambda event: live_events.append(
                        deepcopy(dict(event))
                    ),
                )
                or {}
            )
            after_seq = selected.latest_committed_event_seq_v1(run=run)
            canonical_events = _interval_events_v1(
                selected,
                run=run,
                role=None,
                after_event_seq=before_seq,
                through_event_seq=after_seq,
            )

            expected = row.get("E") or {}
            if not isinstance(expected, Mapping):
                raise TypeError(f"action row {index}.E must be a mapping")
            _assert_event_envelope_v1(
                canonical_events,
                expected,
                label=f"action[{index}].E",
                canonical=True,
            )

            for view_index, raw_view in enumerate(row.get("views") or []):
                if not isinstance(raw_view, Mapping):
                    raise TypeError(
                        f"action row {index}.views[{view_index}] must be a mapping"
                    )
                raw_view_role = raw_view.get("role")
                if raw_view_role is None:
                    raise TypeError(
                        f"action row {index}.views[{view_index}].role must be set"
                    )
                view_expected = raw_view.get("E")
                if not isinstance(view_expected, Mapping):
                    raise TypeError(
                        f"action row {index}.views[{view_index}].E must be a mapping"
                    )
                projected_events = _interval_events_v1(
                    selected,
                    run=run,
                    role=str(raw_view_role),
                    after_event_seq=before_seq,
                    through_event_seq=after_seq,
                )
                _assert_event_envelope_v1(
                    projected_events,
                    view_expected,
                    label=f"action[{index}].views[{view_index}].E",
                    canonical=True,
                )

            blanket = row.get("blanket") or {}
            if blanket:
                if not isinstance(blanket, Mapping):
                    raise TypeError(f"action row {index}.blanket must be a mapping")
                _assert_data_blanket_v1(
                    strategy=selected,
                    run=run,
                    blanket=blanket,
                    live_events=live_events,
                    dispatch_result=result,
                    canonical_events=canonical_events,
                    before_event_seq=before_seq,
                    action=A,
                )

            save_cursor = row.get("save_cursor")
            if save_cursor is not None:
                cursor_name = str(save_cursor)
                if not cursor_name:
                    raise ValueError(f"action row {index}.save_cursor must be non-empty")
                saved_cursors[cursor_name] = int(after_seq)

            admitted += 1

        final_seq = selected.latest_committed_event_seq_v1(run=run)
        return LocalDryRunReceiptV1(
            source=str(source),
            strategy=str(selected.strategy_name),
            attempted_actions=len(actions),
            admitted_actions=admitted,
            preflight_exceptions=exceptions,
            preflight_rejections=rejections,
            final_event_seq=int(final_seq),
            saved_cursors=dict(saved_cursors),
        )
    finally:
        selected.close_run_v1(run=run)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=(
            "python -m ways_to_run.dry_run_examples.dry_run_standard_lingo."
            "local_dry_run_launcher"
        ),
        description=(
            "Run one authored Thinkument P/SM/C tape against a standard dry-run "
            "A/E sequence through the backend strategy membrane."
        ),
    )
    add_live_run_source_arguments_v1(parser)
    parser.add_argument(
        "--actions",
        required=True,
        metavar="MODULE:ATTRIBUTE",
        help=(
            "Sequence (or zero-argument callable returning a sequence) of standard "
            "STEP/UNDO/REDO/PREFLIGHT_* action rows."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    tape = live_run_tape_from_namespace_v1(args)
    prepare_runtime_refs_v1(tuple(args.prepare or ()))
    actions = resolve_action_rows_ref_v1(args.actions)
    receipt = run_standard_dry_run_v1(
        program=tape.P,
        session_metadata=tape.SM,
        initial_parameter_overrides=tape.C,
        actions=actions,
        source=str(args.source),
    )

    if bool(getattr(args, "json_output", False)):
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print(
            "Dry run passed: "
            f"{receipt.source} / {receipt.attempted_actions} A/E row(s) / "
            f"final event_seq={receipt.final_event_seq}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LocalDryRunReceiptV1",
    "main",
    "resolve_action_rows_ref_v1",
    "resolve_object_ref_v1",
    "run_standard_dry_run_v1",
]
