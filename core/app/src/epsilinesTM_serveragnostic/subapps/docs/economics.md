# Accounted widgets and reusable wallets

See the [canonical financial guide](../../../../../../../financial-core/wallet-billing/README.md) for policy decisions and the [Thinkument financial constitution](../../../../../../about/service-financials/our_financial_constitution_panorama_and_malleable_policies.MD) for host configuration and operations. This document describes widget authoring.

The framework owns vendor selection, usage adaptation, operation execution and analytics. `wallet-credits` owns allocation accounting; `wallet-billing` owns commercial policy and payment funding. Neither package imports the framework. Host bindings live in `home.wallet_adapters` and `home.wallet_hosting`.

Edit the single `home/financial_policy.json` sheet for global markup, conversion, subscription tiers, schedules and top-ups. Upstream tariffs live in the referenced `home/vendor_rates.json`; per-card markup is rejected. Rates in the shipped example are fictional. Install the packages, run `migrate` and `migrate_economics`, then set `ECONOMICS_ENABLED=true`. The wallet uses a separate autocommit `economics` connection. See the [wallet README](../../../../../../../financial-core/wallet-credits/README.md) and [billing README](../../../../../../../financial-core/wallet-billing/README.md) for package installation and recovery details.

Authoring imports remain `authoring_funnel.a_service_tracked_widget_computation.economics` and `authoring_funnel.a_service_tracked_widget_computation.base.ServiceReadyWidget`. `EconomicsWidgetMixin.reserve_vendor_usage_v1` adapts vendor descriptors/maxima through a bound trusted provider. Vendor execution never runs in a database transaction. The reusable wallet accepts only approved maximum underlying USD, authoritative actual USD, pricing and opaque evidence.

Use `execute_vendor_operation_v1(prepared, client=..., maximum_units=..., call_key=...)` inside a widget lifecycle. Each dispatched billable attempt requires its own stable call key. Execution happens once. Complete response-native usage settles before returning. When a successful response lacks usable cost, the wallet captures the approved estimate, persists a resolver reference and the original Analytica operation ID, and returns the successful output. The host enqueues a one-shot, read-only lookup after commit; lookup runs outside the wallet transaction and never repeats paid work. Retries use deterministic 0–20% jitter over the 1, 2, 4, 8, 12, and 15 second schedule, bounded by the 60-second deadline and reservation expiry.

Provider execution failures remain platform-paid under the existing failure rules. For a successful call whose cost receipt is still unresolved at the reconciliation deadline, the captured estimate remains charged and a durable breach incident is recorded; later evidence is handled as an adjustment rather than reopening the original hold. The reservation context guarantees cleanup even on exceptions. Successful earlier independent operations retain their charges if a later operation fails.

The global exact Decimal markup and USD-per-credit conversion freeze at authorization. One credit is 1,000,000 microcredits; conversion rounds upward once, never to cents. Final debit is computed across original hold splits in ascending ID order; unused amounts return in reverse order. If actual cost exceeds the cap, the cap is charged and an overrun incident is durable even if analytics emission fails. No observed ratio automatically changes future maxima.

Included allocations spend before purchased/manual funds. Holds preserve source credits through expiry/renewal; released expired portions retire. Paid coverage lives locally in economics so lapse gating works without waiting for a worker. There is no overdraft, automatic top-up, queue, or paid-operation retry.

Run `rav run test_wallet_economics` and `rav run test_wallet_billing` for the
reusable packages, then `rav run twn_tkt` for the Thinkument host suite. The
service suite exercises authenticated ownership, migrations, live-I/O and
black-box execution, verified fake funding, correlated settlement, and the
registered Stripe sandbox E2E.
## Managed vendor assets

Hosts may bind `storagics.context.bind_provider` alongside economics. Prepared
operations expose an optional `asset_capability` implementing the pure storagics
contract. A declared media operation requires that binding; it cannot fall back
to unstored media. The accounted widget reserves forecast bytes before wallet credits,
executes once, resolves vendor cost, materializes and verifies all declared assets,
and only then charges the customer. Text-only calls keep their existing sequence.

Each call and its required assets is one deliverable. Storage failure is
platform-paid, without reversing earlier delivered calls. Replays retrieve a
durable completed result or explicit recovery state. Ambiguous generation is
never automatically repeated. Vendor receipts remain financial evidence; the
`audit-storage-usage` channel links delivery IDs, asset IDs and byte measurements.

The widget imports no Django settings or backend SDK. Backend identity, private
URLs, ownership and effective tier capacity come from the host. See
`financial-core/wallet-storage/README.md` and the workspace `storagics_implementation_plan.md` for
capacity, cleanup and recovery invariants.
