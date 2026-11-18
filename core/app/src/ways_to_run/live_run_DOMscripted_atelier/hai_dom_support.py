from __future__ import annotations

"""Direct DOM helpers for the production hai opinionation.

These helpers are intentionally test/script conveniences, not a second action
DSL. They only drive and inspect the public DOM emitted by that opinionation.

The ordinary default timeout is deliberately short. DOMScriptr runs local
servers and most waits are causal/event driven, so a state transition that has
not appeared within a few seconds is a useful failure.
"""

import json
import os
import time
from itertools import count
from typing import Any, Mapping

from playwright.async_api import expect


HAI_MODULE = "bootstrap_higher_app/thinkumentJS_app_heartbeat.js"
DEFAULT_HAI_DOM_TIMEOUT_MS = int(os.environ.get("HAI_DOM_TIMEOUT_MS", "120000"))
_REQUESTS = count(1)


def browser_launch_options_v1() -> dict[str, Any]:
    # Reuse the already-proven Playwright launch policy when the sufficience
    # support module is present. Keeping this lazy avoids making HAI depend on
    # that test opinionation at runtime.
    try:
        from ways_to_run.live_run_DOMscripted_atelier.sufficience_dom_support import (
            browser_launch_options_v1 as inherited,
        )
    except Exception:
        options: dict[str, Any] = {}
    else:
        options = dict(inherited())

    # Multi-role pedagogical runs deliberately keep several BrowserContexts
    # alive at once. Chromium may otherwise throttle timers on the pages that
    # are not currently foreground, turning a normal ThinkumentJS poll into a
    # multi-second or even missed E2E transition. These flags affect only the
    # scripted headless browser; production heartbeat cadence and application
    # semantics are unchanged.
    args = list(options.get("args") or [])
    for flag in (
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ):
        if flag not in args:
            args.append(flag)
    options["args"] = args
    return options


async def booted_v1(client) -> None:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    page.set_default_timeout(DEFAULT_HAI_DOM_TIMEOUT_MS)
    page.set_default_navigation_timeout(DEFAULT_HAI_DOM_TIMEOUT_MS)
    await page.locator("[data-thinkument-hai]").wait_for(state="attached")
    await client.wait_js(
        "() => document.querySelector('[data-thinkument-config-id]')?.dataset.thinkumentBooted === '1'",
        timeout=DEFAULT_HAI_DOM_TIMEOUT_MS,
    )


async def summary_v1(client) -> dict[str, Any]:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")
    raw = await page.locator("[data-hai-summary]").text_content()
    return json.loads(raw or "{}")


async def assert_summary_v1(
    client,
    *,
    active: list[str] | None,
    runtime_kind: str = "MANUALFILLNEEDEDSTEP",
    timeout_ms: float = DEFAULT_HAI_DOM_TIMEOUT_MS,
) -> None:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    await page.bring_to_front()

    expected = {
        "runtime_kind": runtime_kind,
        "active_widget_ids": active,
    }

    started = time.monotonic()

    def _elapsed() -> float:
        return time.monotonic() - started

    def _mismatches(actual: dict[str, Any]) -> list[str]:
        rows: list[str] = []

        if actual.get("runtime_kind") != runtime_kind:
            rows.append(
                "runtime_kind: "
                f"expected {runtime_kind!r}, "
                f"got {actual.get('runtime_kind')!r}"
            )

        if actual.get("active_widget_ids") != active:
            rows.append(
                "active_widget_ids: "
                f"expected {active!r}, "
                f"got {actual.get('active_widget_ids')!r}"
            )

        return rows

    try:
        await client.wait_js(
            """(expected) => {
              const node = document.querySelector('[data-hai-summary]');
              if (!node) return false;

              let row;
              try {
                row = JSON.parse(node.textContent || '{}');
              } catch {
                return false;
              }

              return (
                row.runtime_kind === expected.runtime_kind
                && JSON.stringify(row.active_widget_ids)
                   === JSON.stringify(expected.active_widget_ids)
              );
            }""",
            expected,
            timeout=timeout_ms,
        )
    except Exception as exc:
        actual = await summary_v1(client)
        mismatches = _mismatches(actual)

        if not mismatches:
            # A timeout-boundary race can leave the authoritative DOM in the
            # requested state after wait_for_function has already rejected.
            return

        raise AssertionError(
            "HAI summary did not converge before timeout.\n"
            f"elapsed:  {_elapsed():.3f}s\n"
            f"expected: {expected!r}\n"
            f"actual:   {actual!r}\n"
            f"mismatch: {'; '.join(mismatches)}"
        ) from exc

    actual = await summary_v1(client)
    mismatches = _mismatches(actual)

    if mismatches:
        raise AssertionError(
            "HAI summary matched transiently but changed before assertion.\n"
            f"elapsed:  {_elapsed():.3f}s\n"
            f"expected: {expected!r}\n"
            f"actual:   {actual!r}\n"
            f"mismatch: {'; '.join(mismatches)}"
        )


async def assert_latest_contains_v1(client, *needles: str) -> None:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")
    locator = page.locator("[data-hai-latest-trident]")
    await locator.wait_for(state="attached")
    for needle in needles:
        await expect(locator).to_contain_text(str(needle))


async def _set_fill_v1(
    client,
    fill: Mapping[str, Any],
) -> None:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    for datum_id, macro in dict(fill).items():
        if not isinstance(macro, Mapping):
            raise TypeError("HAI DOM helper expects datum -> micro mapping fill")
        for micro_name, value in dict(macro).items():
            include = page.locator(
                "[data-hai-micro-include]"
                f'[data-datum-id="{datum_id}"]'
                f'[data-micro-name="{micro_name}"]'
            )
            editor = page.locator(
                "[data-hai-micro-value]"
                f'[data-datum-id="{datum_id}"]'
                f'[data-micro-name="{micro_name}"]'
            )
            await include.wait_for(state="attached")
            await include.check()
            await editor.fill(json.dumps(value))


async def _dispatch_action_v1(
    client,
    *,
    action: str,
    request_prefix: str,
    timeout_ms: float,
) -> dict[str, Any]:
    """Click one HAI dispatch action and return the packet caused by that click."""

    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    await page.bring_to_front()

    request_id = f"{request_prefix}-{next(_REQUESTS)}"
    await page.locator("[data-hai-request-id]").fill(request_id)

    # The result element persists across dispatches. Waiting merely for a
    # non-null value is therefore only causal for the *first* action on a
    # page; later calls could observe the previous dispatch and return before
    # the click they just issued had completed. Fingerprint the prior rendered
    # packet and require a new non-null packet after this click.
    result_node = page.locator("[data-hai-dispatch-result]")
    before_raw = await result_node.text_content()

    await page.locator(f'[data-hai-action="{action}"]').click()

    await client.wait_js(
        """(beforeRaw) => {
          const node = document.querySelector('[data-hai-dispatch-result]');
          if (!node) return false;

          const raw = node.textContent || '';
          if (raw === (beforeRaw ?? '')) return false;

          try { return JSON.parse(raw || 'null') !== null; }
          catch { return false; }
        }""",
        before_raw or "",
        timeout=timeout_ms,
    )
    raw = await result_node.text_content()
    return json.loads(raw or "null")


async def action_v1(
    client,
    action: str,
    *,
    request_prefix: str = "hai-action",
    timeout_ms: float = DEFAULT_HAI_DOM_TIMEOUT_MS,
) -> dict[str, Any]:
    """Causally dispatch a non-STEP HAI action such as UNDO or REDO."""

    normalized = str(action).strip().upper()
    if normalized == "STEP":
        raise ValueError("use step_v1 for STEP so fill/signal/funked controls are explicit")
    if normalized not in {"UNDO", "REDO"}:
        raise ValueError(f"unsupported HAI action: {action!r}")

    return await _dispatch_action_v1(
        client,
        action=normalized,
        request_prefix=request_prefix,
        timeout_ms=timeout_ms,
    )


async def step_v1(
    client,
    *,
    fill: Mapping[str, Any] | None = None,
    signal: Mapping[str, Any] | None = None,
    funked: bool = False,
    request_prefix: str = "hai",
    timeout_ms: float = DEFAULT_HAI_DOM_TIMEOUT_MS,
) -> dict[str, Any]:
    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    await page.bring_to_front()
    await _set_fill_v1(client, fill or {})

    if signal is not None:
        await page.locator("[data-hai-signal-include]").check()
        await page.locator("[data-hai-signal-datum]").fill(
            str(signal.get("datum_id") or "")
        )
        await page.locator("[data-hai-signal-kind]").fill(
            str(signal.get("kind") or "")
        )
        await page.locator("[data-hai-signal-info]").fill(
            json.dumps(dict(signal.get("info") or {}))
        )

    if funked:
        await page.locator("[data-hai-funked]").check()

    return await _dispatch_action_v1(
        client,
        action="STEP",
        request_prefix=request_prefix,
        timeout_ms=timeout_ms,
    )


__all__ = [
    "DEFAULT_HAI_DOM_TIMEOUT_MS",
    "HAI_MODULE",
    "action_v1",
    "assert_latest_contains_v1",
    "assert_summary_v1",
    "booted_v1",
    "browser_launch_options_v1",
    "step_v1",
    "summary_v1",
]
