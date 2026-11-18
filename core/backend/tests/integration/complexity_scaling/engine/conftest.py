from __future__ import annotations

"""
Complexity-suite wall-clock guardrails.

These budgets are intentionally not exact micro-benchmarks. They are coarse,
front-facing regression sentinels for accidental complexity explosions.

Policy:
    - Calibrated from a clean optimized local run.
    - Adds small fixed wall-clock jitter tolerances at enforcement time.
    - Does not use broad multiplicative escape hatches.
    - Keeps the aggregate suite budget hard.
    - Fails only for configured complexity sheets.
    - Reports the slowest individual tests to make regressions obvious.

This should catch:
    - accidental quadratic scans,
    - accidental payload materialization,
    - hidden snapshot/index bloat,
    - broad reprocessing of history,
    - manual IO scaling walls.

It should not catch:
    - tiny normal wall-clock jitter,
    - plugin/setup noise,
    - harmless sub-second variation,
    - small host/load differences between clean local and CI-style runs.
"""

import time
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Tuple

import pytest


# ---------------------------------------------------------------------------
# Aggregate suite budget
# ---------------------------------------------------------------------------

# Keep this hard. Unlike an individual sheet/test, the configured complexity
# total already averages together host jitter across many tests. If this trips,
# the suite as a whole has become materially more expensive.
COMPLEXITY_SUITE_BUDGET_SECONDS = 85.0


# ---------------------------------------------------------------------------
# Fixed wall-clock jitter allowances
# ---------------------------------------------------------------------------

# Baseline budgets below remain the calibrated performance contract.
#
# These tolerances exist only at enforcement time so that minor wall-clock
# variance does not force us to continuously rewrite the calibrated baselines.
#
# Example:
#     sheet baseline 10.0s -> enforcement ceiling 11.5s
#     test baseline   5.0s -> enforcement ceiling  5.5s
#
# These are deliberately fixed additive allowances, not percentages.
COMPLEXITY_SHEET_JITTER_SECONDS = 1.5
COMPLEXITY_TEST_JITTER_SECONDS = 0.5


# ---------------------------------------------------------------------------
# Per-sheet calibrated baselines
# ---------------------------------------------------------------------------

COMPLEXITY_SHEET_BUDGETS_SECONDS: Dict[str, float] = {
    # App fn/session metadata writes.
    # Observed optimized local profile: ~1.5s.
    "test_complexity_appfn_writes_session_metadata.py": 3.0,

    # Datum lifecycle Q/P behavior, reexplode, undo/redo, proc_notes windows.
    # Observed optimized local profile: ~5.5s-6.0s.
    "test_complexity_datum_lifecycle_q.py": 10.0,

    # Main engine complexity contract: runtime index, manual IO, snapshots,
    # ctx surfaces, adversarial mixed sessions.
    # Observed optimized local profile: ~14s-16s.
    "test_complexity_engine.py": 40.0,

    # Public tape undo/redo diagnostics. This is intentionally heavier because
    # it probes depth/form-size/context-shape matrices.
    # Observed optimized local profile: ~7.8s-8.2s.
    "test_complexity_plain_public_tape_undo_redo_scaling_diagnostics.py": 11.0,

    # Runtime write DB/query/index tests.
    # Observed optimized local profile: ~8s-9s.
    "test_complexity_runtime_DB_queries.py": 18.0,

    # Exploded-world datum runtime bounds.
    # Observed optimized local profile: ~1.5s-2.0s.
    "test_exploded_world_datum_runtime_bounds_e2e.py": 4.0,

    # Exploded-world scripted program runner.
    # Observed optimized local profile: ~0.8s-1.0s.
    "test_exploded_world_program_scripted_run_e2e.py": 2.5,

    # Exploded-world tape operations.
    # Observed optimized local profile: ~1.5s-2.0s.
    "test_exploded_world_tape_operations_robustness_and_scalability_e2e.py": 4.0,

    # Session persistence / snapshot / undo payload finalization.
    # Observed optimized local profile: ~0.1s-0.2s.
    # Budget leaves CI room while still catching accidental full-history payloads.
    "test_data_weight_session_persistence_lean_finalization.py": 1.5,

    # Public bounded facade over S/G/G* traces, writes, caps, giant final tables.
    # Observed optimized local profile: ~8s.
    # This includes giant whole-program reads and explicit expert full-table export.
    "test_pkg_facade_data_and_time_complexity.py": 11.0,

    # Public scripting facade: headless reports, scripted manual holes, capped
    # post-script queries, and explicit expert full-table export.
    # Observed optimized local profile: ~7.5s-8s.
    "test_pkg_facade_scripting_data_and_time_complexity.py": 11.0,

    # Role modulation security + complexity proof:
    # exact role membership, active-span-local target derivation, bounded
    # canonical mismatch surfaces, replacement-layer redaction, and server-side
    # mismatch write blocking.
    # Observed optimized local profile: 18 passed in 5.30s.
    # Slowest individual tests: ~1.27s, ~0.98s, ~0.95s.
    "test_role_modulation_complexity_security.py": 7.0,
}


# ---------------------------------------------------------------------------
# Per-test calibrated baselines
# ---------------------------------------------------------------------------

# Optional hard per-test smoke baseline. Sheet budgets remain the primary
# contract. The fixed test jitter allowance is applied only when enforcing.
DEFAULT_COMPLEXITY_TEST_BUDGET_SECONDS = 5.0


# Known intentionally-heavy individual tests may receive explicit baselines.
COMPLEXITY_TEST_BUDGETS_SECONDS: Dict[str, float] = {
    "test_deep_undo_removal_does_not_show_quadratic_wall_after_position_sidecar[1000-10000]": 5.0,
    "test_adversarial_super_long_program_many_small_writes_zips_without_quadratic_wall": 8.0,
    "test_plain_public_tape_undo_redo_full_context_vs_slim_context": 4.0,
    "test_q_reexplode_large_proc_notes_is_state_only_not_runtime_index_or_query_payload": 4.0,
    "test_selective_exact_lookup_uses_index_candidates_not_full_order_scan": 5.0,
    "test_adversarial_every_axis_mixed_end_to_end_contract": 3.0,
    "test_plain_public_tape_shape_matrix_one_frame_vs_many_frames": 3.0,
    "test_plain_public_tape_combined_depth_and_current_form_size_with_slim_context": 3.0,
    "test_plain_public_tape_current_form_size_big_span_vs_many_ticks": 3.0,
    "test_result_size_scales_with_max_results_not_table_size_for_selective_index_query": 2.5,

    # Public facade/script facade heavy-but-legitimate exports and giant traces.
    "test_script_expert_cap_can_export_whole_final_datum_table_after_large_manual_script": 4.5,
    "test_giant_whole_program_final_trace_read_is_clean_capped_and_fast_from_public_api": 3.5,
    "test_giant_whole_program_small_final_trace_query_slope_is_healthy_from_public_api": 3.0,
    "test_expert_caps_can_return_all_final_datum_states_for_very_large_program": 3.0,
    "test_script_fixed_cap_queries_stay_small_as_scripted_program_size_grows": 3.0,
}


def pytest_configure(config: pytest.Config) -> None:
    config._complexity_suite_started_at = time.perf_counter()
    config._complexity_sheet_durations = defaultdict(float)
    config._complexity_test_durations = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item):
    started_at = time.perf_counter()
    yield
    elapsed = time.perf_counter() - started_at

    filename = Path(str(item.fspath)).name

    if filename not in COMPLEXITY_SHEET_BUDGETS_SECONDS:
        return

    item.config._complexity_sheet_durations[filename] += elapsed
    item.config._complexity_test_durations.append((elapsed, item.nodeid))

    baseline_budget = COMPLEXITY_TEST_BUDGETS_SECONDS.get(
        item.name,
        DEFAULT_COMPLEXITY_TEST_BUDGET_SECONDS,
    )
    enforcement_ceiling = baseline_budget + COMPLEXITY_TEST_JITTER_SECONDS

    if elapsed > enforcement_ceiling:
        pytest.fail(
            "complexity test exceeded per-test runtime budget: "
            f"{item.nodeid} took {elapsed:.3f}s > "
            f"{enforcement_ceiling:.3f}s enforcement ceiling "
            f"(baseline={baseline_budget:.3f}s, "
            f"jitter={COMPLEXITY_TEST_JITTER_SECONDS:.3f}s)"
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config

    sheet_durations: DefaultDict[str, float] = (
        config._complexity_sheet_durations
    )
    test_durations: List[Tuple[float, str]] = (
        config._complexity_test_durations
    )

    suite_elapsed = time.perf_counter() - config._complexity_suite_started_at
    configured_total = sum(sheet_durations.values())

    failures: List[str] = []

    # Aggregate suite budget intentionally receives no jitter allowance.
    if configured_total > COMPLEXITY_SUITE_BUDGET_SECONDS:
        failures.append(
            "complexity suite exceeded runtime budget: "
            f"{configured_total:.3f}s > "
            f"{COMPLEXITY_SUITE_BUDGET_SECONDS:.3f}s "
            "(configured complexity sheets only; aggregate budget is hard)"
        )

    for filename, baseline_budget in COMPLEXITY_SHEET_BUDGETS_SECONDS.items():
        elapsed = sheet_durations.get(filename, 0.0)
        enforcement_ceiling = (
            baseline_budget + COMPLEXITY_SHEET_JITTER_SECONDS
        )

        if elapsed > enforcement_ceiling:
            failures.append(
                f"{filename} exceeded sheet runtime budget: "
                f"{elapsed:.3f}s > "
                f"{enforcement_ceiling:.3f}s enforcement ceiling "
                f"(baseline={baseline_budget:.3f}s, "
                f"jitter={COMPLEXITY_SHEET_JITTER_SECONDS:.3f}s)"
            )

    if not failures:
        return

    slowest = sorted(test_durations, reverse=True)[:10]
    slowest_lines = "\n".join(
        f"    {elapsed:.3f}s  {nodeid}"
        for elapsed, nodeid in slowest
    )

    message = "\n".join(
        [
            "",
            "Complexity runtime budget failure.",
            "",
            *failures,
            "",
            (
                "Observed configured complexity-sheet total: "
                f"{configured_total:.3f}s"
            ),
            (
                "Configured complexity-suite hard budget: "
                f"{COMPLEXITY_SUITE_BUDGET_SECONDS:.3f}s"
            ),
            f"Observed pytest session wall time: {suite_elapsed:.3f}s",
            "",
            (
                "Enforcement jitter allowances: "
                f"sheet=+{COMPLEXITY_SHEET_JITTER_SECONDS:.3f}s, "
                f"test=+{COMPLEXITY_TEST_JITTER_SECONDS:.3f}s"
            ),
            "",
            "Slowest configured complexity tests:",
            slowest_lines or "    <none recorded>",
            "",
        ]
    )

    raise pytest.UsageError(message)