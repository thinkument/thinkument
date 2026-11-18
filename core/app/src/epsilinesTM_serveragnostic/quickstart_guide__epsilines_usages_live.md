# `epsilinesTM` Live Usage Quickstart Guide: Emitting, Referencing, Hierarchies, and Targeted Reads

This guide is the definitive developer and runtime manual for **emitting with referencing metadata, forming hierarchical sub-directories, executing fast targeted/batch reads, and maintaining concurrency-certified efficiency** over **Epsilon Channels (`epsilinesTM`)**.

- **Companion Declaration Guide:** [`quickstart_guide__new_epsilines.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/quickstart_guide__new_epsilines.md) (declaring channels, apps, modes, retention, and anomaly aggregators).
- **Architectural Foundation:** [`19_epsilinesTM_subapps__framework_formalism_usage_growth.MD`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/about/framework/19_epsilinesTM_subapps__framework_formalism_usage_growth.MD).
- **Computation Philosophies:** [`COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md) (zero local compute & dispatches in a snap).

---

## 1. Executive Vision: The Jobsian Seam & The Wozniakian Engine

A Thinkument execution strictly bifurcates state into two orthogonal planes:
1. **Theta ($\theta$)**: The deterministic, replayable state machine kernel. Steps advance sequentially, widgets mount and explode, and trident commits ($E_{start}, E_{end}$) are persisted inside the 32-slot ring window for undo/redo.
2. **Epsilon ($\epsilon$)**: The concurrent, asynchronous operational event, referencing, telemetry, and data-flow side-channel.

### The Jobsian Topmost Seam
To the developer or algorithm designer, epsilon is **two effortless types of lines**:
- **Write**: `emit_eps_v1(channel, payload, ...)`
- **Read**: `read_eps_v1(channel, ...)`

No boilerplate, no plumbing variables, complete design freedom. References naturally support **hierarchical sub-directories** (e.g. `ref="plan/stage1/task_a"`), allowing point seeks, sub-tree batch seeks, run-level batches, or owner-level historical aggregates in a single elegant call.

### The Wozniakian Engine
Underneath that sleek seam lies an industrial-grade, concurrency-certified engine:
- **Wires Unentangled**: The widget runtime box cleanly encapsulates execution context (`run_id`, `owner_id`, `form_id`, `role`). Callers pass only domain data; plumbing is resolved automatically.
- **Ownership Cleanly Secured**: Provenance is stamped by the trusted host (never spoofable by caller arguments). Multi-tenant isolation is absolute; role modulation dynamically projects payloads based on visibility policies.
- **High-Performance Concurrency**:
  - Monotonic sequence allocation in PostgreSQL uses row locks strictly isolated to `(run_kind, run_id)` on `RunEpsCursor`. Cross-run writers never block each other.
  - Race-free write deduplication via `UniqueConstraint(["run_kind", "run_id", "event_id"])` with exact replay idempotency.
  - Thread-safe in-memory storage (`InMemoryEpsLog`) with reader-writer locks for concurrent testing.
- **Certified Efficiency**:
  - Btree index seeks on `event_id`, `span_id`, and `expires_at`.
  - Zero redundant serialization/deserialization.
  - TTL pruning for ephemeral operational traces.
- **Empirical Integration Certification**:
  - Verified through `_integration/` with real Celery-backed concurrency, parallel multi-pollers, race-free sequence increments, and cross-widget asynchronous execution "following given ref passed".

```
+---------------------------------------------------------------------------------------+
|                                    RUNTIMES                                           |
|  +--------------------+  +-------------------+  +-----------------+  +--------------+ |
|  |  Widget Explosion  |  |  AI Agent Harness |  | Celery Task /   |  | API Daemon / | |
|  |  Runtimes (P SM C) |  |  (Tree-of-Thoughts|  | Worker Pool     |  | Webhook Host | |
|  +--------------------+  +-------------------+  +-----------------+  +--------------+ |
+---------------------------------------------------------------------------------------+
                                           |
         ref = emit_eps_v1(..., ref)       |     read_eps_v1(..., ref / ref_prefix)
                                           v
+---------------------------------------------------------------------------------------+
|                       CORE LOWER PRIMITIVES (epsilinesTM)                             |
|       - require_registered_eps_channel_v1                                              |
|       - Dead-JSON Schema Validation & Invariant Checking                              |
|       - Referencing Coordinates: ref, parent_ref, meta                                |
|       - Ambient Sink & Reader Binding (bind_eps_sink_v1, bind_eps_reader_v1)          |
+---------------------------------------------------------------------------------------+
                     |                                           ^
      mode="persistence"                                         |
                     v                                           |
+---------------------------------------------------------------------------------------+
|                              SERVICE STORAGE HOST                                     |
|    - In-Memory Live Queue (mode="none" or live I/O polling via /run/{slug}/eps/)     |
|    - Multi-DB PostgreSQL "eps_log" (mode="persistence", RunEpsMessage model)          |
|    - Indexed lookups: event_id (ref), span_id (parent_ref), owner_id, run_id          |
+---------------------------------------------------------------------------------------+
```

---

## 2. Universal Topmost API: The Two Lines

### 2.1 The Write Line: `emit_eps_v1` with Referencing Coordinates

```python
def emit_eps_v1(
    channel: str,
    payload: Mapping[str, Any],
    *,
    ref: Optional[str] = None,          # Unique reference or hierarchical path (e.g. "plan/step1/a")
    parent_ref: Optional[str] = None,   # Parent reference forming tree hierarchies
    meta: Optional[Mapping[str, Any]] = None, # Lean key-value indexing tags
    **kwargs: Any,
) -> str:
    """Validate (channel, payload), attach referencing coordinates, and return confirmed ref."""
```

- **Returns `ref`**: Emitting returns the confirmed unique reference identifier. If `ref` is omitted on a persisting channel, a compact reference is automatically allocated.
- **Hierarchical Path References ("Sub-Dirs")**: Authors can format references as paths (e.g. `"eval/branch_1/probe_a"`), enabling instant sub-tree batch retrieval later.
- **Example**:
  ```python
  # Root thought / goal:
  root_ref = emit_eps_v1(
      "agent.thought",
      {"step": "Decompose goal into subtasks"},
      ref="plan/root",
      meta={"phase": "planning"},
  )

  # Child branch anchored to parent:
  child_ref = emit_eps_v1(
      "agent.thought",
      {"subtask": "Parse schema requirements"},
      ref="plan/stage1/task_a",
      parent_ref=root_ref,
      meta={"phase": "execution"},
  )
  ```

### 2.2 The Read Line: `read_eps_v1` with Multi-Modal Seeks

Reading does not force you into a blunt full-table dump. It provides **targeted precision, sub-directory batch queries, and historical aggregations** in a single uniform call:

```python
def read_eps_v1(
    channel: Optional[str] = None,      # Target channel (optional when seeking by unique ref)
    *,
    # --- Targeted Seeks ---
    ref: Optional[str] = None,          # 1. Point seek: exact reference (O(1))
    parent_ref: Optional[str] = None,   # 2. Hierarchy seek: direct children of parent
    ref_prefix: Optional[str] = None,   # 3. Sub-dir / prefix batch: all descendants under path
    ref_regex: Optional[str] = None,    # 4. Pattern seek: matching regex pattern
    meta: Optional[Mapping[str, Any]] = None, # 5. Tag seek: matching key-value metadata
    
    # --- Scopes & Batches ---
    all_in_run: bool = False,           # 6. Run-level batch: all rows in this run
    all_for_owner: bool = False,        # 7. Owner-level batch: all rows for this owner across runs
    run_id: Optional[str] = None,       # Defaults to active run in widget context
    owner_id: Optional[str] = None,     # Inferred from authenticated context
    
    # --- Pagination & Streaming ---
    after_seq: int = 0,                 # Monotonic cursor for sequential streaming
    limit: int = 100,
    caller_role: Optional[str] = None,
    for_owner: bool = False,
    allow_all: bool = False,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """Targeted or batch retrieval of persisted epsilon records."""
```

#### Usage Modes & Return Shapes:
- **Point Seek (`ref="plan/root"`)**: Returns a **single `dict` envelope** (or `None` if not found) immediately in $O(1)$.
- **Hierarchy Query (`parent_ref="plan/root"`)**: Returns a **`list[dict]`** of all direct children.
- **Sub-Dir / Prefix Batch (`ref_prefix="plan/stage1/"`)**: Returns a **`list[dict]`** of all descendant records under that path in an indexed seek.
- **Pattern Seek (`ref_regex=r"^plan/stage[0-9]+/.*"`)**: Returns a **`list[dict]`** matching structured patterns.
- **Run Batch (`all_in_run=True`)**: Returns a **`list[dict]`** of all records of this channel within the active run.
- **Owner Historical Batch (`all_for_owner=True`)**: Returns a **`list[dict]`** of historical records across runs for the authenticated account.
- **Sequential Streaming Cursor (`after_seq=10`)**: Returns a **`list[dict]`** representing a chronological cursor page.

#### Canonical Envelope Keys:
Every record returned by `read_eps_v1` contains the identical canonical keys:
```python
{
    "ref": "plan/stage1/task_a",         # Unique reference ID
    "parent_ref": "plan/stage1",          # Parent reference (or None)
    "channel": "agent.thought",           # Epsilon channel name
    "payload": {"step": "Parse AST"},     # Validated dead-JSON payload
    "meta": {"phase": "execution"},       # Indexing metadata tags (dict)
    "eps_seq": 4,                         # Monotonic sequence in run
    "emitted_at": "2026-11-15T16:15:00Z", # ISO 8601 UTC timestamp
    "run_id": "98a72f01-...",             # Run identifier (UUID string)
}
```

---

## 3. Core Architectural Invariants

### Invariant 1: The Persistence-Only Read Boundary
`read_eps_v1` is strictly valid **only** for channels declared with `mode=MODE_PERSISTENCE`.
- If a caller invokes `read_eps_v1` on a channel configured with `mode=MODE_NONE`, the framework fails fast:
  ```python
  CannotReadTransientEpsChannelError: Channel 'live.progress' has mode='none' and cannot be read from persistence.
  ```

### Invariant 2: High-Performance Indexed Seeks (No Table Scans)
In PostgreSQL `"eps_log"`:
- `ref` maps to `event_id` (enforced by `UniqueConstraint(["run_kind", "run_id", "event_id"])`).
- `parent_ref` maps to `span_id` (indexed for instant parent-child lookups).
- `ref_prefix` leverages btree pattern matching on `event_id`.
- Local testing uses `InMemoryEpsLog` with dictionary indices `_by_ref[ref]` and `_by_parent[parent_ref]`, ensuring exact contract equivalence without a live database.

### Invariant 3: Unentangled Wires & Runtime Box Abstraction
Inside a widget explosion, the widget runtime box encapsulates its active `run_id`, `owner_id`, `form_id`, and `role`. 
The widget author writes `self.emit_eps_v1(...)` and `self.read_eps_v1(...)` with **zero plumbing wires**:
```python
class MyAnalysisWidget(ServiceReadyWidget):
    def on_step_mount(self, position, fill_data, limits, stats):
        # Zero plumbing: run_id and owner_id are injected automatically
        self.emit_eps_v1("agent.thought", {"thought": "Initialized"}, ref="task/init")
        
        # Zero plumbing: reads default to active run
        prior = self.read_eps_v1("agent.thought", ref="task/init")
        return super().on_step_mount(position, fill_data, limits, stats)
```

### Invariant 4: Cleanly Secured Ownership & Multi-Tenant Isolation
- Provenance is stamped by the trusted host, not spoofable by caller arguments.
- Queries strictly filter by caller ownership (`owner_id`) and authenticated run identity.
- Role modulation dynamically projects payloads based on visibility policies (`VISIBILITY_OWNER_ONLY`, `VISIBILITY_ALL_WITH_MODULATION`, `VISIBILITY_ALL_NO_MODULATION`).

---

## 4. Concurrency Architecture & Lock Isolation

| Concurrency Dimension | Wozniakian Mechanism | Invariant & Guarantee |
| :--- | :--- | :--- |
| **Cross-Run Concurrency** | Row locks on `RunEpsCursor` are strictly scoped to `(run_kind, run_id)`. | **Zero contention** between distinct runs across the cluster. |
| **Intra-Run Concurrency** | Monotonic sequence allocation via `select_for_update()` on cursor. | Race-free sequence numbers; multiple concurrent widgets in the same run serialize smoothly without deadlocks. |
| **Write Races & Idempotency** | PostgreSQL `UniqueConstraint(["run_kind", "run_id", "event_id"])` with `_assert_exact_replay`. | Safe, idempotent deduplication if duplicate `ref` is emitted under race conditions. |
| **Concurrent Reads & Pollers** | Partial index `analytica_eps_poller_seq_idx` (`WHERE visibility != 'owner-only'`). | High-throughput poller reads never block or get blocked by database write transactions. |
| **In-Memory Thread Safety** | `threading.RLock()` in `InMemoryEpsLog`. | Thread-safe in-memory operations across parallel test threads. |

---

## 5. Storage Efficiency & Lifecycle (TTL / Expiry)

1. **Dead-JSON Zero-Copy**: Payload validation operates directly on immutable structures, avoiding redundant stringify/parse cycles.
2. **TTL Expiration Pruning**: Ephemeral operational traces (`retention=RETENTION_TTL`) are stamped with `expires_at = emitted_at + ttl_seconds`. Queries automatically filter `Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())`, and background vacuum sweeps prune expired rows.
3. **Transient Streaming Bypass**: Channels with `mode=MODE_NONE` bypass PostgreSQL entirely, delivering strictly to ephemeral live polling queues and WebSockets.

---

## 6. Live Patterns & Code Recipes

### Recipe 1: Hierarchical Sub-Dir Batch Retrieval (Tree-of-Thoughts)

```python
from epsilinesTM_serveragnostic import emit_eps_v1, read_eps_v1

# 1. Emit deep hierarchy using path-like references
emit_eps_v1("agent.thought", {"text": "Root goal"}, ref="goal/root")
emit_eps_v1("agent.thought", {"text": "Branch 1"}, ref="goal/branch_1", parent_ref="goal/root")
emit_eps_v1("agent.thought", {"text": "Probe 1A"}, ref="goal/branch_1/probe_a", parent_ref="goal/branch_1")
emit_eps_v1("agent.thought", {"text": "Probe 1B"}, ref="goal/branch_1/probe_b", parent_ref="goal/branch_1")
emit_eps_v1("agent.thought", {"text": "Branch 2"}, ref="goal/branch_2", parent_ref="goal/root")

# 2. Read all thoughts under "goal/branch_1/*" in a single batch seek:
branch_1_nodes = read_eps_v1("agent.thought", ref_prefix="goal/branch_1/")
assert len(branch_1_nodes) == 2  # probe_a and probe_b
```

### Recipe 2: Asynchronous Worker "Following Given Ref Passed"

```python
# Upstream task emits work specification and passes ref to Celery
work_ref = emit_eps_v1(
    "batch.item_prepared",
    {"item_id": 42, "payload_url": "s3://..."},
    ref="work_item_42",
)

# ... In Celery worker task receiving work_ref ...
def process_task(work_ref: str):
    # Fetch exact item by reference in O(1)
    record = read_eps_v1("batch.item_prepared", ref=work_ref)
    item_data = record["payload"]
    
    # Process item and emit result linked to original ref
    emit_eps_v1(
        "batch.item_completed",
        {"status": "success", "processed_records": 1000},
        ref=f"result/{work_ref}",
        parent_ref=work_ref,
    )
```

### Recipe 3: Owner Historical Aggregation (Cross-Run Billing / Storage)

```python
# Compute total storage audited across all runs for an owner in the last 7 days
since = datetime.now(timezone.utc) - timedelta(days=7)

historical_storage_events = read_eps_v1(
    "storagics.asset_persisted",
    all_for_owner=True,
    emitted_from=since,
    limit=500,
    for_owner=True,
)

total_bytes = sum(ev["payload"]["byte_count"] for ev in historical_storage_events)
```

### Recipe 4: Dedicated AsyncWork Delegation & Instant Dispatches (`submit_async_work_v1`)

```python
from authoring_w_persistence_async import submit_async_work_v1

# In a widget explosion: delegate heavy work to QUEUE_ASYNCWORK and finish in <100ms
handle = submit_async_work_v1(
    target_name="heavy_data_pipeline",
    target_kwargs={"doc_id": "doc_xyz", "num_chunks": 10},
    timeout_seconds=300,
)

# Store the lightweight ref in the widget's persisted state keys:
state_writes["async_job_ref"] = handle.ref
```

### Recipe 5: Cross-Widget State Wire Following via `AsyncWorkWidgetMixin`

```python
from authoring_w_persistence_async import AsyncWorkWidgetMixin
from thinkwidgets_static_runtime import ServiceReadyWidget

class DownstreamConsumerWidget(AsyncWorkWidgetMixin, ServiceReadyWidget):
    """Downstream widget that monitors ongoing work without blocking dispatch processing."""
    
    def on_step_mount(self, position, fill_data, limits, stats):
        # Read the async work ref from upstream wire
        job_ref = self.read_wire_value("upstream_widget", "async_job_ref")
        
        # Check completion instantly via O(1) BTree point-seek on done sandwich
        if self.is_async_work_done_v1(job_ref):
            result = self.get_async_work_result_v1(job_ref)
            self.set_state_value("final_output", result)
            self.mark_done()
        else:
            # Still working: inspect current progress percentage without stalling
            latest = self.get_async_work_latest_progress_v1(job_ref)
            pct = latest["percent"] if latest else 0.0
            self.set_micro_shell_attribute("progress_pct", pct)
            # Widget remains pending; external poller / frontend will dispatch when ready
```

---

## 7. Integration Certification via `_integration/`

The Thinkument test suite certifies concurrency, efficiency, and integrity under real workloads in `_integration/service/`:

1. **Celery-Backed Parallel Concurrency**:
   - Multiple widgets running concurrently on Celery workers.
   - Emitting onto shared epsilines with parallel sequence increments.
   - Proving zero sequence gaps, zero deadlocks, and exact idempotent conflict resolution.
2. **Parallel Multi-Pollers**:
   - Multiple concurrent pollers reading via cursor `after_seq` while writers are appending.
   - Proving zero dirty reads, role-modulated visibility isolation, and sub-millisecond query latency.
3. **Cross-Widget Asynchronous Coordination ("Following Given Ref Passed")**:
   - Upstream widget emits a task record, Celery worker processes it by reference in $O(1)$, and downstream poller reads child branches.
4. **Hierarchical Sub-Dir Batch Retrieval**:
   - Proving indexed prefix seeks on `ref_prefix` execute without full-table scans under high row counts.
