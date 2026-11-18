# Hub 2: Central Epsilon (`eps`) Declaration Hub

This directory (`thinkument/framework/think-app/src/epsilinesTM_serveragnostic/core`) is **Hub 2** in the first-class, run-level epsilon (`eps`) architecture.

For the definitive end-to-end architecture, see [19_epsilinesTM_subapps__framework_formalism_usage_growth.MD](../../../../../about/framework/19_epsilinesTM_subapps__framework_formalism_usage_growth.MD).

---

## Architectural Role & Scope

- **Layer**: Framework foundational layer in `think-app`, sitting between engine packages (`think-backend`, `think-frontend`) and host services (`thinkument/service`, `service-ui-webapps`, `buildmybook`).
- **Dependencies**: Pure Python, zero Django, zero Celery. Usable across CLI runners, Flask live atelier, and production Celery/Django servers.
- **Contract**: Defines the declarative schema, visibility policy, storage mode, retention, and payload validation for every run-level epsilon channel emitted across the ecosystem.

```
       [ think-backend ]                      [ think-frontend ]
       (_emit_from_widget_v1                   (live vial, eps_log.py,
        record_in_session_queue=False)          thinkumentJS /eps/ poll)
                   \                                     /
                    \                                   /
            +---------------------------------------------------+
            |  HUB 2: epsilinesTM_serveragnostic (Declarations)|
            |  - core/registry.py (EpsChannelSpecV1, EpsAppSpec)|
            |  - epsiline_spec_and_growth_sheet.py (Master Sheet)|
            |  - core/context.py (Ambient bind_eps_sink_v1)     |
            +---------------------------------------------------+
                                    |
                                    v
            +---------------------------------------------------+
            |  HUB 3: thinkument/service (Service Treatment)    |
            |  - service_eps_handling_sheet.py (Dynamic Policy) |
            |  - RunEpsMessage model (append-only log, hash)    |
            |  - UniversalEpsAnomaliesView (Aggregators)        |
            +---------------------------------------------------+
```

---

## Core Formalisms & Primitives

### 1. `EpsChannelSpecV1`

Every channel in the ecosystem is declared with an immutable specification:

```python
from epsilinesTM_serveragnostic import (
    EpsChannelSpecV1,
    MODE_PERSISTENCE,
    RETENTION_DURABLE,
    VISIBILITY_OWNER_ONLY,
)

spec = EpsChannelSpecV1(
    channel="audit-vendor-cost-reconciliation",
    app="economics",
    schema="vendor_cost_reconciliation_v1",
    event="reconciled",
    validator=AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1.validate,
    visibility=VISIBILITY_OWNER_ONLY,
    mode=MODE_PERSISTENCE,
    retention=RETENTION_DURABLE,
    terminal=False,
)
```

- **`channel`**: Dot-namespaced or hyphenated channel name (e.g. `audit-ins`, `ui.eps_fixture`).
- **`app`**: Logical app family (e.g. `analytica`, `economics`, `storagics`).
- **`schema`**: Semantic versioned contract name.
- **`event`**: Specific semantic event type within the stream.
- **`validator`**: Callable validating and returning a pure, JSON-dead payload mapping. Fails closed on malformed input.
- **`visibility`**: Exactly one of the three runtime role-modulation visibility tiers:
  - `VISIBILITY_OWNER_ONLY` (`"owner-only"`): Cleartext for run owner and internal service monitors; hashed for others.
  - `VISIBILITY_ALL_WITH_MODULATION` (`"all-with-modulation"`): Scrubbed and projected according to active caller role.
  - `VISIBILITY_ALL_NO_MODULATION` (`"all-no-modulation"`): Public operational channel readable verbatim across all roles.
- **`mode`**: Ingestion mode (`MODE_PERSISTENCE` vs `MODE_NONE`).
- **`retention`**: Storage lifecycle (`RETENTION_DURABLE`, `RETENTION_TTL`, `RETENTION_NONE`).
- **`terminal`**: Whether the channel signals completion of an audited operation span.

### 2. Central Growth Sheet (`epsiline_spec_and_growth_sheet.py`)

`EPS_CHANNEL_SHEET_V1` and `EPS_APP_SHEET_V1` form the single source of truth for channel declarations. Registration is verified by `assert_eps_channel_sheet_invariants_v1()`:
- No duplicate channel names.
- Every channel references a registered app.
- Every validator is callable and dead-JSON compliant.
- Every visibility, mode, and retention belongs to the allowed invariant constants.

### 3. Dynamic Channel Resolution (`register_dynamic_channel_resolver_v1`)

Dynamic pattern matchers (e.g., regex `audit-[a-z0-9._-]+`) dynamically instantiate valid `EpsChannelSpecV1` instances on demand.

### 4. Ambient Sink Binding (`core/context.py`)

Runtime components emit epsilon without coupling to transport or persistence:

```python
from epsilinesTM_serveragnostic import bind_eps_sink_v1, emit_eps_v1

with bind_eps_sink_v1(custom_sink):
    # Validates against registry before passing to sink
    emit_eps_v1("audit-ins", {"operation_id": "op-123", ...})
```
