from __future__ import annotations

"""Run every shared catalog through Flask + real opinionless ThinkumentJS.

No flow or expectation is specialized for JS. The strategy translates the
same standard P/SM/C/A/E tape into stable role clients, actual ThinkumentJS
loopback dispatch, roleful epsilon, canonical theta, womb observations, and
client-local Q/U reads.

Task-F efficiency invariant:
one strategy instance owns one persistent Node kernel host across the complete
ordinary + funked sheet. Every dry-run case still opens and closes a fresh
role-client set and a fresh Flask/backend session.
"""

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.flask_facade_w_thinkumentjs_frontend_example import (
    FlaskFacadeWithThinkumentJSFrontendOpinionlessDryRunStrategy,
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


def test_all_dry_run_flows_through_flask_w_thinkumentjs_frontend_opinionless_strategy(
) -> None:
    register_dry_run_lib_widgets_flows_v1()

    with FlaskFacadeWithThinkumentJSFrontendOpinionlessDryRunStrategy() as strategy:
        ordinary = run_dry_run_suite_v1(
            DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix=(
                "app-for-fundamentals-flask-thinkumentjs-front"
            ),
        )
        # Fail before paying for the funked catalog if the ordinary membrane is
        # broken. This keeps the sheet fast to diagnose without changing coverage.
        assert_dry_run_suite_v1(ordinary)
        assert len(ordinary.cases) == len(DRY_RUN_CASES)

        funked = run_funked_dry_run_suite_v1(
            FUNKED_DRY_RUN_CASES,
            strategy=strategy,
            dispatcher_identity_prefix=(
                "app-for-fundamentals-p12-flask-thinkumentjs-front"
            ),
        )
        assert_funked_dry_run_suite_v1(funked)
        assert len(funked.cases) == len(FUNKED_DRY_RUN_CASES)
