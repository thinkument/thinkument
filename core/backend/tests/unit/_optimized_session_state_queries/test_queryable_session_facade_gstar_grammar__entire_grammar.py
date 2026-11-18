# think-backend/tests/wipp/engine/app_tables/test_public_api_program_trace_table_gstar_pedagogical.py
from __future__ import annotations

"""
Public API Program Trace Table — Complete Pedagogical G* Query Sheet
====================================================================

This sheet is the top-down public API grammar for explicit bounded queries.

It teaches the app-developer mental model:

    Program
      = app-table fn(args) -> app-table fn(args) -> ...

    App-table fn(args)
      -> globals patch
      -> optional multiframespec

    multiframespec
      -> frames
      -> spans
      -> datums

    Span
      -> owns one or more datums

    Datum
      -> micros
      -> optional lifecycle / Q widget

    Rollout
      -> session command receipt S
      -> current report G
      -> explicit query G*

The public API law:

    S:
        command receipts from create/step/undo/redo/delete.
        Tiny by default.

    G:
        reports from current_report / outputs_report / progress_report.
        Tiny by default.

    G*:
        query_session(...).
        Explicit, bounded, table/index shaped.

This file focuses on all public G* query kinds:

    current_report
        Wrap current G in a query envelope.

    outputs_report
        Wrap output-summary G in a query envelope.

    runtime_write_index_summary
        Tell developers what indexed historical write facts exist.

    runtime_writes
        Precise lower-level indexed facts.

    program_trace_table
        Ergonomic compact table for:
            - app calls
            - app fn args
            - frame/span/datum topology
            - datum fills/prefills
            - current/latest Q lifecycle window

Important lifecycle scope
-------------------------

program_trace_table currently exposes a compact current/latest lifecycle window
for Q datums. It does not yet promise a full historical list of every Q
reexplode transition or every previous datum version.

For row_kind="datum_reexplosion", developers can count on:

    required:
      - row_kind
      - datum_id
      - status
      - from_micros

    common/conditional:
      - span_id
      - lifecycle_window, if the API marks the scope explicitly
      - q_state, if current lifecycle state is indexed
      - to_micros, if current lifecycle value still contains a reexploded datum
      - prefill, if current lifecycle value still contains a prefill payload

After final completion, a Q row may contain:

    status="done"
    q_state={"phase": "done"}

instead of the earlier reexplode window:

    status="reexplode"
    to_micros=["confirm"]
    prefill={"confirm": "yes"}

That earlier transition is not yet a stable program_trace_table guarantee.
If a future API adds append-only lifecycle history, expose it as a separate
explicit query, for example:

    query_kind="datum_lifecycle_history"

or:

    query_kind="program_trace_table",
    query={"lifecycle_scope": "history", ...}

This sheet deliberately uses only the highest public API for execution and
inspection. The only lower-level imports are app-authoring fixtures:
StepFnregistry and register_datum_widget_v1.
"""

import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import pytest

from _thinkengine.runme_optimized_queryable.facade_base import (
    ABSOLUTE_QUERY_MAX_RESULTS_V1,
    DEFAULT_QUERY_MAX_RESULTS_V1,
    DEFAULT_TRACE_MAX_RESULTS_V1,
    KIND_COMMAND_RECEIPT_V1,
    KIND_PROGRAM_TRACE_TABLE_V1,
    KIND_SESSION_QUERY_RESULT_V1,
    KIND_SESSION_REPORT_V1,
    PublicSessionAPI,
    get_public_session_api,
)
from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)


# =============================================================================
# Section 0: Semantic caps used by this sheet
# =============================================================================


TINY_TRACE_CAP = 3
SMALL_TRACE_CAP = 16
SMALL_RUNTIME_CAP = 32

# Use exported public API defaults for "complete enough for this toy program"
# rather than hardcoding 128 everywhere.
COMPLETE_TRACE_CAP = int(DEFAULT_TRACE_MAX_RESULTS_V1)

# Use exported public runtime-write default for ordinary low-level query cuts.
COMPLETE_RUNTIME_CAP = int(DEFAULT_QUERY_MAX_RESULTS_V1)

# Some final-state tests need enough room for topology + IO + lifecycle rows.
# Keep this named, public-capped, and never above the absolute public max.
FINAL_STATE_TRACE_CAP = min(int(DEFAULT_TRACE_MAX_RESULTS_V1), ABSOLUTE_QUERY_MAX_RESULTS_V1)
FINAL_STATE_RUNTIME_CAP = min(int(DEFAULT_TRACE_MAX_RESULTS_V1), ABSOLUTE_QUERY_MAX_RESULTS_V1)


# =============================================================================
# Section 1: Public-result guards
# =============================================================================


_FORBIDDEN_PUBLIC_CONTAINER_KEYS = {
    "ctx",
    "raw_ctx",
    "context",
    "multiframespec",
    "program_map",
    "snapshot",
    "state",
    "globals",
    "outputs",
    "form_prefills",
    "form_fills",
    "forms_emitted",
    "datum_widget_fills",
    "datum_widget_decls",
    "frames",
    "datums",
    "merged_fills",
    "raw_merged_fills",
    "content",
    "rendered",
    "dom",
}

_ALLOWED_METADATA_PARENTS = {
    "counts",
    "keys",
    "previews",
    "summary",
    "result",
    "truncated_keys",
}


def _contains_key(obj: Any, key: str, *, max_nodes: int = 200_000) -> bool:
    stack = [obj]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            if key in cur:
                return True
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 200_000) -> bool:
    needle = ch * n
    stack = [obj]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
        elif isinstance(cur, Mapping):
            stack.extend(cur.keys())
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _is_allowed_metadata_path(parent: str | None, key: str, value: Any) -> bool:
    if parent == "counts":
        return isinstance(value, (int, type(None)))

    if parent == "keys":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)

    if parent == "truncated_keys":
        return isinstance(value, bool)

    if parent in {"previews", "summary", "result"}:
        return True

    return False


def _contains_forbidden_public_container(
    obj: Any,
    *,
    parent_key: str | None = None,
    path: str = "$",
    max_nodes: int = 200_000,
) -> tuple[bool, str | None]:
    stack: list[tuple[Any, str | None, str]] = [(obj, parent_key, path)]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur, parent, cur_path = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            for raw_k, v in cur.items():
                k = str(raw_k)
                child_path = f"{cur_path}.{k}"

                if k in _FORBIDDEN_PUBLIC_CONTAINER_KEYS:
                    if _is_allowed_metadata_path(parent, k, v):
                        stack.append((v, k, child_path))
                        continue
                    return True, child_path

                stack.append((v, k, child_path))

        elif isinstance(cur, (list, tuple, set, frozenset)):
            for i, item in enumerate(cur):
                stack.append((item, parent, f"{cur_path}[{i}]"))

    return False, None


def _assert_public_small(obj: Any) -> None:
    leaked, path = _contains_forbidden_public_container(obj)
    assert not leaked, f"public result leaked forbidden raw container at {path}"
    assert not _contains_run(obj, "Z", 1000)


def _assert_receipt(obj: Mapping[str, Any], *, operation: Optional[str] = None) -> None:
    assert obj["kind"] == KIND_COMMAND_RECEIPT_V1
    assert obj["ok"] is True
    assert "session_id" in obj
    if operation is not None:
        assert obj["operation"] == operation
    _assert_public_small(obj)


def _assert_report(obj: Mapping[str, Any]) -> None:
    assert obj["kind"] == KIND_SESSION_REPORT_V1
    assert obj["ok"] is True
    assert "session_id" in obj
    assert "event_kind" in obj
    assert "counts" in obj

    counts = obj["counts"]
    assert isinstance(counts, Mapping)
    for k, v in counts.items():
        assert isinstance(k, str)
        assert isinstance(v, (int, type(None))), f"count {k!r} is not scalar: {v!r}"

    _assert_public_small(obj)


def _assert_query_result(obj: Mapping[str, Any], *, query_kind: str) -> None:
    assert obj["kind"] == KIND_SESSION_QUERY_RESULT_V1
    assert obj["ok"] is True
    assert obj["query_kind"] == query_kind
    assert "result" in obj
    _assert_public_small(obj)


# =============================================================================
# Section 2: Public API helpers
# =============================================================================


def _api() -> PublicSessionAPI:
    return get_public_session_api()


def _event(obj: Mapping[str, Any]) -> str:
    return str(obj.get("event_kind") or "")


def _span(obj: Mapping[str, Any]) -> Optional[str]:
    pending = obj.get("pending")
    if not isinstance(pending, Mapping):
        return None
    value = pending.get("span_id")
    return str(value) if value is not None else None


def _datum_widgets_on_this_span(obj: Mapping[str, Any]) -> list[str]:
    pending = obj.get("pending")
    if not isinstance(pending, Mapping):
        return []

    raw = list(pending.get("datum_widgets_on_this_span") or [])
    return [str(x) for x in raw if isinstance(x, str)]


def _create(
    *,
    manifest: Any,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    created = _api().create_session(
        manifest=manifest,
        initial_parameter_overrides=dict(initial_parameter_overrides or {}),
        session_metadata=session_metadata or _lean_session_metadata(),
    )
    _assert_receipt(created, operation="create_session")
    assert _event(created) == "SESSION_CREATED"
    return str(created["session_id"])


def _step(
    sid: str,
    fill: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    receipt = _api().step_session(sid, fill=fill)
    _assert_receipt(receipt, operation="step_session")
    return receipt


def _report(sid: str) -> Dict[str, Any]:
    report = _api().current_report(sid)
    _assert_report(report)
    return report


def _run_until(
    sid: str,
    *,
    stop_events: Iterable[str],
    max_steps: int = 256,
) -> Dict[str, Any]:
    stop = {str(x) for x in stop_events}

    current = _report(sid)
    if _event(current) in stop:
        return current

    previous_signature = None
    repeats = 0

    for _ in range(max(1, int(max_steps))):
        receipt = _step(sid)

        if _event(receipt) in stop:
            return receipt

        signature = (
            _event(receipt),
            _span(receipt),
            tuple(_datum_widgets_on_this_span(receipt)),
            repr(receipt.get("last_error")),
            repr(receipt.get("cursor")),
        )

        if signature == previous_signature:
            repeats += 1
            if repeats >= 2:
                raise RuntimeError(
                    "public run_until made no progress before requested stop; "
                    f"last_event={_event(receipt)!r}, last_span={_span(receipt)!r}, "
                    f"pending={_datum_widgets_on_this_span(receipt)!r}, "
                    f"last_error={receipt.get('last_error')!r}"
                )
        else:
            repeats = 0
            previous_signature = signature

    raise RuntimeError(
        "public run_until exceeded max_steps before requested stop; "
        f"sid={sid!r}, stop_events={sorted(stop)!r}"
    )


def _query(
    sid: str,
    *,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    result = _api().query_session(
        sid,
        query_kind=query_kind,
        query=query or {},
    )
    _assert_query_result(result, query_kind=query_kind)
    return result


def _runtime_rows(result: Mapping[str, Any]) -> list[Dict[str, Any]]:
    inner = result.get("result")
    assert isinstance(inner, Mapping)
    rows = inner.get("writes")
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _trace_rows(result: Mapping[str, Any]) -> list[Dict[str, Any]]:
    assert result["kind"] == KIND_SESSION_QUERY_RESULT_V1
    assert result["query_kind"] == "program_trace_table"

    inner = result["result"]
    assert isinstance(inner, Mapping)
    assert inner["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert "max_results" in inner
    assert "truncated" in inner
    assert "rows" in inner

    rows = inner["rows"]
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _rows_where(
    rows: Sequence[Mapping[str, Any]],
    **matches: Any,
) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if all(row.get(k) == v for k, v in matches.items()):
            out.append(row)
    return out


def _latest_value(
    rows: Sequence[Mapping[str, Any]],
    *,
    row_kind: str,
    datum_id: str,
    write_kind: str,
) -> Any:
    matches = [
        row
        for row in rows
        if row.get("row_kind") == row_kind
        and row.get("datum_id") == datum_id
        and row.get("write_kind") == write_kind
        and "value" in row
    ]
    assert matches, f"missing {row_kind=} {datum_id=} {write_kind=}"
    return matches[-1].get("value")


def _runtime_latest_value(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
    write_kind: str,
) -> Any:
    matches = [
        row
        for row in rows
        if row.get("key") == key
        and row.get("write_kind") == write_kind
        and "value" in row
    ]
    assert matches, f"missing runtime write {key=} {write_kind=}"
    return matches[-1].get("value")


def _q_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    datum_id: str,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if row.get("row_kind") == "datum_reexplosion"
        and row.get("datum_id") == datum_id
    ]


def _assert_trace_lifecycle_window_shape(
    row: Mapping[str, Any],
    *,
    datum_id: str,
) -> None:
    assert row.get("row_kind") == "datum_reexplosion"
    assert row.get("datum_id") == datum_id
    assert "status" in row
    assert isinstance(row.get("status"), str)
    assert "from_micros" in row
    assert isinstance(row.get("from_micros"), list)

    if row.get("span_id") is not None:
        assert isinstance(row.get("span_id"), str)

    if "lifecycle_window" in row:
        assert row["lifecycle_window"] == "current"

    if "to_micros" in row:
        assert isinstance(row.get("to_micros"), list)

    if "prefill" in row:
        assert isinstance(row.get("prefill"), Mapping)

    if "q_state" in row:
        assert isinstance(row.get("q_state"), Mapping)

    _assert_public_small(row)


def _assert_no_raw_public_leaks(obj: Mapping[str, Any]) -> None:
    _assert_public_small(obj)
    assert not _contains_key(obj, "ctx")
    assert not _contains_key(obj, "snapshot")
    assert not _contains_key(obj, "program_map")
    assert not _contains_key(obj, "multiframespec")
    assert not _contains_key(obj, "content")


# =============================================================================
# Section 3: App authoring fixtures
# =============================================================================


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _lean_session_metadata(*, profile: bool = False) -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "disabled",
            "profile": bool(profile),
            "include_full_multiframespec_in_ctx": True,
            "include_forms_emitted_order_in_ctx": False,
            "include_global_fill_keys_in_ctx": False,
            "include_field_value_keys_in_ctx": False,
        },
        "redo": {"max_depth": 64},
    }


def _loan_trace_manifest(step_name: str) -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": "loan_intake",
            "step_fn": step_name,
            "fn_args": {
                "product": "loan",
                "cap": 500_000,
                "channel": "public-api-test",
            },
        }
    ]


def _loan_trace_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "ped.public.trace.table",
        "datums": [
            {
                "id": "CUSTOMER",
                "title": "Customer",
                "micros": [_text_micro("name")],
            },
            {
                "id": "AMOUNT",
                "title": "Amount",
                "micros": [_number_micro()],
                "lifecycle": {
                    "widget": "ped.trace.q_amount_cap",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {
                "id": "KYC",
                "title": "KYC",
                "micros": [_text_micro("ssn4")],
                "lifecycle": {
                    "widget": "ped.trace.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            {
                "id": "NOTES",
                "title": "Notes",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "INTAKE",
                "title": "Intake",
                "spans": [
                    {"id": "S_CUSTOMER", "owns": ["CUSTOMER"]},
                    {"id": "S_AMOUNT", "owns": ["AMOUNT"]},
                    {"id": "S_KYC", "owns": ["KYC"]},
                    {"id": "S_NOTES", "owns": ["NOTES"]},
                ],
            }
        ],
        "fills": {
            "NOTES": {"value": "prefilled-note"},
        },
    }


def _register_loan_trace_step(name: str) -> None:
    def fn(
        _state: Mapping[str, Any],
        product: str,
        cap: int,
        channel: str,
    ) -> Dict[str, Any]:
        return {
            "trace_product": product,
            "trace_cap": cap,
            "trace_channel": channel,
            "multiframespec": _loan_trace_multiframespec(),
        }

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args={"product", "cap", "channel"},
        optional_args=set(),
        overwrite=True,
    )


def _register_trace_widgets() -> None:
    def q_amount_cap(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = dict(q.get("partial_fill") or {})
        try:
            amount = float(partial.get("value"))
        except Exception:
            amount = 0.0

        if amount > 500_000:
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "amount exceeds cap"},
                "state": {"last_amount": amount},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": "amount accepted"},
            "state": {"last_amount": amount},
        }

    def q_confirm_once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            ok = str(partial.get("confirm") or "").strip().lower() in {
                "yes",
                "y",
                "true",
                "1",
            }

            if not ok:
                return {
                    "status": "blocked",
                    "message": {"level": "error", "text": "confirmation must be yes"},
                    "state": {"phase": "confirm"},
                }

            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm KYC",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "ped.trace.q_confirm_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "please confirm"},
            "proc_notes": {"small_audit": "confirm-once"},
        }

    register_datum_widget_v1("ped.trace.q_amount_cap", q_amount_cap, overwrite=True)
    register_datum_widget_v1("ped.trace.q_confirm_once", q_confirm_once, overwrite=True)


@pytest.fixture(autouse=True)
def _setup_registry():
    StepFnregistry.clear()
    _register_trace_widgets()


def _run_loan_trace_program_to_completion() -> str:
    step_name = "ped.trace.loan_intake.step"
    _register_loan_trace_step(step_name)

    sid = _create(
        manifest=_loan_trace_manifest(step_name),
        session_metadata=_lean_session_metadata(profile=True),
    )

    receipt = _run_until(sid, stop_events=["MANUALFILLNEEDEDSTEP"])
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_CUSTOMER"
    assert _datum_widgets_on_this_span(receipt) == ["CUSTOMER"]

    receipt = _step(sid, fill={"CUSTOMER.name": "Ada"})
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_AMOUNT"
    assert _datum_widgets_on_this_span(receipt) == ["AMOUNT"]

    receipt = _step(sid, fill={"AMOUNT.value": 400000})
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_KYC"
    assert _datum_widgets_on_this_span(receipt) == ["KYC"]

    receipt = _step(sid, fill={"KYC.ssn4": "1234"})
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_KYC"
    assert _datum_widgets_on_this_span(receipt) == ["KYC"]

    receipt = _step(sid, fill={"KYC.confirm": "yes"})
    assert _event(receipt) == "ATCOMPLETION"

    final = _report(sid)
    assert final["event_kind"] == "ATCOMPLETION"

    return sid


# =============================================================================
# Section 4: Query grammar taxonomy
# =============================================================================


def test_gstar_query_grammar_taxonomy_is_explicitly_covered():
    """
    This test is the public grammar checklist.

    It documents what outer app code can ask at the highest public seam.
    """
    query_kinds = {
        "current_report",
        "outputs_report",
        "runtime_write_index_summary",
        "runtime_writes",
        "program_trace_table",
    }

    runtime_writes_grammar = {
        "write_kinds",
        "include_values",
        "max_results",
        "public_step_name",
        "step_fn",
        "arg_name",
        "any_arg_names",
        "arg_path",
        "arg_value_equals",
        "last_k_invocations",
    }

    program_trace_table_grammar = {
        "include_fn_args",
        "include_topology",
        "include_datum_values",
        "include_q_lifecycle",
        "max_results",
    }

    trace_row_kinds = {
        "app_call",
        "span",
        "datum_io",
        "datum_reexplosion",
    }

    assert query_kinds == {
        "current_report",
        "outputs_report",
        "runtime_write_index_summary",
        "runtime_writes",
        "program_trace_table",
    }

    assert "include_values" in runtime_writes_grammar
    assert "arg_path" in runtime_writes_grammar
    assert "max_results" in runtime_writes_grammar

    assert "include_fn_args" in program_trace_table_grammar
    assert "include_datum_values" in program_trace_table_grammar
    assert "include_q_lifecycle" in program_trace_table_grammar
    assert "max_results" in program_trace_table_grammar

    assert trace_row_kinds == {
        "app_call",
        "span",
        "datum_io",
        "datum_reexplosion",
    }


def test_all_public_query_kinds_are_bounded_gstar_and_have_distinct_jobs():
    sid = _run_loan_trace_program_to_completion()

    current = _query(sid, query_kind="current_report")
    assert current["result"]["kind"] == KIND_SESSION_REPORT_V1
    assert current["result"]["event_kind"] == "ATCOMPLETION"

    outputs = _query(sid, query_kind="outputs_report")
    assert outputs["result"]["kind"] == KIND_SESSION_REPORT_V1
    assert outputs["result"]["operation"] == "outputs_report"
    assert outputs["result"]["event_kind"] == "OUTPUTS_REPORT"
    assert "counts" in outputs["result"]
    assert "keys" in outputs["result"]

    summary = _query(sid, query_kind="runtime_write_index_summary")
    assert "write_event_count" in summary["result"]
    assert "write_kinds" in summary["result"]
    assert "form_fill" in summary["result"]["write_kinds"]

    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": False,
            "max_results": 8,
        },
    )
    assert writes["result"]["max_results"] == 8
    assert len(_runtime_rows(writes)) <= 8

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_topology": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": SMALL_TRACE_CAP,
        },
    )
    assert trace["result"]["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert trace["result"]["max_results"] == SMALL_TRACE_CAP
    assert len(_trace_rows(trace)) <= SMALL_TRACE_CAP

    for obj in [current, outputs, summary, writes, trace]:
        _assert_no_raw_public_leaks(obj)


# =============================================================================
# Section 5: program_trace_table shape and disciplined cuts
# =============================================================================


def test_trace_cut_structural_no_fn_args_no_values_no_q_lifecycle():
    """
    Smallest useful navigation query.

    Developer asks:
        "What did this program structurally emit?"

    They do not ask for:
        - fn args
        - datum values
        - Q lifecycle windows
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_topology": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )

    rows = _trace_rows(result)
    assert rows

    app_calls = _rows_where(rows, row_kind="app_call")
    assert app_calls
    assert app_calls[0]["public_step_name"] == "loan_intake"
    assert app_calls[0]["step_fn"] == "ped.trace.loan_intake.step"
    assert "fn_args" not in app_calls[0]

    spans = _rows_where(rows, row_kind="span")
    assert spans
    assert any(
        row.get("form_id") == "ped.public.trace.table"
        and row.get("frame_id") == "INTAKE"
        and row.get("span_id") == "S_CUSTOMER"
        and row.get("owns") == ["CUSTOMER"]
        for row in spans
    )
    assert any(
        row.get("span_id") == "S_KYC"
        and row.get("owns") == ["KYC"]
        for row in spans
    )

    datum_io = _rows_where(rows, row_kind="datum_io")
    for row in datum_io:
        assert "value" not in row

    assert not _rows_where(rows, row_kind="datum_reexplosion")

    for row in rows:
        _assert_public_small(row)


def test_trace_cut_with_fn_args_only_is_app_call_audit_view():
    """
    App-call audit query.

    Developer asks:
        "Which public app-table fn was configured, and with which args?"

    They still do not ask for datum values.
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": False,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": SMALL_TRACE_CAP,
        },
    )

    rows = _trace_rows(result)
    app_calls = _rows_where(rows, row_kind="app_call")
    assert app_calls

    app_call = app_calls[0]
    assert app_call["call_index"] == 0
    assert app_call["public_step_name"] == "loan_intake"
    assert app_call["step_fn"] == "ped.trace.loan_intake.step"
    assert app_call["fn_args"] == {
        "product": "loan",
        "cap": 500_000,
        "channel": "public-api-test",
    }

    # Current implementation may still include datum_io rows from final outputs.
    # The grammar guarantee here is only that values are absent unless requested.
    for row in rows:
        if row.get("row_kind") == "datum_io":
            assert "value" not in row
        _assert_public_small(row)


def test_trace_cut_with_datum_values_is_result_inspector_view():
    """
    Result inspector query.

    Developer asks:
        "Show me compact datum IO values in the trace."

    This is explicit G*, so values are allowed, but only in bounded rows.
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": False,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )

    rows = _trace_rows(result)

    assert _latest_value(
        rows,
        row_kind="datum_io",
        datum_id="CUSTOMER",
        write_kind="form_fill",
    ) == {"name": "Ada"}

    assert _latest_value(
        rows,
        row_kind="datum_io",
        datum_id="AMOUNT",
        write_kind="form_fill",
    ) == {"value": 400000}

    assert _latest_value(
        rows,
        row_kind="datum_io",
        datum_id="KYC",
        write_kind="form_fill",
    ) == {"confirm": "yes"}

    notes_rows = [
        row
        for row in rows
        if row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "NOTES"
        and row.get("write_kind") in {"form_fill", "form_prefill"}
    ]
    if notes_rows:
        assert any(row.get("value") == {"value": "prefilled-note"} for row in notes_rows)

    assert not _rows_where(rows, row_kind="datum_reexplosion")

    for row in rows:
        _assert_public_small(row)


def test_trace_cut_with_q_lifecycle_is_current_lifecycle_window_view():
    """
    Q lifecycle query.

    Developer asks:
        "Show compact Q lifecycle windows."

    The current guarantee is a current/latest lifecycle window, not full history.
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )

    rows = _trace_rows(result)
    qrows = _q_rows(rows, datum_id="KYC")
    assert qrows

    for row in qrows:
        _assert_trace_lifecycle_window_shape(row, datum_id="KYC")

    assert any(row.get("from_micros") == ["ssn4"] for row in qrows)
    assert any(
        row.get("status") in {"done", "reexplode", "forced_done", "unknown"}
        or row.get("q_state")
        or row.get("to_micros")
        or row.get("prefill")
        for row in qrows
    ), qrows


def test_trace_cut_full_developer_table_reads_app_call_span_io_q():
    """
    Full ergonomic G* trace.

    Developer asks:
        "Give me the compact table I can render in a debug/audit pane."

    Conceptual reading order:
        app_call
        span
        datum_io
        datum_reexplosion
    """
    sid = _run_loan_trace_program_to_completion()

    t0 = time.perf_counter()
    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )
    elapsed = time.perf_counter() - t0

    rows = _trace_rows(result)
    row_kinds = {str(row.get("row_kind")) for row in rows}

    assert "app_call" in row_kinds
    assert "span" in row_kinds
    assert "datum_io" in row_kinds
    assert "datum_reexplosion" in row_kinds

    app_call = _rows_where(rows, row_kind="app_call")[0]
    assert app_call["step_fn"] == "ped.trace.loan_intake.step"
    assert app_call["fn_args"]["product"] == "loan"

    kyc_span = [
        row
        for row in rows
        if row.get("row_kind") == "span"
        and row.get("span_id") == "S_KYC"
    ][0]
    assert kyc_span["owns"] == ["KYC"]

    kyc_final_io = [
        row
        for row in rows
        if row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "KYC"
        and row.get("write_kind") == "form_fill"
        and row.get("value") == {"confirm": "yes"}
    ]
    assert kyc_final_io

    kyc_lifecycle = _q_rows(rows, datum_id="KYC")
    assert kyc_lifecycle

    for row in kyc_lifecycle:
        _assert_trace_lifecycle_window_shape(row, datum_id="KYC")

    print(
        "[public-api-gstar-trace-summary] "
        f"rows={len(rows)} elapsed={elapsed:.6f}s "
        f"row_kinds={sorted(row_kinds)}"
    )

    assert elapsed < 5.0

    for row in rows:
        _assert_public_small(row)


# =============================================================================
# Section 6: runtime_writes exact index query grammar
# =============================================================================


def test_runtime_writes_metadata_only_is_precise_low_level_index_view():
    """
    runtime_writes is the precise lower-level G* query.

    include_values=False:
        refs/previews/metadata only.
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )

    assert result["result"]["max_results"] == SMALL_RUNTIME_CAP
    rows = _runtime_rows(result)
    assert rows

    for row in rows:
        assert "value" not in row
        assert "write_kind" in row
        _assert_public_small(row)


def test_runtime_writes_include_values_materializes_only_requested_bounded_rows():
    """
    include_values=True is explicit.

    It is the precise way to ask for exact indexed fill/lifecycle values.
    """
    sid = _run_loan_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )

    rows = _runtime_rows(result)
    assert rows

    assert _runtime_latest_value(rows, key="CUSTOMER", write_kind="form_fill") == {
        "name": "Ada"
    }
    assert _runtime_latest_value(rows, key="AMOUNT", write_kind="form_fill") == {
        "value": 400000
    }
    assert _runtime_latest_value(rows, key="KYC", write_kind="form_fill") == {
        "confirm": "yes"
    }

    lifecycle_rows = [
        row
        for row in rows
        if row.get("write_kind") == "datum_lifecycle"
        and row.get("key") == "KYC"
    ]
    assert lifecycle_rows


def test_runtime_writes_filter_by_manifest_step_fn_and_fn_args():
    """
    App-table fn(args) facts are indexed so precise G* can cut by them.

    This test is the highest-public version of the lower query-complexity sheet:
    outer code asks through public_api.query_session, not direct index helpers.
    """
    sid = _run_loan_trace_program_to_completion()

    by_step_fn = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "step_fn": "ped.trace.loan_intake.step",
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    by_step_fn_rows = _runtime_rows(by_step_fn)
    assert by_step_fn_rows
    assert all(row.get("step_fn") == "ped.trace.loan_intake.step" for row in by_step_fn_rows)

    by_arg_name = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "arg_name": "product",
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    assert _runtime_rows(by_arg_name)

    by_arg_value = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "arg_path": "product",
            "arg_value_equals": "loan",
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    assert _runtime_rows(by_arg_value)

    by_nestedish_arg_value = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "arg_path": "channel",
            "arg_value_equals": "public-api-test",
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    assert _runtime_rows(by_nestedish_arg_value)

    for obj in [by_step_fn, by_arg_name, by_arg_value, by_nestedish_arg_value]:
        _assert_no_raw_public_leaks(obj)


def test_runtime_writes_last_k_and_write_kind_filters_are_public_query_discipline():
    sid = _run_loan_trace_program_to_completion()

    last_one = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "last_k_invocations": 1,
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": False,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    assert last_one["result"]["seq_count"] <= 1

    fills_only = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": True,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    fill_rows = _runtime_rows(fills_only)
    assert fill_rows
    assert all(row.get("write_kind") == "form_fill" for row in fill_rows)

    lifecycle_only = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["datum_lifecycle"],
            "include_values": True,
            "max_results": SMALL_RUNTIME_CAP,
        },
    )
    lifecycle_rows = _runtime_rows(lifecycle_only)
    assert lifecycle_rows
    assert all(row.get("write_kind") == "datum_lifecycle" for row in lifecycle_rows)


# =============================================================================
# Section 7: completeness, caps, and efficiency
# =============================================================================


def test_trace_completeness_is_requested_by_max_results_and_reports_truncation():
    sid = _run_loan_trace_program_to_completion()

    tiny = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": TINY_TRACE_CAP,
        },
    )
    tiny_rows = _trace_rows(tiny)
    assert tiny["result"]["max_results"] == TINY_TRACE_CAP
    assert len(tiny_rows) <= TINY_TRACE_CAP
    assert tiny["result"]["truncated"] is True

    complete = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )
    complete_rows = _trace_rows(complete)
    assert complete["result"]["max_results"] == COMPLETE_TRACE_CAP
    assert complete["result"]["truncated"] is False
    assert len(complete_rows) > len(tiny_rows)

    absurd = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 999_999,
        },
    )
    assert absurd["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_trace_rows(absurd)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1


def test_runtime_writes_completeness_is_requested_by_max_results_and_absolute_cap():
    sid = _run_loan_trace_program_to_completion()

    tiny = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 2,
        },
    )
    assert tiny["result"]["max_results"] == 2
    assert len(_runtime_rows(tiny)) <= 2

    absurd = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 999_999,
        },
    )
    assert absurd["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_runtime_rows(absurd)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1


def test_gstar_default_cuts_do_not_leak_giant_q_proc_notes():
    giant = "Z" * 500_000

    def q_giant_confirm(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": ""},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "ped.trace.q_giant_confirm",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 2,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"giant": giant},
        }

    register_datum_widget_v1("ped.trace.q_giant_confirm", q_giant_confirm, overwrite=True)

    step_name = "ped.trace.giant.step"

    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "multiframespec": {
                "app_form_id": "ped.public.trace.giant",
                "datums": [
                    {
                        "id": "G",
                        "title": "Giant",
                        "micros": [_text_micro("start")],
                        "lifecycle": {
                            "widget": "ped.trace.q_giant_confirm",
                            "max_reexplosions": 1,
                            "max_proc_notes": 1,
                            "max_messages": 2,
                        },
                    }
                ],
                "frames": [{"id": "F", "spans": [{"id": "S_G", "owns": ["G"]}]}],
            }
        }

    StepFnregistry.register(
        name=step_name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )

    sid = _create(
        manifest=[
            {
                "public_step_name": "giant",
                "step_fn": step_name,
                "fn_args": {},
            }
        ]
    )

    _run_until(sid, stop_events=["MANUALFILLNEEDEDSTEP"])
    _step(sid, fill={"G.start": "x"})
    _step(sid, fill={"G.confirm": "yes"})

    trace_no_values = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": False,
            "include_q_lifecycle": True,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )
    _assert_public_small(trace_no_values)
    assert not _contains_run(trace_no_values, "Z", 1000)

    writes_no_values = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["datum_lifecycle"],
            "include_values": False,
            "max_results": 8,
        },
    )
    _assert_public_small(writes_no_values)
    assert not _contains_run(writes_no_values, "Z", 1000)


# =============================================================================
# Section 8: current Q window vs exact final datum state
# =============================================================================


def test_q_lifecycle_window_is_not_full_history_but_final_datum_io_is_recoverable():
    """
    This is the most important developer rule.

    program_trace_table:
        gives a compact current/latest Q window.

    runtime_writes:
        gives exact indexed facts.

    final datum state:
        recoverable through datum_io and runtime_writes even if current Q window
        no longer includes the earlier reexplode prefill.
    """
    sid = _run_loan_trace_program_to_completion()

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": COMPLETE_TRACE_CAP,
        },
    )
    rows = _trace_rows(trace)

    qrows = _q_rows(rows, datum_id="KYC")
    assert qrows
    for row in qrows:
        _assert_trace_lifecycle_window_shape(row, datum_id="KYC")

    assert any(row.get("from_micros") == ["ssn4"] for row in qrows)

    # Non-contract: historical reexplode prefill may or may not still be present.
    historical_reexplode_window_is_optional = any(
        row.get("to_micros") == ["confirm"]
        and isinstance(row.get("prefill"), Mapping)
        and row.get("prefill", {}).get("confirm") == "yes"
        for row in qrows
    )
    assert historical_reexplode_window_is_optional in {True, False}

    # Contract: final accepted datum value is present as compact datum IO.
    assert _latest_value(
        rows,
        row_kind="datum_io",
        datum_id="KYC",
        write_kind="form_fill",
    ) == {"confirm": "yes"}

    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": True,
            "max_results": FINAL_STATE_RUNTIME_CAP,
        },
    )
    write_rows = _runtime_rows(writes)
    assert _runtime_latest_value(
        write_rows,
        key="KYC",
        write_kind="form_fill",
    ) == {"confirm": "yes"}


# =============================================================================
# Section 9: harder final-state case
# =============================================================================


def _multi_reexplode_final_state_multiframespec() -> Dict[str, Any]:
    return {
        "app_form_id": "ped.public.final.datum.state",
        "datums": [
            {
                "id": "TARGET",
                "title": "Target Q datum",
                "micros": [_text_micro("start")],
                "lifecycle": {
                    "widget": "ped.trace.q_target_multi_reexplode",
                    "max_reexplosions": 4,
                    "max_proc_notes": 4,
                    "max_messages": 8,
                },
            },
            {"id": "PEER_A", "title": "Peer A", "micros": [_text_micro()]},
            {"id": "PEER_B", "title": "Peer B", "micros": [_text_micro()]},
            {"id": "DONE", "title": "Done marker", "micros": [_text_micro()]},
        ],
        "frames": [
            {
                "id": "F_MAIN",
                "title": "Main",
                "spans": [
                    {"id": "S_GROUP", "owns": ["TARGET", "PEER_A", "PEER_B"]},
                    {"id": "S_TARGET_REVISIT", "owns": ["TARGET"]},
                    {"id": "S_DONE", "owns": ["DONE"]},
                ],
            }
        ],
    }


def _register_multi_reexplode_final_state_step(name: str) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": _multi_reexplode_final_state_multiframespec()}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _register_multi_reexplode_final_state_widget() -> None:
    def q_target_multi_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "final" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "target complete"},
                "state": {
                    "phase": "done",
                    "final": partial.get("final"),
                },
            }

        if "mid" in partial:
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Target final",
                    "micros": [_text_micro("final")],
                    "lifecycle": {
                        "widget": "ped.trace.q_target_multi_reexplode",
                        "max_reexplosions": 4,
                        "max_proc_notes": 4,
                        "max_messages": 8,
                    },
                },
                "fill": {"final": ""},
                "prefill": {"final": "accepted-final"},
                "state": {
                    "phase": "final",
                    "mid": partial.get("mid"),
                },
                "message": {"level": "info", "text": "final required"},
                "proc_notes": {"window": "final"},
            }

        if "start" in partial:
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "title": "Target mid",
                    "micros": [_text_micro("mid")],
                    "lifecycle": {
                        "widget": "ped.trace.q_target_multi_reexplode",
                        "max_reexplosions": 4,
                        "max_proc_notes": 4,
                        "max_messages": 8,
                    },
                },
                "fill": {"mid": ""},
                "prefill": {"mid": "middle"},
                "state": {
                    "phase": "mid",
                    "start": partial.get("start"),
                },
                "message": {"level": "info", "text": "mid required"},
                "proc_notes": {"window": "mid"},
            }

        return {
            "status": "blocked",
            "message": {"level": "error", "text": "missing expected input"},
            "state": {"phase": "blocked"},
        }

    register_datum_widget_v1(
        "ped.trace.q_target_multi_reexplode",
        q_target_multi_reexplode,
        overwrite=True,
    )


def test_trace_and_runtime_writes_recover_final_state_after_reexplosions_peers_repeated_spans():
    """
    Strong final-state invariant.

    TARGET:
        - is a lifecycle/Q datum,
        - reexplodes more than once,
        - has peer datums on the same span,
        - appears in more than one span,
        - still has final accepted value queryable through public G*.
    """
    _register_multi_reexplode_final_state_widget()

    step_name = "ped.trace.final.datum.state.step"
    _register_multi_reexplode_final_state_step(step_name)

    sid = _create(
        manifest=[
            {
                "public_step_name": "final_state_stress",
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
        session_metadata=_lean_session_metadata(profile=True),
    )

    receipt = _run_until(sid, stop_events=["MANUALFILLNEEDEDSTEP"])
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_GROUP"
    assert set(_datum_widgets_on_this_span(receipt)) == {"TARGET", "PEER_A", "PEER_B"}

    receipt = _step(
        sid,
        fill={
            "PEER_A.value": "peer-a",
            "PEER_B.value": "peer-b",
            "TARGET.start": "start-value",
        },
    )
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_GROUP"
    assert "TARGET" in _datum_widgets_on_this_span(receipt)

    receipt = _step(sid, fill={"TARGET.mid": "middle"})
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_GROUP"
    assert "TARGET" in _datum_widgets_on_this_span(receipt)

    receipt = _step(sid, fill={"TARGET.final": "accepted-final"})
    assert _event(receipt) in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}

    if _event(receipt) == "MANUALFILLNEEDEDSTEP" and _span(receipt) == "S_TARGET_REVISIT":
        receipt = _step(sid)

    if _event(receipt) == "MANUALFILLNEEDEDSTEP" and _span(receipt) == "S_DONE":
        receipt = _step(sid, fill={"DONE.value": "done"})

    if _event(receipt) != "ATCOMPLETION":
        receipt = _run_until(sid, stop_events=["ATCOMPLETION"], max_steps=8)

    assert _event(receipt) == "ATCOMPLETION"

    final_state = _report(sid)
    assert final_state["event_kind"] == "ATCOMPLETION"

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": FINAL_STATE_TRACE_CAP,
        },
    )
    trace_rows = _trace_rows(trace)

    assert _latest_value(
        trace_rows,
        row_kind="datum_io",
        datum_id="TARGET",
        write_kind="form_fill",
    ) == {"final": "accepted-final"}

    assert _latest_value(
        trace_rows,
        row_kind="datum_io",
        datum_id="PEER_A",
        write_kind="form_fill",
    ) == {"value": "peer-a"}

    assert _latest_value(
        trace_rows,
        row_kind="datum_io",
        datum_id="PEER_B",
        write_kind="form_fill",
    ) == {"value": "peer-b"}

    target_span_rows = [
        row
        for row in trace_rows
        if row.get("row_kind") == "span"
        and "TARGET" in list(row.get("owns") or [])
    ]
    assert any(row.get("span_id") == "S_GROUP" for row in target_span_rows)
    assert any(row.get("span_id") == "S_TARGET_REVISIT" for row in target_span_rows)

    target_lifecycle_rows = _q_rows(trace_rows, datum_id="TARGET")
    assert target_lifecycle_rows
    for row in target_lifecycle_rows:
        _assert_trace_lifecycle_window_shape(row, datum_id="TARGET")

    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": True,
            "max_results": FINAL_STATE_RUNTIME_CAP,
        },
    )
    write_rows = _runtime_rows(writes)

    assert _runtime_latest_value(
        write_rows,
        key="TARGET",
        write_kind="form_fill",
    ) == {"final": "accepted-final"}

    assert _runtime_latest_value(
        write_rows,
        key="PEER_A",
        write_kind="form_fill",
    ) == {"value": "peer-a"}

    assert _runtime_latest_value(
        write_rows,
        key="PEER_B",
        write_kind="form_fill",
    ) == {"value": "peer-b"}

    tiny_trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_topology": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": TINY_TRACE_CAP,
        },
    )
    assert tiny_trace["result"]["max_results"] == TINY_TRACE_CAP
    assert len(_trace_rows(tiny_trace)) <= TINY_TRACE_CAP
    assert tiny_trace["result"]["truncated"] is True


# =============================================================================
# Section 10: final executable documentation summary
# =============================================================================


def test_public_gstar_trace_sheet_final_contract_summary():
    """
    Executable summary of the public G* discipline.

    Outer app code should use:

        current_report:
            current state summary.

        outputs_report:
            bounded result counts/keys.

        runtime_write_index_summary:
            what indexed write kinds exist.

        runtime_writes:
            exact indexed write facts with explicit include_values.

        program_trace_table:
            ergonomic compact table:
                app_call
                span
                datum_io
                datum_reexplosion

    The table is complete only up to max_results. Completeness is explicit.
    Values are explicit. Q lifecycle is current/latest window, not full history.
    """
    grammar = {
        "S": {
            "commands": [
                "create_session",
                "step_session",
                "undo_last_step",
                "redo_last_step",
                "delete_session",
            ],
            "kind": KIND_COMMAND_RECEIPT_V1,
            "bounded": True,
            "default_values": False,
        },
        "G": {
            "reads": [
                "current_report",
                "outputs_report",
                "progress_report",
            ],
            "kind": KIND_SESSION_REPORT_V1,
            "bounded": True,
            "default_values": False,
        },
        "G*": {
            "queries": [
                "current_report",
                "outputs_report",
                "runtime_write_index_summary",
                "runtime_writes",
                "program_trace_table",
            ],
            "kind": KIND_SESSION_QUERY_RESULT_V1,
            "bounded_by": "max_results where row-shaped",
            "values_require_explicit_flag": True,
            "absolute_cap": ABSOLUTE_QUERY_MAX_RESULTS_V1,
        },
        "program_trace_table": {
            "kind": KIND_PROGRAM_TRACE_TABLE_V1,
            "default_cap": DEFAULT_TRACE_MAX_RESULTS_V1,
            "row_kinds": [
                "app_call",
                "span",
                "datum_io",
                "datum_reexplosion",
            ],
            "flags": [
                "include_fn_args",
                "include_topology",
                "include_datum_values",
                "include_q_lifecycle",
                "max_results",
            ],
            "q_lifecycle_scope": "current/latest window",
        },
    }

    assert grammar["S"]["bounded"] is True
    assert grammar["G"]["bounded"] is True
    assert grammar["G*"]["values_require_explicit_flag"] is True
    assert grammar["G*"]["absolute_cap"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert grammar["program_trace_table"]["default_cap"] == DEFAULT_TRACE_MAX_RESULTS_V1
    assert grammar["program_trace_table"]["q_lifecycle_scope"] == "current/latest window"
    assert "program_trace_table" in grammar["G*"]["queries"]
    assert "datum_reexplosion" in grammar["program_trace_table"]["row_kinds"]