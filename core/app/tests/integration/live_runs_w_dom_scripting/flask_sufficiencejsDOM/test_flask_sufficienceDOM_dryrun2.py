from __future__ import annotations

"""Direct DOM repro of catalog P2, including both launch-overlay modes.

P2 is the strongest P/C authoring proof in the ordinary catalog.  The two runs
below use the same authored ThinkProgram but distinct C overlays, then drive
only rendered sufficience controls: STEP, signal-only STEP, vector fill plus
signal, UNDO, and REDO.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program2__thinkprogram_authoring_range import (  # noqa: E402
    PROGRAM,
    PROGRAM_TAKE_OVER,
    PUPPET,
    PUPPET_TAKE_OVER,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (  # noqa: E402
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (  # noqa: E402
    LiveDemoOpinionationSelectionV1,
    live_run_tape_v1,
)
from ways_to_run.live_run_DOMscripted_atelier._whichserver_agnostic_scripted_DOM_run_launcher import (  # noqa: E402
    ScriptedDOMAtelierV1,
)
from ways_to_run.live_run_DOMscripted_atelier.flask_scripted_DOM_run_launcher import (  # noqa: E402
    run_flask_scripted_dom_in_atelier_v1,
)
from ._flask_test_support import (  # noqa: E402
    SUFFICIENCE_MODULE,
    assert_latest_contains_v1,
    assert_summary_v1,
    booted_v1,
    browser_launch_options_v1,
    dispatch_value_v1,
    latest_trident_v1,
    simple_action_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
)


def _assert_probe_proof(
    trident: Mapping[str, Any],
    *,
    label: str,
    env: str,
    minimum: int,
) -> None:
    text = json.dumps(trident, sort_keys=True, default=str)
    for needle in (
        "program_sessions.proof",
        "Appearance title replaces the logical-widget title",
        label,
        env,
        '"first_choice": "alpha"',
        f'"effective_minimum": {minimum}',
        '"appearance_only": true',
        '"replace_me": "appearance"',
    ):
        if needle not in text:
            raise AssertionError(
                f"P2 authoring proof is missing {needle!r}: {text}"
            )


async def scripted_dom_p2_case_v1(
    run,
    *,
    expected_label: str,
    expected_env: str,
    expected_minimum: int,
) -> Mapping[str, Any]:
    client = await run.client(run.urls["web"], name=f"p2-{expected_env}")
    await booted_v1(client)
    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"

    mounted = dispatch_value_v1(await step_v1(client, request_prefix="p2-mount"))
    await sync_all_v1([client], mounted)
    await assert_summary_v1(client, active=["probe"])
    _assert_probe_proof(
        await latest_trident_v1(client),
        label=expected_label,
        env=expected_env,
        minimum=expected_minimum,
    )

    ack = dispatch_value_v1(
        await step_v1(
            client,
            fill={"probe": {"acknowledgement": "authoring surface understood"}},
            request_prefix="p2-probe",
        )
    )
    await sync_all_v1([client], ack)
    await assert_summary_v1(client, active=["daily"])
    await assert_latest_contains_v1(client, "authoring proof acknowledged")

    first_daily = dispatch_value_v1(
        await step_v1(
            client,
            fill={"daily": {"representative_number": 8, "good_day": True}},
            request_prefix="p2-daily-1",
        )
    )
    await sync_all_v1([client], first_daily)
    await assert_summary_v1(client, active=["daily"])
    await assert_latest_contains_v1(client, "believe")

    signaled = dispatch_value_v1(
        await step_v1(
            client,
            signal={
                "datum_id": "daily",
                "kind": "adjust_min",
                "info": {"mins": [10, 12, 14]},
            },
            request_prefix="p2-signal",
        )
    )
    await sync_all_v1([client], signaled)
    await assert_summary_v1(client, active=["daily"])
    await assert_latest_contains_v1(client, "minimum adjusted")

    second_daily = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "daily": {
                    "representative_number": 20,
                    "day_reflection": "ready for the next step",
                }
            },
            request_prefix="p2-daily-2",
        )
    )
    await sync_all_v1([client], second_daily)
    await assert_summary_v1(client, active=["guess", "board"])
    await assert_latest_contains_v1(client, "believe", "started")

    vector = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "board": {"new_1": 1, "new_2": 3, "new_3": 5},
                "guess": {
                    "guess_1_1": 3,
                    "guess_1_2": 7,
                    "guess_1_3": 11,
                },
            },
            signal={
                "datum_id": "guess",
                "kind": "do_not_count",
                "info": {"reason": "demonstrate fill-plus-signal"},
            },
            request_prefix="p2-vector",
        )
    )
    await sync_all_v1([client], vector)
    await assert_summary_v1(client, active=["guess", "board"])
    await assert_latest_contains_v1(client, "closest", "cumulative")

    completed = dispatch_value_v1(
        await step_v1(
            client,
            fill={"guess": {"guess_2_1": 20, "guess_2_2": 27}},
            request_prefix="p2-complete",
        )
    )
    assert completed.get("event_kind") == "ATCOMPLETION"
    await sync_all_v1([client], completed)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")

    undone = dispatch_value_v1(
        await simple_action_v1(client, "UNDO", request_prefix="p2-undo")
    )
    await sync_all_v1([client], undone)
    await assert_summary_v1(client, active=["guess", "board"])

    redone = dispatch_value_v1(
        await simple_action_v1(client, "REDO", request_prefix="p2-redo")
    )
    high = await sync_all_v1([client], redone)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")

    return {
        "kind": "flask_sufficience_dom_p2_case_receipt_v1",
        "ok": True,
        "overlay_env": expected_env,
        "final_event_seq": high,
    }


def _script_for(*, label: str, env: str, minimum: int):
    async def script(run):
        return await scripted_dom_p2_case_v1(
            run,
            expected_label=label,
            expected_env=env,
            expected_minimum=minimum,
        )

    return script


async def _run_v1() -> None:
    register_dry_run_lib_widgets_flows_v1()
    opinionation = LiveDemoOpinionationSelectionV1(
        module=SUFFICIENCE_MODULE,
        use_installed_default=True,
    )

    cases = (
        (
            PROGRAM,
            PUPPET,
            "launch-merge-label",
            "launch-merge",
            4,
        ),
        (
            PROGRAM_TAKE_OVER,
            PUPPET_TAKE_OVER,
            "launch-take-over-label",
            "launch-take-over",
            6,
        ),
    )

    async with ScriptedDOMAtelierV1(
        headless=True,
        launch_options=browser_launch_options_v1(),
    ) as atelier:
        for program, C, label, env, minimum in cases:
            tape = live_run_tape_v1(
                program=program,
                session_metadata=None,
                initial_parameter_overrides=C,
                source=f"{__name__}:{env}",
            )
            receipt = await run_flask_scripted_dom_in_atelier_v1(
                atelier=atelier,
                tape=tape,
                script=_script_for(label=label, env=env, minimum=minimum),
                opinionation=opinionation,
                start_on_create=False,
            )
            assert isinstance(receipt.result, Mapping)
            assert receipt.result.get("ok") is True


def test_flask_sufficienceDOM_dryrun2() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
