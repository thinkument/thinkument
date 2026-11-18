from __future__ import annotations

"""Packito-specific DOM helpers for scripted teaching runs.

The generic HAI helper remains app-pack agnostic. Packito owns two small
pedagogical seams:

* the lazy complete context retained on its inspector outer; and
* durable DOM proof markers showing which overridable HAI callables actually
  ran during a real browser session.

Neither seam is a generic Thinkument/HAI runtime contract. They exist so the
teaching pack can prove its own use of the public contract without adding
backend peeks, sleeps, or test-only transport APIs.
"""

from ways_to_run.live_run_DOMscripted_atelier.hai_dom_support import (
    DEFAULT_HAI_DOM_TIMEOUT_MS,
)


_CALLABLE_SHELL_ATTRIBUTES = {
    "notification": "data-packito-callable-notification-count",
    "widgetNotification": "data-packito-callable-widget-notification-count",
    "outers": "data-packito-callable-outers-count",
    "page": "data-packito-callable-page-count",
}

_CALLABLE_SELECTORS = {
    "widget": '[data-hai-widget-card][data-packito-callable-widget="1"]',
    "widgetsContainer": '[data-hai-widgets][data-packito-callable-widgets-container="1"]',
    "noReadWidget": '[data-hai-widget-card][data-packito-callable-no-read="1"]',
    "noWriteWidget": '[data-hai-widget-card][data-packito-callable-no-write="1"]',
}


async def assert_context_contains_v1(
    client,
    *needles: str,
    timeout_ms: float = DEFAULT_HAI_DOM_TIMEOUT_MS,
) -> None:
    """Assert against the retained full HAI context without rendering full JSON.

    Callers first wait for the causal HAI summary they care about. Once that
    summary has rendered, Packito's inspector outer is updated synchronously in
    the same render pass, so another long Playwright polling loop is both
    unnecessary and expensive. In particular, repeatedly JSON-stringifying a
    growing queue/history on every ``wait_for_function`` poll recreates the hot
    path the lazy inspector was designed to remove.

    ``timeout_ms`` remains in the signature for source compatibility with the
    original helper; the causal wait belongs to the preceding summary/dispatch
    assertion, not to this read-only inspection.
    """

    del timeout_ms

    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    await page.bring_to_front()
    report = await page.evaluate(
        """(needles) => {
          const host = document.querySelector('[data-hai-outer="packito_inspector"]');
          const ctx = host?.__thinkumentPackitoContextV1;
          if (!ctx) {
            return {
              ok: false,
              missing: needles.map(String),
              reason: 'packito inspector has no retained HAI context',
              debug: null,
            };
          }

          const haystack = JSON.stringify(ctx);
          const missing = needles
            .map(String)
            .filter((needle) => !haystack.includes(needle));

          return {
            ok: missing.length === 0,
            missing,
            reason: missing.length ? 'needle absent from current retained context' : null,
            debug: {
              role: ctx.session?.role ?? null,
              cursor: ctx.heartbeat?.canonical_cursor ?? null,
              heartbeat: ctx.heartbeat?.kind ?? null,
              runtime_kind: ctx.view?.runtime_kind ?? null,
              active_widget_ids: ctx.view?.active_widget_ids ?? null,
              funk_receipt: ctx.womb?.funk_receipt ?? null,
              next_funkability: ctx.womb?.next_funkability ?? null,
              funk_status: ctx.womb?.funk_status ?? null,
              funk_sequence: ctx.womb?.funk_sequence ?? null,
              latest_semantic_errors: ctx.womb?.latest_semantic_errors ?? null,
            },
          };
        }""",
        [str(needle) for needle in needles],
    )

    if report.get("ok") is True:
        return

    raise AssertionError(
        "Packito retained HAI context did not contain the requested evidence.\n"
        f"missing: {report.get('missing')!r}\n"
        f"reason:  {report.get('reason')!r}\n"
        f"debug:   {report.get('debug')!r}"
    )


async def callable_invocation_count_v1(client, callable_name: str) -> int:
    """Return Packito's durable proof count for one overridable HAI callable.

    Shell-level callables keep a monotonically increasing count because their
    visible notification/card DOM can legitimately be replaced by the next
    canonical theta. Structural callables that describe the current render use
    a stable marker on the current node instead.
    """

    page = client.page
    if page is None:
        raise RuntimeError("client has no page")

    name = str(callable_name)
    if name in _CALLABLE_SHELL_ATTRIBUTES:
        attribute = _CALLABLE_SHELL_ATTRIBUTES[name]
        raw = await page.locator("[data-thinkument-hai]").get_attribute(attribute)
        try:
            return int(raw or "0")
        except ValueError:
            return 0

    selector = _CALLABLE_SELECTORS.get(name)
    if selector is None:
        raise KeyError(
            f"unknown Packito HAI callable {name!r}; expected one of "
            f"{sorted((*_CALLABLE_SHELL_ATTRIBUTES, *_CALLABLE_SELECTORS))!r}"
        )
    return int(await page.locator(selector).count())


async def assert_callable_invoked_v1(
    client,
    callable_name: str,
    *,
    minimum: int = 1,
) -> None:
    """Assert that Packito visibly exercised one HAI app-pack callable."""

    required = int(minimum)
    if required < 1:
        raise ValueError("minimum must be >= 1")

    observed = await callable_invocation_count_v1(client, callable_name)
    if observed >= required:
        return

    raise AssertionError(
        f"Packito HAI callable {callable_name!r} was not proven invoked: "
        f"observed={observed}, required={required}"
    )


__all__ = [
    "assert_callable_invoked_v1",
    "assert_context_contains_v1",
    "callable_invocation_count_v1",
]
