# Custom ThinkProgramTM Stricter Grammars: Architectural Pattern & Blueprint

This document captures the formal architecture, proof of implementation, and scaling blueprint for authoring custom stricter $P$ grammars atop the Thinkument framework and service platform.

---

## 1. Proof of Concept: `typed_think_program_v1`

The automated acceptance test suite in `thinkument/service-innovations/tests/integration/test_typed_program_language_e2e.py` validates that:
1. Higher typed $P$ programs with static $D$-expression bindings (`D.text`, `D.ref`, `D.list`, `D.dict`, `D.map`) can be submitted as raw JSON without manual pre-compilation.
2. The backend lowerer compiles the program through a 3-tier chain:
   $$\text{typed\_think\_program\_v1} \longrightarrow \text{think\_program\_v1} \longrightarrow \text{thinking\_flow\_explicit} \longrightarrow \text{app\_table\_manifest}$$
3. The `run_from_here` facade mounts, steps, and executes the lowered manifest in live sessions with dynamic wire evaluation and state audits.
4. `thinkument/service` REST endpoints (Starters, Live I/O runs, and Black-Box runs) natively ingest, validate, and launch the grammar.

---

## 2. Why Custom Stricter Grammars Work

Thinkument's execution engine is built on **Separation of Formalisms**:
* The **Continuity Kernel (`think.kernel.v1`)** only understands normalized step transitions, state writes, and low-level data wires (`app_table_manifest`).
* The **Base Ergonomic Layer (`think_program_v1`)** provides human-readable steps and widgets.
* **Higher Grammars (`typed_think_program_v1`, etc.)** can enforce strict type contracts, closed schemas, static expression algebras, or domain-specific notations (e.g. statecharts, workflow graphs, DAGs) at the outer boundary.

Because lowering is a pure AST transformation that happens *before* kernel execution, you can define **infinite specialized $P$ grammars** without modifying the kernel runtime.

```text
  ┌────────────────────────────────────────────────────────┐
  │ CUSTOM HIGHER GRAMMARS                                 │
  │ - typed_think_program_v1 (Metal / Crystal / D-algebra) │
  │ - dag_think_program_v1   (Graph-based declarative flow)│
  │ - statechart_program_v1  (Hierarchical state machines) │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼ [lower_<custom_lang>()]
  ┌────────────────────────────────────────────────────────┐
  │ BASE PROGRAM LAYER (think_program_v1)                  │
  │   - Ergonomic step flow & logical widget declarations  │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼ [lower_think_program_v1()]
  ┌────────────────────────────────────────────────────────┐
  │ CONTINUITY KERNEL (think.kernel.v1)                    │
  │   - AppTableManifest, step functions, trident events   │
  └────────────────────────────────────────────────────────┘
```

---

## 3. The 4-Step Blueprint for Creating a New $P$ Grammar

To add a new grammar (e.g., `dag_think_program_v1` or `domain_specific_program_v1`), follow this exact 4-step recipe established by `typed_think_program_v1`:

### Step 1: Implement the Lowerer
Create a lowering function that transforms your custom syntax down to an ordinary `think_program_v1` dictionary:

```python
from copy import deepcopy
from typing import Any
from _thinkengine._parsing._higher_lang_grammars._langs_core import (
    ProgramLoweringBundle,
    lower_program_to_app_table_bundle,
    register_program_language,
    is_program_language_registered,
)
from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    register_think_program_language_v1,
    overlay_initial_parameter_overrides_onto_program_v1,
)

LANG_MY_CUSTOM_PROGRAM_V1 = "my_custom_program_v1"

def lower_my_custom_program_v1(
    program: Any,
    *,
    initial_parameter_overrides: Any = None,
) -> ProgramLoweringBundle:
    # 1. Apply runtime parameter overrides
    effective = overlay_initial_parameter_overrides_onto_program_v1(
        program, initial_parameter_overrides=initial_parameter_overrides
    )
    
    # 2. Compile your custom syntax down to think_program_v1
    lowered_think_program = my_custom_compiler(effective)
    lowered_think_program["kind"] = LANG_THINK_PROGRAM_V1

    # 3. Recursively lower to AppTable
    register_think_program_language_v1()
    bundle = lower_program_to_app_table_bundle(
        program_language=LANG_THINK_PROGRAM_V1,
        program=lowered_think_program,
        initial_parameter_overrides=initial_parameter_overrides,
    )

    # 4. Augment lowering chain provenance
    provenance = dict(bundle.provenance or {})
    chain = list(provenance.get("lowering_chain") or [])
    chain.insert(0, {
        "language": LANG_MY_CUSTOM_PROGRAM_V1,
        "artifact": LANG_THINK_PROGRAM_V1,
    })
    provenance["lowering_chain"] = chain
    provenance["source_program_language"] = LANG_MY_CUSTOM_PROGRAM_V1
    provenance["source_program"] = deepcopy(program)

    return ProgramLoweringBundle(
        app_table_manifest=bundle.app_table_manifest,
        provenance=provenance,
        session_surface=bundle.session_surface,
    )
```

### Step 2: Register the Language in the Engine Core
Ensure step functions and grammar entries are registered:

```python
def register_my_custom_program_language_v1() -> None:
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()
    if not is_program_language_registered(LANG_MY_CUSTOM_PROGRAM_V1):
        register_program_language(
            language=LANG_MY_CUSTOM_PROGRAM_V1,
            lower=lower_my_custom_program_v1,
            description="My Custom Stricter ThinkProgramTM grammar.",
        )
```

### Step 3: Wire into Service Ingress Seams
Expose the new grammar name in `thinkument/service`:
1. **Starters (`public/PSM_starters/serializers.py`):**
   Add `LANG_MY_CUSTOM_PROGRAM_V1` to `ACCEPTED_SERVICE_PROGRAM_LANGUAGES` and ensure `StartersConfig.ready()` in `apps.py` calls the register function.
2. **Live I/O Runs (`public/PSMC_sessions/prod_runs_w_io/models.py`):**
   Add `LANG_MY_CUSTOM_PROGRAM_V1` to `Run.ACCEPTED_SERVICE_PROGRAM_LANGUAGES`.
3. **Funked Black-Box Runs (`public/PSMC_sessions/prod_runs_black_box_funked/launch.py`):**
   Update `_language()` to accept `LANG_MY_CUSTOM_PROGRAM_V1`.

### Step 4: Verify via CI Runsheets (`zxy_fast` & `zxy_deep`)
Add an integration test targeting:
* Engine registry lookup (`is_program_language_registered`).
* Lowering bundle output (`bundle.app_table_manifest` & `provenance["lowering_chain"]`).
* Live execution via `run_from_here.create_live_session_from_program`.
* Service Starter validation (`validate_service_program_or_raise`).

Run with:
```bash
rav run zxy_fast
```

---

## 4. Architectural Rules for Scaled Grammars

1. **Lowering Must Be Pure:** The lowerer must only perform AST transformations. It should not make network calls or mutate global runtime state.
2. **Preserve Provenance:** Always record the source program and lowering links in `provenance["lowering_chain"]`. This enables live inspection tools, ateliers, and debuggers to display both the high-level DSL and the compiled kernel tables.
3. **Fail Closed Early:** Syntax errors, schema mismatches, and invalid references must raise during lowering/validation at the Starter/API boundary rather than crashing during step execution.
4. **Decouple from Widget Lifecycles:** Higher grammars organize the *orchestration* of widgets. Individual widgets remain independent datum automatons with their own lifecycle, signal catchers, and state writes.
