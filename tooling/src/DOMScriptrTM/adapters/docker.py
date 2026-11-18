"""Optional Docker CLI adapter; Docker remains entirely outside core."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager

from ..server import Server
from .subprocess import subprocess_server, wait_for_http


@asynccontextmanager
async def docker_server(
    image: str,
    *,
    urls: Mapping[str, str] | str,
    docker_args: Sequence[str] = (),
    command: Sequence[str] = (),
    ready_url: str | None = None,
    ready_timeout: float = 20.0,
) -> AsyncIterator[Server]:
    """Run a disposable Docker container and optionally wait on an HTTP URL."""
    cmd = ["docker", "run", "--rm", *docker_args, image, *command]

    async def ready(_process) -> None:
        if ready_url is not None:
            await wait_for_http(ready_url, timeout=ready_timeout)

    async with subprocess_server(cmd, urls=urls, ready=ready) as server:
        yield server
