# Live-run atelier: one P / SM / C tape, exchangeable live hosts

The live-run atelier is the manual-interaction sibling of the dry-run atelier.
They share authored run inputs, but they have different jobs.

```text
dry run
    P / SM / C + scripted A + expected E
    -> execute and prove the session automatically

live run
    P / SM / C
    -> launch the session and expose one live browser capability per role
    -> a human or browser drives A interactively through ThinkumentJS
```

The live-run layer does not import dry-run action specs, expectations, case
runners, epsilon/theta proof machinery, or receipt normalization. It reuses only
the same authored ThinkProgram/session inputs.

## Stable live-run tape and host contract

Every live demo starts from:

```text
P   exact ThinkProgram
SM  exact session metadata
C   exact initial parameter / puppeteering overrides
```

`LiveRunTapeV1` is only a copied/validated container. The server-agnostic layer
lives in:

```text
think-app/src/ways_to_run/live_run_atelier/_whichserver_agnostic_demo_launcher.py
```

It owns P/SM/C loading, role extraction, public-role selection, prepare hooks,
frontend-opinionation selection grammar, host-neutral launch receipts, and the
prepare -> launch -> serve -> close lifecycle.

A concrete host implements:

```text
lambda  start_v1(P, SM, C) -> opaque host handle
rho     receipt_v1(handle) -> role-sealed live page/API capabilities
sigma   serve_v1(handle) -> keep the host alive for live I/O
omega   close_v1(handle) -> release host + session resources
```

The host-neutral layer stays in `think-app`. Moving it into
`service` would invert the dependency: the Django service already
composes the app/frontend packages, while the Flask app must not depend upward
on the service.

## Frontend opinionation: what live demos render

Opinionation is a host/browser composition choice, not part of P, SM, or C.
Both live hosts use the same selection rules:

```text
(no flag)
    -> use the one installed aggregate-static default

--opinionation-module LOGICAL_JS_ASSET
    -> use that registered JS/MJS module for this launch only

--no-opinionation
    -> explicitly disable opinionation for this launch only
```

With the HAI package installed, today's singleton default is:

```text
framework-4-services/src/app_pack_mould/js/thinkumentJS_app_heartbeat.js
```

That module creates the womb runtime, preserves X, publishes a heartbeat
receipt, exposes loopback on boot, and renders the selected installed app pack.

Opinionation selection never mutates the installed static registry and never
enters session metadata.

## Flask live host

The Flask host is:

```text
think-app/src/ways_to_run/live_run_atelier/flask_demo_launcher.py
```

It launches through the existing local Flask facade and exposes the existing
role-sealed access handles.

Example:

```bash
cd think-app
PYTHONPATH=src poetry run python -m ways_to_run.live_run_atelier.flask_demo_launcher \
  --source ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes \
  --prepare ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration:register_dry_run_lib_widgets_flows_v1 \
  --opinionation-module test_opinionations/sufficience.js \
  --port 5052
```

If roles are declared, every authored role gets a distinct sealed page URL.
`--public-view-role` selects only the conventional/default handle; it does not
remove the other role capabilities.

## Django service live host

The Django-specific adapter belongs with the service:

```text
service/src/web_RESTful/PSMC_sessions/live_run_atelier/
    README.md
    django_demo_launcher.py
```

It imports the same host-neutral P/SM/C contract from `think-app`, but
launches through the normal service Run facade and serves the normal published
Run page/events/dispatch/funked/progress routes.

No demo-only dispatch or polling path is introduced.

## Scripted live runs: the consumer model

DOM scripting is not a dry-run strategy and not another action language. A DOM
script is ordinary Python receiving the raw DOMScriptr `Run`:

```python
from playwright.async_api import expect


async def scenario(run):
    client = await run.client(run.urls["web"], name="smoke")
    page = client.page
    assert page is not None

    await expect(page.locator("h1")).to_be_visible()
    await page.get_by_role("button", name="Continue").click()
```

The scenario can use all of DOMScriptr/Playwright directly:

```text
run.urls
run.client(...)
run.sleep(...)                 # only when a wall-clock delay is genuinely intended
client.page
client.open(...)
client.js(...)
client.wait_js(...)
client.check_js(...)
Playwright locator / expect
```

For HAI pages, `ways_to_run.live_run_DOMscripted_atelier.hai_dom_support` adds small conveniences
for the stable public HAI DOM:

```text
booted_v1
summary_v1 / assert_summary_v1
step_v1
action_v1
assert_latest_contains_v1
```

Those helpers are optional. They do not hide the DOMScriptr `Run`, create a
selector DSL, or replace Playwright.

### Flask scripted P / SM / C

```bash
python -m ways_to_run.live_run_DOMscripted_atelier.flask_scripted_DOM_run_launcher \
  --source some.python.module \
  --script some.python.dom_scripts:scenario
```

The Flask scripted adapter starts the real local Flask frontend, yields its
role-sealed page URLs to DOMScriptr, runs the scenario, and performs strict
cleanup.

### Django scripted P / SM / C

Django-specific session creation remains owned by `service`. A
consumer wrapper may start the normal Django live launcher, consume its JSON
role-capability receipt, and hand only those page URLs to DOMScriptr. This keeps
DOM execution host-neutral while preserving the real Django published-run
surface.

`framework-4-services` provides exactly that local external-pack convenience via:

```text
thinkument-app-pack-local django-dom
```

The wrapper is development orchestration only; it does not add a new Django
runtime or route.

## Authoring sources

Both live launchers accept the same source grammar.

Conventional module:

```text
--source some.python.module

PROGRAM             required P
SESSION_METADATA    optional SM; missing/None -> {}
PUPPET              optional C; missing/None -> {}
```

Explicit references:

```text
--program module:PROGRAM_NAME
--session-metadata module:SESSION_METADATA_NAME
--overrides module:PUPPET_NAME
```

Runtime registration is repeatable and host-independent:

```text
--prepare module:callable
```

Use `--json` for a machine-readable launch receipt. The default port is `0`, so
the OS chooses a free local port.

## Ownership rules

Keep in `think-app/ways_to_run/live_run_atelier`:

```text
P/SM/C source loading
host-neutral lifecycle
role/default selection
opinionation selection grammar
launch receipts
Flask host adapter
```

Keep in `think-app/ways_to_run/live_run_DOMscripted_atelier`:

```text
DOMScriptr worker/browser orchestration
Flask DOM server adapter
consumer DOM helper functions
script reference loading
```

Keep in `service/.../PSMC_sessions/live_run_atelier`:

```text
Django setup
Django WSGI serving
Run-facade launch/cleanup
Django role URL materialization
```

Keep in `dry_run_higher_dispatch_polling_system`:

```text
A/E grammars
scripted action tapes
epsilon/theta/Q proofs
strategy normalization
browser-E2E proof strategies
```

Keep in `live_vial` / frontend packages:

```text
HTML shell
ThinkumentJS config/shim
static assets
transport contracts
provisional dispatch progress
```

Keep in authored app packs:

```text
widgets
flows/programs
SM/C values
Funk fillers
runtime registration hooks
browser app-pack assets
optional consumer DOM scripts
```
