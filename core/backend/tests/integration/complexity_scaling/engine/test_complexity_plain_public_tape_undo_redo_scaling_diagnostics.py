# think-backend/tests/wipppp/test_plain_public_tape_undo_redo_scaling_diagnostics.py
from __future__ import annotations

"""
Plain Public Tape Undo/Redo Scaling Diagnostics
===============================================

This diagnostic sheet intentionally avoids Q lifecycle entirely.

Why this file exists
--------------------
The exploded-world sheets show excellent signs that Q lifecycle itself is not
the remaining scaling risk:

    - plain P fill path is sub-millisecond per fill;
    - Q reexplode ticks are bounded and stable;
    - Q lifecycle writes are compact refs/previews;
    - Q undo/redo restores bounded lifecycle patches.

The remaining public-tape question is narrower:

    Is plain public undo/redo cost tied to actual public tape depth, or is the
    visible timing mostly current-form/current-surface reconstruction cost?

The important distinction:

    - True tape depth means many prior public actions/forms, while the current
      undo/redo target remains a tiny one-datum final form.

    - Current form/surface size means the currently active form contains many
      datums/spans/frames. That cost is allowed to scale with the current unit of
      UI work, but should not be mistaken for tape-history depth.

This sheet prints structured timings and asserts broad sanity properties:

    1. P fill remains fast and has no Q writes.
    2. True tape-depth-only undo/redo stays bounded when the final surface is tiny.
    3. Combined one-frame-many-spans diagnostics remain visible, but are labeled
       as combined depth + current form size, not pure depth.
    4. Full ctx vs slim ctx tells us whether context payload building is guilty.
    5. Frame/span shape diagnostics tell us whether current-form topology matters.
    6. Repeated get_session_context at completion tells us whether context reads
       alone are expensive, independent of mutation.
    7. Redo stack branch behavior remains correct under diagnostic load.

Use this sheet before optimizing. The print output is the deliverable: it should
tell us which layer deserves a patch.
"""

import statistics
import time
from typing import Any, Dict, List, Mapping, Sequence

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _manifest(step_name: str) -> List[Dict[str, Any]]:
    return _manifest_many([step_name])


def _manifest_many(step_names: Sequence[str]) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": step_name.replace(".", "_"),
            "step_fn": step_name,
            "fn_args": {},
        }
        for step_name in step_names
    ]


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _make_single_datum_multiframespec(
    *,
    app_form_id: str,
    datum_id: str = "D",
    span_id: str = "S",
    frame_id: str = "F",
    micro_name: str = "value0",
) -> Dict[str, Any]:
    """
    Build a tiny one-frame / one-span / one-datum P-only multiframespec.

    This is used by the true tape-depth diagnostic so prior tape depth can grow
    without also growing the final current form/surface.
    """
    return {
        "app_form_id": app_form_id,
        "datums": [
            {
                "id": datum_id,
                "title": datum_id,
                "micros": [_text_micro(micro_name)],
            }
        ],
        "frames": [
            {
                "id": frame_id,
                "spans": [{"id": span_id, "owns": [datum_id]}],
            }
        ],
    }


def _make_plain_p_multiframespec(
    *,
    app_form_id: str,
    n: int,
    shape: str,
    micros_per_datum: int = 1,
) -> Dict[str, Any]:
    """
    Build a plain P-only multiframespec.

    shape="one_frame_many_spans":
        F owns S0..S{n-1}; each span owns one datum.

    shape="many_frames_one_span_each":
        F0 owns S0, F1 owns S1, ...

    shape="one_frame_one_big_span":
        F owns S_ALL, and S_ALL owns every datum. This is useful for measuring
        same-surface size, but most tape tests should use one span per datum so
        each fill is a public tape step.
    """
    datums: List[Dict[str, Any]] = []
    for i in range(n):
        micros = [_text_micro(f"value{j}") for j in range(micros_per_datum)]
        datums.append({"id": f"D{i}", "title": f"D{i}", "micros": micros})

    if shape == "one_frame_many_spans":
        frames = [
            {
                "id": "F",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
            }
        ]
    elif shape == "many_frames_one_span_each":
        frames = [
            {
                "id": f"F{i}",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]}],
            }
            for i in range(n)
        ]
    elif shape == "one_frame_one_big_span":
        frames = [{"id": "F", "spans": [{"id": "S_ALL", "owns": [f"D{i}" for i in range(n)]}]}]
    else:
        raise AssertionError(f"unknown shape: {shape!r}")

    return {"app_form_id": app_form_id, "datums": datums, "frames": frames}


def _create(
    api,
    step_name: str,
    *,
    include_full_multiframespec_in_ctx: bool,
    include_forms_emitted_order_in_ctx: bool = False,
    include_global_fill_keys_in_ctx: bool = False,
    include_field_value_keys_in_ctx: bool = False,
) -> tuple[str, Mapping[str, Any]]:
    return _create_with_manifest(
        api,
        _manifest(step_name),
        include_full_multiframespec_in_ctx=include_full_multiframespec_in_ctx,
        include_forms_emitted_order_in_ctx=include_forms_emitted_order_in_ctx,
        include_global_fill_keys_in_ctx=include_global_fill_keys_in_ctx,
        include_field_value_keys_in_ctx=include_field_value_keys_in_ctx,
    )


def _create_with_manifest(
    api,
    manifest: Sequence[Mapping[str, Any]],
    *,
    include_full_multiframespec_in_ctx: bool,
    include_forms_emitted_order_in_ctx: bool = False,
    include_global_fill_keys_in_ctx: bool = False,
    include_field_value_keys_in_ctx: bool = False,
) -> tuple[str, Mapping[str, Any]]:
    st = api.create_VM_session(
        manifest=list(manifest),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_full_multiframespec_in_ctx": include_full_multiframespec_in_ctx,
                "include_forms_emitted_order_in_ctx": include_forms_emitted_order_in_ctx,
                "include_global_fill_keys_in_ctx": include_global_fill_keys_in_ctx,
                "include_field_value_keys_in_ctx": include_field_value_keys_in_ctx,
            },
            "redo": {"max_depth": 512},
        },
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return sid, ctx


def _fill_one_span_per_datum_to_completion(
    api,
    sid: str,
    *,
    n: int,
    micros_per_datum: int = 1,
) -> tuple[Mapping[str, Any], float]:
    t0 = time.perf_counter()
    ctx: Mapping[str, Any] = {}
    for i in range(n):
        fill = {
            f"D{i}": {
                f"value{j}": f"v{i}-{j}"
                for j in range(micros_per_datum)
            }
        }
        ctx = api.step_session(sid, fill=fill)
    elapsed = time.perf_counter() - t0
    assert ctx["kind"] == "ATCOMPLETION"
    return ctx, elapsed


def _fill_big_span_to_completion(
    api,
    sid: str,
    *,
    n: int,
    micros_per_datum: int = 1,
) -> tuple[Mapping[str, Any], float]:
    fill = {
        f"D{i}": {
            f"value{j}": f"v{i}-{j}"
            for j in range(micros_per_datum)
        }
        for i in range(n)
    }
    t0 = time.perf_counter()
    ctx = api.step_session(sid, fill=fill)
    elapsed = time.perf_counter() - t0
    assert ctx["kind"] == "ATCOMPLETION"
    return ctx, elapsed


def _measure_undo_redo_pairs(
    api,
    sid: str,
    *,
    pairs: int,
) -> Dict[str, Any]:
    """
    Repeatedly undo and redo the same last public manual action from completion.

    Each pair is:
        ATCOMPLETION --undo--> MANUALFILLNEEDEDSTEP --redo--> ATCOMPLETION

    This isolates public tape pair cost without walking the whole tape backward.
    It reports pair, undo, and redo timings separately so an asymmetric undo
    recovery cost does not get hidden inside a combined pair number.
    """
    pair_samples: List[float] = []
    undo_samples: List[float] = []
    redo_samples: List[float] = []
    undo_kinds: List[str] = []
    redo_kinds: List[str] = []

    for _ in range(pairs):
        pair_t0 = time.perf_counter()

        t0 = time.perf_counter()
        undo_ctx = api.undo_last_step(sid)
        undo_elapsed = time.perf_counter() - t0

        t0 = time.perf_counter()
        redo_ctx = api.redo_last_step(sid)
        redo_elapsed = time.perf_counter() - t0

        pair_elapsed = time.perf_counter() - pair_t0

        pair_samples.append(pair_elapsed)
        undo_samples.append(undo_elapsed)
        redo_samples.append(redo_elapsed)
        undo_kinds.append(str(undo_ctx["kind"]))
        redo_kinds.append(str(redo_ctx["kind"]))

        assert undo_ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert redo_ctx["kind"] == "ATCOMPLETION"

    pair_mean_ms = statistics.mean(pair_samples) * 1000
    pair_median_ms = statistics.median(pair_samples) * 1000
    pair_max_ms = max(pair_samples) * 1000

    undo_mean_ms = statistics.mean(undo_samples) * 1000
    undo_median_ms = statistics.median(undo_samples) * 1000
    undo_max_ms = max(undo_samples) * 1000

    redo_mean_ms = statistics.mean(redo_samples) * 1000
    redo_median_ms = statistics.median(redo_samples) * 1000
    redo_max_ms = max(redo_samples) * 1000

    return {
        "pairs": pairs,
        "total_s": sum(pair_samples),
        # Backward-compatible aliases used by the older diagnostic rows.
        "mean_ms": pair_mean_ms,
        "median_ms": pair_median_ms,
        "max_ms": pair_max_ms,
        # Explicit timing names.
        "pair_mean_ms": pair_mean_ms,
        "pair_median_ms": pair_median_ms,
        "pair_max_ms": pair_max_ms,
        "undo_mean_ms": undo_mean_ms,
        "undo_median_ms": undo_median_ms,
        "undo_max_ms": undo_max_ms,
        "redo_mean_ms": redo_mean_ms,
        "redo_median_ms": redo_median_ms,
        "redo_max_ms": redo_max_ms,
        "undo_kinds": undo_kinds,
        "redo_kinds": redo_kinds,
    }


def _measure_get_context_reads(
    api,
    sid: str,
    *,
    reads: int,
) -> Dict[str, Any]:
    samples: List[float] = []
    kinds: List[str] = []

    for _ in range(reads):
        t0 = time.perf_counter()
        ctx = api.get_session_context(sid)
        samples.append(time.perf_counter() - t0)
        kinds.append(str(ctx["kind"]))

    assert set(kinds) == {"ATCOMPLETION"}
    return {
        "reads": reads,
        "total_s": sum(samples),
        "mean_ms": statistics.mean(samples) * 1000,
        "median_ms": statistics.median(samples) * 1000,
        "max_ms": max(samples) * 1000,
    }


def _assert_no_q_lifecycle(api, sid: str) -> None:
    st = api._get(sid).state

    lifecycle = st.get(KEY_DATUM_LIFECYCLE)
    if isinstance(lifecycle, Mapping):
        assert lifecycle.get("forms") in ({}, None)

    index = st.get(KEY_RUNTIME_WRITE_INDEX, {})
    assert not _contains_write_kind(index, WRITE_KIND_DATUM_LIFECYCLE)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 10_000,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert q["writes"] == []


def _contains_write_kind(obj: Any, write_kind: str) -> bool:
    stack = [obj]
    seen: set[int] = set()

    while stack:
        cur = stack.pop()
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            if cur.get("write_kind") == write_kind:
                return True
            stack.extend(cur.keys())
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _print_summary(label: str, **values: Any) -> None:
    body = " ".join(f"{k}={v}" for k, v in values.items())
    print(f"[plain-tape-diagnostic] {label} {body}")


# ---------------------------------------------------------------------------
# Main diagnostic matrix
# ---------------------------------------------------------------------------


def test_plain_public_tape_true_depth_constant_final_surface_with_slim_context():
    """
    True tape-depth diagnostic.

    This is the clean test for the question:

        Does public undo/redo of the final manual action get slower merely
        because there are many prior public actions/forms behind it?

    The fixture deliberately keeps the final undo/redo surface tiny:
        - final form has one frame;
        - final frame has one span;
        - final span owns one datum;
        - final datum has one micro.

    Only prior history depth grows. If this grows sharply, the public undo/redo
    path is scanning prior tape/session state. If this is flat while the combined
    one-frame-many-spans diagnostics grow, the remaining cost is current-form /
    current-surface construction, not tape depth.
    """
    ns = [40, 80, 160]
    pairs = 20
    rows: List[Dict[str, Any]] = []

    for n in ns:
        step_names: List[str] = []

        for i in range(n):
            step_name = f"test.diag.p.tape.true_depth.prior.{n}.{i}"
            step_names.append(step_name)
            _register_step(
                step_name,
                _make_single_datum_multiframespec(
                    app_form_id=f"diag.p.tape.true_depth.prior.{n}.{i}",
                    datum_id=f"P{i}",
                    span_id=f"SP{i}",
                    frame_id=f"FP{i}",
                ),
            )

        final_step_name = f"test.diag.p.tape.true_depth.final.{n}"
        step_names.append(final_step_name)
        _register_step(
            final_step_name,
            _make_single_datum_multiframespec(
                app_form_id=f"diag.p.tape.true_depth.final.{n}",
                datum_id="FINAL",
                span_id="S_FINAL",
                frame_id="F_FINAL",
            ),
        )

        api = _api()
        sid, ctx = _create_with_manifest(
            api,
            _manifest_many(step_names),
            include_full_multiframespec_in_ctx=False,
        )
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        fill_t0 = time.perf_counter()
        for i in range(n):
            ctx = api.step_session(sid, fill={f"P{i}": {"value0": f"prior-{i}"}})
            assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

        ctx = api.step_session(sid, fill={"FINAL": {"value0": "final"}})
        fill_elapsed = time.perf_counter() - fill_t0
        assert ctx["kind"] == "ATCOMPLETION"

        pair_stats = _measure_undo_redo_pairs(api, sid, pairs=pairs)
        read_stats = _measure_get_context_reads(api, sid, reads=pairs)
        _assert_no_q_lifecycle(api, sid)

        row = {
            "prior_actions": n,
            "fill_elapsed_s": fill_elapsed,
            "fill_avg_ms": fill_elapsed * 1000 / (n + 1),
            "pair_mean_ms": pair_stats["pair_mean_ms"],
            "pair_median_ms": pair_stats["pair_median_ms"],
            "pair_max_ms": pair_stats["pair_max_ms"],
            "undo_mean_ms": pair_stats["undo_mean_ms"],
            "undo_median_ms": pair_stats["undo_median_ms"],
            "redo_mean_ms": pair_stats["redo_mean_ms"],
            "redo_median_ms": pair_stats["redo_median_ms"],
            "get_ctx_mean_ms": read_stats["mean_ms"],
        }
        rows.append(row)

        _print_summary(
            "true_depth_constant_final_surface",
            prior_actions=n,
            fill_avg_ms=f"{row['fill_avg_ms']:.3f}",
            pair_mean_ms=f"{row['pair_mean_ms']:.3f}",
            pair_median_ms=f"{row['pair_median_ms']:.3f}",
            pair_max_ms=f"{row['pair_max_ms']:.3f}",
            undo_mean_ms=f"{row['undo_mean_ms']:.3f}",
            undo_median_ms=f"{row['undo_median_ms']:.3f}",
            redo_mean_ms=f"{row['redo_mean_ms']:.3f}",
            redo_median_ms=f"{row['redo_median_ms']:.3f}",
            get_ctx_mean_ms=f"{row['get_ctx_mean_ms']:.3f}",
        )

    assert max(r["fill_avg_ms"] for r in rows) < 20.0
    assert max(r["pair_mean_ms"] for r in rows) < 250.0

    # This is intentionally stronger than the old combined-shape heuristic:
    # only prior tape depth grows here, while the final public surface stays tiny.
    smallest = rows[0]["pair_median_ms"]
    largest = rows[-1]["pair_median_ms"]
    assert largest < max(50.0, smallest * 4.0)


def test_plain_public_tape_combined_depth_and_current_form_size_with_slim_context():
    """
    Combined diagnostic, not a pure tape-depth diagnostic.

    This intentionally keeps the old one-frame-many-spans fixture because it is
    useful, but the interpretation is now explicit:

        n grows public tape depth AND current form datum/span count.

    If this grows while true_depth_constant_final_surface is flat, do not blame
    public tape depth. Look at current-form/current-frame/current-span context
    construction instead.
    """
    ns = [40, 80, 160]
    pairs = 20
    rows: List[Dict[str, Any]] = []

    for n in ns:
        step_name = f"test.diag.p.tape.slim.{n}"
        _register_step(
            step_name,
            _make_plain_p_multiframespec(
                app_form_id=f"diag.p.tape.slim.{n}",
                n=n,
                shape="one_frame_many_spans",
            ),
        )

        api = _api()
        sid, _ctx = _create(api, step_name, include_full_multiframespec_in_ctx=False)
        _final_ctx, fill_elapsed = _fill_one_span_per_datum_to_completion(api, sid, n=n)
        pair_stats = _measure_undo_redo_pairs(api, sid, pairs=pairs)
        read_stats = _measure_get_context_reads(api, sid, reads=pairs)

        _assert_no_q_lifecycle(api, sid)

        row = {
            "n": n,
            "fill_elapsed_s": fill_elapsed,
            "fill_avg_ms": fill_elapsed * 1000 / n,
            "pair_mean_ms": pair_stats["pair_mean_ms"],
            "pair_median_ms": pair_stats["pair_median_ms"],
            "pair_max_ms": pair_stats["pair_max_ms"],
            "undo_mean_ms": pair_stats["undo_mean_ms"],
            "undo_median_ms": pair_stats["undo_median_ms"],
            "redo_mean_ms": pair_stats["redo_mean_ms"],
            "redo_median_ms": pair_stats["redo_median_ms"],
            "get_ctx_mean_ms": read_stats["mean_ms"],
            "get_ctx_median_ms": read_stats["median_ms"],
        }
        rows.append(row)

        _print_summary(
            "combined_depth_and_form_size",
            n=n,
            fill_elapsed=f"{fill_elapsed:.6f}s",
            fill_avg_ms=f"{row['fill_avg_ms']:.3f}",
            pair_mean_ms=f"{row['pair_mean_ms']:.3f}",
            pair_median_ms=f"{row['pair_median_ms']:.3f}",
            pair_max_ms=f"{row['pair_max_ms']:.3f}",
            undo_mean_ms=f"{row['undo_mean_ms']:.3f}",
            undo_median_ms=f"{row['undo_median_ms']:.3f}",
            redo_mean_ms=f"{row['redo_mean_ms']:.3f}",
            redo_median_ms=f"{row['redo_median_ms']:.3f}",
            get_ctx_mean_ms=f"{row['get_ctx_mean_ms']:.3f}",
        )

    # Broad sanity: this diagnostic should not itself become painfully slow.
    assert max(r["fill_avg_ms"] for r in rows) < 20.0
    assert max(r["pair_mean_ms"] for r in rows) < 500.0

    # Heuristic warning guard: do not require perfect linearity on noisy CI,
    # but make catastrophic superlinearity visible as a failure. This remains
    # intentionally loose because this fixture grows current form size too.
    smallest = rows[0]["pair_mean_ms"]
    largest = rows[-1]["pair_mean_ms"]
    assert largest < max(250.0, smallest * 8.0)


def test_plain_public_tape_undo_redo_full_context_vs_slim_context():
    """
    If full ctx is much slower than slim ctx, optimize rendering/context payload
    construction first.

    This fixture uses the combined one-frame-many-spans shape on purpose: it is
    a current-form/context payload stressor, not a pure tape-depth test.
    """
    n = 160
    pairs = 20
    rows: List[Dict[str, Any]] = []

    for full in [False, True]:
        label = "full" if full else "slim"
        step_name = f"test.diag.p.tape.ctx.{label}"
        _register_step(
            step_name,
            _make_plain_p_multiframespec(
                app_form_id=f"diag.p.tape.ctx.{label}",
                n=n,
                shape="one_frame_many_spans",
            ),
        )

        api = _api()
        sid, _ctx = _create(api, step_name, include_full_multiframespec_in_ctx=full)
        _final_ctx, fill_elapsed = _fill_one_span_per_datum_to_completion(api, sid, n=n)
        pair_stats = _measure_undo_redo_pairs(api, sid, pairs=pairs)
        read_stats = _measure_get_context_reads(api, sid, reads=pairs)

        _assert_no_q_lifecycle(api, sid)

        row = {
            "label": label,
            "fill_avg_ms": fill_elapsed * 1000 / n,
            "pair_mean_ms": pair_stats["pair_mean_ms"],
            "pair_median_ms": pair_stats["pair_median_ms"],
            "undo_mean_ms": pair_stats["undo_mean_ms"],
            "undo_median_ms": pair_stats["undo_median_ms"],
            "redo_mean_ms": pair_stats["redo_mean_ms"],
            "redo_median_ms": pair_stats["redo_median_ms"],
            "get_ctx_mean_ms": read_stats["mean_ms"],
        }
        rows.append(row)

        _print_summary(
            "ctx_richness",
            mode=label,
            n=n,
            fill_avg_ms=f"{row['fill_avg_ms']:.3f}",
            pair_mean_ms=f"{row['pair_mean_ms']:.3f}",
            pair_median_ms=f"{row['pair_median_ms']:.3f}",
            undo_mean_ms=f"{row['undo_mean_ms']:.3f}",
            undo_median_ms=f"{row['undo_median_ms']:.3f}",
            redo_mean_ms=f"{row['redo_mean_ms']:.3f}",
            redo_median_ms=f"{row['redo_median_ms']:.3f}",
            get_ctx_mean_ms=f"{row['get_ctx_mean_ms']:.3f}",
        )

    slim = next(r for r in rows if r["label"] == "slim")
    full = next(r for r in rows if r["label"] == "full")

    assert slim["pair_mean_ms"] < 500.0
    assert full["pair_mean_ms"] < 750.0

    # Do not force full ctx to be close to slim ctx yet. This is diagnostic.
    # But if this ratio is huge in output, patch rendering/context construction.
    ratio = full["pair_mean_ms"] / max(0.001, slim["pair_mean_ms"])
    _print_summary("ctx_richness_ratio", full_over_slim_pair_mean=f"{ratio:.3f}")


def test_plain_public_tape_shape_matrix_one_frame_vs_many_frames():
    """
    Same number of public manual ticks, different current-form topology.

    If many_frames is much worse, look for frame scans or frame reconstruction.
    If one_frame_many_spans is much worse, look for current-span lookup inside a
    large frame.

    This is a current-form topology diagnostic, not a pure tape-depth diagnostic.
    """
    n = 140
    pairs = 18
    shapes = ["one_frame_many_spans", "many_frames_one_span_each"]
    rows: List[Dict[str, Any]] = []

    for shape in shapes:
        step_name = f"test.diag.p.tape.shape.{shape}"
        _register_step(
            step_name,
            _make_plain_p_multiframespec(
                app_form_id=f"diag.p.tape.shape.{shape}",
                n=n,
                shape=shape,
            ),
        )

        api = _api()
        sid, _ctx = _create(api, step_name, include_full_multiframespec_in_ctx=False)
        _final_ctx, fill_elapsed = _fill_one_span_per_datum_to_completion(api, sid, n=n)
        pair_stats = _measure_undo_redo_pairs(api, sid, pairs=pairs)

        _assert_no_q_lifecycle(api, sid)

        row = {
            "shape": shape,
            "fill_avg_ms": fill_elapsed * 1000 / n,
            "pair_mean_ms": pair_stats["pair_mean_ms"],
            "pair_median_ms": pair_stats["pair_median_ms"],
            "undo_mean_ms": pair_stats["undo_mean_ms"],
            "undo_median_ms": pair_stats["undo_median_ms"],
            "redo_mean_ms": pair_stats["redo_mean_ms"],
            "redo_median_ms": pair_stats["redo_median_ms"],
        }
        rows.append(row)

        _print_summary(
            "shape_matrix",
            shape=shape,
            n=n,
            fill_avg_ms=f"{row['fill_avg_ms']:.3f}",
            pair_mean_ms=f"{row['pair_mean_ms']:.3f}",
            pair_median_ms=f"{row['pair_median_ms']:.3f}",
            undo_mean_ms=f"{row['undo_mean_ms']:.3f}",
            undo_median_ms=f"{row['undo_median_ms']:.3f}",
            redo_mean_ms=f"{row['redo_mean_ms']:.3f}",
            redo_median_ms=f"{row['redo_median_ms']:.3f}",
        )

    assert max(r["fill_avg_ms"] for r in rows) < 20.0
    assert max(r["pair_mean_ms"] for r in rows) < 750.0


def test_plain_public_tape_current_form_size_big_span_vs_many_ticks():
    """
    Separates shallow wide current-surface size from combined deep/current-form
    size.

    one_frame_many_spans:
        n public actions, one pending datum after undo, but the current multiframespec
        still has n datums and n spans. This is combined tape depth + current
        form size, not pure tape depth.

    one_frame_one_big_span:
        one public action, n datums on current manual surface.

    If both are similar, the visible timing is probably current multiframespec/current
    surface construction rather than pure public tape-depth traversal.
    """
    n = 160
    pairs = 14

    # Combined: n actions and n datums/spans in the current multiframespec.
    deep_step = "test.diag.p.tape.surface.deep"
    _register_step(
        deep_step,
        _make_plain_p_multiframespec(
            app_form_id="diag.p.tape.surface.deep",
            n=n,
            shape="one_frame_many_spans",
        ),
    )
    deep_api = _api()
    deep_sid, _ctx = _create(deep_api, deep_step, include_full_multiframespec_in_ctx=False)
    _final_ctx, deep_fill_elapsed = _fill_one_span_per_datum_to_completion(deep_api, deep_sid, n=n)
    deep_pair = _measure_undo_redo_pairs(deep_api, deep_sid, pairs=pairs)
    _assert_no_q_lifecycle(deep_api, deep_sid)

    # Wide surface: one action, n datums on current manual surface.
    wide_step = "test.diag.p.tape.surface.wide"
    _register_step(
        wide_step,
        _make_plain_p_multiframespec(
            app_form_id="diag.p.tape.surface.wide",
            n=n,
            shape="one_frame_one_big_span",
        ),
    )
    wide_api = _api()
    wide_sid, _ctx = _create(wide_api, wide_step, include_full_multiframespec_in_ctx=False)
    _final_ctx, wide_fill_elapsed = _fill_big_span_to_completion(wide_api, wide_sid, n=n)
    wide_pair = _measure_undo_redo_pairs(wide_api, wide_sid, pairs=pairs)
    _assert_no_q_lifecycle(wide_api, wide_sid)

    _print_summary(
        "current_form_size",
        mode="combined_deep_tape_one_pending_field_large_form",
        n=n,
        fill_elapsed=f"{deep_fill_elapsed:.6f}s",
        pair_mean_ms=f"{deep_pair['pair_mean_ms']:.3f}",
        pair_median_ms=f"{deep_pair['pair_median_ms']:.3f}",
        undo_mean_ms=f"{deep_pair['undo_mean_ms']:.3f}",
        undo_median_ms=f"{deep_pair['undo_median_ms']:.3f}",
        redo_mean_ms=f"{deep_pair['redo_mean_ms']:.3f}",
        redo_median_ms=f"{deep_pair['redo_median_ms']:.3f}",
    )
    _print_summary(
        "current_form_size",
        mode="shallow_tape_wide_surface",
        n=n,
        fill_elapsed=f"{wide_fill_elapsed:.6f}s",
        pair_mean_ms=f"{wide_pair['pair_mean_ms']:.3f}",
        pair_median_ms=f"{wide_pair['pair_median_ms']:.3f}",
        undo_mean_ms=f"{wide_pair['undo_mean_ms']:.3f}",
        undo_median_ms=f"{wide_pair['undo_median_ms']:.3f}",
        redo_mean_ms=f"{wide_pair['redo_mean_ms']:.3f}",
        redo_median_ms=f"{wide_pair['redo_median_ms']:.3f}",
    )

    assert deep_pair["pair_mean_ms"] < 750.0
    assert wide_pair["pair_mean_ms"] < 750.0


def test_plain_public_tape_optional_context_flags_are_not_hidden_multipliers():
    """
    Optional context fields are useful for debugging, but they must not silently
    turn every public undo/redo into large global scans.

    This fixture uses the combined one-frame-many-spans shape on purpose: it is
    a current-form/context metadata stressor. If this is much slower than slim
    ctx, keep those flags opt-in and optimize their computation with bounded /
    indexed helpers.
    """
    n = 120
    pairs = 14

    step_name = "test.diag.p.tape.optional.ctx.flags"
    _register_step(
        step_name,
        _make_plain_p_multiframespec(
            app_form_id="diag.p.tape.optional.ctx.flags",
            n=n,
            shape="one_frame_many_spans",
        ),
    )

    api = _api()
    sid, _ctx = _create(
        api,
        step_name,
        include_full_multiframespec_in_ctx=False,
        include_forms_emitted_order_in_ctx=True,
        include_global_fill_keys_in_ctx=True,
        include_field_value_keys_in_ctx=True,
    )
    _final_ctx, fill_elapsed = _fill_one_span_per_datum_to_completion(api, sid, n=n)
    pair_stats = _measure_undo_redo_pairs(api, sid, pairs=pairs)
    read_stats = _measure_get_context_reads(api, sid, reads=pairs)

    _assert_no_q_lifecycle(api, sid)

    _print_summary(
        "optional_ctx_flags",
        n=n,
        fill_avg_ms=f"{fill_elapsed * 1000 / n:.3f}",
        pair_mean_ms=f"{pair_stats['pair_mean_ms']:.3f}",
        pair_median_ms=f"{pair_stats['pair_median_ms']:.3f}",
        undo_mean_ms=f"{pair_stats['undo_mean_ms']:.3f}",
        undo_median_ms=f"{pair_stats['undo_median_ms']:.3f}",
        redo_mean_ms=f"{pair_stats['redo_mean_ms']:.3f}",
        redo_median_ms=f"{pair_stats['redo_median_ms']:.3f}",
        get_ctx_mean_ms=f"{read_stats['mean_ms']:.3f}",
    )

    assert pair_stats["pair_mean_ms"] < 1000.0


def _exact_pending_field_ids_from_ctx(ctx: Mapping[str, Any]) -> List[str]:
    out: List[str] = []
    for item in list(ctx.get("datum_widgets_on_this_span") or []):
        if isinstance(item, Mapping):
            fid = (
                item.get("field_id")
                or item.get("id")
                or item.get("name")
                or item.get("datum_id")
            )
            if fid is not None:
                out.append(str(fid))
        else:
            out.append(str(item))
    return out


def _plain_p_fill_value(index: int, *, prefix: str) -> Dict[str, Any]:
    return {"value0": f"{prefix}-{index}"}


def test_plain_public_tape_redo_branch_correctness_still_holds_under_diagnostic_depth():
    """
    Correctness guard while profiling: after undoing several P actions, taking a
    new step must clear the old redo branch, and the final fills must reflect the
    branch actually chosen.
    """
    n = 30
    step_name = "test.diag.p.tape.branch.correctness"
    _register_step(
        step_name,
        _make_plain_p_multiframespec(
            app_form_id="diag.p.tape.branch.correctness",
            n=n,
            shape="one_frame_many_spans",
        ),
    )

    api = _api()
    sid, _ctx = _create(api, step_name, include_full_multiframespec_in_ctx=False)

    ctx, _fill_elapsed = _fill_one_span_per_datum_to_completion(api, sid, n=n)
    assert ctx["kind"] == "ATCOMPLETION"

    for _ in range(5):
        ctx = api.undo_last_step(sid)
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    pending_ids = _exact_pending_field_ids_from_ctx(ctx)
    assert len(pending_ids) == 1
    branch_datum = pending_ids[0]

    assert branch_datum.startswith("D")
    branch_index = int(branch_datum[1:])
    assert n - 5 <= branch_index < n

    ctx = api.step_session(
        sid,
        fill={branch_datum: _plain_p_fill_value(branch_index, prefix="new")},
    )
    assert not ctx.get("last_error"), ctx.get("last_error")
    assert ctx["kind"] in {"MANUALFILLNEEDEDSTEP", "ATCOMPLETION"}

    # Old redo branch must be gone after taking a new user step.
    try:
        api.redo_last_step(sid)
    except Exception:
        pass
    else:
        raise AssertionError("redo should be unavailable after new branch fill")

    for i in range(branch_index + 1, n):
        ctx = api.step_session(
            sid,
            fill={f"D{i}": _plain_p_fill_value(i, prefix="new")},
        )
        assert not ctx.get("last_error"), ctx.get("last_error")

    assert ctx["kind"] == "ATCOMPLETION"

    fills = api._get(sid).state.get("form_fills", {})

    for i in range(branch_index):
        assert fills[f"D{i}"]["value0"] == f"v{i}-0"

    assert fills[branch_datum]["value0"] == f"new-{branch_index}"

    for i in range(branch_index + 1, n):
        assert fills[f"D{i}"]["value0"] == f"new-{i}"

    _assert_no_q_lifecycle(api, sid)