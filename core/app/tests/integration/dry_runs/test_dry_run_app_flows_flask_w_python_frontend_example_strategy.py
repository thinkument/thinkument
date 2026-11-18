from __future__ import annotations

"""Run every shared dry-run catalog through Flask + Python frontend.

The test deliberately reuses the exact ordinary and funked catalogs.  The
strategy adds a stateful role-bound frontend process between the generic dry-run
machinery and the real Flask server; no flow acquires client or Flask branches.
"""

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.flask_facade_w_python_frontend_example import (
    FlaskFacadeWithPythonFrontendExampleDryRunStrategy,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.dry_run_cases import (
    DRY_RUN_CASES,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.dry_run_cases_funked import (
    FUNKED_DRY_RUN_CASES,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.funked_live_session_dry_run_v1 import (
    assert_funked_dry_run_suite_v1,
    run_funked_dry_run_suite_v1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.live_session_dry_run_v1 import (
    assert_dry_run_suite_v1,
    run_dry_run_suite_v1,
)


def test_all_dry_run_flows_through_flask_w_python_frontend_example_strategy(
) -> None:
    register_dry_run_lib_widgets_flows_v1()
    strategy = FlaskFacadeWithPythonFrontendExampleDryRunStrategy()

    ordinary = run_dry_run_suite_v1(
        DRY_RUN_CASES,
        strategy=strategy,
        dispatcher_identity_prefix=(
            "app-for-fundamentals-flask-python-front"
        ),
    )
    funked = run_funked_dry_run_suite_v1(
        FUNKED_DRY_RUN_CASES,
        strategy=strategy,
        dispatcher_identity_prefix=(
            "app-for-fundamentals-p12-flask-python-front"
        ),
    )

    assert_dry_run_suite_v1(ordinary)
    assert_funked_dry_run_suite_v1(funked)
    assert len(ordinary.cases) == len(DRY_RUN_CASES)
    assert len(funked.cases) == len(FUNKED_DRY_RUN_CASES)
