"""One scenario lifetime: optional server, URLs, Clients, cleanup, and sleep."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Any, Mapping

from playwright.async_api import Browser

from .client import Client
from .diagnostics import Diagnostics
from .errors import LifecycleError
from .server import Server, ServerStarter


class Run:
    def __init__(
        self,
        *,
        browser: Browser,
        start_server: ServerStarter | None = None,
        urls: Mapping[str, str] | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        if start_server is not None and urls is not None:
            raise ValueError("pass either start_server or urls, not both")
        self.browser = browser
        self._start_server = start_server
        self._configured_urls = dict(urls or {})
        self._diagnostics = diagnostics or Diagnostics(
            collect_console_errors=False,
            collect_page_errors=False,
        )
        self._stack: AsyncExitStack | None = None
        self._clients: set[Client] = set()
        self._entered = False
        self._urls: Mapping[str, str] = MappingProxyType({})

    @property
    def urls(self) -> Mapping[str, str]:
        return self._urls

    async def __aenter__(self) -> "Run":
        if self._entered:
            raise LifecycleError("Run cannot be entered twice")
        self._entered = True
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        try:
            server = await self._enter_server()
            self._urls = server.urls
            return self
        except BaseException:
            await self._stack.aclose()
            self._stack = None
            self._entered = False
            raise

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        failure = exc is not None
        cleanup_errors: list[BaseException] = []

        if failure:
            diagnostic_results = await asyncio.gather(
                *(client._capture_failure() for client in tuple(self._clients)),
                return_exceptions=True,
            )
            cleanup_errors.extend(
                result for result in diagnostic_results if isinstance(result, BaseException)
            )

        close_results = await asyncio.gather(
            *(client.close() for client in tuple(self._clients)),
            return_exceptions=True,
        )
        cleanup_errors.extend(
            result for result in close_results if isinstance(result, BaseException)
        )

        stack = self._stack
        self._stack = None
        self._entered = False
        if stack is not None:
            try:
                await stack.__aexit__(exc_type, exc, tb)
            except BaseException as stack_error:
                if exc is None:
                    raise
                cleanup_errors.append(stack_error)

        if exc is None and cleanup_errors:
            raise cleanup_errors[0]
        return False

    async def client(
        self,
        url: str | None = None,
        *,
        name: str | None = None,
        **context_options: Any,
    ) -> Client:
        """Create one isolated BrowserContext identity, optionally navigating it."""
        self._require_entered()
        context = await self.browser.new_context(**context_options)
        client = Client(
            context=context,
            name=name,
            diagnostics=self._diagnostics,
            on_close=self._clients.discard,
        )
        self._clients.add(client)
        try:
            await client._start_diagnostics()
            if url is not None:
                await client.open(url)
            return client
        except BaseException:
            await client.close()
            raise

    async def sleep(self, seconds: float) -> None:
        """Explicit wall-clock wait for scenarios where elapsed time is the subject."""
        if seconds < 0:
            raise ValueError("sleep seconds must be >= 0")
        await asyncio.sleep(seconds)

    async def _enter_server(self) -> Server:
        if self._start_server is None:
            return Server(self._configured_urls)

        value: Any = self._start_server
        if callable(value):
            value = value()
        if inspect.isawaitable(value):
            value = await value

        stack = self._stack
        assert stack is not None

        if hasattr(value, "__aenter__") and hasattr(value, "__aexit__"):
            value = await stack.enter_async_context(value)
        elif hasattr(value, "__enter__") and hasattr(value, "__exit__"):
            value = stack.enter_context(value)

        if inspect.isawaitable(value):
            value = await value
        return Server.coerce(value)

    def _require_entered(self) -> None:
        if not self._entered:
            raise LifecycleError("Run must be used inside 'async with engine.run(...)'")
