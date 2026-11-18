# Computation Philosophies: Zero Local Heavy Compute & Dispatches in a Snap

> **Canonical Source of Truth**: This document is consolidated into the framework master documentation:
> [`thinkument/about/framework/20_philosophies_of_a_scalable_system_of_work.MD`](../../../../about/framework/20_philosophies_of_a_scalable_system_of_work.MD).
> Please consult Document 20 for full architectural formalisms, Wire Typing Symmetry, and Philosophy 3 (Public JSONic Authoring & The Single-Envelope Doctrine).

This document defines the core computation philosophies governing all runtime execution, widget dispatches, and worker architectures across the Thinkument and BuildMyBook platforms.


---

## The Dual-Philosophy Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PHILOSOPHY 1: ZERO LOCAL HEAVY COMPUTE (EXTERNAL WEB APIS + STORAGICS STORAGE)                                   │
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

## 1. Philosophy 1: Zero Local Heavy Compute (External Web APIs + Storagics Storage)

### The Architectural Problem It Solves:
In traditional monolithic platforms, background workers often run CPU-intensive tasks locally (such as rendering large PDFs, crunching ML embeddings, or running image transformations). This leads to:
1. Massive CPU contention between interactive user requests and background jobs.
2. Huge memory spikes triggering container OOM (Out-Of-Memory) restarts.
3. Bulky binary data stored in relational database tables, degrading indexing and query latency.

### The Thinkument Law:
> **The host and worker machines are orchestrators and proxies, never heavy local compute nodes.**

1. **Outsourced Work**: Every expensive, resource-using operation is executed through external API-based web services (OpenAI, Anthropic, Stripe, Vercel, external renderers).
2. **Object Storage via `storagics`**: Generated assets, documents, and media are uploaded directly to S3/Linode through `storagics`.
3. **Compact Relational Footprint**: The PostgreSQL `RunEpsMessage` table stores only compact URLs (`"asset_url": "https://s3.amazonaws.com/..."`), status indicators, and execution timestamps. Rows remain $<1\text{KB}$.
4. **Virtual Pool Feasibility**: Because worker tasks spend their lifecycle awaiting network I/O rather than pegging CPUs, a single scaled Railway worker machine can virtually multiplex hundreds of concurrent external API operations alongside interactive dispatches without physical container fragmentation.

---

## 2. Philosophy 2: "Dispatches in a Snap" via Async Delegation & Cross-Widget Wires

### The Interactive Problem It Solves:
In P SM C (Program, State Machine, Continuity Kernel), user clicks trigger dispatches targeting widgets on program steps.
- If a widget explosion synchronously waits for an external web service (e.g. awaiting an LLM response for 12 seconds), the session lock is held for 12 seconds, Celery dispatch processes are blocked, and the user UI freezes.

### The Thinkument Law:
> **Widget explosions must resolve in milliseconds. Heavy external work must be delegated asynchronously, and downstream dependencies must be resolved via static wires.**

### The 2-Step Paradigm:

```
 STEP 1: SUBMITTER WIDGET (EXPLOSION COMPLETES IN <5ms)
 ┌────────────────────────────────────────────────────────────────────────┐
 │ class DocumentPlannerWidget(AsyncWorkWidgetMixin, ServiceReadyWidget): │
 │     def on_generate_click(self):                                       │
 │         handle = self.submit_async_work_v1(                            │
 │             target="ai.generate_chapters",                             │
 │             args={"prompt_id": 104},                                   │
 │             timeout_seconds=300,                                       │
 │         )                                                              │
 │         # Write compact reference to widget state:                     │
 │         self.state["chapter_task_ref"] = handle.ref                    │
 │         # Explosion finishes immediately! Lock released in <5ms.       │
 └────────────────────────────────────┬───────────────────────────────────┘
                                      │
                                      ▼ Wire: "step1_planner.chapter_task_ref"
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
 │             # Reflect live intermediate progress in micro-shell:       │
 │             latest = handle.get_latest_progress()                      │
 │             self.micros["status_display"] = f"Generating: {latest.pct}%│
 │             # Widget remains pending (step does not advance)           │
 │         else:                                                          │
 │             # Work complete! Extract Storagics asset URL:              │
 │             result = handle.get_result()                               │
 │             self.state["chapters_url"] = result["asset_url"]           │
 │             self.mark_done()  # Program advances to Step 3!            │
 └────────────────────────────────────────────────────────────────────────┘
```

### The 3 Ways Cross-Widget Runtimes Interact with Ongoing Work:

#### Mode 1: Non-Blocking Interactive Polling (Live-I/O Runs)
- **Mechanism**: The browser UI sends periodic poll dispatches or heartbeats to `/run/{slug}/dispatch/`.
- **Consumer Explosion**:
  1. Consumer widget reads `ref = self.wires["task_ref"]`.
  2. Calls `handle = self.get_async_work_handle_v1(ref)`.
  3. Executes `<1ms` point seek: `handle.is_done()`.
  4. If ongoing: updates micro-shell with `latest = handle.get_latest_progress()`, keeping `self.is_done = False`. The browser displays the progress bar or spinner.
  5. If done: reads `handle.get_result()`, writes to state, and marks `self.is_done = True`. The step completes!

#### Mode 2: Synchronous Bounded Wait (Black-Box & Batch Automation Runs)
- **Mechanism**: For automated, non-interactive runs (e.g. headless scripts, API black-box runs), there is no human browser polling in real-time.
- **Consumer Explosion**:
  1. Consumer widget calls `result = handle.wait_until_done(timeout_seconds=60, poll_interval=1.0)`.
  2. The handle sleeps in short non-blocking increments, checking `read_eps_v1("asyncwork.done", ...)` until complete or timed out.
  3. Yields the final result in the same execution cycle without requiring external poll loops.

#### Mode 3: Same-Step Peer Widgets & Chain Reaction Dispatches
- **Mechanism**: Two widgets reside on the **exact same program step**.
  - Widget A receives user fill, starts async work via `submit_async_work_v1`, and writes `handle.ref` to state.
  - The framework's **chain-reaction dispatch** immediately triggers dependent peer Widget B on the same step.
  - Widget B reads Widget A's wire, initializes its progress micro-shell, and begins listening for progress updates seamlessly.

---

## 3. Master Anchors & Documentation Sitemap

This philosophy document is anchored permanently across the platform:

1. **Master Subapp Specification**:
   [think-app/.../subapps/asyncwork/README.md](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/subapps/asyncwork/README.md)
2. **Master Epsilines Framework Architecture**:
   [thinkument/about/framework/19_epsilinesTM_subapps__framework_formalism_usage_growth.MD](file:///Users/adarshjeewajee/Desktop/startups/thinkument/about/framework/19_epsilinesTM_subapps__framework_formalism_usage_growth.MD)
3. **Master Live Usage Quickstart**:
   [quickstart_guide__epsilines_usages_live.md](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/quickstart_guide__epsilines_usages_live.md)
4. **Master Channel Declaration Quickstart**:
   [quickstart_guide__new_epsilines.md](file:///Users/adarshjeewajee/Desktop/startups/thinkument/framework/think-app/src/epsilinesTM_serveragnostic/quickstart_guide__new_epsilines.md)
5. **High-Level Authoring Primitives**:
   `thinkument/framework/think-app-authoring/src/authoring_w_persistence_async/`
