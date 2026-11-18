# Formalism behind the examples

The examples share the same Thinkument widget lifecycle and ordinary run
protocol. They differ in authoring form and in how they assemble presentation
assets.

## Crystal: two authoring forms in one strict pack

Crystal is the one-pack cross-funnel example. `crystal.seed` and
`crystal.consumer` are strict Python widgets (Layer B). `crystal.json_ideator`
is declared in JSON (Layer C), which compiles to the same strict widget
lifecycle and is admitted by the same `TypedAuthoringProfile`. Prefer JSON
when the approved operation vocabulary can describe the behavior; use strict
Python for behavior that needs imperative logic. Both forms receive the same
profile and runtime guarantees. Crystal publishes one manifest and requires
no Metal chrome metadata.

## Metal: adapt family slots, then publish K packs

Metal demonstrates how a family can adapt its own aesthetic slots and shared
widget/micro rendering library into HAI's public synchronous `appPack` slots.
Its checked JavaScript factory composes each declared chromeset into one
manifest. The rule is one shared widget/rendering library plus K chromeset
declarations produces K app packs. Widgets and renderers are shared across
those packs; there is no pack for every widget/chrome pairing.

## Shared browser contract

Both families export their final object through
`defineAppPackV1`, which delegates validation and freezing to HAI's existing
`validateAppPack`. HAI owns heartbeat, selection, role-aware rendering,
composer behavior, and outbound dispatch. Widget controls feed the regular HAI
fill composer, whose STEP path validates and dispatches `userFill` actions.
Family-local slots remain adapters; they do not redefine HAI's contract.

See the [authoring funnel guide](../../../about/scaling_app_packs/1_layers_of_authoring_funneling.MD),
the [Crystal family guide](crystal/README.md), and the
[Metal family guide](metal/README.md).
