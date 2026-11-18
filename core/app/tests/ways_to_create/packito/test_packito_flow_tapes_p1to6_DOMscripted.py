from __future__ import annotations

"""Packito through Flask + ThinkumentJS + HAI + real DOMScriptr browser I/O.

Every PROGRAM below is a normal P/SM/C tape. The scenarios intentionally act
through the rendered Packito DOM rather than calling backend/session internals.
One Browser is reused across the suite; each scenario still receives a fresh
server/session and fresh BrowserContexts.

Performance law
---------------
The suite proves each P/SM/C program E2E, but expensive proof data stays in the
browser object model instead of being pretty-printed into the DOM on every
heartbeat. Packito registration is performed once for the suite, Chromium is
amortized once, and scenario timings are printed so a regression is visible.
Set ``PACKITO_E2E_MAX_SECONDS`` in CI when a wall-clock budget should be a hard
contract for a particular machine class.

Role projection law
-------------------
A dispatch result proves that the canonical server mutation completed for the
dispatching client. HAI does not require an already-open browser identity to
observe that mutation within a particular wall-clock heartbeat interval. When
a scenario intentionally changes identity, it therefore opens a fresh role
view *after* the causing dispatch and asserts the canonical theta projection
seen by that role. This is deterministic, uses only the public browser surface,
and avoids sleeps, reloads, backend peeks, and test-only polling contracts.
"""

import asyncio
import json
import os
import time
from typing import Any, Mapping

from playwright.async_api import expect

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
from ways_to_run.live_run_DOMscripted_atelier.hai_dom_support import (  # noqa: E402
    HAI_MODULE,
    action_v1,
    assert_latest_contains_v1,
    assert_summary_v1,
    booted_v1,
    browser_launch_options_v1,
    step_v1,
    summary_v1,
)
from packito_fixture.py.DOMscriptr_support import assert_context_contains_v1  # noqa: E402
from packito_fixture.py.programs.program1__composition_and_progression import (  # noqa: E402
    PROGRAM as P1,
    PUPPET as C1,
    SESSION_METADATA as SM1,
)
from packito_fixture.py.programs.program2__authoring_symbols_overrides_and_wires import (  # noqa: E402
    PROGRAM as P2,
    PUPPET as C2,
    SESSION_METADATA as SM2,
)
from packito_fixture.py.programs.program3__validation_signals_and_lifecycle_flags import (  # noqa: E402
    PROGRAM as P3,
    PUPPET as C3,
    SESSION_METADATA as SM3,
)
from packito_fixture.py.programs.program4__role_modulation_and_projection import (  # noqa: E402
    PROGRAM as P4,
    PUPPET as C4,
    ROLE_AUDITOR,
    ROLE_MAKER,
    ROLE_REVIEWER,
    SESSION_METADATA as SM4,
)
from packito_fixture.py.programs.program5__funked_human_collaboration import (  # noqa: E402
    PROGRAM as P5,
    PUPPET as C5,
    ROLE_GENERATOR,
    ROLE_HUMAN,
    SESSION_METADATA as SM5,
)
from packito_fixture.py.programs.program6__frontend_blanket_history_and_undo_redo import (  # noqa: E402
    PROGRAM as P6,
    PUPPET as C6,
    SESSION_METADATA as SM6,
)
from packito_fixture.py.registration import register_app_pack_v1  # noqa: E402


OPINIONATION = LiveDemoOpinionationSelectionV1(
    module=HAI_MODULE,
    use_installed_default=True,
)


async def _inspector_contains(client, *needles: str) -> None:
    # Assert against the complete retained HAI context without opening the
    # expensive human-facing pretty JSON inspector.
    await assert_context_contains_v1(client, *needles)


def _assert_json_contains_v1(
    value: Any,
    *needles: str,
    label: str,
) -> None:
    """Assert exact causal evidence on a returned browser/backend packet."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    missing = [
        str(needle)
        for needle in needles
        if str(needle) not in payload
    ]
    if not missing:
        return

    # Keep failures useful without dumping an arbitrarily large queue packet.
    preview = payload if len(payload) <= 6_000 else payload[-6_000:]
    raise AssertionError(
        f"{label} did not contain expected causal evidence; "
        f"missing={missing!r}; payload_tail={preview!r}"
    )


async def _packito_boot(run, *, url_key: str = "web", name: str = "packito"):
    client = await run.client(run.urls[url_key], name=name)
    await booted_v1(client)
    page = client.page
    assert page is not None
    await expect(page.locator("[data-thinkument-hai]")).to_have_attribute(
        "data-hai-app-pack",
        "packito",
    )
    await page.locator("[data-packito-inspector]").wait_for(state="attached")
    await expect(page.locator("[data-packito-inspector-json]")).to_contain_text(
        "Open this inspector to materialize"
    )
    return client


async def script_p1(run) -> Mapping[str, Any]:
    client = await _packito_boot(run, name="packito-p1")
    page = client.page
    assert page is not None

    assert (await summary_v1(client)).get("runtime_kind") == "ATSTART"
    await step_v1(client, request_prefix="p1-mount")
    await assert_summary_v1(client, active=["opening"])
    await expect(page.locator('[data-hai-widget-id="opening"]')).to_have_attribute(
        "data-hai-renderer",
        "packito.choice.v1",
    )

    await page.locator('[data-packito-refresh="opening"]').click()
    await expect(page.locator("[data-packito-custom-notice]")).to_have_count(1)

    await step_v1(
        client,
        fill={"opening": {"choice": "alpha", "note": "WHY:first"}},
        request_prefix="p1-opening",
    )

    await step_v1(
        client,
        fill={"board": {"delta": 5}},
        request_prefix="p1-board",
    )
    await expect(page.locator("[data-packito-board-total]")).to_contain_text(
        "total=5"
    )
    await expect(
        page.locator('[data-hai-notification="packito.silent_metric"]')
    ).to_have_count(0)

    await step_v1(
        client,
        fill={"closing": {"choice": "beta", "note": "WHY:finish"}},
        request_prefix="p1-close",
    )
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    await _inspector_contains(
        client,
        '"access_table"',
        '"session_metadata"',
        '"dispatch_timeline"',
    )
    await expect(page.locator("[data-packito-inspector-json]")).to_contain_text(
        "Open this inspector to materialize"
    )
    return {"ok": True, "program": "p1"}


async def script_p2(run) -> Mapping[str, Any]:
    client = await _packito_boot(run, name="packito-p2")
    page = client.page
    assert page is not None

    await step_v1(client, request_prefix="p2-mount")
    await assert_summary_v1(client, active=["source_a"])
    await expect(
        page.locator('[data-hai-widget-id="source_a"] h3')
    ).to_contain_text("Launch C replaced this prompt")
    await _inspector_contains(client, "BECAUSE:", "appearance-a")

    await step_v1(
        client,
        fill={
            "source_a": {
                "choice": "alpha",
                "note": "BECAUSE: launch C",
            }
        },
        request_prefix="p2-source-a",
    )

    await step_v1(
        client,
        fill={
            "source_b": {
                "choice": "beta",
                "note": "WHY:wired",
            }
        },
        request_prefix="p2-source-b",
    )

    wire_index_node = page.locator("[data-packito-wire-index]")
    await wire_index_node.wait_for(state="attached")

    wire_index_text = await wire_index_node.text_content()
    wire_index = json.loads(wire_index_text or "{}")

    assert wire_index["one_source"]["row_count"] == 1
    assert [
        row["datum_id"]
        for row in wire_index["one_source"]["sources"]
    ] == ["source_a"]

    assert wire_index["many_sources"]["row_count"] == 2
    assert [
        row["datum_id"]
        for row in wire_index["many_sources"]["sources"]
    ] == ["source_a", "source_b"]

    one_source_states = wire_index["one_source"]["states"]
    assert len(one_source_states) == 1

    source_a_state = one_source_states[0]
    assert source_a_state["accepted_choice"] == "alpha"
    assert source_a_state["accepted_note"] == "BECAUSE: launch C"
    assert source_a_state["prompt"] == "Launch C replaced this prompt"
    assert source_a_state["appearance_label"] == "appearance-a"
    assert source_a_state["required_note_prefix"] == "BECAUSE:"

    many_source_states = wire_index["many_sources"]["states"]
    assert len(many_source_states) == 2

    assert many_source_states[0]["accepted_choice"] == "alpha"
    assert many_source_states[0]["accepted_note"] == "BECAUSE: launch C"

    assert many_source_states[1]["accepted_choice"] == "beta"
    assert many_source_states[1]["accepted_note"] == "WHY:wired"

    source_b_wired_state = many_source_states[1]["source_state"]
    assert source_b_wired_state["accepted_choice"] == "alpha"
    assert source_b_wired_state["accepted_note"] == "BECAUSE: launch C"
    assert source_b_wired_state["prompt"] == "Launch C replaced this prompt"

    await step_v1(
        client,
        fill={"observer": {"acknowledgement": "first view understood"}},
        request_prefix="p2-observer-1",
    )

    second_wire_index = page.locator("[data-packito-wire-index]")
    await expect(second_wire_index).to_contain_text("self_previous")
    await expect(second_wire_index).to_contain_text('"row_count": 1')

    await step_v1(
        client,
        fill={"observer": {"acknowledgement": "self previous understood"}},
        request_prefix="p2-observer-2",
    )
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    return {"ok": True, "program": "p2"}


async def script_p3(run) -> Mapping[str, Any]:
    client = await _packito_boot(run, name="packito-p3")
    page = client.page
    assert page is not None

    await step_v1(client, request_prefix="p3-mount")
    await assert_summary_v1(client, active=["validated"])

    await page.locator('[data-packito-refresh="validated"]').click()

    await step_v1(
        client,
        fill={
            "validated": {
                "choice": "not-allowed",
                "note": "DOMAIN:would otherwise pass",
            }
        },
        request_prefix="p3-platform-reject",
    )
    await _inspector_contains(client, '"latest_semantic_errors"')

    await step_v1(
        client,
        fill={
            "validated": {
                "choice": "alpha",
                "note": "wrong prefix",
            }
        },
        request_prefix="p3-domain-reject",
    )
    assert await page.locator("[data-packito-custom-notice]").count() >= 2

    await step_v1(
        client,
        fill={
            "validated": {
                "choice": "alpha",
                "note": "DOMAIN:accepted",
            }
        },
        request_prefix="p3-valid",
    )

    await step_v1(
        client,
        fill={"forced_board": {"delta": 1}},
        request_prefix="p3-exhaust",
    )
    await assert_summary_v1(client, active=None, runtime_kind="ATCOMPLETION")
    return {"ok": True, "program": "p3"}


async def script_p4(run) -> Mapping[str, Any]:
    maker = await _packito_boot(
        run,
        url_key=f"role:{ROLE_MAKER}",
        name="maker",
    )

    await step_v1(maker, request_prefix="p4-mount")
    await assert_summary_v1(
        maker,
        active=["maker_choice", "public_board"],
    )

    reviewer_before = await _packito_boot(
        run,
        url_key=f"role:{ROLE_REVIEWER}",
        name="reviewer-before-maker-submit",
    )
    auditor_before = await _packito_boot(
        run,
        url_key=f"role:{ROLE_AUDITOR}",
        name="auditor-before-maker-submit",
    )
    reviewer_before_page = reviewer_before.page
    auditor_before_page = auditor_before.page
    assert reviewer_before_page is not None
    assert auditor_before_page is not None

    await expect(
        reviewer_before_page.locator('[data-packito-no-write="maker_choice"]')
    ).to_be_visible()
    reviewer_before_summary = await summary_v1(reviewer_before)
    assert reviewer_before_summary.get("active_widget_ids") == [
        "maker_choice",
        "public_board",
    ]

    await expect(
        auditor_before_page.locator('[data-packito-no-read="maker_choice"]')
    ).to_be_visible()
    auditor_before_summary = await summary_v1(auditor_before)
    assert auditor_before_summary.get("active_widget_ids") == ["public_board"]
    await _inspector_contains(
        auditor_before,
        "role_mismatch_activity_receipt_v1",
    )

    await step_v1(
        maker,
        fill={
            "maker_choice": {
                "choice": "alpha",
                "note": "WHY:maker",
            }
        },
        request_prefix="p4-maker",
    )

    reviewer = await _packito_boot(
        run,
        url_key=f"role:{ROLE_REVIEWER}",
        name="reviewer-after-maker-submit",
    )
    auditor_after_maker = await _packito_boot(
        run,
        url_key=f"role:{ROLE_AUDITOR}",
        name="auditor-after-maker-submit",
    )
    reviewer_page = reviewer.page
    auditor_after_maker_page = auditor_after_maker.page
    assert reviewer_page is not None
    assert auditor_after_maker_page is not None

    await assert_summary_v1(reviewer, active=["reviewer_choice"])
    await assert_summary_v1(auditor_after_maker, active=[])

    await expect(
        reviewer_page.locator('[data-hai-widget-id="reviewer_choice"]')
    ).to_have_attribute("data-hai-renderer", "packito.choice.v1")
    await expect(
        reviewer_page.locator('[data-packito-no-write="reviewer_choice"]')
    ).to_have_count(0)
    await expect(
        auditor_after_maker_page.locator(
            '[data-packito-no-read="reviewer_choice"]'
        )
    ).to_be_visible()

    await step_v1(
        reviewer,
        fill={
            "reviewer_choice": {
                "choice": "beta",
                "note": "WHY:reviewer",
            }
        },
        request_prefix="p4-reviewer",
    )
    await assert_summary_v1(
        reviewer,
        active=None,
        runtime_kind="ATCOMPLETION",
    )

    maker_done = await _packito_boot(
        run,
        url_key=f"role:{ROLE_MAKER}",
        name="maker-after-reviewer-submit",
    )
    auditor_done = await _packito_boot(
        run,
        url_key=f"role:{ROLE_AUDITOR}",
        name="auditor-after-reviewer-submit",
    )
    await assert_summary_v1(
        maker_done,
        active=None,
        runtime_kind="ATCOMPLETION",
    )
    await assert_summary_v1(
        auditor_done,
        active=None,
        runtime_kind="ATCOMPLETION",
    )
    return {"ok": True, "program": "p4"}


async def script_p5(run) -> Mapping[str, Any]:
    generator = await _packito_boot(
        run,
        url_key=f"role:{ROLE_GENERATOR}",
        name="generator",
    )

    await step_v1(
        generator,
        funked=True,
        request_prefix="p5-generated-seed",
    )

    human = await _packito_boot(
        run,
        url_key=f"role:{ROLE_HUMAN}",
        name="human",
    )
    human_page = human.page
    assert human_page is not None
    await human_page.locator('[data-hai-widget-id="review"]').wait_for(
        state="attached"
    )
    human_summary = await summary_v1(human)
    assert human_summary.get("runtime_kind") == "MANUALFILLNEEDEDSTEP"
    assert human_summary.get("active_widget_ids") == ["review"]
    await _inspector_contains(
        human,
        f'"role":"{ROLE_HUMAN}"',
        '"runtime_kind":"MANUALFILLNEEDEDSTEP"',
    )

    human_dispatch = await step_v1(
        human,
        fill={"review": {"approval": "approve"}},
        funked=True,
        request_prefix="p5-human-resume",
    )

    _assert_json_contains_v1(
        human_dispatch,
        "packito_puzzle_solver_receipt_v1",
        '"retrying_after_semantic_error":true',
        "program_complete_or_not_manual",
        label="P5 human funked dispatch result",
    )
    return {"ok": True, "program": "p5"}


async def script_p6(run) -> Mapping[str, Any]:
    client = await _packito_boot(run, name="packito-p6")
    page = client.page
    assert page is not None

    await step_v1(
        client,
        request_prefix="p6-mount",
    )
    await step_v1(
        client,
        fill={
            "first": {
                "choice": "alpha",
                "note": "WHY:first",
            }
        },
        request_prefix="p6-first",
    )

    await step_v1(
        client,
        fill={
            "second": {
                "choice": "beta",
                "note": "WHY:second",
            }
        },
        request_prefix="p6-second",
    )
    await assert_summary_v1(
        client,
        active=None,
        runtime_kind="ATCOMPLETION",
    )

    await page.locator('[data-packito-control="history"]').click()

    await client.wait_js(
        "() => JSON.parse("
        "document.querySelector('[data-hai-summary]').textContent"
        ").viewing_latest === false"
    )
    assert await page.locator('[data-hai-action="STEP"]').is_disabled()

    await page.locator('[data-packito-control="snap"]').click()
    await expect(
        page.locator("[data-packito-state-summary]")
    ).to_contain_text("snap=false")

    await page.locator('[data-packito-control="latest"]').click()
    await client.wait_js(
        "() => JSON.parse("
        "document.querySelector('[data-hai-summary]').textContent"
        ").viewing_latest === true"
    )

    await page.locator('[data-packito-control="epsilon"]').click()
    await expect(
        page.locator("[data-packito-state-summary]")
    ).to_contain_text("eps=true")

    await page.locator('[data-packito-control="epsilon"]').click()
    await expect(
        page.locator("[data-packito-state-summary]")
    ).to_contain_text("eps=false")

    await action_v1(
        client,
        "UNDO",
        request_prefix="p6-undo",
    )
    await assert_summary_v1(
        client,
        active=["second"],
    )
    await assert_latest_contains_v1(
        client,
        "UNDO",
    )

    await action_v1(
        client,
        "REDO",
        request_prefix="p6-redo",
    )
    await assert_summary_v1(
        client,
        active=None,
        runtime_kind="ATCOMPLETION",
    )
    await assert_latest_contains_v1(
        client,
        "REDO",
    )
    await _inspector_contains(
        client,
        '"action_packets"',
        '"UNDO"',
        '"REDO"',
    )
    return {"ok": True, "program": "p6"}


CASES = (
    ("p1", P1, SM1, C1, None, script_p1),
    ("p2", P2, SM2, C2, None, script_p2),
    ("p3", P3, SM3, C3, None, script_p3),
    ("p4", P4, SM4, C4, ROLE_MAKER, script_p4),
    ("p5", P5, SM5, C5, ROLE_GENERATOR, script_p5),
    ("p6", P6, SM6, C6, None, script_p6),
)


async def _run_all_v1() -> None:
    register_app_pack_v1()

    timings: dict[str, float] = {}
    suite_started = time.perf_counter()

    try:
        async with ScriptedDOMAtelierV1(
            headless=True,
            launch_options=browser_launch_options_v1(),
        ) as atelier:
            for name, P, SM, C, public_role, script in CASES:
                case_started = time.perf_counter()
                try:
                    tape = live_run_tape_v1(
                        program=P,
                        session_metadata=SM,
                        initial_parameter_overrides=C,
                        source=f"packito.pedagogy.{name}",
                    )

                    receipt = await run_flask_scripted_dom_in_atelier_v1(
                        atelier=atelier,
                        tape=tape,
                        script=script,
                        opinionation=OPINIONATION,
                        public_view_role=public_role,
                        prepare_runtime=(),
                        start_on_create=False,
                    )

                    assert isinstance(receipt.result, Mapping)
                    assert receipt.result.get("ok") is True
                    assert receipt.result.get("program") == name
                finally:
                    timings[name] = time.perf_counter() - case_started
                    print(
                        "PACKITO_E2E_CASE_TIMING="
                        + json.dumps(
                            {"case": name, "seconds": round(timings[name], 3)},
                            sort_keys=True,
                        ),
                        flush=True,
                    )
    finally:
        timings["total"] = time.perf_counter() - suite_started
        print(
            "PACKITO_E2E_TIMINGS="
            + json.dumps(
                {key: round(value, 3) for key, value in timings.items()},
                sort_keys=True,
            ),
            flush=True,
        )

    raw_budget = str(os.environ.get("PACKITO_E2E_MAX_SECONDS") or "").strip()
    if raw_budget:
        budget = float(raw_budget)
        assert timings["total"] <= budget, (
            f"Packito E2E suite took {timings['total']:.3f}s; "
            f"configured budget is {budget:.3f}s; per-case={timings!r}"
        )


def test_packito_pedagogy_e2e() -> None:
    asyncio.run(_run_all_v1())


if __name__ == "__main__":
    asyncio.run(_run_all_v1())
