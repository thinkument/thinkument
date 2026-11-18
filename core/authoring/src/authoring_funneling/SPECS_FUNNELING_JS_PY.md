# Python and JavaScript Funnel Specifications

Status: Canonical specification pointer for the Python computation funnels and JavaScript presentation layer.

### Computation Layers (Python)
1. **Layer A (Host Foundation)**: `ServiceReadyWidget` in `think-app`, providing multi-db persistence, transaction atomicity, Layer A economics quoting, and `submit_async_work_v1()`.
2. **Layer B (Typed Strict PSMCW)**: [`a_typed_PSMCW_authoring/`](a_typed_PSMCW_authoring/README.md). Enforces finite static structural contracts on inputs, outputs, parameters, and promises (`Promise[T]`).
3. **Layer C (Typed JSON Widget Declaration)**: [`b_typed_JSON_widget_declaration/`](b_typed_JSON_widget_declaration/README_GRAMMAR_AND_FEATURES.md). Declarative single-envelope JSON widgets executing over `JSONfnchainTM` and offloading to `QUEUE_ASYNCWORK`.

### Presentation Layer (JavaScript / HAI App Packs)
- The public HAI `appPack` contract connects live backend theta and epsilines to the DOM through the `womb(packet, loopback)` membrane.
- When epsilines arrive (`asyncwork.progress`, `asyncwork.done`, `analytics.*`), the HAI opinionation routes them via `appPack.epsRoutes` to `callables.widgetNotification` and `callables.onEpsRow`.
- Detailed App Pack Reference: [`thinkument/about/service-innovations/scaling_app_packs/1_scaling_app_packs_base.MD`](../../../about/service-innovations/scaling_app_packs/1_scaling_app_packs_base.MD).
- Platform Computation Philosophies: [`thinkument/about/framework/20_philosophies_of_a_scalable_system_of_work.MD`](../../../about/framework/20_philosophies_of_a_scalable_system_of_work.MD).
