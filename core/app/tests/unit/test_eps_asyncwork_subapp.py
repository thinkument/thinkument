from __future__ import annotations

"""Unit tests for epsilinesTM_serveragnostic asyncwork subapp specifications, validation, and anomalies."""

import pytest

from epsilinesTM_serveragnostic import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_PROGRESS_CHANNEL,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_APP_SPEC_V1,
    RETENTION_DURABLE,
    RETENTION_TTL,
    VISIBILITY_OWNER_ONLY,
    bind_eps_reader_v1,
    bind_eps_sink_v1,
    emit_eps_v1,
    read_eps_v1,
    require_registered_eps_channel_v1,
)
from epsilinesTM_serveragnostic.subapps.asyncwork.channels import (
    ASYNCWORK_ANNOUNCE_EVENT,
    ASYNCWORK_PROGRESS_EVENT,
    ASYNCWORK_DONE_EVENT,
    ASYNCWORK_OUTCOMES,
    ASYNCWORK_PROGRESS_STATUSES,
)
from epsilinesTM_serveragnostic.subapps.asyncwork.specs import (
    validate_asyncwork_announce_payload,
    validate_asyncwork_progress_payload,
    validate_asyncwork_done_payload,
)
from epsilinesTM_serveragnostic.subapps.asyncwork.anomalies import (
    aggregate_asyncwork_anomalies_v1,
)
from live_vial._json_shell.eps_log import InMemoryEpsLog


@pytest.fixture
def memory_log():
    return InMemoryEpsLog()


@pytest.fixture
def bound_asyncwork_eps(memory_log):
    def sink(channel, payload, **kwargs):
        run_id = kwargs.pop("run_id", "test_run_async_001")
        owner_id = kwargs.pop("owner_id", "test_owner_async")
        ref = kwargs.pop("ref", None)
        parent_ref = kwargs.pop("parent_ref", None)
        meta = kwargs.pop("meta", None)
        vis = kwargs.pop("visibility", VISIBILITY_OWNER_ONLY)
        kwargs.pop("event_id", None)
        kwargs.pop("span_id", None)
        kwargs.pop("record_in_session_queue", None)
        row = memory_log.append(
            run_id=run_id,
            channel=channel,
            payload=payload,
            event_id=ref or "",
            span_id=parent_ref or "",
            owner_id=owner_id,
            meta=meta,
            visibility=vis,
            **kwargs,
        )
        return row.get("event_id") or ""

    def reader(channel, **kwargs):
        return memory_log.query(channel=channel, **kwargs)

    with bind_eps_sink_v1(sink):
        with bind_eps_reader_v1(reader):
            yield memory_log


# =====================================================================
# 1. Registration & App Spec Tests
# =====================================================================

def test_asyncwork_channels_are_registered():
    """Verify all 3 channels are registered and conform to architectural specs."""
    assert ASYNCWORK_APP_SPEC_V1.app == "asyncwork"
    assert len(ASYNCWORK_APP_SPEC_V1.channels) == 3

    ann_spec = require_registered_eps_channel_v1(ASYNCWORK_ANNOUNCE_CHANNEL)
    assert ann_spec.channel == ASYNCWORK_ANNOUNCE_CHANNEL
    assert ann_spec.app == "asyncwork"
    assert ann_spec.event == ASYNCWORK_ANNOUNCE_EVENT
    assert ann_spec.visibility == VISIBILITY_OWNER_ONLY
    assert ann_spec.retention == RETENTION_DURABLE
    assert ann_spec.terminal is False

    prog_spec = require_registered_eps_channel_v1(ASYNCWORK_PROGRESS_CHANNEL)
    assert prog_spec.channel == ASYNCWORK_PROGRESS_CHANNEL
    assert prog_spec.app == "asyncwork"
    assert prog_spec.event == ASYNCWORK_PROGRESS_EVENT
    assert prog_spec.visibility == VISIBILITY_OWNER_ONLY
    assert prog_spec.retention == RETENTION_TTL
    assert prog_spec.terminal is False

    done_spec = require_registered_eps_channel_v1(ASYNCWORK_DONE_CHANNEL)
    assert done_spec.channel == ASYNCWORK_DONE_CHANNEL
    assert done_spec.app == "asyncwork"
    assert done_spec.event == ASYNCWORK_DONE_EVENT
    assert done_spec.visibility == VISIBILITY_OWNER_ONLY
    assert done_spec.retention == RETENTION_DURABLE
    assert done_spec.terminal is True


# =====================================================================
# 2. Payload Validation Tests
# =====================================================================

def test_announce_payload_validation():
    # Valid payload with all fields
    valid = {
        "target": "external_api_fetcher",
        "kwargs": {"document_id": "doc_999", "tier": "gold"},
        "timeout_seconds": 120,
        "max_retries": 3,
        "priority": 1,
        "deduplication_key": "fetch_doc_999",
        "initiator_widget": "DocumentSubmissionWidget",
    }
    validated = validate_asyncwork_announce_payload(valid)
    assert validated["target"] == "external_api_fetcher"
    assert validated["kwargs"]["document_id"] == "doc_999"
    assert validated["timeout_seconds"] == 120
    assert validated["max_retries"] == 3
    assert validated["priority"] == 1

    # Minimal payload
    minimal = {"target": "quick_task"}
    validated_min = validate_asyncwork_announce_payload(minimal)
    assert validated_min["target"] == "quick_task"
    assert validated_min["kwargs"] == {}
    assert validated_min["timeout_seconds"] is None

    # Invalid: non-dict
    with pytest.raises(ValueError, match="must be a dict"):
        validate_asyncwork_announce_payload("not a dict")

    # Invalid: missing target
    with pytest.raises(ValueError, match="target.*required"):
        validate_asyncwork_announce_payload({})

    # Invalid: kwargs not json-serializable
    with pytest.raises(Exception):
        validate_asyncwork_announce_payload({"target": "bad", "kwargs": {"func": lambda x: x}})

    # Invalid: timeout negative
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        validate_asyncwork_announce_payload({"target": "bad", "timeout_seconds": -5})


def test_progress_payload_validation():
    # Valid payload
    valid = {
        "target": "doc_indexer",
        "step_name": "vectorizing",
        "step_index": 2,
        "total_steps": 5,
        "percent": 40.0,
        "status": "running",
        "details": {"chunks_processed": 200},
    }
    validated = validate_asyncwork_progress_payload(valid)
    assert validated["percent"] == 40.0
    assert validated["status"] == "running"
    assert validated["step_index"] == 2

    # Minimal payload
    minimal = {"target": "doc_indexer"}
    validated_min = validate_asyncwork_progress_payload(minimal)
    assert validated_min["status"] == "in_progress"
    assert validated_min["percent"] is None

    # Invalid: percent out of bounds
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        validate_asyncwork_progress_payload({"target": "t", "percent": 150.0})

    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        validate_asyncwork_progress_payload({"target": "t", "percent": -1.0})

    # Invalid: unknown status
    with pytest.raises(ValueError, match="status.*must be one of"):
        validate_asyncwork_progress_payload({"target": "t", "status": "exploding"})


def test_done_payload_validation():
    # Valid success
    valid_success = {
        "target": "doc_indexer",
        "outcome": "success",
        "result": {"vectors_count": 500, "url": "https://s3.example.com/idx.bin"},
        "duration_ms": 3412.5,
    }
    validated = validate_asyncwork_done_payload(valid_success)
    assert validated["outcome"] == "success"
    assert validated["result"]["vectors_count"] == 500
    assert validated["duration_ms"] == 3412.5

    # Valid timeout
    valid_timeout = {
        "target": "doc_indexer",
        "outcome": "timeout",
        "error_message": "External API call exceeded 120s deadline",
        "duration_ms": 120005.0,
    }
    validated_t = validate_asyncwork_done_payload(valid_timeout)
    assert validated_t["outcome"] == "timeout"
    assert "exceeded 120s" in validated_t["error_message"]

    # Invalid: unknown outcome
    with pytest.raises(ValueError, match="outcome.*must be one of"):
        validate_asyncwork_done_payload({"target": "t", "outcome": "maybe_finished"})

    # Invalid: result not JSON serializable
    with pytest.raises(Exception):
        validate_asyncwork_done_payload({"target": "t", "outcome": "success", "result": set([1, 2])})


# =====================================================================
# 3. Emission, References, Hierarchies & Point/Batch Reads
# =====================================================================

def test_asyncwork_lifecycle_emission_and_reads(bound_asyncwork_eps):
    """Test full announcement -> progress stream -> done sandwich emission and targeted reads."""
    # 1. Announce async job
    ann_ref = emit_eps_v1(
        channel=ASYNCWORK_ANNOUNCE_CHANNEL,
        payload={
            "target": "generate_report_v1",
            "kwargs": {"report_type": "quarterly", "year": 2026},
            "timeout_seconds": 60,
        },
        ref="async/report_q4_2026",
        meta={"initiator": "AnalyticsDashboardWidget"},
    )
    assert ann_ref == "async/report_q4_2026"

    # 2. Emit progress updates (children of ann_ref)
    p1_ref = emit_eps_v1(
        channel=ASYNCWORK_PROGRESS_CHANNEL,
        payload={
            "target": "generate_report_v1",
            "step_name": "aggregating_metrics",
            "step_index": 1,
            "total_steps": 3,
            "percent": 33.3,
            "status": "running",
            "details": {"tables_queried": 4},
        },
        parent_ref=ann_ref,
    )
    assert p1_ref is not None

    p2_ref = emit_eps_v1(
        channel=ASYNCWORK_PROGRESS_CHANNEL,
        payload={
            "target": "generate_report_v1",
            "step_name": "rendering_pdf",
            "step_index": 2,
            "total_steps": 3,
            "percent": 66.6,
            "status": "in_progress",
            "details": {"pages_rendered": 12},
        },
        parent_ref=ann_ref,
    )
    assert p2_ref is not None

    # 3. Emit done sandwich (terminal child of ann_ref)
    done_ref = emit_eps_v1(
        channel=ASYNCWORK_DONE_CHANNEL,
        payload={
            "target": "generate_report_v1",
            "outcome": "success",
            "result": {"s3_url": "https://storage.thinkument.com/reports/q4_2026.pdf"},
            "duration_ms": 1420.0,
        },
        ref=f"{ann_ref}/done",
        parent_ref=ann_ref,
    )
    assert done_ref == f"{ann_ref}/done"

    # 4. Verify Point Reads (seeking specific job announcement)
    ann_record = read_eps_v1(ASYNCWORK_ANNOUNCE_CHANNEL, ref=ann_ref, for_owner=True)
    assert ann_record is not None
    assert ann_record["payload"]["target"] == "generate_report_v1"

    # 5. Verify Point Reads (seeking done sandwich)
    done_record = read_eps_v1(ASYNCWORK_DONE_CHANNEL, ref=f"{ann_ref}/done", for_owner=True)
    assert done_record is not None
    assert done_record["payload"]["outcome"] == "success"
    assert done_record["payload"]["result"]["s3_url"] == "https://storage.thinkument.com/reports/q4_2026.pdf"

    # 6. Verify Batch Reads (seeking all children progress ticks by parent_ref)
    progress_records = read_eps_v1(ASYNCWORK_PROGRESS_CHANNEL, parent_ref=ann_ref, for_owner=True)
    assert len(progress_records) == 2
    assert progress_records[0]["payload"]["step_name"] == "aggregating_metrics"
    assert progress_records[1]["payload"]["step_name"] == "rendering_pdf"


# =====================================================================
# 4. Anomaly Aggregation Tests
# =====================================================================

def test_anomaly_aggregation_clean_and_dirty(bound_asyncwork_eps, memory_log):
    # Case A: Clean run
    emit_eps_v1(
        ASYNCWORK_ANNOUNCE_CHANNEL,
        {"target": "clean_job"},
        ref="async/clean_job_1",
    )
    emit_eps_v1(
        ASYNCWORK_PROGRESS_CHANNEL,
        {"target": "clean_job", "percent": 50.0},
        parent_ref="async/clean_job_1",
    )
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {"target": "clean_job", "outcome": "success", "duration_ms": 500.0},
        ref="async/clean_job_1/done",
        parent_ref="async/clean_job_1",
    )

    clean_messages = memory_log.query(allow_all=True)
    clean_anomalies = aggregate_asyncwork_anomalies_v1(clean_messages)
    assert clean_anomalies["total_announced_jobs"] == 1
    assert clean_anomalies["completed_jobs"] == 1
    assert clean_anomalies["failed_jobs"] == 0
    assert clean_anomalies["timed_out_jobs"] == 0
    assert clean_anomalies["unclosed_jobs"] == 0
    assert clean_anomalies["total_anomalies"] == 0

    # Case B: Unclosed job
    emit_eps_v1(
        ASYNCWORK_ANNOUNCE_CHANNEL,
        {"target": "stuck_job"},
        ref="async/stuck_job_2",
    )

    # Case C: Orphaned progress event (no announcement)
    emit_eps_v1(
        ASYNCWORK_PROGRESS_CHANNEL,
        {"target": "ghost_job", "percent": 10.0},
        parent_ref="async/ghost_job_999",
    )

    # Case D: Timed out job
    emit_eps_v1(
        ASYNCWORK_ANNOUNCE_CHANNEL,
        {"target": "timed_out_job"},
        ref="async/timed_out_3",
    )
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {"target": "timed_out_job", "outcome": "timeout", "duration_ms": 65000.0},
        ref="async/timed_out_3/done",
        parent_ref="async/timed_out_3",
    )

    # Case E: Failed job
    emit_eps_v1(
        ASYNCWORK_ANNOUNCE_CHANNEL,
        {"target": "error_job"},
        ref="async/error_4",
    )
    emit_eps_v1(
        ASYNCWORK_DONE_CHANNEL,
        {"target": "error_job", "outcome": "error", "error_message": "Network 500", "duration_ms": 12000.0},
        ref="async/error_4/done",
        parent_ref="async/error_4",
    )

    dirty_messages = memory_log.query(allow_all=True)
    dirty_anomalies = aggregate_asyncwork_anomalies_v1(dirty_messages)

    assert dirty_anomalies["total_announced_jobs"] == 4
    assert dirty_anomalies["completed_jobs"] == 1
    assert dirty_anomalies["timed_out_jobs"] == 1
    assert dirty_anomalies["failed_jobs"] == 1
    assert dirty_anomalies["unclosed_jobs"] == 1  # stuck_job_2
    assert dirty_anomalies["total_anomalies"] >= 2  # orphaned progress + unclosed job
