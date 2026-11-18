from __future__ import annotations

"""
thinksession.__persistence.models
=================================

Implementation-independent session persistence records.

``pickled_stepper`` remains opaque bytes. ``additional_json`` is a generic,
engine-independent extension pocket for compact hosting-owned state. It must
contain dead JSON and is not interpreted as part of the engine snapshot.
"""

from dataclasses import dataclass, field
from typing import Any, Dict
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionState:
    """Durable session record with one generic JSON extension pocket."""

    session_id: UUID
    pickled_stepper: bytes
    session_metadata: Dict[str, Any] = field(default_factory=dict)
    additional_json: Dict[str, Any] = field(default_factory=dict)
    latest_event_seq: int = 0