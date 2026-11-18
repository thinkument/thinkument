# `asyncwork` Subapp & The Two Core Computation Philosophies

This document defines the architectural foundation and operational philosophy of the **`asyncwork`** Epsiline subapp within the Thinkument platform and framework (`epsilinesTM_serveragnostic`).

- **Governing Platform Philosophies:** [`COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/COMPUTATION_PHILOSOPHIES__EXTERNAL_APIS_AND_DISPATCHES_IN_A_SNAP.md)
- **Master Live Usage Quickstart:** [`quickstart_guide__epsilines_usages_live.md`](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/quickstart_guide__epsilines_usages_live.md)

---

## 1. Top-Down Vision: The Dual Computation Philosophies

The Thinkument platform operates under two foundational system engineering philosophies that govern all asynchronous execution, widget runtimes, and worker pool topologies:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PHILOSOPHY 1: ZERO LOCAL HEAVY COMPUTE (EXTERNAL WEB APIS + STORAGICS)                                          │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Expensive, resource-intensive work is NEVER computed locally on Railway worker CPUs.                          │
│ • All heavy work is delegated to specialized external API-based web services (LLMs, media generators, Stripe). │
│ • Heavy artifacts (PDFs, datasets, images, reports) are stored directly in S3/Linode via Storagics.            │
│ • PostgreSQL "eps_log" rows store ONLY compact URLs, execution metadata, and dead JSON pointers (<1KB).          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       ▲
                                                       │ INSPIRES & ENABLES
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PHILOSOPHY 2: "DISPATCHES IN A SNAP" VIA ASYNC DELEGATION & CROSS-WIDGET WIRES                                  │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Interactive UserActions and step dispatches resolve in milliseconds (<50ms).                                  │
│ • Submitter Widget explodes, delegates heavy external work via `self.submit_async_work_v1()`, writes the compact │
│   `ref` to its state keys, and completes its explosion INSTANTLY. Session lock is released immediately.         │
│ • Consumer Widget connects to Submitter Widget via static wires, reads the `ref`, and polls for progress/done.  │
│ • When done, Consumer Widget extracts the Storagics asset URL, marks itself complete, and advances the program! │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Philosophy 1: External Web APIs & Storagics Storage

### Core Principles:
1. **Lightweight Orchestration**:
   - The platform’s worker machines are **proxies and orchestrators**, not heavy number-crunchers.
   - Tasks running on the `asyncwork` queue spend their time performing network I/O: calling external vendor APIs, streaming tokens, awaiting webhooks, or polling vendor job statuses.
2. **Object Storage via `storagics`**:
   - Whenever an external web service produces a payload (such as an audio file, a rendered document, or an analyzed dataset), it is immediately uploaded to object storage via `storagics`.
   - The PostgreSQL `RunEpsMessage` row stores only the resulting S3 URL (`"asset_url": "https://s3.amazonaws.com/..."`), status, and timing metadata.
   - The PostgreSQL database remains compact, highly indexed, and blazingly fast.
3. **Queue & Worker Pool Justification**:
   - Because async tasks are I/O-bound (waiting on external HTTP responses), they require virtually zero CPU and negligible RAM (~20MB).
   - This justifies our **virtual worker pool separation on a single scaled Railway machine**: interactive dispatch tasks and external I/O tasks coexist on the same worker machine without competing for CPU resources.

---

## 3. Philosophy 2: "Dispatches in a Snap" via Cross-Widget Wire Following

Interactive responsiveness is the lifeblood of P SM C (Program, State Machine, Continuity Kernel). If a widget tries to synchronously await a 15-second external API call during its explosion, the session lock is held, the dispatch queue backs up, and the user experiences latency.

By splitting work into **Submission** and **Wire Consumption**, dispatches become "breeze fast":

```
 STEP 1: SUBMITTER WIDGET (EXPLODES IN <5ms)
 ┌────────────────────────────────────────────────────────────────────────┐
 │ class DocumentPlannerWidget(AsyncWorkWidgetMixin, ServiceReadyWidget): │
 │     def on_generate_click(self):                                       │
 │         handle = self.submit_async_work_v1(                            │
 │             target="ai.generate_chapters",                             │
 │             args={"prompt_id": 104},                                   │
 │             timeout_seconds=300,                                       │
 │         )                                                              │
 │         # Write compact reference to state key:                        │
 │         self.state["chapter_task_ref"] = handle.ref                    │
 │         # Explosion finishes immediately!                              │
 └────────────────────────────────────┬───────────────────────────────────┘
                                      │
                                      ▼ State Wire: "step1.state.chapter_task_ref"
                                      │
 STEP 2: CONSUMER WIDGET (POLLS VIA WIRES & MARKS DONE)
 ┌────────────────────────────────────┴───────────────────────────────────┐
 │ class ChapterReviewerWidget(AsyncWorkWidgetMixin, ServiceReadyWidget): │
 │     # Statically declared wire:                                        │
 │     # wires = {"task_ref": "step1_planner.chapter_task_ref"}           │
 │                                                                        │
 │     def on_poll_step(self):                                            │
 │         ref = self.wires["task_ref"]                                   │
 │         handle = self.get_async_work_handle_v1(ref)                      │
 │                                                                        │
 │         if not handle.is_done():                                       │
 │             # Reflect intermediate progress in micro-shell:            │
 │             latest = handle.get_latest_progress()                      │
 │             self.micros["status_display"] = f"Generating: {latest.pct}%│
 │             # Widget remains pending (step does not advance)           │
 │         else:                                                          │
 │             # Work complete! Extract result from Storagics:            │
 │             result = handle.get_result()                               │
 │             self.state["chapters_url"] = result["asset_url"]           │
 │             self.mark_done()  # Program advances to Step 3!            │
 └────────────────────────────────────────────────────────────────────────┘
```

### System Benefits:
- **Sub-50ms Dispatch Cycles**: The user dispatch on Step 1 executes in milliseconds. The session lock is released immediately.
- **Continuous Visual Telemetry**: The UI poller on Step 2 polls `/run/{slug}/eps/` and `/events/`, rendering live progress ticks from `asyncwork.progress` in the widget micro-shell without holding server-side locks.
- **Fail-Safe & Resilient**: If the browser disconnects or the user closes the laptop, the background Celery task continues running. When the user returns 10 minutes later, Step 2 inspects the wire, checks `handle.is_done()`, and immediately picks up the result.

---

## 4. The 3-Phase Sandwiching Epsilon Lifecycle

All execution in `asyncwork` compiles cleanly into three canonical Epsiline channels under `EpsAppSpecV1(name="asyncwork")`:

1. **`asyncwork.announce` (Parent Announcement)**:
   - Emitted by Submitter Widget upon calling `submit_async_work_v1()`.
   - Confirms root `ref` (e.g. `ref="task_99"`).
   - Service hook (`MODE_PERSISTENCE_AND_FN_POST`) commits to PostgreSQL and automatically enqueues Celery task to `QUEUE_ASYNCWORK`.
2. **`asyncwork.progress` (Child Intermediate Progress)**:
   - Emitted periodically by the running Celery worker task.
   - Carries `parent_ref="task_99"`.
   - Payload: `{"pct": 45, "status": "calling_vendor", "msg": "Awaiting Claude response..."}`.
3. **`asyncwork.done` (Sandwiching Terminal Emit)**:
   - Emitted once by the Celery worker task upon completion, error, or timeout.
   - Carries `parent_ref="task_99"`, `ref="task_99/done"`, `terminal=True`.
   - Payload: `{"outcome": "success", "result": {"asset_url": "..."}, "duration_sec": 14.2}`.

---

## 5. Architectural Invariants

1. **Strict JSON Safety**: All arguments, payloads, and results are dead JSON (`assert_dead_json` enforced). No `pickle` across Redis or Celery.
2. **Whitelisted Target Registry**: Only functions registered via `@async_work_target` may be executed by the worker pool.
3. **$<1\text{ms}$ BTree Point Seeks**: Checking doneness via `read_eps_v1("asyncwork.done", ref=f"{ref}/done")` hits composite BTree indexes on `event_id` and `span_id`, providing instantaneous status resolution.
4. **Zero Head-of-Line Blocking**: Dedicated Redis queues (`celery` vs `asyncwork`) and `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` guarantee interactive dispatches are never queued behind heavy external API calls.
