from __future__ import annotations

"""Dry-run-owned public event protocol vocabulary.

These are standard lingo facts, not adapter facts.  Concrete strategies may
obtain them from callbacks, HTTP responses, DOM-visible state, or another
transport, but the dry-run E grammar reasons over the same canonical packet
vocabulary.
"""

from typing import Any, Mapping


CONTROLLER_LOOP_EVENT_KIND_V1 = "controller_loop_event_v1"
SESSION_EVENT_KIND_V1 = "datum_lifecycle_event_v1"


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AssertionError(f"{label} must be a mapping; actual={value!r}")
    return value


def assert_standard_event_v1(
    event: Mapping[str, Any],
    *,
    canonical: bool,
) -> None:
    if not isinstance(event, Mapping):
        raise AssertionError(f"event must be a mapping; actual={event!r}")

    kind = event.get("kind")
    if kind not in {CONTROLLER_LOOP_EVENT_KIND_V1, SESSION_EVENT_KIND_V1}:
        raise AssertionError(f"unknown standard event kind: {kind!r}")

    for key in ("event_id", "emitted_at", "kind"):
        if key not in event:
            raise AssertionError(f"event missing required key {key!r}: {event!r}")

    if canonical:
        seq = event.get("event_seq")
        if type(seq) is not int or seq < 1:
            raise AssertionError(
                f"canonical event_seq must be positive int; actual={seq!r}"
            )
    elif "event_seq" in event:
        raise AssertionError(
            f"live/provisional event must not contain event_seq: {event!r}"
        )

    payload = _require_mapping(event.get("payload"), label="event.payload")

    if kind == CONTROLLER_LOOP_EVENT_KIND_V1:
        if event.get("phase") not in {"start", "end"}:
            raise AssertionError(
                f"controller phase must be start/end: {event!r}"
            )
        for key in ("name", "action", "phase"):
            if key not in event:
                raise AssertionError(
                    f"controller event missing {key!r}: {event!r}"
                )
        _require_mapping(payload.get("U"), label="controller payload.U")
        if payload.get("timestamp") != event.get("emitted_at"):
            raise AssertionError(
                "controller payload.timestamp must equal emitted_at"
            )
        return

    for key in ("name", "datum_id", "span_id", "frame_id", "form_id"):
        if key not in event:
            raise AssertionError(f"datum event missing {key!r}: {event!r}")


def assert_strict_canonical_event_order_v1(
    events: list[Mapping[str, Any]],
    *,
    contiguous: bool,
) -> None:
    for event in events:
        assert_standard_event_v1(event, canonical=True)
    seqs = [int(event["event_seq"]) for event in events]
    if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
        raise AssertionError(f"canonical event order is not strict: {seqs!r}")
    if contiguous and seqs:
        if seqs != list(range(seqs[0], seqs[-1] + 1)):
            raise AssertionError(
                f"canonical interval is not contiguous: {seqs!r}"
            )


__all__ = [
    "CONTROLLER_LOOP_EVENT_KIND_V1",
    "SESSION_EVENT_KIND_V1",
    "assert_standard_event_v1",
    "assert_strict_canonical_event_order_v1",
]
