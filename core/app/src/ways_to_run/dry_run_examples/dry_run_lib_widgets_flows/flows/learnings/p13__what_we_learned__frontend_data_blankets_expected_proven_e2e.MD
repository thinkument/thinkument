# P13 — frontend data blankets expected and proven E2E

## The question

What can core prove end to end about the data consumed by frontend
poller-dispatchers without making the dry-run formalism itself depend on Flask,
Django, Celery, Redis, a database transaction, or an HTTP route?

## The answer

The standard dry-run language can prove one data blanket:

```text
standard A
    -> synchronous dispatch receipt
    -> live epsilon controller/datum packets
    -> committed theta page
    -> named-role theta projection
    -> roleless/named-role Q/U reads
```

How those observations are obtained is now an exchangeable strategy concern.

The current `base-facade-strategy` obtains them directly from core. A future
server or DOM strategy can obtain the same standard observations through a
remote or frontend execution layer.

Server layers still separately own hosting mechanics:

```text
request authentication and access-handle sealing
transaction commit/rollback
cross-worker serialization
request-id durability/idempotency
provisional progress storage and expiry
HTTP status and serialization
```

Those hosting concerns do not own a second trident, message, A, E, or U grammar.

---

## 1. One standard execution language

P13 is authored only in standard dry-run data:

```text
P
SM
C
A
E
```

The P13 flow file does not import a concrete transport.

The run sheet selects a strategy.

Today:

```text
BaseFacadeBackendOnlyDryRunStrategy
```

translates the standard operations to `run_from_here`.

Tomorrow another strategy may translate the same operations to a live server or
browser.

---

## 2. epsilon: live/provisional packets

The standard blanket calls the live channel epsilon.

For the current base-facade strategy, epsilon is implemented by the existing
threaded callback wires:

```text
controller_events_callback
explosion_events_callback
```

The packets arrive while the dispatch call is still open and intentionally do
not carry canonical `event_seq`.

A future strategy may source epsilon from:

```text
request progress storage
SSE
websocket
browser event bridge
another provisional transport
```

The generic runner does not care which mechanism produced them; it receives
standard event packets from the strategy.

---

## 3. theta: committed queue packets

The standard committed channel is theta.

For the current strategy it is supplied by committed facade event reads.

The generic runner proves that one admitted action has a balanced standard
envelope:

```text
Estart
zero or more informative datum packets
Eend
```

and that the committed interval is strictly ordered and contiguous canonically.

---

## 4. Exact epsilon-to-theta bridge

For one admitted action with:

```python
exact_live_canonical_wire=True
```

the generic runner proves:

```text
1. capture epsilon while dispatch is open
2. dispatch through the selected strategy
3. poll theta after dispatch
4. remove only event_seq from committed packets
5. require exact ordered equality
```

Therefore:

```text
epsilon packet body == theta packet body
```

with canonical `event_seq` as the committed enrichment.

This proof is no longer coupled to how epsilon or theta were physically
transported.

---

## 5. Data-blanket expectation

An ordinary action may declare:

```python
blanket=DATA_BLANKET(
    live=...,
    dispatch=...,
    canonical_page=...,
    contexts=[...],
    exact_live_canonical_wire=True,
)
```

### `live`

Uses the same Estart/Edatums/Eend expectation grammar as committed events.

### `dispatch`

Uses standard dotted-path needles against the strategy-returned synchronous
receipt.

### `canonical_page`

Uses standard dotted-path needles against the strategy-returned theta page.

### `contexts`

Asks the strategy for fresh roleless or role-projected Q/U after dispatch.

The E language is shared. Strategies do not get their own assertion language.

---

## 6. Role modulation remains one law

Existing `views=[ROLE_VIEW(...)]` proves that every named role:

```text
scans the same canonical interval
advances to the same canonical cursor
retains the controller event spine
receives only readable datum events
receives independently projected U at start and end
receives projected A and actor correlation according to target visibility
receives exact hidden event-sequence ranges
```

The selected strategy supplies the projected theta page. The generic runner
proves the common role law.

---

## 7. Why this scales to a frontend strategy

A browser/DOM strategy may implement standard A by:

```text
locating fields represented by the current Q/U
performing DOM fills/clicks/signals
submitting through the frontend
hearing provisional frontend/server progress as epsilon
polling committed frontend/server state as theta
reading visible role-projected Q/U from the DOM or client model
```

It can normalize those observations into the same standard dry-run vocabulary.

The flow file, case file, event needles, role expectations, and generic proof
machinery remain untouched.

---

## 8. What remains server-specific

Core/strategy-level P13 does not prove:

```text
HTTP authentication
transaction visibility
cross-worker locking
request idempotency
progress TTL
status codes
wire serialization errors
```

A server strategy and its server-specific integration tests should prove those
hosting facts while still satisfying the same outer dry-run language.

This creates a clean nesting:

```text
standard dry-run proof
    says what must be observed

strategy
    says how one environment obtains those observations

server/DOM internals
    remain implementation details behind the strategy
```

---

## Final laws

```text
□ P13 P/SM/C/A/E is strategy-agnostic.
□ Live epsilon packets are observable during dispatch.
□ Live packets do not contain event_seq.
□ Committed theta packets are strictly ordered canonical packets.
□ epsilon bodies equal theta bodies after removing only event_seq.
□ Role views advance through one canonical cursor spine.
□ Hidden positions are explicitly receipted.
□ Controller U is projected independently at start and end.
□ Datum packets are whole-visible or wholly omitted.
□ A and actor/correlation blackout follows readable target authority.
□ Post-dispatch Q/U reads agree with event-boundary projection laws.
□ The current backend-only facade is one strategy, not the dry-run definition.
```

## Final takeaway

A downstream poller-dispatcher can design against one stable set of semantic
wires:

```text
A
controller packets
datum packets
dispatch receipts
theta pages
projected Q/U
```

The dry-run formalism proves their relationships. The selected strategy decides
how they are reached.
