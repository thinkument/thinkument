# Hub 1 — Generic `EpsLog` & Frontend Live-I/O Polling Vial (`think-frontend`)

This directory (`thinkument/framework/think-frontend/src/live_vial/_json_shell/`) owns the **generic, domain-free runtime contract** for the run-level epsilon (`eps`) channel alongside the canonical session-state event channel (`theta`).

---

## 1. The Two-Cursor Run Model `(C, E)`

Every live session run produces two distinct, monotonically ordered event streams:

1. **`theta` (`C`, `event_seq`) — Canonical Trident Stream:**
   - Carries committed session-state transitions (`controller_loop_event_v1`: `start`, `end`, `aborted`) and canonical snapshots (`U`).
   - Polled via `GET /run/<access_id>/poll/?after_seq=<C>&limit=<N>` (`Q.cursor` in `thinkumentJS`).
   - Strictly reserves the 32-slot in-session ring buffer for tridents so `undo` / `redo` / step history cannot be evicted by chatty widget telemetry.

2. **`eps` (`E`, `eps_seq`) — Run-Level Live-Emission Stream:**
   - Carries live widget-explosion and runtime channel messages (`datum_lifecycle_event_v1` / out-of-dispatch service emissions) ordered by a monotonically increasing per-run integer `eps_seq >= 1`.
   - Polled via `GET /run/<access_id>/eps/?after_seq=<E>&limit=<N>[&window=<W>]` (`Q.eps_cursor` in `thinkumentJS`).
   - Persists independently of session state `U` (`UNDO` / `REDO` never delete or roll back `eps_seq`).

---

## 2. The 3-Visibility Contract (`eps_log.py`)

`think-frontend` defines the three structural visibility classes without knowing any application or service channel names:

| Visibility Class | Constant | Poller / Reader Behavior |
| :--- | :--- | :--- |
| **`owner-only`** | `VISIBILITY_OWNER_ONLY` | Strictly omitted from `/run/<access_id>/eps/` frontend poll responses (`next_after_seq` advances past omitted rows). Visible only when `for_owner=True` (service analytics / owner dashboards). |
| **`all-no-modulation`** | `VISIBILITY_ALL_NO_MODULATION` | Delivered in full (`obfuscated: False`) to every run poller regardless of role. |
| **`all-with-modulation`** | `VISIBILITY_ALL_WITH_MODULATION` | Evaluated against the run's datum read-role map `(frame_id, span_id, datum_id)`. Authorized roles receive the full row (`obfuscated: False`); unauthorized roles receive an **Integrity Trident** (`obfuscated: True`). |

### The Integrity Trident (`obfuscated: True`)
When a poller's role is not authorized to read an `all-with-modulation` row, `project_eps_row_v1` returns:
- **Preserved envelope:** `eps_seq`, `event_id`, `channel`, `emitted_at`, `content_hash`, `visibility`, `theta_event_seq_at_emit`, `emitter_origin`, `request_id`, `trident_dispatch_id`, `obfuscated=True`, `form_id`.
- **Redacted body:** `datum_id=None`, `frame_id=None`, `span_id=None`, `payload=None`.
- **`content_hash`:** HMAC-SHA256 (`compute_eps_content_hash_v1(payload, run_key=...)`) computed over canonical JSON with a per-run derived secret key, preventing dictionary-guessing of small payloads while allowing authorized peers to verify payload integrity.

---

## 3. Causal Lineage: Mapping `eps` to Tridents & Runtime Corners

Even though `eps` rows are not sandwiched inside `theta` tridents, every `EpsRow` records exact causal lineage:

| Runtime Corner | `emitter_origin` | `trident_dispatch_id` | `theta_event_seq_at_emit` | `datum_id` / `frame_id` / `span_id` |
| :--- | :--- | :--- | :--- | :--- |
| **1. Widget Explosion (`user_fill` / `user_signal` / mount / chain)** | `"widget_explosion"` | Active controller trident `dispatch_id` (e.g. `"1"`) | `event_seq` of enclosing trident `start` | Populated from exploding datum |
| **2. Widget Explosion that later aborts** | `"widget_explosion"` | Aborted trident `dispatch_id` | `event_seq` of trident `start` (matched by `aborted` event) | Populated from exploding datum |
| **3. Controller / Session Lifecycle Hook (non-widget)** | `"controller_lifecycle"` | Active trident `dispatch_id` or `None` | Current `theta` high-water `event_seq` | `None` |
| **4. Out-of-Dispatch Service Task (Celery / Reconciliation)** | `"service_background"` | Originating trident `dispatch_id` if correlated, else `None` | Current `theta` high-water `event_seq` | Optional |
| **5. Storage / External Webhook Callback** | `"external_webhook"` | `None` | Current `theta` high-water `event_seq` | `None` |

---

## 4. Wake-Up Catch-Up (`window`) & Dispatch Drain Ordering

- **Bounded Cold Wake-Up (`after_seq=0&window=512`):** When a frontend boots cold (`Q.eps_cursor === 0`), `thinkumentJS` passes `window: G.maxEpsRows` (`512`). `EpsLog.read` filters out `owner-only` rows first and returns the latest `512` poller-eligible rows, advancing `Q.eps_cursor` to `eps_head`.
- **Drain `eps` Before `theta` (`enqueueDispatch`):** After `portal.dispatch(...)` resolves (or throws), `thinkumentJS` awaits `epsPoller.catchUp()` **before** `poller.catchUpTo(committedThetaSeq)` so `epsilon` dissemination always precedes the corresponding `theta` trident commit dissemination.
