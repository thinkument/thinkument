# Authoring Funnels: Architecture & Navigation

> **Status:** Canonical source of truth for authoring funnels in `think-app-authoring`.  
> **Underlying Standard:** [21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD](../../../about/framework/21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD)  
> **Master Philosophies:** [20_philosophies_of_a_scalable_system_of_work.MD](../../../about/framework/20_philosophies_of_a_scalable_system_of_work.MD)

---

## 1. The Three Authoring Funnels

`think-app-authoring` structures program and widget authoring into three cohesive, cascading funnels that lower deterministically to the Thinkument continuity kernel:

```text
====================================================================================================
                             THE THREE-TIER AUTHORING FUNNEL FAMILY
====================================================================================================

 Funnel C: c_one_JSONic_programming_language_widgets_inline_or_published_imported/
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ • Level 3: unified_typed_jsonic_think_program_v1 (The Apex Unified PSMCW Language)     │
 │ • Inline JSONic Widgets ($W \in \text{kind: json\_widget\_v1}$) declared inside $P$   │
 │ • Published widgets referenced via shorthand string identifiers                        │
 │ • Content-addressed synthetic class synthesis & zero-leak kernel registration          │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │ synthesizes inline W via Funnel B & lowers via Funnel A
                                             ▼
 Funnel A: a_typed_PSMCW_authoring/
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ • Level 2: typed_think_program_v1 (Higher Typed P Engine)                              │
 │ • Static D-expression binding recipes (compile_strict_program, strict_binding_recipe_v1)│
 │ • Law of Wire Typing Symmetry: Producer Promise[T] unwrap to T for consumer D-bindings │
 │ • Strict Mouth/Belly/Rear port contracts and static wire topology                     │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │ lowers to Base JSON P
                                             ▼
                                     think_program_v1
                                             │ lowers to execution kernel
                                             ▼
                              thinking_flow_explicit (think.kernel.v1)

                                     ▲
                                     │ supplies declarative W definitions
 Funnel B: b_typed_JSON_widget_declaration/
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ • Standalone Declarative JSONic Widget Factory (json_widget_v1)                        │
 │ • Finite manifest normalization (normalize_manifest_v1) and strict port schemas       │
 │ • Inner DSL Engine: JSONfnchainTM flow compilation & THINKUMENT_GLOBAL_VOCAB           │
 │ • Automatic Celery queue segregation: QUEUE_DISPATCH (<150ms snap) vs QUEUE_ASYNCWORK  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Granular Funnel Responsibilities

### Funnel A: `a_typed_PSMCW_authoring/` (Level 2: Typed P Engine)
- **Role:** Owns the typed program compilation pipeline (`compile_strict_program`) and static D-expression bindings.
- **Port Schema Normalization:** Validates `inputs`, `outputs`, and `parameters` schemas via `bindings2bindingsTM`.
- **Wire Typing Symmetry:** Enforces that when an upstream widget emits `outputs={'item': Promise(T)}`, downstream consumers declare clean semantic `inputs={'item': T}`, unwrapping the promise automatically across the static wire.
- **Recipe Generation:** Emits compiled `strict_binding_recipe_v1` strings and parameter bundles for the runtime.
- **Documentation:** [`a_typed_PSMCW_authoring/README.md`](a_typed_PSMCW_authoring/README.md).

### Funnel B: `b_typed_JSON_widget_declaration/` (Pure JSONic Widget Factory)
- **Role:** The standalone factory and grammar engine for declarative JSON widgets ($W$).
- **Single-Envelope Doctrine (Philosophy 3):** Authors define self-contained widget manifests containing Mouth (`declaration.inputs`, `args`), Belly (`signals.mount`, `signals.fill` via `JSONfnchainTM`), and Rear (`declaration.outputs`, `micros`).
- **Vocabularies:** Composes pure in-memory transforms from Custom Python Ops (`text.*`, `math.*`, `data.*`) and external calls from Vendor Hub Ops (`vendor.llm.*`, `vendor.media.*`, `asyncwork.*`).
- **Physical Pool Segregation:** In-memory transforms run fast-path on `QUEUE_DISPATCH`; operations with vendor calls or async waiting automatically yield promises and execute on `QUEUE_ASYNCWORK`.
- **Documentation:** [`b_typed_JSON_widget_declaration/README_GRAMMAR_AND_FEATURES.md`](b_typed_JSON_widget_declaration/README_GRAMMAR_AND_FEATURES.md).

### Funnel C: `c_one_JSONic_programming_language_widgets_inline_or_published_imported/` (Level 3: Apex Unified Language)
- **Role:** The apex synthesis funnel creating the unified, sealed PSMCW language: **`unified_typed_jsonic_think_program_v1`**.
- **Inline + Published Integration:** Allows an author to declare bespoke JSONic widgets inline directly inside `run.program.widgets`, or reference published catalog widgets via shorthand strings.
- **Content-Addressable Synthetic Synthesis:** Extracts inline manifests, computes deterministic SHA256 fingerprints, synthesizes in-memory classes via Funnel B (`prepare_json_widget_v1`), registers them into the kernel, and hands off to Funnel A for static D-binding validation.
- **Logical Equivalence Invariant:** Programs authored purely inline, purely published, or as a hybrid mix produce mathematically identical state transitions, wire data passing, and telemetry streams.
- **Universal Registration:** Accepted natively by all service endpoints taking a $P$ (`/sessions/`, `/starters/`, `/black-box-runs/`).

---

## 3. Authoring Decision Guide & Entrypoints Matrix

| Use Case | Recommended Funnel | Canonical Language / Grammar | Primary Python Entrypoints |
| :--- | :--- | :--- | :--- |
| **Self-Contained Single-File App**<br>Rapid prototyping, ad-hoc workflows, or tightly coupled bespoke widgets | **Funnel C** | `unified_typed_jsonic_think_program_v1` | `compile_unified_typed_jsonic_program`<br>`lower_unified_typed_jsonic_think_program_v1`<br>`register_unified_typed_jsonic_think_program_language_v1` |
| **Enterprise Catalog Assembly**<br>Composing multi-step flows strictly from pre-published, approved organization widgets | **Funnel A** | `typed_think_program_v1` | `compile_strict_program`<br>`lower_typed_think_program_v1`<br>`register_typed_think_program_language_v1` |
| **Standalone Widget Publishing**<br>Authoring a reusable, general-purpose widget family to publish to the global marketplace | **Funnel B** | `json_widget_v1` | `normalize_manifest_v1`<br>`prepare_json_widget_v1`<br>`register_prepared_json_widget_v1` |
| **Base Execution Kernel Target**<br>Low-level engine execution and testing | Kernel Core | `thinking_flow_explicit` (`think.kernel.v1`) | `pull_thinkwidget_class_into_kernel_v1`<br>`lower_think_program_to_kernel_program_v1` |

---

## 4. Related Specifications & Architecture Documents
- **Grand Unification Standard:** [`thinkument/about/framework/21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD`](../../../about/framework/21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD).
- **Master Platform Philosophies:** [`thinkument/about/framework/20_philosophies_of_a_scalable_system_of_work.MD`](../../../about/framework/20_philosophies_of_a_scalable_system_of_work.MD).
- **Standalone Flow Engine:** [`independent-tooling/src/JSONfnchainTM/README.md`](../../../../../independent-tooling/src/JSONfnchainTM/README.md).
- **JSONic Authoring Guide:** [`independent-tooling/src/JSONfnchainTM/AUTHOR-ME.md`](../../../../../independent-tooling/src/JSONfnchainTM/AUTHOR-ME.md).
