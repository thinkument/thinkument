# Thinkument App (`think-app`)

`think-app` wraps the core execution engine (`think-backend`) and its widget runtime with the frontend live vial (`think-frontend`) into a coherent application platform. It serves as the framework foundation directly beneath higher services (`thinkument/service`) and creativity packages (`service-ui-webapps`).

## Architectural Pillars

### 1. `ways_to_run`
Owns local and standalone execution runners:
- **`live_run_atelier`**: Server-agnostic interactive live-I/O execution bed with Flask adapter.
- **`live_run_DOMscripted_atelier`**: Playwright browser DOM-scripted verification runner proving user interactions, dispatches, and role modulations without sleeps.

### 2. `ways_to_create`
Owns the Human-AI Interaction (HAI) app-pack foundation:
- **`app_pack_mould`**: Runtime activator, session metadata pocket registry (`app_pack_mould.app_pack`), static root discovery, and browser app-pack contract (`app_packs.js`).
- **`app_packs_examples`**: Canonical reference packs (such as `example_notes` and teaching packs).
- **`app_pack_publication_registrar`**: Central publication registry for creativity app pack families (`app_pack_families.py`, `app_packs.py`, `authoring_profiles.py`, `contracts.py`, `publication.py`, `static_roots.py`).

### 3. `epsilinesTM_serveragnostic`
Subapp-agnostic epsilon framework and applied subapp channels:
- **`core/` (Foundation Hub 2)**:
  - Canonical channel and app specifications (`EpsChannelSpecV1`, `EpsAppSpecV1`, `EpsTrafficRoutingV1`).
  - Declarative handling traits on channels (`mode`, `retention`, `ttl_seconds`, `terminal`).
  - Dynamic channel resolvers via `register_dynamic_channel_resolver_v1` (enabling dynamic audit patterns without central churn).
  - Generalized validation, sink registration, and runtime routing.
  - Zero database or persistence coupling; purely server-agnostic.
- **`epsiline_spec_and_growth_sheet.py`**:
  - Unified front declaration and growth sheet (`EPS_CHANNEL_SHEET_V1`).
  - Single source of truth for channel invariants across all applications.
- **`subapps/` (Applied Subapps Hub)**:
  - Modular, cleanly isolated subapps:
    - `analytics/`: Analytica emission channels (`audit-ins`, `audit-outs`, `audit-error`), event envelopes, and stream validation.
    - `economics/`: Vendor pricing calculation, credit precharge estimation, and usage reconciliation.
    - `storagics/`: Storage asset lifecycle, quota checks, and usage emission (`audit-storage-usage`).
    - `base.py`: Base `ServiceReadyWidget` mixin for service-tracked computation.
  - Root economics logic (`filter_vendor_usage_anomalies`) is owned by `financial-core/wallet-credits/src/wallet_economics/anomalies.py`, keeping the agnostic framework completely free of financial coupling.

Package-owned browser roots follow the [static publication contract](../think-frontend/src/__staticfiles_mgmt/README.md).
