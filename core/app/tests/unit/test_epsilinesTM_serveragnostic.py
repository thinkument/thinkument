from __future__ import annotations

"""Unit tests for epsilinesTM_serveragnostic standalone execution and contracts."""

from dataclasses import dataclass
from unittest.mock import MagicMock
import pytest

from epsilinesTM_serveragnostic import (
    AUDIT_INS_CHANNEL,
    AUDIT_OUTS_CHANNEL,
    AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL,
    AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1,
    AUDIT_VENDOR_USAGE_CHANNEL,
    AnalyticaOperationStreamValidatorV1,
    AnalyticaProtocolError,
    EconomicsNotConfigured,
    FakeEconomicsProvider,
    RecordingEmitter,
    ReservationClosed,
    ReservationRequest,
    VendorUsageUnavailable,
    VendorOperationError,
    analytica_envelope_v1,
    bind_provider_v1,
    execute_accounted_vendor_operation,
    get_provider_v1,
    has_provider_v1,
    is_analytica_channel_v1,
)
from wallet_economics.usage import (
    VendorCallDescriptor,
    VendorReceipt,
    VendorResult,
    VendorUsage,
)


@dataclass
class DummyPreparedCall:
    descriptor: VendorCallDescriptor
    asset_capability: Any = None
    outcome: str = "success"
    completeness: str = "complete"
    provider_details: dict[str, Any] | None = None

    def execute(self, client: Any = None) -> VendorResult:
        if self.outcome != "success":
            receipt = VendorReceipt(
                version="1",
                vendor="test_vendor",
                operation="test_op",
                requested_model="m1",
                resolved_model="m1",
                requested_pricing_dimensions={"tokens": 10},
                resolved_pricing_dimensions={"tokens": 10},
                provider_request_id="req_123",
                outcome="error",
                usage=VendorUsage(
                    schema="test_schema",
                    units={},
                    completeness="unknown",
                    provider_details=self.provider_details or {},
                ),
                elapsed_ms=15,
            )
            return VendorResult(value=None, receipt=receipt)
        receipt = VendorReceipt(
            version="1",
            vendor="test_vendor",
            operation="test_op",
            requested_model="m1",
            resolved_model="m1",
            requested_pricing_dimensions={"tokens": 10},
            resolved_pricing_dimensions={"tokens": 10},
            provider_request_id="req_123",
            outcome="success",
            usage=VendorUsage(
                schema="test_schema",
                units={"tokens": 10} if self.completeness == "complete" else {},
                completeness=self.completeness,
                provider_details=self.provider_details or {},
            ),
            elapsed_ms=15,
        )
        return VendorResult(value={"text": "hello from general plane"}, receipt=receipt)


def test_provider_context_binding():
    assert not has_provider_v1()
    with pytest.raises(EconomicsNotConfigured):
        get_provider_v1()

    fake = FakeEconomicsProvider()
    with bind_provider_v1(fake):
        assert has_provider_v1()
        assert get_provider_v1() is fake

    assert not has_provider_v1()


def test_channel_recognition():
    assert is_analytica_channel_v1(AUDIT_INS_CHANNEL)
    assert is_analytica_channel_v1(AUDIT_OUTS_CHANNEL)
    assert is_analytica_channel_v1(AUDIT_VENDOR_USAGE_CHANNEL)
    assert is_analytica_channel_v1("audit-custom.step")
    assert not is_analytica_channel_v1("custom-channel")
    assert not is_analytica_channel_v1(None)


def test_analytica_envelope_with_general_plane_identity():
    envelope = analytica_envelope_v1(
        channel=AUDIT_VENDOR_USAGE_CHANNEL,
        schema="thinkument.analytica.audit-vendor-usage.v1",
        event="vendor_usage",
        operation_id="op-12345",
        event_index=1,
        caller_identity="general_plane:data_pipeline_step",
        body={
            "vendor": "test_vendor",
            "operation": "test_op",
            "status": "success",
            "elapsed_ms": 12.5,
            "request": {"model": "gpt-4"},
            "usage": {"tokens": 10},
            "attributes": {"batch_id": "b-99"},
            "error": None,
        },
    )
    assert envelope["widget_class"] == "general_plane:data_pipeline_step"
    assert envelope["operation_id"] == "op-12345"
    assert envelope["event_index"] == 1
    assert envelope["channel"] == AUDIT_VENDOR_USAGE_CHANNEL


def test_stream_validator():
    validator = AnalyticaOperationStreamValidatorV1()
    ins = analytica_envelope_v1(
        channel=AUDIT_INS_CHANNEL,
        schema="thinkument.analytica.audit-ins.v1",
        event="input",
        operation_id="op-1",
        event_index=0,
        caller_identity="task:runner",
        body={
            "trigger": "start",
            "authored_args": {"input": "test"},
            "history_wires": {},
            "current_fills": {},
            "signal": None,
        },
    )
    validator.accept_v1(AUDIT_INS_CHANNEL, ins)

    usage = analytica_envelope_v1(
        channel=AUDIT_VENDOR_USAGE_CHANNEL,
        schema="thinkument.analytica.audit-vendor-usage.v1",
        event="vendor_usage",
        operation_id="op-1",
        event_index=1,
        caller_identity="task:runner",
        body={
            "vendor": "openai",
            "operation": "chat",
            "status": "success",
            "elapsed_ms": 45.0,
            "request": None,
            "usage": None,
            "attributes": None,
            "error": None,
        },
    )
    validator.accept_v1(AUDIT_VENDOR_USAGE_CHANNEL, usage)

    reconciliation = analytica_envelope_v1(
        channel=AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL,
        schema=AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1,
        event="vendor_cost_reconciliation",
        operation_id="op-1",
        event_index=2,
        caller_identity="task:runner",
        body={
            "vendor_call_id": "res-1",
            "charge_id": "chg-1",
            "original_operation_id": "vendor-op-1",
            "vendor": "openai",
            "operation": "chat",
            "settlement_status": "reconciled",
            "estimated_usd": "0.05",
            "actual_usd": "0.04",
            "estimated_microcredits": 50,
            "calculated_microcredits": 40,
            "charged_microcredits": 40,
            "refunded_microcredits": 10,
            "excess_microcredits": 0,
            "usage": {"usd_picodollar": 40000000000},
            "reconciliation_details": {},
        },
    )
    validator.accept_v1(AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL, reconciliation)

    outs = analytica_envelope_v1(
        channel=AUDIT_OUTS_CHANNEL,
        schema="thinkument.analytica.audit-outs.v1",
        event="output",
        operation_id="op-1",
        event_index=3,
        caller_identity="task:runner",
        body={
            "outcome": {"kind": "satisfied"},
            "state_writes": {"result": "done"},
            "state_deleted": [],
        },
    )
    validator.accept_v1(AUDIT_OUTS_CHANNEL, outs)


def test_breach_reconciliation_represents_unresolved_usage_as_null():
    validator = AnalyticaOperationStreamValidatorV1()
    ins = analytica_envelope_v1(
        channel=AUDIT_INS_CHANNEL,
        schema="thinkument.analytica.audit-ins.v1",
        event="input",
        operation_id="reconcile:reservation-1",
        event_index=0,
        caller_identity="task:vendor-cost-worker",
        body={
            "trigger": "vendor-cost-reconciliation",
            "authored_args": {},
            "history_wires": {},
            "current_fills": {},
            "signal": None,
        },
    )
    validator.accept_v1(AUDIT_INS_CHANNEL, ins)
    envelope = analytica_envelope_v1(
        channel=AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL,
        schema=AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1,
        event="vendor_cost_reconciliation",
        operation_id="reconcile:reservation-1",
        event_index=1,
        caller_identity="task:vendor-cost-worker",
        body={
            "vendor_call_id": "reservation-1",
            "charge_id": "charge-1",
            "original_operation_id": "source-operation-1",
            "vendor": "vercel",
            "operation": "T1",
            "settlement_status": "breach_cap_retained",
            "estimated_usd": "0.05",
            "actual_usd": None,
            "estimated_microcredits": 5000,
            "calculated_microcredits": None,
            "charged_microcredits": 5000,
            "refunded_microcredits": 0,
            "excess_microcredits": 0,
            "usage": {},
            "reconciliation_details": {"failure_reason": "provider_cost_unavailable"},
        },
    )
    assert envelope["body"]["calculated_microcredits"] is None
    validator.accept_v1(AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL, envelope)
    outs = analytica_envelope_v1(
        channel=AUDIT_OUTS_CHANNEL,
        schema="thinkument.analytica.audit-outs.v1",
        event="output",
        operation_id="reconcile:reservation-1",
        event_index=2,
        caller_identity="task:vendor-cost-worker",
        body={"outcome": {"kind": "breach_cap_retained"}, "state_writes": {}, "state_deleted": []},
    )
    validator.accept_v1(AUDIT_OUTS_CHANNEL, outs)
    validator.assert_closed_v1()


def test_general_plane_execute_accounted_vendor_operation_success():
    fake_provider = FakeEconomicsProvider()
    emitter = RecordingEmitter()

    descriptor = VendorCallDescriptor(
        version="1",
        operation="test_op",
        vendor="test_vendor",
        requested_model="m1",
        requested_pricing_dimensions={"tokens": 10},
        request_fingerprint="fp-12345678",
        request_summary={"tokens": 10},
        execution_limits={},
    )
    prepared = DummyPreparedCall(descriptor=descriptor)

    with bind_provider_v1(fake_provider):
        result = execute_accounted_vendor_operation(
            prepared,
            client=None,
            maximum_units={"tokens": 10},
            call_key="general-task-001",
            emitter=emitter,
            caller_identity="general_plane:standalone_task",
            attribution={"task_id": "task-001"},
        )

    assert result.value == {"text": "hello from general plane"}
    assert result.receipt.outcome == "success"

    # Verify provider calls
    assert len(fake_provider.reservations) == 1
    assert len(fake_provider.charges) == 1

    # Verify telemetry emitted
    usage_events = emitter.by_channel(AUDIT_VENDOR_USAGE_CHANNEL)
    assert len(usage_events) == 1
    env = usage_events[0]
    assert env["widget_class"] == "general_plane:standalone_task"
    assert env["body"]["vendor"] == "test_vendor"
    assert env["body"]["status"] == "success"
    assert env["body"]["usage"]["usage"]["units"] == {"tokens": 10}


def test_general_plane_execute_accounted_vendor_operation_failure():
    fake_provider = FakeEconomicsProvider()
    emitter = RecordingEmitter()

    descriptor = VendorCallDescriptor(
        version="1",
        operation="test_op",
        vendor="test_vendor",
        requested_model="m1",
        requested_pricing_dimensions={"tokens": 10},
        request_fingerprint="fp-fail-123",
        request_summary={},
        execution_limits={},
    )
    prepared = DummyPreparedCall(descriptor=descriptor, outcome="error")

    with bind_provider_v1(fake_provider):
        with pytest.raises(VendorOperationError):
            execute_accounted_vendor_operation(
                prepared,
                client=None,
                maximum_units={"tokens": 10},
                call_key="general-task-fail",
                emitter=emitter,
                caller_identity="general_plane:failing_task",
            )

    # Provider recorded platform_paid incident
    assert len(fake_provider.incidents) == 1
    assert fake_provider.incidents[0]["reason"] == "operation_failed"

    # Telemetry emitted with error
    usage_events = emitter.by_channel(AUDIT_VENDOR_USAGE_CHANNEL)
    assert len(usage_events) == 1
    assert usage_events[0]["body"]["status"] == "error"


@pytest.mark.parametrize(
    "completeness,provider_details,should_charge",
    [
        ("complete", {}, True),
        ("unknown", {"resolver_reference": {"generation_id": "gen-1"}}, True),
        ("unknown", {}, False),
    ],
)
def test_charge_accepts_complete_or_resolvable_usage_only(
    completeness, provider_details, should_charge
):
    fake_provider = FakeEconomicsProvider()
    descriptor = VendorCallDescriptor(
        version="1",
        operation="test_op",
        vendor="test_vendor",
        requested_model="m1",
        requested_pricing_dimensions={"tokens": 10},
        request_fingerprint=f"fp-{completeness}-{bool(provider_details)}",
        request_summary={},
        execution_limits={},
    )
    prepared = DummyPreparedCall(
        descriptor=descriptor,
        completeness=completeness,
        provider_details=provider_details,
    )
    with bind_provider_v1(fake_provider):
        if should_charge:
            execute_accounted_vendor_operation(
                prepared,
                client=None,
                maximum_units={"tokens": 10},
                call_key=f"call-{completeness}-{bool(provider_details)}",
            )
            assert len(fake_provider.charges) == 1
            assert not fake_provider.incidents
        else:
            with pytest.raises(VendorUsageUnavailable, match="valid resolver_reference"):
                execute_accounted_vendor_operation(
                    prepared,
                    client=None,
                    maximum_units={"tokens": 10},
                    call_key="call-unresolvable",
                )
            assert not fake_provider.charges
            assert fake_provider.incidents[0]["reason"] == "cost_resolution_failed"


def test_pending_charge_persists_original_analytica_operation_id():
    class CapturingProvider(FakeEconomicsProvider):
        def charge(self, reservation_id, usage):
            self.last_usage = usage
            return super().charge(reservation_id, usage)

    provider = CapturingProvider()
    descriptor = VendorCallDescriptor(
        version="1",
        operation="test_op",
        vendor="test_vendor",
        requested_model="m1",
        requested_pricing_dimensions={"tokens": 10},
        request_fingerprint="fp-operation-id",
        request_summary={},
        execution_limits={},
    )
    prepared = DummyPreparedCall(
        descriptor=descriptor,
        completeness="unknown",
        provider_details={"resolver_reference": {"generation_id": "gen-1"}},
    )
    with bind_provider_v1(provider):
        execute_accounted_vendor_operation(
            prepared,
            client=None,
            maximum_units={"tokens": 10},
            call_key="call-operation-id",
            operation_id="source-analytica-operation",
        )

    assert provider.last_usage.usage.provider_details[
        "original_operation_id"
    ] == "source-analytica-operation"


def test_eps_channel_sheet_invariants():
    from epsilinesTM_serveragnostic.epsiline_spec_and_growth_sheet import assert_eps_channel_sheet_invariants_v1
    assert_eps_channel_sheet_invariants_v1()


def test_eps_registry_lookups_and_unregistered_error():
    from epsilinesTM_serveragnostic import (
        AUDIT_INS_CHANNEL,
        UnregisteredEpsChannelError,
        policy_of_v1,
        visibility_of_v1,
        require_registered_eps_channel_v1,
    )
    spec = require_registered_eps_channel_v1(AUDIT_INS_CHANNEL)
    assert spec.channel == AUDIT_INS_CHANNEL
    assert spec.visibility == "owner-only"
    assert spec.app == "analytica"
    assert visibility_of_v1(AUDIT_INS_CHANNEL) == "owner-only"
    assert policy_of_v1(AUDIT_INS_CHANNEL) is spec

    with pytest.raises(UnregisteredEpsChannelError):
        require_registered_eps_channel_v1("nonexistent.channel")


def test_ambient_eps_sink_and_generality_registration():
    from epsilinesTM_serveragnostic import (
        EpsAppSpecV1,
        EpsChannelSpecV1,
        RecordingEmitter,
        bind_eps_sink_v1,
        emit_eps_v1,
        register_eps_app_v1,
        register_eps_channel_v1,
    )

    # V6 Generality: register a non-Analytica app and custom channel
    custom_app = EpsAppSpecV1(
        name="custom_search_flow",
        channels=(
            EpsChannelSpecV1(
                channel="custom.search.query_expansion",
                app="custom_search_flow",
                schema="custom_search_schema_v1",
                event="query_expanded",
                validator=lambda raw: raw,
                visibility="all-no-modulation",
            ),
        ),
    )
    register_eps_app_v1(custom_app)

    emitter = RecordingEmitter()
    with bind_eps_sink_v1(emitter):
        emit_eps_v1("custom.search.query_expansion", {"query": "vector databases", "expansions": ["ann", "hnsw"]})

    emitted = emitter.by_channel("custom.search.query_expansion")
    assert len(emitted) == 1
    assert emitted[0]["expansions"] == ["ann", "hnsw"]


# ---------------------------------------------------------------------------
# Stream 19: Comprehensive Vessel Specification & Dynamic Resolver Tests
# ---------------------------------------------------------------------------

def test_vessel_spec_allowed_mode_and_retention_invariants():
    from epsilinesTM_serveragnostic import (
        EpsChannelSpecV1,
        MODE_PERSISTENCE,
        MODE_NONE,
        RETENTION_DURABLE,
        RETENTION_TTL,
        RETENTION_NONE,
        VISIBILITY_OWNER_ONLY,
        VISIBILITY_ALL_WITH_MODULATION,
        VISIBILITY_ALL_NO_MODULATION,
    )
    from epsilinesTM_serveragnostic.core.contracts import InvalidEpsChannelSpecificationError

    # 1. Valid: persistence + durable
    spec1 = EpsChannelSpecV1(
        channel="test.vessel.durable",
        app="test_app",
        mode=MODE_PERSISTENCE,
        retention=RETENTION_DURABLE,
        visibility=VISIBILITY_OWNER_ONLY,
    )
    assert spec1.mode == MODE_PERSISTENCE
    assert spec1.retention == RETENTION_DURABLE
    assert spec1.ttl_seconds is None

    # 2. Valid: persistence + ttl with positive ttl_seconds
    spec2 = EpsChannelSpecV1(
        channel="test.vessel.ttl",
        app="test_app",
        mode=MODE_PERSISTENCE,
        retention=RETENTION_TTL,
        ttl_seconds=3600,
        visibility=VISIBILITY_ALL_WITH_MODULATION,
    )
    assert spec2.retention == RETENTION_TTL
    assert spec2.ttl_seconds == 3600

    # 3. Invalid: persistence + ttl with missing or <= 0 ttl_seconds fails closed
    with pytest.raises(InvalidEpsChannelSpecificationError):
        EpsChannelSpecV1(
            channel="test.vessel.invalid_ttl1",
            app="test_app",
            mode=MODE_PERSISTENCE,
            retention=RETENTION_TTL,
            ttl_seconds=None,
        )
    with pytest.raises(InvalidEpsChannelSpecificationError):
        EpsChannelSpecV1(
            channel="test.vessel.invalid_ttl2",
            app="test_app",
            mode=MODE_PERSISTENCE,
            retention=RETENTION_TTL,
            ttl_seconds=0,
        )

    # 4. Valid: mode none + retention none
    spec3 = EpsChannelSpecV1(
        channel="test.vessel.none",
        app="test_app",
        mode=MODE_NONE,
        retention=RETENTION_NONE,
        visibility=VISIBILITY_ALL_NO_MODULATION,
    )
    assert spec3.mode == MODE_NONE
    assert spec3.retention == RETENTION_NONE

    # 5. Invalid: mode none + retention durable fails closed
    with pytest.raises(InvalidEpsChannelSpecificationError):
        EpsChannelSpecV1(
            channel="test.vessel.invalid_mode_retention",
            app="test_app",
            mode=MODE_NONE,
            retention=RETENTION_DURABLE,
        )

    # 6. Invalid mode string fails closed
    with pytest.raises(InvalidEpsChannelSpecificationError):
        EpsChannelSpecV1(
            channel="test.vessel.invalid_mode",
            app="test_app",
            mode="invalid_mode",
            retention=RETENTION_DURABLE,
        )

    # 7. Invalid retention string fails closed
    with pytest.raises(InvalidEpsChannelSpecificationError):
        EpsChannelSpecV1(
            channel="test.vessel.invalid_retention",
            app="test_app",
            mode=MODE_PERSISTENCE,
            retention="invalid_retention",
        )


def test_dynamic_channel_resolver_lifecycle_and_priority():
    from epsilinesTM_serveragnostic import (
        EpsChannelSpecV1,
        UnregisteredEpsChannelError,
        get_registered_eps_channel_v1,
        register_dynamic_channel_resolver_v1,
        register_eps_channel_v1,
    )

    # Register an exact channel
    exact_spec = EpsChannelSpecV1(
        channel="audit-fixed-probe",
        app="analytica",
        schema="fixed_probe_v1",
    )
    register_eps_channel_v1(exact_spec)

    # Verify exact match resolves directly
    resolved_exact = get_registered_eps_channel_v1("audit-fixed-probe")
    assert resolved_exact is not None
    assert resolved_exact.schema == "fixed_probe_v1"

    # Verify dynamic resolver resolves dynamic matching pattern
    resolved_dynamic = get_registered_eps_channel_v1("audit-custom.step99")
    assert resolved_dynamic is not None
    assert resolved_dynamic.channel == "audit-custom.step99"
    assert resolved_dynamic.app == "analytica"

    # Non-matching channel returns None from get_registered_eps_channel_v1
    assert get_registered_eps_channel_v1("unmatched.non_audit.channel") is None

    # Invalid resolver registration (non-callable) fails closed with TypeError
    with pytest.raises(TypeError):
        register_dynamic_channel_resolver_v1("bad_resolver", "not_a_callable")  # type: ignore


def test_declarative_app_spec_anomaly_aggregator_validation():
    from epsilinesTM_serveragnostic import EpsAppSpecV1

    # 1. Valid: callable aggregator
    def dummy_aggregator(envelopes, filters):
        return []

    app1 = EpsAppSpecV1(app="app_with_aggregator", anomaly_aggregator=dummy_aggregator)
    assert app1.anomaly_aggregator is dummy_aggregator

    # 2. Valid: None aggregator
    app2 = EpsAppSpecV1(app="app_without_aggregator", anomaly_aggregator=None)
    assert app2.anomaly_aggregator is None

    # 3. Invalid: non-callable aggregator fails closed with TypeError
    with pytest.raises(TypeError):
        EpsAppSpecV1(app="app_bad", anomaly_aggregator="not_callable")  # type: ignore


def test_visibility_tier_definitions():
    from epsilinesTM_serveragnostic import (
        ALLOWED_EPS_VISIBILITIES,
        VISIBILITY_OWNER_ONLY,
        VISIBILITY_ALL_WITH_MODULATION,
        VISIBILITY_ALL_NO_MODULATION,
        visibility_of_v1,
        AUDIT_INS_CHANNEL,
        FORMREACT_WIDGET_EXPLOSION_CHANNEL,
    )

    assert VISIBILITY_OWNER_ONLY in ALLOWED_EPS_VISIBILITIES
    assert VISIBILITY_ALL_WITH_MODULATION in ALLOWED_EPS_VISIBILITIES
    assert VISIBILITY_ALL_NO_MODULATION in ALLOWED_EPS_VISIBILITIES

    # Core channel visibilities
    assert visibility_of_v1(AUDIT_INS_CHANNEL) == VISIBILITY_OWNER_ONLY
    assert visibility_of_v1(FORMREACT_WIDGET_EXPLOSION_CHANNEL) == VISIBILITY_ALL_WITH_MODULATION


def test_eps_channel_sheet_invariants_complete():
    from epsilinesTM_serveragnostic import (
        EPS_APP_SHEET_V1,
        EPS_CHANNEL_SHEET_V1,
        assert_eps_channel_sheet_invariants_v1,
    )

    # Central verification function passes with zero errors
    assert_eps_channel_sheet_invariants_v1()

    # Invariant: Every channel references an app present in EPS_APP_SHEET_V1
    for app_spec in EPS_CHANNEL_SHEET_V1:
        assert app_spec.name in EPS_APP_SHEET_V1, f"App {app_spec.name} missing from EPS_APP_SHEET_V1"
        for spec in app_spec.channels:
            assert spec.app in EPS_APP_SHEET_V1, f"Channel {spec.channel} references unregistered app {spec.app}"
            assert spec.mode in ("persistence", "none"), f"Channel {spec.channel} has invalid mode {spec.mode}"
            assert spec.retention in ("durable", "ttl", "none"), f"Channel {spec.channel} has invalid retention {spec.retention}"
            assert callable(spec.validator), f"Channel {spec.channel} has non-callable validator"


