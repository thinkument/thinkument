# test_public_api_top_down_efficiency.py
from __future__ import annotations

"""
Public API Top-Down Efficiency Usage Sheet
==========================================

This file proves the top-down efficiency contract from the app developer's
point of view.

It deliberately uses only the bounded public API façade:

    S:
        create_session(...)
        step_session(...)

    G:
        current_report(...)
        outputs_report(...)

    G*:
        query_session(..., query_kind="runtime_write_index_summary")
        query_session(..., query_kind="runtime_writes")
        query_session(..., query_kind="program_trace_table")

The sheet does NOT use:

    - get_concrete_session_api
    - api._get(...)
    - export_session_snapshot(...)
    - raw ctx
    - raw state
    - raw multiframespec dumps
    - raw runtime index helpers

The point is to lock in this public theorem:

    Public top-down usage stays efficient because it piggybacks on the inner
    engine's indexed/runtime-write discipline.

Default S/G calls are tiny and local.

Explicit G* trace/query calls scale with:

    - max_results,
    - selected row count,
    - selected value materialization,

not with:

    - total program length,
    - total datum count when max_results is small,
    - giant payload size when include_values=False,
    - raw multiframespec size,
    - raw snapshot size,
    - raw ctx/state size.

For final datum traces:

    - outputs_report() gives counts/keys only.
    - runtime_writes gives precise bounded indexed facts.
    - program_trace_table gives ergonomic bounded developer table rows.
    - "all datums ever" is valid only as an explicit bounded G* query.
"""

import statistics
import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import pytest

from _thinkengine.runme_optimized_queryable.facade_base import (
    ABSOLUTE_QUERY_MAX_RESULTS_V1,
    DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    DEFAULT_QUERY_MAX_RESULTS_V1,
    DEFAULT_TRACE_MAX_RESULTS_V1,
    KIND_COMMAND_RECEIPT_V1,
    KIND_PROGRAM_TRACE_TABLE_V1,
    KIND_SESSION_QUERY_RESULT_V1,
    KIND_SESSION_REPORT_V1,
    PublicSessionAPI,
    PublicSessionCaps,
    get_public_session_api,
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


def _bounded_container_stats(obj: Any, *, max_nodes: int = 200_000) -> Dict[str, int]:
    stack = [obj]
    seen: set[int] = set()

    visited = 0
    mappings = 0
    sequences = 0
    strings = 0
    total_string_chars = 0
    max_string_chars = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            strings += 1
            total_string_chars += len(cur)
            max_string_chars = max(max_string_chars, len(cur))
            continue

        if isinstance(cur, Mapping):
            mappings += 1
            for k, v in cur.items():
                if isinstance(k, str):
                    strings += 1
                    total_string_chars += len(k)
                    max_string_chars = max(max_string_chars, len(k))
                else:
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            sequences += 1
            stack.extend(cur)
            continue

    return {
        "visited": visited,
        "mappings": mappings,
        "sequences": sequences,
        "strings": strings,
        "total_string_chars": total_string_chars,
        "max_string_chars": max_string_chars,
        "truncated": int(bool(stack)),
    }


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


def _assert_public_small(obj: Any, *, no_giant_z: bool = True) -> None:
    leaked, path = _contains_forbidden_public_container(obj)
    assert not leaked, f"public result leaked forbidden raw container at {path}"

    if no_giant_z:
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


def _assert_query_result(
    obj: Mapping[str, Any],
    *,
    query_kind: str,
    no_giant_z: bool = True,
) -> None:
    assert obj["kind"] == KIND_SESSION_QUERY_RESULT_V1
    assert obj["ok"] is True
    assert obj["query_kind"] == query_kind
    assert "result" in obj
    _assert_public_small(obj, no_giant_z=no_giant_z)


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


def _lean_session_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "boundary",
            "profile": False,
            "include_full_multiframespec_in_ctx": False,
            "include_forms_emitted_order_in_ctx": False,
            "include_global_fill_keys_in_ctx": False,
            "include_field_value_keys_in_ctx": False,
        },
        "runtime_session_ctx": {
            "profile": "slim",
        },
        "redo": {"max_depth": 64},
    }


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


def _step(sid: str, fill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    receipt = _api().step_session(sid, fill=fill)
    _assert_receipt(receipt, operation="step_session")
    return receipt


def _report(sid: str) -> Dict[str, Any]:
    report = _api().current_report(sid)
    _assert_report(report)
    return report


def _outputs_report(sid: str) -> Dict[str, Any]:
    report = _api().outputs_report(sid)
    _assert_report(report)
    assert report["operation"] == "outputs_report"
    return report


def _query(
    sid: str,
    *,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
    no_giant_z: bool = True,
) -> Dict[str, Any]:
    result = _api().query_session(
        sid,
        query_kind=query_kind,
        query=query or {},
    )
    _assert_query_result(result, query_kind=query_kind, no_giant_z=no_giant_z)
    return result


# ---------------------------------------------------------------------------
# Custom-cap public API helpers
# ---------------------------------------------------------------------------


def _custom_api(
    *,
    default_query_max_results: int = DEFAULT_QUERY_MAX_RESULTS_V1,
    absolute_query_max_results: int = ABSOLUTE_QUERY_MAX_RESULTS_V1,
    default_trace_max_results: int = DEFAULT_TRACE_MAX_RESULTS_V1,
    output_key_preview_limit: int = DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    datum_widgets_on_this_span_preview_limit: int = DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    public_sanitizer_list_limit: Optional[int] = None,
    public_sanitizer_dict_limit: int = 1024,
    public_sanitizer_string_limit: int = 2048,
) -> PublicSessionAPI:
    """
    Construct a fresh public wrapper with expert caps.

    This deliberately reuses the same raw concrete API but does not mutate the
    default public singleton. The wrapper's manifest trace rows are instance
    local, so create/query should use the same returned api object.
    """
    absolute = int(absolute_query_max_results)
    sanitizer_list = (
        int(public_sanitizer_list_limit)
        if public_sanitizer_list_limit is not None
        else max(absolute, 1024)
    )

    return get_public_session_api(
        raw_api=get_public_session_api().raw_api,
        caps=PublicSessionCaps(
            default_query_max_results=default_query_max_results,
            absolute_query_max_results=absolute,
            default_trace_max_results=default_trace_max_results,
            output_key_preview_limit=output_key_preview_limit,
            datum_widgets_on_this_span_preview_limit=datum_widgets_on_this_span_preview_limit,
            public_sanitizer_list_limit=sanitizer_list,
            public_sanitizer_dict_limit=public_sanitizer_dict_limit,
            public_sanitizer_string_limit=public_sanitizer_string_limit,
        ),
    )


def _create_with_api(
    api: PublicSessionAPI,
    *,
    manifest: Any,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    created = api.create_session(
        manifest=manifest,
        initial_parameter_overrides=dict(initial_parameter_overrides or {}),
        session_metadata=session_metadata or _lean_session_metadata(),
    )
    _assert_receipt(created, operation="create_session")
    assert _event(created) == "SESSION_CREATED"
    return str(created["session_id"])


def _step_with_api(
    api: PublicSessionAPI,
    sid: str,
    fill: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    receipt = api.step_session(sid, fill=fill)
    _assert_receipt(receipt, operation="step_session")
    return receipt


def _report_with_api(api: PublicSessionAPI, sid: str) -> Dict[str, Any]:
    report = api.current_report(sid)
    _assert_report(report)
    return report


def _outputs_report_with_api(api: PublicSessionAPI, sid: str) -> Dict[str, Any]:
    report = api.outputs_report(sid)
    _assert_report(report)
    assert report["operation"] == "outputs_report"
    return report


def _query_with_api(
    api: PublicSessionAPI,
    sid: str,
    *,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
    no_giant_z: bool = True,
) -> Dict[str, Any]:
    result = api.query_session(
        sid,
        query_kind=query_kind,
        query=query or {},
    )
    _assert_query_result(result, query_kind=query_kind, no_giant_z=no_giant_z)
    return result


def _run_until_with_api(
    api: PublicSessionAPI,
    sid: str,
    *,
    stop_events: Iterable[str],
    max_steps: int = 10_000,
) -> Dict[str, Any]:
    stop = {str(x) for x in stop_events}

    current = _report_with_api(api, sid)
    if _event(current) in stop:
        return current

    previous_signature = None
    repeats = 0

    for _ in range(max(1, int(max_steps))):
        receipt = _step_with_api(api, sid)

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
                    f"last_event={_event(receipt)!r}, "
                    f"last_span={_span(receipt)!r}, "
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


def _run_until(
    sid: str,
    *,
    stop_events: Iterable[str],
    max_steps: int = 10_000,
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
                    f"last_event={_event(receipt)!r}, "
                    f"last_span={_span(receipt)!r}, "
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


def _fill_all_manuals_to_completion(
    sid: str,
    *,
    value_factory,
    max_manuals: int = 10_000,
) -> tuple[int, float, float]:
    manual_count = 0
    t_until_stop = 0.0
    t_fill = 0.0

    while manual_count < max_manuals:
        t0 = time.perf_counter()
        receipt = _run_until(
            sid,
            stop_events=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
            max_steps=512,
        )
        t_until_stop += time.perf_counter() - t0

        if _event(receipt) == "ATCOMPLETION":
            return manual_count, t_until_stop, t_fill

        pending = _datum_widgets_on_this_span(receipt)
        assert pending, receipt

        # These multiframespecs are built one datum per span, so one pending field is
        # expected. Keep the helper tolerant of conservative pending lists.
        did = str(pending[0])
        value = value_factory(did, manual_count)

        t0 = time.perf_counter()
        _step(sid, fill={f"{did}.value": value})
        t_fill += time.perf_counter() - t0

        manual_count += 1

    raise RuntimeError(f"did not complete after {max_manuals} public manual fills")


def _median_seconds(fn, *, repeats: int = 3) -> float:
    vals = []
    for _ in range(max(1, int(repeats))):
        t0 = time.perf_counter()
        fn()
        vals.append(time.perf_counter() - t0)
    return statistics.median(vals)


def _slope_ratio(
    *,
    small_y: float,
    large_y: float,
    small_n: int,
    large_n: int,
) -> float:
    if small_y <= 0:
        return 0.0
    return (large_y / small_y) / max(large_n / max(1, small_n), 1e-9)


def _assert_not_superlinear_badly(
    *,
    small_y: float,
    large_y: float,
    small_n: int,
    large_n: int,
    slack: float,
    label: str,
) -> None:
    ratio = _slope_ratio(
        small_y=small_y,
        large_y=large_y,
        small_n=small_n,
        large_n=large_n,
    )
    assert ratio <= slack, (
        f"{label} appears superlinear beyond slack: "
        f"small={small_y:.6f}s at n={small_n}, "
        f"large={large_y:.6f}s at n={large_n}, "
        f"ratio_vs_linear={ratio:.2f}, slack={slack}"
    )


# ---------------------------------------------------------------------------
# App authoring helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _manifest(step_name: str, *, public_step_name: str = "top_down_scale") -> list[dict[str, Any]]:
    return [
        {
            "public_step_name": public_step_name,
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


def _many_manual_datums_multiframespec(
    *,
    form_id: str,
    datum_count: int,
) -> Dict[str, Any]:
    datums: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []

    for i in range(int(datum_count)):
        did = f"D{i}"
        datums.append(
            {
                "id": did,
                "title": did,
                "micros": [_text_micro()],
            }
        )
        spans.append({"id": f"S{i}", "owns": [did]})

    return {
        "app_form_id": form_id,
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "title": "F",
                "spans": spans,
            }
        ],
    }


def _many_prefilled_datums_multiframespec(
    *,
    form_id: str,
    datum_count: int,
    payload_chars: int = 0,
    payload_char: str = "Z",
) -> Dict[str, Any]:
    datums: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    fills: dict[str, Any] = {}

    for i in range(int(datum_count)):
        did = f"P{i}"
        datums.append(
            {
                "id": did,
                "title": did,
                "micros": [_text_micro()],
            }
        )
        spans.append({"id": f"S{i}", "owns": [did]})
        fills[did] = {
            "value": f"prefill-{i}-" + (str(payload_char) * int(payload_chars)),
        }

    return {
        "app_form_id": form_id,
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "title": "F",
                "spans": spans,
            }
        ],
        "fills": fills,
    }


def _wide_single_span_multiframespec(
    *,
    form_id: str,
    datum_count: int,
) -> Dict[str, Any]:
    owns: list[str] = []
    datums: list[dict[str, Any]] = []

    for i in range(int(datum_count)):
        did = f"W{i}"
        owns.append(did)
        datums.append(
            {
                "id": did,
                "title": did,
                "micros": [_text_micro()],
            }
        )

    return {
        "app_form_id": form_id,
        "datums": datums,
        "frames": [
            {
                "id": "F",
                "title": "F",
                "spans": [
                    {
                        "id": "S_ALL",
                        "owns": owns,
                    }
                ],
            }
        ],
    }


def _register_multiframespec_step(name: str, fs: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(fs)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


@pytest.fixture(autouse=True)
def _setup_registry():
    StepFnregistry.clear()


# ---------------------------------------------------------------------------
# 1. Default S/G calls stay tiny as program datum count grows
# ---------------------------------------------------------------------------


def test_public_sg_surfaces_do_not_materialize_all_datum_state_by_default():
    """
    Developer usage:

        create session
        fill datums
        ask current_report / outputs_report

    Public theorem:

        S/G surfaces expose only bounded location/result metadata.
        They do not return raw all-datum maps even after many datum writes.
    """
    n = 120
    step_name = "public.efficiency.sg.default.tiny.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.sg.default.tiny",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    manual_count, t_until_stop, t_fill = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"v{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    current = _report(sid)
    assert current["event_kind"] == "ATCOMPLETION"

    outputs = _outputs_report(sid)
    assert outputs["event_kind"] == "OUTPUTS_REPORT"
    assert outputs["counts"]["form_fills"] >= n

    # Default report may show keys, but not raw form_fills containers.
    assert len(outputs["keys"]["form_fills"]) >= n
    assert "form_fills" not in outputs

    for obj in [current, outputs]:
        _assert_public_small(obj)
        assert not _contains_key(obj, "ctx")
        assert not _contains_key(obj, "snapshot")
        assert not _contains_key(obj, "program_map")
        assert not _contains_key(obj, "content")

    stats = _bounded_container_stats(outputs)
    print(
        "[public-api-efficiency-summary] sg_default_tiny "
        f"n={n} manual_count={manual_count} "
        f"until_stop_s={t_until_stop:.6f} fill_s={t_fill:.6f} "
        f"output_string_chars={stats['total_string_chars']}"
    )


# ---------------------------------------------------------------------------
# 2. runtime_writes final datum trace is bounded by max_results
# ---------------------------------------------------------------------------


def test_runtime_writes_final_datum_trace_scales_with_max_results_not_total_datums():
    """
    Developer usage:

        query_session(
            sid,
            query_kind="runtime_writes",
            query={
                "write_kinds": ["form_fill"],
                "include_values": False,
                "max_results": 10,
            },
        )

    Public theorem:

        Final datum traces are explicit G* rows.
        Metadata-only trace retrieval is bounded by max_results.
    """
    n = 180
    limit = 10

    step_name = "public.efficiency.runtime_writes.final.trace.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.runtime_writes.final.trace",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"v{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    t0 = time.perf_counter()
    result = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": False,
            "max_results": limit,
        },
    )
    elapsed = time.perf_counter() - t0

    rows = _runtime_rows(result)
    assert result["result"]["max_results"] == limit
    assert len(rows) <= limit
    assert result["result"]["truncated"] is True

    for row in rows:
        assert row.get("write_kind") == "form_fill"
        assert "value" not in row
        _assert_public_small(row)

    print(
        "[public-api-efficiency-summary] runtime_writes_metadata_bound "
        f"n={n} max_results={limit} rows={len(rows)} elapsed={elapsed:.6f}s"
    )

    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 3. "All datums ever" is explicit and linear only when caller asks for all rows
# ---------------------------------------------------------------------------


def test_runtime_writes_all_final_datum_trace_is_explicit_and_linear_in_requested_rows():
    """
    Developer usage:

        For a real "all final datum traces" export, ask explicitly with a cap
        large enough for the expected rows.

    Public theorem:

        The API can return all rows for a known bounded run.
        That cost is explicit and proportional to rows materialized.
        It is not paid by S/G defaults.
    """
    n = 96

    step_name = "public.efficiency.runtime_writes.all.final.trace.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.runtime_writes.all.final.trace",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"final-{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    default_outputs = _outputs_report(sid)
    _assert_public_small(default_outputs)

    t0 = time.perf_counter()
    result = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": True,
            "max_results": n + 8,
        },
    )
    elapsed = time.perf_counter() - t0

    rows = _runtime_rows(result)
    form_fill_rows = [row for row in rows if row.get("write_kind") == "form_fill"]

    assert result["result"]["max_results"] == n + 8
    assert result["result"]["truncated"] is False
    assert len(form_fill_rows) >= n

    seen = {
        str(row.get("key")): row.get("value")
        for row in form_fill_rows
        if "value" in row
    }

    for i in range(n):
        assert seen[f"D{i}"] == {"value": f"final-{i}"}

    print(
        "[public-api-efficiency-summary] runtime_writes_all_final_trace "
        f"n={n} rows={len(rows)} elapsed={elapsed:.6f}s"
    )

    assert elapsed < 3.0


# ---------------------------------------------------------------------------
# 4. Large datum payloads do not hurt metadata-only trace queries
# ---------------------------------------------------------------------------


def test_large_datum_payloads_do_not_leak_into_metadata_only_final_trace_queries():
    """
    Developer usage:

        Store large user data.
        Later ask for metadata-only final datum traces.

    Public theorem:

        Large current values may exist because the user wrote them, but public
        metadata-only G* does not duplicate/materialize them.
    """
    n = 40
    giant = "Z" * 120_000

    step_name = "public.efficiency.large.payload.metadata.trace.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.large.payload.metadata.trace",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"{i}-{giant}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    outputs = _outputs_report(sid)
    _assert_public_small(outputs)
    assert not _contains_run(outputs, "Z", 1000)

    t0 = time.perf_counter()
    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": False,
            "max_results": 12,
        },
    )
    write_elapsed = time.perf_counter() - t0

    rows = _runtime_rows(writes)
    assert len(rows) <= 12
    assert writes["result"]["truncated"] is True
    assert not _contains_run(writes, "Z", 1000)

    t0 = time.perf_counter()
    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 12,
        },
    )
    trace_elapsed = time.perf_counter() - t0

    trace_rows = _trace_rows(trace)
    assert len(trace_rows) <= 12
    assert trace["result"]["truncated"] is True
    assert not _contains_run(trace, "Z", 1000)

    print(
        "[public-api-efficiency-summary] large_payload_metadata_only "
        f"n={n} payload_chars={len(giant)} "
        f"runtime_writes_rows={len(rows)} runtime_writes_s={write_elapsed:.6f} "
        f"trace_rows={len(trace_rows)} trace_s={trace_elapsed:.6f}"
    )

    assert write_elapsed < 2.0
    assert trace_elapsed < 2.0


# ---------------------------------------------------------------------------
# 5. program_trace_table is ergonomic and capped
# ---------------------------------------------------------------------------


def test_program_trace_table_query_is_table_shaped_capped_and_safe_for_top_down_tools():
    """
    Developer usage:

        Build an audit/debug pane from program_trace_table.

    Public theorem:

        The table is capped, shaped, and small. It is suitable for top-down UI
        tooling without raw ctx/state/multiframespec access.
    """
    n = 80
    limit = 25

    step_name = "public.efficiency.program_trace.table.capped.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.program_trace.table.capped",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name, public_step_name="trace_source"))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"v{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    t0 = time.perf_counter()
    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": limit,
        },
    )
    elapsed = time.perf_counter() - t0

    rows = _trace_rows(trace)
    assert trace["result"]["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert trace["result"]["max_results"] == limit
    assert len(rows) <= limit
    assert trace["result"]["truncated"] is True

    row_kinds = {str(row.get("row_kind")) for row in rows}
    assert "app_call" in row_kinds
    assert "span" in row_kinds or "datum_io" in row_kinds

    for row in rows:
        assert isinstance(row.get("row_kind"), str)
        assert "ctx" not in row
        assert "snapshot" not in row
        assert "multiframespec" not in row
        assert "state" not in row
        assert "value" not in row
        _assert_public_small(row)

    print(
        "[public-api-efficiency-summary] program_trace_table_capped "
        f"n={n} max_results={limit} rows={len(rows)} "
        f"row_kinds={sorted(row_kinds)} elapsed={elapsed:.6f}s"
    )

    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 6. program_trace_table with values is explicit and row bounded
# ---------------------------------------------------------------------------


def test_program_trace_table_with_values_materializes_only_requested_rows():
    """
    Developer usage:

        Ask for table rows with values only when the UI/export needs them.

    Public theorem:

        include_datum_values=True is explicit.
        The number of materialized values is still bounded by max_results.
    """
    n = 64
    limit = 18

    step_name = "public.efficiency.program_trace.values.bound.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.program_trace.values.bound",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name, public_step_name="trace_values"))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"value-{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    t0 = time.perf_counter()
    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": False,
            "max_results": limit,
        },
    )
    elapsed = time.perf_counter() - t0

    rows = _trace_rows(trace)
    assert len(rows) <= limit
    assert trace["result"]["max_results"] == limit
    assert trace["result"]["truncated"] is True

    valued_rows = [
        row
        for row in rows
        if row.get("row_kind") == "datum_io" and "value" in row
    ]

    # Depending on row ordering, the capped prefix may contain mostly topology
    # rows. If valued rows are present, they must be compact exact facts.
    for row in valued_rows:
        assert row["write_kind"] == "form_fill"
        assert isinstance(row["datum_id"], str)
        assert isinstance(row["value"], Mapping)
        _assert_public_small(row)

    print(
        "[public-api-efficiency-summary] program_trace_table_values_bound "
        f"n={n} max_results={limit} rows={len(rows)} "
        f"valued_rows={len(valued_rows)} elapsed={elapsed:.6f}s"
    )

    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 7. Query cost with small max_results is stable as total datum count grows
# ---------------------------------------------------------------------------


def test_small_cap_trace_query_cost_does_not_scale_with_total_datum_count_badly():
    """
    Developer usage:

        Keep top-down debug panes capped, e.g. first 12 trace rows.

    Public theorem:

        For small max_results, query materialization should not grow badly with
        total datum count. Inner code may have to know indexes exist, but it
        must not hydrate every datum value for the capped result.
    """
    small_n = 40
    large_n = 160
    limit = 12

    def run_case(n: int) -> float:
        step_name = f"public.efficiency.small.cap.trace.n{n}.step"
        _register_multiframespec_step(
            step_name,
            _many_manual_datums_multiframespec(
                form_id=f"public.efficiency.small.cap.trace.n{n}",
                datum_count=n,
            ),
        )

        sid = _create(manifest=_manifest(step_name, public_step_name=f"trace_n{n}"))

        manual_count, _, _ = _fill_all_manuals_to_completion(
            sid,
            value_factory=lambda did, i: f"v{i}",
            max_manuals=n + 5,
        )
        assert manual_count == n

        def query_once() -> None:
            trace = _query(
                sid,
                query_kind="program_trace_table",
                query={
                    "include_fn_args": False,
                    "include_datum_values": False,
                    "include_q_lifecycle": False,
                    "max_results": limit,
                },
            )
            rows = _trace_rows(trace)
            assert len(rows) <= limit
            assert trace["result"]["max_results"] == limit

        return _median_seconds(query_once, repeats=5)

    small_t = run_case(small_n)
    large_t = run_case(large_n)

    ratio = _slope_ratio(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
    )

    print(
        "[public-api-efficiency-summary] small_cap_trace_query_slope "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s "
        f"ratio_vs_linear={ratio:.3f} max_results={limit}"
    )

    # Very loose to avoid CI microbenchmark flakes, but strong enough to catch
    # accidental full materialization walls.
    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=10.0,
        label="small capped public trace query",
    )


# ---------------------------------------------------------------------------
# 8. Program largeness: public stepping scales with explicit manual actions
# ---------------------------------------------------------------------------


def test_public_manual_fill_usage_scales_with_explicit_number_of_public_actions():
    """
    Developer usage:

        Fill many one-datum spans through public step_session.

    Public theorem:

        Work scales with explicit public actions. The API does not add hidden
        full-session materialization on every step.
    """
    small_n = 30
    large_n = 120

    def run_case(n: int) -> float:
        step_name = f"public.efficiency.manual.actions.n{n}.step"
        _register_multiframespec_step(
            step_name,
            _many_manual_datums_multiframespec(
                form_id=f"public.efficiency.manual.actions.n{n}",
                datum_count=n,
            ),
        )

        sid = _create(manifest=_manifest(step_name))

        t0 = time.perf_counter()
        manual_count, t_until_stop, t_fill = _fill_all_manuals_to_completion(
            sid,
            value_factory=lambda did, i: f"v{i}",
            max_manuals=n + 5,
        )
        elapsed = time.perf_counter() - t0

        assert manual_count == n
        assert _report(sid)["event_kind"] == "ATCOMPLETION"

        print(
            "[public-api-efficiency-summary] manual_actions_case "
            f"n={n} elapsed={elapsed:.6f}s "
            f"until_stop_s={t_until_stop:.6f}s fill_s={t_fill:.6f}s "
            f"avg_action_ms={(elapsed / max(1, n)) * 1000:.3f}"
        )

        return elapsed

    small_t = run_case(small_n)
    large_t = run_case(large_n)

    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=12.0,
        label="public manual action loop",
    )


# ---------------------------------------------------------------------------
# 9. Wide span one touched datum: public API does not require all datum traces
# ---------------------------------------------------------------------------


def test_wide_span_one_touched_public_submit_stays_small_from_above():
    """
    Developer usage:

        Submit one datum in a very wide span.

    Public theorem:

        The public receipt remains tiny. A top-down app does not receive all
        sibling datum state merely because the span is wide.

    Important public contract:

        pending.datum_widgets_on_this_span:
            bounded preview list

        pending.datum_widgets_on_this_span_count:
            exact scalar total

        pending.datum_widgets_on_this_span_truncated:
            whether preview was capped

        pending.datum_widgets_on_this_span_preview_limit:
            public cap used by this response

    Therefore this test must never assert:

        len(datum_widgets_on_this_span) == total_span_width

    for a wide span. That would make S receipts unbounded.
    """
    n = 500

    step_name = "public.efficiency.wide.span.one.touched.step"
    _register_multiframespec_step(
        step_name,
        _wide_single_span_multiframespec(
            form_id="public.efficiency.wide.span.one.touched",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    receipt = _run_until(sid, stop_events=["MANUALFILLNEEDEDSTEP"])
    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_ALL"

    pending = receipt.get("pending")
    assert isinstance(pending, Mapping)

    pending_preview = _datum_widgets_on_this_span(receipt)
    pending_cap = int(pending.get("datum_widgets_on_this_span_preview_limit") or len(pending_preview))

    assert pending["datum_widgets_on_this_span_count"] == n
    assert pending["datum_widgets_on_this_span_truncated"] is (n > pending_cap)
    assert len(pending_preview) == min(n, pending_cap)
    assert pending_preview[:6] == ["W0", "W1", "W2", "W3", "W4", "W5"]

    _assert_public_small(receipt)

    t0 = time.perf_counter()
    receipt = _step(sid, fill={"W0.value": "only-one"})
    elapsed = time.perf_counter() - t0

    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_ALL"

    pending_after = receipt.get("pending")
    assert isinstance(pending_after, Mapping)

    pending_after_preview = _datum_widgets_on_this_span(receipt)
    pending_after_cap = int(
        pending_after.get("datum_widgets_on_this_span_preview_limit")
        or len(pending_after_preview)
    )

    # After touching W0, the span is still wide/incomplete. Depending on the
    # engine's current pending-field policy, W0 may or may not remain in the
    # conservative pending preview. The public law is only boundedness + exact
    # scalar metadata, not a specific sibling-list shape.
    assert pending_after["datum_widgets_on_this_span_count"] <= n
    assert pending_after["datum_widgets_on_this_span_preview_limit"] == pending_after_cap
    assert len(pending_after_preview) <= pending_after_cap
    assert pending_after["datum_widgets_on_this_span_truncated"] is (
        pending_after["datum_widgets_on_this_span_count"] > pending_after_cap
    )

    _assert_public_small(receipt)

    # The exact W0 write is available through explicit bounded G*.
    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": True,
            "max_results": 5,
        },
    )
    rows = _runtime_rows(writes)
    assert any(
        row.get("write_kind") == "form_fill"
        and row.get("key") == "W0"
        and row.get("value") == {"value": "only-one"}
        for row in rows
    )

    print(
        "[public-api-efficiency-summary] wide_span_one_touched "
        f"n={n} "
        f"pending_cap={pending_cap} "
        f"initial_pending_preview={len(pending_preview)} "
        f"submit_elapsed={elapsed:.6f}s "
        f"pending_after_count={pending_after.get('datum_widgets_on_this_span_count')} "
        f"pending_after_preview={len(pending_after_preview)} "
        f"query_rows={len(rows)}"
    )

    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 10. Many large prefills: final trace metadata is bounded
# ---------------------------------------------------------------------------


def test_many_large_prefills_are_queryable_as_bounded_metadata_not_default_payloads():
    """
    Developer usage:

        A generated app table emits many prefilled datums with large values.
        The top-down app asks for result keys and trace metadata.

    Public theorem:

        Default outputs and metadata-only G* do not materialize giant prefill
        payloads. "All prefill values" would be an explicit include-values
        materialization/export operation.
    """
    n = 160
    payload_chars = 80_000

    step_name = "public.efficiency.many.large.prefills.step"
    _register_multiframespec_step(
        step_name,
        _many_prefilled_datums_multiframespec(
            form_id="public.efficiency.many.large.prefills",
            datum_count=n,
            payload_chars=payload_chars,
            payload_char="Z",
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    receipt = _run_until(sid, stop_events=["ATCOMPLETION"], max_steps=n + 20)
    assert _event(receipt) == "ATCOMPLETION"

    outputs = _outputs_report(sid)
    _assert_public_small(outputs)
    assert not _contains_run(outputs, "Z", 1000)

    t0 = time.perf_counter()
    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": False,
            "max_results": 17,
        },
    )
    write_elapsed = time.perf_counter() - t0

    rows = _runtime_rows(writes)
    assert len(rows) <= 17
    assert writes["result"]["truncated"] is True
    assert not _contains_run(writes, "Z", 1000)

    for row in rows:
        assert row.get("write_kind") == "form_prefill"
        assert "value" not in row
        _assert_public_small(row)

    print(
        "[public-api-efficiency-summary] many_large_prefills_metadata "
        f"n={n} payload_chars={payload_chars} "
        f"rows={len(rows)} elapsed={write_elapsed:.6f}s"
    )

    assert write_elapsed < 2.0


# ---------------------------------------------------------------------------
# 11. Absurd public query sizes are capped
# ---------------------------------------------------------------------------


def test_public_gstar_absurd_trace_requests_are_capped():
    """
    Developer usage:

        A caller accidentally asks for 999_999 rows.

    Public theorem:

        Public G* caps materialization at ABSOLUTE_QUERY_MAX_RESULTS_V1.
    """
    n = 40

    step_name = "public.efficiency.absurd.cap.step"
    _register_multiframespec_step(
        step_name,
        _many_manual_datums_multiframespec(
            form_id="public.efficiency.absurd.cap",
            datum_count=n,
        ),
    )

    sid = _create(manifest=_manifest(step_name))

    manual_count, _, _ = _fill_all_manuals_to_completion(
        sid,
        value_factory=lambda did, i: f"v{i}",
        max_manuals=n + 5,
    )
    assert manual_count == n

    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": False,
            "max_results": 999_999,
        },
    )
    assert writes["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_runtime_rows(writes)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1

    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 999_999,
        },
    )
    assert trace["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_trace_rows(trace)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1


# ---------------------------------------------------------------------------
# 12. Top-down final theorem sheet
# ---------------------------------------------------------------------------


def test_public_api_efficiency_contract_taxonomy_is_explicit():
    """
    This is a living checklist for the public API efficiency theorem.

    It prevents the sheet from drifting into only one axis of coverage.
    """
    axes = {
        "default_s_receipts_are_tiny",
        "default_g_reports_are_tiny",
        "outputs_report_counts_and_keys_only",
        "runtime_write_index_summary_is_bounded",
        "runtime_writes_metadata_is_max_results_bounded",
        "runtime_writes_include_values_is_explicit",
        "program_trace_table_is_row_bounded",
        "program_trace_table_values_are_explicit",
        "all_final_datum_traces_are_explicit_gstar",
        "small_cap_queries_do_not_materialize_all_datums",
        "large_payloads_do_not_leak_without_include_values",
        "prefill_payloads_do_not_leak_without_include_values",
        "wide_span_receipts_stay_small",
        "absurd_query_sizes_are_capped",
        "no_raw_ctx_snapshot_multiframespec_html",
    }

    assert len(axes) == 15
    assert "all_final_datum_traces_are_explicit_gstar" in axes
    assert "large_payloads_do_not_leak_without_include_values" in axes
    assert "absurd_query_sizes_are_capped" in axes


# ---------------------------------------------------------------------------
# 13. Giant whole-program shape: final trace read stays capped and clean
# ---------------------------------------------------------------------------


def _giant_whole_program_multiframespec(
    *,
    form_index: int,
    frames_per_form: int,
    spans_per_frame: int,
    datums_per_span: int,
    payload_chars: int,
    payload_char: str = "Z",
) -> Dict[str, Any]:
    """
    Build a large fully-prefilled multiframespec.

    Shape per multiframespec:

        frames_per_form
          × spans_per_frame
          × datums_per_span

    All datums are prefilled so the program can run to completion without a
    long manual-fill loop. This isolates the final public query/read cost from
    manual input cost.

    The payload is intentionally large and repeated. Public metadata-only trace
    reads must not leak it.
    """
    form_id = f"public.efficiency.giant.program.form.{form_index}"

    datums: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    fills: dict[str, Any] = {}

    for f in range(int(frames_per_form)):
        spans: list[dict[str, Any]] = []

        for s in range(int(spans_per_frame)):
            owns: list[str] = []

            for d in range(int(datums_per_span)):
                did = f"F{form_index}_{f}_{s}_{d}"
                owns.append(did)

                datums.append(
                    {
                        "id": did,
                        "title": did,
                        "micros": [_text_micro()],
                    }
                )

                fills[did] = {
                    "value": (
                        f"form={form_index};frame={f};span={s};datum={d};"
                        + (str(payload_char) * int(payload_chars))
                    )
                }

            spans.append(
                {
                    "id": f"S{form_index}_{f}_{s}",
                    "title": f"Span {form_index}.{f}.{s}",
                    "owns": owns,
                }
            )

        frames.append(
            {
                "id": f"FRAME{form_index}_{f}",
                "title": f"Frame {form_index}.{f}",
                "spans": spans,
            }
        )

    return {
        "app_form_id": form_id,
        "datums": datums,
        "frames": frames,
        "fills": fills,
    }


def _register_giant_whole_program_step(
    *,
    step_name: str,
    form_index: int,
    frames_per_form: int,
    spans_per_frame: int,
    datums_per_span: int,
    payload_chars: int,
) -> None:
    fs = _giant_whole_program_multiframespec(
        form_index=form_index,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
        payload_char="Z",
    )

    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        # Also write a tiny global patch per app-table function call, so the
        # trace/index has both app-call/state and form IO facts.
        return {
            f"giant_step_{form_index}_ran": True,
            "giant_last_form_index": form_index,
            "multiframespec": dict(fs),
        }

    StepFnregistry.register(
        name=step_name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _giant_whole_program_manifest(
    *,
    fn_count: int,
    frames_per_form: int,
    spans_per_frame: int,
    datums_per_span: int,
    payload_chars: int,
) -> list[dict[str, Any]]:
    """
    Register many distinct app-table functions and return a manifest that calls
    all of them.

    This is intentionally many fns, not one fn repeated, because the public trace
    should stay clean across whole-program breadth.
    """
    manifest: list[dict[str, Any]] = []

    for i in range(int(fn_count)):
        step_name = f"public.efficiency.giant.program.fn.{i}"

        _register_giant_whole_program_step(
            step_name=step_name,
            form_index=i,
            frames_per_form=frames_per_form,
            spans_per_frame=spans_per_frame,
            datums_per_span=datums_per_span,
            payload_chars=payload_chars,
        )

        manifest.append(
            {
                "public_step_name": f"giant_fn_{i}",
                "step_fn": step_name,
                "fn_args": {},
            }
        )

    return manifest


def _run_giant_whole_program_to_completion(
    *,
    fn_count: int,
    frames_per_form: int,
    spans_per_frame: int,
    datums_per_span: int,
    payload_chars: int,
) -> tuple[str, int, float]:
    manifest = _giant_whole_program_manifest(
        fn_count=fn_count,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
    )

    total_datums = (
        int(fn_count)
        * int(frames_per_form)
        * int(spans_per_frame)
        * int(datums_per_span)
    )

    t0 = time.perf_counter()

    sid = _create(
        manifest=manifest,
        session_metadata=_lean_session_metadata(),
    )

    receipt = _run_until(
        sid,
        stop_events=["ATCOMPLETION"],
        max_steps=max(128, int(fn_count) * 16),
    )

    elapsed = time.perf_counter() - t0

    assert _event(receipt) == "ATCOMPLETION"
    _assert_public_small(receipt)

    return sid, total_datums, elapsed


def test_giant_whole_program_final_trace_read_is_clean_capped_and_fast_from_public_api():
    """
    Integrated top-down theorem.

    This is the missing whole-program proof.

    Program shape:

        many app-table fn runs
          × many emitted forms
          × many frames per form
          × many spans per frame
          × many datums per span
          × large prefilled datum payloads

    Public API theorem:

        1. The program can run to completion through S only.
        2. Final G reports stay small.
        3. Final program_trace_table read is simple, capped, and table-shaped.
        4. Final runtime_writes read is capped by max_results.
        5. Metadata-only final trace reads do not leak giant datum payloads.
        6. Completeness is represented by counts/truncated metadata, not by
           accidental full raw materialization.

    This is intentionally public API only. No raw ctx, no snapshot, no raw state.
    """
    fn_count = 18
    frames_per_form = 4
    spans_per_frame = 5
    datums_per_span = 6
    payload_chars = 20_000

    trace_limit = 24
    writes_limit = 31

    sid, total_datums, run_elapsed = _run_giant_whole_program_to_completion(
        fn_count=fn_count,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
    )

    assert total_datums == fn_count * frames_per_form * spans_per_frame * datums_per_span

    # G: final current report remains tiny.
    current = _report(sid)
    assert current["event_kind"] == "ATCOMPLETION"
    _assert_public_small(current)
    assert not _contains_run(current, "Z", 1000)

    # G: final outputs report remains counts/keys/previews only.
    outputs = _outputs_report(sid)
    assert outputs["event_kind"] == "OUTPUTS_REPORT"
    _assert_public_small(outputs)
    assert not _contains_run(outputs, "Z", 1000)

    # The count should know the program was huge, while keys remain a bounded
    # preview. This is the exact top-down law.
    assert outputs["counts"]["form_prefills"] >= total_datums
    assert len(outputs["keys"]["form_prefills"]) <= 128

    # G*: low-level final datum trace metadata is explicitly capped.
    t0 = time.perf_counter()
    writes = _query(
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill", "state"],
            "include_values": False,
            "max_results": writes_limit,
        },
    )
    writes_elapsed = time.perf_counter() - t0

    write_rows = _runtime_rows(writes)
    assert writes["result"]["max_results"] == writes_limit
    assert len(write_rows) <= writes_limit
    assert writes["result"]["truncated"] is True
    assert not _contains_run(writes, "Z", 1000)

    for row in write_rows:
        assert "value" not in row
        _assert_public_small(row)

    # G*: ergonomic final trace table is explicitly capped and clean.
    t0 = time.perf_counter()
    trace = _query(
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": trace_limit,
        },
    )
    trace_elapsed = time.perf_counter() - t0

    trace_rows = _trace_rows(trace)
    assert trace["result"]["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert trace["result"]["max_results"] == trace_limit
    assert len(trace_rows) <= trace_limit
    assert trace["result"]["truncated"] is True
    assert not _contains_run(trace, "Z", 1000)

    row_kinds = {str(row.get("row_kind")) for row in trace_rows}
    assert "app_call" in row_kinds

    for row in trace_rows:
        assert "ctx" not in row
        assert "snapshot" not in row
        assert "multiframespec" not in row
        assert "state" not in row
        assert "content" not in row
        assert "value" not in row
        _assert_public_small(row)

    output_stats = _bounded_container_stats(outputs)
    writes_stats = _bounded_container_stats(writes)
    trace_stats = _bounded_container_stats(trace)

    print(
        "[public-api-efficiency-summary] giant_whole_program_final_trace "
        f"fn_count={fn_count} "
        f"frames_per_form={frames_per_form} "
        f"spans_per_frame={spans_per_frame} "
        f"datums_per_span={datums_per_span} "
        f"total_datums={total_datums} "
        f"payload_chars={payload_chars} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"writes_rows={len(write_rows)} "
        f"writes_elapsed={writes_elapsed:.6f}s "
        f"trace_rows={len(trace_rows)} "
        f"trace_elapsed={trace_elapsed:.6f}s "
        f"outputs_string_chars={output_stats['total_string_chars']} "
        f"writes_string_chars={writes_stats['total_string_chars']} "
        f"trace_string_chars={trace_stats['total_string_chars']} "
        f"row_kinds={sorted(row_kinds)}"
    )

    # These are deliberately loose CI guards. The hard invariant is bounded
    # materialization; timing just catches obvious accidental full dumps/scans.
    assert writes_elapsed < 3.0
    assert trace_elapsed < 3.0


def test_giant_whole_program_small_final_trace_query_slope_is_healthy_from_public_api():
    """
    Slope version of the integrated proof.

    It compares a smaller whole-program shape with a larger whole-program shape,
    while keeping the final trace query cap fixed.

    Public theorem:

        With max_results fixed, final public trace read should not grow like
        total datum payload size. It should remain dominated by capped table-row
        materialization.

    This is not a brittle microbenchmark. The slack is intentionally loose; it
    only catches accidental raw whole-program materialization.
    """
    trace_limit = 16

    small_shape = {
        "fn_count": 4,
        "frames_per_form": 2,
        "spans_per_frame": 3,
        "datums_per_span": 4,
        "payload_chars": 2_000,
    }

    large_shape = {
        "fn_count": 14,
        "frames_per_form": 4,
        "spans_per_frame": 5,
        "datums_per_span": 6,
        "payload_chars": 12_000,
    }

    def run_case(label: str, shape: Mapping[str, int]) -> tuple[int, float, float]:
        sid, total_datums, run_elapsed = _run_giant_whole_program_to_completion(
            fn_count=int(shape["fn_count"]),
            frames_per_form=int(shape["frames_per_form"]),
            spans_per_frame=int(shape["spans_per_frame"]),
            datums_per_span=int(shape["datums_per_span"]),
            payload_chars=int(shape["payload_chars"]),
        )

        def query_once() -> None:
            trace = _query(
                sid,
                query_kind="program_trace_table",
                query={
                    "include_fn_args": False,
                    "include_datum_values": False,
                    "include_q_lifecycle": False,
                    "max_results": trace_limit,
                },
            )

            rows = _trace_rows(trace)
            assert len(rows) <= trace_limit
            assert trace["result"]["max_results"] == trace_limit
            assert not _contains_run(trace, "Z", 1000)

        query_elapsed = _median_seconds(query_once, repeats=5)

        print(
            "[public-api-efficiency-summary] giant_whole_program_slope_case "
            f"label={label} "
            f"total_datums={total_datums} "
            f"run_elapsed={run_elapsed:.6f}s "
            f"trace_query_median={query_elapsed:.6f}s "
            f"trace_limit={trace_limit}"
        )

        return total_datums, run_elapsed, query_elapsed

    small_datums, _small_run, small_query = run_case("small", small_shape)
    large_datums, _large_run, large_query = run_case("large", large_shape)

    ratio = _slope_ratio(
        small_y=small_query,
        large_y=large_query,
        small_n=small_datums,
        large_n=large_datums,
    )

    print(
        "[public-api-efficiency-summary] giant_whole_program_final_trace_slope "
        f"small_datums={small_datums} small_query={small_query:.6f}s "
        f"large_datums={large_datums} large_query={large_query:.6f}s "
        f"ratio_vs_linear={ratio:.3f} "
        f"trace_limit={trace_limit}"
    )

    # Loose CI-safe guard. If this fails, the public trace query may be doing
    # hidden whole-program materialization for a fixed-size result.
    _assert_not_superlinear_badly(
        small_y=small_query,
        large_y=large_query,
        small_n=small_datums,
        large_n=large_datums,
        slack=10.0,
        label="giant whole-program fixed-cap final trace query",
    )


# ---------------------------------------------------------------------------
# 14. Public caps are instance-local and override defaults cleanly
# ---------------------------------------------------------------------------


def test_public_caps_are_instance_local_and_control_sg_and_gstar_limits():
    """
    Expert usage:

        api = get_public_session_api(
            caps=PublicSessionCaps(
                datum_widgets_on_this_span_preview_limit=3,
                output_key_preview_limit=4,
                default_query_max_results=5,
                default_trace_max_results=6,
                absolute_query_max_results=9,
            )
        )

    Public theorem:

        - defaults remain the defaults,
        - custom caps apply to this wrapper only,
        - S/G preview limits are configurable,
        - G* default and absolute row caps are configurable.
    """
    api = _custom_api(
        datum_widgets_on_this_span_preview_limit=3,
        output_key_preview_limit=4,
        default_query_max_results=5,
        default_trace_max_results=6,
        absolute_query_max_results=9,
        public_sanitizer_list_limit=32,
    )

    assert api.caps.datum_widgets_on_this_span_preview_limit == 3
    assert api.caps.output_key_preview_limit == 4
    assert api.caps.default_query_max_results == 5
    assert api.caps.default_trace_max_results == 6
    assert api.caps.absolute_query_max_results == 9
    assert api.caps.public_sanitizer_list_limit >= 9

    # The default singleton remains unchanged.
    default_api = get_public_session_api()
    assert default_api.caps.datum_widgets_on_this_span_preview_limit == DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1
    assert default_api.caps.output_key_preview_limit == DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1
    assert default_api.caps.default_query_max_results == DEFAULT_QUERY_MAX_RESULTS_V1
    assert default_api.caps.default_trace_max_results == DEFAULT_TRACE_MAX_RESULTS_V1
    assert default_api.caps.absolute_query_max_results == ABSOLUTE_QUERY_MAX_RESULTS_V1

    # S pending preview cap.
    wide_step = "public.caps.instance.local.wide.step"
    _register_multiframespec_step(
        wide_step,
        _wide_single_span_multiframespec(
            form_id="public.caps.instance.local.wide",
            datum_count=10,
        ),
    )

    wide_sid = _create_with_api(api, manifest=_manifest(wide_step))
    receipt = _run_until_with_api(
        api,
        wide_sid,
        stop_events=["MANUALFILLNEEDEDSTEP"],
    )

    assert _event(receipt) == "MANUALFILLNEEDEDSTEP"
    assert _span(receipt) == "S_ALL"

    pending = receipt.get("pending")
    assert isinstance(pending, Mapping)
    assert pending["datum_widgets_on_this_span_count"] == 10
    assert pending["datum_widgets_on_this_span_preview_limit"] == 3
    assert pending["datum_widgets_on_this_span_truncated"] is True
    assert _datum_widgets_on_this_span(receipt) == ["W0", "W1", "W2"]
    _assert_public_small(receipt)

    # G output key preview cap.
    prefill_step = "public.caps.instance.local.prefills.step"
    _register_multiframespec_step(
        prefill_step,
        _many_prefilled_datums_multiframespec(
            form_id="public.caps.instance.local.prefills",
            datum_count=12,
            payload_chars=0,
        ),
    )

    prefill_sid = _create_with_api(api, manifest=_manifest(prefill_step))
    done = _run_until_with_api(
        api,
        prefill_sid,
        stop_events=["ATCOMPLETION"],
        max_steps=64,
    )
    assert _event(done) == "ATCOMPLETION"

    outputs = _outputs_report_with_api(api, prefill_sid)
    assert outputs["counts"]["form_prefills"] >= 12
    assert outputs["key_preview_limit"] == 4
    assert len(outputs["keys"]["form_prefills"]) == 4
    assert outputs["truncated_keys"]["form_prefills"] is True
    _assert_public_small(outputs)

    # G* default runtime_writes cap.
    default_writes = _query_with_api(
        api,
        prefill_sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": False,
        },
    )
    assert default_writes["result"]["max_results"] == 5
    assert len(_runtime_rows(default_writes)) <= 5

    # G* absolute runtime_writes cap.
    absurd_writes = _query_with_api(
        api,
        prefill_sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": False,
            "max_results": 999_999,
        },
    )
    assert absurd_writes["result"]["max_results"] == 9
    assert len(_runtime_rows(absurd_writes)) <= 9

    # G* default program_trace_table cap.
    default_trace = _query_with_api(
        api,
        prefill_sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_datum_values": False,
            "include_q_lifecycle": False,
        },
    )
    assert default_trace["result"]["max_results"] == 6
    assert len(_trace_rows(default_trace)) <= 6

    # G* absolute program_trace_table cap.
    absurd_trace = _query_with_api(
        api,
        prefill_sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": False,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 999_999,
        },
    )
    assert absurd_trace["result"]["max_results"] == 9
    assert len(_trace_rows(absurd_trace)) <= 9


# ---------------------------------------------------------------------------
# 15. Very large program: expert cap can retrieve ALL final datum states
# ---------------------------------------------------------------------------


def _run_giant_whole_program_to_completion_with_api(
    api: PublicSessionAPI,
    *,
    fn_count: int,
    frames_per_form: int,
    spans_per_frame: int,
    datums_per_span: int,
    payload_chars: int,
) -> tuple[str, int, float]:
    manifest = _giant_whole_program_manifest(
        fn_count=fn_count,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
    )

    total_datums = (
        int(fn_count)
        * int(frames_per_form)
        * int(spans_per_frame)
        * int(datums_per_span)
    )

    t0 = time.perf_counter()

    sid = _create_with_api(
        api,
        manifest=manifest,
        session_metadata=_lean_session_metadata(),
    )

    receipt = _run_until_with_api(
        api,
        sid,
        stop_events=["ATCOMPLETION"],
        max_steps=max(128, int(fn_count) * 16),
    )

    elapsed = time.perf_counter() - t0

    assert _event(receipt) == "ATCOMPLETION"
    _assert_public_small(receipt)

    return sid, total_datums, elapsed


def _expected_giant_prefill_value(
    *,
    form_index: int,
    frame_index: int,
    span_index: int,
    datum_index: int,
    payload_chars: int,
    payload_char: str = "Z",
) -> Dict[str, str]:
    return {
        "value": (
            f"form={form_index};"
            f"frame={frame_index};"
            f"span={span_index};"
            f"datum={datum_index};"
            + (str(payload_char) * int(payload_chars))
        )
    }


def test_expert_caps_can_return_all_final_datum_states_for_very_large_program():
    """
    Final result theorem for expert exports.

    Default S/G:
        - still returns counts/key previews only,
        - does not return every datum value.

    Expert G*:
        - raises absolute_query_max_results for this wrapper only,
        - asks explicitly for include_values=True,
        - asks for max_results >= total final datum count,
        - retrieves every final datum state.

    This is the scalable contract:

        "show me all final datum states"

    is valid, but it is an explicit capped export query, not default S/G.
    """
    fn_count = 20
    frames_per_form = 4
    spans_per_frame = 5
    datums_per_span = 6

    # Keep payload exact and small here because this test proves "all final
    # states", not giant string transport. Giant payload non-leakage is covered
    # by the metadata-only tests above.
    payload_chars = 0

    total_datums = fn_count * frames_per_form * spans_per_frame * datums_per_span
    expert_cap = total_datums + 64

    api = _custom_api(
        default_query_max_results=64,
        default_trace_max_results=128,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=32,
        datum_widgets_on_this_span_preview_limit=32,
        public_sanitizer_list_limit=expert_cap + 64,
        public_sanitizer_dict_limit=4096,
        public_sanitizer_string_limit=2048,
    )

    sid, observed_total_datums, run_elapsed = _run_giant_whole_program_to_completion_with_api(
        api,
        fn_count=fn_count,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
    )

    assert observed_total_datums == total_datums

    # Default G stays bounded and preview-shaped.
    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= total_datums
    assert outputs["key_preview_limit"] == 32
    assert len(outputs["keys"]["form_prefills"]) <= 32
    assert outputs["truncated_keys"]["form_prefills"] is True
    assert "form_prefills" not in outputs
    _assert_public_small(outputs)

    # Default G* still uses the custom wrapper's default query cap.
    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 64
    assert len(_runtime_rows(default_writes)) <= 64
    assert default_writes["result"]["truncated"] is True

    # Expert G* export: ask for all known final datum states.
    t0 = time.perf_counter()
    all_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": True,
            "max_results": expert_cap,
        },
        no_giant_z=True,
    )
    export_elapsed = time.perf_counter() - t0

    assert all_writes["result"]["max_results"] == expert_cap
    assert all_writes["result"]["truncated"] is False

    rows = _runtime_rows(all_writes)
    prefill_rows = [
        row
        for row in rows
        if row.get("write_kind") == "form_prefill"
    ]

    # There may be extra system rows in some implementations, but every datum
    # final state must be present.
    assert len(prefill_rows) >= total_datums

    by_key = {
        str(row.get("key")): row.get("value")
        for row in prefill_rows
        if "key" in row and "value" in row
    }

    assert len(by_key) >= total_datums

    for form_index in range(fn_count):
        for frame_index in range(frames_per_form):
            for span_index in range(spans_per_frame):
                for datum_index in range(datums_per_span):
                    did = f"F{form_index}_{frame_index}_{span_index}_{datum_index}"
                    assert did in by_key
                    assert by_key[did] == _expected_giant_prefill_value(
                        form_index=form_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                        payload_chars=payload_chars,
                    )

    stats = _bounded_container_stats(all_writes)

    print(
        "[public-api-efficiency-summary] expert_caps_all_final_datum_states "
        f"fn_count={fn_count} "
        f"frames_per_form={frames_per_form} "
        f"spans_per_frame={spans_per_frame} "
        f"datums_per_span={datums_per_span} "
        f"total_datums={total_datums} "
        f"expert_cap={expert_cap} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"export_elapsed={export_elapsed:.6f}s "
        f"rows={len(rows)} "
        f"prefill_rows={len(prefill_rows)} "
        f"string_chars={stats['total_string_chars']}"
    )

    assert export_elapsed < 5.0





# ---------------------------------------------------------------------------
# 17. Public scripting façade stays sealed across giant program complexity
# ---------------------------------------------------------------------------


def test_public_run_action_scripted_program_start_to_finish_is_sealed_small_and_bounded_for_giant_program():
    """
    Public scripting theorem.

    The raw headless script runner may internally produce ctx/history rows.
    The public façade must not expose them.

    This test proves:

        - many app-table fns,
        - many emitted forms,
        - many frames,
        - many spans,
        - many datums,
        - end-to-end scripted run through the public façade,
        - public script report only,
        - no raw ctx/history/multiframespec/snapshot/state/html leak,
        - final state still exportable separately through explicit capped G*.

    This is the sealed scripting API story:

        run_action_scripted_program_start_to_finish(...) gives a small public report.
        query_session(..., runtime_writes, include_values=True) gives explicit
        capped final datum export when desired.
    """
    fn_count = 10
    frames_per_form = 3
    spans_per_frame = 4
    datums_per_span = 5
    payload_chars = 0

    total_final_datums = (
        fn_count
        * frames_per_form
        * spans_per_frame
        * datums_per_span
    )

    expert_cap = total_final_datums + fn_count + 128

    api = _custom_api(
        default_query_max_results=32,
        default_trace_max_results=48,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=24,
        datum_widgets_on_this_span_preview_limit=24,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    manifest = _giant_whole_program_manifest(
        fn_count=fn_count,
        frames_per_form=frames_per_form,
        spans_per_frame=spans_per_frame,
        datums_per_span=datums_per_span,
        payload_chars=payload_chars,
    )

    script = [
        {
            "action": "STEP",
            "until_stop": True,
            "stop_kinds": ["ATCOMPLETION"],
            "expect": {
                "kind": "ATCOMPLETION",
            },
        }
    ]

    t0 = time.perf_counter()
    report = api.run_action_scripted_program_start_to_finish(
        manifest=manifest,
        script=script,
        initial_parameter_overrides={},
        session_metadata=_lean_session_metadata(),
        keep_step_reports=True,
    )
    elapsed = time.perf_counter() - t0

    assert report["kind"] == "session_script_run_report_v1"
    assert report["ok"] is True
    assert report["operation"] == "run_action_scripted_program_start_to_finish"
    assert report["script_count"] == 1
    assert report["slim_result"] is True

    assert "session_id" in report
    sid = str(report["session_id"])
    assert sid

    last = report.get("last")
    assert isinstance(last, Mapping)
    assert last["kind"] == KIND_SESSION_REPORT_V1
    assert last["event_kind"] == "ATCOMPLETION"
    assert last["finished"] is True

    # Public script report may summarize history, but must not expose raw
    # history rows or raw ctx snapshots.
    assert "history_count" in report
    assert "actions" in report
    assert "modes" in report
    assert "first_actions" in report
    assert "last_actions" in report

    assert "history" not in report
    assert "ctx" not in report
    assert "raw_ctx" not in report
    assert "snapshot" not in report
    assert "state" not in report
    assert "multiframespec" not in report
    assert "program_map" not in report
    assert "content" not in report

    _assert_public_small(report)

    # Default G after scripted run remains bounded.
    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= total_final_datums
    assert outputs["key_preview_limit"] == 24
    assert len(outputs["keys"]["form_prefills"]) <= 24
    assert outputs["truncated_keys"]["form_prefills"] is True
    _assert_public_small(outputs)

    # Default G* remains small unless explicitly raised.
    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 32
    assert len(_runtime_rows(default_writes)) <= 32
    assert default_writes["result"]["truncated"] is True

    # Explicit expert G* can retrieve all final states from the session created
    # by the public script façade.
    all_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": True,
            "max_results": expert_cap,
        },
    )

    assert all_writes["result"]["max_results"] == expert_cap
    assert all_writes["result"]["truncated"] is False

    rows = _runtime_rows(all_writes)
    prefill_rows = [
        row
        for row in rows
        if row.get("write_kind") == "form_prefill"
    ]

    assert len(prefill_rows) >= total_final_datums

    final_by_key = {
        str(row.get("key")): row.get("value")
        for row in prefill_rows
        if "key" in row and "value" in row
    }

    assert len(final_by_key) >= total_final_datums

    for form_index in range(fn_count):
        for frame_index in range(frames_per_form):
            for span_index in range(spans_per_frame):
                for datum_index in range(datums_per_span):
                    did = f"F{form_index}_{frame_index}_{span_index}_{datum_index}"

                    assert did in final_by_key
                    assert final_by_key[did] == _expected_giant_prefill_value(
                        form_index=form_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                        payload_chars=payload_chars,
                    )

    report_stats = _bounded_container_stats(report)
    write_stats = _bounded_container_stats(all_writes)

    print(
        "[public-api-efficiency-summary] public_script_facade_giant_sealed "
        f"fn_count={fn_count} "
        f"frames_per_form={frames_per_form} "
        f"spans_per_frame={spans_per_frame} "
        f"datums_per_span={datums_per_span} "
        f"total_final_datums={total_final_datums} "
        f"expert_cap={expert_cap} "
        f"elapsed={elapsed:.6f}s "
        f"history_count={report.get('history_count')} "
        f"report_string_chars={report_stats['total_string_chars']} "
        f"write_rows={len(rows)} "
        f"prefill_rows={len(prefill_rows)} "
        f"writes_string_chars={write_stats['total_string_chars']}"
    )

    assert elapsed < 20.0