from __future__ import annotations

"""Run every dry-run catalog through the current base-facade strategy.

Performance contract
--------------------
The base-facade strategy is the low-overhead reference execution lens.  It
runs the highest facade directly in-process, so it should not acquire costs
belonging to higher abstraction layers such as HTTP transport, server
lifecycle, serialization, or transport polling.
"""

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.base_facade_backend_only import (
    BaseFacadeBackendOnlyDryRunStrategy,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.dry_run_cases import DRY_RUN_CASES
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.dry_run_cases_funked import (
    FUNKED_DRY_RUN_CASES,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.dry_run_performance_contract_v1 import (
    DryRunPerformanceContractV1,
    assert_performance_contract_v1,
    timed_v1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.funked_live_session_dry_run_v1 import (
    assert_funked_dry_run_suite_v1,
    run_funked_dry_run_suite_v1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.live_session_dry_run_v1 import (
    assert_dry_run_suite_v1,
    run_dry_run_suite_v1,
)


_BASE_PERFORMANCE = DryRunPerformanceContractV1(
    fixed_allowance_seconds=0.20,
    max_seconds_per_case=0.30,
    efficiency_reason=(
        "The base-facade strategy is the lowest-overhead reference strategy. "
        "It drives the highest facade directly in-process and should not "
        "acquire transport, server-lifecycle, serialization, polling, or "
        "other adapter-layer costs."
    ),
)


def test_all_dry_run_flows_through_base_facade_strategy() -> None:
    strategy = BaseFacadeBackendOnlyDryRunStrategy()
    register_dry_run_lib_widgets_flows_v1()

    def run_catalogs():
        ordinary = run_dry_run_suite_v1(
            DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="app-for-fundamentals-dry-run",
        )
        funked = run_funked_dry_run_suite_v1(
            FUNKED_DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="app-for-fundamentals-p12-e2e",
        )
        return ordinary, funked

    timed = timed_v1(run_catalogs)
    ordinary, funked = timed.value

    assert_dry_run_suite_v1(ordinary)
    assert_funked_dry_run_suite_v1(funked)
    assert len(ordinary.cases) == len(DRY_RUN_CASES)
    assert len(funked.cases) == len(FUNKED_DRY_RUN_CASES)

    assert_performance_contract_v1(
        strategy_name=strategy.strategy_name,
        elapsed_seconds=timed.elapsed_seconds,
        case_count=len(DRY_RUN_CASES) + len(FUNKED_DRY_RUN_CASES),
        contract=_BASE_PERFORMANCE,
    )


__all__ = ["DRY_RUN_CASES", "FUNKED_DRY_RUN_CASES"]
