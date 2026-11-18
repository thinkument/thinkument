from __future__ import annotations

"""
Authoring complexity-scaling timing guardrails.

This conftest is intentionally scoped to:

    tests/unit/sessions/complexity_scaling/

It covers exactly these canonical sheets:

    test_complexity_scaling_thinkcontinuitykernelTM.py
    test_complexity_scaling_thinkwidgetTM.py
    test_complexity_chainreactiontm_chain_reaction_e2e.py

Purpose
-------

The tests themselves prove structural complexity laws such as:

    - touched-datum-only execution;
    - one lifecycle write per actual transition;
    - history query deduplication;
    - bounded history, receipts, rows, indexes, and persistence tails;
    - no accidental large-value materialization;
    - bounded concurrent capture;
    - chain scheduling independent from unrelated roles;
    - current-form reads independent from unrelated prior forms.

This conftest adds coarse wall-clock regression sentinels. It is deliberately
not a microbenchmark framework.

Timing policy
-------------

Only pytest call-phase time for the configured sheets is charged.

The guardrails are layered:

    1. per-test budget;
    2. per-sheet aggregate budget;
    3. aggregate configured-suite budget.

The budgets use fixed additive tolerance. They are not calculated from the
current run and must not automatically expand after a regression.

Environment overrides exist for materially slower CI environments, but changing
them should be an explicit infrastructure decision rather than a routine way to
make regressions pass.

Optional stress modes
---------------------

Think continuity kernel:

    THINK_KERNEL_SCALE_CRAZY=1
    THINK_KERNEL_USER_CRAZY=1

ThinkWidget class adapter:

    APP_TABLE_CLASS_ADAPTER_COMPLEXITY_CRAZY=1

Optional stress tests remain skipped by their test modules unless the matching
environment flag is enabled. When enabled, this conftest selects separate,
larger stress budgets.

Useful overrides
----------------

Whole configured suite:

    AUTHORING_COMPLEXITY_SUITE_BUDGET_SECONDS

Individual sheets:

    AUTHORING_KERNEL_SHEET_BUDGET_SECONDS
    AUTHORING_THINKWIDGET_SHEET_BUDGET_SECONDS
    AUTHORING_FUNKTM_SHEET_BUDGET_SECONDS

Default individual test:

    AUTHORING_COMPLEXITY_TEST_BUDGET_SECONDS

Optional stress:

    AUTHORING_KERNEL_CRAZY_SHEET_BUDGET_SECONDS
    AUTHORING_KERNEL_USER_CRAZY_SHEET_BUDGET_SECONDS
    AUTHORING_THINKWIDGET_CRAZY_SHEET_BUDGET_SECONDS

Diagnostics:

    AUTHORING_COMPLEXITY_TOP_SLOWEST
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Mapping, MutableMapping, Tuple

import pytest


# =============================================================================
# Canonical configured sheets
# =============================================================================

KERNEL_SHEET = "test_complexity_scaling_thinkcontinuitykernelTM.py"
THINKWIDGET_SHEET = "test_complexity_scaling_thinkwidgetTM.py"
FUNKTM_SHEET = "test_complexity_chainreactiontm_chain_reaction_e2e.py"

CONFIGURED_COMPLEXITY_SHEETS = frozenset(
    {
        KERNEL_SHEET,
        THINKWIDGET_SHEET,
        FUNKTM_SHEET,
    }
)


# =============================================================================
# Environment parsing
# =============================================================================

def _env_flag(name: str) -> bool:
    return os.environ.get(name, "0").strip() == "1"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return float(default)

    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise pytest.UsageError(
            f"{name} must be a positive finite number; received {raw!r}"
        ) from exc

    if value <= 0 or value == float("inf") or value != value:
        raise pytest.UsageError(
            f"{name} must be a positive finite number; received {raw!r}"
        )

    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return int(default)

    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise pytest.UsageError(
            f"{name} must be a positive integer; received {raw!r}"
        ) from exc

    if value <= 0:
        raise pytest.UsageError(
            f"{name} must be a positive integer; received {raw!r}"
        )

    return value


RUN_KERNEL_SCALE_CRAZY = _env_flag("THINK_KERNEL_SCALE_CRAZY")
RUN_KERNEL_USER_CRAZY = _env_flag("THINK_KERNEL_USER_CRAZY")
RUN_THINKWIDGET_CRAZY = _env_flag(
    "APP_TABLE_CLASS_ADAPTER_COMPLEXITY_CRAZY"
)

TOP_SLOWEST_COUNT = _env_int(
    "AUTHORING_COMPLEXITY_TOP_SLOWEST",
    15,
)


# =============================================================================
# Budget model
# =============================================================================

@dataclass(frozen=True)
class SheetBudget:
    filename: str
    seconds: float
    marker: str


def _kernel_sheet_budget_seconds() -> float:
    if RUN_KERNEL_USER_CRAZY:
        return _env_float(
            "AUTHORING_KERNEL_USER_CRAZY_SHEET_BUDGET_SECONDS",
            90.0,
        )

    if RUN_KERNEL_SCALE_CRAZY:
        return _env_float(
            "AUTHORING_KERNEL_CRAZY_SHEET_BUDGET_SECONDS",
            60.0,
        )

    return _env_float(
        "AUTHORING_KERNEL_SHEET_BUDGET_SECONDS",
        10.0,
    )


def _thinkwidget_sheet_budget_seconds() -> float:
    if RUN_THINKWIDGET_CRAZY:
        return _env_float(
            "AUTHORING_THINKWIDGET_CRAZY_SHEET_BUDGET_SECONDS",
            60.0,
        )

    return _env_float(
        "AUTHORING_THINKWIDGET_SHEET_BUDGET_SECONDS",
        12.0,
    )


SHEET_BUDGETS: Mapping[str, SheetBudget] = {
    KERNEL_SHEET: SheetBudget(
        filename=KERNEL_SHEET,
        seconds=_kernel_sheet_budget_seconds(),
        marker="thinkcontinuitykernel_complexity",
    ),
    THINKWIDGET_SHEET: SheetBudget(
        filename=THINKWIDGET_SHEET,
        seconds=_thinkwidget_sheet_budget_seconds(),
        marker="thinkwidget_complexity",
    ),
    FUNKTM_SHEET: SheetBudget(
        filename=FUNKTM_SHEET,
        seconds=_env_float(
            "AUTHORING_FUNKTM_SHEET_BUDGET_SECONDS",
            6.0,
        ),
        marker="chainreactiontm_complexity",
    ),
}

DEFAULT_TEST_BUDGET_SECONDS = _env_float(
    "AUTHORING_COMPLEXITY_TEST_BUDGET_SECONDS",
    3.0,
)

DEFAULT_SUITE_BUDGET_SECONDS = (
    sum(sheet.seconds for sheet in SHEET_BUDGETS.values()) + 4.0
)

CONFIGURED_SUITE_BUDGET_SECONDS = _env_float(
    "AUTHORING_COMPLEXITY_SUITE_BUDGET_SECONDS",
    DEFAULT_SUITE_BUDGET_SECONDS,
)


# =============================================================================
# Explicit per-test budgets
# =============================================================================

# These exceptions document tests that intentionally execute materially larger
# shapes. Ordinary tests use DEFAULT_TEST_BUDGET_SECONDS.
#
# The optional crazy-test ceilings are relevant only when those tests are
# enabled by their own module-level skip conditions.
PER_TEST_BUDGETS_SECONDS: Mapping[str, float] = {
    # ---------------------------------------------------------------------
    # Think continuity kernel
    # ---------------------------------------------------------------------
    "test_kernel_runtime_many_sequential_k_steps_scales_with_executed_steps_not_history_scan": 4.0,
    "test_kernel_many_datums_in_one_k_step_scales_with_touched_datums_and_one_write_each": 4.0,
    "test_kernel_many_datums_share_one_history_query_without_multiplying_queries": 4.0,
    "test_kernel_many_history_fanins_into_one_datum_queries_only_unique_prior_facts": 4.0,
    "test_kernel_large_source_datum_write_does_not_leak_into_history_when_include_value_false": 4.0,
    "test_kernel_include_values_true_is_explicit_materialization_boundary": 4.0,
    "test_kernel_higher_language_public_facade_many_steps_many_datums_e2e_stays_machine_code_only": 4.0,
    "test_kernel_mixed_cross_axis_default_surfaces_do_not_duplicate_large_values": 5.0,
    "test_kernel_default_manual_io_cap_rejects_multi_page_giant_submit_before_state_or_index_growth": 4.0,
    "test_kernel_user_authored_compute_cost_is_isolated_from_index_and_history_surfaces": 5.0,
    "test_kernel_large_authored_source_state_opt_in_grows_current_state_not_runtime_index_or_default_query": 5.0,
    "test_kernel_explicit_include_values_export_opt_in_scales_with_requested_rows_and_value_size": 5.0,
    "test_kernel_many_duplicate_history_aliases_scale_as_alias_fanin_but_still_one_query": 4.0,
    "test_kernel_user_authored_archival_of_hydrated_history_is_explicit_state_growth_not_index_growth": 5.0,
    "test_kernel_optional_crazy_many_steps_many_datums_many_histories": _env_float(
        "AUTHORING_KERNEL_CRAZY_TEST_BUDGET_SECONDS",
        45.0,
    ),
    "test_kernel_optional_user_crazy_compute_values_fanin_and_archival": _env_float(
        "AUTHORING_KERNEL_USER_CRAZY_TEST_BUDGET_SECONDS",
        70.0,
    ),

    # ---------------------------------------------------------------------
    # ThinkWidget class adapter
    # ---------------------------------------------------------------------
    "test_adapter_complexity_many_done_datums_are_linear_and_one_write_per_touched_q": 5.0,
    "test_adapter_complexity_wide_span_one_touched_datum_does_not_scan_or_eval_siblings": 5.0,
    "test_adapter_complexity_large_self_state_is_not_duplicated_into_runtime_index_or_query_preview": 6.0,
    "test_adapter_complexity_reexplode_then_done_is_two_writes_per_touched_datum_only": 6.0,
    "test_adapter_complexity_current_form_reads_do_not_scale_with_prior_unrelated_forms": 5.0,
    "test_adapter_complexity_undo_redo_replays_only_public_tape_action": 6.0,
    "test_adapter_complexity_crazy_all_touched_reexplode_once_diagnostic": _env_float(
        "AUTHORING_THINKWIDGET_CRAZY_TEST_BUDGET_SECONDS",
        50.0,
    ),

    # ---------------------------------------------------------------------
    # chainreactionTM
    # ---------------------------------------------------------------------
    "test_history_tail_and_size_caps_bound_large_prior_values": 4.0,
    "test_recent_history_window_prefers_latest_writes_under_long_sessions": 4.0,
    "test_receipt_dispatch_rows_are_bounded_even_for_many_generated_fills": 4.0,
    "test_grouped_roles_are_deterministic_and_do_not_scan_unrelated_later_roles": 3.0,

}


# =============================================================================
# Runtime bookkeeping
# =============================================================================

@dataclass(frozen=True)
class TimedTest:
    elapsed: float
    nodeid: str
    filename: str
    test_name: str
    budget: float


def _filename_for_item(item: pytest.Item) -> str:
    return Path(str(item.fspath)).name


def _is_configured_complexity_item(item: pytest.Item) -> bool:
    return _filename_for_item(item) in CONFIGURED_COMPLEXITY_SHEETS


def _test_budget_for(item: pytest.Item) -> float:
    return float(
        PER_TEST_BUDGETS_SECONDS.get(
            item.name,
            DEFAULT_TEST_BUDGET_SECONDS,
        )
    )


def _format_seconds(value: float) -> str:
    return f"{float(value):.3f}s"


def _timing_state(
    config: pytest.Config,
) -> tuple[
    DefaultDict[str, float],
    List[TimedTest],
]:
    sheet_durations = getattr(
        config,
        "_authoring_complexity_sheet_durations",
        None,
    )
    timed_tests = getattr(
        config,
        "_authoring_complexity_timed_tests",
        None,
    )

    if not isinstance(sheet_durations, defaultdict):
        sheet_durations = defaultdict(float)
        config._authoring_complexity_sheet_durations = sheet_durations

    if not isinstance(timed_tests, list):
        timed_tests = []
        config._authoring_complexity_timed_tests = timed_tests

    return sheet_durations, timed_tests


# =============================================================================
# Pytest registration
# =============================================================================

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "authoring_complexity: authoring complexity-scaling contract test.",
    )
    config.addinivalue_line(
        "markers",
        "thinkcontinuitykernel_complexity: ThinkContinuityKernelTM complexity test.",
    )
    config.addinivalue_line(
        "markers",
        "thinkwidget_complexity: ThinkWidgetTM class-adapter complexity test.",
    )
    config.addinivalue_line(
        "markers",
        "chainreactiontm_complexity: chainreactionTM chain-reaction complexity test.",
    )
    config.addinivalue_line(
        "markers",
        "authoring_complexity_optional_stress: optional large stress diagnostic.",
    )

    config._authoring_complexity_started_at = time.perf_counter()
    config._authoring_complexity_sheet_durations = defaultdict(float)
    config._authoring_complexity_timed_tests = []


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config

    optional_stress_tests = {
        "test_kernel_optional_crazy_many_steps_many_datums_many_histories",
        "test_kernel_optional_user_crazy_compute_values_fanin_and_archival",
        "test_adapter_complexity_crazy_all_touched_reexplode_once_diagnostic",
    }

    for item in items:
        filename = _filename_for_item(item)
        sheet = SHEET_BUDGETS.get(filename)
        if sheet is None:
            continue

        item.add_marker(pytest.mark.authoring_complexity)
        item.add_marker(getattr(pytest.mark, sheet.marker))

        if item.name in optional_stress_tests:
            item.add_marker(pytest.mark.authoring_complexity_optional_stress)


# =============================================================================
# Call-phase timing
# =============================================================================

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item):
    if not _is_configured_complexity_item(item):
        yield
        return

    started_at = time.perf_counter()
    outcome = yield
    elapsed = time.perf_counter() - started_at

    filename = _filename_for_item(item)
    budget = _test_budget_for(item)

    sheet_durations, timed_tests = _timing_state(item.config)
    sheet_durations[filename] += elapsed
    timed_tests.append(
        TimedTest(
            elapsed=elapsed,
            nodeid=item.nodeid,
            filename=filename,
            test_name=item.name,
            budget=budget,
        )
    )

    # Preserve the test's original exception as the primary failure. Timing
    # enforcement is applied only when the call itself otherwise succeeded.
    if outcome.excinfo is not None:
        return

    if elapsed > budget:
        pytest.fail(
            "authoring complexity test exceeded its call-phase runtime budget:\n"
            f"    test:    {item.nodeid}\n"
            f"    elapsed: {_format_seconds(elapsed)}\n"
            f"    budget:  {_format_seconds(budget)}\n"
            "\n"
            "This timing limit is a regression sentinel. Confirm the test's "
            "structural complexity assertions first; do not raise the budget "
            "without a clean baseline showing that the intended workload "
            "itself changed.",
            pytrace=False,
        )


# =============================================================================
# Reporting helpers
# =============================================================================

def _sheet_summary_lines(
    sheet_durations: Mapping[str, float],
) -> list[str]:
    lines: list[str] = []

    for filename in sorted(CONFIGURED_COMPLEXITY_SHEETS):
        observed = float(sheet_durations.get(filename, 0.0))
        budget = SHEET_BUDGETS[filename].seconds
        lines.append(
            "    "
            f"{filename}: "
            f"{_format_seconds(observed)} / {_format_seconds(budget)}"
        )

    return lines


def _slowest_summary_lines(
    timed_tests: List[TimedTest],
) -> list[str]:
    slowest = sorted(
        timed_tests,
        key=lambda row: row.elapsed,
        reverse=True,
    )[:TOP_SLOWEST_COUNT]

    if not slowest:
        return ["    <none recorded>"]

    return [
        "    "
        f"{_format_seconds(row.elapsed)} / "
        f"{_format_seconds(row.budget)}  "
        f"{row.nodeid}"
        for row in slowest
    ]


def _build_summary(
    *,
    sheet_durations: Mapping[str, float],
    timed_tests: List[TimedTest],
    session_wall_time: float,
) -> str:
    configured_total = sum(float(v) for v in sheet_durations.values())

    return "\n".join(
        [
            "",
            "Authoring complexity timing summary",
            "===================================",
            "",
            "Configured sheet call-phase elapsed / budget:",
            *_sheet_summary_lines(sheet_durations),
            "",
            "Configured total:",
            "    "
            f"{_format_seconds(configured_total)} / "
            f"{_format_seconds(CONFIGURED_SUITE_BUDGET_SECONDS)}",
            "",
            "Whole pytest session wall time, informational only:",
            f"    {_format_seconds(session_wall_time)}",
            "",
            "Optional stress modes:",
            f"    THINK_KERNEL_SCALE_CRAZY={int(RUN_KERNEL_SCALE_CRAZY)}",
            f"    THINK_KERNEL_USER_CRAZY={int(RUN_KERNEL_USER_CRAZY)}",
            f"    APP_TABLE_CLASS_ADAPTER_COMPLEXITY_CRAZY={int(RUN_THINKWIDGET_CRAZY)}",
            "",
            f"Slowest configured tests, top {TOP_SLOWEST_COUNT}:",
            *_slowest_summary_lines(timed_tests),
            "",
        ]
    )


def _timing_failures(
    *,
    sheet_durations: Mapping[str, float],
) -> list[str]:
    failures: list[str] = []

    configured_total = sum(float(v) for v in sheet_durations.values())
    if configured_total > CONFIGURED_SUITE_BUDGET_SECONDS:
        failures.append(
            "configured authoring complexity total exceeded budget: "
            f"{_format_seconds(configured_total)} > "
            f"{_format_seconds(CONFIGURED_SUITE_BUDGET_SECONDS)}"
        )

    for filename, sheet in sorted(SHEET_BUDGETS.items()):
        observed = float(sheet_durations.get(filename, 0.0))
        if observed > sheet.seconds:
            failures.append(
                f"{filename} exceeded sheet budget: "
                f"{_format_seconds(observed)} > "
                f"{_format_seconds(sheet.seconds)}"
            )

    return failures


# =============================================================================
# Session-level enforcement
# =============================================================================

def pytest_sessionfinish(
    session: pytest.Session,
    exitstatus: int,
) -> None:
    config = session.config
    sheet_durations, timed_tests = _timing_state(config)

    if not timed_tests:
        return

    started_at = getattr(
        config,
        "_authoring_complexity_started_at",
        None,
    )
    session_wall_time = (
        time.perf_counter() - float(started_at)
        if isinstance(started_at, (int, float))
        else 0.0
    )

    summary = _build_summary(
        sheet_durations=sheet_durations,
        timed_tests=timed_tests,
        session_wall_time=session_wall_time,
    )

    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(summary)

    # Do not obscure an existing collection, test, interruption, or internal
    # failure with a secondary aggregate timing error. Individual timing
    # overruns have already failed at call time when the call otherwise passed.
    if exitstatus != pytest.ExitCode.OK:
        return

    failures = _timing_failures(
        sheet_durations=sheet_durations,
    )
    if not failures:
        return

    message = "\n".join(
        [
            "",
            "Authoring complexity aggregate runtime budget failure.",
            "",
            *[f"- {failure}" for failure in failures],
            summary,
            "The structural assertions remain the primary complexity proof. "
            "Investigate changed scans, materialization, history growth, "
            "callback work, locking, or persistence work before changing a "
            "budget.",
        ]
    )

    raise pytest.UsageError(message)