from __future__ import annotations

"""Run every shared dry-run catalog through the real local-Flask strategy.

Performance contract
--------------------
The Flask strategy intentionally pays for real loopback HTTP, JSON,
Werkzeug request handling, Flask routing, capability resolution, and live
progress polling.

It must *not* pay Werkzeug's historical 500 ms ``serve_forever()`` shutdown
poll for every dry-run case.  The strategy keeps the real threaded server and
actual HTTP client while using a short serve-loop poll interval so teardown is
responsive.  This sheet protects both that structural invariant and the
resulting end-to-end performance class.
"""

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.flask_facade_backend_only import (
    FlaskFacadeBackendOnlyDryRunStrategy,
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


_FLASK_PERFORMANCE = DryRunPerformanceContractV1(
    fixed_allowance_seconds=0.30,
    max_seconds_per_case=0.45,
    efficiency_reason=(
        "The Flask strategy runs a real threaded Werkzeug server and actual "
        "loopback HTTP requests. Its dominant avoidable historical cost was "
        "Werkzeug serve_forever()'s default 0.5-second shutdown poll. The "
        "strategy therefore keeps server shutdown polling short rather than "
        "weakening the proof with app.test_client() or direct facade calls."
    ),
)

# The implementation currently uses 10 ms.  Keep the proof tolerant of small
# tuning changes while making restoration of Werkzeug's 500 ms default fail
# immediately and explain why.
_MAX_FLASK_SERVER_SHUTDOWN_POLL_SECONDS = 0.05


def test_all_dry_run_flows_through_flask_backend_only_strategy() -> None:
    strategy = FlaskFacadeBackendOnlyDryRunStrategy()
    register_dry_run_lib_widgets_flows_v1()

    assert (
        strategy.server_shutdown_poll_seconds
        <= _MAX_FLASK_SERVER_SHUTDOWN_POLL_SECONDS
    ), (
        "Flask dry-run server shutdown polling became too coarse. "
        "This strategy was made efficient by avoiding Werkzeug's default "
        "0.5-second serve_forever() shutdown poll for every catalog case "
        "while preserving a real local HTTP server."
    )

    def run_catalogs():
        ordinary = run_dry_run_suite_v1(
            DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="flask-fundamentals-dry-run",
        )
        funked = run_funked_dry_run_suite_v1(
            FUNKED_DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix="flask-fundamentals-p12-e2e",
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
        contract=_FLASK_PERFORMANCE,
    )


__all__ = ["DRY_RUN_CASES", "FUNKED_DRY_RUN_CASES"]
