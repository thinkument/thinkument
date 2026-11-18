from __future__ import annotations

"""Prove the same catalogs run unchanged via the exchangeability copier.

Performance contract
--------------------
The copier proves strategy exchangeability; it does not represent a higher
transport or process boundary.  It should therefore remain in approximately
the same performance class as the direct base-facade strategy and must not
silently accumulate server, serialization, polling, or orchestration costs.
"""

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.dummy_base_backend_only_copier_for_tests import (
    DummyBaseBackendOnlyCopierForTestsStrategy,
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


_COPIER_PERFORMANCE = DryRunPerformanceContractV1(
    fixed_allowance_seconds=0.30,
    max_seconds_per_case=0.30,
    efficiency_reason=(
        "The copier exists to prove strategy exchangeability, not to add "
        "another execution layer. It should remain in the same performance "
        "class as the direct base-facade strategy and should not acquire "
        "transport, server-lifecycle, serialization, or polling costs."
    ),
)


def test_all_dry_run_flows_through_copier_strategy() -> None:
    strategy = DummyBaseBackendOnlyCopierForTestsStrategy()
    register_dry_run_lib_widgets_flows_v1()

    def run_catalogs():
        ordinary = run_dry_run_suite_v1(
            DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="copier-fundamentals-dry-run",
        )
        funked = run_funked_dry_run_suite_v1(
            FUNKED_DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="copier-fundamentals-p12-e2e",
        )
        return ordinary, funked

    timed = timed_v1(run_catalogs)
    ordinary, funked = timed.value

    assert_dry_run_suite_v1(ordinary)
    assert_funked_dry_run_suite_v1(funked)
    assert ordinary.strategy_name == strategy.strategy_name
    assert funked.strategy_name == strategy.strategy_name
    assert len(ordinary.cases) == len(DRY_RUN_CASES)
    assert len(funked.cases) == len(FUNKED_DRY_RUN_CASES)

    assert_performance_contract_v1(
        strategy_name=strategy.strategy_name,
        elapsed_seconds=timed.elapsed_seconds,
        case_count=len(DRY_RUN_CASES) + len(FUNKED_DRY_RUN_CASES),
        contract=_COPIER_PERFORMANCE,
    )


__all__ = ["DRY_RUN_CASES", "FUNKED_DRY_RUN_CASES"]
