"""Optional Uvicorn CLI adapter with no runtime import of uvicorn."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from ..server import Server
from .subprocess import subprocess_server, wait_for_http


@asynccontextmanager
async def uvicorn_server(
    app: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    extra_args: Sequence[str] = (),
    ready_timeout: float = 10.0,
) -> AsyncIterator[Server]:
    """Run ``python -m uvicorn <app>`` and wait until its root URL responds."""
    url = f"http://{host}:{port}"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        app,
        "--host",
        host,
        "--port",
        str(port),
        *extra_args,
    ]

    async def ready(_process) -> None:
        await wait_for_http(url, timeout=ready_timeout)

    async with subprocess_server(command, urls={"web": url}, ready=ready) as server:
        yield server
