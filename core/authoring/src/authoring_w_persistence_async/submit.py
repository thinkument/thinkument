from __future__ import annotations

"""Standalone asynchronous work submission and handle resolution."""

import time
import uuid
from typing import Any, Callable, Dict, Mapping, Optional, Union

from epsilinesTM_serveragnostic import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    emit_eps_v1,
)
from .handle import AsyncWorkHandle


def submit_async_work_v1(
    target: Union[str, Callable[..., Any]],
    kwargs: Optional[Mapping[str, Any]] = None,
    *,
    timeout_seconds: Optional[float] = None,
    ref: Optional[str] = None,
    max_retries: Optional[int] = None,
    priority: Optional[int] = None,
    meta: Optional[Mapping[str, Any]] = None,
    deduplication_key: Optional[str] = None,
    run_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    initiator_widget: Optional[str] = None,
) -> AsyncWorkHandle:
    """Submit a task for asynchronous execution on the dedicated worker pool.
    
    Adheres strictly to Philosophy 2:
    - Widget runs this submission in $<5ms$.
    - Emission of `asyncwork.announce` triggers post-commit Celery dispatch automatically.
    - Returns an `AsyncWorkHandle` whose `.ref` can be written to widget state.
    """
    if isinstance(target, str):
        target_name = target.strip()
    elif callable(target):
        target_name = getattr(target, "__name__", str(target)).strip()
    else:
        raise ValueError(f"target must be a string name or callable, got {type(target)!r}")

    if not target_name:
        raise ValueError("target name cannot be empty")

    payload: Dict[str, Any] = {
        "target": target_name,
        "kwargs": dict(kwargs or {}),
    }
    if timeout_seconds is not None:
        payload["timeout_seconds"] = float(timeout_seconds)
    if max_retries is not None:
        payload["max_retries"] = int(max_retries)
    if priority is not None:
        payload["priority"] = int(priority)
    if deduplication_key is not None:
        payload["deduplication_key"] = str(deduplication_key)
    if initiator_widget is not None:
        payload["initiator_widget"] = str(initiator_widget)

    # Auto-allocate structured ref if not explicitly provided
    assigned_ref = ref
    if not assigned_ref:
        assigned_ref = f"async/{target_name}/{uuid.uuid4().hex[:12]}"

    emit_kwargs: Dict[str, Any] = {
        "channel": ASYNCWORK_ANNOUNCE_CHANNEL,
        "payload": payload,
        "ref": assigned_ref,
    }
    if meta:
        emit_kwargs["meta"] = dict(meta)
    if run_id:
        emit_kwargs["run_id"] = str(run_id)
    if owner_id:
        emit_kwargs["owner_id"] = str(owner_id)

    confirmed_ref = emit_eps_v1(**emit_kwargs)

    return AsyncWorkHandle(
        announcement_ref=confirmed_ref or assigned_ref,
        run_id=run_id,
        owner_id=owner_id,
    )


def get_async_work_handle_v1(
    ref: str,
    *,
    run_id: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> AsyncWorkHandle:
    """Resolve an AsyncWorkHandle from a stored task reference string."""
    return AsyncWorkHandle(announcement_ref=ref, run_id=run_id, owner_id=owner_id)
