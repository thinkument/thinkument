# Fully-funked black-box runs

## Purpose

`run_funked_black_box_from_program(...)` is the one-shot `run_from_here` facade for executing a resolved `P / SM / C` flow from start to canonical completion without yielding to manual I/O.

It is intended for experimentation, instrumentation, batch evaluation, generated analyses, and service-hosted jobs where the entire authored program must be satisfiable by configured chain-reaction fillers.

It does not create a second runtime model. It uses the same:

- ThinkProgram and session-metadata resolution;
- ordinary live-session creation;
- role modulation;
- controller dispatch machinery;
- canonical event tape;
- chainreactionTM runtime;
- dispatch staleness boundary;
- lifecycle callbacks;
- outputs/report surfaces; and
- deletion surface

as an ordinary live run.

Conceptually:

```text
resolve P / SM / C
      |
      v
static fully-funked contract preflight
      |
      v
create ordinary live session
      |
      v
one empty manual STEP
      |
      v
ordinary chainreactionTM generated STEP dispatches
      |
      +----> ATCOMPLETION
      |          |
      |          v
      |       success
      |
      +----> manual frontier / no progress /
             cap / semantic exhaustion /
             systematic failure
                    |
                    v
                  error
```

The important design law is:

```text
black-box run != a second engine mode

black-box run =
    ordinary live session
    + fully-funked static contract
    + one ordinary starting STEP
    + ordinary generated chain dispatches
    + mandatory ATCOMPLETION postcondition
    + default cleanup
```

---

## Public entry point

```python
run_funked_black_box_from_program(
    *,
    program,
    program_language,
    initial_parameter_overrides=None,
    session_metadata=None,
    roles=None,
    role_mismatch_policy=None,
    identity_id=None,
    threaded_callbacks=None,
    retain_session=False,
)
```

The facade intentionally remains server-agnostic.

Service-specific concerns such as:

- durable black-box job records;
- authenticated ownership;
- Celery execution;
- durable epsilon-message persistence;
- notification delivery;
- result indexing; and
- query APIs

belong above this facade in the hosting layer.

---

## Resolution happens before P / SM contract validation

Black-box validation is defined over the **resolved launch surfaces**, not the unbound source dictionaries.

The facade first applies the same launch machinery used by ordinary session creation:

1. jointly route `initial_parameter_overrides` across the ThinkProgram and session-metadata symbol surfaces;
2. bind session-metadata symbols;
3. apply explicit `roles` and `role_mismatch_policy` overlays when supplied.

Conceptually:

```text
authored P
authored SM
launch C
   |
   v
shared launch resolution
   |
   +----> resolved P
   |
   +----> resolved SM
              |
              v
      chainreactionTM normalization
              |
              v
      black-box static contract
```

Only after those launch surfaces are resolved does the facade normalize `chainreactionTM` configuration and validate the fully-funked contract.

This matters because `C` can change effective launch values. It also means a black-box configuration known to be invalid can fail before allocating a temporary live session.

---

## Static fully-funked contract

The v1 static receipt kind is:

```text
funked_black_box_contract_v1
```

For every role authored on resolved `P`:

1. the role must exist in resolved `SM.roles`;
2. chainreactionTM must be enabled;
3. the role must occur in the normalized chain-reaction role schedule;
4. the role must have a non-null normalized funk filler configuration.

Failure raises:

```text
FunkedBlackBoxContractError
```

before live-session allocation.

The exception carries `.report` with:

```text
{
  kind,
  ok,
  chainreaction_enabled,
  program_roles,
  session_metadata_roles,
  scheduled_roles,
  missing_program_roles_from_session_metadata,
  missing_program_roles_from_chainreaction_schedule,
  unfunkable_program_roles,
  extra_session_metadata_roles,
  extra_scheduled_roles
}
```

Extra session-metadata roles or scheduled roles are diagnostic only. They do not invalidate the black-box contract.

### Role discovery

The contract scanner reads role declarations from the current logical-widget role seams and also scans compatible step-level surfaces:

```text
widget.role
widget.roles

step.role
step.roles

step.overrides.role
step.overrides.roles
```

This prevents the black-box safety contract from silently weakening merely because a role declaration moves from a logical widget definition to a step appearance.

---

## Why static validation is not sufficient

A complete role sheet cannot prove runtime progress.

For example:

- a filler can return a no-op;
- a filler can repeatedly produce semantically invalid data;
- semantic retry limits can be exhausted;
- generated-fill limits can be reached;
- a program can expose an unroled manual frontier;
- a runtime condition can leave no writable pending datum for the selected role;
- a chain-reaction version can decide not to continue;
- a dispatch can be rejected; or
- a dispatch can terminate with a systematic error.

Therefore black-box execution has a second invariant:

```text
the actual run must reach canonical ATCOMPLETION
```

A configuration may therefore be:

```text
statically fully-funkable
```

while still being:

```text
runtime incomplete
```

These are deliberately separate failure classes.

---

## Start semantics

After successful static preflight, the facade creates one ordinary live session and reads its current canonical event high-water.

It then submits exactly one initial dispatch:

```text
action = STEP
fill   = {}
signal = null
role   = null
```

with chainreactionTM enabled from resolved session metadata.

That empty STEP is the ordinary controller start of the program.

It therefore participates in the same normal execution law:

```text
controller start
      |
      v
datum lifecycle activity / epsilon emission
      |
      v
controller end
```

After the initial dispatch closes, chainreactionTM repeatedly selects scheduled pending roles and performs ordinary generated STEP dispatches.

There is no privileged black-box path that bypasses the controller, datum lifecycle, authorization, event tape, or normal generated-dispatch machinery.

---

## Generated dispatches

Every chain-reaction continuation remains an ordinary dispatch.

Generated dispatches use the highest-facade identity convention:

```text
funkedauto-<generated-role>-<initial-identity>
```

Each generated dispatch therefore still has:

- its own dispatcher identity;
- its selected role;
- ordinary role-aware write authorization;
- an ordinary controller envelope;
- ordinary datum lifecycle execution;
- ordinary canonical event production;
- ordinary live/provisional callback emission; and
- ordinary staleness and dispatch-result semantics.

The black-box facade merely keeps control until either completion or a chain stop condition is reached.

---

## Identity

If no `identity_id` is supplied, the facade creates a black-box identity derived from the allocated session ID.

The initial identity acts as the root identity for generated chain dispatches.

Conceptually:

```text
blackbox-<session-id>
        |
        +----> funkedauto-role-a-blackbox-<session-id>
        |
        +----> funkedauto-role-b-blackbox-<session-id>
        |
        +----> ...
```

A service host may instead provide its own stable per-job identity.

---

## Runtime success

Success requires both:

```text
final_context.kind == "ATCOMPLETION"
```

and:

```text
no rejected/system-error terminal dispatch result
```

The success result kind is:

```text
funked_black_box_run_result_v1
```

and includes:

```text
{
  kind,
  ok,
  session_id,
  session_retained,
  dispatcher_identity_id,
  contract,
  dispatch_result,
  final_context,
  final_context_kind,
  chain_stopped_reason,
  outputs_report,
  events,
  latest_event_seq,
  delete_report?                 # when retain_session=False
}
```

`dispatch_result.chainreactionTM_receipt` remains the authoritative chain receipt for information such as:

- whether chainreactionTM was enabled;
- generated-dispatch counts;
- roles used;
- semantic retry state;
- cap state; and
- stop reason.

`events` is the session's retained canonical event window.

Its size remains governed by ordinary session storage policy. Black-box execution does not introduce an unbounded private event queue.

---

## Runtime failure

A statically valid run that does not reach canonical `ATCOMPLETION` raises:

```text
FunkedBlackBoxRunIncompleteError
```

Its `.report` uses:

```text
funked_black_box_run_error_report_v1
```

and contains the same core runtime information gathered at the stopping point, including:

```text
contract
dispatch_result
final_context
final_context_kind
chain_stopped_reason
outputs_report
events
latest_event_seq
```

The distinction is intentional:

```text
FunkedBlackBoxContractError
    resolved P / SM is known before allocation
    not to represent a fully-funked program

FunkedBlackBoxRunIncompleteError
    the static contract was valid
    but the actual runtime did not finish
```

Other unexpected engine or hosting failures continue to propagate as their own exceptions.

---

## Cleanup and retention

The default is:

```python
retain_session=False
```

The live session is temporary.

On successful completion:

1. final result information is collected;
2. outputs and retained canonical events are read;
3. the live session is deleted;
4. the result is returned.

On ordinary runtime incompletion:

1. the error report is collected;
2. the live session is deleted;
3. `FunkedBlackBoxRunIncompleteError` is raised.

On another runtime exception, the facade performs best-effort cleanup before re-raising.

For trusted diagnostics or hosting inspection:

```python
retain_session=True
```

keeps the allocated session after success or runtime failure.

The caller then owns eventual cleanup through:

```python
delete_live_session(...)
```

Static contract failures occur before live-session allocation, so there is no session to retain or delete.

---

# Live epsilon messages

## Core epsilon law

Datum lifecycle messages emitted while a dispatch is in flight are available through the existing trusted:

```python
threaded_callbacks
```

surface.

They remain distinct from canonical queue polling.

Conceptually:

```text
epsilon
    = live/provisional observation

theta
    = committed canonical event queue
```

An epsilon callback can hear a datum event before the dispatch's controller envelope has completely closed.

The canonical queue remains the sole owner of:

```text
event_seq
```

Therefore the public `run_from_here` membrane presents datum epsilon callbacks with provisional/source-shaped event packets and removes any canonical `event_seq` metadata from that callback copy.

This preserves the invariant:

```text
epsilon says:
    "this happened live on the run-level eps channel (ordered by eps_seq)"

theta says:
    "this was committed at canonical sequence N (ordered by event_seq)"
```

When a widget emits an `owner-only` channel (such as `audit-*`) via `emit(..., record_in_session_queue=False)`, the emission is delivered strictly to `explosion_events_callback` (`eps`) and is not appended to the bounded `_session_events_v1` (`theta`) queue, ensuring high-frequency audit/economics emissions never evict `controller.loop.start` / `controller.loop.end` tridents from `theta`.

---

## Exact dispatch context for epsilon consumers

A single funked run can contain many ordinary dispatches:

```text
initial dispatch
generated dispatch role A
generated dispatch role A
generated dispatch role B
...
```

The same trusted callback object may therefore observe events from several dispatches.

For hosting layers that need to attribute epsilon messages to the exact ordinary dispatch that produced them, the explosion callback object may implement:

```python
observe_dispatch_context_v1(dispatch_context)
```

The highest facade invokes that optional hook immediately before the corresponding ordinary dispatch can produce subsequent datum epsilon messages.

The host-visible dispatch context includes information such as:

```text
session_id
dispatch_action
dispatcher_identity_id
dispatcher_role
before_event_seq
dispatch_context
```

This hook is process-local observation only.

It does **not** alter:

- action packet `A`;
- canonical context `U`;
- datum event packets;
- event sequencing;
- role modulation;
- outputs;
- engine state; or
- session persistence.

It exists so trusted hosting infrastructure can correctly distinguish, for example:

```text
initial black-box dispatch
```

from:

```text
generated solver dispatch
```

even though both reuse the same callback composition.

---

# Django production hosting

## Two production run modalities

At the Django service layer there are two distinct hosting models.

### Interactive production runs

An interactive production Run:

```text
P / SM / C
   |
   v
create live session
   |
   v
persist session
   |
   v
create role-sealed Run bearer(s)
   |
   v
humans and/or funked dispatches continue later
```

The live session itself is durable because the product requires later:

- polling;
- dispatching;
- role-specific access;
- continuation;
- replay;
- owner operations; and
- session deletion.

### Fully-funked black-box runs

A production black-box Run instead behaves as:

```text
persist black-box request
        |
        v
queue one Celery worker
        |
        v
worker calls run_funked_black_box_from_program(...)
        |
        v
temporary ordinary live session
        |
        v
run entire program to completion or failure
        |
        v
delete temporary core session
        |
        v
persist black-box doneness/result summary
```

The black-box service therefore does **not** create interactive `Run` bearer handles.

The durable product object is a `BlackBoxRun` job/request record, not a retained interactive session.

---

## Black-box service record

Each hosted black-box execution receives its own durable black-box Run ID.

The record persists the control-plane information required to understand and query the job:

```text
id
owner
source
starter_id?
client_request_id
request_fingerprint
request_json
status
celery_job_id
final_context_kind
result_summary
failure_json
created_at
started_at
completed_at
updated_at
```

Its lifecycle is:

```text
queued
  |
  v
running
  |
  +----> succeeded
  |
  +----> failed
```

The service record intentionally does not hold a foreign key to a core live session.

A core session used while the worker executes is an implementation detail of the ordinary runtime and is removed by the black-box facade when `retain_session=False`.

---

## Black-box request idempotency

The service requires a caller-supplied:

```text
request_id
```

scoped to the authenticated owner.

The normalized launch request is fingerprinted.

Therefore:

```text
same owner
+ same request_id
+ same normalized request
    -> return the existing BlackBoxRun

same owner
+ same request_id
+ different normalized request
    -> explicit conflict
```

This prevents accidental duplicate batch execution while refusing to reinterpret the same immutable request ID as a different operation.

---

# Direct P / SM / C versus Starter launch

## Direct production launch

The Django service supports a direct authored launch surface:

```text
P
SM
C
roles
role_mismatch_policy
```

Interactive production hosting exposes this through:

```python
Run.objects.create_from_program(...)
```

A black-box request has an equivalent direct launch form and ultimately calls:

```python
run_funked_black_box_from_program(...)
```

inside one worker.

---

## Starter-backed launch

A Django `Starter` is a persisted authenticated launch template.

It stores:

```text
ThinkProgram manifest
+
launch defaults in extras
```

including surfaces such as:

```text
program_language
initial_parameter_overrides
session_metadata
roles
role_mismatch_policy
```

Starter launch resolution is shared between interactive and black-box hosting.

The merge law is:

```text
initial_parameter_overrides
    shallow merge

session_metadata
    deep merge

roles
    deep merge

role_mismatch_policy
    deep merge
```

Conceptually:

```text
Starter P / SM / C defaults
           +
request-time launch overrides
           |
           v
 shared launch-surface resolver
           |
           v
 resolved service launch request
          / \
         /   \
        v     v
 interactive black-box
```

The point of centralizing this logic is that a Starter must not mean one thing when launched interactively and another when launched as a fully-funked batch job.

---

# Shared Django epsilon-message traffic

## Purpose

Interactive production Runs and black-box Runs both need durable access to selected live datum messages.

Those messages may represent application-defined categories such as:

```text
billing.cost
audit.trace
run.log
result.material
human.notification
instrumentation.metric
```

The widget is responsible only for deciding:

```text
when to emit
message type
message content
```

The widget must remain unaware of:

- Django;
- database persistence;
- notification infrastructure;
- query indexing;
- Celery;
- interactive versus black-box hosting; or
- downstream routing policy.

---

## One shared traffic-control entry point

Every hosted datum epsilon message is normalized to:

```text
MSG = {
    type,
    content,
    meta
}
```

and combined with trusted hosting context:

```text
CTX = {
    run_kind,
    run_id,
    owner_id,
    access_id?,
    session_id?,
    request_id?,
    dispatcher_identity_id?,
    dispatcher_role?,
    dispatch_action?,
    ...
}
```

The single shared service entry point is:

```python
run_eps_msg_traffic_control(
    CTX,
    MSG,
)
```

Conceptually:

```text
widget emits epsilon
        |
        v
core threaded callback
        |
        v
Django callback bridge
        |
        v
run_eps_msg_traffic_control(CTX, MSG)
        |
        +------------------------+
        |                        |
        v                        v
durable append-only         secondary routing
message persistence         / notifications
```

The traffic-control function centrally composes subordinate host functions instead of accumulating all future behavior directly in one large function.

Its first responsibilities are:

```text
persist_run_eps_msg(...)
route_run_eps_msg_notifications(...)
```

Future behavior can scale behind those host seams without changing widgets or the core runtime.

---

## Shared persistence model

Both run modalities write to one append-only table.

Each row stores the compact dimensions useful for common querying:

```text
owner
run_kind
run_id

access_id
session_id

dispatch_request_id
identity_id
role
dispatch_action

msg_type
msg_content

event_id
source
form_id
frame_id
span_id
datum_id
signal_kind

emitted_at
observed_at
```

The same table can therefore represent:

```text
interactive production epsilon
```

and:

```text
black-box production epsilon
```

without duplicating persistence logic.

---

## Run identity in epsilon storage

For an interactive production Run:

```text
run_kind = live_io
run_id   = core session ID
```

Using the core session ID means epsilon emitted through different role-sealed bearer handles naturally groups under the same interactive program run.

The bearer used for a particular dispatch can still be retained separately as:

```text
access_id
```

For a black-box execution:

```text
run_kind = black_box
run_id   = BlackBoxRun.id
```

The service therefore has a durable grouping key even though the temporary core session is deleted.

---

## Query efficiency

The durable table is designed around the primary expected query dimensions rather than indexing every metadata column.

Important indexed access paths include:

```text
owner + emitted time

message type + emitted time

run kind + run ID + append order

run kind + message type + emitted time
```

This directly supports queries such as:

```text
all messages for this user

all messages of this type

all messages in this time period

all messages for this interactive run

all messages for this black-box run

all black-box billing messages in this period

all audit messages grouped by run
```

Additional metadata such as:

```text
span_id
datum_id
role
signal_kind
```

remains stored for filtering and diagnostics without imposing an index-write cost on every possible forensic field.

---

## Append-only law

Hosted epsilon persistence is conceptually an append log.

Application code may:

```text
insert
read
filter
group
```

but should not reinterpret historical messages by updating them in place.

This is particularly important when epsilon types are used for:

- billing;
- audit;
- execution traces;
- durable application results; or
- instrumentation.

Deleting a temporary core black-box session must not delete those rows.

Similarly, deleting or ending an interactive live session must not implicitly erase application audit history merely because the underlying runtime object is gone.

For that reason the message table does not depend on a cascading foreign key to the runtime session.

---

# Interactive production epsilon integration

Existing interactive production dispatch already creates a provisional publisher used by the frontend dispatch-progress channel.

The hosted callback composition becomes:

```text
raw engine lifecycle
        |
        v
provisional dispatch publisher
        |
        +----> role-projected ephemeral frontend progress
        |
        v
shared durable epsilon callback
        |
        v
run_eps_msg_traffic_control(...)
```

The two mechanisms have different purposes:

```text
provisional dispatch progress
    short-lived
    request/identity scoped
    frontend-oriented
    role projected

durable epsilon traffic
    append-only
    owner/run queryable
    application-oriented
    persists after dispatch completion
```

They therefore share the same raw lifecycle callback chain without sharing storage semantics.

---

# Black-box epsilon integration

The black-box worker constructs the same shared durable epsilon callback before calling:

```python
run_funked_black_box_from_program(...)
```

The callback remains installed for:

```text
initial STEP
+
all generated chainreactionTM STEP dispatches
```

Because the highest facade reports the active dispatch context before every ordinary generated dispatch, persisted messages can record the actual generated:

```text
role
identity
action
```

rather than attributing an entire chain only to the initial black-box identity.

This makes message streams suitable for later analysis such as:

```text
which role generated this cost?
which generated dispatch emitted this audit event?
which datum and span produced this durable result?
```

---

# Notification routing

Persistence and notification are separate concerns.

The base traffic-control order is:

```text
1. persist message
2. invoke secondary notification/routing hook
```

This ensures the durable application fact is recorded before optional delivery behavior is attempted.

A notification layer can later implement behavior such as:

```text
notify a user that manual input is needed

publish selected messages to websocket/SSE infrastructure

send billing messages to an accounting subsystem

materialize selected result message types elsewhere

forward alert types to email or another messaging system
```

without making datum widgets or `run_from_here` depend on those products.

---

# Service API shape

## Black-box Runs

The production service exposes a dedicated black-box control plane:

```text
POST /black-box-runs/
GET  /black-box-runs/
GET  /black-box-runs/<run-id>/
```

Creation accepts either:

```text
Starter + launch overrides
```

or:

```text
direct P / SM / C
```

but not both in one request.

The endpoint persists the request first and then queues one Celery job to own the complete run.

It does not expose live datum-fill endpoints because a black-box Run is defined precisely by the absence of manual I/O.

---

## Shared epsilon queries

Hosted durable epsilon messages are exposed through an owner-scoped query API such as:

```text
GET /analytics/
```

with filters for dimensions such as:

```text
run_kind
run_id
type
emitted_from
emitted_to
before_id
limit
group_by_run
```

Examples:

```text
/analytics/?type=billing.cost

/analytics/?run_kind=black_box&type=audit.trace

/analytics/?run_kind=live_io&run_id=<session-id>

/analytics/?emitted_from=<ISO>&emitted_to=<ISO>

/analytics/?type=result.material&group_by_run=1
```

The authenticated owner is always an implicit filter.

A caller cannot use this API to inspect another owner's epsilon history merely by knowing a run ID.

---

# Persistence boundary for black-box execution

The service-level statement:

```text
a black-box Run does not persist its session
```

means:

```text
the completed product artifact is not a retained Thinkument session
```

The core facade still executes through an ordinary live session because this is precisely how black-box execution preserves the same runtime semantics as every other run mode.

Under a Django host whose globally installed session repository is database-backed, the temporary core session may therefore exist in that repository while the Celery worker is actively executing.

With:

```python
retain_session=False
```

it is removed before ordinary black-box completion or ordinary incomplete-run propagation.

Therefore the durable black-box artifacts are:

```text
BlackBoxRun request/status
+
durable epsilon messages
```

not:

```text
interactive Run bearers
+
retained ThinkumentSesh
```

If the host ever requires a stronger invariant that the transient engine session must **never touch durable storage even during execution**, that is a separate persistence-architecture feature. It would require a safely scoped per-run repository selection rather than changing the process-global Django repository inside a worker.

That is intentionally outside the black-box execution contract.

---

# Relationship between the two production run modalities

The complete production picture is:

```text
                         authored P / SM / C
                                |
                                v
                     shared launch resolution
                                |
                +---------------+---------------+
                |                               |
                v                               v
       interactive prod Run              black-box prod Run
                |                               |
                v                               v
       retained live session              persisted job request
                |                               |
                v                               v
       role-sealed bearers                  one Celery worker
                |                               |
                v                               v
     many later dispatches               whole funked execution
                |                               |
                +---------------+---------------+
                                |
                                v
                   shared epsilon traffic control
                                |
                +---------------+---------------+
                |                               |
                v                               v
          append-only DB                notification/routing
```

The reusable pieces are therefore deliberately split by responsibility:

```text
core run_from_here
    execution semantics

shared service launch resolver
    Starter/direct P-SM-C launch semantics

prod_runs_w_io
    retained interactive session hosting

prod_runs_black_box_funked
    one-shot worker/job hosting

run_eps_msg_traffic
    shared durable epsilon persistence
    and downstream traffic control
```

---

# Testing expectations

The full feature should retain proof at several layers.

## Core black-box contract tests

Prove:

1. chainreactionTM must be enabled;
2. every program role must exist in resolved session metadata;
3. every program role must appear in the effective schedule;
4. every program role must have a filler configuration;
5. step-local and override role declarations are discovered;
6. extra session-metadata roles remain diagnostic rather than invalid.

## Core black-box integration tests

Use real authored programs to prove:

1. multi-role fully-funked completion;
2. rejection of an authored human-only barrier;
3. static success but runtime no-op incompletion;
4. cleanup when `retain_session=False`;
5. explicit session retention when `retain_session=True`.

## Core live-callback tests

Prove:

1. datum epsilon callbacks are provisional and never expose canonical `event_seq`;
2. canonical queue events retain their canonical sequence;
3. callback composition remains intact;
4. optional `observe_unmodulated_context_v1(...)` forwarding still works;
5. optional `observe_dispatch_context_v1(...)` forwarding works;
6. generated dispatches report their own actual role and identity.

## Shared service launch tests

Prove that Starter resolution has the same semantics for interactive and black-box launching:

```text
C -> shallow merge
SM -> deep merge
roles -> deep merge
role_mismatch_policy -> deep merge
```

## Django black-box E2E tests

Prove:

1. direct P / SM / C launch succeeds;
2. Starter-backed launch succeeds;
3. successful jobs reach `ATCOMPLETION`;
4. the temporary session is not retained afterward;
5. request IDs are idempotent;
6. request-ID payload conflicts are rejected;
7. Run detail is owner-scoped;
8. failures persist durable failure metadata;
9. black-box Runs never create interactive role bearer handles.

## Shared epsilon persistence tests

Prove:

1. message type and content are persisted;
2. compact event metadata is persisted;
3. generated dispatch role and identity are persisted correctly;
4. interactive and black-box messages use the same table;
5. owner filtering prevents cross-owner reads;
6. filtering by message type works;
7. filtering by time range works;
8. filtering by run kind and run ID works;
9. grouping by Run works;
10. persistence is append-only;
11. persistence can coexist with the existing provisional frontend callback chain.

## Interactive production regression tests

Existing live-I/O E2Es must continue proving:

- role-sealed bearer access;
- role-projected state;
- ordinary dispatch;
- funked dispatch;
- exact cursor/staleness behavior;
- idempotent request replay;
- provisional dispatch progress;
- hosted frontend shells; and
- persisted session continuity.

Adding durable epsilon traffic must not change any of those contracts.

---

# Final invariant

A fully-funked black-box run is ultimately governed by one simple rule:

```text
Given resolved P / SM / C:

    if P is statically configured so every authored role is funkable,
    create the ordinary runtime,
    start it through one ordinary STEP,
    allow ordinary chainreactionTM dispatches to continue,
    expose ordinary live epsilon along the way,
    and require the resulting runtime to reach ATCOMPLETION.

Anything short of ATCOMPLETION is not a successful black-box run.
```

At the service layer:

```text
interactive Runs persist the session because future I/O is the product.

black-box Runs persist the request, status, result summary, and selected
epsilon application messages because completed execution is the product.
```

Both modalities remain views over the same underlying Thinkument execution model.