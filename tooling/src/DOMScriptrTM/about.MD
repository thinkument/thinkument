# DOMScriptrTM

A deliberately thin async-Python orchestration layer over Playwright for running
arbitrary backend + HTML/CSS/JS applications as fast, isolated, multi-client E2E
scenarios.

The central rule is:

> **Wait for state, never for time, unless elapsed time itself is what the test is testing.**

DOMScriptr does not invent a selector language, browser protocol, action DSL,
assertion framework, polling engine, or scheduler. Playwright already owns those
problems well.

---

## Final architecture

```text
worker process
└── Engine                         one reusable Playwright Browser
    ├── Run                        one scenario
    │   ├── optional server        arbitrary pluggable starter
    │   ├── Client "alice"         one isolated BrowserContext
    │   │   ├── Page               tab/window
    │   │   └── Page               another tab/window/site
    │   ├── Client "bob"           independent BrowserContext/session
    │   └── Client K               independent BrowserContext/session
    ├── Run
    └── Run N
```

Formal ownership:

```text
Engine owns Browser
Run    owns optional server + {Client1 ... ClientK}
Client owns exactly one BrowserContext + zero or more Pages
Page   is raw Playwright
```

Therefore:

```text
Client != URL
Client != Page
Client != website

same app + many users  => many Clients
one user + many tabs   => one Client, many Pages
one user + many sites  => one Client, Pages/navigation across sites
```

This is the tightest scalable unit split because browser processes are expensive,
BrowserContexts are deliberately lightweight and isolated, and Pages are cheaper
still. Playwright documents BrowserContexts as cookie/cache-isolated and recommends
explicit context lifecycle management.

---

## Runtime file structure

```text
DOMScriptrTM/
├── __init__.py
├── engine.py
├── run.py
├── client.py
├── server.py
├── diagnostics.py
├── errors.py
├── adapters/
│   ├── __init__.py
│   ├── subprocess.py
│   ├── uvicorn.py
│   └── docker.py
└── test/
    ├── __init__.py
    └── example_independent_server_w_frontapp.py
```


`test/` is example/E2E support, not runtime API.

The earlier rough `core/` and `api.py` layers are intentionally absent: they add an
extra indirection without adding an ownership boundary. `__init__.py` is the public
API.

---

## Public surface

```python
from DOMScriptrTM import (
    Diagnostics,
    Engine,
    Server,
)
```

Intended public API:

```text
Engine(...)
Engine.run(...)

Run.urls
Run.client(...)
Run.sleep(...)

Client.context
Client.page
Client.pages
Client.open(...)
Client.js(...)
Client.check_js(...)
Client.wait_js(...)
Client.close()

Server.urls
Diagnostics(...)
```

Everything else stays raw Playwright/Python:

```text
page.locator(...)
page.get_by_role(...)
page.get_by_label(...)
page.evaluate(...)
expect(...)
context...
asyncio.gather / asyncio.TaskGroup
normal Python sequencing / loops / branches / helpers
```

No DOMScriptr wrapper should be added unless it creates a real lifecycle or semantic
boundary that Playwright does not already provide.

---

## Canonical usage

```python
from DOMScriptrTM import Engine
from playwright.async_api import expect


async def scenario():
    async with Engine(headless=True) as engine:
        async with engine.run(start_server) as run:
            alice = await run.client(run.urls["web"], name="alice")
            bob = await run.client(run.urls["web"], name="bob")

            await alice.page.get_by_label("Email").fill("alice@example.com")
            await alice.page.get_by_role("button", name="Login").click()

            await bob.page.get_by_label("Email").fill("bob@example.com")
            await bob.page.get_by_role("button", name="Login").click()

            await expect(alice.page.get_by_text("Welcome Alice")).to_be_visible()

            state = await alice.js("() => window.app.state")
            await alice.check_js("() => window.app.errors.length === 0")
            await bob.wait_js("() => window.app.connected === true")

            await alice.page.get_by_role("textbox").fill("hello")
            await alice.page.get_by_role("button", name="Send").click()

            await expect(bob.page.locator(".message").last).to_have_text("hello")

            settings = await alice.open(run.urls["web"] + "/settings")
            await settings.get_by_role("button", name="Save").click()

            # Explicit time only when time itself is the scenario condition.
            await run.sleep(5)
            await alice.check_js("() => window.sessionExpired === true")

            await bob.close()
            charlie = await run.client(run.urls["web"], name="charlie")
```

The conceptual `client.kill()` operation from scenario sketches maps to
`await client.close()`. There is intentionally only one destruction verb in the
runtime API.

---

## Fastest-correct execution model

For each requested operation:

```text
requested operation
      |
      v
condition already satisfied? ---- yes ---> execute immediately
      |
      no
      v
wait only for exact required state
      |
      v
execute at first permitted moment
```

Rules:

```text
1. Initial navigation defaults to wait_until="commit".
2. The next Playwright action supplies the real actionability condition.
3. DOM expectations use Playwright web-first expect(...).
4. Arbitrary JS state uses js/check_js/wait_js.
5. No readiness sleeps.
6. No global networkidle synchronization.
7. No custom DOM polling loops.
8. No sleeps hidden inside DOMScriptr.
```

Playwright's locator actions already auto-wait for actionability. Its web assertions
retry until the expected DOM state is reached. `Page.wait_for_function` with
`polling="raf"` provides the generic browser-state wait primitive.

`networkidle` is deliberately not the default: Playwright itself discourages it for
testing and recommends assertions/readiness conditions instead.

---

## Engine

`Engine` is worker/browser lifetime:

```python
async with Engine(
    browser="chromium",
    headless=True,
) as engine:
    ...
```

Owns:

```text
Playwright process/driver lifetime
one Browser
browser launch configuration
```

Visible debugging uses the same semantics:

```python
Engine(headless=False)
Engine(headless=False, slow_mo=250)
```

Browser-specific launch options remain available without growing DOMScriptr:

```python
Engine(
    launch_options={
        "executable_path": "/usr/bin/chromium",
    }
)
```

One Engine should normally be reused for many sequential Runs within one worker.
Horizontal scale uses worker processes, not one browser process per Client.

---

## Run

One `Run` is one scenario lifetime and owns:

```text
optional server lifecycle
server URL mapping
all Clients created by the scenario
failure diagnostic scope
explicit wall-clock sleeps
deterministic cleanup
```

Started server:

```python
async with engine.run(start_server) as run:
    ...
```

Already-running system:

```python
async with engine.run(
    urls={
        "web": "https://app.example.com",
        "admin": "https://admin.example.com",
    }
) as run:
    ...
```

No server and no named URLs is also valid when callers pass absolute URLs directly
to `run.client()` / `client.open()`.

---

## Server starter contract

Core has no Flask/FastAPI/Django/Node/Docker knowledge.

The preferred starter is a context manager that yields only after the server is
actually ready and tears it down on exit:

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def start_server():
    server = await launch_anything()
    try:
        await wait_until_server_ready(server)
        yield {
            "web": "http://127.0.0.1:41001",
            "admin": "http://127.0.0.1:41002",
        }
    finally:
        await stop_server(server)
```

For ergonomic pluggability, `Run` accepts all of these shapes:

```text
async context manager -> Server / Mapping[str, str] / str
sync context manager  -> Server / Mapping[str, str] / str
awaitable              -> Server / Mapping[str, str] / str
direct callable result -> Server / Mapping[str, str] / str
direct value           -> Server / Mapping[str, str] / str
```

A bare string becomes:

```python
{"web": the_string}
```

Context-manager starters are preferred because only they can guarantee automatic
server teardown. Direct returned mappings are appropriate for externally managed or
already-running systems.

Core invariant:

> A starter that claims ownership of startup must not yield until its URLs are ready.

Adapters are optional conveniences only. The runtime contract remains the same for:

```text
Flask
Django
FastAPI/Uvicorn
Node
Go
Rust
subprocesses
containers
remote deployments
anything else that can expose URLs
```

---

## Client

Each `Client` owns exactly one new `BrowserContext`:

```python
alice = await run.client(url, name="alice")
bob = await run.client(url, name="bob")
```

Result:

```text
Browser
├── Context Alice -> Alice cookies/storage/session
└── Context Bob   -> Bob cookies/storage/session
```

The contexts do not share cookies/cache/session state.

A Client may start without a Page:

```python
alice = await run.client(name="alice")
page = await alice.open(url)
```

or create the first Page immediately:

```python
alice = await run.client(url, name="alice")
```

One Client can own many Pages/sites while retaining one browser identity:

```python
settings = await alice.open(url + "/settings")
billing = await alice.open("https://billing.example.com")
```

`client.page` remains the initial/default page. `client.pages` exposes current Pages.
For non-default Pages, use raw Playwright directly.

`Client.close()` is idempotent and closes the BrowserContext, therefore all Pages and
all browser-session state owned by that identity.

---

## The only three custom JS-state primitives

### `js`: read now

```python
value = await client.js("() => window.app.state")
```

Semantics:

```text
evaluate now
return value now
no retry
```

### `check_js`: assert now

```python
await client.check_js("() => window.app.errors.length === 0")
```

Semantics:

```text
evaluate now
truthy -> continue
falsy  -> fail immediately
no retry
```

### `wait_js`: wait until

```python
await client.wait_js(
    """({id}) => window.jobs[id]?.status === "done""" ,
    {"id": 42},
)
```

Semantics:

```text
observe browser predicate
resume at first observed truthy result
```

This is the only generic custom waiting primitive because arbitrary JavaScript state
cannot always be expressed as a DOM locator/assertion.

---

## DOM actions and expectations

Use Playwright directly:

```python
await page.get_by_role("button", name="Send").click()
await page.get_by_label("Username").fill("alice")
await expect(page.locator(".status")).to_have_text("Ready")
```

This naturally allows before/action/after test sequences:

```python
await expect(page.locator("#status")).to_have_text("Idle")
await page.get_by_role("button", name="Run").click()
await expect(page.locator("#status")).to_have_text("Done")
```

or arbitrary JS state:

```python
await client.check_js("() => app.phase === 'idle'")
await page.get_by_role("button", name="Run").click()
await client.wait_js("() => app.phase === 'done'")
```

DOMScriptr must never add its own selector/action/assertion abstraction over these.

---

## Concurrency

Use Python:

```python
async with asyncio.TaskGroup() as tg:
    tg.create_task(alice.wait_js("() => app.ready"))
    tg.create_task(bob.wait_js("() => app.ready"))
    tg.create_task(charlie.wait_js("() => app.ready"))
```

or:

```python
await asyncio.gather(
    alice.page.get_by_role("button", name="Send").click(),
    bob.page.get_by_role("button", name="Send").click(),
)
```

No custom scheduler is needed. This keeps scenario control ordinary Python and makes
multi-client workloads compose naturally.

Scaling units:

```text
within a Run     -> BrowserContext per Client
within a worker  -> one Browser reused across Runs
across CPU/hosts -> worker processes
```

Do not share one Browser object across unrelated OS processes.

---

## Explicit time

Only when elapsed wall-clock time is itself under test:

```python
await page.get_by_role("button", name="Login").click()
await run.sleep(10)
await client.check_js("() => window.sessionExpired")
```

`Run.sleep` is intentionally just validated `asyncio.sleep`; its value is semantic
visibility in scenario code, not additional machinery.

---

## Diagnostics

Normal successful runs do no screenshot/trace artifact work.

Failure artifacts can be enabled without changing scenario code:

```python
from DOMScriptrTM import Diagnostics, Engine

policy = Diagnostics(
    trace_on_failure=True,
    screenshot_on_failure=True,
    artifact_dir="artifacts/dom",
)

async with Engine(diagnostics=policy) as engine:
    ...
```

Optional lightweight collection can record:

```text
console errors
uncaught page errors
failed requests
```

On failure, Playwright tracing is reused rather than reimplemented. A trace contains
action timing, DOM snapshots, screenshots, network data, and source context useful for
before/after inspection.

Diagnostics must never change scenario semantics and should never mask the original
scenario failure.

---

## Cleanup order

Normal or failing scenario:

```text
capture requested failure diagnostics
        |
        v
close all remaining Client BrowserContexts
        |
        v
exit/stop server starter
        |
        v
Run exits
```

Engine exit:

```text
close Browser
    |
    v
stop Playwright
```

`Run` closes remaining Clients concurrently so cleanup remains fast for large K.
`Client.close()` is idempotent, so callers may explicitly close identities early.

---

## Optional adapters

Adapters are convenience only and never alter core contracts:

```text
adapters/subprocess.py -> start any executable
adapters/uvicorn.py    -> run python -m uvicorn
adapters/docker.py     -> run disposable docker container
```

`wait_for_http()` exists only for **server startup readiness**. It is not a browser/DOM
polling mechanism and must not be used as scenario synchronization.

Apps are always free to provide their own starter function instead of using adapters.

---

## Test contract

The complete pytest file covers four layers.

### 1. Pure lifecycle/server contract

```text
Server coercion and immutability
sync context-manager starter
async context-manager starter
awaitable/direct starter
existing URLs
Client BrowserContext isolation
idempotent close
Run cleanup
invalid lifecycle use
```

### 2. Real browser, application-agnostic behavior

```text
raw Playwright DOM actions
Playwright DOM expectations
arbitrary page.evaluate scripting
js / check_js / wait_js semantics
state-driven delayed action without sleeps
multiple Pages in one Client
K Clients concurrently in one Browser
Browser reuse across Runs
failure trace + screenshot
```

### 3. Real Flask + HTML/CSS/JS E2E

The example server is deliberately ordinary Flask/Werkzeug and exercises:

```text
real HTTP backend
real HTML/CSS/JS frontend
login cookie/session identity
server state per user
shared backend state
DOM update loop
multiple clients/users against one app
concurrent actions
cross-user observation
multiple pages/routes in one Client
sync and async server starter forms
```

### 4. Scale shape

The tests create multiple BrowserContexts concurrently and perform simultaneous DOM
operations. Production scale should increase worker processes horizontally rather
than changing core semantics.

---

## Test dependencies and commands

Runtime dependency:

```text
playwright
```

Test/example dependencies:

```text
pytest
pytest-asyncio
flask
```

Install a Playwright browser in normal development environments:

```bash
python -m playwright install chromium
```

Then run tests 

If a system Chromium should be used instead:

```bash
DOMSCRIPTR_BROWSER_EXECUTABLE=/path/to/chromium \
pytest command
```

---

## Permanent ownership boundary

| DOMScriptr | Playwright | Python |
|---|---|---|
| Engine lifetime | Browser | sequencing |
| Run lifetime | BrowserContext | variables |
| server plugging | Page | branching |
| Client lifecycle | locators | loops |
| multi-user structure | DOM actions | helpers |
| JS read-now | actionability | composition |
| JS check-now | web assertions | TaskGroup/gather |
| JS wait-until | browser events | scenario logic |
| cleanup policy | JS execution | |
| diagnostics policy | tracing | |

---

## Do not build

```text
custom selector language
custom locator wrappers
custom DOM polling engine
custom assertion framework
custom browser RPC
scenario DSL
YAML/JSON scenario language
Step/Action/Expectation class hierarchies
React/Vue/Svelte-specific core APIs
backend-framework-specific core APIs
wrappers for ordinary Playwright methods
one browser process per Client
arbitrary readiness sleeps
global network-idle synchronization
custom concurrency scheduler
```

If future functionality can be expressed cleanly with raw Playwright or Python, it
belongs in scenario code, not DOMScriptr core.

---

## Final formalism

```text
Engine
    owns one Browser per worker lifetime

Run
    owns zero-or-one server lifecycle
    owns {Client1 ... ClientK}

Client_i
    owns BrowserContext_i
    owns {Page_i1 ... Page_in}

DOM
    actions/assertions = Playwright directly

JS
    js(f)       = evaluate f now
    check_js(f) = evaluate f now; require truthy
    wait_js(f)  = resume at first observed truthy f

sleep(t)
    = explicit wall-clock wait only
```

> **DOMScriptrTM is a thin async-Python orchestration layer over Playwright: one reusable Browser per worker, one Run per scenario, one isolated BrowserContext per Client identity, any number of Pages/sites per Client, arbitrary pluggable server startup, direct Playwright DOM control, exactly three generic JS-state primitives, deterministic cleanup, optional failure diagnostics, and no waiting beyond the first moment the requested state permits progress.**

Keep the core this small.
