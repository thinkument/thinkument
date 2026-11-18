# think-app-authoring

`think-app-authoring` is the dedicated package for all Thinkument Program, Session Metadata, and Computations (P SM C) authoring primitives and funnels.

It cleanly presents 4 top-level authoring hubs directly under `src/`:

## 1. Pure Backend Primitives (`src/authoring_pure_backend_no_funnel/`)
- Pure, typed Python templates that create valid, executable `ThinkProgram` and `SessionMetadata` instances.
- Exercises core execution features: funked execution, puppeteering, role modulation, and app pack bindings (`template_thinkprogram_SM_app_packs.py`).
- Requires only the engine and framework base to execute, with zero funneling dependencies.

## 2. Funneled Authoring Hub (`src/authoring_funneling/`)
- Service-ready typed PSMCW authoring and declarative widget creation:
  - `a_typed_PSMCW_authoring/`: High-level typed builder and decorator-based widget authoring (`@strict_widget`).
  - `b_typed_JSON_widget_declaration/`: Declarative pure-JSON widget definitions with runtime validation.
  - `examples/`: Canonical creative reference implementations (`metal`, `crystal`).
- Re-exports the complete authoring API for downstream packages.

## 3. Funneled Authoring Templates (`src/authoring_funneling_templates/`)
- Catalogued public templates (`catalog.py`, `catalog.v1.json`) available for rapid creative composition.
- Modular facets (`metal_micro`, `public_json_widget`, `typed_program`, etc.) with strict schema validation.

## 4. Preloaded Assets (`src/authoring_funneling_preloaded_assets/`)
- Catalogued inhouse JSON widget declarations (`inhouse_JSON_widgets/catalog.v1.json`, `entries/`).
- Trusted library manifests and schemas.

> [!NOTE]
> App pack publication machinery and registry have moved to `ways_to_create.app_pack_publication_registrar` in `think-app`. Authoring packs are declared via pluggy entrypoints referencing the registrar.
