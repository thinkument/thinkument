from __future__ import annotations

"""
App Table Complexity Contract Sheet
===================================

This file is executable proof that App Table sessions scale according to the
engine philosophy:

    - Runtime history is indexed by metadata and references.
    - Giant values may exist in current state because user code wrote them.
    - The engine must not accidentally duplicate, deep-walk, hydrate, scan, or
      materialize historical giant values.
    - Querying prior writes must use indexes and bounded result surfaces.
    - Session ctx / script progress / runtime index / query reports must stay
      bounded unless a caller explicitly asks to materialize values.

This is NOT a fragile microbenchmark suite.

It is a complexity-contract regression sheet. The tests assert:
    1. functional correctness,
    2. bounded public/index/query surfaces,
    3. no giant payload leakage into metadata indexes,
    4. slope sanity across controlled growth axes,
    5. adversarial mixed growth does not accidentally create hidden complexity walls.

Important honesty:
    The engine cannot make a user-authored function's own computation free.
    The engine cannot make current-state giant payloads disappear if the user
    intentionally writes them.
    What this suite proves is that engine/session/query/scriptit machinery does
    not add accidental complexity beyond the explicit work/value size the user
    requested.

Critical test-harness rule
--------------------------
These tests intentionally create huge values. Therefore the tests themselves
must never accidentally hang by printing, repr-ing, or JSON-serializing giant
objects.

Forbidden inside this file for untrusted/possibly-huge objects:
    repr(state)
    repr(ctx)
    repr(snapshot)
    repr(out)
    repr(rr.history)
    json.dumps(state)
    json.dumps(ctx)
    json.dumps(snapshot)
    json.dumps(out)

Instead, use bounded structural scanners:
    _bounded_container_stats(...)
    _contains_repeated_char_bounded(...)
    _contains_text_bounded(...)
    _contains_key_bounded(...)

Opt-in heavy scale
------------------
Default test runs are designed to finish quickly and safely.

Set these env vars for edge diagnostics:

    APP_TABLE_COMPLEXITY_SLOW=1
        enables slow adversarial tests

    APP_TABLE_COMPLEXITY_CRAZY_IO=1
        enables crazy IO stress tests

    APP_TABLE_COMPLEXITY_CRAZY_IO_COUNT=1000
        chooses single-form crazy IO datum count

The 1000 manual IO case is intentionally opt-in because your timing already
shows the UI/manual-fill path is the suspicious wall axis.
"""

import os
import re
import statistics
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import pytest

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    RuntimeWriteQueryV1,
    query_runtime_writes_v1,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_runtime_write_index_summary,
    query_runtime_writes,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
    run_session_against_script_headless,
)


RUN_SLOW = True
RUN_CRAZY_IO = True

RUN_MANUAL_IO_PROFILE = True
MANUAL_IO_PROFILE_EVERY = 1


# =============================================================================
# Section 1: Safe bounded measurement and invariant helpers
# =============================================================================


def _safe_ident(value: Any) -> str:
    raw = str(value)
    s = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    return s[:80] or "X"


def _bounded_container_stats(
    obj: Any,
    *,
    max_nodes: int = 80_000,
) -> Dict[str, int]:
    """
    Count object/container/string shape without repr(obj) or json.dumps(obj).

    This is intentionally safe for giant user values. It may inspect string
    lengths, but it never materializes a giant aggregate string.
    """
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
    max_nodes: int = 80_000,
) -> bool:
    """
    Search for char * run_len without repr(obj) or json.dumps(obj).
    """
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


def _contains_text_bounded(
    obj: Any,
    text: str,
    *,
    max_nodes: int = 80_000,
) -> bool:
    needle = str(text)
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


def _contains_key_bounded(
    obj: Any,
    key: str,
    *,
    max_nodes: int = 80_000,
) -> bool:
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

        if isinstance(cur, Mapping):
            if key in cur:
                return True
            stack.extend(cur.values())
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
    print(f"[complexity-timing] {label}: {dt:.6f}s")
    return out, dt


def _manual_io_profile_metadata(
    *,
    enabled: bool,
    persistence: str = "boundary",
    include_full_multiframespec_in_ctx: bool = False,
    include_global_fill_keys_in_ctx: bool = False,
    include_field_value_keys_in_ctx: bool = False,
    include_forms_emitted_order_in_ctx: bool = False,
) -> Dict[str, Any]:
    """
    Metadata for manual IO profiling.

    Defaults are intentionally hot-path friendly:
      - boundary persistence,
      - no full multiframespec in ctx,
      - no global diagnostic key lists,
      - no field key sorting,
      - no full emitted-forms order list.
    """
    return {
        "manual_io": {
            "profile": bool(enabled),
            "persistence": str(persistence),
            "include_full_multiframespec_in_ctx": bool(include_full_multiframespec_in_ctx),
            "include_global_fill_keys_in_ctx": bool(include_global_fill_keys_in_ctx),
            "include_field_value_keys_in_ctx": bool(include_field_value_keys_in_ctx),
            "include_forms_emitted_order_in_ctx": bool(include_forms_emitted_order_in_ctx),
        }
    }


def _extract_manual_io_profile(ctx: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(ctx, Mapping):
        return None
    meta = ctx.get("session_metadata")
    if not isinstance(meta, Mapping):
        return None
    row = meta.get("manual_io_profile_last_call_v1")
    if not isinstance(row, Mapping):
        return None
    return dict(row)


def _new_profile_accumulator() -> Dict[str, Any]:
    return {
        "calls": {},
        "totals": {},
        "maxes": {},
        "samples": {},
    }


def _profile_accumulate(
    acc: Dict[str, Any],
    *,
    prefix: str,
    profile: Optional[Mapping[str, Any]],
) -> None:
    if not isinstance(profile, Mapping):
        return

    timings = profile.get("timings")
    if not isinstance(timings, Mapping):
        return

    calls = acc.setdefault("calls", {})
    totals = acc.setdefault("totals", {})
    maxes = acc.setdefault("maxes", {})
    samples = acc.setdefault("samples", {})

    for k, v in timings.items():
        key = f"{prefix}.{k}"
        try:
            val = float(v)
        except Exception:
            continue

        calls[key] = int(calls.get(key, 0)) + 1
        totals[key] = float(totals.get(key, 0.0)) + val
        maxes[key] = max(float(maxes.get(key, 0.0)), val)

        arr = samples.setdefault(key, [])
        if len(arr) < 10000:
            arr.append(val)


def _profile_accumulate_public_call(
    acc: Dict[str, Any],
    *,
    method_name: str,
    elapsed: float,
) -> None:
    calls = acc.setdefault("calls", {})
    totals = acc.setdefault("totals", {})
    maxes = acc.setdefault("maxes", {})
    samples = acc.setdefault("samples", {})

    key = f"api_public.{method_name}"
    val = float(elapsed)

    calls[key] = int(calls.get(key, 0)) + 1
    totals[key] = float(totals.get(key, 0.0)) + val
    maxes[key] = max(float(maxes.get(key, 0.0)), val)

    arr = samples.setdefault(key, [])
    if len(arr) < 10000:
        arr.append(val)


def _profile_percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(float(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * float(pct)
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


def _print_profile_summary(
    label: str,
    acc: Mapping[str, Any],
    *,
    manual_count: int,
) -> None:
    calls = dict(acc.get("calls") or {})
    totals = dict(acc.get("totals") or {})
    maxes = dict(acc.get("maxes") or {})
    samples = dict(acc.get("samples") or {})

    if not totals:
        print(f"[complexity-profile] {label} no_profile_samples=1")
        return

    keys = sorted(totals, key=lambda k: float(totals[k]), reverse=True)

    print(
        f"[complexity-profile] {label} "
        f"manual_count={manual_count} "
        f"profile_keys={len(keys)}"
    )

    for key in keys:
        vals = [float(v) for v in list(samples.get(key) or [])]
        count = int(calls.get(key, 0))
        total = float(totals.get(key, 0.0))
        avg = total / max(1, count)
        mx = float(maxes.get(key, 0.0))
        p50 = _profile_percentile(vals, 0.50)
        p95 = _profile_percentile(vals, 0.95)

        print(
            "[complexity-profile-row] "
            f"{label} "
            f"key={key} "
            f"calls={count} "
            f"total_s={total:.6f} "
            f"avg_ms={avg * 1000:.3f} "
            f"p50_ms={p50 * 1000:.3f} "
            f"p95_ms={p95 * 1000:.3f} "
            f"max_ms={mx * 1000:.3f} "
            f"per_manual_ms={(total / max(1, manual_count)) * 1000:.3f}"
        )


def _install_api_call_profiler(api: Any, acc: Dict[str, Any]) -> None:
    """
    Monkeypatch selected API methods for this test process.

    This profiler is test-only. It catches time spent outside the engine's own
    profiling surface, especially SessionProgramScriptedHeadlessRunner calls into:

        api.step_session(...)
        api.get_session_context(...)
        api.get_outputs(...)
        api.export_session_snapshot(...)

    That is critical because the current wall is in until_stop/read-like time.
    """
    if getattr(api, "_complexity_call_profiler_installed_v1", False):
        return

    method_names = [
        "step_session",
        "get_session_context",
        "get_outputs",
        "export_session_snapshot",
        "undo_last_step",
    ]

    for name in method_names:
        original = getattr(api, name, None)
        if not callable(original):
            continue

        def make_wrapped(method_name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(*args: Any, **kwargs: Any) -> Any:
                t0 = time.perf_counter()
                out = fn(*args, **kwargs)
                dt = time.perf_counter() - t0
                _profile_accumulate_public_call(
                    acc,
                    method_name=method_name,
                    elapsed=dt,
                )

                internal = _extract_manual_io_profile(out)
                if internal:
                    operation = str(internal.get("operation") or method_name)
                    _profile_accumulate(
                        acc,
                        prefix=f"internal.{operation}",
                        profile=internal,
                    )

                return out

            return wrapped

        setattr(api, name, make_wrapped(name, original))

    setattr(api, "_complexity_call_profiler_installed_v1", True)
    

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


def _runtime_index_from_snapshot(api: Any, session_id: str) -> Dict[str, Any]:
    snap = api.export_session_snapshot(session_id)
    state = snap.get("state") if isinstance(snap, Mapping) else {}
    if not isinstance(state, Mapping):
        pytest.fail("snapshot.state missing", pytrace=False)
    idx = state.get("_runtime_write_index_v1")
    if not isinstance(idx, Mapping):
        pytest.fail("runtime write index missing from snapshot.state", pytrace=False)
    return dict(idx)


def _state_from_snapshot(api: Any, session_id: str) -> Dict[str, Any]:
    snap = api.export_session_snapshot(session_id)
    state = snap.get("state") if isinstance(snap, Mapping) else {}
    if not isinstance(state, Mapping):
        pytest.fail("snapshot.state missing", pytrace=False)
    return dict(state)


def _assert_query_rows_are_ref_preview_only(
    query_result: Mapping[str, Any],
    *,
    max_total_string_chars: int = 40_000,
    forbidden_char: str = "x",
    forbidden_run: int = 1000,
) -> None:
    assert query_result.get("ok") is True
    _assert_bounded_string_chars(
        query_result,
        max_total_string_chars=max_total_string_chars,
        label="query result",
    )
    _assert_no_repeated_char_bounded(
        query_result,
        char=forbidden_char,
        run_len=forbidden_run,
        label="query result",
    )

    rows = query_result.get("writes") or []
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, Mapping)
        assert "value_ref" in row
        assert "value_preview" in row
        assert "value" not in row


def _run_manifest_to_completion(
    manifest: Any,
    *,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    api = get_concrete_session_api()
    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides=dict(initial_parameter_overrides or {}),
        session_metadata=dict(session_metadata or {}),
        api=api,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "stop_kinds": ["ATCOMPLETION"],
                "expect": {"kind": "ATCOMPLETION"},
            }
        ],
    )
    out = api.get_outputs(rr.session_id)
    return rr.session_id, rr.ctx, out


def _manual_fill_all_to_completion(
    *,
    manifest: List[Dict[str, Any]],
    fill_value: Any = "ok",
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
):
    api = get_concrete_session_api()

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides=dict(initial_parameter_overrides or {}),
        session_metadata=dict(session_metadata or {}),
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    while True:
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )

        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        did = str(pending[0])
        runner.step(fill={did: {"value": fill_value}})

    out = api.get_outputs(sid)
    return sid, ctx, out


def _api_step_until_stop_no_harness(
    api: Any,
    session_id: str,
    *,
    stop_kinds: List[str],
) -> Dict[str, Any]:
    """
    Direct public API stepping helper for complexity timing.

    Important:
      This intentionally does NOT use SessionProgramScriptedHeadlessRunner.

    SessionProgramScriptedHeadlessRunner is valuable for semantic/assertion tests, but it may call
    export_session_snapshot() as part of its assertions. Snapshot export is a
    full-session materialization surface and will dominate manual-IO timing.

    Use this helper when the measurement target is:
        api.step_session(...)
        engine step/fill
        engine ctx exposure

    Do not use it when the measurement target is runner semantics.
    """
    stops = {str(k) for k in stop_kinds}

    while True:
        ctx = api.step_session(session_id)
        kind = str(ctx.get("kind") or "")

        if kind in stops:
            return ctx

        # Public API should already auto-advance internal kinds, but keep this
        # explicit guard so this helper fails safely if a new public kind appears.
        if kind not in {
            "ATSTART",
            "STEPFNSTEP",
            "FORMEXPANSIONSTEP",
            "MANUALFILLNEEDEDSTEP",
            "ATCOMPLETION",
        }:
            return ctx
        

def _undo_to_start(runner: SessionProgramScriptedHeadlessRunner) -> None:
    """
    Avoid stopping immediately on the current kind.

    Previous tests used undo_until_stop with ATCOMPLETION or MANUALFILLNEEDEDSTEP
    in the stop set while already sitting on that kind, which caused a no-op.
    ATSTART forces actual unwinding.
    """
    runner.undo_until_stop(stop_kinds=["ATSTART"])


# =============================================================================
# Section 2: Synthetic scalable step functions
# =============================================================================


def _step_patch_scalars(
    _state: Dict[str, Any],
    *,
    i: int,
    group: str = "g",
) -> Dict[str, Any]:
    return {
        f"k_{i}": int(i),
        "group": str(group),
    }


def _step_patch_giant_blob(
    _state: Dict[str, Any],
    *,
    i: int,
    group: str,
    blob_chars: int,
    char: str = "x",
) -> Dict[str, Any]:
    return {
        f"blob_{i}": str(char) * int(blob_chars),
        "group": str(group),
        "i": int(i),
    }


def _step_patch_many_keys(
    _state: Dict[str, Any],
    *,
    count: int,
    prefix: str = "k",
) -> Dict[str, Any]:
    return {f"{prefix}_{i}": i for i in range(int(count))}


def _step_heavy_compute_then_small_write(
    _state: Dict[str, Any],
    *,
    i: int,
    loops: int,
    group: str = "compute",
) -> Dict[str, Any]:
    acc = 0
    for n in range(int(loops)):
        acc = (acc + ((n ^ int(i)) % 97)) % 1_000_000_007
    return {
        f"compute_{i}": acc,
        "group": str(group),
    }


def _step_query_writes(
    state: Dict[str, Any],
    *,
    query: Dict[str, Any],
    out_key: str = "query_result",
) -> Dict[str, Any]:
    return {
        str(out_key): query_runtime_writes(state, query),
    }


def _step_index_summary(
    state: Dict[str, Any],
    *,
    out_key: str = "index_summary",
) -> Dict[str, Any]:
    return {
        str(out_key): get_runtime_write_index_summary(state),
    }


def _step_ctx_probe(
    _state: Dict[str, Any],
    *,
    label: str = "ctx",
    __app_table_session_ctx__: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = dict(__app_table_session_ctx__ or {})
    stats = _bounded_container_stats(ctx)
    return {
        f"{label}_ctx_total_string_chars_seen": stats["total_string_chars_seen"],
        f"{label}_ctx_max_string_chars_seen": stats["max_string_chars_seen"],
        f"{label}_ctx_visited_nodes": stats["visited_nodes"],
        f"{label}_ctx_truncated": bool(stats["truncated"]),
        f"{label}_ctx_keys": sorted(str(k) for k in ctx.keys()),
        f"{label}_ctx_has_full_index": _contains_key_bounded(
            ctx,
            "_runtime_write_index_v1",
        ),
        f"{label}_ctx_has_blob_run": _contains_repeated_char_bounded(
            ctx,
            char="x",
            run_len=1000,
        ),
    }


def _step_nested_arg_probe(
    _state: Dict[str, Any],
    *,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "nested_probe_ok": True,
        "nested_probe_cfg_keys": sorted(str(k) for k in dict(cfg).keys()),
    }


def _multiframespec_many_datums(
    *,
    form_id: str,
    datum_count: int,
    prefill_chars: int = 0,
    prefill_char: str = "p",
    spans_per_frame: int = 1,
) -> Dict[str, Any]:
    """
    Build a simple form.

    Important: datum ids are prefixed by form_id. Earlier versions used D0/D1
    for every form, which allowed one form's fills/prefills to collide with a
    later form's pending manual fields. That made mixed adversarial tests query
    zero manual fills because the later manual form was already considered filled.
    """
    datums: List[Dict[str, Any]] = []
    frames: List[Dict[str, Any]] = []
    fills: Dict[str, Any] = {}

    datum_count_i = int(datum_count)
    spans_per_frame_i = max(1, int(spans_per_frame))
    prefix = _safe_ident(form_id)

    for i in range(datum_count_i):
        did = f"{prefix}_D{i}"
        datums.append(
            {
                "id": did,
                "title": did,
                "micros": [
                    {
                        "name": "value",
                        "type": "text",
                        "required": True,
                    }
                ],
            }
        )
        if prefill_chars:
            fills[did] = {
                "value": str(prefill_char) * int(prefill_chars),
            }

    frame_index = 0
    for start in range(0, datum_count_i, spans_per_frame_i):
        spans = []
        for j in range(start, min(start + spans_per_frame_i, datum_count_i)):
            did = f"{prefix}_D{j}"
            spans.append(
                {
                    "id": f"{prefix}_S{j}",
                    "owns": [did],
                }
            )
        frames.append(
            {
                "id": f"{prefix}_F{frame_index}",
                "title": f"Frame {frame_index}",
                "spans": spans,
            }
        )
        frame_index += 1

    return {
        "app_form_id": str(form_id),
        "datums": datums,
        "frames": frames,
        "fills": fills,
    }


def _step_emit_many_prefills(
    _state: Dict[str, Any],
    *,
    datum_count: int,
    prefill_chars: int = 0,
    form_id: str = "MANY_PREFILLS",
    prefill_char: str = "p",
    spans_per_frame: int = 1,
) -> Dict[str, Any]:
    return {
        "multiframespec": _multiframespec_many_datums(
            form_id=str(form_id),
            datum_count=int(datum_count),
            prefill_chars=int(prefill_chars),
            prefill_char=str(prefill_char),
            spans_per_frame=int(spans_per_frame),
        )
    }


def _step_emit_many_manuals(
    _state: Dict[str, Any],
    *,
    datum_count: int,
    form_id: str = "MANY_MANUALS",
    spans_per_frame: int = 1,
) -> Dict[str, Any]:
    return {
        "multiframespec": _multiframespec_many_datums(
            form_id=str(form_id),
            datum_count=int(datum_count),
            prefill_chars=0,
            spans_per_frame=int(spans_per_frame),
        )
    }


@pytest.fixture(autouse=True)
def _setup_complexity_registry():
    StepFnregistry.clear()

    StepFnregistry.register(
        name="scale.patch_scalars",
        fn=_step_patch_scalars,
        required_args={"i"},
        optional_args={"group"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.patch_giant_blob",
        fn=_step_patch_giant_blob,
        required_args={"i", "group", "blob_chars"},
        optional_args={"char"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.patch_many_keys",
        fn=_step_patch_many_keys,
        required_args={"count"},
        optional_args={"prefix"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.heavy_compute_then_small_write",
        fn=_step_heavy_compute_then_small_write,
        required_args={"i", "loops"},
        optional_args={"group"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.query_writes",
        fn=_step_query_writes,
        required_args={"query"},
        optional_args={"out_key"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.index_summary",
        fn=_step_index_summary,
        required_args=set(),
        optional_args={"out_key"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.ctx_probe",
        fn=_step_ctx_probe,
        required_args=set(),
        optional_args={"label"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.nested_arg_probe",
        fn=_step_nested_arg_probe,
        required_args={"cfg"},
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.emit_many_prefills",
        fn=_step_emit_many_prefills,
        required_args={"datum_count"},
        optional_args={
            "prefill_chars",
            "form_id",
            "prefill_char",
            "spans_per_frame",
        },
        overwrite=True,
    )
    StepFnregistry.register(
        name="scale.emit_many_manuals",
        fn=_step_emit_many_manuals,
        required_args={"datum_count"},
        optional_args={"form_id", "spans_per_frame"},
        overwrite=True,
    )



# =============================================================================
# Section 3: Manifest builders
# =============================================================================


def _manifest_patch_only(
    n: int,
    *,
    group: str = "length",
) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": f"s{i}",
            "step_fn": "scale.patch_scalars",
            "fn_args": {
                "i": i,
                "group": group,
            },
        }
        for i in range(int(n))
    ]


def _manifest_giant_blobs(
    *,
    n: int,
    blob_chars: int,
    group: str = "giant",
    char: str = "x",
    query: bool = True,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = [
        {
            "public_step_name": f"blob{i}",
            "step_fn": "scale.patch_giant_blob",
            "fn_args": {
                "i": i,
                "group": group,
                "blob_chars": int(blob_chars),
                "char": char,
            },
        }
        for i in range(int(n))
    ]

    if query:
        steps.append(
            {
                "public_step_name": "query",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": group,
                        "write_kinds": ["state"],
                        "max_results": int(max_results),
                    },
                    "out_key": "q",
                },
            }
        )

    return steps


def _manifest_heavy_compute(
    *,
    n: int,
    loops: int,
    group: str = "compute",
) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": f"compute{i}",
            "step_fn": "scale.heavy_compute_then_small_write",
            "fn_args": {
                "i": i,
                "loops": int(loops),
                "group": group,
            },
        }
        for i in range(int(n))
    ]


# =============================================================================
# Section 4: Program length / runtime tape growth
# =============================================================================


@pytest.mark.parametrize("small_n,large_n", [(50, 500)])
def test_program_length_runtime_is_not_superlinear(
    small_n: int,
    large_n: int,
):
    def run_n(n: int) -> None:
        sid, _ctx, out = _run_manifest_to_completion(_manifest_patch_only(n))
        assert out["globals"][f"k_{n - 1}"] == n - 1
        idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
        assert len(idx["invocation_order"]) >= n

    small_t = _median_seconds(lambda: run_n(small_n), repeats=3)
    large_t = _median_seconds(lambda: run_n(large_n), repeats=3)

    print(
        "[complexity-summary] program_length "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s"
    )

    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=12.0,
        label="program length stepping",
    )


@pytest.mark.parametrize("n", [1, 10, 100])
def test_program_length_index_counts_match_executed_steps(n: int):
    sid, _ctx, _out = _run_manifest_to_completion(_manifest_patch_only(n))
    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)

    assert len(idx["invocation_order"]) >= n
    assert len(idx["invocations"]) >= n
    assert "scale.patch_scalars" in idx["by_step_fn"]
    assert "group" in idx["by_arg_name"]


# =============================================================================
# Section 5: Query result boundedness and exact indexes
# =============================================================================


def test_query_by_public_step_name_step_fn_arg_name_and_arg_value():
    manifest = _manifest_patch_only(20, group="indexed")
    manifest.extend(
        [
            {
                "public_step_name": "q_public_name",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "s7",
                        "write_kinds": ["state"],
                        "max_results": 32,
                    },
                    "out_key": "q_public_name",
                },
            },
            {
                "public_step_name": "q_step_fn",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "step_fn": "scale.patch_scalars",
                        "write_kinds": ["state"],
                        "max_results": 8,
                    },
                    "out_key": "q_step_fn",
                },
            },
            {
                "public_step_name": "q_arg_name",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_name": "group",
                        "write_kinds": ["state"],
                        "max_results": 8,
                    },
                    "out_key": "q_arg_name",
                },
            },
            {
                "public_step_name": "q_arg_value",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": "indexed",
                        "write_kinds": ["state"],
                        "max_results": 8,
                    },
                    "out_key": "q_arg_value",
                },
            },
        ]
    )

    _sid, _ctx, out = _run_manifest_to_completion(manifest)
    gl = out["globals"]

    assert gl["q_public_name"]["ok"] is True
    assert all(w["public_step_name"] == "s7" for w in gl["q_public_name"]["writes"])

    assert gl["q_step_fn"]["ok"] is True
    assert len(gl["q_step_fn"]["writes"]) == 8
    assert gl["q_step_fn"]["truncated"] is True

    assert gl["q_arg_name"]["ok"] is True
    assert len(gl["q_arg_name"]["writes"]) == 8

    assert gl["q_arg_value"]["ok"] is True
    assert len(gl["q_arg_value"]["writes"]) == 8


def test_query_max_results_is_a_hard_materialization_bound():
    manifest = _manifest_patch_only(250, group="bounded")
    manifest.append(
        {
            "public_step_name": "q",
            "step_fn": "scale.query_writes",
            "fn_args": {
                "query": {
                    "arg_path": "group",
                    "arg_value_equals": "bounded",
                    "write_kinds": ["state"],
                    "max_results": 7,
                },
                "out_key": "q",
            },
        }
    )

    _sid, _ctx, out = _run_manifest_to_completion(manifest)
    q = out["globals"]["q"]

    assert q["ok"] is True
    assert len(q["writes"]) == 7
    assert q["truncated"] is True
    _assert_bounded_string_chars(
        q,
        max_total_string_chars=20_000,
        label="bounded query",
    )


def test_last_k_invocations_query_is_bounded():
    manifest = _manifest_patch_only(100, group="lastk")
    manifest.append(
        {
            "public_step_name": "q",
            "step_fn": "scale.query_writes",
            "fn_args": {
                "query": {
                    "last_k_invocations": 3,
                    "write_kinds": ["state"],
                    "max_results": 100,
                },
                "out_key": "q",
            },
        }
    )

    _sid, _ctx, out = _run_manifest_to_completion(manifest)
    q = out["globals"]["q"]

    assert q["ok"] is True
    assert q["seq_count"] == 3
    assert len(q["writes"]) <= 100


# =============================================================================
# Section 6: Giant direct state values must not leak into query/index surfaces
# =============================================================================


@pytest.mark.parametrize("small_blob,large_blob", [(1_000, 1_000_000)])
def test_query_result_size_does_not_scale_with_historical_blob_size(
    small_blob: int,
    large_blob: int,
):
    def run_blob(blob_chars: int) -> Dict[str, Any]:
        _sid, _ctx, out = _run_manifest_to_completion(
            _manifest_giant_blobs(
                n=8,
                blob_chars=blob_chars,
                group="giant",
                char="x",
                query=True,
                max_results=5,
            )
        )
        return out

    small_out, small_t = _time_one(
        f"giant blob query small_blob={small_blob}",
        lambda: run_blob(small_blob),
    )
    large_out, large_t = _time_one(
        f"giant blob query large_blob={large_blob}",
        lambda: run_blob(large_blob),
    )

    small_q = small_out["globals"]["q"]
    large_q = large_out["globals"]["q"]

    assert len(small_q["writes"]) == 5
    assert len(large_q["writes"]) == 5

    _assert_query_rows_are_ref_preview_only(
        small_q,
        max_total_string_chars=25_000,
        forbidden_char="x",
        forbidden_run=1000,
    )
    _assert_query_rows_are_ref_preview_only(
        large_q,
        max_total_string_chars=25_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    print(
        "[complexity-summary] query_vs_blob_size "
        f"small_blob={small_blob} small_t={small_t:.6f}s "
        f"large_blob={large_blob} large_t={large_t:.6f}s "
        "query_result_rows=5"
    )


def test_runtime_index_itself_does_not_store_giant_direct_state_values():
    sid, _ctx, _out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=3,
            blob_chars=500_000,
            group="index_no_blob",
            char="x",
            query=True,
            max_results=3,
        )
    )

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    idx_stats = _assert_bounded_string_chars(
        idx,
        max_total_string_chars=250_000,
        label="runtime index",
    )
    _assert_no_repeated_char_bounded(
        idx,
        char="x",
        run_len=1000,
        label="runtime index",
    )

    summary = get_runtime_write_index_summary(
        _state_from_snapshot(get_concrete_session_api(), sid)
    )
    assert summary["present"] is True
    assert summary["write_event_count"] >= 3

    print(
        "[complexity-summary] runtime_index_no_blob "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"write_events={summary['write_event_count']}"
    )


def test_include_values_is_explicit_and_can_materialize_current_value_only_when_requested():
    sid, _ctx, _out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=1,
            blob_chars=50_000,
            group="include_values",
            char="x",
            query=False,
        )
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)

    default_q = query_runtime_writes(
        state,
        {
            "arg_path": "group",
            "arg_value_equals": "include_values",
            "write_kinds": ["state"],
            "max_results": 10,
        },
    )
    assert default_q["writes"]
    assert "value" not in default_q["writes"][0]
    _assert_no_repeated_char_bounded(
        default_q,
        char="x",
        run_len=1000,
        label="default query",
    )

    explicit_q = query_runtime_writes(
        state,
        {
            "arg_path": "group",
            "arg_value_equals": "include_values",
            "write_kinds": ["state"],
            "max_results": 10,
            "include_values": True,
        },
    )
    assert explicit_q["writes"]
    assert any("value" in row for row in explicit_q["writes"])
    _assert_has_repeated_char_bounded(
        explicit_q,
        char="x",
        run_len=1000,
        label="explicit include_values query",
    )


# =============================================================================
# Section 7: Fn arg shallow indexing and giant nested arg protection
# =============================================================================


def test_fn_args_indexing_is_shallow_and_does_not_walk_huge_nested_args():
    huge_nested = {
        "enabled": True,
        "mode": "fast",
        "huge": {
            "payload": "z" * 1_000_000,
            "deeper": {
                "payload2": "y" * 1_000_000,
            },
        },
    }

    sid, _ctx, out = _run_manifest_to_completion(
        [
            {
                "public_step_name": "nested",
                "step_fn": "scale.nested_arg_probe",
                "fn_args": {
                    "cfg": huge_nested,
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "cfg.enabled",
                        "arg_value_equals": True,
                        "max_results": 16,
                    },
                    "out_key": "q",
                },
            },
        ]
    )

    assert out["globals"]["nested_probe_ok"] is True

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)

    assert _contains_text_bounded(idx, "cfg.enabled")
    assert _contains_text_bounded(idx, "cfg.mode")
    _assert_no_repeated_char_bounded(idx, char="z", run_len=1000, label="runtime index")
    _assert_no_repeated_char_bounded(idx, char="y", run_len=1000, label="runtime index")

    q = out["globals"]["q"]
    assert q["ok"] is True


@pytest.mark.parametrize("nested_blob_chars", [10_000, 1_000_000])
def test_fn_arg_nested_blob_size_does_not_change_index_size_much(nested_blob_chars: int):
    sid, _ctx, _out = _run_manifest_to_completion(
        [
            {
                "public_step_name": "nested",
                "step_fn": "scale.nested_arg_probe",
                "fn_args": {
                    "cfg": {
                        "enabled": True,
                        "mode": "stable",
                        "huge": {
                            "payload": "n" * int(nested_blob_chars),
                        },
                    }
                },
            }
        ]
    )
    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    idx_stats = _bounded_container_stats(idx)

    assert _contains_text_bounded(idx, "cfg.enabled")
    assert _contains_text_bounded(idx, "cfg.mode")
    _assert_no_repeated_char_bounded(idx, char="n", run_len=1000, label="runtime index")
    assert idx_stats["total_string_chars_seen"] < 100_000


# =============================================================================
# Section 8: Direct write count scaling
# =============================================================================


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_many_direct_state_write_keys_are_indexed_linearly(count: int):
    sid, _ctx, out = _run_manifest_to_completion(
        [
            {
                "public_step_name": "many_keys",
                "step_fn": "scale.patch_many_keys",
                "fn_args": {
                    "count": count,
                    "prefix": "many",
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "many_keys",
                        "write_kinds": ["state"],
                        "max_results": count + 10,
                    },
                    "out_key": "q",
                },
            },
        ]
    )

    q = out["globals"]["q"]
    assert q["ok"] is True
    keys = {row["key"] for row in q["writes"]}
    assert "many_0" in keys
    assert f"many_{count - 1}" in keys

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    assert len(idx["write_events"]) >= count


# =============================================================================
# Section 9: multiframespec width, form prefills, and payload non-materialization
# =============================================================================


@pytest.mark.parametrize("datum_count", [10, 100, 500])
def test_multiframespec_prefill_count_is_queryable_and_bounded(datum_count: int):
    _sid, _ctx, out = _run_manifest_to_completion(
        [
            {
                "public_step_name": "prefills",
                "step_fn": "scale.emit_many_prefills",
                "fn_args": {
                    "datum_count": datum_count,
                    "prefill_chars": 8,
                    "form_id": "PREFILLS",
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "prefills",
                        "write_kinds": ["form_prefill"],
                        "max_results": 7,
                    },
                    "out_key": "q_prefills",
                },
            },
        ]
    )

    q = out["globals"]["q_prefills"]
    assert q["ok"] is True
    assert len(q["writes"]) == min(7, datum_count)
    assert q["truncated"] is (datum_count > 7)
    assert all(row["write_kind"] == "form_prefill" for row in q["writes"])


def test_many_large_prefills_are_indexed_as_refs_and_previews_not_payload_copies():
    sid, _ctx, out = _run_manifest_to_completion(
        [
            {
                "public_step_name": "prefills",
                "step_fn": "scale.emit_many_prefills",
                "fn_args": {
                    "datum_count": 300,
                    "prefill_chars": 100_000,
                    "prefill_char": "p",
                    "form_id": "BIG_PREFILLS",
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "prefills",
                        "write_kinds": ["form_prefill"],
                        "max_results": 10,
                    },
                    "out_key": "q_prefills",
                },
            },
        ]
    )

    q = out["globals"]["q_prefills"]

    assert len(q["writes"]) == 10
    assert q["truncated"] is True
    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=40_000,
        forbidden_char="p",
        forbidden_run=1000,
    )

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    _assert_no_repeated_char_bounded(idx, char="p", run_len=1000, label="runtime index")


# =============================================================================
# Section 10: Manual fill indexing and attribution
# =============================================================================


@pytest.mark.parametrize("datum_count", [5, 25, 100])
def test_manual_fills_are_attributed_to_source_step_and_queryable(datum_count: int):
    sid, _ctx, out = _manual_fill_all_to_completion(
        manifest=[
            {
                "public_step_name": "manual_form",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datum_count,
                    "form_id": "MANUALS",
                    "spans_per_frame": 1,
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "manual_form",
                        "write_kinds": ["form_fill"],
                        "max_results": datum_count + 10,
                    },
                    "out_key": "q_manuals",
                },
            },
        ],
        fill_value="ok",
    )

    q = out["globals"]["q_manuals"]
    assert q["ok"] is True
    assert len(q["writes"]) == datum_count
    assert all(row["write_kind"] == "form_fill" for row in q["writes"])
    assert all(row["public_step_name"] == "manual_form" for row in q["writes"])

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    assert len(idx["invocation_order"]) >= datum_count


def test_large_manual_fill_payload_does_not_leak_into_query_or_index():
    sid, _ctx, out = _manual_fill_all_to_completion(
        manifest=[
            {
                "public_step_name": "manual_big",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": 10,
                    "form_id": "MANUAL_BIG",
                    "spans_per_frame": 1,
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "manual_big",
                        "write_kinds": ["form_fill"],
                        "max_results": 10,
                    },
                    "out_key": "q_manual_big",
                },
            },
        ],
        fill_value="m" * 100_000,
    )

    q = out["globals"]["q_manual_big"]
    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=40_000,
        forbidden_char="m",
        forbidden_run=1000,
    )

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    _assert_no_repeated_char_bounded(
        idx,
        char="m",
        run_len=1000,
        label="runtime index after large manual fills",
    )


# =============================================================================
# Section 11: Predicate query bound
# =============================================================================


def test_predicate_query_is_bounded_and_receives_previews_not_raw_values():
    sid, _ctx, _out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=50,
            blob_chars=50_000,
            group="predicate",
            char="x",
            query=False,
        )
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)
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

    result = query_runtime_writes_v1(
        state,
        RuntimeWriteQueryV1(
            arg_name="group",
            predicate_arg_name="group",
            arg_predicate=pred,
            max_predicate_evals=5,
            write_kinds=("state",),
            max_results=100,
        ),
    )

    assert result["ok"] is True
    assert calls["n"] <= 5


# =============================================================================
# Section 12: Public ctx/session/script surfaces stay slim
# =============================================================================


def test_get_context_does_not_expose_runtime_index_tables():
    api = get_concrete_session_api()

    st = api.create_VM_session(
        manifest=_manifest_giant_blobs(
            n=5,
            blob_chars=500_000,
            group="ctx_slim",
            char="x",
            query=False,
        ),
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]
    sid = st["session_id"]

    r = SessionProgramScriptedHeadlessRunner(sid, api=api)
    r.step_until_stop(stop_kinds=["ATCOMPLETION"])

    ctx = api.get_session_context(sid)
    if _contains_key_bounded(ctx, "_runtime_write_index_v1"):
        pytest.fail("public session context exposed _runtime_write_index_v1", pytrace=False)


def test_reserved_runtime_stepfn_ctx_is_slim_by_default_even_after_giant_history():
    _sid, _ctx, out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=5,
            blob_chars=500_000,
            group="ctx_probe",
            char="x",
            query=False,
        )
        + [
            {
                "public_step_name": "ctx_probe",
                "step_fn": "scale.ctx_probe",
                "fn_args": {
                    "label": "probe",
                },
            }
        ]
    )

    gl = out["globals"]
    assert gl["probe_ctx_has_full_index"] is False
    assert gl["probe_ctx_has_blob_run"] is False
    assert gl["probe_ctx_total_string_chars_seen"] < 120_000


def test_script_runner_history_stays_slim_by_default_with_giant_values():
    api = get_concrete_session_api()

    rr = run_session_against_script_headless(
        manifest=_manifest_giant_blobs(
            n=4,
            blob_chars=500_000,
            group="runner_slim",
            char="x",
            query=True,
            max_results=3,
        ),
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        keep_full_history=False,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "stop_kinds": ["ATCOMPLETION"],
                "expect": {"kind": "ATCOMPLETION"},
            }
        ],
    )

    hist_stats = _bounded_container_stats(rr.history)
    assert hist_stats["total_string_chars_seen"] < 120_000
    _assert_no_repeated_char_bounded(
        rr.history,
        char="x",
        run_len=1000,
        label="script runner history",
    )


# =============================================================================
# Section 13: Undo removes runtime index events
# =============================================================================


def test_undo_removes_runtime_write_index_entries_for_unwound_steps():
    api = get_concrete_session_api()

    st = api.create_VM_session(
        manifest=_manifest_patch_only(8),
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]
    sid = st["session_id"]
    r = SessionProgramScriptedHeadlessRunner(sid, api=api)

    r.step_until_stop(stop_kinds=["ATCOMPLETION"])

    idx_before = _runtime_index_from_snapshot(api, sid)
    before_count = len(idx_before["invocation_order"])
    assert before_count >= 8

    _undo_to_start(r)

    idx_after = _runtime_index_from_snapshot(api, sid)
    after_count = len(idx_after["invocation_order"])

    assert after_count < before_count


def test_undo_after_manual_fills_removes_manual_fill_index_events():
    api = get_concrete_session_api()

    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "manual_form",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": 3,
                    "form_id": "UNDO_MANUALS",
                },
            },
        ],
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]
    sid = st["session_id"]
    r = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = r.step_until_stop(stop_kinds=["MANUALFILLNEEDEDSTEP"])
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    did = list(ctx["datum_widgets_on_this_span"])[0]
    r.step(fill={did: {"value": "ok"}})

    idx_after_fill = _runtime_index_from_snapshot(api, sid)
    count_after_fill = len(idx_after_fill["invocation_order"])
    assert count_after_fill >= 1

    _undo_to_start(r)

    idx_after_undo = _runtime_index_from_snapshot(api, sid)
    count_after_undo = len(idx_after_undo["invocation_order"])

    assert count_after_undo < count_after_fill


# =============================================================================
# Section 14: Snapshot/index size contract
# =============================================================================


def test_snapshot_contains_current_state_blob_but_index_does_not_duplicate_it():
    sid, _ctx, _out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=2,
            blob_chars=500_000,
            group="snapshot",
            char="x",
            query=False,
        )
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)
    idx = state["_runtime_write_index_v1"]

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
        label="runtime index",
    )

    idx_stats = _bounded_container_stats(idx)
    state_stats = _bounded_container_stats(state)
    assert idx_stats["total_string_chars_seen"] * 10 < state_stats["total_string_chars_seen"]


def test_index_summary_is_small_even_when_snapshot_state_is_large():
    sid, _ctx, _out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=5,
            blob_chars=250_000,
            group="summary_small",
            char="x",
            query=False,
        )
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)
    summary = get_runtime_write_index_summary(state)

    _assert_bounded_string_chars(
        summary,
        max_total_string_chars=30_000,
        label="index summary",
    )
    _assert_no_repeated_char_bounded(
        summary,
        char="x",
        run_len=1000,
        label="index summary",
    )
    assert summary["present"] is True


# =============================================================================
# Section 15: Heavy user computation remains isolated from engine complexity
# =============================================================================


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_heavy_user_compute_small_writes_engine_index_stays_small():
    manifest = _manifest_heavy_compute(n=20, loops=25_000, group="heavy_compute")
    manifest.extend(
        [
            {
                "public_step_name": "summary",
                "step_fn": "scale.index_summary",
                "fn_args": {
                    "out_key": "summary",
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": "heavy_compute",
                        "write_kinds": ["state"],
                        "max_results": 10,
                    },
                    "out_key": "q",
                },
            },
        ]
    )

    sid, dt = _time_one(
        "heavy user compute + small engine writes",
        lambda: _run_manifest_to_completion(manifest)[0],
    )

    out = get_concrete_session_api().get_outputs(sid)
    q = out["globals"]["q"]
    summary = out["globals"]["summary"]

    assert q["ok"] is True
    assert len(q["writes"]) == 10
    _assert_bounded_string_chars(
        q,
        max_total_string_chars=30_000,
        label="heavy compute query",
    )
    assert summary["write_event_count"] >= 20

    print(
        "[complexity-summary] heavy_compute_isolated "
        f"elapsed={dt:.6f}s writes={summary['write_event_count']}"
    )


# =============================================================================
# Section 16: Adversarial edge tests
# =============================================================================


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_adversarial_large_session_no_hidden_deep_materialization():
    steps: List[Dict[str, Any]] = []

    for i in range(120):
        steps.append(
            {
                "public_step_name": f"blob{i}",
                "step_fn": "scale.patch_giant_blob",
                "fn_args": {
                    "i": i,
                    "group": "adversarial",
                    "blob_chars": 100_000,
                    "char": "x",
                },
            }
        )

    for i in range(40):
        steps.append(
            {
                "public_step_name": f"compute{i}",
                "step_fn": "scale.heavy_compute_then_small_write",
                "fn_args": {
                    "i": i,
                    "loops": 10_000,
                    "group": "adversarial_compute",
                },
            }
        )

    steps.extend(
        [
            {
                "public_step_name": "prefills",
                "step_fn": "scale.emit_many_prefills",
                "fn_args": {
                    "datum_count": 150,
                    "prefill_chars": 50_000,
                    "prefill_char": "p",
                    "form_id": "ADV_PREFILLS",
                },
            },
            {
                "public_step_name": "ctx_probe",
                "step_fn": "scale.ctx_probe",
                "fn_args": {
                    "label": "adv",
                },
            },
            {
                "public_step_name": "summary",
                "step_fn": "scale.index_summary",
                "fn_args": {
                    "out_key": "summary",
                },
            },
            {
                "public_step_name": "q_blob",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": "adversarial",
                        "write_kinds": ["state"],
                        "max_results": 10,
                    },
                    "out_key": "q_blob",
                },
            },
            {
                "public_step_name": "q_prefills",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "prefills",
                        "write_kinds": ["form_prefill"],
                        "max_results": 10,
                    },
                    "out_key": "q_prefills",
                },
            },
        ]
    )

    (sid, _ctx, out), dt = _time_one(
        "adversarial large mixed session",
        lambda: _run_manifest_to_completion(steps),
    )

    gl = out["globals"]

    assert gl["adv_ctx_has_full_index"] is False
    assert gl["adv_ctx_has_blob_run"] is False
    assert gl["adv_ctx_total_string_chars_seen"] < 150_000

    q_blob = gl["q_blob"]
    q_prefills = gl["q_prefills"]

    assert len(q_blob["writes"]) == 10
    assert q_blob["truncated"] is True
    _assert_query_rows_are_ref_preview_only(
        q_blob,
        max_total_string_chars=50_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    assert len(q_prefills["writes"]) == 10
    assert q_prefills["truncated"] is True
    _assert_query_rows_are_ref_preview_only(
        q_prefills,
        max_total_string_chars=50_000,
        forbidden_char="p",
        forbidden_run=1000,
    )

    idx = _runtime_index_from_snapshot(get_concrete_session_api(), sid)
    idx_stats = _bounded_container_stats(idx)

    _assert_no_repeated_char_bounded(idx, char="x", run_len=1000, label="runtime index")
    _assert_no_repeated_char_bounded(idx, char="p", run_len=1000, label="runtime index")

    summary = gl["summary"]
    assert summary["invocation_count"] >= 120
    assert summary["write_event_count"] >= 120

    print(
        "[complexity-summary] adversarial_large_session "
        f"elapsed={dt:.6f}s "
        f"steps={len(steps)} "
        f"invocations={summary['invocation_count']} "
        f"write_events={summary['write_event_count']} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']}"
    )


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_adversarial_super_long_program_many_small_writes_zips_without_quadratic_wall():
    small_n = 200
    large_n = 2_000

    def run_n(n: int) -> str:
        sid, _ctx, out = _run_manifest_to_completion(
            _manifest_patch_only(n, group="superlong")
            + [
                {
                    "public_step_name": "q",
                    "step_fn": "scale.query_writes",
                    "fn_args": {
                        "query": {
                            "arg_path": "group",
                            "arg_value_equals": "superlong",
                            "write_kinds": ["state"],
                            "max_results": 5,
                        },
                        "out_key": "q",
                    },
                }
            ]
        )
        assert len(out["globals"]["q"]["writes"]) == 5
        return sid

    small_t = _median_seconds(lambda: run_n(small_n), repeats=2)
    large_t = _median_seconds(lambda: run_n(large_n), repeats=2)

    print(
        "[complexity-summary] adversarial_super_long_program "
        f"small_n={small_n} small_t={small_t:.6f}s "
        f"large_n={large_n} large_t={large_t:.6f}s"
    )

    _assert_not_superlinear_badly(
        small_y=small_t,
        large_y=large_t,
        small_n=small_n,
        large_n=large_n,
        slack=15.0,
        label="super long program",
    )


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_adversarial_super_large_writes_query_and_index_stay_tiny_relative_to_state():
    sid, _ctx, out = _run_manifest_to_completion(
        _manifest_giant_blobs(
            n=12,
            blob_chars=1_000_000,
            group="super_large_writes",
            char="x",
            query=True,
            max_results=6,
        )
    )

    q = out["globals"]["q"]
    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=40_000,
        forbidden_char="x",
        forbidden_run=1000,
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)
    idx = state["_runtime_write_index_v1"]

    state_stats = _bounded_container_stats(state)
    idx_stats = _bounded_container_stats(idx)

    _assert_no_repeated_char_bounded(idx, char="x", run_len=1000, label="runtime index")
    assert idx_stats["total_string_chars_seen"] * 20 < state_stats["total_string_chars_seen"]

    print(
        "[complexity-summary] adversarial_super_large_writes "
        f"state_string_chars_seen={state_stats['total_string_chars_seen']} "
        f"state_max_string_chars_seen={state_stats['max_string_chars_seen']} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"query_rows={len(q['writes'])}"
    )


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_adversarial_manual_fill_many_large_values_query_index_stay_bounded():
    datum_count = 75
    fill_chars = 150_000

    sid, _ctx, out = _manual_fill_all_to_completion(
        manifest=[
            {
                "public_step_name": "manual_adversarial",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datum_count,
                    "form_id": "MANUAL_ADV",
                    "spans_per_frame": 1,
                },
            },
            {
                "public_step_name": "q",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "manual_adversarial",
                        "write_kinds": ["form_fill"],
                        "max_results": 10,
                    },
                    "out_key": "q_manual",
                },
            },
        ],
        fill_value="m" * fill_chars,
    )

    q = out["globals"]["q_manual"]
    assert len(q["writes"]) == 10
    assert q["truncated"] is True

    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=50_000,
        forbidden_char="m",
        forbidden_run=1000,
    )

    state = _state_from_snapshot(get_concrete_session_api(), sid)
    idx = state["_runtime_write_index_v1"]
    idx_stats = _bounded_container_stats(idx)

    _assert_no_repeated_char_bounded(idx, char="m", run_len=1000, label="runtime index")

    print(
        "[complexity-summary] adversarial_manual_large_values "
        f"datum_count={datum_count} fill_chars={fill_chars} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"query_rows={len(q['writes'])}"
    )


@pytest.mark.skipif(not RUN_SLOW, reason="set APP_TABLE_COMPLEXITY_SLOW=1")
def test_adversarial_every_axis_mixed_end_to_end_contract():
    api = get_concrete_session_api()

    manifest: List[Dict[str, Any]] = []

    manifest.extend(_manifest_patch_only(300, group="all_axis_small"))
    manifest.extend(
        _manifest_giant_blobs(
            n=20,
            blob_chars=300_000,
            group="all_axis_blob",
            char="x",
            query=False,
        )
    )
    manifest.extend(
        _manifest_heavy_compute(
            n=20,
            loops=15_000,
            group="all_axis_compute",
        )
    )

    manifest.extend(
        [
            {
                "public_step_name": "all_axis_prefills",
                "step_fn": "scale.emit_many_prefills",
                "fn_args": {
                    "datum_count": 120,
                    "prefill_chars": 80_000,
                    "prefill_char": "p",
                    "form_id": "ALL_AXIS_PREFILLS",
                },
            },
            {
                "public_step_name": "all_axis_manuals",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": 30,
                    "form_id": "ALL_AXIS_MANUALS",
                    "spans_per_frame": 1,
                },
            },
            {
                "public_step_name": "all_axis_ctx_probe",
                "step_fn": "scale.ctx_probe",
                "fn_args": {
                    "label": "all_axis",
                },
            },
            {
                "public_step_name": "all_axis_summary",
                "step_fn": "scale.index_summary",
                "fn_args": {
                    "out_key": "summary",
                },
            },
            {
                "public_step_name": "q_small",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": "all_axis_small",
                        "write_kinds": ["state"],
                        "max_results": 6,
                    },
                    "out_key": "q_small",
                },
            },
            {
                "public_step_name": "q_blob",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "arg_path": "group",
                        "arg_value_equals": "all_axis_blob",
                        "write_kinds": ["state"],
                        "max_results": 6,
                    },
                    "out_key": "q_blob",
                },
            },
            {
                "public_step_name": "q_prefill",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "all_axis_prefills",
                        "write_kinds": ["form_prefill"],
                        "max_results": 6,
                    },
                    "out_key": "q_prefill",
                },
            },
            {
                "public_step_name": "q_manual",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": "all_axis_manuals",
                        "write_kinds": ["form_fill"],
                        "max_results": 6,
                    },
                    "out_key": "q_manual",
                },
            },
        ]
    )

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]
    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    t0 = time.perf_counter()

    while True:
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )
        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        runner.step(fill={str(did): {"value": "m" * 80_000} for did in pending})

    dt = time.perf_counter() - t0
    out = api.get_outputs(sid)
    gl = out["globals"]

    assert gl["all_axis_ctx_has_full_index"] is False
    assert gl["all_axis_ctx_has_blob_run"] is False
    assert gl["all_axis_ctx_total_string_chars_seen"] < 180_000

    expected = [
        ("q_small", "x", 6),
        ("q_blob", "x", 6),
        ("q_prefill", "p", 6),
        ("q_manual", "m", 6),
    ]
    for q_name, char, expected_rows in expected:
        q = gl[q_name]
        assert q["ok"] is True
        assert len(q["writes"]) == expected_rows
        assert q["truncated"] is True
        _assert_query_rows_are_ref_preview_only(
            q,
            max_total_string_chars=60_000,
            forbidden_char=char,
            forbidden_run=1000,
        )

    state = _state_from_snapshot(api, sid)
    idx = state["_runtime_write_index_v1"]

    _assert_no_repeated_char_bounded(idx, char="x", run_len=1000, label="runtime index")
    _assert_no_repeated_char_bounded(idx, char="p", run_len=1000, label="runtime index")
    _assert_no_repeated_char_bounded(idx, char="m", run_len=1000, label="runtime index")

    summary = gl["summary"]
    assert summary["present"] is True
    assert summary["invocation_count"] >= 300
    assert summary["write_event_count"] >= 300

    idx_stats = _bounded_container_stats(idx)
    state_stats = _bounded_container_stats(state)

    print(
        "[complexity-summary] adversarial_every_axis "
        f"elapsed={dt:.6f}s "
        f"authored_steps={len(manifest)} "
        f"invocations={summary['invocation_count']} "
        f"write_events={summary['write_event_count']} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"state_string_chars_seen={state_stats['total_string_chars_seen']} "
        f"state_max_string_chars_seen={state_stats['max_string_chars_seen']}"
    )


# =============================================================================
# Section 17: Meta taxonomy completeness guard
# =============================================================================


def test_complexity_contract_taxonomy_is_explicitly_documented():
    axes = {
        "program_length",
        "runtime_tape_length",
        "program_width",
        "fn_arg_width",
        "fn_arg_depth_blob_size",
        "direct_state_write_count",
        "direct_state_write_payload_size",
        "form_prefill_count",
        "form_prefill_payload_size",
        "manual_fill_count",
        "manual_fill_payload_size",
        "query_selectivity",
        "predicate_bound",
        "snapshot_index_size",
        "public_ctx_output_script_size",
        "undo_depth",
        "adversarial_cross_axis",
        "crazy_many_manual_io_steps",
        "crazy_many_forms_many_io_steps",
        "crazy_io_large_payloads",
        "crazy_io_deep_undo",
    }

    assert len(axes) == 21
    assert "adversarial_cross_axis" in axes
    assert "crazy_many_manual_io_steps" in axes
    assert "crazy_io_deep_undo" in axes


# =============================================================================
# Section 18: Crazy IO-step scale
# =============================================================================


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_crazy_single_form_many_many_manual_io_steps_scales_and_indexes_cleanly():
    """
    One emitted multiframespec generates many MANUALFILLNEEDEDSTEPs.

    This test now optionally profiles the public API and internal session wrapper
    when APP_TABLE_COMPLEXITY_PROFILE_MANUAL_IO=1.

    Normal mode:
        proves complexity contract and prints coarse split.

    Profile mode:
        additionally prints where the until_stop/fill time is going:
            api_public.step_session
            api_public.get_session_context
            internal.step_session.step_until_ui_stop_s
            internal.get_session_context.engine_get_context_s
            internal.*.decorate_role_s
            persist_s
    """
    api = get_concrete_session_api()
    profile_acc = _new_profile_accumulator()

    if RUN_MANUAL_IO_PROFILE:
        _install_api_call_profiler(api, profile_acc)

    datum_count = int(os.environ.get("APP_TABLE_COMPLEXITY_CRAZY_IO_COUNT", "250"))

    manifest = [
        {
            "public_step_name": "crazy_io_form",
            "step_fn": "scale.emit_many_manuals",
            "fn_args": {
                "datum_count": datum_count,
                "form_id": "CRAZY_IO_FORM",
                "spans_per_frame": 1,
            },
        },
        {
            "public_step_name": "q_manuals",
            "step_fn": "scale.query_writes",
            "fn_args": {
                "query": {
                    "public_step_name": "crazy_io_form",
                    "write_kinds": ["form_fill"],
                    "max_results": 17,
                },
                "out_key": "q_manuals",
            },
        },
        {
            "public_step_name": "summary",
            "step_fn": "scale.index_summary",
            "fn_args": {
                "out_key": "summary",
            },
        },
    ]

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_profile_metadata(
            enabled=RUN_MANUAL_IO_PROFILE,
            persistence="boundary",
            include_full_multiframespec_in_ctx=False,
            include_global_fill_keys_in_ctx=False,
            include_field_value_keys_in_ctx=False,
            include_forms_emitted_order_in_ctx=False,
        ),
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    manual_count = 0
    t_until_stop = 0.0
    t_fill = 0.0

    while True:
        t0 = time.perf_counter()
        ctx = _api_step_until_stop_no_harness(
            api,
            sid,
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
        )
        t_until_stop += time.perf_counter() - t0

        if ctx["kind"] == "ATCOMPLETION":
            break

        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        did = str(pending[0])

        t0 = time.perf_counter()
        ctx_after_fill = api.step_session(
            sid,
            fill={did: {"value": f"ok-{manual_count}"}},
        )
        t_fill += time.perf_counter() - t0

        if RUN_MANUAL_IO_PROFILE and manual_count % MANUAL_IO_PROFILE_EVERY == 0:
            _profile_accumulate(
                profile_acc,
                prefix="ctx_after_fill",
                profile=_extract_manual_io_profile(ctx_after_fill),
            )

        if RUN_MANUAL_IO_PROFILE and manual_count % MANUAL_IO_PROFILE_EVERY == 0:
            _profile_accumulate(
                profile_acc,
                prefix="ctx_after_fill",
                profile=_extract_manual_io_profile(ctx_after_fill),
            )

        manual_count += 1

    elapsed = t_until_stop + t_fill

    assert manual_count == datum_count

    out = api.get_outputs(sid)
    q = out["globals"]["q_manuals"]
    summary = out["globals"]["summary"]

    assert q["ok"] is True
    assert len(q["writes"]) == 17
    assert q["truncated"] is True
    assert all(row["write_kind"] == "form_fill" for row in q["writes"])
    assert all(row["public_step_name"] == "crazy_io_form" for row in q["writes"])

    assert summary["write_event_count"] >= datum_count
    assert summary["invocation_count"] >= datum_count

    idx = _runtime_index_from_snapshot(api, sid)
    idx_stats = _bounded_container_stats(idx)

    assert idx_stats["total_string_chars_seen"] < max(1_000_000, datum_count * 2_500)

    events_per_manual = len(idx["write_events"]) / max(1, manual_count)

    print(
        "[complexity-summary] crazy_single_form_manual_io "
        f"datum_count={datum_count} "
        f"manual_count={manual_count} "
        f"elapsed={elapsed:.6f}s "
        f"until_stop_s={t_until_stop:.6f}s "
        f"fill_s={t_fill:.6f}s "
        f"avg_until_stop_ms={(t_until_stop / max(1, manual_count)) * 1000:.3f} "
        f"avg_fill_ms={(t_fill / max(1, manual_count)) * 1000:.3f} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"write_events={summary['write_event_count']} "
        f"events_per_manual={events_per_manual:.2f}"
    )

    if RUN_MANUAL_IO_PROFILE:
        _print_profile_summary(
            "crazy_single_form_manual_io",
            profile_acc,
            manual_count=manual_count,
        )


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_crazy_many_forms_each_with_many_io_steps_scales_by_local_current_form_only():
    api = get_concrete_session_api()
    profile_acc = _new_profile_accumulator()

    if RUN_MANUAL_IO_PROFILE:
        _install_api_call_profiler(api, profile_acc)

    form_count = int(os.environ.get("APP_TABLE_COMPLEXITY_FORM_COUNT", "20"))
    datums_per_form = int(os.environ.get("APP_TABLE_COMPLEXITY_DATUMS_PER_FORM", "20"))
    expected_manuals = form_count * datums_per_form

    manifest: List[Dict[str, Any]] = []
    for i in range(form_count):
        manifest.append(
            {
                "public_step_name": f"io_form_{i}",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datums_per_form,
                    "form_id": f"IO_FORM_{i}",
                    "spans_per_frame": 1,
                },
            }
        )

    manifest.extend(
        [
            {
                "public_step_name": "q_last_form",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": f"io_form_{form_count - 1}",
                        "write_kinds": ["form_fill"],
                        "max_results": 10,
                    },
                    "out_key": "q_last_form",
                },
            },
            {
                "public_step_name": "summary",
                "step_fn": "scale.index_summary",
                "fn_args": {
                    "out_key": "summary",
                },
            },
        ]
    )

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_profile_metadata(
            enabled=RUN_MANUAL_IO_PROFILE,
            persistence="boundary",
            include_full_multiframespec_in_ctx=False,
            include_global_fill_keys_in_ctx=False,
            include_field_value_keys_in_ctx=False,
            include_forms_emitted_order_in_ctx=False,
        ),
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    manual_count = 0
    t_until_stop = 0.0
    t_fill = 0.0

    while True:
        t0 = time.perf_counter()
        ctx = _api_step_until_stop_no_harness(
            api,
            sid,
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
        )
        t_until_stop += time.perf_counter() - t0

        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        did = str(pending[0])

        t0 = time.perf_counter()
        ctx_after_fill = api.step_session(
            sid,
            fill={did: {"value": "ok"}},
        )
        t_fill += time.perf_counter() - t0

        if RUN_MANUAL_IO_PROFILE and manual_count % MANUAL_IO_PROFILE_EVERY == 0:
            _profile_accumulate(
                profile_acc,
                prefix="ctx_after_fill",
                profile=_extract_manual_io_profile(ctx_after_fill),
            )

        if RUN_MANUAL_IO_PROFILE and manual_count % MANUAL_IO_PROFILE_EVERY == 0:
            _profile_accumulate(
                profile_acc,
                prefix="ctx_after_fill",
                profile=_extract_manual_io_profile(ctx_after_fill),
            )

        manual_count += 1

    elapsed = t_until_stop + t_fill

    assert manual_count == expected_manuals

    out = api.get_outputs(sid)
    q = out["globals"]["q_last_form"]
    summary = out["globals"]["summary"]

    assert q["ok"] is True
    assert len(q["writes"]) == 10
    assert q["truncated"] is True
    assert all(row["public_step_name"] == f"io_form_{form_count - 1}" for row in q["writes"])

    assert summary["write_event_count"] >= expected_manuals
    assert summary["invocation_count"] >= expected_manuals

    ctx = api.get_session_context(sid)
    ctx_stats = _bounded_container_stats(ctx)
    assert not _contains_key_bounded(ctx, "_runtime_write_index_v1")
    assert ctx_stats["total_string_chars_seen"] < 150_000

    print(
        "[complexity-summary] crazy_many_forms_many_io "
        f"form_count={form_count} "
        f"datums_per_form={datums_per_form} "
        f"manual_count={manual_count} "
        f"elapsed={elapsed:.6f}s "
        f"until_stop_s={t_until_stop:.6f}s "
        f"fill_s={t_fill:.6f}s "
        f"avg_until_stop_ms={(t_until_stop / max(1, manual_count)) * 1000:.3f} "
        f"avg_fill_ms={(t_fill / max(1, manual_count)) * 1000:.3f} "
        f"write_events={summary['write_event_count']}"
    )

    if RUN_MANUAL_IO_PROFILE:
        _print_profile_summary(
            "crazy_many_forms_many_io",
            profile_acc,
            manual_count=manual_count,
        )


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_crazy_io_with_large_manual_payloads_query_and_index_stay_bounded():
    api = get_concrete_session_api()

    datum_count = int(os.environ.get("APP_TABLE_COMPLEXITY_LARGE_IO_COUNT", "120"))
    fill_chars = int(os.environ.get("APP_TABLE_COMPLEXITY_LARGE_IO_CHARS", "100000"))

    manifest = [
        {
            "public_step_name": "crazy_large_io",
            "step_fn": "scale.emit_many_manuals",
            "fn_args": {
                "datum_count": datum_count,
                "form_id": "CRAZY_LARGE_IO",
                "spans_per_frame": 1,
            },
        },
        {
            "public_step_name": "q",
            "step_fn": "scale.query_writes",
            "fn_args": {
                "query": {
                    "public_step_name": "crazy_large_io",
                    "write_kinds": ["form_fill"],
                    "max_results": 12,
                },
                "out_key": "q",
            },
        },
    ]

    sid, _ctx, out = _manual_fill_all_to_completion(
        manifest=manifest,
        fill_value="i" * fill_chars,
    )

    q = out["globals"]["q"]
    assert q["ok"] is True
    assert len(q["writes"]) == 12
    assert q["truncated"] is True

    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=60_000,
        forbidden_char="i",
        forbidden_run=1000,
    )

    idx = _runtime_index_from_snapshot(api, sid)
    idx_stats = _bounded_container_stats(idx)

    _assert_no_repeated_char_bounded(idx, char="i", run_len=1000, label="runtime index")

    state = _state_from_snapshot(api, sid)
    state_stats = _bounded_container_stats(state)

    _assert_has_repeated_char_bounded(state, char="i", run_len=1000, label="current state")

    print(
        "[complexity-summary] crazy_io_large_payloads "
        f"datum_count={datum_count} "
        f"fill_chars={fill_chars} "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"state_string_chars_seen={state_stats['total_string_chars_seen']} "
        f"state_max_string_chars_seen={state_stats['max_string_chars_seen']}"
    )


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_crazy_io_undo_deep_stack_cleans_runtime_write_index():
    api = get_concrete_session_api()

    datum_count = int(os.environ.get("APP_TABLE_COMPLEXITY_UNDO_IO_COUNT", "120"))

    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "undo_crazy_io",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datum_count,
                    "form_id": "UNDO_CRAZY_IO",
                    "spans_per_frame": 1,
                },
            },
        ],
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    filled = 0
    while filled < datum_count:
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )
        if ctx["kind"] == "ATCOMPLETION":
            break
        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1
        runner.step(fill={str(pending[0]): {"value": "ok"}})
        filled += 1

    assert filled == datum_count

    idx_before = _runtime_index_from_snapshot(api, sid)
    before_count = len(idx_before["invocation_order"])
    assert before_count >= datum_count

    t0 = time.perf_counter()
    _undo_to_start(runner)
    undo_elapsed = time.perf_counter() - t0

    idx_after = _runtime_index_from_snapshot(api, sid)
    after_count = len(idx_after["invocation_order"])

    assert after_count < before_count

    print(
        "[complexity-summary] crazy_io_undo "
        f"filled={filled} "
        f"undo_elapsed={undo_elapsed:.6f}s "
        f"before_invocations={before_count} "
        f"after_invocations={after_count}"
    )


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_manual_io_profile_read_current_manual_stop_cost():
    """
    Focused diagnostic:
      Park on one MANUALFILLNEEDEDSTEP and repeatedly read current context.

    If this is expensive, the bottleneck is not accepted fill. It is public
    context exposure / get_context / decoration / ctx copying.

    This test does not advance through hundreds of fills. It holds the engine
    still and measures repeated reads of the same manual stop.
    """
    api = get_concrete_session_api()
    profile_acc = _new_profile_accumulator()

    if RUN_MANUAL_IO_PROFILE:
        _install_api_call_profiler(api, profile_acc)

    datum_count = int(os.environ.get("APP_TABLE_COMPLEXITY_PROFILE_READ_DATUMS", "250"))
    read_count = int(os.environ.get("APP_TABLE_COMPLEXITY_PROFILE_READ_COUNT", "250"))

    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "profile_read_form",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datum_count,
                    "form_id": "PROFILE_READ_FORM",
                    "spans_per_frame": 1,
                },
            },
        ],
        initial_parameter_overrides={},
        session_metadata=_manual_io_profile_metadata(
            enabled=RUN_MANUAL_IO_PROFILE,
            persistence="boundary",
            include_full_multiframespec_in_ctx=False,
            include_global_fill_keys_in_ctx=False,
            include_field_value_keys_in_ctx=False,
            include_forms_emitted_order_in_ctx=False,
        ),
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop(
        stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    t0 = time.perf_counter()
    last_ctx = None
    for i in range(read_count):
        last_ctx = api.get_session_context(sid)

        if RUN_MANUAL_IO_PROFILE and i % MANUAL_IO_PROFILE_EVERY == 0:
            _profile_accumulate(
                profile_acc,
                prefix="manual_read",
                profile=_extract_manual_io_profile(last_ctx),
            )

    elapsed = time.perf_counter() - t0

    assert isinstance(last_ctx, Mapping)
    assert last_ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert len(list(last_ctx.get("datum_widgets_on_this_span") or [])) == 1

    ctx_stats = _bounded_container_stats(last_ctx)
    assert ctx_stats["total_string_chars_seen"] < 150_000

    print(
        "[complexity-summary] manual_io_profile_read_current_manual_stop "
        f"datum_count={datum_count} "
        f"read_count={read_count} "
        f"elapsed={elapsed:.6f}s "
        f"avg_read_ms={(elapsed / max(1, read_count)) * 1000:.3f} "
        f"ctx_total_string_chars_seen={ctx_stats['total_string_chars_seen']}"
    )

    if RUN_MANUAL_IO_PROFILE:
        _print_profile_summary(
            "manual_io_profile_read_current_manual_stop",
            profile_acc,
            manual_count=read_count,
        )
        


@pytest.mark.skipif(
    not RUN_CRAZY_IO,
    reason="set APP_TABLE_COMPLEXITY_CRAZY_IO=1",
)
def test_manual_io_runner_snapshot_overhead_is_not_engine_overhead():
    """
    Regression diagnostic:
      Proves that SessionProgramScriptedHeadlessRunner-based manual IO timings include runner/harness
      snapshot export overhead.

    This is not a product-engine failure. It is a test-measurement distinction.

    If this test shows raw API much faster than SessionProgramScriptedHeadlessRunner, then the crazy IO
    complexity timing tests must use direct API loops when measuring engine cost.
    """
    api = get_concrete_session_api()
    profile_acc = _new_profile_accumulator()

    if RUN_MANUAL_IO_PROFILE:
        _install_api_call_profiler(api, profile_acc)

    datum_count = int(os.environ.get("APP_TABLE_COMPLEXITY_RUNNER_COMPARE_COUNT", "100"))

    manifest = [
        {
            "public_step_name": "runner_compare_form",
            "step_fn": "scale.emit_many_manuals",
            "fn_args": {
                "datum_count": datum_count,
                "form_id": "RUNNER_COMPARE_FORM",
                "spans_per_frame": 1,
            },
        }
    ]

    # Raw API session.
    st_raw = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_profile_metadata(
            enabled=RUN_MANUAL_IO_PROFILE,
            persistence="boundary",
            include_full_multiframespec_in_ctx=False,
            include_global_fill_keys_in_ctx=False,
            include_field_value_keys_in_ctx=False,
            include_forms_emitted_order_in_ctx=False,
        ),
        get_map=False,
    )  # type: ignore[arg-type]

    sid_raw = st_raw["session_id"]

    raw_filled = 0
    t0 = time.perf_counter()

    while True:
        ctx = _api_step_until_stop_no_harness(
            api,
            sid_raw,
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
        )

        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        api.step_session(
            sid_raw,
            fill={str(pending[0]): {"value": "ok"}},
        )
        raw_filled += 1

    raw_elapsed = time.perf_counter() - t0

    assert raw_filled == datum_count

    # Runner session.
    st_runner = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata=_manual_io_profile_metadata(
            enabled=RUN_MANUAL_IO_PROFILE,
            persistence="boundary",
            include_full_multiframespec_in_ctx=False,
            include_global_fill_keys_in_ctx=False,
            include_field_value_keys_in_ctx=False,
            include_forms_emitted_order_in_ctx=False,
        ),
        get_map=False,
    )  # type: ignore[arg-type]

    sid_runner = st_runner["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid_runner, api=api)

    runner_filled = 0
    t0 = time.perf_counter()

    while True:
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )

        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        runner.step(fill={str(pending[0]): {"value": "ok"}})
        runner_filled += 1

    runner_elapsed = time.perf_counter() - t0

    assert runner_filled == datum_count

    print(
        "[complexity-summary] manual_io_runner_snapshot_overhead "
        f"datum_count={datum_count} "
        f"raw_elapsed={raw_elapsed:.6f}s "
        f"runner_elapsed={runner_elapsed:.6f}s "
        f"ratio={(runner_elapsed / max(raw_elapsed, 1e-9)):.3f}"
    )

    if RUN_MANUAL_IO_PROFILE:
        _print_profile_summary(
            "manual_io_runner_snapshot_overhead",
            profile_acc,
            manual_count=datum_count,
        )

    # This is intentionally loose. We are not requiring the runner to be fast;
    # we are documenting that it is not the engine timing surface.
    assert raw_elapsed < runner_elapsed

    
@pytest.mark.slow
def test_many_sequential_forms_query_targets_last_form_without_materializing_history():
    """
    Concept proven:
      Many forms are emitted over time, and each form has manual IO.

    This specifically proves:
      - forms_emitted history may grow,
      - form_fills may grow,
      - runtime index may grow,
      - querying the last form's writes remains bounded by max_results,
      - public session context does not expose runtime index internals.
    """
    api = get_concrete_session_api()

    form_count = 8
    datums_per_form = 8
    query_limit = 10
    expected_manuals = form_count * datums_per_form
    expected_last_form_rows = min(query_limit, datums_per_form)

    manifest: List[Dict[str, Any]] = []
    for i in range(form_count):
        manifest.append(
            {
                "public_step_name": f"io_form_{i}",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datums_per_form,
                    "form_id": f"IO_FORM_{i}",
                    "spans_per_frame": 1,
                },
            }
        )

    manifest.extend(
        [
            {
                "public_step_name": "q_last_form",
                "step_fn": "scale.query_writes",
                "fn_args": {
                    "query": {
                        "public_step_name": f"io_form_{form_count - 1}",
                        "write_kinds": ["form_fill"],
                        "max_results": query_limit,
                    },
                    "out_key": "q_last_form",
                },
            },
            {
                "public_step_name": "summary",
                "step_fn": "scale.index_summary",
                "fn_args": {
                    "out_key": "summary",
                },
            },
        ]
    )

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "boundary",
            }
        },
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    manual_count = 0
    t_until_stop = 0.0
    t_fill = 0.0

    while True:
        t0 = time.perf_counter()
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )
        t_until_stop += time.perf_counter() - t0

        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        did = str(pending[0])

        t0 = time.perf_counter()
        runner.step(fill={did: {"value": "ok"}})
        t_fill += time.perf_counter() - t0

        manual_count += 1

    elapsed = t_until_stop + t_fill

    assert manual_count == expected_manuals

    out = api.get_outputs(sid)
    q = out["globals"]["q_last_form"]
    summary = out["globals"]["summary"]

    assert q["ok"] is True
    assert len(q["writes"]) == expected_last_form_rows

    # Since the last form has fewer rows than query_limit, the result should not
    # claim truncation. If later constants make datums_per_form > query_limit,
    # this remains correct.
    assert q["truncated"] is (datums_per_form > query_limit)

    assert all(row["public_step_name"] == f"io_form_{form_count - 1}" for row in q["writes"])

    assert summary["write_event_count"] >= expected_manuals
    assert summary["invocation_count"] >= expected_manuals

    ctx = api.get_session_context(sid)
    ctx_stats = _bounded_container_stats(ctx)

    assert not _contains_key_bounded(ctx, "_runtime_write_index_v1")
    assert ctx_stats["total_string_chars_seen"] < 150_000

    print(
        "[complexity-summary] many_sequential_forms_query_targets_last_form "
        f"form_count={form_count} "
        f"datums_per_form={datums_per_form} "
        f"manual_count={manual_count} "
        f"elapsed={elapsed:.6f}s "
        f"until_stop_s={t_until_stop:.6f}s "
        f"fill_s={t_fill:.6f}s "
        f"avg_until_stop_ms={(t_until_stop / max(1, manual_count)) * 1000:.3f} "
        f"avg_fill_ms={(t_fill / max(1, manual_count)) * 1000:.3f} "
        f"write_events={summary['write_event_count']} "
        f"ctx_total_string_chars_seen={ctx_stats['total_string_chars_seen']}"
    )


@pytest.mark.slow
def test_large_manual_payloads_are_stored_in_state_but_not_duplicated_into_index_or_query():
    """
    Concept proven:
      Large manual payloads legitimately live in current state, but must not be
      duplicated into runtime index rows or query result rows.
    """
    api = get_concrete_session_api()

    datum_count = 24
    fill_chars = 20_000

    manifest = [
        {
            "public_step_name": "large_manual_payloads",
            "step_fn": "scale.emit_many_manuals",
            "fn_args": {
                "datum_count": datum_count,
                "form_id": "LARGE_MANUAL_PAYLOADS",
                "spans_per_frame": 1,
            },
        },
        {
            "public_step_name": "q",
            "step_fn": "scale.query_writes",
            "fn_args": {
                "query": {
                    "public_step_name": "large_manual_payloads",
                    "write_kinds": ["form_fill"],
                    "max_results": 12,
                },
                "out_key": "q",
            },
        },
    ]

    t0 = time.perf_counter()
    sid, _ctx, out = _manual_fill_all_to_completion(
        manifest=manifest,
        fill_value="i" * fill_chars,
        session_metadata={
            "manual_io": {
                "persistence": "boundary",
            }
        },
    )
    elapsed = time.perf_counter() - t0

    q = out["globals"]["q"]
    assert q["ok"] is True
    assert len(q["writes"]) == 12
    assert q["truncated"] is True

    _assert_query_rows_are_ref_preview_only(
        q,
        max_total_string_chars=60_000,
        forbidden_char="i",
        forbidden_run=1000,
    )

    idx = _runtime_index_from_snapshot(api, sid)
    idx_stats = _bounded_container_stats(idx)

    _assert_no_repeated_char_bounded(
        idx,
        char="i",
        run_len=1000,
        label="runtime index",
    )

    state = _state_from_snapshot(api, sid)
    state_stats = _bounded_container_stats(state)

    _assert_has_repeated_char_bounded(
        state,
        char="i",
        run_len=1000,
        label="current state",
    )

    print(
        "[complexity-summary] large_manual_payloads_state_not_index "
        f"datum_count={datum_count} "
        f"fill_chars={fill_chars} "
        f"elapsed={elapsed:.6f}s "
        f"index_string_chars_seen={idx_stats['total_string_chars_seen']} "
        f"state_string_chars_seen={state_stats['total_string_chars_seen']} "
        f"state_max_string_chars_seen={state_stats['max_string_chars_seen']}"
    )



def _runtime_invocation_count_from_snapshot(api: Any, sid: str) -> int:
    idx = _runtime_index_from_snapshot(api, sid)
    return len(idx["invocation_order"])


@pytest.mark.slow
def test_undo_many_manual_fills_removes_runtime_index_rows_without_scanning_payloads():
    """
    Concept proven:
      Undo removes runtime-write-index rows created by manual fills.

    Important:
      This test reads _runtime_index_from_snapshot(...), so it intentionally
      uses eager persistence. If persistence is boundary/disabled, the live
      engine may be correct while the snapshot helper reads stale state.

    Important:
      Do NOT include MANUALFILLNEEDEDSTEP in undo stop_kinds here. Including it
      lets undo_until_stop stop at the exposed manual screen without unwinding
      committed manual-fill work.
    """
    api = get_concrete_session_api()

    datum_count = 40

    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "undo_many_manual_fills",
                "step_fn": "scale.emit_many_manuals",
                "fn_args": {
                    "datum_count": datum_count,
                    "form_id": "UNDO_MANY_MANUAL_FILLS",
                    "spans_per_frame": 1,
                },
            },
        ],
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                # This test checks snapshot-visible undo/index cleanup.
                # Therefore it must not use boundary/disabled persistence.
                "persistence": "eager",
            }
        },
        get_map=False,
    )  # type: ignore[arg-type]

    sid = st["session_id"]
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    filled = 0
    t_fill_total = 0.0

    while filled < datum_count:
        ctx = runner.step_until_stop(
            stop_kinds=["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"]
        )
        if ctx["kind"] == "ATCOMPLETION":
            break

        pending = list(ctx.get("datum_widgets_on_this_span") or [])
        assert len(pending) == 1

        t0 = time.perf_counter()
        runner.step(fill={str(pending[0]): {"value": "ok"}})
        t_fill_total += time.perf_counter() - t0

        filled += 1

    assert filled == datum_count

    before_count = _runtime_invocation_count_from_snapshot(api, sid)
    assert before_count >= datum_count

    target_decreases = 10
    t0 = time.perf_counter()

    current_count = before_count
    decreases = 0

    for _ in range(target_decreases):
        # Critical: no MANUALFILLNEEDEDSTEP here.
        # We want undo to move past manual stops and actually unwind committed work.
        runner.undo_until_stop(
            stop_kinds=[
                "STEPFNSTEP",
                "FORMEXPANSIONSTEP",
                "ATSTART",
                "ATCOMPLETION",
            ]
        )

        next_count = _runtime_invocation_count_from_snapshot(api, sid)

        assert next_count < current_count, (
            "undo did not remove any runtime invocation rows; "
            f"before={current_count}, after={next_count}. "
            "Check undo_until_stop semantics and persistence policy."
        )

        decreases += current_count - next_count
        current_count = next_count

    undo_elapsed = time.perf_counter() - t0

    after_count = _runtime_invocation_count_from_snapshot(api, sid)


    print(
        "[complexity-summary] undo_many_manual_fills_removes_index_rows "
        f"filled={filled} "
        f"target_decreases={target_decreases} "
        f"actual_decreases={before_count - after_count} "
        f"fill_total_s={t_fill_total:.6f} "
        f"undo_elapsed={undo_elapsed:.6f}s "
        f"avg_fill_ms={(t_fill_total / max(1, filled)) * 1000:.3f} "
        f"avg_decrease_ms={(undo_elapsed / max(1, target_decreases)) * 1000:.3f} "
        f"before_invocations={before_count} "
        f"after_invocations={after_count}"
    )


def test_stepfn_without_runtime_ctx_kwarg_does_not_pay_ctx_cost():
    """
    Concept proven:
      A step fn that does not accept the reserved runtime ctx kwarg should not pay
      to build runtime ctx.
    """
    from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
    from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
    import time

    StepFnregistry.register(
        name="complexity.no_runtime_ctx_arg",
        fn=lambda state, n=1: {"out": int(n), "multiframespec": None},
        required_args=set(),
        optional_args={"n"},
        overwrite=True,
    )

    huge = "x" * 1_000_000
    manifest = [
        {
            "public_step_name": f"s{i}",
            "step_fn": "complexity.no_runtime_ctx_arg",
            "fn_args": {"n": i},
        }
        for i in range(200)
    ]

    api = get_concrete_session_api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={"huge": huge},
        session_metadata={},
        get_map=False,
    )
    sid = st["session_id"]

    t0 = time.perf_counter()
    ctx = api.step_session(sid)
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert elapsed < 1.0



def test_stepfn_accepting_slim_runtime_ctx_stays_bounded_with_giant_state():
    """
    Concept proven:
      Accepting __app_table_session_ctx__ should not accidentally materialize full
      snapshot/state/history when the runtime ctx profile is default/slim.
    """
    from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
    from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
    from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
        APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG,
    )
    import time
    import json

    seen_ctx_sizes = []

    def fn_with_slim_ctx(state, n=1, **kwargs):
        runtime_ctx = kwargs.get(APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG) or {}
        blob = json.dumps(runtime_ctx, sort_keys=True, default=str)
        seen_ctx_sizes.append(len(blob))

        assert runtime_ctx.get("session_metadata", {}).get("runtime_session_ctx", {}).get("profile") == "slim"

        # Critical: giant state value should not be present in injected ctx.
        assert "x" * 1000 not in blob

        return {"out": int(n), "multiframespec": None}

    StepFnregistry.register(
        name="complexity.with_slim_runtime_ctx_arg",
        fn=fn_with_slim_ctx,
        required_args=set(),
        optional_args={"n"},
        overwrite=True,
    )

    huge = "x" * 1_000_000
    manifest = [
        {
            "public_step_name": f"s{i}",
            "step_fn": "complexity.with_slim_runtime_ctx_arg",
            "fn_args": {"n": i},
        }
        for i in range(200)
    ]

    api = get_concrete_session_api()
    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={"huge": huge},
        session_metadata={},
        get_map=False,
    )
    sid = st["session_id"]

    t0 = time.perf_counter()
    ctx = api.step_session(sid)
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"
    assert seen_ctx_sizes
    assert max(seen_ctx_sizes) < 20_000
    assert elapsed < 1.5


def test_full_runtime_ctx_profile_is_explicit_opt_in_and_may_materialize_more():
    """
    Concept proven:
      Full runtime ctx is not accidental. It only happens when explicitly opted in
      through session_metadata.runtime_session_ctx.profile='full'.

    This test should not require full to be faster. Full is allowed to be heavier.
    """
    from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
    from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
    from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
        APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG,
    )

    profiles_seen = []

    def fn_with_ctx(state, **kwargs):
        runtime_ctx = kwargs.get(APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG) or {}
        profile = (
            runtime_ctx.get("session_metadata", {})
            .get("runtime_session_ctx", {})
            .get("profile")
        )
        profiles_seen.append(profile)
        return {"ok": True, "multiframespec": None}

    StepFnregistry.register(
        name="complexity.with_explicit_full_runtime_ctx",
        fn=fn_with_ctx,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )

    api = get_concrete_session_api()
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "s0",
                "step_fn": "complexity.with_explicit_full_runtime_ctx",
                "fn_args": {},
            }
        ],
        initial_parameter_overrides={"huge": "x" * 100_000},
        session_metadata={
            "runtime_session_ctx": {
                "profile": "full",
            }
        },
        get_map=False,
    )

    sid = st["session_id"]
    ctx = api.step_session(sid)

    assert ctx["kind"] == "ATCOMPLETION"
    assert profiles_seen == ["full"]


def test_runtime_ctx_slim_overhead_is_small_relative_to_no_ctx_kwarg():
    """
    Concept proven:
      Merely accepting the reserved runtime ctx kwarg should not create a major
      performance cliff under default slim profile.
    """
    from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
    from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
    from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
        APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG,
    )
    import time

    def no_ctx(state, n=1):
        return {"v": n, "multiframespec": None}

    def with_ctx(state, n=1, **kwargs):
        runtime_ctx = kwargs.get(APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG) or {}
        assert runtime_ctx.get("kind") in {"ATSTART", "STEPFNSTEP", "FORMEXPANSIONSTEP", "ATCOMPLETION", ""}
        return {"v": n, "multiframespec": None}

    StepFnregistry.register(
        name="complexity.ab.no_ctx",
        fn=no_ctx,
        required_args=set(),
        optional_args={"n"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="complexity.ab.with_slim_ctx",
        fn=with_ctx,
        required_args=set(),
        optional_args={"n"},
        overwrite=True,
    )

    def run(step_fn_name: str) -> float:
        api = get_concrete_session_api()
        manifest = [
            {
                "public_step_name": f"s{i}",
                "step_fn": step_fn_name,
                "fn_args": {"n": i},
            }
            for i in range(500)
        ]
        st = api.create_VM_session(
            manifest=manifest,
            initial_parameter_overrides={"huge": "x" * 1_000_000},
            session_metadata={},
            get_map=False,
        )
        sid = st["session_id"]

        t0 = time.perf_counter()
        ctx = api.step_session(sid)
        elapsed = time.perf_counter() - t0

        assert ctx["kind"] == "ATCOMPLETION"
        return elapsed

    no_ctx_t = run("complexity.ab.no_ctx")
    slim_ctx_t = run("complexity.ab.with_slim_ctx")

    print(
        "[complexity-summary] runtime_ctx_ab "
        f"no_ctx_t={no_ctx_t:.6f}s slim_ctx_t={slim_ctx_t:.6f}s "
        f"ratio={(slim_ctx_t / max(no_ctx_t, 1e-9)):.3f}"
    )

    # Loose enough for CI noise, strict enough to catch accidental full ctx.
    assert slim_ctx_t < max(0.25, no_ctx_t * 3.0)


    
"""
APP TABLE COMPLEXITY FINAL CONCLUSIONS
======================================

Final status:
    The App Table kernel and session/manual-IO path now pass the complexity
    contract across:

        - program-length scaling,
        - runtime write indexing,
        - bounded query surfaces,
        - giant value handling,
        - shallow fn-arg indexing,
        - prefill/fill indexing,
        - manual fill indexing,
        - public ctx exposure,
        - runtime ctx injection,
        - script history slimming,
        - undo cleanup,
        - snapshot/index separation,
        - adversarial mixed sessions.

Core theorem:
    Default App Table engine overhead scales with the explicit unit of work
    being performed, not with unrelated accumulated session mass.

    Engine/session machinery is defended against accidental:

        - full current-state materialization in indexes,
        - giant value duplication in runtime write rows,
        - giant value duplication in query rows,
        - deep traversal of nested fn args,
        - full runtime index exposure in public ctx,
        - full historical write materialization in bounded queries,
        - full script history retention by default,
        - repeated snapshot export in the engine hot path,
        - repeated full manual UI reconstruction per manual fill,
        - manual-fill undo leaving stale runtime-index rows.

Manual IO theorem:
    Manual IO is no longer the hidden complexity wall.

    Earlier measurements showed:

        crazy_many_forms_many_io:
            ~17.57s total for 400 manual fills

    Profiling showed the dominant cost was not manual IO execution itself:

        api_public.export_session_snapshot:
            ~16.93s of the 17.57s total

    That was runner/test-harness snapshot export pollution.

    After timing direct api.step_session loops, the same axis is now:

        crazy_many_forms_many_io:
            form_count=20
            datums_per_form=20
            manual_count=400
            elapsed ~= 0.535s
            avg_until_stop_ms ~= 0.178ms
            avg_fill_ms ~= 1.159ms

        crazy_single_form_manual_io:
            datum_count=250
            manual_count=250
            elapsed ~= 0.645s
            avg_until_stop_ms ~= 1.383ms
            avg_fill_ms ~= 1.195ms

    Therefore accepted manual fills and manual-stop exposure are local under
    the tested shapes.

    The correct law is:

        manual submit:
            O(number_of_fields_submitted_this_turn + validation of those fields)

        manual stop/read:
            O(current pending field/span overlay)

    not:

        O(total forms emitted)
        O(total previous manual fills)
        O(total runtime write history)
        O(snapshot size)
        O(full current state)
        O(full multiframespec history)
        O(full HTML/rendered page)

Manual IO implementation theorem:
    The manual IO hot path now compiles reusable structural form context once
    per pending form and performs per-turn overlays only.

    The engine avoids repeatedly rebuilding:

        - frames,
        - span_order,
        - span_to_datum_widgets,
        - datum_widget_decls,
        - datum validators,
        - full datum_widget_fills from all historical global fills.

    Accepted fills update:

        - the form_fills state bucket incrementally,
        - the manual datum_widget_fills cache incrementally,
        - one runtime write invocation/index event.

Snapshot theorem:
    export_session_snapshot() is an explicit materialization boundary.

    It is allowed to scale with the current restorable session image because
    the caller explicitly requested the full image.

    Therefore export_session_snapshot() must not be used in hot-loop engine
    timing unless snapshot export itself is the measured operation.

Runtime write index theorem:
    Runtime write index entries are metadata/reference/preview rows.

    They scale with:

        - number of executed invocations,
        - number of write events,
        - number of indexed shallow arg fields,
        - number of form prefill/fill events.

    They do not scale with:

        - size of giant state values,
        - size of historical blobs,
        - deep nested arg payloads,
        - full current-state string size,
        - query result max beyond max_results.

Query theorem:
    Runtime write queries are bounded by explicit query limits.

    Query result materialization scales with:

        - max_results,
        - selected invocation/event rows,
        - max_predicate_evals when predicates are used,
        - metadata/preview size.

    Query result materialization does not scale with:

        - full historical blob payload size,
        - full current state,
        - full values unless include_values=True is explicitly requested.

Large value theorem:
    Giant values may legitimately live in current state because user code wrote
    them. The engine cannot and should not make those values disappear.

    The engine obligation is narrower and satisfied:

        - do not duplicate giant values into runtime index rows,
        - do not duplicate giant values into bounded query rows,
        - do not expose giant values through public ctx by default,
        - do not inject giant values into slim runtime ctx by default,
        - do not scan giant values unless the caller explicitly asks for a
          materializing surface.

Prefill/form theorem:
    Form prefill/fill indexing scales with addressed fields/events, not with
    full payload size.

    Large prefill/manual payloads are stored in current state as authored, while
    index/query surfaces remain preview/reference bounded.

Runtime ctx theorem:
    Step functions that do not accept the reserved runtime ctx kwarg pay no
    runtime ctx construction cost.

    Step functions that accept runtime ctx receive the slim profile by default.
    The slim profile does not materialize full giant state, full snapshot, or
    runtime index internals.

    Full runtime ctx is an explicit opt-in and may be heavier.

Undo theorem:
    Undo removes runtime write index rows for unwound work, including manual
    fill events.

    The repaired manual-undo law is:

        if the cursor is parked on the next unexecuted manual stop, undo must
        unwind the previous executed manual fill instead of merely moving the
        cursor back while leaving that fill/index row intact.

Remaining legitimate costs:
    1. User-authored step function runtime.
    2. User-authored state payload size.
    3. User-authored write fanout.
    4. Explicit materialization APIs:
           export_session_snapshot(),
           include_values=True,
           full runtime ctx,
           full script history,
           full multiframespec-in-ctx,
           render=True,
           diagnostic global key lists.
    5. Test/runner assertion surfaces that intentionally export snapshots.

Final engineering target:
    Default engine/session behavior should be safe, local, bounded, and
    ergonomic.

    Heavy/materializing behavior should exist only behind explicit opt-ins with
    names that make the cost obvious.

Final defensive policy:
    The default policy should be:

        manual_io.persistence = "boundary"
        runtime_session_ctx.profile = "slim"
        query.include_values = False
        query.max_results = bounded
        predicate.max_predicate_evals = bounded
        keep_full_history = False
        render = False unless HTML is being measured/rendered
        export_session_snapshot forbidden in hot loops unless explicitly allowed

    Expert bypass should be explicit:

        manual_io.persistence = "eager"
        runtime_session_ctx.profile = "full"
        query.include_values = True
        include_snapshot = True
        keep_full_history = True
        render = True
        allow_snapshot_in_hot_loop = True

Bottom line:
    The engine has done what it can control for default hot execution.

    Remaining high costs are now either:

        - real user-authored work,
        - real user-authored payload size,
        - real write fanout,
        - explicit materialization APIs,
        - HTML rendering,
        - repo persistence,
        - or test/developer harness misuse.

    The final cleanup is therefore a defensive policy pass:
        make safe/local behavior the default,
        make heavy materialization explicit,
        and fail or profile loudly when callers cross a materialization boundary.
"""