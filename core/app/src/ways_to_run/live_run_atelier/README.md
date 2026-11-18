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
bootstrap_higher_app/thinkumentJS_app_heartbeat.js
```

That module is intentionally opinion-light: it creates the womb runtime,
preserves X, publishes a heartbeat receipt, and exposes loopback on boot. It is
not the minimal forms UI.

The current minimal complete manual DOM station is:

```text
test_opinionations/sufficience.js
```

It renders the current readable/active shells and reaches guarded STEP,
UNDO, REDO, optional signal, and funked STEP through the public ThinkumentJS
loopback. For a visibly interactive demo, select it explicitly.

Opinionation selection never mutates the installed static registry and never
enters session metadata.

## Flask live host

The Flask host is:

```text
think-app/src/ways_to_run/live_run_atelier/flask_demo_launcher.py
```

It overlays C onto P with the existing ThinkProgram mechanism because the local
Flask launch spec consumes one already-effective program, splits SM into normal
metadata/roles/role-mismatch policy, launches through the existing Flask
facade, and exposes the existing role-sealed access handles.

Example:

```bash
cd think-app
PYTHONPATH=src poetry run python -m ways_to_run.live_run_atelier.flask_demo_launcher \
  --source ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes \
  --prepare ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration:register_dry_run_lib_widgets_flows_v1 \
  --opinionation-module test_opinionations/sufficience.js \
  --port 5052
```

Omit `--opinionation-module` to use the installed HAI default. Use
`--no-opinionation` to render only the transport shell with no higher app
opinionation.

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

It imports the same host-neutral P/SM/C contract from `think-app`, but it
launches through `Run.objects.create_from_program(...)` instead of creating a
fake authenticated Starter. That service seam is also what
`create_from_starter(...)` delegates to.

Therefore a Django demo uses the normal service machinery:

```text
P / SM / C
  -> RunManager.create_from_program
  -> core live session persisted through DjangoSessionRepo
  -> role-sealed Run bearer rows
  -> normal runs:run-page / events / dispatch / funked / progress routes
  -> normal ThinkumentJS static composition
```

No demo-only dispatch or polling path is introduced.

See the service-side README for the command and service runtime requirements.

## Authoring sources

Both launchers accept the same source grammar.

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
```
