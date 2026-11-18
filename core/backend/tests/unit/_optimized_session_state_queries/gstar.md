# Thinkument Public Session API Cheatsheet

## 0. The top-down model

A Thinkument program is a sequence of app-table function calls:

```text
Program
  = app_table_fn(args)
  -> app_table_fn(args)
  -> app_table_fn(args)
  -> ...
```

Each app-table function may emit:

```text
app_table_fn(args)
  -> globals patch
  -> optional multiframespec
```

A multiframespec is a public form topology:

```text
multiframespec
  -> frames
  -> spans
  -> datums
```

A span owns one or more datums:

```text
Span
  = {
      span_id,
      owns: [datum_id, ...]
    }
```

A datum is satisfied by fill/prefill/lifecycle facts:

```text
Datum
  = {
      datum_id,
      micros,
      optional lifecycle / Q widget
    }
```

A Q/lifecycle datum may:

```text
partial fill in
  -> blocked
  -> done
  -> forced_done
  -> reexplode into a new datum surface
       with new micros
       with fill/prefill/state/message/proc_notes
```

The public session rollout is:

```text
create_session(...)
  -> S receipt

step_session(...)
  -> S receipt
  -> maybe MANUALFILLNEEDEDSTEP
  -> maybe ATCOMPLETION

current_report(...)
  -> G report

query_session(...)
  -> G* explicit bounded query
```

---

# 1. The three public return classes

## S: command receipt

Used for mutations:

```python
api.create_session(...)
api.step_session(...)
api.undo_last_step(...)
api.redo_last_step(...)
api.delete_session(...)
```

Shape:

```python
{
    "kind": "session_command_receipt_v1",
    "ok": True,
    "operation": "step_session",
    "session_id": "...",
    "accepted": True,
    "event_kind": "MANUALFILLNEEDEDSTEP",
    "cursor": {...},
    "pending": {
        "form_id": "...",
        "frame_id": "...",
        "span_id": "...",
        "datum_widgets_on_this_span": ["DATUM_ID"],
    },
    "finished": False,
    "last_error": None,
}
```

Use S when you are driving the session.

S is intentionally tiny. It should not contain raw `ctx`, `multiframespec`, `snapshot`, `outputs`, `globals`, `html`, or full history.

---

## G: bounded report

Used for small reads:

```python
api.current_report(session_id)
api.outputs_report(session_id)
api.progress_report(session_id)
```

`current_report` answers:

```text
Where is the session now?
What event is current?
What span is pending?
Which datum fields are pending?
```

`outputs_report` answers:

```text
What output buckets exist?
How many keys do they have?
Which bounded key names exist?
```

Example:

```python
api.outputs_report(sid)
```

Returns:

```python
{
    "kind": "session_report_v1",
    "operation": "outputs_report",
    "event_kind": "OUTPUTS_REPORT",
    "counts": {
        "globals": 3,
        "form_prefills": 1,
        "form_fills": 4,
        "merged_fills": 5,
    },
    "keys": {
        "globals": ["trace_product", "trace_cap"],
        "form_prefills": ["NOTES"],
        "form_fills": ["CUSTOMER", "AMOUNT", "KYC"],
        "merged_fills": ["CUSTOMER", "AMOUNT", "KYC", "NOTES"],
    },
    "truncated_keys": {
        "globals": False,
        "form_prefills": False,
        "form_fills": False,
        "merged_fills": False,
    },
}
```

G is also intentionally tiny. It gives counts and keys, not raw full maps.

---

## G*: explicit bounded query

Used for deeper inspection:

```python
api.query_session(
    sid,
    query_kind="...",
    query={...},
)
```

G* is for questions like:

```text
Show me indexed write facts.
Show me exact datum values.
Show me the compact app-call/span/datum/Q trace.
Show me runtime write index summary.
```

Every G* result is explicit and bounded. Row-shaped queries use `max_results`.

---

# 2. Public API usage pattern

```python
from _thinkengine.public_facade import get_public_session_api

api = get_public_session_api()

created = api.create_session(
    manifest=[
        {
            "public_step_name": "loan_intake",
            "step_fn": "loan.intake.step",
            "fn_args": {
                "product": "loan",
                "cap": 500_000,
            },
        }
    ],
    initial_parameter_overrides={},
    session_metadata={...},
)

sid = created["session_id"]

receipt = api.step_session(sid)
if receipt["event_kind"] == "MANUALFILLNEEDEDSTEP":
    span = receipt["pending"]["span_id"]
    pending = receipt["pending"]["datum_widgets_on_this_span"]

receipt = api.step_session(
    sid,
    fill={
        "CUSTOMER.name": "Ada",
    },
)

report = api.current_report(sid)

outputs = api.outputs_report(sid)

trace = api.query_session(
    sid,
    query_kind="program_trace_table",
    query={
        "include_fn_args": True,
        "include_topology": True,
        "include_datum_values": True,
        "include_q_lifecycle": True,
        "max_results": 128,
    },
)
```

---

# 3. G* query grammar

The stable public query kinds are:

```python
query_kind="current_report"
query_kind="outputs_report"
query_kind="runtime_write_index_summary"
query_kind="runtime_writes"
query_kind="program_trace_table"
```

---

## 3.1 `current_report`

Wraps current G inside a G* envelope.

```python
api.query_session(
    sid,
    query_kind="current_report",
    query={},
)
```

Use when a tool wants all reads to go through one query endpoint.

Equivalent payload inside `result` is `api.current_report(sid)`.

---

## 3.2 `outputs_report`

Wraps output-summary G inside a G* envelope.

```python
api.query_session(
    sid,
    query_kind="outputs_report",
    query={},
)
```

Use when you want counts and keys through the query endpoint.

This is still not raw outputs. It is a bounded summary.

---

## 3.3 `runtime_write_index_summary`

Asks:

```text
What write kinds exist?
How many indexed write events exist?
What can I query?
```

```python
api.query_session(
    sid,
    query_kind="runtime_write_index_summary",
    query={},
)
```

Useful before exact inspection.

Example result shape:

```python
{
    "kind": "session_query_result_v1",
    "query_kind": "runtime_write_index_summary",
    "result": {
        "write_event_count": 12,
        "write_kinds": [
            "form_fill",
            "form_prefill",
            "datum_lifecycle",
            "state",
        ],
    },
}
```

---

## 3.4 `runtime_writes`

Precise lower-level indexed write facts.

Use this when you know the exact indexed facts you want.

```python
api.query_session(
    sid,
    query_kind="runtime_writes",
    query={
        "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
        "include_values": False,
        "max_results": 32,
    },
)
```

Metadata-only rows:

```python
{
    "write_kind": "form_fill",
    "key": "CUSTOMER",
    "step_fn": "loan.intake.step",
    "public_step_name": "loan_intake",
}
```

With values:

```python
api.query_session(
    sid,
    query_kind="runtime_writes",
    query={
        "write_kinds": ["form_fill"],
        "include_values": True,
        "max_results": 32,
    },
)
```

Rows may include:

```python
{
    "write_kind": "form_fill",
    "key": "CUSTOMER",
    "value": {"name": "Ada"},
}
```

### Runtime write query fields

```python
{
    "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
    "include_values": True,
    "max_results": 32,

    # optional filters, where indexed:
    "step_fn": "loan.intake.step",
    "public_step_name": "loan_intake",
    "arg_name": "product",
    "any_arg_names": ["product", "channel"],
    "arg_path": "product",
    "arg_value_equals": "loan",
    "last_k_invocations": 1,
}
```

Use `runtime_writes` when you need exact indexed rows.

---

## 3.5 `program_trace_table`

This is the ergonomic developer trace.

Use this for audit panes, debug views, compact result inspectors, and support tooling.

```python
api.query_session(
    sid,
    query_kind="program_trace_table",
    query={
        "include_fn_args": True,
        "include_topology": True,
        "include_datum_values": True,
        "include_q_lifecycle": True,
        "max_results": 128,
    },
)
```

The result is table-shaped:

```python
{
    "kind": "session_query_result_v1",
    "query_kind": "program_trace_table",
    "result": {
        "kind": "program_trace_table_v1",
        "max_results": 128,
        "row_count": 17,
        "total_available": 17,
        "truncated": False,
        "rows": [
            ...
        ],
    },
}
```

---

# 4. `program_trace_table` rows

The trace table has four row kinds.

## 4.1 `app_call`

Shows the app-table function call.

```python
{
    "row_kind": "app_call",
    "call_index": 0,
    "public_step_name": "loan_intake",
    "step_fn": "loan.intake.step",
    "fn_args": {
        "product": "loan",
        "cap": 500_000,
        "channel": "public-api-test",
    },
}
```

`fn_args` appears only when:

```python
"include_fn_args": True
```

Use this to answer:

```text
Which app-table fn was configured?
With which args?
```

---

## 4.2 `span`

Shows compact topology.

```python
{
    "row_kind": "span",
    "form_id": "loan.form",
    "frame_id": "INTAKE",
    "span_id": "S_KYC",
    "owns": ["KYC"],
}
```

Use this to answer:

```text
What frames/spans/datums did the program emit?
Which datums belong to which span?
```

---

## 4.3 `datum_io`

Shows compact datum fill/prefill facts.

Without values:

```python
{
    "row_kind": "datum_io",
    "datum_id": "CUSTOMER",
    "span_id": "S_CUSTOMER",
    "write_kind": "form_fill",
}
```

With values:

```python
{
    "row_kind": "datum_io",
    "datum_id": "CUSTOMER",
    "span_id": "S_CUSTOMER",
    "write_kind": "form_fill",
    "value": {"name": "Ada"},
}
```

Values appear only when:

```python
"include_datum_values": True
```

Use this to answer:

```text
What final datum values exist?
Which prefills were present?
What did the user submit?
What did Q eventually accept?
```

---

## 4.4 `datum_reexplosion`

Shows the compact current/latest Q lifecycle window.

Example current done window:

```python
{
    "row_kind": "datum_reexplosion",
    "datum_id": "KYC",
    "span_id": "S_KYC",
    "status": "done",
    "from_micros": ["ssn4"],
    "q_state": {"phase": "done"},
}
```

Example reexplode window, if still retained:

```python
{
    "row_kind": "datum_reexplosion",
    "datum_id": "KYC",
    "span_id": "S_KYC",
    "status": "reexplode",
    "from_micros": ["ssn4"],
    "to_micros": ["confirm"],
    "prefill": {"confirm": "yes"},
    "q_state": {"phase": "confirm"},
}
```

Use this to answer:

```text
Which datum had Q lifecycle behavior?
What is the current/latest lifecycle status?
What lifecycle state is visible?
What micros did the datum originate from?
```

Important: `program_trace_table` currently exposes a **current/latest lifecycle window**, not a full append-only historical list of every reexplode transition.

If you need full historical lifecycle transitions later, add a separate query kind such as:

```python
query_kind="datum_lifecycle_history"
```

or extend trace grammar explicitly:

```python
query_kind="program_trace_table",
query={
    "include_q_lifecycle": True,
    "lifecycle_scope": "history",
    "max_results": 128,
}
```

Do not silently overload the current trace table to return unbounded lifecycle history.

---

# 5. Which endpoint should I use?

## Driving a session

Use S commands:

```python
api.create_session(...)
api.step_session(...)
api.undo_last_step(...)
api.redo_last_step(...)
api.delete_session(...)
```

---

## Showing “where are we now?”

Use G:

```python
api.current_report(sid)
```

or G* wrapper:

```python
api.query_session(sid, query_kind="current_report", query={})
```

---

## Showing “what outputs exist?”

Use G:

```python
api.outputs_report(sid)
```

This gives counts and keys only.

---

## Showing exact final datum values

Use `program_trace_table` when you want ergonomic table rows:

```python
api.query_session(
    sid,
    query_kind="program_trace_table",
    query={
        "include_datum_values": True,
        "max_results": 128,
    },
)
```

Use `runtime_writes` when you want exact indexed write rows:

```python
api.query_session(
    sid,
    query_kind="runtime_writes",
    query={
        "write_kinds": ["form_fill"],
        "include_values": True,
        "max_results": 128,
    },
)
```

---

## Showing fn args + spans + datum IO + Q windows

Use full trace:

```python
api.query_session(
    sid,
    query_kind="program_trace_table",
    query={
        "include_fn_args": True,
        "include_topology": True,
        "include_datum_values": True,
        "include_q_lifecycle": True,
        "max_results": 128,
    },
)
```

This is the main developer debug/audit view.

---

## Showing low-level index facts

Use runtime writes:

```python
api.query_session(
    sid,
    query_kind="runtime_writes",
    query={
        "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
        "include_values": False,
        "max_results": 32,
    },
)
```

Then turn on values only when needed:

```python
api.query_session(
    sid,
    query_kind="runtime_writes",
    query={
        "write_kinds": ["form_fill"],
        "include_values": True,
        "max_results": 32,
    },
)
```

---

# 6. Query discipline

Every public query should follow these rules.

## 6.1 Default is small

S and G do not return raw payloads.

```text
No raw ctx.
No raw snapshot.
No raw program_map.
No raw multiframespec.
No raw outputs.
No raw globals.
No raw HTML.
No full history.
```

## 6.2 Values are explicit

Values appear only when the caller asks:

```python
"include_values": True
```

or:

```python
"include_datum_values": True
```

## 6.3 Completeness is explicit

Every row-shaped query must be capped:

```python
"max_results": 128
```

The response says:

```python
{
    "truncated": True,
    "max_results": 128,
}
```

when more data exists.

## 6.4 Absurd requests are capped

This is safe:

```python
"max_results": 999_999
```

because public API caps it to:

```python
ABSOLUTE_QUERY_MAX_RESULTS_V1
```

## 6.5 Table-shaped beats blob-shaped

Prefer:

```python
[
    {"row_kind": "app_call", ...},
    {"row_kind": "span", ...},
    {"row_kind": "datum_io", ...},
]
```

over:

```python
{
    "entire_snapshot": {...},
    "entire_multiframespec": {...},
    "entire_outputs": {...},
}
```

Tables are easier to cap, page, filter, render, and audit.

---

# 7. How to add a new public G* query

A new query should be added when a caller needs a repeated, named inspection pattern that is too awkward to express with `runtime_writes`.

Good examples:

```python
query_kind="program_trace_table"
query_kind="datum_lifecycle_history"
query_kind="span_completion_table"
query_kind="validation_error_table"
query_kind="app_call_summary"
```

Bad examples:

```python
query_kind="raw_snapshot"
query_kind="raw_ctx"
query_kind="raw_outputs"
query_kind="full_multiframespec"
```

Those break the bounded public contract.

A new G* query should have:

```python
{
    "kind": "session_query_result_v1",
    "ok": True,
    "session_id": sid,
    "query_kind": "...",
    "result": {
        "kind": "..._v1",
        "max_results": 128,
        "truncated": False,
        "rows": [...],
    },
}
```

For non-row summary queries, keep scalar/count/key metadata:

```python
{
    "kind": "some_summary_v1",
    "counts": {...},
    "keys": {...},
}
```

Checklist for a new query:

```text
1. Is it explicitly named?
2. Is it bounded?
3. Does it avoid raw ctx/snapshot/multiframespec/output maps?
4. Does it have max_results if row-shaped?
5. Are values behind an explicit include_* flag?
6. Does it return table rows or scalar summaries?
7. Does it expose stable row_kind/result kind names?
8. Does it document scope: current, latest, history, summary, or exact?
```

---

# 8. Should step functions use this same G* grammar?

Short answer: conceptually yes, mechanically no.

The public G* grammar is for **outside callers**:

```text
apps
controllers
frontends
admin tools
audit views
debug panes
tests
```

Step functions are inside the runtime belly. They should not normally call:

```python
get_public_session_api().query_session(...)
```

from inside their own execution.

Why not?

```text
1. Reentrancy risk:
   A step fn is already executing inside a session transition.

2. Layering:
   Public API wraps raw runtime behavior for outside callers.
   Step fns are runtime code, not public clients.

3. Determinism:
   Step fn logic should depend on explicit inputs:
       state
       fn_args
       controlled runtime services
   not arbitrary public session queries.

4. Performance:
   Public G* does sanitation/projection meant for app-facing output.
   Runtime belly code may need lower-level indexed helpers directly.

5. Coupling:
   If step fns depend on public debug queries, changing presentation queries
   can accidentally change program semantics.
```

The correct pattern is:

```text
Outside caller:
    use public G* grammar.

Inside step fn:
    use explicit runtime-provided services/helpers,
    or pass needed facts through state/fn_args,
    or use internal runtime_write_index helpers if the engine intentionally
    provides them to step fn code.
```

So the grammar can be shared as a **conceptual query language**, but not by having step functions call the public façade.

Better internal design:

```python
def step_fn(state, *, runtime_query=None, **fn_args):
    facts = runtime_query(
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_fill"],
            "include_values": True,
            "max_results": 32,
        },
    )
```

But that `runtime_query` should be an internal, explicitly injected service, not the public session API singleton.

Rule:

```text
Public API G*:
    for outside readers.

Internal runtime query service:
    for step functions, if needed.

Same concepts.
Separate seams.
```

---

# 9. Trace query: the tested ergonomic path

The tested full trace query is:

```python
trace = api.query_session(
    sid,
    query_kind="program_trace_table",
    query={
        "include_fn_args": True,
        "include_topology": True,
        "include_datum_values": True,
        "include_q_lifecycle": True,
        "max_results": 128,
    },
)
```

Read it as:

```text
Give me a compact table containing:
  app_call rows
  span rows
  datum_io rows
  datum_reexplosion rows

Include:
  fn args
  topology
  datum values
  current/latest Q lifecycle windows

Return:
  at most 128 rows
```

Typical developer rendering:

```text
APP CALL
  loan_intake
  step_fn = ped.trace.loan_intake.step
  args = {product: loan, cap: 500000}

SPAN
  S_CUSTOMER owns CUSTOMER
  S_AMOUNT   owns AMOUNT
  S_KYC      owns KYC

DATUM IO
  CUSTOMER form_fill = {name: Ada}
  AMOUNT   form_fill = {value: 400000}
  KYC      form_fill = {confirm: yes}

Q LIFECYCLE
  KYC status = done
  from_micros = [ssn4]
  q_state = {phase: done}
```

This is the front-facing “debug table” query.

---

# 10. Final mental model

Use the smallest surface that answers the question.

```text
I want to drive the program.
  -> S command: step_session

I want to know where it is.
  -> G: current_report

I want output counts/keys.
  -> G: outputs_report

I want exact write facts.
  -> G*: runtime_writes

I want a developer-readable trace table.
  -> G*: program_trace_table

I want a new repeated inspection view.
  -> Add a new named G* query.

I want raw ctx/snapshot/multiframespec.
  -> Not from public_api.
```

The contract is:

```text
S/G:
    tiny by default.

G*:
    explicit, bounded, inspectable.

runtime_writes:
    precise indexed facts.

program_trace_table:
    ergonomic compact trace.

step fns:
    do not call public_api;
    use injected/internal runtime query services if they need runtime facts.
```
