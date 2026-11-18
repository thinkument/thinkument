from __future__ import annotations

"""Shared dry-run catalogs through Flask + real Chromium + sufficience DOM.

One strategy owns one persistent Node/Playwright/Chromium host for the sheet.
Every catalog row still gets a fresh real threaded Flask server, fresh backend
session, and fresh isolated BrowserContext/Page per role.  P7 is excluded only
because its forged lower-transport fixtures are not representable through a
correct browser-facing ThinkumentJS membrane.

Rows are executed fail-fast one by one.  This does not alter the execution
model: the same strategy-scoped Chromium process survives across rows while
lambda/omega remains case-local.
"""

import __staticfiles_mgmt.machinery as machinery

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.flask_facade_w_thinkumentjs_sufficiencejs_opinionation import (
    FlaskFacadeWithThinkumentJSSufficienceBrowserDryRunStrategy,
    P7_TRANSPORT_BOUNDARY_CASE,
    SUFFICIENCE_OPINIONATION_LOGICAL_NAME,
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


_MAX_FLASK_SERVER_SHUTDOWN_POLL_SECONDS = 0.05


def _assert_sufficience_is_normal_static_asset() -> None:
    machinery.validate_static_namespace()
    resolved = machinery.resolve_static_asset_path(
        SUFFICIENCE_OPINIONATION_LOGICAL_NAME
    ).resolve()
    assert resolved.is_file(), resolved


def _run_and_assert_ordinary_cases(
    cases,
    *,
    strategy,
    dispatcher_identity_prefix: str,
) -> int:
    completed = 0
    for case in cases:
        result = run_dry_run_suite_v1(
            (case,),
            strategy=strategy,
            dispatcher_identity_prefix=dispatcher_identity_prefix,
        )
        assert_dry_run_suite_v1(result)
        completed += len(result.cases)
    return completed


def _run_and_assert_funked_cases(
    cases,
    *,
    strategy,
    dispatcher_identity_prefix: str,
) -> int:
    completed = 0
    for case in cases:
        result = run_funked_dry_run_suite_v1(
            (case,),
            strategy=strategy,
            dispatcher_identity_prefix=dispatcher_identity_prefix,
        )
        assert_funked_dry_run_suite_v1(result)
        completed += len(result.cases)
    return completed


def test_all_supported_dry_run_flows_through_real_flask_browser_dom_strategy(
) -> None:
    register_dry_run_lib_widgets_flows_v1()
    _assert_sufficience_is_normal_static_asset()

    with FlaskFacadeWithThinkumentJSSufficienceBrowserDryRunStrategy() as strategy:
        # A case-local real Werkzeug server must not reintroduce the historical
        # 500 ms serve_forever() shutdown tax across the browser catalog.
        assert (
            strategy.server_shutdown_poll_seconds
            <= _MAX_FLASK_SERVER_SHUTDOWN_POLL_SECONDS
        ), (
            "Flask browser dry-run server shutdown polling became too coarse; "
            "keep the real threaded server but preserve responsive teardown."
        )

        skipped = strategy.skipped_cases_v1(DRY_RUN_CASES)
        assert [case.name for case, _reason in skipped] == [
            P7_TRANSPORT_BOUNDARY_CASE
        ]
        assert skipped[0][1]

        ordinary_cases = strategy.supported_cases_v1(DRY_RUN_CASES)
        ordinary_names = [case.name for case in ordinary_cases]
        assert (
            "dry_run_lib_widgets_flows.P9.role_modulated_reads_writes"
            in ordinary_names
        )
        assert (
            "dry_run_lib_widgets_flows.P13."
            "frontend_data_blankets_expected_proven_e2e"
            in ordinary_names
        )

        ordinary_count = _run_and_assert_ordinary_cases(
            ordinary_cases,
            strategy=strategy,
            dispatcher_identity_prefix=(
                "app-for-fundamentals-flask-browser-sufficience"
            ),
        )
        assert ordinary_count == len(ordinary_cases)

        assert strategy.skipped_cases_v1(
            FUNKED_DRY_RUN_CASES,
            funked=True,
        ) == ()
        funked_cases = strategy.supported_cases_v1(
            FUNKED_DRY_RUN_CASES,
            funked=True,
        )

        funked_count = _run_and_assert_funked_cases(
            funked_cases,
            strategy=strategy,
            dispatcher_identity_prefix=(
                "app-for-fundamentals-p12-flask-browser-sufficience"
            ),
        )
        assert funked_count == len(funked_cases)
