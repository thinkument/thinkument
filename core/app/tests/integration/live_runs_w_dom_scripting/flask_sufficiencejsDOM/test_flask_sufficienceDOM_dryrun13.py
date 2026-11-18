from __future__ import annotations

"""Direct DOM repro of catalog P13 frontend data blankets.

This is intentionally above the dry-run A/E machinery.  Real role pages capture
the normalized sufficience packet DOM while ordinary rendered controls dispatch.
For each admitted dispatch we require both provisional epsilon and canonical
theta, prove epsilon rows reconcile in order to theta after removing only
``event_seq``, then assert the role-projected current U/active-shell view.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program13___frontend_data_blankets_expected_proven_e2e import (  # noqa: E402
    PROGRAM,
    PUPPET,
    ROLE_AUDITOR,
    ROLE_MAKER,
    ROLE_REVIEWER,
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
    flask_role_url_key_v1,
    run_flask_scripted_dom_v1,
)
from ._flask_test_support import (  # noqa: E402
    SUFFICIENCE_MODULE,
    assert_epsilon_reconciled_by_theta_v1,
    assert_latest_contains_v1,
    assert_summary_v1,
    assert_trident_continuity_v1,
    assert_u_paths_v1,
    booted_v1,
    browser_launch_options_v1,
    dispatch_value_v1,
    install_packet_capture_v1,
    packet_count_v1,
    step_v1,
    summary_v1,
    sync_all_v1,
    wait_packet_triggers_v1,
)


async def _dispatch_with_blanket_proof(
    *,
    actor,
    clients: Mapping[str, Any],
    fill: Mapping[str, Mapping[str, Any]] | None = None,
    request_prefix: str,
    required: Iterable[str] = ("epsilon", "theta"),
) -> Mapping[str, Any]:
    start_index = await packet_count_v1(actor)
    result = dispatch_value_v1(
        await step_v1(
            actor,
            fill=fill,
            request_prefix=request_prefix,
        )
    )
    await sync_all_v1(clients, result)
    packets = await wait_packet_triggers_v1(
        actor,
        start_index=start_index,
        required=required,
    )
    if "epsilon" in required:
        assert_epsilon_reconciled_by_theta_v1(packets)
    return result


async def scripted_dom_p13_v1(run) -> Mapping[str, Any]:
    roles = (ROLE_MAKER, ROLE_REVIEWER, ROLE_AUDITOR)
    values = await asyncio.gather(
        *(
            run.client(
                run.urls[flask_role_url_key_v1(role)],
                name=f"p13-{role}",
            )
            for role in roles
        )
    )
    clients = dict(zip(roles, values))
    await asyncio.gather(*(booted_v1(client) for client in values))
    await asyncio.gather(*(install_packet_capture_v1(client) for client in values))

    for role, client in clients.items():
        row = await summary_v1(client)
        if row.get("runtime_kind") != "ATSTART":
            raise AssertionError(f"P13 role {role!r} did not boot at ATSTART: {row!r}")

    maker = clients[ROLE_MAKER]
    reviewer = clients[ROLE_REVIEWER]
    auditor = clients[ROLE_AUDITOR]

    mounted = await _dispatch_with_blanket_proof(
        actor=maker,
        clients=clients,
        request_prefix="p13-mount",
        required=("theta",),
    )
    await asyncio.gather(
        assert_summary_v1(maker, active=["daily", "board"]),
        assert_summary_v1(reviewer, active=["daily", "board"]),
        assert_summary_v1(auditor, active=["board"]),
    )
    await assert_u_paths_v1(
        auditor,
        {
            "role_mismatch_modulation_info.mismatch_datum_ids": ["daily"],
            "role_mismatch_modulation_info.receipt.kind": (
                "role_mismatch_activity_receipt_v1"
            ),
        },
    )

    board = await _dispatch_with_blanket_proof(
        actor=maker,
        clients=clients,
        fill={"board": {"new_1": 1, "new_2": 3, "new_3": 5}},
        request_prefix="p13-board",
    )
    await assert_latest_contains_v1(maker, "cumulative")
    await asyncio.gather(
        assert_summary_v1(maker, active=["daily", "board"]),
        assert_summary_v1(reviewer, active=["daily", "board"]),
        assert_summary_v1(auditor, active=["board"]),
    )

    daily = await _dispatch_with_blanket_proof(
        actor=maker,
        clients=clients,
        fill={"daily": {"representative_number": 9, "good_day": True}},
        request_prefix="p13-daily",
    )
    await assert_latest_contains_v1(maker, "believe")
    await assert_latest_contains_v1(reviewer, "believe", "started", "hint")
    await asyncio.gather(
        assert_summary_v1(maker, active=[]),
        assert_summary_v1(reviewer, active=["guess"]),
        assert_summary_v1(auditor, active=[]),
    )
    await assert_u_paths_v1(
        maker,
        {"role_mismatch_modulation_info.mismatch_datum_ids": ["guess"]},
    )
    await assert_u_paths_v1(
        reviewer,
        {"role_mismatch_modulation_info.mismatch_datum_ids": []},
    )
    await assert_u_paths_v1(
        auditor,
        {"role_mismatch_modulation_info.mismatch_datum_ids": ["guess"]},
    )

    done = await _dispatch_with_blanket_proof(
        actor=reviewer,
        clients=clients,
        fill={
            "guess": {
                "guess_1_1": 17,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
        request_prefix="p13-complete",
    )
    assert done.get("event_kind") == "ATCOMPLETION"
    assert done.get("finished") is True
    await asyncio.gather(
        *(
            assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
            for client in clients.values()
        )
    )
    await assert_latest_contains_v1(reviewer, "correct")

    # Every projected role sees one contiguous controller boundary tape even
    # when its theta page hides some middle datum events.
    await asyncio.gather(*(assert_trident_continuity_v1(client) for client in values))

    final_event_seq = int((await summary_v1(reviewer))["cursor"])
    return {
        "kind": "flask_sufficience_dom_p13_receipt_v1",
        "ok": True,
        "mount_event_kind": mounted.get("event_kind"),
        "board_event_kind": board.get("event_kind"),
        "daily_event_kind": daily.get("event_kind"),
        "final_event_seq": final_event_seq,
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
        script=scripted_dom_p13_v1,
        opinionation=LiveDemoOpinionationSelectionV1(
            module=SUFFICIENCE_MODULE,
            use_installed_default=True,
        ),
        public_view_role=ROLE_MAKER,
        prepare_runtime=(register_dry_run_lib_widgets_flows_v1,),
        start_on_create=False,
        headless=True,
        launch_options=browser_launch_options_v1(),
    )
    assert isinstance(receipt.result, Mapping)
    assert receipt.result.get("ok") is True


def test_flask_sufficienceDOM_dryrun13() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
