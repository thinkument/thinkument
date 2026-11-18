from __future__ import annotations

"""Direct DOM repro of catalog P3 lifecycle/system execution flags."""

import asyncio
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program3__thinkwidget_lifecycle_execution_flags import (  # noqa: E402
    PROGRAM,
    PUPPET,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (  # noqa: E402
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (  # noqa: E402
    LiveDemoOpinionationSelectionV1,
    live_run_tape_v1,
)
from ways_to_run.live_run_DOMscripted_atelier.flask_scripted_DOM_run_launcher import (  # noqa: E402
    run_flask_scripted_dom_v1,
)
from ._flask_test_support import (  # noqa: E402
    SUFFICIENCE_MODULE,
    assert_latest_contains_v1,
    assert_summary_v1,
    booted_v1,
    browser_launch_options_v1,
    dispatch_value_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
)


async def scripted_dom_p3_v1(run) -> Mapping[str, Any]:
    client = await run.client(run.urls["web"], name="p3")
    await booted_v1(client)
    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"

    mounted = dispatch_value_v1(await step_v1(client, request_prefix="p3-mount"))
    await sync_all_v1([client], mounted)
    await assert_summary_v1(client, active=["board", "daily"])

    board = dispatch_value_v1(
        await step_v1(
            client,
            fill={"board": {"new_1": 1, "new_2": 3, "new_3": 5}},
            request_prefix="p3-board-open",
        )
    )
    await sync_all_v1([client], board)
    await assert_summary_v1(client, active=["board", "daily"])
    await assert_latest_contains_v1(client, "cumulative")

    gate = dispatch_value_v1(
        await step_v1(
            client,
            fill={"daily": {"representative_number": 7, "good_day": True}},
            request_prefix="p3-gate",
        )
    )
    await sync_all_v1([client], gate)
    await assert_summary_v1(client, active=["guess"])
    await assert_latest_contains_v1(client, "believe", "started")

    miss = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "guess": {
                    "guess_1_1": 1,
                    "guess_1_2": 2,
                    "guess_1_3": 3,
                }
            },
            request_prefix="p3-guess-miss",
        )
    )
    await sync_all_v1([client], miss)
    await assert_summary_v1(client, active=["guess"])
    await assert_latest_contains_v1(client, "closest")

    guess_done = dispatch_value_v1(
        await step_v1(
            client,
            fill={"guess": {"guess_2_1": 17, "guess_2_2": 18}},
            request_prefix="p3-guess-done",
        )
    )
    await sync_all_v1([client], guess_done)
    await assert_summary_v1(client, active=["board"])
    await assert_latest_contains_v1(client, "correct")

    forced = dispatch_value_v1(
        await step_v1(
            client,
            fill={"board": {"new_1": 1, "new_2": 3, "new_3": 5}},
            request_prefix="p3-forced-exhaustion",
        )
    )
    assert forced.get("event_kind") == "ATCOMPLETION"
    assert forced.get("finished") is True
    high = await sync_all_v1([client], forced)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    await assert_latest_contains_v1(client, "cumulative")

    return {
        "kind": "flask_sufficience_dom_p3_receipt_v1",
        "ok": True,
        "final_event_seq": high,
    }


async def _run_v1() -> None:
    tape = live_run_tape_v1(
        program=PROGRAM,
        session_metadata=None,
        initial_parameter_overrides=PUPPET,
        source=__name__,
    )
    receipt = await run_flask_scripted_dom_v1(
        tape=tape,
        script=scripted_dom_p3_v1,
        opinionation=LiveDemoOpinionationSelectionV1(
            module=SUFFICIENCE_MODULE,
            use_installed_default=True,
        ),
        prepare_runtime=(register_dry_run_lib_widgets_flows_v1,),
        start_on_create=False,
        headless=True,
        launch_options=browser_launch_options_v1(),
    )
    assert isinstance(receipt.result, Mapping)
    assert receipt.result.get("ok") is True


def test_flask_sufficienceDOM_dryrun3() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
