"""One isolated browser identity/session backed by one BrowserContext."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any, Callable, Sequence

from playwright.async_api import BrowserContext, Page

from .diagnostics import Diagnostics
from .errors import NoPageError

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class Client:
    """Thin identity/session wrapper; DOM operations remain raw Playwright."""

    def __init__(
        self,
        *,
        context: BrowserContext,
        name: str | None = None,
        diagnostics: Diagnostics | None = None,
        on_close: Callable[["Client"], Any] | None = None,
    ) -> None:
        self.context = context
        self.name = name
        self._page: Page | None = None
        self._closed = False
        self._diagnostics = diagnostics or Diagnostics(
            collect_console_errors=False,
            collect_page_errors=False,
        )
        self._on_close = on_close
        self._events: list[str] = []
        self._trace_started = False
        self._wire_diagnostics()

    @property
    def page(self) -> Page | None:
        """The initial/default page, if one has been opened and remains live."""
        return self._page

    @property
    def pages(self) -> Sequence[Page]:
        """Current live pages owned by this client's BrowserContext."""
        return tuple(self.context.pages)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def diagnostic_events(self) -> tuple[str, ...]:
        return tuple(self._events)

    async def _start_diagnostics(self) -> None:
        if self._diagnostics.trace_on_failure:
            await self.context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )
            self._trace_started = True

    async def open(
        self,
        url: str,
        *,
        wait_until: str = "commit",
        **goto_options: Any,
    ) -> Page:
        """Open a new page and navigate only until commit by default."""
        if self._closed:
            raise NoPageError("cannot open a page on a closed Client")
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until=wait_until, **goto_options)
        except BaseException:
            await page.close()
            raise
        if self._page is None or self._page.is_closed():
            self._page = page
        return page

    async def js(self, expression: str, arg: Any = None) -> Any:
        """Evaluate arbitrary browser JavaScript now and return its value."""
        return await self._require_page().evaluate(expression, arg)

    async def check_js(
        self,
        expression: str,
        arg: Any = None,
        *,
        message: str | None = None,
    ) -> Any:
        """Evaluate now; fail immediately unless the result is truthy."""
        result = await self._require_page().evaluate(expression, arg)
        if not result:
            raise AssertionError(message or f"JS check failed: {expression}")
        return result

    async def wait_js(
        self,
        expression: str,
        arg: Any = None,
        *,
        timeout: float | None = None,
        polling: str | float = "raf",
    ) -> Any:
        """Resume at the first observed truthy evaluation of expression."""
        handle = await self._require_page().wait_for_function(
            expression,
            arg=arg,
            timeout=timeout,
            polling=polling,
        )
        try:
            return await handle.json_value()
        finally:
            await handle.dispose()

    async def _capture_failure(self) -> None:
        if self._closed:
            return
        policy = self._diagnostics
        if not (policy.trace_on_failure or policy.screenshot_on_failure):
            return

        root = policy.path
        root.mkdir(parents=True, exist_ok=True)
        stem = _safe_stem(self.name or f"client-{id(self):x}")

        if policy.screenshot_on_failure:
            for index, page in enumerate(self.pages):
                if page.is_closed():
                    continue
                try:
                    await page.screenshot(
                        path=str(root / f"{stem}-page-{index}.png"),
                        full_page=True,
                    )
                except Exception as exc:  # diagnostics must never mask test failure
                    self._events.append(f"diagnostic screenshot failed: {exc!r}")

        if self._trace_started:
            try:
                await self.context.tracing.stop(path=str(root / f"{stem}-trace.zip"))
                self._trace_started = False
            except Exception as exc:  # diagnostics must never mask test failure
                self._events.append(f"diagnostic trace failed: {exc!r}")

    async def close(self) -> None:
        """Idempotently destroy the full browser identity/session."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._trace_started:
                await self.context.tracing.stop()
                self._trace_started = False
        finally:
            try:
                await self.context.close()
            finally:
                if self._on_close is not None:
                    result = self._on_close(self)
                    if inspect.isawaitable(result):
                        await result

    def _require_page(self) -> Page:
        page = self._page
        if page is None or page.is_closed():
            raise NoPageError(
                "Client has no live default page; call await client.open(url) first"
            )
        return page

    def _wire_diagnostics(self) -> None:
        policy = self._diagnostics

        if policy.collect_console_errors:
            self.context.on("page", self._wire_page)
            for page in self.context.pages:
                self._wire_page(page)
        elif policy.collect_page_errors:
            self.context.on("page", self._wire_page)
            for page in self.context.pages:
                self._wire_page(page)

        if policy.collect_request_failures:
            self.context.on(
                "requestfailed",
                lambda request: self._events.append(
                    f"requestfailed {request.method} {request.url}: "
                    f"{request.failure or 'unknown'}"
                ),
            )

    def _wire_page(self, page: Page) -> None:
        policy = self._diagnostics
        if policy.collect_console_errors:
            page.on(
                "console",
                lambda msg: self._events.append(f"console.error: {msg.text}")
                if msg.type == "error"
                else None,
            )
        if policy.collect_page_errors:
            page.on(
                "pageerror",
                lambda exc: self._events.append(f"pageerror: {exc}"),
            )


def _safe_stem(value: str) -> str:
    return _SAFE_NAME.sub("_", value).strip("._") or "client"
