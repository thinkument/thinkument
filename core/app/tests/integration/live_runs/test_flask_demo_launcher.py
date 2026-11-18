from __future__ import annotations

"""Focused proof that the live launcher exposes one real Flask page per role."""

import threading
from urllib.request import urlopen

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes import (
    PROGRAM,
    PUPPET,
    SESSION_METADATA,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (
    register_dry_run_lib_widgets_flows_v1,
)
from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (
    live_run_tape_v1,
)
from ways_to_run.live_run_atelier.flask_demo_launcher import FlaskLiveDemoLauncherV1


def test_flask_live_demo_exposes_one_real_browser_page_per_authored_role() -> None:
    register_dry_run_lib_widgets_flows_v1()

    launcher = FlaskLiveDemoLauncherV1()
    handle = launcher.start_v1(
        tape=live_run_tape_v1(
            program=PROGRAM,
            session_metadata=SESSION_METADATA,
            initial_parameter_overrides=PUPPET,
        ),
        public_view_role="maker",
    )
    server_thread = threading.Thread(
        target=launcher.serve_v1,
        kwargs={"handle": handle},
        daemon=True,
    )
    server_thread.start()

    try:
        receipt = launcher.receipt_v1(handle=handle)
        assert receipt.selected_role == "maker"
        for access in receipt.accesses:
            assert access.role in [
            "maker",
            "reviewer",
            "auditor",
        ]
        assert len({access.page_url for access in receipt.accesses}) == 3

        for access in receipt.accesses:
            with urlopen(access.page_url, timeout=10) as response:
                body = response.read().decode("utf-8")
            assert response.status == 200
            assert "thinkument-root" in body
            assert "type=\"module\"" in body or "type='module'" in body
    finally:
        launcher.close_v1(handle=handle)
        server_thread.join(timeout=5)
        assert not server_thread.is_alive()
