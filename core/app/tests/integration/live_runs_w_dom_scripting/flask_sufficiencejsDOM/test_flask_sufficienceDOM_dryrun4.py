from __future__ import annotations

"""Direct DOM repro of catalog P4 exact wires/args/history observation."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program4__thinkwidget_wires_args_and_history_observation import (  # noqa: E402
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
    latest_trident_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
)


def _assert_self_previous_proof(trident: Mapping[str, Any], expected: bool) -> None:
    text = json.dumps(trident, sort_keys=True, default=str)
    needle = f'"self_previous_present": {str(expected).lower()}'
    if needle not in text:
        raise AssertionError(
            f"P4 wiring proof did not carry {needle!r}: {text}"
        )
    for required in ("one_source", "many_sources", "wiring.proof"):
        if required not in text:
            raise AssertionError(
                f"P4 wiring proof omitted {required!r}: {text}"
            )


async def scripted_dom_p4_v1(run) -> Mapping[str, Any]:
    client = await run.client(run.urls["web"], name="p4")
    await booted_v1(client)
    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"

    mounted = dispatch_value_v1(await step_v1(client, request_prefix="p4-mount"))
    await sync_all_v1([client], mounted)
    await assert_summary_v1(client, active=["daily"])

    daily = dispatch_value_v1(
        await step_v1(
            client,
            fill={"daily": {"representative_number": 9, "good_day": True}},
            request_prefix="p4-daily",
        )
    )
    await sync_all_v1([client], daily)
    await assert_summary_v1(client, active=["guess"])
    await assert_latest_contains_v1(client, "believe", "started", "hint")

    guess = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "guess": {
                    "guess_1_1": 9,
                    "guess_1_2": 3,
                    "guess_1_3": 5,
                }
            },
            request_prefix="p4-guess",
        )
    )
    await sync_all_v1([client], guess)
    await assert_summary_v1(client, active=["observer"])
    await assert_latest_contains_v1(client, "correct", "wiring proof mounted")
    _assert_self_previous_proof(await latest_trident_v1(client), False)

    first_observer = dispatch_value_v1(
        await step_v1(
            client,
            fill={"observer": {"acknowledgement": "first wiring view understood"}},
            request_prefix="p4-observer-1",
        )
    )
    await sync_all_v1([client], first_observer)
    await assert_summary_v1(client, active=["observer"])
    await assert_latest_contains_v1(client, "acknowledged", "wiring proof mounted")
    _assert_self_previous_proof(await latest_trident_v1(client), True)

    done = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "observer": {
                    "acknowledgement": "self previous wiring understood",
                }
            },
            request_prefix="p4-observer-2",
        )
    )
    assert done.get("event_kind") == "ATCOMPLETION"
    high = await sync_all_v1([client], done)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    await assert_latest_contains_v1(client, "acknowledged")

    return {
        "kind": "flask_sufficience_dom_p4_receipt_v1",
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
        script=scripted_dom_p4_v1,
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


def test_flask_sufficienceDOM_dryrun4() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
