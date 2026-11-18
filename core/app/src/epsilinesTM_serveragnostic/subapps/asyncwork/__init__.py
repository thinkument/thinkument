from __future__ import annotations

"""`asyncwork` subapp within the Epsilines framework."""

from ...core.registry import EpsAppSpecV1, register_eps_app_v1
from .anomalies import aggregate_asyncwork_anomalies_v1
from .channels import (
    ALLOWED_OUTCOMES,
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_ANNOUNCE_SCHEMA_V1,
    ASYNCWORK_APP,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_DONE_SCHEMA_V1,
    ASYNCWORK_PROGRESS_CHANNEL,
    ASYNCWORK_PROGRESS_SCHEMA_V1,
    OUTCOME_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    STATUS_CHECKPOINT,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_RUNNING,
    STATUS_WAITING,
    STATUS_WARNING,
)
from .specs import (
    ASYNCWORK_ANNOUNCE_SPEC_V1,
    ASYNCWORK_CHANNELS_V1,
    ASYNCWORK_DONE_SPEC_V1,
    ASYNCWORK_PROGRESS_SPEC_V1,
    validate_asyncwork_announce_payload_v1,
    validate_asyncwork_done_payload_v1,
    validate_asyncwork_progress_payload_v1,
)

ASYNCWORK_APP_SPEC_V1 = EpsAppSpecV1(
    name=ASYNCWORK_APP,
    channels=ASYNCWORK_CHANNELS_V1,
    anomaly_aggregator=aggregate_asyncwork_anomalies_v1,
)

# Register the subapp into the central registry at import time
register_eps_app_v1(ASYNCWORK_APP_SPEC_V1, replace=True)

__all__ = [
    "ALLOWED_OUTCOMES",
    "ASYNCWORK_ANNOUNCE_CHANNEL",
    "ASYNCWORK_ANNOUNCE_SCHEMA_V1",
    "ASYNCWORK_ANNOUNCE_SPEC_V1",
    "ASYNCWORK_APP",
    "ASYNCWORK_APP_SPEC_V1",
    "ASYNCWORK_CHANNELS_V1",
    "ASYNCWORK_DONE_CHANNEL",
    "ASYNCWORK_DONE_SCHEMA_V1",
    "ASYNCWORK_DONE_SPEC_V1",
    "ASYNCWORK_PROGRESS_CHANNEL",
    "ASYNCWORK_PROGRESS_SCHEMA_V1",
    "ASYNCWORK_PROGRESS_SPEC_V1",
    "OUTCOME_ERROR",
    "OUTCOME_SUCCESS",
    "OUTCOME_TIMEOUT",
    "STATUS_CHECKPOINT",
    "STATUS_DONE",
    "STATUS_IN_PROGRESS",
    "STATUS_RUNNING",
    "STATUS_WAITING",
    "STATUS_WARNING",
    "aggregate_asyncwork_anomalies_v1",
    "validate_asyncwork_announce_payload_v1",
    "validate_asyncwork_done_payload_v1",
    "validate_asyncwork_progress_payload_v1",
]
