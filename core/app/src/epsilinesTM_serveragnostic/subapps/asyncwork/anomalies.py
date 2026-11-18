from __future__ import annotations

"""Anomaly aggregator for the `asyncwork` subapp."""

from datetime import datetime, timezone
from typing import Any, Mapping

from .channels import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_PROGRESS_CHANNEL,
    OUTCOME_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
)


def aggregate_asyncwork_anomalies_v1(
    messages: list[Mapping[str, Any]],
    context: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Audit a stream of asyncwork epsilon messages for anomalies and execution health.

    Audits:
    1. Unclosed jobs: `asyncwork.announce` events with no matching `asyncwork.done`.
    2. Timeout breaches: unclosed announcements that have exceeded their `timeout_seconds`.
    3. Orphaned progress events: `asyncwork.progress` events referencing a non-existent parent.
    4. Post-terminal events: progress events emitted after an `asyncwork.done` was already recorded.
    """
    announcements: dict[str, dict[str, Any]] = {}
    done_events: dict[str, dict[str, Any]] = {}
    progress_by_parent: dict[str, list[dict[str, Any]]] = {}
    anomalies: list[dict[str, Any]] = []

    for msg in messages:
        ch = str(msg.get("type") or msg.get("channel") or "").strip()
        ref = str(msg.get("ref") or msg.get("event_id") or "").strip()
        parent_ref = str(msg.get("parent_ref") or msg.get("span_id") or "").strip()
        content = msg.get("content") or msg.get("payload") or {}

        if ch == ASYNCWORK_ANNOUNCE_CHANNEL:
            if ref:
                announcements[ref] = {
                    "ref": ref,
                    "target": content.get("target"),
                    "timeout_seconds": content.get("timeout_seconds"),
                    "emitted_at": msg.get("created_at") or msg.get("emitted_at"),
                }

        elif ch == ASYNCWORK_DONE_CHANNEL:
            target_parent = parent_ref or ref.removesuffix("/done")
            if target_parent:
                if target_parent in done_events:
                    anomalies.append({
                        "kind": "duplicate_done_sandwich",
                        "parent_ref": target_parent,
                        "details": "Multiple asyncwork.done events emitted for same announcement.",
                    })
                done_events[target_parent] = {
                    "outcome": content.get("outcome"),
                    "duration_sec": content.get("duration_sec"),
                    "error": content.get("error"),
                }

        elif ch == ASYNCWORK_PROGRESS_CHANNEL:
            if parent_ref:
                progress_by_parent.setdefault(parent_ref, []).append(dict(content))
                if parent_ref in done_events:
                    anomalies.append({
                        "kind": "post_terminal_progress",
                        "parent_ref": parent_ref,
                        "details": "Progress event emitted after job already marked done.",
                    })
            else:
                anomalies.append({
                    "kind": "missing_parent_ref_progress",
                    "details": "Progress event missing parent_ref.",
                })

    # Check for orphaned progress events
    for parent_ref in progress_by_parent:
        if parent_ref not in announcements:
            anomalies.append({
                "kind": "orphaned_progress",
                "parent_ref": parent_ref,
                "details": f"Progress events emitted for unknown announcement ref {parent_ref!r}.",
            })

    # Check for unclosed announcements
    now = datetime.now(timezone.utc)
    for ref, ann in announcements.items():
        if ref not in done_events:
            timeout = ann.get("timeout_seconds")
            is_timed_out = False
            emitted_at = ann.get("emitted_at")
            if timeout and emitted_at:
                try:
                    if isinstance(emitted_at, str):
                        dt = datetime.fromisoformat(emitted_at.replace("Z", "+00:00"))
                    elif isinstance(emitted_at, datetime):
                        dt = emitted_at
                    else:
                        dt = None
                    if dt and (now - dt).total_seconds() > timeout:
                        is_timed_out = True
                except Exception:
                    pass

            anomalies.append({
                "kind": "unclosed_async_job",
                "ref": ref,
                "target": ann.get("target"),
                "timeout_breached": is_timed_out,
                "details": f"Job {ref!r} announced but no terminal done event recorded.",
            })

    completed_count = sum(1 for d in done_events.values() if d.get("outcome") == OUTCOME_SUCCESS)
    failed_count = sum(1 for d in done_events.values() if d.get("outcome") == OUTCOME_ERROR)
    timed_out_count = sum(1 for d in done_events.values() if d.get("outcome") == OUTCOME_TIMEOUT)

    return {
        "app": "asyncwork",
        "total_announced_jobs": len(announcements),
        "completed_jobs": completed_count,
        "failed_jobs": failed_count,
        "timed_out_jobs": timed_out_count,
        "unclosed_jobs": len(announcements) - len(done_events),
        "total_anomalies": len(anomalies),
        "anomalies": anomalies,
    }


__all__ = ["aggregate_asyncwork_anomalies_v1"]
