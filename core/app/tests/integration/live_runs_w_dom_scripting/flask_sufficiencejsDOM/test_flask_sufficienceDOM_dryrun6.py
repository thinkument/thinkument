from __future__ import annotations

"""Direct DOM repro of catalog P6 semantic-validation layering.

The platform-invalid number remains a legal public STEP shape.  It therefore
belongs in this browser proof: ThinkumentJS admits the shape, backend micro
semantic validation rejects it before the widget lifecycle runs, and the same
rendered widget stays active with last_error exposed in U.
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

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program6__micros_shell__semantic_validation_by_platform_and_the_alternative_functional_lifecycle_validation_later import (  # noqa: E402
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
    assert_latest_informative_empty_v1,
    assert_summary_v1,
    booted_v1,
    browser_launch_options_v1,
    current_u_v1,
    dispatch_value_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
)


async def scripted_dom_p6_v1(run) -> Mapping[str, Any]:
    client = await run.client(run.urls["web"], name="p6")
    await booted_v1(client)
    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"

    mounted = dispatch_value_v1(await step_v1(client, request_prefix="p6-mount"))
    await sync_all_v1([client], mounted)
    await assert_summary_v1(client, active=["semantic_probe"])
    await assert_latest_contains_v1(client, "platform-validated")

    signal_only = dispatch_value_v1(
        await step_v1(
            client,
            signal={
                "datum_id": "semantic_probe",
                "kind": "explain",
                "info": {"lesson": "signals are commands"},
            },
            request_prefix="p6-signal",
        )
    )
    await sync_all_v1([client], signal_only)
    await assert_summary_v1(client, active=["semantic_probe"])
    await assert_latest_contains_v1(
        client,
        "semantic_validation.lifecycle_observed",
        "signal_catcher",
        "signals themselves are not micro values",
    )

    platform_rejected = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "semantic_probe": {
                    "platform_number": 5,
                    "lifecycle_code": "LIFE-would-have-been-valid",
                }
            },
            signal={
                "datum_id": "semantic_probe",
                "kind": "explain",
                "info": {"should_reach_handler": False},
            },
            request_prefix="p6-platform-reject",
        )
    )
    await sync_all_v1([client], platform_rejected)
    await assert_summary_v1(client, active=["semantic_probe"])
    await assert_latest_informative_empty_v1(client)
    U = await current_u_v1(client)
    if U is None or U.get("last_error") is None:
        raise AssertionError(f"P6 platform rejection omitted U.last_error: {U!r}")
    if "must be" not in json.dumps(U.get("last_error"), default=str).lower():
        raise AssertionError(f"unexpected platform semantic error: {U.get('last_error')!r}")

    lifecycle_rejected = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "semantic_probe": {
                    "platform_number": 12,
                    "lifecycle_code": "wrong-prefix",
                }
            },
            request_prefix="p6-lifecycle-reject",
        )
    )
    await sync_all_v1([client], lifecycle_rejected)
    await assert_summary_v1(client, active=["semantic_probe"])
    await assert_latest_contains_v1(
        client,
        "semantic_validation.lifecycle_observed",
        "fill_handler",
        "lifecycle_code must start",
    )

    done = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "semantic_probe": {
                    "platform_number": 12,
                    "lifecycle_code": "LIFE-accepted",
                }
            },
            request_prefix="p6-complete",
        )
    )
    assert done.get("event_kind") == "ATCOMPLETION"
    assert done.get("finished") is True
    high = await sync_all_v1([client], done)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    await assert_latest_contains_v1(
        client,
        "semantic_validation.lifecycle_observed",
        "both platform and lifecycle validation accepted",
    )

    return {
        "kind": "flask_sufficience_dom_p6_receipt_v1",
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
        script=scripted_dom_p6_v1,
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


def test_flask_sufficienceDOM_dryrun6() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
