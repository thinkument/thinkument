from __future__ import annotations

"""Server-agnostic DOM-scripted live-run sandbox.

This layer deliberately knows nothing about Thinkument P/SM/C, dry-run A/E,
Flask, Django, or any frontend opinionation.  It composes DOMScriptrTM into the
small reusable execution shape needed by arbitrary applications:

    one ScriptedDOMAtelierV1 / Playwright Browser per worker
        -> many sequential Runs
            -> one optional pluggable server starter per Run
            -> K isolated BrowserContext-backed Clients
            -> raw Playwright DOM actions/assertions and arbitrary JS reads

A DOM script is ordinary Python receiving the raw DOMScriptr ``Run``.  There is
no second action DSL, selector DSL, expectation DSL, scheduler, or polling
abstraction here.

Fast-path synchronization is event/condition based:

* navigation defaults to DOMScriptr's ``wait_until='commit'``;
* Playwright locators act as soon as their target is actionable;
* Playwright ``expect`` returns as soon as its DOM condition is true;
* ``Client.wait_js`` returns as soon as its JavaScript predicate is truthy;
* wall-clock waiting happens only when a scenario explicitly calls
  ``run.sleep(seconds)``.

For throughput, keep one atelier entered across many scenarios so browser
startup is amortized.  Use multiple Clients for isolated identities and
``asyncio.gather`` whenever independent browser work should proceed in
parallel.  Horizontal scaling remains worker-process scaling.
"""

import argparse
import asyncio
import inspect
import json
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Awaitable, Callable, Mapping, Optional, TypeVar

from DOMScriptrTM import Diagnostics, Engine
from DOMScriptrTM.run import Run


ScriptResultT = TypeVar("ScriptResultT")
ServerStarterV1 = Any
DOMScriptV1 = Callable[[Run], Awaitable[ScriptResultT] | ScriptResultT]


@dataclass(frozen=True, slots=True)
class ScriptedDOMRunReceiptV1:
    """Small host-neutral receipt for one completed DOM script."""

    script_name: str
    urls: Mapping[str, str]
    result: Any = None

    @property
    def kind(self) -> str:
        return "thinkument_scripted_dom_run_receipt_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "script_name": self.script_name,
            "urls": dict(self.urls),
            "result": self.result,
        }


def _script_name_v1(script: DOMScriptV1[Any]) -> str:
    module = str(getattr(script, "__module__", "") or "")
    qualname = str(
        getattr(script, "__qualname__", None)
        or getattr(script, "__name__", None)
        or type(script).__name__
    )
    return f"{module}:{qualname}" if module else qualname


async def _invoke_script_v1(
    script: DOMScriptV1[ScriptResultT],
    run: Run,
) -> ScriptResultT:
    value = script(run)
    if inspect.isawaitable(value):
        return await value
    return value


class ScriptedDOMAtelierV1:
    """Reusable worker-local DOMScriptr Engine for many scripted Runs.

    One instance owns one Playwright Browser for its lifetime. ``run_v1``
    creates one independent DOMScriptr Run, enters the supplied server starter,
    invokes the caller's script, and lets DOMScriptr close all browser clients
    before the server starter is exited.
    """

    def __init__(
        self,
        *,
        browser: str = "chromium",
        headless: bool = True,
        slow_mo: Optional[float] = None,
        launch_options: Optional[Mapping[str, Any]] = None,
        diagnostics: Optional[Diagnostics] = None,
    ) -> None:
        engine_kwargs: dict[str, Any] = {
            "browser": str(browser),
            "headless": bool(headless),
        }
        if slow_mo is not None:
            engine_kwargs["slow_mo"] = float(slow_mo)
        if launch_options is not None:
            engine_kwargs["launch_options"] = dict(launch_options)
        if diagnostics is not None:
            engine_kwargs["diagnostics"] = diagnostics

        self._engine = Engine(**engine_kwargs)
        self._entered = False

    @property
    def engine(self) -> Engine:
        if not self._entered:
            raise RuntimeError(
                "ScriptedDOMAtelierV1 must be entered before accessing engine"
            )
        return self._engine

    async def __aenter__(self) -> "ScriptedDOMAtelierV1":
        if self._entered:
            raise RuntimeError("ScriptedDOMAtelierV1 is already entered")
        await self._engine.__aenter__()
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if not self._entered:
            return False
        try:
            return bool(await self._engine.__aexit__(exc_type, exc, tb))
        finally:
            self._entered = False

    async def run_v1(
        self,
        *,
        script: DOMScriptV1[ScriptResultT],
        start_server: Optional[ServerStarterV1] = None,
        urls: Optional[Mapping[str, str]] = None,
        diagnostics: Optional[Diagnostics] = None,
    ) -> ScriptedDOMRunReceiptV1:
        """Execute one direct DOM/JS scenario and fail at its first failure.

        Supply at most one of ``start_server`` or ``urls``. Omitting both is
        valid: the script may open absolute URLs directly.
        """
        if not self._entered:
            raise RuntimeError("ScriptedDOMAtelierV1 must be entered before run_v1")
        if not callable(script):
            raise TypeError("script must be callable")
        if start_server is not None and urls is not None:
            raise ValueError("supply start_server or urls, not both")

        run_kwargs: dict[str, Any] = {}
        if diagnostics is not None:
            run_kwargs["diagnostics"] = diagnostics

        run_cm = (
            self._engine.run(start_server, **run_kwargs)
            if start_server is not None
            else self._engine.run(urls=dict(urls or {}), **run_kwargs)
        )

        async with run_cm as run:
            result = await _invoke_script_v1(script, run)
            return ScriptedDOMRunReceiptV1(
                script_name=_script_name_v1(script),
                urls=dict(run.urls),
                result=result,
            )


async def run_scripted_dom_once_v1(
    *,
    script: DOMScriptV1[ScriptResultT],
    start_server: Optional[ServerStarterV1] = None,
    urls: Optional[Mapping[str, str]] = None,
    browser: str = "chromium",
    headless: bool = True,
    slow_mo: Optional[float] = None,
    launch_options: Optional[Mapping[str, Any]] = None,
    diagnostics: Optional[Diagnostics] = None,
) -> ScriptedDOMRunReceiptV1:
    """One-shot convenience; suites should normally reuse an atelier."""
    async with ScriptedDOMAtelierV1(
        browser=browser,
        headless=headless,
        slow_mo=slow_mo,
        launch_options=launch_options,
        diagnostics=diagnostics,
    ) as atelier:
        return await atelier.run_v1(
            script=script,
            start_server=start_server,
            urls=urls,
        )


def run_scripted_dom_once_sync_v1(**kwargs: Any) -> ScriptedDOMRunReceiptV1:
    """Synchronous CLI/test convenience around ``run_scripted_dom_once_v1``."""
    return asyncio.run(run_scripted_dom_once_v1(**kwargs))


def resolve_object_ref_v1(ref: str) -> Any:
    raw = str(ref or "").strip()
    module_name, separator, attr_path = raw.partition(":")
    if not separator or not module_name or not attr_path:
        raise ValueError("object reference must be 'python.module:attribute'")

    value: Any = import_module(module_name)
    for part in attr_path.split("."):
        if not part:
            raise ValueError(f"invalid empty attribute in object ref {raw!r}")
        value = getattr(value, part)
    return value


def resolve_dom_script_ref_v1(ref: str) -> DOMScriptV1[Any]:
    value = resolve_object_ref_v1(ref)
    if not callable(value):
        raise TypeError(f"DOM script reference {ref!r} is not callable")
    return value


def resolve_server_starter_ref_v1(ref: str) -> ServerStarterV1:
    value = resolve_object_ref_v1(ref)
    if not callable(value):
        raise TypeError(f"server starter reference {ref!r} is not callable")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=(
            "python -m ways_to_run.live_run_DOMscripted_atelier."
            "_whichserver_agnostic_scripted_DOM_run_launcher"
        ),
        description=(
            "Run one arbitrary DOM script through DOMScriptrTM against an "
            "arbitrary zero-argument server starter."
        ),
    )
    parser.add_argument(
        "--server-starter",
        required=True,
        metavar="MODULE:CALLABLE",
        help=(
            "Zero-argument starter accepted by DOMScriptrTM Run: sync/async "
            "context manager, awaitable/direct starter, or callable returning one."
        ),
    )
    parser.add_argument(
        "--script",
        required=True,
        metavar="MODULE:CALLABLE",
        help="Callable receiving the raw DOMScriptrTM Run.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser instead of using headless Chromium.",
    )
    parser.add_argument(
        "--slow-mo",
        type=float,
        default=None,
        help="Optional Playwright slow_mo for visible debugging only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the completion receipt as JSON.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    receipt = run_scripted_dom_once_sync_v1(
        script=resolve_dom_script_ref_v1(args.script),
        start_server=resolve_server_starter_ref_v1(args.server_starter),
        headless=not bool(args.headed),
        slow_mo=args.slow_mo,
    )
    if args.json_output:
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print(
            "DOM script passed: "
            f"{receipt.script_name} against {dict(receipt.urls)!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DOMScriptV1",
    "ScriptedDOMAtelierV1",
    "ScriptedDOMRunReceiptV1",
    "ServerStarterV1",
    "resolve_dom_script_ref_v1",
    "resolve_object_ref_v1",
    "resolve_server_starter_ref_v1",
    "run_scripted_dom_once_sync_v1",
    "run_scripted_dom_once_v1",
]
