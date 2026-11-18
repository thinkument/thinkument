from __future__ import annotations

"""Immutable application-facing readers for event-trident streams.

The module is the single downstream interpretation surface shared by the
canonical E2E proof sheet, the UI E2E proof sheet, and real applications.
It depends only on public event/U/Di packet shapes.  It performs no session
writes and contains no pytest assertions.

Reader policy
-------------
* Required malformed shapes fail loudly.
* Semantically absent optional collections read as empty collections.
* Ownership and event order are preserved.
* Completed read-model snapshots are recursively immutable.
* Canonical and role-projected streams are never silently mixed.
* A bounded retained queue may contain residual packets rather than only
  complete tridents; those residuals are represented explicitly.
"""

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any, DefaultDict, Iterable, Mapping, Optional, TypeVar

from _thinksessions.run.runme_surfaces_out.helpers_event_read import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    SESSION_EVENT_KIND_V1,
    assert_canonical_event_v1,
)


JsonMapping = Mapping[str, Any]
_IndexKeyT = TypeVar("_IndexKeyT")


def _nonempty_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _required_mapping(value: Any, *, label: str) -> JsonMapping:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_sequence(value: Any, *, label: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a list/tuple")
    return tuple(value)


def freeze_json_v1(value: Any) -> Any:
    """Return a recursively immutable copy of one dead-JSON value."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json_v1(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_v1(item) for item in value)
    raise TypeError(f"value is not dead JSON: {type(value)!r}")


def thaw_json_v1(value: Any) -> Any:
    """Return an ordinary mutable dead-JSON copy of a frozen value."""
    if isinstance(value, Mapping):
        return {str(key): thaw_json_v1(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_v1(item) for item in value]
    return value


def controller_U_v1(event: JsonMapping) -> JsonMapping:
    """Read the complete source/destination U snapshot from a controller event."""
    payload = _required_mapping(event.get("payload"), label="event.payload")
    return _required_mapping(payload.get("U"), label="event.payload.U")


def controller_A_v1(event: JsonMapping) -> Optional[JsonMapping]:
    """Read normalized A, or ``None`` when a role projection hides all targets."""
    payload = _required_mapping(event.get("payload"), label="event.payload")
    action = payload.get("A")
    if action is None:
        return None
    return _required_mapping(action, label="event.payload.A")


def datum_states_by_id_v1(U: JsonMapping) -> Mapping[str, JsonMapping]:
    """Index the complete active-span Di vector without losing ownership order."""
    rows = U.get("datum_states_on_this_span")
    if rows is None:
        return MappingProxyType({})
    if not isinstance(rows, (list, tuple)):
        raise TypeError("U.datum_states_on_this_span must be a list/tuple")

    out: dict[str, JsonMapping] = {}
    for row in rows:
        row_m = _required_mapping(row, label="datum state row")
        datum_id = _nonempty_text(row_m.get("datum_id"))
        if datum_id is None:
            raise ValueError("datum state row has empty datum_id")
        if datum_id in out:
            raise ValueError(f"duplicate datum state id: {datum_id!r}")
        out[datum_id] = row_m
    return MappingProxyType(out)


@dataclass(frozen=True, slots=True)
class ScopeRefV1:
    """Normalized authored-scope reference for one U boundary."""

    kind: str
    form_id: Optional[str]
    frame_id: Optional[str]
    span_id: Optional[str]
    active: bool

    @property
    def index_key(self) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
        if not self.active:
            return (f"@{self.kind}", None, None, None)
        return ("scope", self.form_id, self.frame_id, self.span_id)


def scope_from_U_v1(U: JsonMapping) -> ScopeRefV1:
    kind = str(U.get("kind") or "<unknown>")
    form_id = _nonempty_text(U.get("form_id") or U.get("app_form_id"))
    frame_id = _nonempty_text(U.get("current_frame_id") or U.get("frame_id"))
    span_id = _nonempty_text(
        U.get("current_span") or U.get("current_span_id") or U.get("span_id")
    )
    active = span_id is not None and kind not in {"ATSTART", "ATCOMPLETION"}
    return ScopeRefV1(kind, form_id, frame_id, span_id, active)


def authored_span_rank_v1(U: JsonMapping) -> Optional[int]:
    """Return the current authored span's zero-based rank when recoverable."""
    scope = scope_from_U_v1(U)
    if not scope.active or scope.span_id is None:
        return None
    order = U.get("span_order")
    if not isinstance(order, (list, tuple)):
        return None
    try:
        return [str(item) for item in order].index(scope.span_id)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class TridentV1:
    """One complete admitted controller envelope: start, middle*, end."""

    local_id: str
    dispatch_id: Optional[str]
    action_name: str
    start: JsonMapping
    informative: tuple[JsonMapping, ...]
    end: JsonMapping
    source_scope: ScopeRefV1
    destination_scope: ScopeRefV1
    source_span_rank: Optional[int]
    destination_span_rank: Optional[int]
    outcome: str
    transition: str

    @property
    def start_seq(self) -> int:
        return int(self.start["event_seq"])

    @property
    def end_seq(self) -> int:
        return int(self.end["event_seq"])


@dataclass(frozen=True, slots=True)
class PartialEnvelopeV1:
    """A retained/live-stream envelope fragment that cannot be completed yet."""

    start: JsonMapping
    informative: tuple[JsonMapping, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class TridentLogV1:
    """Immutable one-pass aggregate plus bounded-window residuals."""

    ordered: tuple[TridentV1, ...]
    by_local_id: Mapping[str, TridentV1]
    by_dispatch_id: Mapping[str, TridentV1]
    by_action_name: Mapping[str, tuple[TridentV1, ...]]
    by_source_scope: Mapping[tuple[Any, ...], tuple[TridentV1, ...]]
    by_destination_scope: Mapping[tuple[Any, ...], tuple[TridentV1, ...]]
    by_source_span_id: Mapping[str, tuple[TridentV1, ...]]
    by_destination_span_id: Mapping[str, tuple[TridentV1, ...]]
    by_source_span_rank: Mapping[tuple[Optional[str], int], tuple[TridentV1, ...]]
    by_destination_span_rank: Mapping[
        tuple[Optional[str], int], tuple[TridentV1, ...]
    ]
    orphan_events: tuple[JsonMapping, ...]
    orphan_ends: tuple[JsonMapping, ...]
    interrupted_partials: tuple[PartialEnvelopeV1, ...]
    open_suffix: Optional[PartialEnvelopeV1]
    events_seen: int


def semantic_errors_v1(trident: TridentV1) -> JsonMapping:
    """Return datum/span semantic errors from the authoritative end U."""
    errors = controller_U_v1(trident.end).get("last_error")
    if not isinstance(errors, Mapping):
        return MappingProxyType({})
    return MappingProxyType(dict(errors))


def dispatch_context_v1(trident: TridentV1) -> Optional[JsonMapping]:
    """Return generated-dispatch context from the end boundary, losslessly."""
    payload = _required_mapping(trident.end.get("payload"), label="end.payload")
    value = payload.get("dispatch_context")
    if value is None:
        return None
    return _required_mapping(value, label="end.payload.dispatch_context")


def trident_outcome_v1(trident: TridentV1) -> str:
    """Classify success, semantic rejection, or caught systematic failure."""
    payload = _required_mapping(trident.end.get("payload"), label="end.payload")
    if payload.get("outcome") == "system_error":
        return "system_error"
    result = payload.get("result")
    if isinstance(result, Mapping) and isinstance(result.get("last_error"), Mapping):
        if result["last_error"]:
            return "semantic_rejected"
    return "success"


def trident_transition_v1(trident: TridentV1) -> str:
    """Classify the total N/S authored-scope relation across the envelope."""
    source = trident.source_scope
    destination = trident.destination_scope
    if not source.active and not destination.active:
        return "N->N"
    if not source.active and destination.active:
        return "N->S"
    if source.active and not destination.active:
        return "S->N"
    if source.index_key == destination.index_key:
        return "S->S"
    return "S1->S2"


def _freeze_index(
    raw: Mapping[_IndexKeyT, list[TridentV1]],
) -> Mapping[_IndexKeyT, tuple[TridentV1, ...]]:
    return MappingProxyType({key: tuple(value) for key, value in raw.items()})


def _assert_boundary_mirrors(event: JsonMapping, *, projected: bool) -> None:
    """Validate A/fill/signal mirrors without rejecting fully hidden projection."""
    payload = _required_mapping(event.get("payload"), label="controller.payload")
    action = payload.get("A")
    if action is None:
        if not projected:
            raise AssertionError("canonical controller boundary requires payload.A")
        if payload.get("fill") is not None or payload.get("signal") is not None:
            raise AssertionError("fully hidden projected A requires null mirrors")
        return
    action_m = _required_mapping(action, label="controller.payload.A")
    if payload.get("fill") != action_m.get("fill"):
        raise AssertionError("controller payload.fill does not mirror payload.A.fill")
    if payload.get("signal") != action_m.get("signal"):
        raise AssertionError("controller payload.signal does not mirror payload.A.signal")


class TridentStreamBuilderV1:
    """Incremental average-O(1)-per-event immutable read-model builder."""

    def __init__(self, *, projected: bool = False) -> None:
        self.projected = bool(projected)
        self.events_seen = 0
        self._last_seq = 0
        self._open_start: Optional[JsonMapping] = None
        self._open_middle: list[JsonMapping] = []
        self._ordered: list[TridentV1] = []
        self._by_local_id: dict[str, TridentV1] = {}
        self._by_dispatch_id: dict[str, TridentV1] = {}
        self._by_action_name: DefaultDict[str, list[TridentV1]] = defaultdict(list)
        self._by_source_scope: DefaultDict[tuple[Any, ...], list[TridentV1]] = (
            defaultdict(list)
        )
        self._by_destination_scope: DefaultDict[tuple[Any, ...], list[TridentV1]] = (
            defaultdict(list)
        )
        self._by_source_span_id: DefaultDict[str, list[TridentV1]] = defaultdict(list)
        self._by_destination_span_id: DefaultDict[str, list[TridentV1]] = (
            defaultdict(list)
        )
        self._by_source_span_rank: DefaultDict[
            tuple[Optional[str], int], list[TridentV1]
        ] = defaultdict(list)
        self._by_destination_span_rank: DefaultDict[
            tuple[Optional[str], int], list[TridentV1]
        ] = defaultdict(list)
        self._orphan_events: list[JsonMapping] = []
        self._orphan_ends: list[JsonMapping] = []
        self._interrupted: list[PartialEnvelopeV1] = []

    def feed(self, raw_event: JsonMapping) -> None:
        """Consume one strictly increasing canonical or one-role projected event."""
        assert_canonical_event_v1(raw_event)
        seq = int(raw_event["event_seq"])
        if seq <= self._last_seq:
            raise ValueError(
                "trident builder requires strictly increasing event_seq; "
                f"last={self._last_seq}, received={seq}"
            )
        self._last_seq = seq
        self.events_seen += 1
        event = freeze_json_v1(deepcopy(dict(raw_event)))

        if event.get("kind") != CONTROLLER_LOOP_EVENT_KIND_V1:
            if self._open_start is None:
                self._orphan_events.append(event)
            else:
                self._open_middle.append(event)
            return

        phase = event.get("phase")
        if phase == "start":
            if self._open_start is not None:
                self._interrupted.append(
                    PartialEnvelopeV1(
                        self._open_start,
                        tuple(self._open_middle),
                        "next_controller_start_arrived",
                    )
                )
            self._open_start = event
            self._open_middle = []
            return
        if phase != "end":
            raise AssertionError(f"unknown controller phase: {phase!r}")
        if self._open_start is None:
            self._orphan_ends.append(event)
            return

        start = self._open_start
        middle = tuple(self._open_middle)
        self._open_start = None
        self._open_middle = []
        self._complete(start, middle, event)

    def _complete(
        self,
        start: JsonMapping,
        middle: tuple[JsonMapping, ...],
        end: JsonMapping,
    ) -> None:
        start_dispatch_id = start.get("dispatch_id")
        if start_dispatch_id != end.get("dispatch_id"):
            raise AssertionError("controller start/end dispatch_id mismatch")
        for field in (
            "session_id",
            "action",
            "dispatcher_identity_id",
            "dispatcher_role",
        ):
            if start.get(field) != end.get(field):
                raise AssertionError(f"controller start/end {field} mismatch")
        if int(start["event_seq"]) >= int(end["event_seq"]):
            raise AssertionError("controller end must follow controller start")

        _assert_boundary_mirrors(start, projected=self.projected)
        _assert_boundary_mirrors(end, projected=self.projected)
        if controller_A_v1(start) != controller_A_v1(end):
            raise AssertionError("controller start/end normalized A mismatch")

        if not self.projected:
            if not isinstance(start_dispatch_id, str) or not start_dispatch_id:
                raise AssertionError("canonical trident requires dispatch_id")
            if not _nonempty_text(start.get("dispatcher_identity_id")):
                raise AssertionError("canonical trident requires dispatcher identity")
            seqs = [
                int(start["event_seq"]),
                *[int(item["event_seq"]) for item in middle],
                int(end["event_seq"]),
            ]
            expected = list(range(seqs[0], seqs[-1] + 1))
            if seqs != expected:
                raise AssertionError(
                    "canonical trident interval is not contiguous: "
                    f"actual={seqs!r}, expected={expected!r}"
                )

        start_U = controller_U_v1(start)
        end_U = controller_U_v1(end)
        dispatch_id = (
            start_dispatch_id
            if isinstance(start_dispatch_id, str) and start_dispatch_id
            else None
        )
        local_id = dispatch_id or f"projected:{start['event_id']}"
        source_scope = scope_from_U_v1(start_U)
        destination_scope = scope_from_U_v1(end_U)
        provisional = TridentV1(
            local_id=local_id,
            dispatch_id=dispatch_id,
            action_name=str(start["action"]),
            start=start,
            informative=middle,
            end=end,
            source_scope=source_scope,
            destination_scope=destination_scope,
            source_span_rank=authored_span_rank_v1(start_U),
            destination_span_rank=authored_span_rank_v1(end_U),
            outcome="",
            transition="",
        )
        trident = TridentV1(
            local_id=provisional.local_id,
            dispatch_id=provisional.dispatch_id,
            action_name=provisional.action_name,
            start=provisional.start,
            informative=provisional.informative,
            end=provisional.end,
            source_scope=provisional.source_scope,
            destination_scope=provisional.destination_scope,
            source_span_rank=provisional.source_span_rank,
            destination_span_rank=provisional.destination_span_rank,
            outcome=trident_outcome_v1(provisional),
            transition=trident_transition_v1(provisional),
        )
        self._append_trident(trident)

    def _append_trident(self, trident: TridentV1) -> None:
        if trident.local_id in self._by_local_id:
            raise AssertionError(f"duplicate local trident id: {trident.local_id}")
        self._ordered.append(trident)
        self._by_local_id[trident.local_id] = trident
        if trident.dispatch_id is not None:
            if trident.dispatch_id in self._by_dispatch_id:
                raise AssertionError(f"duplicate dispatch_id: {trident.dispatch_id}")
            self._by_dispatch_id[trident.dispatch_id] = trident
        self._by_action_name[trident.action_name].append(trident)
        self._by_source_scope[trident.source_scope.index_key].append(trident)
        self._by_destination_scope[trident.destination_scope.index_key].append(trident)
        if trident.source_scope.active and trident.source_scope.span_id:
            self._by_source_span_id[trident.source_scope.span_id].append(trident)
        if trident.destination_scope.active and trident.destination_scope.span_id:
            self._by_destination_span_id[trident.destination_scope.span_id].append(
                trident
            )
        if trident.source_span_rank is not None:
            self._by_source_span_rank[
                (trident.source_scope.form_id, trident.source_span_rank)
            ].append(trident)
        if trident.destination_span_rank is not None:
            self._by_destination_span_rank[
                (trident.destination_scope.form_id, trident.destination_span_rank)
            ].append(trident)

    def snapshot(self) -> TridentLogV1:
        """Freeze the current complete indexes and residual stream state."""
        open_suffix = None
        if self._open_start is not None:
            open_suffix = PartialEnvelopeV1(
                self._open_start,
                tuple(self._open_middle),
                "retained_window_or_live_stream_ends_before_controller_end",
            )
        return TridentLogV1(
            ordered=tuple(self._ordered),
            by_local_id=MappingProxyType(dict(self._by_local_id)),
            by_dispatch_id=MappingProxyType(dict(self._by_dispatch_id)),
            by_action_name=_freeze_index(self._by_action_name),
            by_source_scope=_freeze_index(self._by_source_scope),
            by_destination_scope=_freeze_index(self._by_destination_scope),
            by_source_span_id=_freeze_index(self._by_source_span_id),
            by_destination_span_id=_freeze_index(self._by_destination_span_id),
            by_source_span_rank=_freeze_index(self._by_source_span_rank),
            by_destination_span_rank=_freeze_index(
                self._by_destination_span_rank
            ),
            orphan_events=tuple(self._orphan_events),
            orphan_ends=tuple(self._orphan_ends),
            interrupted_partials=tuple(self._interrupted),
            open_suffix=open_suffix,
            events_seen=self.events_seen,
        )


def build_trident_log_v1(
    events: Iterable[JsonMapping], *, projected: bool = False
) -> TridentLogV1:
    """Build the immutable log in one pass over an ordered event iterable."""
    builder = TridentStreamBuilderV1(projected=projected)
    for event in events:
        builder.feed(event)
    return builder.snapshot()


# UI/application readers ----------------------------------------------------


def latest_complete_U_v1(log: TridentLogV1) -> JsonMapping:
    """Return the destination U of the latest complete trident."""
    if not log.ordered:
        raise ValueError("trident log has no complete trident")
    return controller_U_v1(log.ordered[-1].end)


def active_span_U_v1(log: TridentLogV1) -> JsonMapping:
    """Return latest destination U and require that it exposes an active span."""
    U = latest_complete_U_v1(log)
    if not scope_from_U_v1(U).active:
        raise ValueError("latest complete trident does not end on an active span")
    return U


def span_datum_vector_v1(U: JsonMapping) -> tuple[JsonMapping, ...]:
    """Return the complete static ownership-order Di vector, or empty if absent."""
    return tuple(
        _required_mapping(row, label="U.datum_states_on_this_span[]")
        for row in _optional_sequence(
            U.get("datum_states_on_this_span"),
            label="U.datum_states_on_this_span",
        )
    )


def pending_datum_ids_v1(U: JsonMapping) -> tuple[str, ...]:
    """Return the dynamic pending/editable datum-id subset."""
    return tuple(
        str(value)
        for value in _optional_sequence(
            U.get("datum_widgets_on_this_span"),
            label="U.datum_widgets_on_this_span",
        )
    )


def authoritative_datum_ids_v1(U: JsonMapping) -> tuple[str, ...]:
    """Return authoritative datum ids in static ownership order."""
    return tuple(
        str(row["datum_id"])
        for row in span_datum_vector_v1(U)
        if bool(row.get("is_authoritative"))
    )


def datum_micro_specs_v1(Di: JsonMapping) -> tuple[JsonMapping, ...]:
    """Return the current effective micro declarations for one Di."""
    micros = Di.get("micros")
    if micros is None:
        micros = _required_mapping(Di.get("shell"), label="Di.shell").get(
            "micros"
        )
    return tuple(
        _required_mapping(micro, label="Di.micros[]")
        for micro in _optional_sequence(micros, label="Di.micros")
    )


def datum_fill_v1(Di: JsonMapping) -> tuple[bool, Any]:
    """Return the presence bit and current merged datum-local macro fill."""
    return bool(Di.get("has_fill")), Di.get("fill")



def semantic_validator_specs_v1(Di: JsonMapping) -> JsonMapping:
    """Return the joined current validator summary, or an empty mapping."""
    value = Di.get("semantic_validation")
    if value is None:
        return MappingProxyType({})
    return _required_mapping(value, label="Di.semantic_validation")


def thinkwidget_messages_v1(trident: TridentV1) -> tuple[JsonMapping, ...]:
    """Select only ThinkWidget datum.message packets from the middle region."""
    return tuple(
        event
        for event in trident.informative
        if event.get("kind") == SESSION_EVENT_KIND_V1
        and event.get("source") in {"datum_widget", "datum_widget_result"}
        and event.get("name") == "datum.message"
    )


def frame_by_id_v1(U: JsonMapping, frame_id: str) -> JsonMapping:
    """Find one renderer-oriented U.frames record."""
    for frame in _optional_sequence(U.get("frames"), label="U.frames"):
        frame_m = _required_mapping(frame, label="U.frames[]")
        if str(frame_m.get("id") or frame_m.get("name") or "") == str(frame_id):
            return frame_m
    raise KeyError(frame_id)


def effective_datum_shell_by_id_v1(U: JsonMapping, datum_id: str) -> JsonMapping:
    """Return the exact effective shell, with a render-critical Di fallback.

    Full ``U.multiframespec`` inclusion is policy-controlled.  When present,
    its datum row is used.  Otherwise the current active-span Di shell is the
    stable rendering authority.
    """
    fs = U.get("multiframespec")
    if fs is not None:
        fs_m = _required_mapping(fs, label="U.multiframespec")
        for datum in _optional_sequence(
            fs_m.get("datums"), label="U.multiframespec.datums"
        ):
            datum_m = _required_mapping(datum, label="multiframespec.datums[]")
            if str(datum_m.get("id") or "") == str(datum_id):
                return datum_m
    row = datum_states_by_id_v1(U).get(str(datum_id))
    if row is not None:
        return _required_mapping(row.get("shell"), label="Di.shell")
    raise KeyError(datum_id)


def span_spec_v1(
    U: JsonMapping, *, frame_id: str, span_id: str
) -> JsonMapping:
    """Find a rich multiframespec span; fail clearly when that pocket is absent."""
    fs = U.get("multiframespec")
    if fs is None:
        raise KeyError(
            (frame_id, span_id, "U.multiframespec is not included by policy")
        )
    fs_m = _required_mapping(fs, label="U.multiframespec")
    for frame in _optional_sequence(
        fs_m.get("frames"), label="U.multiframespec.frames"
    ):
        frame_m = _required_mapping(frame, label="multiframespec.frames[]")
        if str(frame_m.get("id") or "") != str(frame_id):
            continue
        for span in _optional_sequence(
            frame_m.get("spans"), label="multiframespec.frames[].spans"
        ):
            span_m = _required_mapping(span, label="multiframespec span")
            if str(span_m.get("id") or "") == str(span_id):
                return span_m
    raise KeyError((frame_id, span_id))


def parse_versioned_json_error_v1(
    error_text: Any,
    *,
    expected_version: int = 1,
    micro_name: Optional[str] = None,
) -> Optional[JsonMapping]:
    """Parse one explicitly app-owned versioned JSON error component.

    The engine-level datum error remains opaque text.  Callers must name a
    micro component when a human-readable aggregate contains multiple errors.
    Trailing aggregate text is intentionally tolerated after the decoded JSON
    component; the JSON decoder returns only the first value.
    """
    if not isinstance(error_text, str):
        return None
    candidate = error_text.strip()
    if micro_name is not None:
        prefix = f"{micro_name}:"
        start: Optional[int] = None
        if candidate.startswith(prefix):
            start = len(prefix)
        else:
            marker = f"; {prefix}"
            marker_at = candidate.find(marker)
            if marker_at >= 0:
                start = marker_at + len(marker)
        if start is None:
            return None
        candidate = candidate[start:].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        version = int(value.get("v") or -1)
    except (TypeError, ValueError):
        return None
    if version != int(expected_version):
        return None
    return freeze_json_v1(value)


__all__ = [
    "JsonMapping",
    "ScopeRefV1",
    "TridentV1",
    "PartialEnvelopeV1",
    "TridentLogV1",
    "TridentStreamBuilderV1",
    "freeze_json_v1",
    "thaw_json_v1",
    "controller_U_v1",
    "controller_A_v1",
    "datum_states_by_id_v1",
    "scope_from_U_v1",
    "authored_span_rank_v1",
    "semantic_errors_v1",
    "dispatch_context_v1",
    "trident_outcome_v1",
    "trident_transition_v1",
    "build_trident_log_v1",
    "latest_complete_U_v1",
    "active_span_U_v1",
    "span_datum_vector_v1",
    "pending_datum_ids_v1",
    "authoritative_datum_ids_v1",
    "datum_micro_specs_v1",
    "datum_fill_v1",
    "semantic_validator_specs_v1",
    "thinkwidget_messages_v1",
    "frame_by_id_v1",
    "effective_datum_shell_by_id_v1",
    "span_spec_v1",
    "parse_versioned_json_error_v1",
]
