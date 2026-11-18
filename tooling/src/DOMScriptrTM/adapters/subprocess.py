"""Generic subprocess server adapter using only the Python standard library."""

from __future__ import annotations

import asyncio
import os
import time
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from ..server import Server

ReadyCheck = Callable[[asyncio.subprocess.Process], Awaitable[None]]


async def wait_for_http(
    url: str,
    *,
    timeout: float = 10.0,
    interval: float = 0.025,
) -> None:
    """Wait for server startup; this is lifecycle readiness, not DOM synchronization."""
    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            await asyncio.to_thread(_probe_http, url)
            return
        except BaseException as exc:
            last_error = exc
            await asyncio.sleep(interval)
    raise TimeoutError(f"server did not become ready at {url!r}") from last_error


@asynccontextmanager
async def subprocess_server(
    command: Sequence[str],
    *,
    urls: Mapping[str, str] | str,
    ready: ReadyCheck | None = None,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    terminate_timeout: float = 5.0,
    stdout: Any = None,
    stderr: Any = None,
) -> AsyncIterator[Server]:
    """Start any executable and own its lifecycle for the duration of a Run."""
    if not command:
        raise ValueError("command must not be empty")

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdout=stdout,
        stderr=stderr,
    )
    try:
        if ready is not None:
            await ready(process)
        yield Server.coerce(urls)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=terminate_timeout)
            except TimeoutError:
                process.kill()
                await process.wait()


def _probe_http(url: str) -> None:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=0.5):
        return
