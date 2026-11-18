# `epsilinesTM` Quickstart Guide: Declaring, Emitting, and Auditing Epsilon Channels

This guide is the everyday developer handbook for adding, declaring, persisting, and auditing **Epsilon Channels (`epsilinesTM`)** in Thinkument.

- **Companion Live Usage Guide (Emit, Query, Read):** [`quickstart_guide__epsilines_usages_live.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/quickstart_guide__epsilines_usages_live.md)
- **Master Architectural Formalism:** [`19_epsilinesTM_subapps__framework_formalism_usage_growth.MD`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/about/framework/19_epsilinesTM_subapps__framework_formalism_usage_growth.MD)

---

## 1. What is an Epsiline?

A Thinkument run maintains a strict separation between two streams:
- **Theta ($\theta$)**: The deterministic, replayable state machine kernel. Steps advance, widgets explode, and Trident commits ($E_{start}, E_{end}$) are recorded in the session ring.
- **Epsilon ($\epsilon$)**: The concurrent operational, telemetry, and financial side-channel. Widgets emit structured events to report progress, trace execution spans, account for vendor operations, or audit anomalies without mutating or stalling the state machine.

An **epsiline** is a fully configured, service-tracked communication line. Declaring an epsiline in this package (`epsilinesTM_serveragnostic`) automatically grants it:
1. **Payload Schema Validation**: Guarantees dead-JSON integrity before events cross the network.
2. **Role-Modulated Visibility**: Enforces privacy boundaries between owners, participants, and public pollers.
3. **Automated Service Persistence**: The Django host (`epsilinesTM_serverside`) dynamically derives persistence rules, committing rows to PostgreSQL `"eps_log"`.
4. **Universal Anomaly Auditing**: Mounts directly into `GET /epsilines/anomalies/?app=<app_name>` without writing backend service code.

---

## 2. The Vessel Specification Matrix

Every epsiline channel is declared via `EpsChannelSpecV1`:

```python
from epsilinesTM_serveragnostic import (
    EpsAppSpecV1,
    EpsChannelSpecV1,
    MODE_PERSISTENCE,
    MODE_NONE,
    RETENTION_DURABLE,
    RETENTION_TTL,
    RETENTION_NONE,
    VISIBILITY_OWNER_ONLY,
    VISIBILITY_ALL_WITH_MODULATION,
    VISIBILITY_ALL_NO_MODULATION,
)
```

| Field | Type | Description | Allowed Values / Invariants |
| :--- | :--- | :--- | :--- |
| **`channel`** | `str` | Unique channel identifier. | E.g. `"audit-ins"`, `"agent.thought"`. |
| **`app`** | `str` | Owning subapp namespace. | Must match an `EpsAppSpecV1` name (e.g. `"analytica"`, `"economics"`). |
| **`schema`** | `str` | Semantic versioned contract name. | Versioned string (e.g. `"agent_thought_v1"`). |
| **`event`** | `str` | Semantic event kind within stream. | E.g. `"thought_streamed"`, `"step_started"`. |
| **`validator`** | `Callable` | Payload validation function. | Callable `(payload) -> dict` returning dead JSON; fails closed. |
| **`visibility`** | `str` | Role-modulation visibility tier. | `VISIBILITY_OWNER_ONLY`<br>`VISIBILITY_ALL_WITH_MODULATION`<br>`VISIBILITY_ALL_NO_MODULATION` |
| **`mode`** | `str` | Service ingestion mode. | `MODE_PERSISTENCE` (saved to DB)<br>`MODE_NONE` (transient in-memory / pubsub). |
| **`retention`** | `str` | Storage durability lifetime. | `RETENTION_DURABLE` (permanent log)<br>`RETENTION_TTL` (ephemeral expiry)<br>`RETENTION_NONE` (never persisted). |
| **`ttl_seconds`**| `int \| None`| Expiration lifetime when `retention == RETENTION_TTL`.| Integer `> 0` if `retention == "ttl"`; otherwise `None`. |
| **`terminal`** | `bool` | Closes an audited operation span. | `True` for terminators (`audit-outs`, `audit-error`); `False` otherwise. |

---

## 3. Allowed Mode & Retention Combinations

The registry enforces mathematical invariants between storage mode and retention policy:

| Mode | Retention | `ttl_seconds` | Behavior |
| :--- | :--- | :---: | :--- |
| **`MODE_PERSISTENCE`** | **`RETENTION_DURABLE`** | `None` | Immutable append-only log in PostgreSQL `"eps_log"` (`RunEpsMessage`). Permanent audit trail. |
| **`MODE_PERSISTENCE`** | **`RETENTION_TTL`** | `int > 0` | Persisted with an expiration timestamp (`created_at + ttl_seconds`). Automatically pruned after expiry. |
| **`MODE_NONE`** | **`RETENTION_NONE`** | `None` | **Zero DB writes**. Emitted strictly to live polling queues and transient WebSockets for real-time UI animation. |

> [!CAUTION]
> Setting `mode="none"` with `retention="durable"` or `mode="persistence"` with `retention="none"` is an invariant violation and will fail closed with `InvalidEpsChannelSpecificationError`.

---

## 4. Visibility Tiers & Role Modulation

- **`VISIBILITY_OWNER_ONLY` (`"owner-only"`)**:
  - Cleartext payload is accessible **only** to the run session owner and authenticated administrators.
  - Public pollers querying `/run/{slug}/eps/` use the PostgreSQL partial index `analytica_eps_poller_seq_idx` (`WHERE visibility != 'owner-only'`), filtering out internal audit rows before data hits the network.
- **`VISIBILITY_ALL_WITH_MODULATION` (`"all-with-modulation"`)**:
  - All authenticated session participants can read messages. Payloads are dynamically projected according to the caller's active role.
- **`VISIBILITY_ALL_NO_MODULATION` (`"all-no-modulation"`)**:
  - Verbatim public operational channel accessible across all roles.

---

## 5. Declaring a New Epsiline in 3 Steps

Adding a brand-new line (e.g. `agent_ops.thought`) requires zero changes to the Django host:

### Step 1: Register in `epsiline_spec_and_growth_sheet.py`

Open [`epsiline_spec_and_growth_sheet.py`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/epsiline_spec_and_growth_sheet.py):

```python
from epsilinesTM_serveragnostic.core import (
    EpsAppSpecV1,
    EpsChannelSpecV1,
    MODE_PERSISTENCE,
    RETENTION_DURABLE,
    VISIBILITY_ALL_WITH_MODULATION,
)

# 1. Define payload validator (fails closed on undeclared fields)
def validate_thought_payload_v1(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a mapping")
    return {
        "thought": str(payload.get("thought", "")),
        "confidence": float(payload.get("confidence", 1.0)),
    }

# 2. Define app with optional anomaly aggregator
def filter_agent_anomalies_v1(envelopes: list[dict], **kwargs) -> list[dict]:
    # Flag any low-confidence thoughts as anomalies
    return [
        e for e in envelopes
        if e.get("payload", {}).get("confidence", 1.0) < 0.5
    ]

AGENT_OPS_APP = EpsAppSpecV1(
    app="agent_ops",
    anomaly_aggregator=filter_agent_anomalies_v1,
)

# 3. Declare channel specification
AGENT_THOUGHT_CHANNEL = EpsChannelSpecV1(
    channel="agent_ops.thought",
    app="agent_ops",
    schema="agent_thought_v1",
    event="thought_streamed",
    validator=validate_thought_payload_v1,
    visibility=VISIBILITY_ALL_WITH_MODULATION,
    mode=MODE_PERSISTENCE,
    retention=RETENTION_DURABLE,
    terminal=False,
)
```

Add `AGENT_OPS_APP` to `_EPS_APP_SPECS` and `AGENT_THOUGHT_CHANNEL` to `_EPS_CHANNEL_SPECS`.

### Step 2: Emit from a Widget

In your widget class (inheriting from `ServiceReadyWidget` or `AnalyticaPoweredDatumLifecycleWidget`):

```python
from epsilinesTM_serveragnostic.subapps import ServiceReadyWidget

class MyAutonomousAgentWidget(ServiceReadyWidget):
    def on_step_mount(self, position, fill_data, limits, stats):
        # Emit operational thought stream
        self.emit_eps_v1(
            "agent_ops.thought",
            {"thought": "Decomposing user request...", "confidence": 0.95},
        )
        return super().on_step_mount(position, fill_data, limits, stats)
```

### Step 3: Consume and Audit via Service Endpoints

Because the service host dynamically derives its handling policies from `EPS_CHANNEL_SHEET_V1`, your new line immediately enjoys full platform capabilities:

1. **Live Real-Time Polling**:
   - `GET /run/{slug}/eps/?after_seq=0`
   - Returns paginated `thinkument_eps_page_v1` with your event and monotonically assigned `eps_seq`.
2. **Durable Analytics Audit Stream**:
   - `GET /analytics/?channel=agent_ops.thought`
   - Returns immutable append-only records from PostgreSQL `"eps_log"`.
3. **Universal Anomaly Audit**:
   - `GET /epsilines/anomalies/?app=agent_ops`
   - Staff endpoint: delegates directly to your `filter_agent_anomalies_v1` aggregator!

---

## 6. Dynamic Channel Pattern Resolvers

If your subapp needs to support parameterized or wildcard channel names (e.g. `audit-custom.<step_name>` or `agent.trace.<task_id>`) without hardcoding every string in the registry:

```python
from epsilinesTM_serveragnostic import register_dynamic_channel_resolver_v1
import re

_AGENT_TRACE_RE = re.compile(r"^agent\.trace\.[a-z0-9_-]+$")

register_dynamic_channel_resolver_v1(
    "agent_ops",
    lambda channel: EpsChannelSpecV1(
        channel=channel,
        app="agent_ops",
        schema="agent_trace_v1",
        event="trace_event",
        validator=validate_trace_payload_v1,
        visibility=VISIBILITY_OWNER_ONLY,
        mode=MODE_PERSISTENCE,
        retention=RETENTION_DURABLE,
    ) if _AGENT_TRACE_RE.fullmatch(channel) else None,
)
```

Any channel matching `agent.trace.*` will automatically resolve, validate, persist, and route without requiring static declarations.

---

## 7. Testing Your New Epsiline

You can verify your new line with zero network or database setup:

```python
from epsilinesTM_serveragnostic import (
    require_registered_eps_channel_v1,
    get_registered_eps_channel_v1,
)

def test_my_new_channel_is_active():
    spec = require_registered_eps_channel_v1("agent_ops.thought")
    assert spec.app == "agent_ops"
    assert spec.mode == "persistence"
    assert spec.retention == "durable"
    
    # Verify validator fails closed
    cleaned = spec.validator({"thought": "Validating", "confidence": 0.8})
    assert cleaned["confidence"] == 0.8
```

Run unit tests instantly:
```bash
poetry run pytest tests/unit/test_epsilinesTM_serveragnostic.py
```

---

## 8. Reference Case: The `asyncwork` Subapp

The `asyncwork` subapp (`thinkument/framework/think-app/src/epsilinesTM_serveragnostic/subapps/asyncwork/`) demonstrates the full lifecycle:

| Channel | Role | Mode & Retention | Post-Commit Trigger |
| :--- | :--- | :--- | :--- |
| **`asyncwork.announce`** | Starts an async task chain; specifies target name, args, timeout, and queue. | `MODE_PERSISTENCE` / `RETENTION_DURABLE` | Celery task enqueued onto `QUEUE_ASYNCWORK` via `transaction.on_commit`. |
| **`asyncwork.progress`** | Streaming progress ticks (0.0% to 100.0%) with step details. | `MODE_PERSISTENCE` / `RETENTION_TTL` | None (pure streaming poller data). |
| **`asyncwork.done`** | Terminal sandwich event announcing outcome (`success`, `error`, `timeout`) and result or error details. | `MODE_PERSISTENCE` / `RETENTION_DURABLE` (`terminal=True`) | None (signals completion to wait loops and cross-widget wires). |

See [subapps/asyncwork/README.md](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/subapps/asyncwork/README.md) and [COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md) for full architectural blueprints.
