from __future__ import annotations

"""Direct DOM-scripted P9 integration run through Flask + sufficience.js.

This intentionally does not invoke the dry-run case runner or browser strategy.
P9 is reused only as authored application material (P / SM / C). The script
owns its own direct DOM actions and DOM/JS expectations.

Causal synchronization is deliberately separate from semantic assertions:

    dispatch
        -> canonical after_event_seq
        -> syncTo(after_event_seq) on every client
        -> rendered cursor reaches after_event_seq
        -> assert the semantic DOM projection for each role

No wall-clock sleeps are used.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from playwright.async_api import expect

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes import (  # noqa: E402
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


SUFFICIENCE_MODULE = "test_opinionations/sufficience.js"
SUFFICIENCE_ROOT = (
    '[data-thinkument-sufficience="thinkument_test_sufficience_opinionation_v1"]'
)
SUMMARY = "[data-sufficience-summary]"
ASSERT_TIMEOUT_MS = 5_000


def _launch_options() -> dict[str, object]:
    explicit = os.getenv("DOMSCRIPTR_BROWSER_EXECUTABLE")
    executable = explicit or shutil.which("chromium") or shutil.which(
        "google-chrome"
    )
    return {"executable_path": executable} if executable else {}


async def _booted(client) -> None:
    await expect(client.page.locator(SUFFICIENCE_ROOT)).to_have_count(1)
    await expect(
        client.page.get_by_role(
            "heading",
            name="Thinkument sufficience station",
        )
    ).to_be_visible()


async def _summary(client) -> Mapping[str, Any]:
    raw = await client.page.locator(SUMMARY).text_content()
    value = json.loads(raw or "{}")
    if not isinstance(value, Mapping):
        raise AssertionError(
            f"sufficience summary is not an object: {value!r}"
        )
    return value


async def _assert_summary(
    client,
    *,
    active: list[str] | None,
    runtime_kind: str | None = None,
) -> None:
    """Wait for the requested semantic DOM projection.

    Cursor convergence does not belong here. Every post-dispatch caller first
    crosses the canonical high-water barrier through ``_sync_all``. Keeping
    that transport/render barrier separate from this semantic assertion makes
    failures attributable and avoids testing the same synchronization twice.

    The expectation crosses the Playwright argument boundary as JSON text
    rather than as a compound Python object.
    """

    expected = {
        "active": active,
        "runtimeKind": runtime_kind,
    }
    expected_json = json.dumps(
        expected,
        separators=(",", ":"),
        sort_keys=True,
    )

    try:
        await client.wait_js(
            """(expectedJSON) => {
              const expected = JSON.parse(expectedJSON);

              const node = document.querySelector(
                '[data-sufficience-summary]'
              );
              if (!node) return false;

              let row;
              try {
                row = JSON.parse(node.textContent || '{}');
              } catch {
                return false;
              }

              const actualActive = row.active_widget_ids ?? null;

              const activeOK =
                JSON.stringify(actualActive)
                === JSON.stringify(expected.active);

              const kindOK =
                expected.runtimeKind === null
                || row.runtime_kind === expected.runtimeKind;

              return activeOK && kindOK;
            }""",
            expected_json,
            timeout=ASSERT_TIMEOUT_MS,
        )
    except Exception as exc:
        actual = await _summary(client)
        raise AssertionError(
            "sufficience summary did not converge: "
            f"expected={expected!r}, actual={dict(actual)!r}"
        ) from exc


async def _set_micro(
    client,
    datum_id: str,
    micro_name: str,
    value: Any,
) -> None:
    selector_tail = (
        f'[data-datum-id="{datum_id}"]'
        f'[data-micro-name="{micro_name}"]'
    )
    include = client.page.locator(
        f'[data-sufficience-micro-include="1"]{selector_tail}'
    )
    editor = client.page.locator(
        f'[data-sufficience-micro-value="1"]{selector_tail}'
    )

    await expect(include).to_have_count(1)
    await expect(editor).to_have_count(1)

    await include.check()
    await editor.fill(
        json.dumps(
            value,
            separators=(",", ":"),
        )
    )


async def _wait_outcome(
    client,
    request_id: str,
) -> Mapping[str, Any]:
    outcome = await client.wait_js(
        """(rid) => {
          const read = (selector) => {
            const node = document.querySelector(selector);
            if (!node) return null;

            try {
              return JSON.parse(node.textContent || 'null');
            } catch {
              return null;
            }
          };

          const result = read('[data-sufficience-dispatch-result]');
          if (result && result.request_id === rid) {
            return {
              kind: 'dispatch',
              value: result,
            };
          }

          const local = read('[data-sufficience-local-receipt]');

          if (
            local?.kind === 'thinkument_sufficience_local_error_v1'
          ) {
            return {
              kind: 'local_error',
              value: local,
            };
          }

          if (
            local?.kind
              === 'thinkument_outbound_dispatch_validation_v1'
            && local.ok === false
          ) {
            return {
              kind: 'local_rejection',
              value: local,
            };
          }

          return false;
        }""",
        request_id,
        timeout=ASSERT_TIMEOUT_MS,
    )

    if not isinstance(outcome, Mapping):
        raise AssertionError(
            f"unexpected sufficience outcome: {outcome!r}"
        )

    return outcome


async def _step(
    client,
    *,
    fill: Mapping[str, Mapping[str, Any]] | None = None,
    funked: bool = False,
) -> Mapping[str, Any]:
    for datum_id, micros in dict(fill or {}).items():
        for micro_name, value in dict(micros).items():
            await _set_micro(
                client,
                str(datum_id),
                str(micro_name),
                value,
            )

    request_id = f"p9-dom-{uuid4().hex}"

    await client.page.locator(
        "[data-sufficience-request-id]"
    ).fill(request_id)

    funked_box = client.page.locator(
        "[data-sufficience-funked]"
    )

    if funked:
        await funked_box.check()
    elif await funked_box.is_checked():
        await funked_box.uncheck()

    await client.page.locator(
        '[data-sufficience-action="STEP"]'
    ).click()

    return await _wait_outcome(
        client,
        request_id,
    )


async def _exact_public_step(
    client,
    *,
    user_fill: Mapping[str, Any],
) -> Mapping[str, Any]:
    request_id = f"p9-dom-exact-{uuid4().hex}"

    details = client.page.locator(
        "[data-sufficience-exact-action-composer]"
    )

    if not await details.evaluate(
        "node => Boolean(node.open)"
    ):
        await details.locator("summary").click()

    action = {
        "action": "STEP",
        "userFill": dict(user_fill),
        "userSignal": None,
        "requestId": request_id,
    }

    await client.page.locator(
        "[data-sufficience-exact-action]"
    ).fill(
        json.dumps(
            action,
            separators=(",", ":"),
        )
    )

    await client.page.locator(
        "[data-sufficience-exact-action-dispatch]"
    ).click()

    return await _wait_outcome(
        client,
        request_id,
    )


def _dispatch_value(
    outcome: Mapping[str, Any],
) -> Mapping[str, Any]:
    if outcome.get("kind") != "dispatch":
        raise AssertionError(
            "expected dispatched server receipt, "
            f"got {outcome!r}"
        )

    value = outcome.get("value")

    if not isinstance(value, Mapping):
        raise AssertionError(
            "dispatch outcome has no mapping value: "
            f"{outcome!r}"
        )

    return value


def _after_event_seq(
    result: Mapping[str, Any],
) -> int:
    pocket = result.get("dispatch_concurrency")

    if not isinstance(pocket, Mapping):
        raise AssertionError(
            "dispatch result lacks concurrency pocket: "
            f"{result!r}"
        )

    value = pocket.get("after_event_seq")

    if type(value) is not int:
        raise AssertionError(
            f"after_event_seq is not an int: {value!r}"
        )

    return value


async def _sync_to(
    client,
    event_seq: int,
) -> None:
    """Cross the canonical event/render high-water barrier for one client."""

    await client.page.evaluate(
        """async (wanted) => {
          const root = document.querySelector(
            '[data-thinkument-config-id]'
          );
          const control = root?.thinkumentClientControl;

          if (
            !control
            || typeof control.syncTo !== 'function'
          ) {
            throw new Error(
              'Thinkument browser control syncTo is unavailable'
            );
          }

          await control.syncTo(wanted);
        }""",
        int(event_seq),
    )

    # syncTo establishes the browser-control barrier. Then wait until the
    # opinionation itself has rendered a summary through that same high-water.
    await client.wait_js(
        """(wanted) => {
          const node = document.querySelector(
            '[data-sufficience-summary]'
          );
          if (!node) return false;

          try {
            const row = JSON.parse(
              node.textContent || '{}'
            );
            return Number(row.cursor) >= wanted;
          } catch {
            return false;
          }
        }""",
        int(event_seq),
        timeout=ASSERT_TIMEOUT_MS,
    )


async def _sync_all(
    clients: Mapping[str, Any],
    event_seq: int,
) -> None:
    await asyncio.gather(
        *(
            _sync_to(
                client,
                event_seq,
            )
            for client in clients.values()
        )
    )


def _assert_write_role_rejection(
    outcome: Mapping[str, Any],
) -> None:
    if outcome.get("kind") != "local_rejection":
        raise AssertionError(
            "expected local role rejection, "
            f"got {outcome!r}"
        )

    receipt = outcome.get("value")

    if not isinstance(receipt, Mapping):
        raise AssertionError(
            "local rejection is not a mapping: "
            f"{outcome!r}"
        )

    errors = [
        row
        for row in list(receipt.get("errors") or [])
        if isinstance(row, Mapping)
    ]

    if not any(
        row.get("code") == "write_role_denied"
        for row in errors
    ):
        raise AssertionError(
            "expected write_role_denied, "
            f"got {receipt!r}"
        )


async def scripted_dom_p9_v1(
    run,
) -> Mapping[str, Any]:
    roles = (
        ROLE_MAKER,
        ROLE_REVIEWER,
        ROLE_AUDITOR,
    )

    # Each role receives its own isolated browser context/session.
    values = await asyncio.gather(
        *(
            run.client(
                run.urls[
                    flask_role_url_key_v1(role)
                ],
                name=role,
            )
            for role in roles
        )
    )

    clients = dict(
        zip(
            roles,
            values,
        )
    )

    await asyncio.gather(
        *(
            _booted(client)
            for client in values
        )
    )

    maker = clients[ROLE_MAKER]
    reviewer = clients[ROLE_REVIEWER]
    auditor = clients[ROLE_AUDITOR]

    # ------------------------------------------------------------------
    # Before A1
    # ------------------------------------------------------------------
    #
    # Do not wait on boot-time cursor or active-list representation.
    # Before the first canonical dispatch those are frontend transport /
    # opinionation details. The meaningful invariant is that each page
    # has rendered the unstarted run.
    #
    # This check is intentionally immediate after the sufficience station
    # itself has booted: a broken boot should fail immediately rather than
    # consuming a polling timeout for a state no action can advance.

    initial = await asyncio.gather(
        *(
            _summary(client)
            for client in values
        )
    )

    for role, row in zip(
        roles,
        initial,
    ):
        if row.get("runtime_kind") != "ATSTART":
            raise AssertionError(
                f"role {role!r} did not boot at ATSTART: "
                f"{dict(row)!r}"
            )

    # ------------------------------------------------------------------
    # A1
    # ------------------------------------------------------------------
    #
    # Direct DOM STEP mounts maker daily + public board.
    #
    # Dispatch receipt establishes the canonical high-water. Every role
    # client is then synchronized and rendered through that exact barrier
    # before semantic DOM projection is asserted.

    first = _dispatch_value(
        await _step(maker)
    )
    high = _after_event_seq(first)

    await _sync_all(
        clients,
        high,
    )

    await asyncio.gather(
        _assert_summary(
            maker,
            active=["daily", "board"],
        ),
        _assert_summary(
            reviewer,
            active=["daily", "board"],
        ),
        _assert_summary(
            auditor,
            active=["board"],
        ),
    )

    # ------------------------------------------------------------------
    # A2
    # ------------------------------------------------------------------
    #
    # Reviewer can read daily but cannot write it. This is a local/public
    # preflight rejection, therefore it must not advance canonical event
    # sequence.

    reviewer_before = int(
        (await _summary(reviewer))["cursor"]
    )

    denied = await _step(
        reviewer,
        fill={
            "daily": {
                "representative_number": 9,
                "good_day": True,
            }
        },
    )

    _assert_write_role_rejection(denied)

    reviewer_after = int(
        (await _summary(reviewer))["cursor"]
    )

    assert reviewer_after == reviewer_before

    # ------------------------------------------------------------------
    # A3
    # ------------------------------------------------------------------
    #
    # Public board remains writable/readable under every role projection.

    board = _dispatch_value(
        await _step(
            maker,
            fill={
                "board": {
                    "new_1": 1,
                    "new_2": 3,
                    "new_3": 5,
                }
            },
        )
    )
    high = _after_event_seq(board)

    await _sync_all(
        clients,
        high,
    )

    await asyncio.gather(
        _assert_summary(
            maker,
            active=["daily", "board"],
        ),
        _assert_summary(
            reviewer,
            active=["daily", "board"],
        ),
        _assert_summary(
            auditor,
            active=["board"],
        ),
    )

    # ------------------------------------------------------------------
    # A4
    # ------------------------------------------------------------------
    #
    # Maker closes daily. Reviewer-owned guess becomes the next span.

    daily = _dispatch_value(
        await _step(
            maker,
            fill={
                "daily": {
                    "representative_number": 9,
                    "good_day": True,
                }
            },
        )
    )
    high = _after_event_seq(daily)

    await _sync_all(
        clients,
        high,
    )

    await asyncio.gather(
        _assert_summary(
            maker,
            active=[],
        ),
        _assert_summary(
            reviewer,
            active=["guess"],
        ),
        _assert_summary(
            auditor,
            active=[],
        ),
    )

    # ------------------------------------------------------------------
    # A5
    # ------------------------------------------------------------------
    #
    # Maker has no structured guess editor. The diagnostic exact-public-A
    # DOM surface still proves public preflight denial without exposing
    # lower transport identity/role/cursor controls.

    maker_before = int(
        (await _summary(maker))["cursor"]
    )

    maker_guess_denied = await _exact_public_step(
        maker,
        user_fill={
            "guess": {
                "guess_1_1": 9,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
    )

    _assert_write_role_rejection(
        maker_guess_denied
    )

    maker_after = int(
        (await _summary(maker))["cursor"]
    )

    assert maker_after == maker_before

    # ------------------------------------------------------------------
    # A6
    # ------------------------------------------------------------------
    #
    # Reviewer completes the canonical run through ordinary rendered
    # fields.

    await _assert_summary(
        reviewer,
        active=["guess"],
    )

    done = _dispatch_value(
        await _step(
            reviewer,
            fill={
                "guess": {
                    "guess_1_1": 17,
                    "guess_1_2": 3,
                    "guess_1_3": 5,
                }
            },
        )
    )

    assert done.get("event_kind") == "ATCOMPLETION"
    assert done.get("finished") is True

    high = _after_event_seq(done)

    await _sync_all(
        clients,
        high,
    )

    await asyncio.gather(
        *(
            _assert_summary(
                client,
                active=None,
                runtime_kind="ATCOMPLETION",
            )
            for client in clients.values()
        )
    )

    return {
        "kind": "flask_sufficience_dom_p9_receipt_v1",
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
        script=scripted_dom_p9_v1,
        opinionation=LiveDemoOpinionationSelectionV1(
            module=SUFFICIENCE_MODULE,
            use_installed_default=True,
        ),
        public_view_role=ROLE_MAKER,
        prepare_runtime=(
            register_dry_run_lib_widgets_flows_v1,
        ),
        start_on_create=False,
        headless=True,
        launch_options=_launch_options(),
    )

    assert isinstance(
        receipt.result,
        Mapping,
    )
    assert receipt.result.get("ok") is True


def test_flask_sufficienceDOM_dryrun9() -> None:
    asyncio.run(_run_v1())


if __name__ == "__main__":
    asyncio.run(_run_v1())