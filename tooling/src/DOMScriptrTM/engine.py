"""Worker-level Playwright and Browser lifetime."""

from __future__ import annotations

from typing import Any, Mapping

from playwright.async_api import Browser, Playwright, async_playwright

from .diagnostics import Diagnostics
from .errors import LifecycleError
from .run import Run
from .server import ServerStarter


class Engine:
    """Reuse one browser across many sequential scenario Runs."""

    def __init__(
        self,
        *,
        browser: str = "chromium",
        headless: bool = True,
        slow_mo: float | None = None,
        launch_options: Mapping[str, Any] | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        self.browser_name = browser
        self.headless = headless
        self.slow_mo = slow_mo
        self.launch_options = dict(launch_options or {})
        self.diagnostics = diagnostics
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise LifecycleError("Engine must be entered before using its Browser")
        return self._browser

    async def __aenter__(self) -> "Engine":
        if self._playwright is not None:
            raise LifecycleError("Engine cannot be entered twice")

        playwright = await async_playwright().start()
        self._playwright = playwright
        try:
            try:
                browser_type = getattr(playwright, self.browser_name)
            except AttributeError as exc:
                raise ValueError(
                    "browser must be one of: chromium, firefox, webkit"
                ) from exc

            options = dict(self.launch_options)
            options.setdefault("headless", self.headless)
            if self.slow_mo is not None:
                options.setdefault("slow_mo", self.slow_mo)
            self._browser = await browser_type.launch(**options)
            return self
        except BaseException:
            self._playwright = None
            await playwright.stop()
            raise

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        close_error: BaseException | None = None
        if browser is not None:
            try:
                await browser.close()
            except BaseException as error:
                close_error = error
        if playwright is not None:
            try:
                await playwright.stop()
            except BaseException:
                if exc is None and close_error is None:
                    raise
        if exc is None and close_error is not None:
            raise close_error
        return False

    def run(
        self,
        start_server: ServerStarter | None = None,
        *,
        urls: Mapping[str, str] | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> Run:
        """Create a scenario context over this Engine's reusable Browser."""
        return Run(
            browser=self.browser,
            start_server=start_server,
            urls=urls,
            diagnostics=diagnostics or self.diagnostics,
        )
