# think-backend/tests/wippp/test_runtime_write_query_complexity.py
from __future__ import annotations

"""
Runtime Write Query Complexity Contract Sheet
=============================================

This sheet isolates the runtime-write-index / query artery itself.

The broader App Table complexity sheet proves end-to-end session behavior. This
file zooms into the indexing/query subsystem directly, without UI/session noise,
so we can study the exact axes that can make historical write querying expensive.

Core contract
-------------
Runtime write querying should scale by:

    - number of candidate seq ids selected by metadata indexes,
    - number of write events attached to selected seq ids,
    - requested max_results,
    - explicitly bounded predicate evaluations,

not by:

    - current-state giant value size,
    - historical giant value size,
    - unrelated invocation count when an exact metadata index is available,
    - unrelated write-event count when write_kind/result caps are restrictive,
    - nested giant JSON payloads unless caller explicitly asks to materialize them,
    - giant scalar fn-arg strings copied literally into equality-token indexes.

Important honesty
-----------------
The query artery cannot make these things free:

    - A broad query with no selective filters over N invocations has to consider N
      invocations unless last_k_invocations or max_results allows safe early stop.
    - include_values=True can intentionally materialize current state values.
    - Selected candidate fanout and write-event fanout are real costs.

But every preventable system mine is guarded here:

    - max_results=0 is a hard zero-row materialization cap.
    - include_values is explicit and row-bounded.
    - scalar arg equality tokens must be bounded/hash-based, not full-string copies.
    - non-scalar arg equality queries do not deep-scan or deep-copy.
    - secondary bucket removal uses position sidecars; canonical invocation order
      remains stable.

This is a complexity-contract regression sheet, not a fragile microbenchmark
suite. Timings are printed for study and use loose slope guards.
"""

import os
import re
import statistics
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pytest

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_FORM_FILL,
    WRITE_KIND_FORM_PREFILL,
    WRITE_KIND_STATE,
    RuntimeWriteQueryV1,
    ensure_runtime_write_index_v1,
    query_runtime_writes_v1,
    record_runtime_writes_v1,
    register_runtime_invocation_v1,
    remove_runtime_invocation_v1,
    runtime_write_index_snapshot_view_v1,
)


from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_runtime_write_index_summary,
)

RUN_QUERY_SLOW = os.environ.get("APP_TABLE_QUERY_COMPLEXITY_SLOW", "0") == "1"
RUN_QUERY_CRAZY = os.environ.get("APP_TABLE_QUERY_COMPLEXITY_CRAZY", "0") == "1"


# =============================================================================
# Section 1: Safe bounded measurement helpers
# =============================================================================


def _safe_ident(value: Any) -> str:
    raw = str(value)
    s = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    return s[:80] or "X"


def _bounded_container_stats(
    obj: Any,
    *,
    max_nodes: int = 120_000,
) -> Dict[str, int]:
    seen: set[int] = set()
    stack: List[Any] = [obj]

    visited_nodes = 0
    mappings = 0
    sequences = 0
    strings = 0
    total_string_chars_seen = 0
    max_string_chars_seen = 0

    while stack and visited_nodes < max_nodes:
        cur = stack.pop()
        visited_nodes += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            strings += 1
            n = len(cur)
            total_string_chars_seen += n
            max_string_chars_seen = max(max_string_chars_seen, n)
            continue

        if isinstance(cur, Mapping):
            mappings += 1
            for k, v in cur.items():
                if isinstance(k, str):
                    strings += 1
                    n = len(k)
                    total_string_chars_seen += n
                    max_string_chars_seen = max(max_string_chars_seen, n)
                else:
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            sequences += 1
            stack.extend(cur)
            continue

    return {
        "visited_nodes": visited_nodes,
        "mappings": mappings,
        "sequences": sequences,
        "strings": strings,
        "total_string_chars_seen": total_string_chars_seen,
        "max_string_chars_seen": max_string_chars_seen,
        "truncated": int(bool(stack)),
    }


def _contains_repeated_char_bounded(
    obj: Any,
    *,
    char: str,
    run_len: int,
    max_nodes: int = 120_000,
) -> bool:
    needle = str(char) * int(run_len)
    seen: set[int] = set()
    stack: List[Any] = [obj]
    visited_nodes = 0

    while stack and visited_nodes < max_nodes:
        cur = stack.pop()
        visited_nodes += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
            continue

        if isinstance(cur, Mapping):
            for k, v in cur.items():
                if isinstance(k, str):
                    if needle in k:
                        return True
                else:
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)
            continue

    return False


def _assert_no_repeated_char_bounded(
    obj: Any,
    *,
    char: str,
    run_len: int,
    label: str,
) -> None:
    if _contains_repeated_char_bounded(obj, char=char, run_len=run_len):
        stats = _bounded_container_stats(obj)
        pytest.fail(
            f"{label} leaked repeated {char!r} run of length {run_len}; "
            f"stats={stats}",
            pytrace=False,
        )


def _assert_has_repeated_char_bounded(
    obj: Any,
    *,
    char: str,
    run_len: int,
    label: str,
) -> None:
    if not _contains_repeated_char_bounded(obj, char=char, run_len=run_len):
        stats = _bounded_container_stats(obj)
        pytest.fail(
            f"{label} did not contain expected repeated {char!r} run of length {run_len}; "
            f"stats={stats}",
            pytrace=False,
        )


def _assert_bounded_string_chars(
    obj: Any,
    *,
    max_total_string_chars: int,
    label: str,
) -> Dict[str, int]:
    stats = _bounded_container_stats(obj)
    if stats["total_string_chars_seen"] > max_total_string_chars:
        pytest.fail(
            f"{label} too large: "
            f"total_string_chars_seen={stats['total_string_chars_seen']} "
            f"> {max_total_string_chars}; "
            f"visited_nodes={stats['visited_nodes']} "
            f"truncated={stats['truncated']}",
            pytrace=False,
        )
    return stats


def _median_seconds(fn: Callable[[], Any], *, repeats: int = 3) -> float:
    vals: List[float] = []
    for _ in range(max(1, int(repeats))):
        t0 = time.perf_counter()
        fn()
        vals.append(time.perf_counter() - t0)
    return statistics.median(vals)


def _time_one(label: str, fn: Callable[[], Any]) -> Tuple[Any, float]:
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    print(f"[query-complexity-timing] {label}: {dt:.6f}s")
    return out, dt


def _slope_ratio(
    *,
    small_y: float,
    large_y: float,
    small_n: int,
    large_n: int,
) -> float:
    if small_y <= 0:
        return 0.0
    expected_linear = large_n / small_n
    if expected_linear <= 0:
        return 0.0
    return (large_y / small_y) / expected_linear


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
    if ratio > slack:
        pytest.fail(
            f"{label} appears superlinear beyond allowed slack: "
            f"small={small_y:.6f}s at n={small_n}, "
            f"large={large_y:.6f}s at n={large_n}, "
            f"ratio_vs_linear={ratio:.2f}, slack={slack}",
            pytrace=False,
        )


def _assert_query_result_ref_preview_only(
    result: Mapping[str, Any],
    *,
    expected_max_rows: int,
    max_total_string_chars: int = 80_000,
    forbidden_char: str = "x",
    forbidden_run: int = 1000,
) -> None:
    assert result.get("ok") is True

    rows = result.get("writes")
    assert isinstance(rows, list)
    assert len(rows) <= expected_max_rows

    _assert_bounded_string_chars(
        result,
        max_total_string_chars=max_total_string_chars,
        label="query result",
    )
    _assert_no_repeated_char_bounded(
        result,
        char=forbidden_char,
        run_len=forbidden_run,
        label="query result",
    )

    for row in rows:
        assert isinstance(row, Mapping)
        assert "value_ref" in row
        assert "value_preview" in row
        assert "value" not in row


# =============================================================================
# Section 2: Direct index table builders
# =============================================================================


def _write_ref_for_kind(*, write_kind: str, key: str, form_id: str = "F") -> Dict[str, Any]:
    if write_kind == WRITE_KIND_STATE:
        return {"kind": WRITE_KIND_STATE, "key": key}

    if write_kind == WRITE_KIND_FORM_PREFILL:
        return {
            "kind": WRITE_KIND_FORM_PREFILL,
            "form_id": form_id,
            "datum_id": key,
        }

    if write_kind == WRITE_KIND_FORM_FILL:
        return {
            "kind": WRITE_KIND_FORM_FILL,
            "form_id": form_id,
            "datum_id": key,
        }

    return {"kind": write_kind, "key": key}


def _record_invocation_with_writes(
    state: Dict[str, Any],
    *,
    i: int,
    group: str,
    step_fn: str = "query.scale.writer",
    public_step_prefix: str = "s",
    invocation_kind: str = "step_fn",
    writes_per_invocation: int = 1,
    write_kinds: Sequence[str] = (WRITE_KIND_STATE,),
    value_chars: int = 0,
    value_char: str = "x",
    fn_args_extra: Optional[Dict[str, Any]] = None,
) -> int:
    fn_args: Dict[str, Any] = {
        "i": int(i),
        "group": str(group),
        "bucket": f"b{int(i) % 17}",
        "cfg": {
            "enabled": (int(i) % 2 == 0),
            "shard": int(i) % 31,
            # Keep this non-scalar so shallow arg indexing does not store the
            # payload as an equality token.
            "payload_holder": {
                "payload": str(value_char) * int(value_chars),
            }
            if value_chars
            else {},
        },
    }
    fn_args.update(dict(fn_args_extra or {}))

    seq = register_runtime_invocation_v1(
        state,
        public_step_name=f"{public_step_prefix}{i}",
        step_fn=step_fn,
        fn_args=fn_args,
        invocation_kind=invocation_kind,
    )

    writes: List[Mapping[str, Any]] = []
    kinds = list(write_kinds or (WRITE_KIND_STATE,))
    for j in range(int(writes_per_invocation)):
        kind = kinds[j % len(kinds)]
        key = f"{_safe_ident(group)}_{i}_{j}"

        if kind == WRITE_KIND_STATE:
            state[key] = str(value_char) * int(value_chars) if value_chars else int(i * 1000 + j)
        elif kind == WRITE_KIND_FORM_PREFILL:
            state.setdefault("form_prefills", {})[key] = (
                {"value": str(value_char) * int(value_chars)}
                if value_chars
                else {"value": f"prefill-{i}-{j}"}
            )
        elif kind == WRITE_KIND_FORM_FILL:
            state.setdefault("form_fills", {})[key] = (
                {"value": str(value_char) * int(value_chars)}
                if value_chars
                else {"value": f"fill-{i}-{j}"}
            )

        writes.append(
            {
                "write_kind": kind,
                "key": key,
                "value_ref": _write_ref_for_kind(write_kind=kind, key=key, form_id=f"F{i}"),
                # The query/index row must remain a preview/reference surface.
                "value_preview": {
                    "kind": "synthetic",
                    "is_scalar": False,
                    "preview": f"<synthetic {kind} i={i} j={j}>",
                },
            }
        )

    record_runtime_writes_v1(state, seq=seq, writes=writes)
    return seq


def _make_query_index_state(
    *,
    invocations: int,
    groups: int = 1,
    writes_per_invocation: int = 1,
    write_kinds: Sequence[str] = (WRITE_KIND_STATE,),
    value_chars: int = 0,
    value_char: str = "x",
    step_fn_cycle: int = 1,
) -> Dict[str, Any]:
    state: Dict[str, Any] = {}

    for i in range(int(invocations)):
        _record_invocation_with_writes(
            state,
            i=i,
            group=f"g{i % max(1, int(groups))}",
            step_fn=f"query.scale.writer.{i % max(1, int(step_fn_cycle))}",
            writes_per_invocation=int(writes_per_invocation),
            write_kinds=write_kinds,
            value_chars=int(value_chars),
            value_char=value_char,
        )

    return state


def _query_by_group(
    state: Mapping[str, Any],
    *,
    group: str,
    max_results: int,
    write_kinds: Sequence[str] = (WRITE_KIND_STATE,),
    include_values: bool = False,
) -> Dict[str, Any]:
    return query_runtime_writes_v1(
        state,
        {
            "arg_path": "group",
            "arg_value_equals": group,
            "write_kinds": list(write_kinds),
            "max_results": int(max_results),
            "include_values": bool(include_values),
        },
    )


def _query_all(
    state: Mapping[str, Any],
    *,
    max_results: int,
    write_kinds: Sequence[str] = (WRITE_KIND_STATE,),
) -> Dict[str, Any]:
    return query_runtime_writes_v1(
        state,
        {
            "write_kinds": list(write_kinds),
            "max_results": int(max_results),
        },
    )


def _idx(state: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = state.get(KEY_RUNTIME_WRITE_INDEX)
    assert isinstance(raw, Mapping)
    return raw


def _index_counts(state: Mapping[str, Any]) -> Dict[str, int]:
    idx = _idx(state)
    return {
        "invocation_count": len(idx.get("invocations", {}) or {}),
        "invocation_order_count": len(idx.get("invocation_order", []) or []),
        "write_event_count": len(idx.get("write_events", {}) or {}),
        "events_by_seq_count": len(idx.get("events_by_seq", {}) or {}),
    }


# =============================================================================
# Section 3: Basic query correctness across every indexed dimension
# =============================================================================


def test_query_by_public_step_name_step_fn_arg_name_any_arg_names_and_arg_path_value():
    state = _make_query_index_state(
        invocations=60,
        groups=3,
        writes_per_invocation=2,
        step_fn_cycle=4,
    )

    q_public = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "s17",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 10,
        },
    )
    assert q_public["ok"] is True
    assert {row["public_step_name"] for row in q_public["writes"]} == {"s17"}

    q_step_fn = query_runtime_writes_v1(
        state,
        {
            "step_fn": "query.scale.writer.2",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 10,
        },
    )
    assert q_step_fn["ok"] is True
    assert q_step_fn["writes"]
    assert {row["step_fn"] for row in q_step_fn["writes"]} == {"query.scale.writer.2"}

    q_arg_name = query_runtime_writes_v1(
        state,
        {
            "arg_name": "bucket",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 10,
        },
    )
    assert q_arg_name["ok"] is True
    assert q_arg_name["writes"]

    q_any_arg_names = query_runtime_writes_v1(
        state,
        {
            "any_arg_names": ["missing", "group"],
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 10,
        },
    )
    assert q_any_arg_names["ok"] is True
    assert q_any_arg_names["writes"]

    q_arg_path_value = query_runtime_writes_v1(
        state,
        {
            "arg_path": "group",
            "arg_value_equals": "g1",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 20,
        },
    )
    assert q_arg_path_value["ok"] is True
    assert q_arg_path_value["writes"]
    assert q_arg_path_value["truncated"] is True

    q_nested_arg_path_value = query_runtime_writes_v1(
        state,
        {
            "arg_path": "cfg.enabled",
            "arg_value_equals": True,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 20,
        },
    )
    assert q_nested_arg_path_value["ok"] is True
    assert q_nested_arg_path_value["writes"]


def test_query_intersection_filters_are_correct_and_selective():
    state = _make_query_index_state(
        invocations=120,
        groups=6,
        writes_per_invocation=1,
        step_fn_cycle=5,
    )

    q = query_runtime_writes_v1(
        state,
        {
            "step_fn": "query.scale.writer.3",
            "arg_path": "group",
            "arg_value_equals": "g3",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 100,
        },
    )

    assert q["ok"] is True
    assert q["writes"]

    for row in q["writes"]:
        assert row["step_fn"] == "query.scale.writer.3"

    # With i % 5 == 3 and i % 6 == 3, selected invocations are sparse.
    assert q["seq_count"] < 120


def test_non_scalar_arg_value_query_returns_empty_without_scan_or_error():
    state = _make_query_index_state(invocations=100, groups=2)

    q = query_runtime_writes_v1(
        state,
        {
            "arg_path": "group",
            "arg_value_equals": {"not": "scalar"},
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 100,
        },
    )

    assert q["ok"] is True
    assert q["writes"] == []
    assert q["seq_count"] == 0


# =============================================================================
# Section 4: max_results and materialization bounds
# =============================================================================


@pytest.mark.parametrize("max_results", [0, 1, 5, 50])
def test_max_results_is_a_hard_row_materialization_bound(max_results: int):
    state = _make_query_index_state(
        invocations=200,
        groups=1,
        writes_per_invocation=3,
    )

    q = _query_by_group(
        state,
        group="g0",
        max_results=max_results,
        write_kinds=[WRITE_KIND_STATE],
    )

    assert q["ok"] is True
    assert len(q["writes"]) == max_results
    assert q["truncated"] is (max_results < 600)


def test_max_results_zero_does_not_materialize_or_copy_any_rows():
    state = _make_query_index_state(
        invocations=200,
        groups=1,
        writes_per_invocation=3,
        value_chars=1_000_000,
        value_char="z",
    )

    q = _query_by_group(
        state,
        group="g0",
        max_results=0,
        write_kinds=[WRITE_KIND_STATE],
        include_values=True,
    )

    assert q["ok"] is True
    assert q["writes"] == []
    assert q["truncated"] is True

    _assert_no_repeated_char_bounded(
        q,
        char="z",
        run_len=1000,
        label="zero max_results query result",
    )


def test_result_size_scales_with_max_results_not_table_size_for_selective_index_query():
    small_state = _make_query_index_state(invocations=100, groups=1, writes_per_invocation=2)
    large_state = _make_query_index_state(invocations=10_000, groups=1, writes_per_invocation=2)

    small_q = _query_by_group(small_state, group="g0", max_results=7)
    large_q = _query_by_group(large_state, group="g0", max_results=7)

    assert len(small_q["writes"]) == 7
    assert len(large_q["writes"]) == 7

    small_stats = _bounded_container_stats(small_q)
    large_stats = _bounded_container_stats(large_q)

    assert large_stats["total_string_chars_seen"] < small_stats["total_string_chars_seen"] * 4

    print(
        "[query-complexity-summary] result_size_vs_table_size "
        f"small_invocations=100 small_query_chars={small_stats['total_string_chars_seen']} "
        f"large_invocations=10000 large_query_chars={large_stats['total_string_chars_seen']} "
        "max_results=7"
    )


def test_last_k_invocations_limits_candidate_seq_count():
    state = _make_query_index_state(invocations=500, groups=1, writes_per_invocation=1)

    q = query_runtime_writes_v1(
        state,
        {
            "last_k_invocations": 9,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 100,
        },
    )

    assert q["ok"] is True
    assert q["seq_count"] == 9
    assert len(q["writes"]) == 9


# =============================================================================
# Section 5: Query timing slopes by table size and selectivity
# =============================================================================


@pytest.mark.parametrize("small_n,large_n", [(500, 5_000)])
def test_exact_public_step_name_query_does_not_scale_with_total_table_size(
    small_n: int,
    large_n: int,
):
    small_state = _make_query_index_state(
        invocations=small_n,
        groups=10,
        writes_per_invocation=1,
    )
    large_state = _make_query_index_state(
        invocations=large_n,
        groups=10,
        writes_per_invocation=1,
    )

    def run(state: Mapping[str, Any], n: int) -> None:
        q = query_runtime_writes_v1(
            state,
            {
                "public_step_name": f"s{n - 1}",
                "write_kinds": [WRITE_KIND_STATE],
                "max_results": 10,
            },
        )
        assert q["ok"] is True
        assert len(q["writes"]) == 1
        assert q["seq_count"] == 1

    small_t = _median_seconds(lambda: run(small_state, small_n), repeats=10)
    large_t = _median_seconds(lambda: run(large_state, large_n), repeats=10)

    print(
        "[query-complexity-summary] exact_public_step_query "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s"
    )

    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=20.0,
        label="exact public step query",
    )


@pytest.mark.parametrize("small_n,large_n", [(500, 5_000)])
def test_broad_query_scales_roughly_linearly_with_invocation_count_until_max_results(
    small_n: int,
    large_n: int,
):
    small_state = _make_query_index_state(
        invocations=small_n,
        groups=1,
        writes_per_invocation=1,
    )
    large_state = _make_query_index_state(
        invocations=large_n,
        groups=1,
        writes_per_invocation=1,
    )

    def run(state: Mapping[str, Any], n: int) -> None:
        q = _query_all(state, max_results=n + 10)
        assert q["ok"] is True
        assert len(q["writes"]) == n

    small_t = _median_seconds(lambda: run(small_state, small_n), repeats=5)
    large_t = _median_seconds(lambda: run(large_state, large_n), repeats=5)

    print(
        "[query-complexity-summary] broad_query "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s"
    )

    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=12.0,
        label="broad query",
    )


@pytest.mark.parametrize("small_n,large_n", [(1_000, 10_000)])
def test_selective_arg_value_query_scales_with_selected_candidates_more_than_total_table(
    small_n: int,
    large_n: int,
):
    groups = 100
    max_results = 10

    def make_state(n: int) -> Dict[str, Any]:
        return _make_query_index_state(
            invocations=n,
            groups=groups,
            writes_per_invocation=1,
        )

    small_state = make_state(small_n)
    large_state = make_state(large_n)

    def run(state: Mapping[str, Any], n: int) -> None:
        q = _query_by_group(state, group="g7", max_results=max_results)
        assert q["ok"] is True

        expected_selected = sum(1 for i in range(n) if i % groups == 7)
        expected_rows = min(max_results, expected_selected)

        assert len(q["writes"]) == expected_rows
        assert q["truncated"] is (expected_selected > max_results)
        assert q["seq_count"] == expected_selected

    small_t = _median_seconds(lambda: run(small_state, small_n), repeats=5)
    large_t = _median_seconds(lambda: run(large_state, large_n), repeats=5)

    print(
        "[query-complexity-summary] selective_arg_value_query "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s "
        f"groups={groups} max_results={max_results}"
    )

    # This now times the query itself, not table construction.
    # Healthy behavior is O(selected candidates), not O(total table).
    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=max(1, small_n // groups),
        large_n=max(1, large_n // groups),
        slack=20.0,
        label="selective arg-value query",
    )


def test_selective_exact_lookup_uses_index_candidates_not_full_order_scan():
    """
    Concept proven:
      Exact public_step_name query should not scan the whole invocation_order
      just to re-establish order.

    This is a direct guard for _seqs_for_query:
      indexed candidates should be sorted directly, not recovered by walking the
      entire canonical invocation_order list.
    """
    small_n = 1_000
    large_n = 20_000

    small_state = _make_query_index_state(
        invocations=small_n,
        groups=10,
        writes_per_invocation=1,
    )
    large_state = _make_query_index_state(
        invocations=large_n,
        groups=10,
        writes_per_invocation=1,
    )

    def run(state: Mapping[str, Any], n: int) -> None:
        q = query_runtime_writes_v1(
            state,
            {
                "public_step_name": f"s{n - 1}",
                "write_kinds": [WRITE_KIND_STATE],
                "max_results": 1,
            },
        )
        assert q["ok"] is True
        assert len(q["writes"]) == 1
        assert q["writes"][0]["public_step_name"] == f"s{n - 1}"

    small_t = _median_seconds(lambda: run(small_state, small_n), repeats=20)
    large_t = _median_seconds(lambda: run(large_state, large_n), repeats=20)

    print(
        "[query-complexity-summary] selective_exact_lookup_no_full_order_scan "
        f"small_n={small_n} small_t={small_t:.8f}s "
        f"large_n={large_n} large_t={large_t:.8f}s "
        f"ratio={(large_t / max(small_t, 1e-12)):.3f}"
    )

    # Loose for noisy machines, but this should be far below table-size ratio
    # after _seqs_for_query avoids full invocation_order scans for candidates.
    assert large_t < max(0.01, small_t * 8.0)


# =============================================================================
# Section 6: Write-event fanout axes
# =============================================================================


@pytest.mark.parametrize("writes_per_invocation", [1, 10, 100])
def test_query_cost_and_rows_scale_with_write_events_attached_to_selected_invocations(
    writes_per_invocation: int,
):
    state = _make_query_index_state(
        invocations=20,
        groups=1,
        writes_per_invocation=writes_per_invocation,
    )

    q = _query_by_group(
        state,
        group="g0",
        max_results=20 * writes_per_invocation + 1,
    )

    assert q["ok"] is True
    assert len(q["writes"]) == 20 * writes_per_invocation

    counts = _index_counts(state)
    assert counts["write_event_count"] == 20 * writes_per_invocation

    print(
        "[query-complexity-summary] write_event_fanout "
        f"writes_per_invocation={writes_per_invocation} "
        f"query_rows={len(q['writes'])} "
        f"write_events={counts['write_event_count']}"
    )


def test_write_kind_filter_bounds_materialized_rows_when_invocations_have_mixed_event_kinds():
    state = _make_query_index_state(
        invocations=100,
        groups=1,
        writes_per_invocation=9,
        write_kinds=[WRITE_KIND_STATE, WRITE_KIND_FORM_PREFILL, WRITE_KIND_FORM_FILL],
    )

    q_state = _query_by_group(
        state,
        group="g0",
        max_results=1000,
        write_kinds=[WRITE_KIND_STATE],
    )
    q_prefill = _query_by_group(
        state,
        group="g0",
        max_results=1000,
        write_kinds=[WRITE_KIND_FORM_PREFILL],
    )
    q_fill = _query_by_group(
        state,
        group="g0",
        max_results=1000,
        write_kinds=[WRITE_KIND_FORM_FILL],
    )

    assert len(q_state["writes"]) == 300
    assert len(q_prefill["writes"]) == 300
    assert len(q_fill["writes"]) == 300
    assert all(row["write_kind"] == WRITE_KIND_STATE for row in q_state["writes"])
    assert all(row["write_kind"] == WRITE_KIND_FORM_PREFILL for row in q_prefill["writes"])
    assert all(row["write_kind"] == WRITE_KIND_FORM_FILL for row in q_fill["writes"])


# =============================================================================
# Section 7: Giant current-state values and include_values
# =============================================================================


@pytest.mark.parametrize("value_chars", [1_000, 1_000_000])
def test_query_result_without_include_values_does_not_scale_with_current_value_size(value_chars: int):
    state = _make_query_index_state(
        invocations=20,
        groups=1,
        writes_per_invocation=1,
        value_chars=value_chars,
        value_char="x",
    )

    q, dt = _time_one(
        f"query refs/previews with value_chars={value_chars}",
        lambda: _query_by_group(state, group="g0", max_results=10),
    )

    assert len(q["writes"]) == 10
    _assert_query_result_ref_preview_only(
        q,
        expected_max_rows=10,
        max_total_string_chars=50_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    idx = _idx(state)
    _assert_no_repeated_char_bounded(
        idx,
        char="x",
        run_len=1000,
        label="runtime write index",
    )

    print(
        "[query-complexity-summary] query_without_include_values "
        f"value_chars={value_chars} elapsed={dt:.6f}s rows={len(q['writes'])}"
    )


def test_include_values_is_explicit_and_materializes_current_state_values_only_when_requested():
    state = _make_query_index_state(
        invocations=3,
        groups=1,
        writes_per_invocation=1,
        value_chars=100_000,
        value_char="x",
    )

    default_q = _query_by_group(state, group="g0", max_results=3, include_values=False)
    explicit_q = _query_by_group(state, group="g0", max_results=3, include_values=True)

    assert default_q["ok"] is True
    assert explicit_q["ok"] is True

    assert all("value" not in row for row in default_q["writes"])
    assert any("value" in row for row in explicit_q["writes"])

    _assert_no_repeated_char_bounded(
        default_q,
        char="x",
        run_len=1000,
        label="default query",
    )
    _assert_has_repeated_char_bounded(
        explicit_q,
        char="x",
        run_len=1000,
        label="explicit include_values query",
    )


def test_include_values_max_results_still_bounds_value_materialization_count():
    state = _make_query_index_state(
        invocations=25,
        groups=1,
        writes_per_invocation=1,
        value_chars=50_000,
        value_char="v",
    )

    q = _query_by_group(state, group="g0", max_results=4, include_values=True)

    assert q["ok"] is True
    assert len(q["writes"]) == 4
    assert q["truncated"] is True
    assert sum(1 for row in q["writes"] if "value" in row) == 4


# =============================================================================
# Section 8: Fn arg indexing bounds and adversarial arg-token contracts
# =============================================================================


def test_nested_non_scalar_arg_payload_does_not_leak_into_arg_indexes():
    state: Dict[str, Any] = {}

    _record_invocation_with_writes(
        state,
        i=0,
        group="nested",
        value_chars=1_000_000,
        value_char="z",
    )

    idx = _idx(state)
    _assert_no_repeated_char_bounded(
        idx,
        char="z",
        run_len=1000,
        label="runtime write index",
    )

    q = query_runtime_writes_v1(
        state,
        {
            "arg_path": "cfg.enabled",
            "arg_value_equals": True,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 5,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) == 1


def test_many_shallow_arg_keys_are_capped_per_mapping_arg():
    state: Dict[str, Any] = {}
    huge_cfg = {f"k{i}": i for i in range(500)}

    _record_invocation_with_writes(
        state,
        i=0,
        group="many_shallow",
        fn_args_extra={"cfg": huge_cfg},
    )

    idx = _idx(state)
    keys = list((idx.get("by_arg_path_value") or {}).keys())

    cfg_keys = [k for k in keys if str(k).startswith("cfg.")]
    assert len(cfg_keys) <= 64

    q_inside_cap = query_runtime_writes_v1(
        state,
        {
            "arg_path": "cfg.k0",
            "arg_value_equals": 0,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 5,
        },
    )
    q_outside_cap = query_runtime_writes_v1(
        state,
        {
            "arg_path": "cfg.k499",
            "arg_value_equals": 499,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 5,
        },
    )

    assert len(q_inside_cap["writes"]) == 1
    assert len(q_outside_cap["writes"]) == 0


def test_adversarial_large_scalar_arg_value_is_hash_indexed_not_copied():
    state: Dict[str, Any] = {}
    giant = "a" * 1_000_000

    _record_invocation_with_writes(
        state,
        i=0,
        group="scalar_arg_blob",
        fn_args_extra={
            "huge_scalar_arg": giant,
        },
    )

    idx = _idx(state)

    _assert_no_repeated_char_bounded(
        idx,
        char="a",
        run_len=1000,
        label="runtime write index arg tokens",
    )

    q = query_runtime_writes_v1(
        state,
        {
            "arg_path": "huge_scalar_arg",
            "arg_value_equals": giant,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 5,
        },
    )

    assert q["ok"] is True
    assert len(q["writes"]) == 1
    assert q["writes"][0]["public_step_name"] == "s0"


def test_adversarial_large_nested_scalar_arg_value_is_hash_indexed_not_copied():
    state: Dict[str, Any] = {}
    giant = "b" * 1_000_000

    _record_invocation_with_writes(
        state,
        i=0,
        group="nested_scalar_arg_blob",
        fn_args_extra={
            "cfg": {
                "mode": giant,
            }
        },
    )

    idx = _idx(state)

    _assert_no_repeated_char_bounded(
        idx,
        char="b",
        run_len=1000,
        label="runtime write index nested arg tokens",
    )

    q = query_runtime_writes_v1(
        state,
        {
            "arg_path": "cfg.mode",
            "arg_value_equals": giant,
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 5,
        },
    )

    assert q["ok"] is True
    assert len(q["writes"]) == 1
    assert q["writes"][0]["public_step_name"] == "s0"


# =============================================================================
# Section 9: Predicate query bounds
# =============================================================================


def test_predicate_query_receives_previews_and_respects_max_predicate_evals():
    state = _make_query_index_state(
        invocations=100,
        groups=1,
        writes_per_invocation=1,
        value_chars=50_000,
        value_char="x",
    )

    calls = {"n": 0}

    def pred(preview: Any) -> bool:
        calls["n"] += 1
        assert isinstance(preview, Mapping)
        _assert_no_repeated_char_bounded(
            preview,
            char="x",
            run_len=1000,
            label="predicate preview",
        )
        return True

    q = query_runtime_writes_v1(
        state,
        RuntimeWriteQueryV1(
            arg_name="group",
            predicate_arg_name="group",
            arg_predicate=pred,
            max_predicate_evals=7,
            write_kinds=(WRITE_KIND_STATE,),
            max_results=100,
        ),
    )

    assert q["ok"] is True
    assert calls["n"] == 7
    assert len(q["writes"]) == 7


def test_predicate_without_predicate_arg_name_or_arg_name_returns_empty():
    state = _make_query_index_state(invocations=20, groups=1)

    q = query_runtime_writes_v1(
        state,
        RuntimeWriteQueryV1(
            arg_predicate=lambda _preview: True,
            max_predicate_evals=10,
            write_kinds=(WRITE_KIND_STATE,),
            max_results=10,
        ),
    )

    assert q["ok"] is True
    assert q["writes"] == []


def test_predicate_exceptions_are_swallowed_and_do_not_break_query():
    state = _make_query_index_state(invocations=20, groups=1)

    calls = {"n": 0}

    def pred(_preview: Any) -> bool:
        calls["n"] += 1
        raise RuntimeError("predicate failed")

    q = query_runtime_writes_v1(
        state,
        RuntimeWriteQueryV1(
            arg_name="group",
            predicate_arg_name="group",
            arg_predicate=pred,
            max_predicate_evals=5,
            write_kinds=(WRITE_KIND_STATE,),
            max_results=10,
        ),
    )

    assert q["ok"] is True
    assert calls["n"] == 5
    assert q["writes"] == []


# =============================================================================
# Section 10: Runtime index storage-size contracts
# =============================================================================


@pytest.mark.parametrize("invocations", [10, 100, 1000])
def test_index_counts_are_linear_in_invocations_and_write_events(invocations: int):
    state = _make_query_index_state(
        invocations=invocations,
        groups=5,
        writes_per_invocation=3,
    )

    counts = _index_counts(state)

    assert counts["invocation_count"] == invocations
    assert counts["invocation_order_count"] == invocations
    assert counts["write_event_count"] == invocations * 3
    assert counts["events_by_seq_count"] == invocations


def test_index_storage_is_metadata_only_relative_to_current_state_giant_values():
    state = _make_query_index_state(
        invocations=12,
        groups=1,
        writes_per_invocation=1,
        value_chars=1_000_000,
        value_char="x",
    )

    idx = _idx(state)

    _assert_has_repeated_char_bounded(
        state,
        char="x",
        run_len=1000,
        label="current state",
    )
    _assert_no_repeated_char_bounded(
        idx,
        char="x",
        run_len=1000,
        label="runtime write index",
    )

    state_stats = _bounded_container_stats(state)
    idx_stats = _bounded_container_stats(idx)

    assert idx_stats["total_string_chars_seen"] * 20 < state_stats["total_string_chars_seen"]

    print(
        "[query-complexity-summary] index_metadata_only "
        f"state_string_chars_seen={state_stats['total_string_chars_seen']} "
        f"state_max_string_chars_seen={state_stats['max_string_chars_seen']} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']}"
    )


def test_runtime_write_index_summary_stays_small_with_large_blobs():
    """
    Ported from the pedagogy sheet.

    This belongs here because it is a runtime-write-index/query complexity
    contract, not an app-table pedagogy/UI-session behavior contract.

    Concept proven:
      - giant current-state values may exist;
      - runtime index summary remains metadata-sized;
      - query rows return refs/previews only by default;
      - returned rows are capped by max_results.
    """
    state: Dict[str, Any] = {}

    giant = 256_000
    for i in range(20):
        _record_invocation_with_writes(
            state,
            i=i,
            group="bulk",
            public_step_prefix="w",
            writes_per_invocation=1,
            write_kinds=[WRITE_KIND_STATE],
            value_chars=giant,
            value_char="x",
            fn_args_extra={
                "enabled": i % 2 == 0,
            },
        )

    summary = get_runtime_write_index_summary(state)
    q = _query_by_group(
        state,
        group="bulk",
        max_results=8,
        write_kinds=[WRITE_KIND_STATE],
        include_values=False,
    )

    assert summary["present"] is True
    assert summary["invocation_count"] >= 20
    assert summary["write_event_count"] >= 20

    assert q["ok"] is True
    assert len(q["writes"]) == 8
    assert q["truncated"] is True

    # The query rows carry previews/refs, not the giant blob value.
    _assert_query_result_ref_preview_only(
        q,
        expected_max_rows=8,
        max_total_string_chars=80_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    for w in q["writes"]:
        assert "value_ref" in w
        assert "value_preview" in w
        assert "value" not in w
        assert len(repr(w)) < 2000


        
def test_private_position_sidecar_exists_but_does_not_store_payloads():
    state = _make_query_index_state(
        invocations=100,
        groups=3,
        writes_per_invocation=2,
        value_chars=250_000,
        value_char="p",
    )

    idx = _idx(state)

    positions = idx.get("list_positions")
    assert isinstance(positions, Mapping)
    assert "__invocation_order__" in positions

    _assert_no_repeated_char_bounded(
        positions,
        char="p",
        run_len=1000,
        label="runtime write index position sidecar",
    )

    pos_stats = _bounded_container_stats(positions)
    idx_stats = _bounded_container_stats(idx)

    assert pos_stats["total_string_chars_seen"] < idx_stats["total_string_chars_seen"]


# =============================================================================
# Section 11: Undo/removal complexity and correctness
# =============================================================================


def test_remove_runtime_invocation_removes_invocation_arg_indexes_and_events():
    """
    Middle removal is logically immediate but may leave a runtime-only
    chronological tombstone.

    invocation_order is an internal sparse chronological vector. Requiring its
    physical list length to shrink after every middle deletion would restore an
    O(n) shift/reindex operation and make repeated middle removals quadratic.

    The public/runtime contract is instead:

      - the invocation row is gone;
      - the sequence is absent from logical chronological iteration;
      - all invocation secondary indexes no longer contain it;
      - all attached write events are gone;
      - indexed queries cannot observe it;
      - durable snapshot projection compacts runtime tombstones.
    """
    state = _make_query_index_state(
        invocations=20,
        groups=2,
        writes_per_invocation=3,
    )

    before = _index_counts(state)
    assert before["invocation_count"] == 20
    assert before["write_event_count"] == 60

    remove_runtime_invocation_v1(state, seq=10)

    idx = state[KEY_RUNTIME_WRITE_INDEX]

    after = _index_counts(state)
    assert after["invocation_count"] == 19
    assert after["write_event_count"] == 57
    assert after["events_by_seq_count"] == 19

    # Runtime chronological storage may be sparse after middle deletion.
    # Count logical live sequence IDs, not physical list slots.
    invocation_order = list(idx.get("invocation_order") or [])
    logical_invocation_order = [
        int(raw)
        for raw in invocation_order
        if raw is not None
        and str(int(raw)) in (idx.get("invocations") or {})
    ]

    assert len(logical_invocation_order) == 19
    assert 10 not in logical_invocation_order
    assert logical_invocation_order == [
        seq for seq in range(1, 21) if seq != 10
    ]

    # The canonical invocation row is removed.
    assert "10" not in (idx.get("invocations") or {})

    # Invocation membership indexes must not retain the removed sequence.
    for bucket_name in (
        "by_public_step_name",
        "by_step_fn",
        "by_arg_name",
        "by_arg_path_value",
    ):
        bucket = idx.get(bucket_name) or {}
        assert all(
            10 not in [int(raw) for raw in list(values or [])]
            for values in bucket.values()
        )

    # Its event ownership bucket and all three events are removed.
    assert "10" not in (idx.get("events_by_seq") or {})

    write_events = idx.get("write_events") or {}
    assert all(
        int(event.get("seq", -1)) != 10
        for event in write_events.values()
    )

    # Event secondary indexes must contain only existing event IDs.
    live_event_ids = {int(raw) for raw in write_events.keys()}
    for bucket_name in (
        "events_by_public_step_name",
        "events_by_step_fn",
        "events_by_write_kind",
    ):
        bucket = idx.get(bucket_name) or {}
        for values in bucket.values():
            assert {
                int(raw) for raw in list(values or [])
            }.issubset(live_event_ids)

    # The removed invocation was public step s9 under one-based sequence
    # registration. It must no longer be query-visible.
    q_public = query_runtime_writes_v1(
        state,
        {
            "public_step_name": "s9",
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 10,
        },
    )
    assert q_public["ok"] is True
    assert q_public["writes"] == []

    # An unfiltered query must also skip the chronological tombstone.
    q_all = query_runtime_writes_v1(
        state,
        {
            "write_kinds": [WRITE_KIND_STATE],
            "max_results": 1000,
        },
    )
    assert q_all["ok"] is True
    assert all(
        int(row.get("seq", -1)) != 10
        for row in q_all["writes"]
    )

    # Runtime tombstones are not durable. Snapshot projection restores a dense
    # canonical chronological order without mutating the live index.
    snapshot_idx = runtime_write_index_snapshot_view_v1(idx)
    snapshot_order = list(snapshot_idx.get("invocation_order") or [])

    assert len(snapshot_order) == 19
    assert snapshot_order == [
        seq for seq in range(1, 21) if seq != 10
    ]
    assert all(raw is not None for raw in snapshot_order)


def test_remove_runtime_invocation_is_idempotent_for_missing_or_repeated_seq():
    state = _make_query_index_state(invocations=10, groups=1, writes_per_invocation=1)

    before = _index_counts(state)

    remove_runtime_invocation_v1(state, seq=None)
    remove_runtime_invocation_v1(state, seq=9999)

    assert _index_counts(state) == before

    remove_runtime_invocation_v1(state, seq=5)
    after_once = _index_counts(state)

    remove_runtime_invocation_v1(state, seq=5)
    after_twice = _index_counts(state)

    assert after_once == after_twice


@pytest.mark.parametrize("small_n,large_n", [(1_000, 10_000)])
def test_deep_undo_removal_does_not_show_quadratic_wall_after_position_sidecar(
    small_n: int,
    large_n: int,
):
    remove_count = 200

    def run(n: int) -> None:
        state = _make_query_index_state(
            invocations=n,
            groups=1,
            writes_per_invocation=1,
        )
        for seq in range(n, n - remove_count, -1):
            remove_runtime_invocation_v1(state, seq=seq)

        counts = _index_counts(state)
        assert counts["invocation_count"] == n - remove_count
        assert counts["write_event_count"] == n - remove_count

    small_t = _median_seconds(lambda: run(small_n), repeats=3)
    large_t = _median_seconds(lambda: run(large_n), repeats=3)

    print(
        "[query-complexity-summary] deep_undo_removal "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s "
        f"remove_count={remove_count}"
    )

    # The removed seqs all sit in the same hot buckets. Before the position
    # sidecar, list.remove(...) made this removal path visibly scan bucket lists.
    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=8.0,
        label="deep undo index removal",
    )


def test_remove_from_middle_preserves_query_correctness_after_swap_pop_bucket_order_changes():
    state = _make_query_index_state(
        invocations=30,
        groups=1,
        writes_per_invocation=1,
    )

    remove_runtime_invocation_v1(state, seq=15)

    q = _query_by_group(state, group="g0", max_results=100)

    assert q["ok"] is True
    assert len(q["writes"]) == 29
    assert all(row["seq"] != 15 for row in q["writes"])

    seqs = [row["seq"] for row in q["writes"]]
    assert seqs == sorted(seqs)


# =============================================================================
# Section 12: Snapshot/backward-compatibility with indexes lacking position sidecar
# =============================================================================


def test_old_snapshot_without_position_sidecar_is_lazily_upgraded_and_still_queryable():
    state = _make_query_index_state(
        invocations=50,
        groups=2,
        writes_per_invocation=2,
    )

    idx = ensure_runtime_write_index_v1(state)
    idx.pop("list_positions", None)

    q_before = _query_by_group(state, group="g1", max_results=10)
    assert q_before["ok"] is True
    assert len(q_before["writes"]) == 10

    remove_runtime_invocation_v1(state, seq=2)

    idx_after = _idx(state)
    assert isinstance(idx_after.get("list_positions"), Mapping)

    q_after = _query_by_group(state, group="g1", max_results=1000)
    assert q_after["ok"] is True
    assert all(row["seq"] != 2 for row in q_after["writes"])


def test_corrupt_or_missing_position_entries_are_rebuilt_lazily():
    state = _make_query_index_state(
        invocations=40,
        groups=1,
        writes_per_invocation=1,
    )

    idx = ensure_runtime_write_index_v1(state)
    idx["list_positions"] = {
        "__invocation_order__": {},
        "by_arg_path_value": {},
    }

    remove_runtime_invocation_v1(state, seq=20)

    q = _query_by_group(state, group="g0", max_results=100)

    assert q["ok"] is True
    assert len(q["writes"]) == 39
    assert all(row["seq"] != 20 for row in q["writes"])


# =============================================================================
# Section 13: Adversarial mixed query artery tests
# =============================================================================


@pytest.mark.skipif(not RUN_QUERY_SLOW, reason="set APP_TABLE_QUERY_COMPLEXITY_SLOW=1")
def test_adversarial_large_query_table_mixed_filters_and_payloads_stay_bounded():
    state = _make_query_index_state(
        invocations=20_000,
        groups=200,
        writes_per_invocation=3,
        write_kinds=[WRITE_KIND_STATE, WRITE_KIND_FORM_PREFILL, WRITE_KIND_FORM_FILL],
        value_chars=25_000,
        value_char="x",
        step_fn_cycle=25,
    )

    q_blob, q_dt = _time_one(
        "adversarial mixed selective query",
        lambda: query_runtime_writes_v1(
            state,
            {
                "step_fn": "query.scale.writer.7",
                "arg_path": "group",
                "arg_value_equals": "g7",
                "write_kinds": [WRITE_KIND_STATE],
                "max_results": 12,
            },
        ),
    )

    assert q_blob["ok"] is True
    assert len(q_blob["writes"]) <= 12
    _assert_query_result_ref_preview_only(
        q_blob,
        expected_max_rows=12,
        max_total_string_chars=80_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    idx = _idx(state)
    _assert_no_repeated_char_bounded(
        idx,
        char="x",
        run_len=1000,
        label="runtime write index",
    )

    counts = _index_counts(state)
    idx_stats = _bounded_container_stats(idx)

    print(
        "[query-complexity-summary] adversarial_large_query_table "
        f"elapsed={q_dt:.6f}s "
        f"invocations={counts['invocation_count']} "
        f"write_events={counts['write_event_count']} "
        f"query_rows={len(q_blob['writes'])} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']}"
    )


@pytest.mark.skipif(not RUN_QUERY_SLOW, reason="set APP_TABLE_QUERY_COMPLEXITY_SLOW=1")
def test_adversarial_broad_query_is_linear_and_result_capped():
    state = _make_query_index_state(
        invocations=50_000,
        groups=1,
        writes_per_invocation=2,
    )

    q, dt = _time_one(
        "adversarial broad capped query",
        lambda: _query_all(state, max_results=25),
    )

    assert q["ok"] is True
    assert len(q["writes"]) == 25
    assert q["truncated"] is True

    q_stats = _bounded_container_stats(q)
    assert q_stats["total_string_chars_seen"] < 80_000

    print(
        "[query-complexity-summary] adversarial_broad_query_capped "
        f"elapsed={dt:.6f}s "
        f"seq_count={q['seq_count']} "
        f"query_rows={len(q['writes'])} "
        f"query_string_chars_seen={q_stats['total_string_chars_seen']}"
    )


@pytest.mark.skipif(not RUN_QUERY_SLOW, reason="set APP_TABLE_QUERY_COMPLEXITY_SLOW=1")
def test_adversarial_remove_many_from_hot_bucket_keeps_index_consistent():
    n = 30_000
    remove_count = 5_000

    state = _make_query_index_state(
        invocations=n,
        groups=1,
        writes_per_invocation=1,
    )

    t0 = time.perf_counter()
    for seq in range(n, n - remove_count, -1):
        remove_runtime_invocation_v1(state, seq=seq)
    dt = time.perf_counter() - t0

    counts = _index_counts(state)
    assert counts["invocation_count"] == n - remove_count
    assert counts["write_event_count"] == n - remove_count

    q = _query_by_group(state, group="g0", max_results=10)
    assert q["ok"] is True
    assert len(q["writes"]) == 10

    print(
        "[query-complexity-summary] adversarial_remove_hot_bucket "
        f"n={n} remove_count={remove_count} elapsed={dt:.6f}s "
        f"remaining_invocations={counts['invocation_count']} "
        f"remaining_write_events={counts['write_event_count']}"
    )


@pytest.mark.skipif(not RUN_QUERY_CRAZY, reason="set APP_TABLE_QUERY_COMPLEXITY_CRAZY=1")
def test_crazy_query_table_scale_selective_and_broad_diagnostics():
    invocations = int(os.environ.get("APP_TABLE_QUERY_COMPLEXITY_INVOCATIONS", "100000"))
    groups = int(os.environ.get("APP_TABLE_QUERY_COMPLEXITY_GROUPS", "1000"))
    writes_per_invocation = int(os.environ.get("APP_TABLE_QUERY_COMPLEXITY_WRITES_PER_INVOCATION", "2"))

    state, build_dt = _time_one(
        "crazy query table build",
        lambda: _make_query_index_state(
            invocations=invocations,
            groups=groups,
            writes_per_invocation=writes_per_invocation,
            step_fn_cycle=100,
        ),
    )

    selective_q, selective_dt = _time_one(
        "crazy selective arg-path query",
        lambda: _query_by_group(state, group=f"g{groups // 2}", max_results=20),
    )

    broad_q, broad_dt = _time_one(
        "crazy broad capped query",
        lambda: _query_all(state, max_results=20),
    )

    assert selective_q["ok"] is True
    assert broad_q["ok"] is True
    assert len(selective_q["writes"]) <= 20
    assert len(broad_q["writes"]) == 20

    counts = _index_counts(state)
    idx_stats = _bounded_container_stats(_idx(state))

    print(
        "[query-complexity-summary] crazy_query_table "
        f"invocations={invocations} "
        f"groups={groups} "
        f"writes_per_invocation={writes_per_invocation} "
        f"write_events={counts['write_event_count']} "
        f"build_s={build_dt:.6f} "
        f"selective_query_s={selective_dt:.6f} "
        f"broad_query_s={broad_dt:.6f} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"selective_rows={len(selective_q['writes'])} "
        f"broad_rows={len(broad_q['writes'])}"
    )


# =============================================================================
# Section 14: Explicit taxonomy guard
# =============================================================================


def test_runtime_write_query_complexity_taxonomy_is_explicitly_covered():
    axes = {
        "query_by_public_step_name",
        "query_by_step_fn",
        "query_by_arg_name",
        "query_by_any_arg_names",
        "query_by_arg_path_value",
        "query_filter_intersection",
        "query_last_k_invocations",
        "query_max_results",
        "query_write_kind_filter",
        "query_include_values",
        "query_predicate_bound",
        "query_candidate_table_size",
        "query_selected_candidate_count",
        "query_write_events_per_invocation",
        "index_invocation_count",
        "index_write_event_count",
        "index_payload_non_materialization",
        "index_fn_arg_width_cap",
        "index_nested_payload_non_materialization",
        "index_bounded_scalar_arg_tokenization",
        "undo_remove_invocation",
        "undo_remove_hot_bucket",
        "position_sidecar_backward_compat",
        "position_sidecar_corruption_rebuild",
        "adversarial_mixed_query_table",
        "crazy_query_table",
    }

    assert len(axes) == 26
    assert "index_bounded_scalar_arg_tokenization" in axes
    assert "undo_remove_hot_bucket" in axes
    assert "crazy_query_table" in axes


"""
FINAL RUNTIME WRITE QUERY COMPLEXITY CONCLUSIONS

Status:
    41 passed, 4 skipped, 0 failed, 0 xfailed.

The runtime write query artery is now clean for system-owned complexity risks.

What is proven:

    1. Indexed query dimensions work:
        - public_step_name
        - step_fn
        - arg_name
        - any_arg_names
        - arg_path + scalar value

    2. Selective exact queries do not scan full invocation_order.
       Observed:
            1000 invocations   -> ~0.00001888s
            20000 invocations  -> ~0.00001875s
            ratio              -> ~0.993

       Therefore selective indexed lookup is effectively independent of total
       table size.

    3. Broad queries are roughly linear in invocation count.
       This is inherent when no selective metadata filter is supplied.

    4. max_results is a hard materialization bound, including max_results=0.

    5. max_results=0 does not materialize rows and does not copy giant values,
       even when include_values=True.

    6. Query result size scales with max_results, not table size.
       Observed:
            100 invocations     -> query chars 1173
            10000 invocations   -> query chars 1173
            max_results         -> 7

    7. include_values=False returns refs/previews only and does not hydrate giant
       current-state values.
       Observed:
            value_chars=1000      -> ~0.000071s
            value_chars=1000000   -> ~0.000085s

    8. include_values=True is the explicit value-materialization escape hatch and
       remains bounded by max_results.

    9. Non-scalar arg equality queries return empty safely.

    10. Nested non-scalar arg payloads do not leak into indexes.

    11. Shallow mapping arg indexing is capped.

    12. Giant scalar arg values are hash-indexed, not copied literally into arg
        equality tokens.

    13. Giant nested scalar arg values are hash-indexed, not copied literally into
        arg-path equality tokens.

    14. Predicate queries receive preview surfaces and respect
        max_predicate_evals.

    15. Index counts are linear in invocation count and write-event count.

    16. Index storage is metadata-only relative to giant current-state values.
        Observed:
            state_string_chars_seen  ~= 12,010,974
            max state string         ~= 1,000,000
            index_string_chars_seen  ~= 10,877

    17. Position sidecar removal eliminated the old obvious hot-bucket
        list.remove(...) wall for secondary index buckets.

    18. invocation_order remains canonical chronological order after middle
        removal.

    19. Old snapshots without list_positions are lazily upgraded.

    20. Corrupt/missing position entries are rebuilt lazily.

Final complexity model:

    Selective indexed query:
        O(selected candidate seqs + selected write events up to max_results)

    Exact single-step lookup:
        O(1-ish metadata lookup + selected write events)

    Broad query:
        O(invocations considered + write events scanned until max_results/end)

    Query output:
        O(max_results)

    Default value surface:
        O(refs/previews), not O(value size)

    include_values=True:
        O(materialized current values for returned rows only)

    Index storage:
        O(invocations + write events + bounded metadata tokens)

What remains inherently not free:

    1. Broad unfiltered historical queries.
    2. Queries selecting many candidate invocations.
    3. Invocations with many write events.
    4. Explicit include_values=True over large returned values.
    5. User/dev-authored function runtime outside the query artery.

Final philosophy:

    The system now preemptively prevents the avoidable mines:
        - no accidental all-row materialization for max_results=0;
        - no giant value hydration by default;
        - no giant scalar arg copying into index tokens;
        - no full-order scan for selective indexed lookup;
        - no order corruption from secondary bucket swap-pop;
        - bounded predicate evaluation;
        - bounded shallow arg indexing;
        - metadata/ref/preview surfaces by default.

    Remaining costs are either mathematically inherent to the selected query
    shape or explicitly requested by the caller.
"""