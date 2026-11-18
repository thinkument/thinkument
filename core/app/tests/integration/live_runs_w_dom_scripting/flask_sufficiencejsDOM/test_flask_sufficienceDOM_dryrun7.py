from __future__ import annotations

"""Direct DOM repro of the module historically named program7, catalog P8.

The source filename is ``program7__...`` but its public dry-run case is P8:
session metadata as the scalable activation head.  This test keeps the user-
requested ``dryrun7`` filename while documenting that catalog identity.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program7__thinkprogram_session_metadata_as_a_scalable_activation_head import (  # noqa: E402
    ACTIVATION_POCKET,
    PROGRAM,
    PUPPET,
    SESSION_METADATA,
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
    assert_u_paths_v1,
    booted_v1,
    browser_launch_options_v1,
    dispatch_value_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
)


_METADATA_EXPECTED = {
    "session_metadata.manual_io.persistence": "disabled",
    "session_metadata.manual_io.profile": True,
    "session_metadata.manual_io.include_full_multiframespec_in_ctx": True,
    "session_metadata.manual_io.include_forms_emitted_order_in_ctx": True,
    "session_metadata.manual_io.max_fields_per_submit": 64,
    "session_metadata.manual_io.max_payload_chars": 100_000,
    "session_metadata.session_storage.events_snapshot_window": 64,
    "session_metadata.session_storage.forms_emitted_snapshot_window": 8,
    "session_metadata.session_storage.redo_max_depth": 4,
    "session_metadata.session_storage.redo_action_max_payload_chars": 20_000,
    f"session_metadata.{ACTIVATION_POCKET}.kind": (
        "dry_run_lib_widgets_flows_activation_v1"
    ),
    f"session_metadata.{ACTIVATION_POCKET}.enabled": True,
}


async def scripted_dom_p8_metadata_v1(run) -> Mapping[str, Any]:
    client = await run.client(run.urls["web"], name="p8-session-metadata")
    await booted_v1(client)
    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"

    mounted = dispatch_value_v1(await step_v1(client, request_prefix="p8-mount"))
    await sync_all_v1([client], mounted)
    await assert_summary_v1(client, active=["daily"])
    await assert_u_paths_v1(client, _METADATA_EXPECTED)

    daily = dispatch_value_v1(
        await step_v1(
            client,
            fill={"daily": {"representative_number": 11, "good_day": True}},
            request_prefix="p8-daily",
        )
    )
    await sync_all_v1([client], daily)
    await assert_summary_v1(client, active=["guess"])
    await assert_latest_contains_v1(client, "believe", "started", "hint")
    await assert_u_paths_v1(client, _METADATA_EXPECTED)

    done = dispatch_value_v1(
        await step_v1(
            client,
            fill={
                "guess": {
                    "guess_1_1": 17,
                    "guess_1_2": 3,
                    "guess_1_3": 5,
                }
            },
            request_prefix="p8-complete",
        )
    )
    assert done.get("event_kind") == "ATCOMPLETION"
    assert done.get("finished") is True
    high = await sync_all_v1([client], done)
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    await assert_latest_contains_v1(client, "correct")
    await assert_u_paths_v1(client, _METADATA_EXPECTED)

    return {
        "kind": "flask_sufficience_dom_p8_metadata_receipt_v1",
        "ok": True,
        "final_event_seq": high,
    }


async def _run_v1() -> None:
    tape = live_run_tape_v1(
        program=PROGRAM,
        session_metadata=SESSION_METADATA,
        initial_parameter_overrides=PUPPET,
        source=__name__,
    )
    receipt = await run_flask_scripted_dom_v1(
        tape=tape,
        script=scripted_dom_p8_metadata_v1,
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


def test_flask_sufficienceDOM_dryrun7() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
