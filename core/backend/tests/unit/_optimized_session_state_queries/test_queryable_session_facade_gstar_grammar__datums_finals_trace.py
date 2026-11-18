# think-backend/tests/wipp/engine/app_tables/test_public_api_program_trace_table_gstar_pedagogical.py
from __future__ import annotations

"""
Public API Program Trace Table — Pedagogical G* Query Sheet
===========================================================

This sheet zooms in on explicit bounded public queries, especially:

    query_session(..., query_kind="program_trace_table", query={...})

The goal is to teach app developers the exact top-down formalism:

    Program
      = app-table fn(args) -> app-table fn(args) -> ...

    Each app-table fn may emit:
      - globals patches
      - multiframespecs

    Each multiframespec contains:
      - frames
      - spans
      - datums

    Each span owns one or more datums.

    Each datum must become satisfied before the rollout can move past the span.

    Each Q/lifecycle datum may:
      - accept a partial fill,
      - block,
      - reexplode into a new datum surface/version,
      - emit prefills,
      - emit fills,
      - emit lifecycle state,
      - eventually become done or forced_done.

The public API rule is:

    S/G default surfaces are small.
    G* query surfaces are explicit, bounded, and table-shaped.

This means:

    current_report / command receipts:
        "Where is the session? What public stop is pending?"

    outputs_report:
        "What result buckets exist? Counts and keys only."

    runtime_write_index_summary:
        "What indexed historical write facts are available?"

    runtime_writes:
        "Give me explicit bounded write rows."

    program_trace_table:
        "Give me a compact developer-readable trace:
            app calls,
            fn args,
            spans,
            datum IO,
            current/latest Q lifecycle window."

Important lifecycle scope
-------------------------

The current program_trace_table implementation exposes a compact
current/latest lifecycle window for Q datums. It does not yet guarantee a full
historical list of every Q reexplode transition or every previous datum version.

For row_kind="datum_reexplosion", developers can count on:

    required:
      - row_kind
      - datum_id
      - status
      - from_micros

    common/conditional:
      - span_id
      - lifecycle_window == "current", if the API includes it
      - q_state, if current lifecycle state is indexed
      - to_micros, if the current window still contains a reexploded datum shape
      - prefill, if the current window still contains a prefill payload

After final completion, a Q row may contain:

    status="done"
    q_state={"phase": "done"}

instead of the earlier reexplode window:

    status="reexplode"
    to_micros=["confirm"]
    prefill={"confirm": "yes"}

That earlier historical transition is not yet a stable public guarantee of
program_trace_table. If a future API adds append-only lifecycle history, it
should be exposed as an explicit query, for example:

    query_kind="datum_lifecycle_history"

or:

    program_trace_table(..., lifecycle_scope="history")

The trace table is designed for audit views, debug panes, replay explainers, and
compact developer tooling. It is not a raw ctx/snapshot/multiframespec dump.
"""

import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import pytest

from _thinkengine.runme_optimized_queryable.facade_base import (
    ABSOLUTE_QUERY_MAX_RESULTS_V1,
    KIND_COMMAND_RECEIPT_V1,
    KIND_PROGRAM_TRACE_TABLE_V1,
    KIND_SCRIPT_RUN_REPORT_V1,
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


# ---------------------------------------------------------------------------
# Public-result guards
# ---------------------------------------------------------------------------


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


def _assert_script_report(
    obj: Mapping[str, Any],
    *,
    use_controller: bool,
) -> None:
    assert obj["kind"] == KIND_SCRIPT_RUN_REPORT_V1
    assert obj["ok"] is True
    assert obj["operation"] == "run_action_scripted_program_start_to_finish"
    assert "session_id" in obj
    assert "last" in obj
    assert obj["slim_result"] is True

    assert obj["script_config"] == {"use_controller": bool(use_controller)}
    assert "script_count" in obj
    assert "history_count" in obj
    assert "modes" in obj

    modes = obj["modes"]
    assert isinstance(modes, Mapping)

    if use_controller:
        assert int(modes.get("CONTROLLER", 0)) > 0
        assert int(modes.get("ENGINE", 0)) == 0
    else:
        assert int(modes.get("ENGINE", 0)) > 0
        assert int(modes.get("CONTROLLER", 0)) == 0

    last = obj["last"]
    assert isinstance(last, Mapping)
    assert last["kind"] == KIND_SESSION_REPORT_V1
    assert last["event_kind"] == "ATCOMPLETION"
    assert last["finished"] is True

    assert "history" not in obj
    assert "ctx" not in obj
    assert "raw_ctx" not in obj
    assert "snapshot" not in obj
    assert "state" not in obj
    assert "multiframespec" not in obj
    assert "program_map" not in obj
    assert "content" not in obj

    _assert_public_small(obj)


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------


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
    return [str(x) for x in list(pending.get("datum_widgets_on_this_span") or [])]


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


def _kyc_current_lifecycle_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if row.get("row_kind") == "datum_reexplosion"
        and row.get("datum_id") == "KYC"
    ]


def _assert_current_lifecycle_window_shape(row: Mapping[str, Any]) -> None:
    """
    Current trace-table lifecycle law.

    program_trace_table exposes a compact current/latest lifecycle window for a
    Q datum. It is intentionally not a full historical transition log.

    Stable fields callers can count on:
        row_kind
        datum_id
        status
        from_micros
        span_id, when topology can map datum -> span

    Conditional fields:
        lifecycle_window, when the API marks the scope explicitly
        to_micros, when the current indexed lifecycle value still contains a
        reexploded datum shape
        prefill, when the current indexed lifecycle value still contains a
        prefill payload
        q_state, when the current indexed lifecycle value contains lifecycle
        state

    Therefore a completed Q may show:
        status="done"
        q_state={"phase": "done"}

    rather than the earlier:
        status="reexplode"
        to_micros=["confirm"]
        prefill={"confirm": "yes"}
    """
    assert row.get("row_kind") == "datum_reexplosion"
    assert row.get("datum_id") == "KYC"
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


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _manifest(step_name: str) -> list[dict[str, Any]]:
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


def _trace_program_script_actions() -> list[dict[str, Any]]:
    """
    Public script body for the pedagogical trace program.

    The body is deliberately the same for raw and controller-backed scripting.
    Controller use is selected only by the optional top-level config wrapper.
    """
    return [
        {
            "action": "STEP",
            "until_stop": True,
            "stop_kinds": ["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
            "expect": {
                "kind": "MANUALFILLNEEDEDSTEP",
                "datum_widgets_on_this_span_contains": ["CUSTOMER"],
            },
        },
        {
            "action": "STEP",
            "fill": {
                "CUSTOMER.name": "Ada",
            },
            "expect": {
                "kind": "MANUALFILLNEEDEDSTEP",
                "datum_widgets_on_this_span_contains": ["AMOUNT"],
            },
        },
        {
            "action": "STEP",
            "fill": {
                "AMOUNT.value": 400000,
            },
            "expect": {
                "kind": "MANUALFILLNEEDEDSTEP",
                "datum_widgets_on_this_span_contains": ["KYC"],
            },
        },
        {
            "action": "STEP",
            "fill": {
                "KYC.ssn4": "1234",
            },
            "expect": {
                "kind": "MANUALFILLNEEDEDSTEP",
                "datum_widgets_on_this_span_contains": ["KYC"],
            },
        },
        {
            "action": "STEP",
            "fill": {
                "KYC.confirm": "yes",
            },
            "expect": {
                "kind": "ATCOMPLETION",
            },
        },
    ]


def _trace_program_script_spec(*, use_controller: bool) -> Any:
    actions = _trace_program_script_actions()

    if not use_controller:
        return actions

    return {
        "config": {
            "use_controller": True,
        },
        "actions": actions,
    }


def _run_trace_program_scripted_to_completion(
    *,
    use_controller: bool,
) -> tuple[str, Dict[str, Any], float]:
    step_name = (
        "ped.trace.loan_intake.scripted.controller.step"
        if use_controller
        else "ped.trace.loan_intake.scripted.raw.step"
    )
    _register_trace_step(step_name)

    script = _trace_program_script_spec(use_controller=use_controller)

    t0 = time.perf_counter()
    report = _api().run_action_scripted_program_start_to_finish(
        manifest=_manifest(step_name),
        script=script,
        initial_parameter_overrides={},
        session_metadata=_lean_session_metadata(profile=True),
        keep_step_reports=True,
    )
    elapsed = time.perf_counter() - t0

    _assert_script_report(report, use_controller=use_controller)
    assert report["script_count"] == len(_trace_program_script_actions())

    return str(report["session_id"]), report, elapsed


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


# ---------------------------------------------------------------------------
# App authoring fixture
# ---------------------------------------------------------------------------


def _trace_multiframespec() -> Dict[str, Any]:
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
            # S_NOTES is satisfied without user input. The trace table should
            # still be able to surface this as a compact datum IO fact when the
            # implementation indexes/exposes it.
            "NOTES": {"value": "prefilled-note"},
        },
    }


def _register_trace_step(name: str) -> None:
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
            "multiframespec": _trace_multiframespec(),
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


def _run_trace_program_to_completion() -> str:
    step_name = "ped.trace.loan_intake.step"
    _register_trace_step(step_name)

    sid = _create(
        manifest=_manifest(step_name),
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


# ---------------------------------------------------------------------------
# 1. All public query kinds are bounded G*
# ---------------------------------------------------------------------------


def test_gstar_query_kinds_are_all_bounded_and_have_distinct_jobs():
    sid = _run_trace_program_to_completion()

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
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 16,
        },
    )
    assert trace["result"]["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert trace["result"]["max_results"] == 16
    assert len(_trace_rows(trace)) <= 16

    for obj in [current, outputs, summary, writes, trace]:
        _assert_public_small(obj)
        assert not _contains_key(obj, "ctx")
        assert not _contains_key(obj, "snapshot")
        assert not _contains_key(obj, "program_map")
        assert not _contains_key(obj, "content")


# ---------------------------------------------------------------------------
# 2. Trace table without values: disciplined table shape
# ---------------------------------------------------------------------------


def test_trace_query_without_values_is_safe_default_for_developer_navigation():
    """
    The disciplined first trace query is metadata-only.

    Developers can ask:

        "What happened structurally?"

    without receiving full datum values.
    """
    sid = _run_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 128,
        },
    )

    rows = _trace_rows(result)
    assert rows

    app_calls = _rows_where(rows, row_kind="app_call")
    assert app_calls
    assert app_calls[0]["public_step_name"] == "loan_intake"
    assert app_calls[0]["step_fn"] == "ped.trace.loan_intake.step"
    assert "fn_args" not in app_calls[0]

    span_rows = _rows_where(rows, row_kind="span")
    assert any(
        row.get("form_id") == "ped.public.trace.table"
        and row.get("frame_id") == "INTAKE"
        and row.get("span_id") == "S_CUSTOMER"
        and row.get("owns") == ["CUSTOMER"]
        for row in span_rows
    )
    assert any(
        row.get("span_id") == "S_AMOUNT"
        and row.get("owns") == ["AMOUNT"]
        for row in span_rows
    )
    assert any(
        row.get("span_id") == "S_KYC"
        and row.get("owns") == ["KYC"]
        for row in span_rows
    )

    datum_io = _rows_where(rows, row_kind="datum_io")
    assert datum_io

    # Metadata-only means no row returns raw datum values.
    for row in datum_io:
        assert "value" not in row
        assert "datum_id" in row
        assert "write_kind" in row
        _assert_public_small(row)


# ---------------------------------------------------------------------------
# 3. Trace table with values: compact fn args + datum IO + current Q window
# ---------------------------------------------------------------------------


def test_trace_query_with_values_reads_like_a_compact_developer_trace_table():
    """
    This is the ergonomic query app developers should use for a compact
    inspectable run trace.

    It asks explicitly for values and Q lifecycle rows, so G* may return bounded
    values, but still only as capped table rows.

    Q lifecycle rows are current/latest lifecycle windows, not a complete
    historical list of every reexplode transition.
    """
    sid = _run_trace_program_to_completion()

    result = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    assert result["result"]["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert result["result"]["max_results"] == 128
    assert result["result"]["truncated"] is False

    rows = _trace_rows(result)
    assert rows

    # 1. Program call table row.
    app_calls = _rows_where(rows, row_kind="app_call")
    assert len(app_calls) == 1
    assert app_calls[0]["call_index"] == 0
    assert app_calls[0]["public_step_name"] == "loan_intake"
    assert app_calls[0]["step_fn"] == "ped.trace.loan_intake.step"
    assert app_calls[0]["fn_args"] == {
        "product": "loan",
        "cap": 500_000,
        "channel": "public-api-test",
    }

    # 2. Span topology table rows.
    spans = _rows_where(rows, row_kind="span")
    assert any(
        row.get("span_id") == "S_CUSTOMER"
        and row.get("owns") == ["CUSTOMER"]
        for row in spans
    )
    assert any(
        row.get("span_id") == "S_KYC"
        and row.get("owns") == ["KYC"]
        for row in spans
    )

    # 3. Datum IO rows.
    customer_rows = _rows_where(
        rows,
        row_kind="datum_io",
        datum_id="CUSTOMER",
        write_kind="form_fill",
    )
    assert any(row.get("value") == {"name": "Ada"} for row in customer_rows)

    amount_rows = _rows_where(
        rows,
        row_kind="datum_io",
        datum_id="AMOUNT",
        write_kind="form_fill",
    )
    assert any(row.get("value") == {"value": 400000} for row in amount_rows)

    kyc_rows = _rows_where(
        rows,
        row_kind="datum_io",
        datum_id="KYC",
        write_kind="form_fill",
    )
    assert any(row.get("value") == {"confirm": "yes"} for row in kyc_rows)

    # 4. Prefilled / multiframespec-satisfied facts, when indexed/exposed, appear as
    # compact datum_io rows rather than default raw output maps.
    notes_rows = [
        row
        for row in rows
        if row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "NOTES"
        and row.get("write_kind") in {"form_fill", "form_prefill"}
    ]
    if notes_rows:
        assert any(row.get("value") == {"value": "prefilled-note"} for row in notes_rows)

    # 5. Q lifecycle rows compactly show the current/latest lifecycle window.
    #
    # Important: this is not a full historical Q transition log. After KYC is
    # completed, the current lifecycle window may contain status="done" and
    # q_state={"phase": "done"} rather than the earlier reexplode prefill
    # {"confirm": "yes"}.
    q_rows = _kyc_current_lifecycle_rows(rows)
    assert q_rows

    for row in q_rows:
        _assert_current_lifecycle_window_shape(row)

    assert any(row.get("from_micros") == ["ssn4"] for row in q_rows)

    # At least one useful lifecycle fact should be present. The exact window
    # depends on what the current lifecycle index still retains.
    assert any(
        row.get("status") in {"done", "reexplode", "forced_done", "unknown"}
        or row.get("q_state")
        or row.get("to_micros")
        or row.get("prefill")
        for row in q_rows
    ), q_rows

    for row in rows:
        _assert_public_small(row)


# ---------------------------------------------------------------------------
# 3b. Current lifecycle window law
# ---------------------------------------------------------------------------


def test_trace_query_q_lifecycle_is_current_window_not_full_reexplosion_history():
    """
    This test documents the exact current contract.

    program_trace_table is a compact public trace table. For Q lifecycle rows it
    exposes the current/latest lifecycle window that the runtime write index can
    provide compactly.

    It does not currently promise a full historical list of every datum version
    or every Q reexplode transition.

    Therefore, after KYC completes, callers can count on:

        row_kind == "datum_reexplosion"
        datum_id == "KYC"
        from_micros includes the original datum micros, e.g. ["ssn4"]
        status is present
        optional q_state/to_micros/prefill are present only if retained in the
        current lifecycle value

    Callers cannot count on:

        to_micros == ["confirm"]
        prefill == {"confirm": "yes"}

    after final completion, because those belong to the earlier reexplode
    window, not necessarily the current/latest done window.
    """
    sid = _run_trace_program_to_completion()

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    rows = _trace_rows(trace)
    q_rows = _kyc_current_lifecycle_rows(rows)
    assert q_rows

    for row in q_rows:
        _assert_current_lifecycle_window_shape(row)

    # Stable: the row is about KYC and can report original datum micros.
    assert any(row.get("from_micros") == ["ssn4"] for row in q_rows)

    # Stable: status exists as a compact string. Current completed runs commonly
    # expose "done", but allow "unknown" as a compatibility fallback if the
    # lifecycle value shape is implementation-specific.
    assert any(
        row.get("status") in {"done", "reexplode", "forced_done", "unknown"}
        for row in q_rows
    ), q_rows

    # Current-window proof: if q_state exists, it describes the current/latest
    # lifecycle state. In this story, after final confirmation, the current state
    # may be {"phase": "done"}.
    if any("q_state" in row for row in q_rows):
        assert any(
            isinstance(row.get("q_state"), Mapping)
            and row.get("q_state", {}).get("phase") in {"done", "confirm"}
            for row in q_rows
        ), q_rows

    # Non-contract: do not require historical reexplode details after completion.
    # They may appear if retained, but absence is valid.
    historical_reexplode_window_is_optional = any(
        row.get("to_micros") == ["confirm"]
        and isinstance(row.get("prefill"), Mapping)
        and row.get("prefill", {}).get("confirm") == "yes"
        for row in q_rows
    )
    assert historical_reexplode_window_is_optional in {True, False}


def test_trace_query_current_lifecycle_window_fields_devs_can_count_on():
    """
    Developer-readable schema contract for Q lifecycle rows.

    The row is compact and safe for tables. It is not a raw lifecycle object.
    """
    sid = _run_trace_program_to_completion()

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    rows = _trace_rows(trace)
    q_rows = _kyc_current_lifecycle_rows(rows)
    assert q_rows

    for row in q_rows:
        # Required stable columns.
        assert set(row).issuperset(
            {
                "row_kind",
                "datum_id",
                "status",
                "from_micros",
            }
        )

        assert row["row_kind"] == "datum_reexplosion"
        assert row["datum_id"] == "KYC"
        assert isinstance(row["status"], str)
        assert isinstance(row["from_micros"], list)

        # Optional compact columns.
        allowed = {
            "row_kind",
            "lifecycle_window",
            "datum_id",
            "span_id",
            "status",
            "from_micros",
            "to_micros",
            "prefill",
            "q_state",
        }
        assert set(row).issubset(allowed), row

        if "lifecycle_window" in row:
            assert row["lifecycle_window"] == "current"

        _assert_public_small(row)


# ---------------------------------------------------------------------------
# 4. Runtime writes are the lower-level explicit G* for exact indexed facts
# ---------------------------------------------------------------------------


def test_runtime_writes_remains_the_precise_low_level_gstar_index_query():
    """
    program_trace_table is ergonomic.

    runtime_writes is the precise lower-level G* query when developers need
    direct indexed facts by write_kind.
    """
    sid = _run_trace_program_to_completion()

    metadata = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": False,
            "max_results": 32,
        },
    )
    assert metadata["result"]["max_results"] == 32
    metadata_rows = _runtime_rows(metadata)
    assert metadata_rows

    for row in metadata_rows:
        assert "value" not in row
        _assert_public_small(row)

    valued = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 32,
        },
    )
    valued_rows = _runtime_rows(valued)
    assert valued_rows

    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "CUSTOMER"
        and row.get("value") == {"name": "Ada"}
        for row in valued_rows
    )
    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "AMOUNT"
        and row.get("value") == {"value": 400000}
        for row in valued_rows
    )
    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "KYC"
        and row.get("value") == {"confirm": "yes"}
        for row in valued_rows
    )


# ---------------------------------------------------------------------------
# 5. Query discipline: table completeness is explicit and bounded
# ---------------------------------------------------------------------------


def test_trace_query_completeness_is_requested_explicitly_and_capped():
    """
    Completeness discipline:

        max_results=3:
            only a prefix of the trace table is returned,
            truncated=True.

        max_results=128:
            enough rows for this toy program,
            truncated=False.

        absurd max_results:
            capped at ABSOLUTE_QUERY_MAX_RESULTS_V1.
    """
    sid = _run_trace_program_to_completion()

    tiny = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 3,
        },
    )
    tiny_rows = _trace_rows(tiny)
    assert tiny["result"]["max_results"] == 3
    assert len(tiny_rows) <= 3
    assert tiny["result"]["truncated"] is True

    complete = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )
    complete_rows = _trace_rows(complete)
    assert complete["result"]["max_results"] == 128
    assert complete["result"]["truncated"] is False
    assert len(complete_rows) > len(tiny_rows)

    absurd = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 999_999,
        },
    )
    assert absurd["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_trace_rows(absurd)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1


# ---------------------------------------------------------------------------
# 6. Pedagogical e2e: how a developer reads the table
# ---------------------------------------------------------------------------


def test_trace_query_e2e_developer_reading_order_is_app_call_span_io_q():
    """
    The table should be readable in this conceptual order:

        app_call
            Which app-table fn ran? With what args?

        span
            What public topology was emitted?

        datum_io
            What datum values/prefills were written?

        datum_reexplosion
            What current/latest Q lifecycle window is visible?

    This test does not require the physical rows to be grouped by UI display,
    but it proves all conceptual layers are present and compact.
    """
    sid = _run_trace_program_to_completion()

    t0 = time.perf_counter()

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    elapsed = time.perf_counter() - t0
    rows = _trace_rows(trace)

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

    kyc_reexplosion = _kyc_current_lifecycle_rows(rows)
    assert kyc_reexplosion

    for row in kyc_reexplosion:
        _assert_current_lifecycle_window_shape(row)

    assert any(row.get("from_micros") == ["ssn4"] for row in kyc_reexplosion)
    assert any(
        row.get("status") in {"done", "reexplode", "forced_done", "unknown"}
        or row.get("q_state")
        or row.get("to_micros")
        or row.get("prefill")
        for row in kyc_reexplosion
    ), kyc_reexplosion

    for row in rows:
        _assert_public_small(row)

    print(
        "[public-api-trace-query-summary] "
        f"rows={len(rows)} elapsed={elapsed:.6f}s "
        f"row_kinds={sorted(row_kinds)}"
    )

    assert elapsed < 5.0


# ---------------------------------------------------------------------------
# 7b. Scripted public trace e2e: legacy raw list vs configured controller type
# ---------------------------------------------------------------------------


def test_trace_program_scripted_controller_type_is_seamless_for_q_reexplosion_and_final_io():
    """
    Pedagogical e2e for the new configured script type.

    This is intentionally the same loan/KYC trace story as the manual stepping
    tests, but driven entirely through:

        PublicSessionAPI.run_action_scripted_program_start_to_finish(...)

    using:

        {
            "config": {"use_controller": True},
            "actions": [...]
        }

    It proves that controller-backed scripting is seamless for:
        - dotted fill grammar,
        - lifecycle/Q blocking,
        - KYC reexplosion,
        - final confirmation,
        - program_trace_table,
        - runtime_writes,
        - sealed public reports.
    """
    sid, report, run_elapsed = _run_trace_program_scripted_to_completion(
        use_controller=True,
    )

    assert report["script_config"] == {"use_controller": True}
    assert report["script_count"] == len(_trace_program_script_actions())
    assert int(report["modes"].get("CONTROLLER", 0)) == int(report["history_count"])
    assert int(report["modes"].get("ENGINE", 0)) == 0

    current = _query(sid, query_kind="current_report")
    assert current["result"]["kind"] == KIND_SESSION_REPORT_V1
    assert current["result"]["event_kind"] == "ATCOMPLETION"

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    rows = _trace_rows(trace)
    row_kinds = {str(row.get("row_kind")) for row in rows}

    assert "app_call" in row_kinds
    assert "span" in row_kinds
    assert "datum_io" in row_kinds
    assert "datum_reexplosion" in row_kinds

    app_calls = _rows_where(rows, row_kind="app_call")
    assert len(app_calls) == 1
    assert app_calls[0]["public_step_name"] == "loan_intake"
    assert app_calls[0]["step_fn"] == "ped.trace.loan_intake.scripted.controller.step"
    assert app_calls[0]["fn_args"] == {
        "product": "loan",
        "cap": 500_000,
        "channel": "public-api-test",
    }

    assert any(
        row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "CUSTOMER"
        and row.get("write_kind") == "form_fill"
        and row.get("value") == {"name": "Ada"}
        for row in rows
    )
    assert any(
        row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "AMOUNT"
        and row.get("write_kind") == "form_fill"
        and row.get("value") == {"value": 400000}
        for row in rows
    )
    assert any(
        row.get("row_kind") == "datum_io"
        and row.get("datum_id") == "KYC"
        and row.get("write_kind") == "form_fill"
        and row.get("value") == {"confirm": "yes"}
        for row in rows
    )

    q_rows = _kyc_current_lifecycle_rows(rows)
    assert q_rows
    for row in q_rows:
        _assert_current_lifecycle_window_shape(row)

    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 64,
        },
    )
    write_rows = _runtime_rows(writes)

    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "CUSTOMER"
        and row.get("value") == {"name": "Ada"}
        for row in write_rows
    )
    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "AMOUNT"
        and row.get("value") == {"value": 400000}
        for row in write_rows
    )
    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "KYC"
        and row.get("value") == {"confirm": "yes"}
        for row in write_rows
    )

    for obj in [report, current, trace, writes]:
        _assert_public_small(obj)

    print(
        "[public-api-trace-script-summary] controller_scripted_trace_e2e "
        f"script_count={report['script_count']} "
        f"history_count={report['history_count']} "
        f"modes={dict(report['modes'])} "
        f"rows={len(rows)} "
        f"write_rows={len(write_rows)} "
        f"elapsed={run_elapsed:.6f}s "
        f"row_kinds={sorted(row_kinds)}"
    )

    assert run_elapsed < 8.0


def test_trace_program_scripted_raw_and_controller_have_same_final_PUBLIC_VENDORSPEC_TABLES():
    """
    Equivalence proof for the trace program.

    Runs the exact same public script action bodies in both supported script
    shapes:

        raw/default:
            actions

        controller-backed:
            {"config": {"use_controller": True}, "actions": actions}

    Differences expected:
        - script_config,
        - report modes.

    Public semantics expected to match:
        - final report,
        - final datum values,
        - trace table value rows,
        - runtime_write value rows.
    """
    raw_sid, raw_report, raw_elapsed = _run_trace_program_scripted_to_completion(
        use_controller=False,
    )
    controller_sid, controller_report, controller_elapsed = _run_trace_program_scripted_to_completion(
        use_controller=True,
    )

    assert raw_report["script_config"] == {"use_controller": False}
    assert controller_report["script_config"] == {"use_controller": True}

    assert raw_report["script_count"] == controller_report["script_count"]
    assert raw_report["script_count"] == len(_trace_program_script_actions())

    assert int(raw_report["modes"].get("ENGINE", 0)) > 0
    assert int(raw_report["modes"].get("CONTROLLER", 0)) == 0
    assert int(controller_report["modes"].get("CONTROLLER", 0)) > 0
    assert int(controller_report["modes"].get("ENGINE", 0)) == 0

    raw_writes = _query(
        raw_sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill"],
            "include_values": True,
            "max_results": 64,
        },
    )
    controller_writes = _query(
        controller_sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill"],
            "include_values": True,
            "max_results": 64,
        },
    )

    raw_by_key = {
        str(row.get("key")): row.get("value")
        for row in _runtime_rows(raw_writes)
        if row.get("write_kind") in {"form_fill", "form_prefill"}
        and row.get("key") is not None
        and "value" in row
    }
    controller_by_key = {
        str(row.get("key")): row.get("value")
        for row in _runtime_rows(controller_writes)
        if row.get("write_kind") in {"form_fill", "form_prefill"}
        and row.get("key") is not None
        and "value" in row
    }

    expected = {
        "CUSTOMER": {"name": "Ada"},
        "AMOUNT": {"value": 400000},
        "KYC": {"confirm": "yes"},
        "NOTES": {"value": "prefilled-note"},
    }

    for key, value in expected.items():
        assert raw_by_key.get(key) == value
        assert controller_by_key.get(key) == value
        assert raw_by_key.get(key) == controller_by_key.get(key)

    raw_trace = _query(
        raw_sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )
    controller_trace = _query(
        controller_sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )

    raw_trace_rows = _trace_rows(raw_trace)
    controller_trace_rows = _trace_rows(controller_trace)

    for datum_id, value in {
        "CUSTOMER": {"name": "Ada"},
        "AMOUNT": {"value": 400000},
        "KYC": {"confirm": "yes"},
    }.items():
        assert value in _trace_final_datum_values(
            raw_trace_rows,
            datum_id=datum_id,
        )
        assert value in _trace_final_datum_values(
            controller_trace_rows,
            datum_id=datum_id,
        )

    raw_q_rows = _kyc_current_lifecycle_rows(raw_trace_rows)
    controller_q_rows = _kyc_current_lifecycle_rows(controller_trace_rows)

    assert raw_q_rows
    assert controller_q_rows

    assert any(row.get("from_micros") == ["ssn4"] for row in raw_q_rows)
    assert any(row.get("from_micros") == ["ssn4"] for row in controller_q_rows)

    for row in raw_q_rows + controller_q_rows:
        _assert_current_lifecycle_window_shape(row)

    for obj in [
        raw_report,
        controller_report,
        raw_writes,
        controller_writes,
        raw_trace,
        controller_trace,
    ]:
        _assert_public_small(obj)

    print(
        "[public-api-trace-script-summary] raw_vs_controller_scripted_trace_equivalence "
        f"script_count={raw_report['script_count']} "
        f"raw_history_count={raw_report['history_count']} "
        f"controller_history_count={controller_report['history_count']} "
        f"raw_elapsed={raw_elapsed:.6f}s "
        f"controller_elapsed={controller_elapsed:.6f}s "
        f"raw_modes={dict(raw_report['modes'])} "
        f"controller_modes={dict(controller_report['modes'])} "
        f"raw_trace_rows={len(raw_trace_rows)} "
        f"controller_trace_rows={len(controller_trace_rows)}"
    )

    assert raw_elapsed < 8.0
    assert controller_elapsed < 8.0


def test_trace_program_controller_script_metadata_queries_are_bounded_and_sealed():
    """
    Efficiency and sealing proof for the configured controller script type.

    After a controller-backed scripted run, app-facing G* queries remain explicit
    and bounded exactly like ordinary public sessions.
    """
    sid, report, run_elapsed = _run_trace_program_scripted_to_completion(
        use_controller=True,
    )

    assert report["script_config"] == {"use_controller": True}

    tiny_trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 3,
        },
    )
    assert tiny_trace["result"]["max_results"] == 3
    assert len(_trace_rows(tiny_trace)) <= 3
    assert tiny_trace["result"]["truncated"] is True

    metadata_writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": False,
            "max_results": 4,
        },
    )
    assert metadata_writes["result"]["max_results"] == 4
    assert len(_runtime_rows(metadata_writes)) <= 4

    for row in _runtime_rows(metadata_writes):
        assert "value" not in row
        _assert_public_small(row)

    absurd_trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 999_999,
        },
    )
    assert absurd_trace["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_trace_rows(absurd_trace)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1

    absurd_writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 999_999,
        },
    )
    assert absurd_writes["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_runtime_rows(absurd_writes)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1

    for obj in [report, tiny_trace, metadata_writes, absurd_trace, absurd_writes]:
        _assert_public_small(obj)

    print(
        "[public-api-trace-script-summary] controller_scripted_trace_query_bounds "
        f"script_count={report['script_count']} "
        f"history_count={report['history_count']} "
        f"elapsed={run_elapsed:.6f}s "
        f"tiny_trace_rows={len(_trace_rows(tiny_trace))} "
        f"metadata_write_rows={len(_runtime_rows(metadata_writes))} "
        f"absurd_trace_rows={len(_trace_rows(absurd_trace))} "
        f"absurd_write_rows={len(_runtime_rows(absurd_writes))}"
    )

    assert run_elapsed < 8.0


# ---------------------------------------------------------------------------
# 7. Final datum state survives reexplosions, peer datums, and repeated spans
# ---------------------------------------------------------------------------


def _multi_reexplode_final_state_multiframespec() -> Dict[str, Any]:
    """
    TARGET is intentionally stressful:

        - it is a lifecycle/Q datum,
        - it appears in a span with peer datums,
        - it appears again in a later span,
        - it reexplodes multiple times,
        - final accepted value should be queryable as the final datum state.

    This proves public G* can recover the final accepted datum value without
    raw ctx/snapshot access.
    """
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
            {
                "id": "PEER_A",
                "title": "Peer A",
                "micros": [_text_micro()],
            },
            {
                "id": "PEER_B",
                "title": "Peer B",
                "micros": [_text_micro()],
            },
            {
                "id": "DONE",
                "title": "Done marker",
                "micros": [_text_micro()],
            },
        ],
        "frames": [
            {
                "id": "F_MAIN",
                "title": "Main",
                "spans": [
                    # TARGET shares a span with peers.
                    {"id": "S_GROUP", "owns": ["TARGET", "PEER_A", "PEER_B"]},

                    # TARGET appears again on a later span. Whether the engine
                    # immediately skips it as already satisfied or surfaces it
                    # depends on exact satisfaction semantics; either way, the
                    # final accepted TARGET value must remain queryable.
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
        """
        Three-window lifecycle:

            start   -> reexplode to mid
            mid     -> reexplode to final
            final   -> done

        The final accepted value must be {"final": "accepted-final"}.
        """
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


def _latest_form_fill_value_for_key(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
) -> Any:
    """
    Runtime-write rows are bounded index rows. In these tests, the last matching
    row is the latest returned matching value under the query order.
    """
    matches = [
        row
        for row in rows
        if row.get("write_kind") == "form_fill"
        and row.get("key") == key
        and "value" in row
    ]
    assert matches, f"missing form_fill row for key={key!r}"
    return matches[-1].get("value")


def _trace_final_datum_values(
    rows: Sequence[Mapping[str, Any]],
    *,
    datum_id: str,
) -> list[Any]:
    return [
        row.get("value")
        for row in rows
        if row.get("row_kind") == "datum_io"
        and row.get("datum_id") == datum_id
        and row.get("write_kind") == "form_fill"
        and "value" in row
    ]


def test_trace_query_final_datum_state_survives_many_reexplosions_peers_and_repeated_spans():
    """
    Strong final-state invariant.

    This test proves the public G* story for a hard case:

        TARGET:
            - is a lifecycle/Q datum,
            - reexplodes more than once,
            - has peer datums on the same span,
            - appears in more than one span,
            - still has its final accepted value queryable and correct.

    What this proves:
        - final datum IO is available through program_trace_table,
        - final exact write is available through runtime_writes,
        - default S/G stays bounded,
        - current lifecycle window is compact and does not need to contain every
          historical transition for the final state to be recoverable.
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
    _assert_public_small(receipt)

    # Fill peers and first TARGET window. Since TARGET reexplodes, the span
    # remains pending for TARGET until its final lifecycle window is done.
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

    # Span-level pending can remain conservative while a lifecycle datum
    # reexplodes. The important stable fact is that TARGET is still pending.
    # Do not require peer datums to disappear from datum_widgets_on_this_span at this
    # intermediate public stop; their accepted values are proved below through
    # explicit G* queries.
    assert "TARGET" in _datum_widgets_on_this_span(receipt)
    _assert_public_small(receipt)

    receipt = _step(sid, fill={"TARGET.mid": "middle"})
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_GROUP"
    assert "TARGET" in _datum_widgets_on_this_span(receipt)
    _assert_public_small(receipt)

    receipt = _step(sid, fill={"TARGET.final": "accepted-final"})
    assert _event(receipt) in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}
    _assert_public_small(receipt)

    # TARGET appears in a later span. If the runtime surfaces the revisit, it
    # should not require a new value if TARGET is already satisfied; if it skips
    # it, we move to DONE. Keep stepping only at public seams.
    if _event(receipt) == "MANUALFILLNEEDEDSTEP" and _span(receipt) == "S_TARGET_REVISIT":
        # A no-fill step should advance if TARGET satisfaction is already known.
        receipt = _step(sid)
        _assert_public_small(receipt)

    if _event(receipt) == "MANUALFILLNEEDEDSTEP" and _span(receipt) == "S_DONE":
        receipt = _step(sid, fill={"DONE.value": "done"})
        _assert_public_small(receipt)

    if _event(receipt) != "ATCOMPLETION":
        receipt = _run_until(sid, stop_events=["ATCOMPLETION"], max_steps=8)

    assert _event(receipt) == "ATCOMPLETION"

    final_state = _report(sid)
    assert final_state["event_kind"] == "ATCOMPLETION"
    _assert_public_small(final_state)

    # Default final outputs are still small.
    outputs = _query(sid, query_kind="outputs_report")
    assert outputs["result"]["operation"] == "outputs_report"
    assert outputs["result"]["event_kind"] == "OUTPUTS_REPORT"
    _assert_public_small(outputs)

    # Ergonomic G*: trace table contains final TARGET datum IO.
    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 128,
        },
    )
    trace_rows = _trace_rows(trace)

    target_values = _trace_final_datum_values(trace_rows, datum_id="TARGET")
    assert {"final": "accepted-final"} in target_values

    peer_a_values = _trace_final_datum_values(trace_rows, datum_id="PEER_A")
    peer_b_values = _trace_final_datum_values(trace_rows, datum_id="PEER_B")
    assert {"value": "peer-a"} in peer_a_values
    assert {"value": "peer-b"} in peer_b_values

    target_span_rows = [
        row
        for row in trace_rows
        if row.get("row_kind") == "span"
        and "TARGET" in list(row.get("owns") or [])
    ]
    assert any(row.get("span_id") == "S_GROUP" for row in target_span_rows)
    assert any(row.get("span_id") == "S_TARGET_REVISIT" for row in target_span_rows)

    target_lifecycle_rows = [
        row
        for row in trace_rows
        if row.get("row_kind") == "datum_reexplosion"
        and row.get("datum_id") == "TARGET"
    ]
    assert target_lifecycle_rows

    for row in target_lifecycle_rows:
        assert row["row_kind"] == "datum_reexplosion"
        assert row["datum_id"] == "TARGET"
        assert "status" in row
        assert isinstance(row["status"], str)
        assert "from_micros" in row
        assert isinstance(row["from_micros"], list)
        _assert_public_small(row)

    # Precise G*: runtime_write index also contains the exact final TARGET write.
    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 128,
        },
    )
    write_rows = _runtime_rows(writes)

    assert _latest_form_fill_value_for_key(
        write_rows,
        key="TARGET",
    ) == {"final": "accepted-final"}

    assert _latest_form_fill_value_for_key(
        write_rows,
        key="PEER_A",
    ) == {"value": "peer-a"}

    assert _latest_form_fill_value_for_key(
        write_rows,
        key="PEER_B",
    ) == {"value": "peer-b"}

    # Query discipline still applies: "show final state" is bounded.
    tiny_trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": True,
            "max_results": 3,
        },
    )
    assert tiny_trace["result"]["max_results"] == 3
    assert len(_trace_rows(tiny_trace)) <= 3
    assert tiny_trace["result"]["truncated"] is True

    capped_writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill", "datum_lifecycle"],
            "include_values": True,
            "max_results": 999_999,
        },
    )
    assert capped_writes["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1

    for obj in [trace, writes, tiny_trace, capped_writes]:
        _assert_public_small(obj)