┌──────────────────────────────────────────────────────────────────────────────┐
│                  datomatonTM DATUM LIFECYCLE WIDGET                          │
│                                                                              │
│  LHS INPUTS q                                                                │
│  ───────────                                                                 │
│                                                                              │
│  Step fn multiframespec.app_form_id ───────▶ q["form_id"]                    │
│  Step fn frames[].frame_id ────────────────▶ q["frame_id"]                   │
│  Step fn spans[].span_id ─────────────────▶ q["span_id"]                    │
│  Step fn spans[].owns[] ──────────────────▶ q["datum_id"]                   │
│                                                                              │
│  Step fn datums[datum_id] ────────────────▶ q["datum"]                      │
│       or previous reexplode result["datum"] ─▶ q["datum"]                  │
│                                                                              │
│  Step fn fills[datum_id] ────────────────▶ q["prefill"]                    │
│       or previous reexplode result["prefill"] ─▶ q["prefill"]              │
│                                                                              │
│  User/runtime fill candidate ─────────────▶ q["raw_fill"]                  │
│       or previous reexplode result["fill"] ─▶ q["raw_fill"]                │
│                                                                              │
│  Runtime validation of raw fill vs datum ─▶ q["partial_fill"]              │
│                                                                              │
│  Runtime structural check ────────────────▶ q["structurally_satisfied"]     │
│                                                                              │
│  Lifecycle initial_state ────────────────▶ q["state"] first time            │
│       or previous result["state"] ───────▶ q["state"] later                 │
│                                                                              │
│  Previous result["message(s)"] ──────────▶ q["messages"]                   │
│                                                                              │
│  Previous result["proc_notes"] ─────────────▶ q["proc_notes"]                    │
│                                                                              │
│  Lifecycle flags ────────────────────────▶  q["max_reexplosions"]           │
│                                           ▶ q["max_proc_notes"]                │
│                                           ▶ q["max_messages"]               │
│                                                                              │
│  Runtime counter ────────────────────────▶ q["reexplode_count"]            │
│                                                                              │
│  Runtime/controller/mount/fill cause ────▶ q["signal"]                     │
│                                           ▶ q["ctx"]                        │
│                                                                              │
│  Runtime event sink ─────────────────────▶ q["emit"]                       │
│                                                                              │
│                                                                              │
│  RHS OUTPUT result                                                           │
│  ─────────────────                                                           │
│                                                                              │
│  result["status"] == "done"                                                  │
│       ├─ marks datum lifecycle satisfied                                     │
│       ├─ may commit accepted fill through normal form-fill path              │
│       ├─ may carry result["state"] into later same-form mount/eval           │
│       ├─ may append result["message(s)"]                                     │
│       └─ may emit result["events"]                                           │
│                                                                              │
│  result["status"] == "blocked"                                               │
│       ├─ keeps datum/span unsatisfied                                        │
│       ├─ may carry result["state"]                                           │
│       ├─ may append result["message(s)"]                                     │
│       ├─ may append result["proc_notes"]                                        │
│       └─ may emit result["events"]                                           │
│                                                                              │
│  result["status"] == "reexplode"                                             │
│       ├─ result["datum"] ───────▶ next q["datum"]                            │
│       ├─ result["fill"] ────────▶ next q["raw_fill"] candidate               │
│       │                            └─ validation ─▶ next q["partial_fill"]   │
│       ├─ result["prefill"] ─────▶ next q["prefill"]                          │
│       ├─ result["state"] ───────▶ next q["state"]                            │
│       ├─ result["message(s)"] ──▶ next q["messages"]                         │
│       ├─ result["proc_notes"] ─────▶ next q["proc_notes"]                          │
│       ├─ increments counter ────▶ next q["reexplode_count"]                  │
│       └─ result["events"] ──────▶ transient event packets                    │
│                                                                              │
│  q["emit"](...)                                                              │
│       └─ immediate transient event packet during widget execution            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

