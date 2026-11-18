"""Thorough contract + real-browser E2E coverage for DOMScriptrTM.

For environments without Playwright-managed Chromium, set:

    DOMSCRIPTR_BROWSER_EXECUTABLE=/path/to/chromium

Flask is required only for the Flask-backed integration tests.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import pytest
from playwright.async_api import expect

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from DOMScriptrTM import (  # noqa: E402
    Diagnostics,
    Engine,
    Server,
)
from DOMScriptrTM.errors import (  # noqa: E402
    LifecycleError,
    NoPageError,
    ServerContractError,
)
from DOMScriptrTM.run import Run  # noqa: E402

HAS_FLASK = importlib.util.find_spec("flask") is not None


def _launch_options() -> dict[str, object]:
    explicit = os.getenv("DOMSCRIPTR_BROWSER_EXECUTABLE")
    executable = explicit or shutil.which("chromium") or shutil.which("google-chrome")
    return {"executable_path": executable} if executable else {}


def _engine(**kwargs) -> Engine:
    return Engine(launch_options=_launch_options(), **kwargs)


DATA_APP_HTML = """<!doctype html>
<html><body>
  <h1>Local DOM App</h1>
  <label>Value <input aria-label="Value" id="value"></label>
  <button id="copy">Copy</button>
  <output id="out"></output>
  <div id="late"></div>
  <script>
    window.app = {ready: false, copies: 0, errors: []};
    document.querySelector('#copy').addEventListener('click', () => {
      document.querySelector('#out').textContent = document.querySelector('#value').value;
      window.app.copies += 1;
    });
    setTimeout(() => {
      const b = document.createElement('button');
      b.textContent = 'Appears Later';
      b.addEventListener('click', () => window.app.lateClicked = true);
      document.querySelector('#late').appendChild(b);
      window.app.ready = true;
    }, 60);
  </script>
</body></html>"""


async def _load_data_app(client) -> None:
    await client.page.set_content(DATA_APP_HTML)



class _FakeTracing:
    def __init__(self) -> None:
        self.started = False
        self.stopped = 0

    async def start(self, **_kwargs) -> None:
        self.started = True

    async def stop(self, **_kwargs) -> None:
        self.started = False
        self.stopped += 1


class _FakeContext:
    def __init__(self) -> None:
        self.pages = []
        self.closed = False
        self.tracing = _FakeTracing()
        self.handlers: dict[str, list] = {}

    def on(self, event, callback) -> None:
        self.handlers.setdefault(event, []).append(callback)

    async def new_page(self):  # pragma: no cover - unit tests create no fake pages
        raise AssertionError("not expected")

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[_FakeContext] = []

    async def new_context(self, **_kwargs) -> _FakeContext:
        context = _FakeContext()
        self.contexts.append(context)
        return context


# ---------------------------------------------------------------------------
# Server and lifecycle contract: no browser process needed.
# ---------------------------------------------------------------------------


def test_server_contract_is_small_immutable_and_ergonomic() -> None:
    server = Server.coerce("http://127.0.0.1:9999")
    assert server.urls == {"web": "http://127.0.0.1:9999"}

    mapping_server = Server.coerce({"web": "http://a", "admin": "http://b"})
    assert mapping_server.urls["admin"] == "http://b"

    with pytest.raises(TypeError):
        mapping_server.urls["x"] = "http://c"  # type: ignore[index]

    with pytest.raises(ServerContractError):
        Server.coerce(42)  # type: ignore[arg-type]

    with pytest.raises(ServerContractError):
        Server({"": "http://bad"})


@pytest.mark.asyncio
async def test_run_accepts_sync_context_manager_server_starter_and_cleans_it() -> None:
    events: list[str] = []

    @contextmanager
    def starter():
        events.append("enter")
        try:
            yield {"web": "http://sync.example"}
        finally:
            events.append("exit")

    async with Run(browser=_FakeBrowser(), start_server=starter) as run:
        assert run.urls["web"] == "http://sync.example"
        assert events == ["enter"]

    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_run_accepts_async_context_manager_server_starter_and_cleans_it() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def starter():
        events.append("enter")
        try:
            yield Server({"web": "http://async.example"})
        finally:
            events.append("exit")

    async with Run(browser=_FakeBrowser(), start_server=starter) as run:
        assert run.urls == {"web": "http://async.example"}

    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_run_accepts_async_function_direct_mapping_and_existing_urls() -> None:
    async def starter():
        return {"web": "http://awaitable.example"}

    async with Run(browser=_FakeBrowser(), start_server=starter) as run:
        assert run.urls["web"] == "http://awaitable.example"

    async with Run(browser=_FakeBrowser(), urls={"web": "http://existing.example"}) as run:
        assert run.urls["web"] == "http://existing.example"


@pytest.mark.asyncio
async def test_client_contexts_are_isolated_and_run_cleanup_is_complete_and_idempotent() -> None:
    browser = _FakeBrowser()
    async with Run(browser=browser, urls={}) as run:
        alice = await run.client(name="alice")
        bob = await run.client(name="bob")
        assert alice.context is not bob.context
        await alice.close()
        await alice.close()
        assert alice.closed
        assert alice.context.closed
        assert not bob.closed

    assert bob.closed
    assert bob.context.closed
    assert len(browser.contexts) == 2


@pytest.mark.asyncio
async def test_client_requires_a_page_for_js_conveniences() -> None:
    async with Run(browser=_FakeBrowser(), urls={}) as run:
        client = await run.client()
        with pytest.raises(NoPageError):
            await client.js("() => 1")


@pytest.mark.asyncio
async def test_run_rejects_use_outside_lifetime_and_negative_sleep() -> None:
    run = Run(browser=_FakeBrowser(), urls={})
    with pytest.raises(LifecycleError):
        await run.client()

    async with run:
        with pytest.raises(ValueError):
            await run.sleep(-0.01)


def test_run_rejects_ambiguous_server_configuration() -> None:
    with pytest.raises(ValueError):
        Run(
            browser=_FakeBrowser(),
            start_server=lambda: {"web": "http://a"},
            urls={"web": "http://b"},
        )


# ---------------------------------------------------------------------------
# Real browser, app-agnostic frontend semantics. No Flask needed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_browser_dom_actions_dom_assertions_and_three_js_semantics() -> None:
    async with _engine(headless=True) as engine:
        async with engine.run(urls={"web": "about:blank"}) as run:
            client = await run.client(run.urls["web"], name="data-app")
            await _load_data_app(client)

            await expect(client.page.get_by_role("heading", name="Local DOM App")).to_be_visible()
            await client.page.get_by_label("Value").fill("hello")
            await client.page.get_by_role("button", name="Copy").click()
            await expect(client.page.locator("#out")).to_have_text("hello")

            state = await client.js("() => ({copies: window.app.copies})")
            assert state == {"copies": 1}

            await client.check_js("() => window.app.copies === 1")
            with pytest.raises(AssertionError, match="JS check failed"):
                await client.check_js("() => window.app.copies === 999")

            ready = await client.wait_js("() => window.app.ready && 'ready'")
            assert ready == "ready"

            # No sleep: Locator.click waits until this exact action target exists/actionable.
            await client.page.get_by_role("button", name="Appears Later").click()
            await client.check_js("() => window.app.lateClicked === true")


@pytest.mark.asyncio
async def test_real_browser_arbitrary_frontend_scripting_and_multiple_pages_per_identity() -> None:
    second_html = "<h1>Second Page</h1><script>window.site='second'</script>"
    async with _engine(headless=True) as engine:
        async with engine.run(urls={}) as run:
            alice = await run.client("about:blank", name="alice")
            await _load_data_app(alice)
            await alice.page.evaluate(
                """() => {
                    const n = document.createElement('div');
                    n.id = 'injected';
                    n.textContent = 'arbitrary frontend scripting works';
                    document.body.appendChild(n);
                    window.customState = {nested: {value: 17}};
                }"""
            )
            await expect(alice.page.locator("#injected")).to_have_text(
                "arbitrary frontend scripting works"
            )
            assert await alice.js("() => window.customState.nested.value") == 17

            page2 = await alice.open("about:blank")
            await page2.set_content(second_html)
            await expect(page2.get_by_role("heading", name="Second Page")).to_be_visible()
            assert await page2.evaluate("() => window.site") == "second"
            assert len(alice.pages) == 2
            assert alice.page is not page2  # default remains the initial page


@pytest.mark.asyncio
async def test_many_clients_can_act_concurrently_in_one_browser() -> None:
    k = 8
    async with _engine(headless=True) as engine:
        async with engine.run(urls={"web": "about:blank"}) as run:
            clients = await asyncio.gather(
                *(run.client("about:blank", name=f"user-{i}") for i in range(k))
            )
            await asyncio.gather(*(_load_data_app(client) for client in clients))

            async def act(i, client) -> None:
                await client.page.get_by_label("Value").fill(f"v-{i}")
                await client.page.get_by_role("button", name="Copy").click()
                await expect(client.page.locator("#out")).to_have_text(f"v-{i}")
                await client.check_js("() => window.app.copies === 1")

            await asyncio.gather(*(act(i, client) for i, client in enumerate(clients)))
            assert len({id(client.context) for client in clients}) == k


@pytest.mark.asyncio
async def test_engine_reuses_one_browser_across_sequential_runs() -> None:
    async with _engine(headless=True) as engine:
        browser = engine.browser
        async with engine.run(urls={"web": "about:blank"}) as first:
            client = await first.client("about:blank")
            await _load_data_app(client)
            await expect(client.page.locator("h1")).to_have_text("Local DOM App")
        assert engine.browser is browser

        async with engine.run(urls={"web": "about:blank"}) as second:
            client = await second.client("about:blank")
            await _load_data_app(client)
            await expect(client.page.locator("h1")).to_have_text("Local DOM App")
        assert engine.browser is browser


@pytest.mark.asyncio
async def test_failure_diagnostics_capture_trace_and_screenshot_without_changing_scenario_api(
    tmp_path: Path,
) -> None:
    diagnostics = Diagnostics(
        trace_on_failure=True,
        screenshot_on_failure=True,
        artifact_dir=tmp_path,
    )
    async with _engine(headless=True) as engine:
        with pytest.raises(RuntimeError, match="intentional"):
            async with engine.run(urls={"web": "about:blank"}, diagnostics=diagnostics) as run:
                client = await run.client("about:blank", name="failing-client")
                await _load_data_app(client)
                await expect(client.page.locator("h1")).to_have_text("Local DOM App")
                raise RuntimeError("intentional")

    assert (tmp_path / "failing-client-trace.zip").is_file()
    assert (tmp_path / "failing-client-page-0.png").is_file()


# ---------------------------------------------------------------------------
# Real Flask backend + HTML/CSS/JS frontend, including multiple app users.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_FLASK, reason="Flask is a test-only dependency")
@pytest.mark.asyncio
async def test_flask_real_e2e_sync_server_starter_deep_frontend_surface() -> None:
    from DOMScriptrTM.test.example_independent_server_w_frontapp import (
        flask_server,
    )

    async with _engine(headless=True) as engine:
        async with engine.run(flask_server) as run:
            alice = await run.client(run.urls["web"], name="alice")

            await expect(alice.page.get_by_role("heading", name="DOMScriptr fixture")).to_be_visible()
            await alice.wait_js("() => window.app.connected")
            await alice.check_js("() => window.app.errors.length === 0")

            await alice.page.get_by_label("Username").fill("alice")
            await alice.page.get_by_role("button", name="Login").click()
            await expect(alice.page.locator("#whoami")).to_have_text("alice")
            assert await alice.js("() => window.app.user") == "alice"

            # Session-local backend state.
            for _ in range(3):
                await alice.page.get_by_role("button", name="Increment").click()
            await expect(alice.page.locator("#counter")).to_have_text("3")

            # The target is created later. There is deliberately no readiness sleep.
            await alice.page.get_by_role("button", name="Delayed Action").click()
            await alice.check_js("() => window.app.delayedClicks === 1")

            # Another page, same BrowserContext/cookies/session.
            settings = await alice.open(run.urls["web"] + "/settings")
            await expect(settings.locator("#settings-user")).to_have_text("alice")
            await settings.get_by_role("button", name="Save").click()
            assert await settings.evaluate("() => window.settingsSaved") == 1


@pytest.mark.skipif(not HAS_FLASK, reason="Flask is a test-only dependency")
@pytest.mark.asyncio
async def test_flask_many_users_same_app_concurrent_actions_and_cross_user_observation() -> None:
    from DOMScriptrTM.test.example_independent_server_w_frontapp import (
        flask_server,
    )

    k = 6
    names = [f"user-{i}" for i in range(k)]

    async with _engine(headless=True) as engine:
        async with engine.run(flask_server) as run:
            clients = await asyncio.gather(
                *(run.client(run.urls["web"], name=name) for name in names)
            )

            async def login(name, client) -> None:
                await client.page.get_by_label("Username").fill(name)
                await client.page.get_by_role("button", name="Login").click()
                await expect(client.page.locator("#whoami")).to_have_text(name)

            await asyncio.gather(*(login(name, client) for name, client in zip(names, clients)))

            # BrowserContext identity isolation: each client sees a different backend session.
            assert await asyncio.gather(*(c.js("() => window.app.user") for c in clients)) == names

            await clients[0].page.get_by_role("button", name="Increment").click()
            await clients[0].page.get_by_role("button", name="Increment").click()
            await clients[1].page.get_by_role("button", name="Increment").click()
            await expect(clients[0].page.locator("#counter")).to_have_text("2")
            await expect(clients[1].page.locator("#counter")).to_have_text("1")
            await expect(clients[2].page.locator("#counter")).to_have_text("0")

            async def send(name, client) -> None:
                await client.page.get_by_label("Message").fill(f"hello from {name}")
                await client.page.get_by_role("button", name="Send").click()

            await asyncio.gather(*(send(name, client) for name, client in zip(names, clients)))

            # Every independent user eventually observes all shared backend messages.
            await asyncio.gather(
                *(expect(c.page.locator(".message")).to_have_count(k) for c in clients)
            )
            for client in clients:
                await client.check_js(f"() => window.app.messages.length === {k}")
                await client.check_js("() => window.app.errors.length === 0")

            # Different route/URL, same per-user session, opened concurrently.
            settings_pages = await asyncio.gather(
                *(client.open(run.urls["web"] + "/settings") for client in clients)
            )
            await asyncio.gather(
                *(
                    expect(page.locator("#settings-user")).to_have_text(name)
                    for name, page in zip(names, settings_pages)
                )
            )


@pytest.mark.skipif(not HAS_FLASK, reason="Flask is a test-only dependency")
@pytest.mark.asyncio
async def test_flask_async_server_starter_is_equally_pluggable() -> None:
    from DOMScriptrTM.test.example_independent_server_w_frontapp import (
        flask_server,
    )

    @asynccontextmanager
    async def async_starter():
        with flask_server() as urls:
            yield Server(urls)

    async with _engine(headless=True) as engine:
        async with engine.run(async_starter) as run:
            client = await run.client(run.urls["web"])
            await expect(client.page.locator("h1")).to_have_text("DOMScriptr fixture")
