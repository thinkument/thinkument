from __future__ import annotations

"""Focused E2E proof of Packito's complete HAI browser override surface.

The broader ``test_packito_flow_tapes_p1to6_DOMscripted.py`` proves the six teaching P/SM/C tapes.

This file has one narrower job: prove that every overridable HAI callable and
message/outer route Packito claims is actually exercised by the production HAI
opinionation in a real Chromium session.

There are no backend peeks and no sleeps. Dispatch completion, canonical HAI
summaries, role-sealed fresh views, and persistent Packito-only DOM proof
markers provide the causal barriers.
"""

import asyncio
import re
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
    assert_summary_v1,
    booted_v1,
    browser_launch_options_v1,
    step_v1,
)
from packito_fixture.py.DOMscriptr_support import (  # noqa: E402
    assert_callable_invoked_v1,
)
from packito_fixture.py.programs.program4__role_modulation_and_projection import (  # noqa: E402
    PROGRAM as P4,
    PUPPET as C4,
    ROLE_AUDITOR,
    ROLE_MAKER,
    ROLE_REVIEWER,
    SESSION_METADATA as SM4,
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
_NONZERO = re.compile(r"^[1-9][0-9]*$")


async def _boot(run, *, url_key: str = "web", name: str):
    client = await run.client(run.urls[url_key], name=name)
    await booted_v1(client)
    page = client.page
    assert page is not None
    await expect(page.locator("[data-thinkument-hai]")).to_have_attribute(
        "data-hai-app-pack",
        "packito",
    )
    return client


async def _assert_nonzero_attribute(locator, attribute: str) -> None:
    await expect(locator).to_have_attribute(attribute, _NONZERO)


async def script_override_routes_and_role_renderers(run) -> Mapping[str, Any]:
    maker = await _boot(
        run,
        url_key=f"role:{ROLE_MAKER}",
        name="packito-overrides-maker",
    )
    maker_page = maker.page
    assert maker_page is not None
    shell = maker_page.locator("[data-thinkument-hai]")

    # Boot/snapshot already proves the page/outer/container delegation path.
    await assert_callable_invoked_v1(maker, "page")
    await assert_callable_invoked_v1(maker, "outers")
    await assert_callable_invoked_v1(maker, "widgetsContainer")

    # Mount creates both a global and a widget-scoped provisional message.
    # Their visible nodes may later be replaced by theta, so Packito records
    # durable shell counts at the exact callable invocation point.
    await step_v1(maker, request_prefix="override-surface-mount")
    await assert_summary_v1(
        maker,
        active=["maker_choice", "public_board"],
    )
    await assert_callable_invoked_v1(maker, "notification")
    await assert_callable_invoked_v1(maker, "widgetNotification")

    # Dedicated renderer portfolio is live at the same time.
    await expect(
        maker_page.locator('[data-hai-widget-id="maker_choice"]')
    ).to_have_attribute("data-hai-renderer", "packito.choice.v1")
    await expect(
        maker_page.locator('[data-hai-widget-id="public_board"]')
    ).to_have_attribute("data-hai-renderer", "packito.board.v1")

    # Outer powder rules are behavior, not documentation: inspector opts into
    # epsilon; controls explicitly does not.
    inspector_outer = maker_page.locator('[data-hai-outer="packito_inspector"]')
    controls_outer = maker_page.locator('[data-hai-outer="packito_controls"]')
    await _assert_nonzero_attribute(
        inspector_outer,
        "data-packito-outer-inspector-epsilon-count",
    )
    assert (
        await controls_outer.get_attribute(
            "data-packito-outer-controls-epsilon-count"
        )
    ) is None

    # Choice signal exercises a custom message route from a live substrate
    # callback. The custom route owns display and leaves a durable count.
    await maker_page.locator('[data-packito-refresh="maker_choice"]').click()
    await _assert_nonzero_attribute(shell, "data-packito-custom-route-count")
    await expect(maker_page.locator("[data-packito-custom-notice]")).to_have_count(1)

    # Board reexplosion emits a silent metric as well as an ordinary datum
    # message. The silent route must never produce notification DOM.
    await step_v1(
        maker,
        fill={"public_board": {"delta": 4}},
        request_prefix="override-surface-silent-route",
    )
    await expect(
        maker_page.locator(
            '[data-hai-notification="packito.silent_metric"], '
            '[data-hai-widget-notification="packito.silent_metric"], '
            '[data-packito-custom-notice="packito.silent_metric"]'
        )
    ).to_have_count(0)

    # Fresh identities against the same canonical span deterministically prove
    # the no-write and no-read override callables.
    reviewer = await _boot(
        run,
        url_key=f"role:{ROLE_REVIEWER}",
        name="packito-overrides-reviewer",
    )
    auditor = await _boot(
        run,
        url_key=f"role:{ROLE_AUDITOR}",
        name="packito-overrides-auditor",
    )
    await assert_callable_invoked_v1(reviewer, "noWriteWidget")
    await assert_callable_invoked_v1(auditor, "noReadWidget")

    reviewer_page = reviewer.page
    auditor_page = auditor.page
    assert reviewer_page is not None
    assert auditor_page is not None
    await expect(
        reviewer_page.locator('[data-packito-no-write="maker_choice"]')
    ).to_be_visible()
    await expect(
        auditor_page.locator('[data-packito-no-read="maker_choice"]')
    ).to_be_visible()

    return {
        "kind": "packito_override_routes_and_role_renderers_v1",
        "ok": True,
    }


async def script_generic_widget_fallback(run) -> Mapping[str, Any]:
    client = await _boot(run, name="packito-overrides-fallback")
    page = client.page
    assert page is not None

    await step_v1(client, request_prefix="fallback-mount")
    await assert_summary_v1(client, active=["first"])

    await step_v1(
        client,
        fill={
            "first": {
                "choice": "alpha",
                "note": "WHY:first",
            }
        },
        request_prefix="fallback-first",
    )
    await assert_summary_v1(client, active=["second"])

    # P6 intentionally supplies a renderer key the Packito renderer portfolio
    # does not claim. HAI must therefore invoke appPack.callables.widget.
    await assert_callable_invoked_v1(client, "widget")
    fallback = page.locator(
        '[data-hai-widget-id="second"][data-packito-callable-widget="1"]'
    )
    await expect(fallback).to_have_attribute(
        "data-hai-renderer",
        "packito.unclaimed.fallback.v1",
    )

    # The fallback is not merely decorative: it emits the standard micro hooks
    # and can drive a legal dispatch through the same guarded HAI loopback.
    await step_v1(
        client,
        fill={
            "second": {
                "choice": "beta",
                "note": "WHY:second",
            }
        },
        request_prefix="fallback-second",
    )
    await assert_summary_v1(
        client,
        active=None,
        runtime_kind="ATCOMPLETION",
    )

    return {
        "kind": "packito_generic_widget_fallback_v1",
        "ok": True,
    }


async def _run_v1() -> None:
    register_app_pack_v1()

    async with ScriptedDOMAtelierV1(
        headless=True,
        launch_options=browser_launch_options_v1(),
    ) as atelier:
        role_receipt = await run_flask_scripted_dom_in_atelier_v1(
            atelier=atelier,
            tape=live_run_tape_v1(
                program=P4,
                session_metadata=SM4,
                initial_parameter_overrides=C4,
                source="packito.override_surface.roles",
            ),
            script=script_override_routes_and_role_renderers,
            opinionation=OPINIONATION,
            public_view_role=ROLE_MAKER,
            prepare_runtime=(),
            start_on_create=False,
        )
        assert isinstance(role_receipt.result, Mapping)
        assert role_receipt.result.get("ok") is True

        fallback_receipt = await run_flask_scripted_dom_in_atelier_v1(
            atelier=atelier,
            tape=live_run_tape_v1(
                program=P6,
                session_metadata=SM6,
                initial_parameter_overrides=C6,
                source="packito.override_surface.fallback",
            ),
            script=script_generic_widget_fallback,
            opinionation=OPINIONATION,
            prepare_runtime=(),
            start_on_create=False,
        )
        assert isinstance(fallback_receipt.result, Mapping)
        assert fallback_receipt.result.get("ok") is True


def test_packito_complete_override_surface_e2e() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())
