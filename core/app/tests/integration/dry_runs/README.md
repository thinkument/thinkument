# Dry-run atelier: one formalism, exchangeable execution membranes

The dry-run system has one stable language and one exchangeable execution
membrane.

```text
standard dry-run language and proof machinery
    P / SM / C / A / E
    widgets, flows, cases, role expectations, queue/event expectations

exchangeable execution strategy
    how this environment starts a run
    how it applies role-bound A
    how it hears live epsilon
    how it polls committed theta
    how it reads role-projected Q/U
    how it performs funked dispatch
    how it closes the run
```

Permanent law:

```text
same P / SM / C / A / E catalogs
    + different BaseDryRunStrategy implementation
    = same formalism executed through another system layer
```

The dry run is not `run_from_here`, Flask, Django, Python, JavaScript,
ThinkumentJS, Chromium, or a DOM. Those are execution membranes behind the
same formal language.

Current matrix:

```text
1.  base facade backend only
2.  copier proof
3.  Flask facade backend only
4.  Django facade backend only
5.  Flask facade + stateful Python frontend example
6.  Django facade + stateful Python frontend example
7.  Flask facade + real ThinkumentJS, opinionless womb probe
8.  Django facade + real ThinkumentJS, opinionless womb probe
9.  Django facade + real Chromium + real ThinkumentJS + sufficience DOM
10. Flask facade + real Chromium + real ThinkumentJS + sufficience DOM
```

No widget, flow, ordinary case, funked case, A grammar, E grammar, or generic
assertion branches on those concrete strategies.

---

## 1. Formal model

A run starts from:

```text
P   ThinkProgram
SM  session metadata
C   initial parameter / puppeteering overrides
```

A dry-run case applies an ordered role-bound action tape:

```text
A1, A2, ... An
```

and proves E over:

```text
synchronous dispatch receipt
live epsilon packets emitted while dispatch is open
committed theta packets
role-projected theta pages
role-projected Q/U context
```

The P/SM/C/A/E grammar is strategy-independent. A strategy translates that
language into the layer it drives and translates layer-specific observations
back into the same proof vocabulary.

---

## 2. Universal strategy spaces

Every `BaseDryRunStrategy` covers the same lifecycle.

```text
lambda(P, SM, C) -> opaque run handle

gamma(run, role, A) -> standard dispatch result

gamma_f(run, role, A) -> standard dispatch result

epsilon(run, role/request) -> ordered provisional live events

theta.latest(run) -> canonical high-water

theta.poll(run, role, after, identity, limit) -> role-projected page

Q/U(run, role) -> current role-projected session context

omega(run) -> release all run/client resources
```

Live epsilon packets are provisional and never carry canonical `event_seq`.
Theta owns canonical ordering and Q advancement.

Roles are parameters of gamma, gamma_f, epsilon, theta, and Q/U. They are not a
strategy-specific grammar.

---

## 3. Strategy capability is explicit

A higher membrane may make a lower-layer adversarial operation impossible by
design. The base contract therefore has one optional seam:

```text
case_skip_reason_v1(case_name, funked) -> None | reason
```

The default is full support. A strategy may exclude a case only when the case
is semantically unrepresentable at that membrane, never because it is slow,
flaky, inconvenient, or currently broken.

Both real sufficience browser strategies exclude exactly:

```text
dry_run_lib_widgets_flows.P7.dispatch_failure_boundaries
```

because P7 deliberately forges transport-owned cursor/wire facts that a correct
human-facing ThinkumentJS browser must not expose.

P9 remains supported. Its projected-out write is expressed through the
sufficience exact-public-A diagnostic control, which still crosses the normal
`loopback.validateDispatch()` guard and cannot forge identity, role, or cursor.

---

## 4. Ownership layers

### Standard language and proof machinery

```text
src/ways_to_run/dry_run_examples/dry_run_higher_dispatch_polling_system/dry_run_standard_lingo/
```

Owns P/SM/C/A/E execution law, STEP/UNDO/REDO, preflight taxonomy,
controller-envelope assertions, datum-event assertions, role projection,
data-blanket expectations, cursor semantics, epsilon/theta invariants, funked
receipts, and suite failure aggregation.

It does not own HTTP, Django, Flask, Celery, Node, Playwright, Chromium,
ThinkumentJS, DOM selectors, browser identities, or transport request ids.

### Reusable app library

```text
src/ways_to_run/dry_run_examples/dry_run_higher_dispatch_polling_system/dry_run_lib_widgets_flows/
```

Owns widgets, programs, P/SM/C values, ordinary/funked A/E tapes, filler
registrations, and app-specific expectation needles.

### Strategy adapters

```text
think-app/src/ways_to_run/dry_run_examples/dry_run_higher_dispatch_polling_system/dry_run_adapter_strategies/
service/src/web_RESTful/tests/runs/dry_run_proof/
```

Concrete strategies own only launch/close, role identity/capability mapping,
A translation, observation acquisition, and transport/DOM normalization.

---

## 5. Real sufficience browser membrane

Tasks F and G raise the membrane to the actual public browser page.

```text
real server
    -> role-sealed /run/.../page/
    -> real HTML shell + real client config
    -> headless Chromium
    -> wrapper_shim.js
    -> createPortal
    -> createThinkumentApp
    -> womb.js
    -> launch-selected test_opinionations/sufficience.js
    -> rendered DOM
```

There is no fake DOM and no direct call from the strategy to synthetic
`bootThinkument()`.

The server host is exchangeable:

```text
Task F: Django StaticLiveServer
Task G: real threaded local Flask/Werkzeug server
```

Everything above the page URL is shared by
`ThinkumentJSSufficienceBrowserDryRunStrategy`.

---

## 6. Browser lifetime

```text
one strategy
    -> one persistent Node/Playwright host
    -> one Chromium process

one dry-run case
    -> one fresh backend session
    -> one isolated BrowserContext + Page per role
    -> one browser-generated identity per role
    -> fresh DOM / Q / X / poller / storage

case omega
    -> call root.disposeThinkument() on every page
    -> stop ThinkumentJS pollers
    -> close browser contexts
    -> release concrete server/backend resources

strategy omega
    -> close Chromium
    -> close Node host
```

Role pages are booted sequentially inside the persistent browser host. Runtime
behavior after boot is fully multi-client. Sequential boot avoids needless
startup concentration while preserving complete context/page/storage identity
isolation.

### Django omega

Django additionally owns persisted `Starter` / `Run` capability rows and trusted
observer-route registrations. Its omega therefore:

```text
remove trusted provisional observer routes
end the backend session
delete exactly lambda's Run rows by primary key
delete the ephemeral Starter
```

### Flask omega

Flask owns no persisted capability rows. Its omega therefore stays smaller:

```text
browser pages stop first
Werkzeug server.shutdown()
server_close()
join server thread
close_app_sessions(app)
```

The Flask server uses a short `serve_forever()` poll interval rather than
Werkzeug's historical 500 ms default, so one real server per catalog case does
not accumulate avoidable teardown latency.

---

## 7. Browser gamma: A -> DOM action

For visible STEP:

```text
A.user_fill
    -> check datum.micro include control
    -> fill datum.micro JSON textarea

A.user_signal
    -> enable signal
    -> fill datum_id / kind / info

funked
    -> check funked control

request id
    -> fill requestId control

A.action
    -> click STEP / UNDO / REDO
```

STEP, UNDO, and REDO remain first-class visible semantic actions.

The exact-public-A composer is a narrow negative-test escape hatch only for a
target that rendered Q explicitly marks as role-obfuscated. A missing control
for a readable datum is a DOM contract failure and never falls back silently.

Every click still executes:

```text
loopback.validateDispatch(A)
    -> if valid
loopback.dispatch(A)
```

Transport-owned fields remain sealed:

```text
identity_id
role
my_current_event_seq_number
```

---

## 8. Browser theta/Q/U: E comes from rendered client state

`sufficience.js` renders the current inbound blanket at:

```text
[data-sufficience-packet]
```

The strategy reads this DOM packet and reconstructs standard theta/Q/U from the
client's rendered Q, not from a direct server context/events API.

```text
Q.actions
Q.open_action
Q.orphan_informative_events
Q.orphan_ends
    -> visible canonical events

Q.cursor
    -> canonical scanned-through high-water

missing canonical positions inside that interval
    -> role-projection hidden ranges
```

This preserves the same standard theta vocabulary used by every lower strategy.

---

## 9. Browser epsilon has two intentionally different proofs

### Roleful browser epsilon

A `MutationObserver` records each rendered sufficience packet after the click.
That proves the real role page receives/renders epsilon and later reconciles the
same visible provisional events through theta.

```text
DOM click
    -> HTTP dispatch
    -> progress page
    -> ThinkumentJS epsilon dissemination
    -> sufficience rerender
```

For every role-visible provisional event, the strategy proves a later rendered
canonical theta event matches after removing only `event_seq`.

### Privileged generic dry-run epsilon

Some shared E, notably P13 and generated P12 funk receipts, asks for an
unmodulated live observer distinct from the human role page. The dispatch still
executes under the sealed browser role; the privileged lens is observation only.

Django realizes this with a trusted provisional observer route.

Flask already has the equivalent host capability in its normal local adapter:
when the launch asks for `include_unmodulated_access=True`, `_dispatch()` fans
raw provisional callbacks into both:

```text
primary role-sealed progress scope
trusted role=None progress scope
```

The browser strategy points the generic proof port at the run's unmodulated `eps` endpoint (`/run/<access_id>/eps/`).

---

## 10. Decoupled run-level epsilon drain law

The synchronous dispatch result and the run-level `eps` channel are distinct observable surfaces. Under decoupled epsilon architecture (`D40`–`D43`):

1. **`theta` (`GET /run/<access_id>/events/`)**: Exclusively holds committed controller tridents (`Estart` + `Eend` with context snapshots).
2. **`eps` (`GET /run/<access_id>/eps/`)**: Continuous, monotonic run-level stream of widget message emissions (`EpsRow`), decoupled from theta ring buffers and request lifecycle flags.

The real-browser membrane drains `eps` rows while dispatch is in-flight, and performs one final page drain once the dispatch returns:

```text
while dispatch is in-flight:
    drain currently published eps rows

when dispatch result returns:
    drain remaining eps rows for this request/run
    return gamma/gamma_f observation
```

The provisional cursor advances from the progress page's
`next_after_provisional_seq`, even when a page contains no visible rows.

This makes epsilon proof Markovian and closes the generated-funk end-event race.

---

## 11. Canonical synchronization

Healthy correctness depends on the real ThinkumentJS adaptive background poller
plus explicit synchronization to a known canonical high-water.

At proof boundaries the harness calls the public browser control:

```text
root.thinkumentClientControl.syncTo(highWater)
```

That invokes the real app `syncTo()` / poll-pull path. It is not a test-only
state mutation and it does not bypass the server.

The current test bootstrap keeps background polling moderate:

```text
base              1000 ms
dispatch-fast       100 ms
remote activity     250 ms
progress             25 ms
```

Proof synchronization is explicit rather than relying on an artificially hot
background timer.

---

## 12. Task G: Flask-specific lambda

The Flask browser strategy is:

```text
think-app/src/ways_to_run/dry_run_examples/dry_run_higher_dispatch_polling_system/dry_run_adapter_strategies/
    flask_facade_w_thinkumentjs_sufficiencejs_opinionation.py
```

Its lambda performs only host translation:

```text
standard P + C
    -> effective authored ThinkProgram

standard SM
    -> session_metadata / roles / role_mismatch_policy

launch composition
    -> start_on_create=False
    -> include_unmodulated_access=True
    -> expose_typed_exceptions=True
    -> opinionation_module="test_opinionations/sufficience.js"

create_app_for_program(...)
    -> highest-package static composition validation
    -> real Flask app + backend session + opaque access handles

make_server(host, 0, threaded=True)
    -> ephemeral loopback port
    -> real Werkzeug request loop

role access handles
    -> absolute role page URLs

unmodulated access handle
    -> role=None proof page URL
    -> trusted dispatchProgress URL
```

The strategy performs one real HTTP readiness read before Chromium boots. From
that point onward all user-facing reads/actions used by standard E are through
the real browser membrane.

No Flask production endpoint is added or weakened for Task G.

---

## 13. Task G dispatch/error normalization

The DOM/higher-JS path remains identical to Django:

```text
standard A
-> DOM controls
-> loopback.validateDispatch()
-> ThinkumentJS sealed wire packet
-> Flask endpoint
-> standard browser observation
```

The Flask concrete strategy only normalizes host-specific terminal details:

```text
station-guard write_role_denied
    -> standard PermissionError expectation path

Flask HTTP 403
    -> standard PermissionError expectation path

Flask typed 500 packet or aborted proof-progress error
    -> reified standard exception type/message

HTTP 200 / 409 dispatch result
    -> normalize_harmonized_server_receipt_v1(...)
```

No Flask-only receipt key leaks into generic P/SM/C/A/E proof machinery.

---

## 14. What Tasks F/G prove

For every supported shared flow, passing either real-browser strategy proves:

```text
P / SM / C launch
role capabilities
launch-selected sufficience opinionation
real public page
real static asset serving
real Chromium
real wrapper shim
real ThinkumentJS portal
real outbound guard
real browser identity / role sealing
real DOM input edits
real DOM click handlers
real direct/funked dispatch
real provisional progress
real epsilon dissemination + render
real canonical polling/digest/Q
real theta dissemination + render
role-projected DOM state
standard dry-run E reconstructed from the frontend
stable multi-client role behavior
privileged observer kept distinct from roleful browser observation
```

Task F proves that theorem over Django.

Task G proves the same theorem over Flask without changing the catalogs or the
browser membrane.

A different production opinionation still needs its own focused DOM/component
tests, but it can reuse the same lower theorem and does not need to fork the
P/SM/C/A/E catalogs.

---

## 15. What never moves into a concrete strategy

```text
widget registrations
program construction
flow catalogs
case catalogs
expected app event needles
role expectation semantics
cursor symbolic grammar
failure aggregation
canonical controller-envelope proof law
```

Strategies own only:

```text
environment launch/close
client identity/capability mapping
A translation into their membrane
direct/funked execution choice
live observation acquisition
committed observation acquisition
client-state retention
transport/DOM-to-standard normalization
explicit capability exclusions for impossible operations
```

---

## 16. Forever-scalable shape

```text
                         standard dry-run library
                    P / SM / C / A / E / widgets / flows
                                  |
                                  v
                       generic dry-run machinery
                    ordinary + funked + projections
                                  |
                     BaseDryRunStrategy interface
                                  |
          +-----------------------+-------------------------+
          |                       |                         |
          v                       v                         v
   direct backend          server backend-only        server + client
      strategies              strategies                strategies
                                                           |
                                  +------------------------+------------------+
                                  |                                           |
                                  v                                           v
                       reference/synthetic clients                    real browser
                                  |                                           |
                        Python / ThinkumentJS                       ThinkumentJS + DOM
                                  |                                           |
                            Flask / Django                             Flask / Django
```

The permanent abstraction remains:

```text
a standard role-based session-driving and observation formalism
whose execution membrane can be raised to any system layer
without forking the program/flow/expectation library
```
