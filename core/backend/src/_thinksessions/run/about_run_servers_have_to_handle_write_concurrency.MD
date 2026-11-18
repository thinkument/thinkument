

### `think-backend/src/_thinksessions/run/_about_run_servers_have_to_handle_write_concurrency.MD`

````markdown
## Dispatch staleness and concurrency boundary

```text
Dispatcher / poller
decentralized index belief: C
        │
        │ dispatch(..., my_current_event_seq_number=C)
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Highest _thinksessions.run.run_from_here façade            │
│                                                               │
│ Process-local per-session serialized boundary                 │
│                                                               │
│ Central index:        A = latest canonical event_seq          │
│ Decentralized belief: C = caller's last observed seq          │
│ Active scope:         form / frame / span                     │
│ Write targets:        T = canonical targets of dispatch       │
│ Target index:         L(t) = last successful change seq       │
│ Scope index:          S = last active-scope change seq        │
│                                                               │
│ C omitted  → unchecked compatibility allow                    │
│ C invalid  → reject invalid_event_cursor                      │
│ C > A      → reject future_event_cursor                       │
│ C = A      → allow at_high_water                              │
│ C < A and S > C                                               │
│            → reject stale_scope_changed                       │
│ C < A and max(L(t) for t in T) > C                            │
│            → reject stale_conflict                            │
│ otherwise  → allow stale_but_disjoint                         │
│                                                               │
│ On a successful committed target write:                       │
│     L(t) = resulting canonical high-water                     │
│                                                               │
│ On movement to another form, frame, or span:                  │
│     S = resulting canonical high-water                        │
└───────────────────────────────────────────────────────────────┘
````

Before this diagram's cursor decision, the façade applies the established role
write guard to both fill and signal targets. Authorization failure raises
`PermissionError`; staleness details are not released to an unauthorized
caller.

Scope invalidation is evaluated before target conflict. This prevents a client
whose cursor predates a form/frame/span transition from writing to a newly
active surface merely because the new surface reuses a datum id.

## Controller trident safety law

Once `controller.loop.start` has been successfully recorded in the canonical
queue, every ordinary in-process Python `Exception` raised during controller
routing, liaison execution, U recovery, or result construction is converted
into one matching `controller.loop.end` packet with:

```text
payload.outcome = "system_error"
payload.system_error.kind = "controller_dispatch_system_error_v1"
```

Callback exceptions are isolated after canonical queue insertion and cannot
break canonical event recording.

This is an ordinary-Exception safety guarantee, not a crash-liveness or sink
transaction guarantee. Hard process death, `SystemExit`, `KeyboardInterrupt`,
machine loss, or canonical queue sink failure may leave an open start. A later
start lets a downstream projector classify the older envelope as interrupted.
It does not establish which engine mutations, if any, survived a hard crash.

Only controller events are required to carry complete `U`. Datum lifecycle and
external events are informative and need not carry `U`. The latest known
complete frontend state is therefore the `U` on the latest controller event in
the retained/replayed stream, not necessarily the payload of the latest event
of any kind.

A normal in-process dispatch has one controller start, zero or more informative
events, and one matching controller end. The start and end share a
`dispatch_id`; every event has its own immutable `event_id` and canonical
`event_seq`.

Informative events emitted while no controller action is open are valid
orphan or between-envelope events.

A semantic validation rejection remains a successful controller outcome and is
reported in `end.payload.result.last_error`. A systematic controller failure is
reported separately in `end.payload.system_error`.

The in-core canonical queue is bounded. “Forward-only” means event sequence and
history order never reverse; it does not mean every event is retained forever.
Applications requiring complete audit history must durably persist canonical
events outside the bounded live queue.

## Required server boundary

**Concurrency is not solved by this façade across processes, and exposing it as
flat server endpoints does not change that.**

Two processes can validate against the same central index `A` before either
commits. One dispatch may then commit and make the other stale after the second
dispatch has already passed its process-local validation.

The server layer mapping dispatches to a session must therefore enforce
sequential access with an appropriate distributed per-session lock,
transaction, actor, queue, compare-and-swap primitive, or equivalent mechanism.

That boundary must span:

1. loading the session and canonical high-water `A`;
2. loading the scope and target last-changed index;
3. resolving canonical targets `T`;
4. checking caller cursor `C`;
5. executing the direct dispatch or complete chain reaction;
6. assigning canonical event sequences;
7. updating scope and target change indexes;
8. committing the engine mutation, events, high-water, and indexes atomically.

It must also cover session migration and process restart.

Server transaction atomicity is also what determines whether a hard process
failure can leave a durable partial engine mutation. The core controller
envelope guarantee alone does not provide crash rollback.

The highest façade intentionally does not choose a persistence repository or
restore/save the scope and target indexes automatically. Repository selection
and transaction ownership belong to the hosting layer.

The Django coordinator restores the persisted index only after acquiring the
authoritative session-row lock and cold-loading that row. It then invokes the
ordinary highest-façade dispatch while holding the same core process-local
session lock, explicitly checkpoints the complete opaque runtime, persists the
updated index, stores the immutable request receipt, and commits everything
through the outer transaction.

The explicit opaque-runtime checkpoint is mandatory even when the core
session's ordinary manual-I/O persistence policy is `"disabled"`. That core
policy controls standalone core persistence behavior; it does not authorize a
hosting transaction to commit only a scalar event high-water while retaining
an older engine blob.

During one dispatch, queue insertion may advance the database high-water scalar
before the logical action has reached its final opaque-runtime checkpoint.
Those scalar updates remain inside the same outer transaction. Before commit,
the coordinator must persist one complete engine blob whose retained queue and
next sequence position encode exactly the same high-water.

Transaction rollback alone is not sufficient when the failed operation already
mutated process-local runtime objects. The server must also invalidate the
complete session representation held by the repository/runtime layer.

The recovery invariant is:

```text
after aborted transaction:
    durable opaque blob == pre-operation blob
    durable high-water == pre-operation high-water
    no request receipt exists
    no abandoned hot session representation remains

before next dispatch:
    cold runtime high-water == locked durable high-water

before successful transaction commit:
    checkpointed opaque-runtime high-water
        == committed durable high-water
```

The equality check is fail-closed and precedes controller dispatch.

Under that serialized boundary, the façade guarantees correct staleness
validation, canonical event ordering, and seamless dispatcher/poller
synchronization.

The Django transaction order is:

```text
lock authoritative session row
    -> reject/replay immutable request id when applicable
    -> evict and cold-load the locked opaque runtime
    -> verify cold runtime high-water == locked scalar high-water
    -> restore persisted staleness index
    -> execute direct dispatch or complete generated chain
    -> force complete opaque-runtime checkpoint
    -> verify after high-water did not regress
    -> persist updated staleness index
    -> persist immutable operation receipt
    -> commit
```

Any exception from dispatch, opaque-runtime checkpointing, staleness
persistence, receipt persistence, or transaction commit rolls back the
database transaction and requires complete hot-runtime eviction.

Precisely:

```text
server-provided per-session sequentiality
    +
highest-façade authorization/staleness/dispatch boundary
    +
queue-owned canonical event_seq
    =
no admitted stale dispatch and one pollable canonical event order
```

Without the first term, the equation does not hold.

## Run-level epsilon (`eps`) channel feedback

Canonical session events (`theta`) remain transaction-owned. They become
authoritative only when the hosting dispatch commits, and their `event_seq`
values must never be reused for speculative delivery.

Servers additionally expose a separate, append-only, run-level epsilon (`eps`)
channel (`EpsLog`):

```text
scope = run_id (role-modulated at read time via visibility + required_roles)

explosion/controller/dispatch-context callbacks
    -> attribute current hop (identity_id, role, trident_dispatch_id,
       theta_event_seq_at_emit, emitter_origin)
    -> append row with run-scoped eps_seq
    -> pollers and dispatchers read /eps/?after_seq=...

transaction commit
    -> canonical theta events become visible on /events/
    -> eps rows remain in the append-only eps log

transaction rollback
    -> already-emitted eps rows remain in the append-only eps log
       (flagged as uncommitted when theta_event_seq_at_emit > session_latest_event_seq)
    -> no rolled-back state enters the canonical theta queue
```

The `/eps/` channel is deliberately separate from `/events/` (`theta`). An
`eps` emission may describe live work during an in-flight dispatch (or a
dispatch that later rolls back), so it is ordered by run-scoped `eps_seq` and
carries causal lineage (`theta_event_seq_at_emit`, `emitter_origin`,
`trident_dispatch_id`) rather than a canonical `event_seq`.

The Django service persists `eps` rows into PostgreSQL (`RunEpsMessage` +
`RunEpsCursor`) through an autocommit database connection alias (`eps_log`) so
pollers can observe live `eps` rows while a Celery worker holds `SELECT ... FOR UPDATE`
on `ThinkumentSesh` on the `default` connection, with zero Redis dependency for `eps`.
The single-process Flask server uses the same `EpsLog` contract with
`InMemoryEpsLog`.

`chainreactionTM` needs no special inner instrumentation: generated dispatches
reuse the same threaded callback mapping and invoke
`observe_dispatch_context_v1(ctx)` before each hop so every inner datum
explosion is recorded with exact per-hop attribution (`dispatcher_identity_id`,
`dispatcher_role`, `trident_dispatch_id`, `theta_event_seq_at_emit`).

## What the core currently guarantees

For one process, provided every write for a session enters through
`_thinksessions.run.run_from_here`:

* dispatches for that session are serialized;
* role authorization is checked before staleness;
* checked stale, future, and malformed dispatches are rejected before
  controller entry;
* stale rejection emits no event and does not move the canonical high-water;
* accepted fills and accepted signals update the same target frontier;
* scope movement invalidates cursors from an older authored surface;
* every recorded event receives one canonical queue-owned sequence;
* pollers observe one canonical sequence order;
* once a controller start is successfully recorded, ordinary in-process
  controller exceptions are converted into one matching bounded system-error
  end;
* callback exceptions cannot prevent canonical controller-event recording.

Different sessions have independent locks, queues, high-waters, scope indexes,
and target indexes. They may execute concurrently within ordinary process and
resource limits.

## What the core does not claim

The current core E2E does not prove:

* cross-process mutual exclusion;
* database transaction atomicity;
* crash atomicity;
* dispatch completion after hard process death;
* dispatch completion after `SystemExit` or `KeyboardInterrupt`;
* canonical event-sink recovery;
* distributed lock correctness;
* session migration correctness;
* worker restart recovery;
* ownership handoff between processes;
* exactly-once network delivery;
* automatic retry ownership.

Those are hosting-server responsibilities.

The core does not perform implicit auxiliary persistence and does not claim
that an arbitrary repository commits its opaque session state and hosting JSON
atomically. The Django adapter and coordination layer provide that transaction.

## Required server test

A server wrapping these endpoints should add an integration test shaped like:

```text
process/worker A                  process/worker B
----------------                  ----------------
request session lock
acquire
load A, S, L
validate C
dispatch
commit engine/events/A/S/L
release
                                  acquire
                                  load new A, S, L
                                  validate the same old C
                                  reject if conflicting
                                  release
```

The server test must prove that the second worker cannot validate against the
pre-commit state while the first worker owns the session's write transaction.

```
```
