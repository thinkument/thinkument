# Funnel C: One JSONic Programming Language (Inline or Published Widgets)

> **Status:** Canonical specification and package documentation for Funnel C in `think-app-authoring`.  
> **Master Language:** `unified_typed_jsonic_think_program_v1` (`LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1`).  
> **Canonical Standard:** [21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD](../../../../about/framework/21_JSONic_sustainable_ergonomic_safe_PSMCW_programming_sealed_complete_formalism_specs_grammar_usage.MD).

---

## 1. Overview

`c_one_JSONic_programming_language_widgets_inline_or_published_imported` is the apex synthesis funnel in the Thinkument framework. It combines:
1. **Funnel A (`a_typed_PSMCW_authoring`)**: Level 2 Typed P with static D-expression bindings and wire typing symmetry.
2. **Funnel B (`b_typed_JSON_widget_declaration`)**: Pure declarative JSONic widget engine (`kind: "json_widget_v1"`) powered by `JSONfnchainTM`.

It enables authors to declare complete multi-step applications in a single JSON document where widgets can be:
- Declared **inline** directly inside `run.program.widgets.<id>.widget` (or `.inline_widget`).
- Referenced via **published shorthand strings** (e.g. `"com.example.catalog:v1_0_0"`).
- Mixed seamlessly within the same program topology.

---

## 2. Execution Pipeline

```text
  unified_typed_jsonic_think_program_v1 (P with inline & shorthand W)
                     │
                     ▼
  [1. Inline Widget Extraction & Content Fingerprinting]
     • Detect inline JSONic widgets (kind: "json_widget_v1")
     • Validate manifest via normalize_manifest_v1(manifest)
     • Compute content-addressed fingerprint: sha256(canonical_manifest)
     • Generate deterministic synthetic runtime ID: synthetic_inline_{fingerprint[:16]}
                     │
                     ▼
  [2. Memory Preparation & Kernel Registration]
     • Call prepare_json_widget_v1(manifest, widget_id=synthetic_id)
     • Register into process kernel via register_prepared_json_widget_v1(artifact)
     • Replace inline dict with synthetic_id string in program dict
                     │
                     ▼
  [3. Hand off to typed_think_program_v1 Compiler]
     • Call compile_strict_program(p, prepared_json_widgets=prepared_artifacts)
     • Validates D-expression bindings, port schemas, sources, parameters
     • Emits wires, strict_binding_recipe_v1, and parameter overlays
                     │
                     ▼
  [4. Standard Lowering to Kernel & App Table]
     • Lowers think_program_v1 -> thinking_flow_explicit
     • Provenance chain captures complete lowering history and inline widget manifests
```

---

## 3. Public Entrypoints

- `LANG_UNIFIED_TYPED_JSONIC_THINK_PROGRAM_V1`: The canonical language identifier string (`"unified_typed_jsonic_think_program_v1"`).
- `compile_unified_typed_jsonic_program(program, ...)`: Compiles an authored program, synthesizing in-memory classes for inline manifests and lowering to Level 2 Typed P.
- `lower_unified_typed_jsonic_think_program_v1(program, ...)`: Lowers the program all the way to `ProgramLoweringBundle` for execution in the continuity kernel.
- `register_unified_typed_jsonic_think_program_language_v1()`: Registers the language into the global runtime parser registry (`_langs_core`).
