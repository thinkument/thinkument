from __future__ import annotations

"""Default in-memory session repository plus optional generic auxiliary JSON."""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional
from uuid import UUID

from _thinkprogram._iomicrosTM.tiny_helpers import DeadJSONError, assert_dead_json
from _thinkengine.__persistence.models import SessionState


class SessionRepo:
    _states: Dict[UUID, SessionState] = {}
    _steppers: Dict[UUID, Any] = {}

    @classmethod
    def create(cls, state: SessionState, stepper: Any) -> None:
        cls.save_state(state)
        cls.save_stepper(state.session_id, stepper)

    @classmethod
    def get(cls, session_id: UUID) -> SessionState:
        try:
            return cls._states[session_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown session_id: {session_id}"
            ) from exc

    @classmethod
    def get_stepper(cls, session_id: UUID) -> Optional[Any]:
        return cls._steppers.get(session_id)

    @classmethod
    def save_stepper(cls, session_id: UUID, stepper: Any) -> None:
        cls._steppers[session_id] = stepper

    @classmethod
    def save_state(cls, state: SessionState) -> None:
        cls._states[state.session_id] = state

    @classmethod
    def delete(cls, session_id: UUID) -> None:
        cls._states.pop(session_id, None)
        cls._steppers.pop(session_id, None)

    @classmethod
    def get_latest_event_seq(
        cls,
        session_id: str | UUID,
    ) -> int:
        sid = (
            session_id
            if isinstance(session_id, UUID)
            else UUID(str(session_id))
        )
        return max(0, int(cls.get(sid).latest_event_seq))

    @classmethod
    def save_latest_event_seq(
        cls,
        session_id: str | UUID,
        latest_event_seq: int,
    ) -> None:
        sid = (
            session_id
            if isinstance(session_id, UUID)
            else UUID(str(session_id))
        )
        seq = int(latest_event_seq)
        if seq < 0:
            raise ValueError("latest_event_seq must be >= 0")

        state = cls.get(sid)
        cls.save_state(
            SessionState(
                session_id=state.session_id,
                pickled_stepper=state.pickled_stepper,
                session_metadata=deepcopy(state.session_metadata),
                additional_json=deepcopy(state.additional_json),
                latest_event_seq=max(int(state.latest_event_seq), seq),
            )
        )

    @classmethod
    def save_aux_json(
        cls,
        session_id: str | UUID,
        *,
        namespace: str,
        value: Mapping[str, Any],
    ) -> None:
        ns = str(namespace or "").strip()
        if not ns:
            raise ValueError("namespace must be non-empty")

        payload = dict(value)
        try:
            assert_dead_json(
                payload,
                path=f"session_aux_json[{ns!r}]",
            )
        except DeadJSONError as exc:
            raise TypeError(str(exc)) from exc

        sid = (
            session_id
            if isinstance(session_id, UUID)
            else UUID(str(session_id))
        )
        state = cls.get(sid)
        additional = deepcopy(
            dict(state.additional_json or {})
        )
        additional[ns] = deepcopy(payload)
        cls.save_state(
            SessionState(
                session_id=state.session_id,
                pickled_stepper=state.pickled_stepper,
                session_metadata=deepcopy(
                    state.session_metadata
                ),
                additional_json=additional,
                latest_event_seq=int(state.latest_event_seq),
            )
        )

    @classmethod
    def get_aux_json(
        cls,
        session_id: str | UUID,
        *,
        namespace: str,
    ) -> Optional[Dict[str, Any]]:
        sid = (
            session_id
            if isinstance(session_id, UUID)
            else UUID(str(session_id))
        )
        try:
            state = cls.get(sid)
        except KeyError:
            # Auxiliary JSON is optional hosting state. Absence of the owning
            # session in this repository means that this repository has no
            # auxiliary value for it.
            return None

        row = dict(state.additional_json or {}).get(
            str(namespace)
        )
        return deepcopy(row) if row is not None else None