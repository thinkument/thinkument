from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

from .constants import (
    ADAPTER_RESERVED_STATE_KEY,
    CONFIG_KEY,
    MESSAGE_EVENT_AUDIENCE,
    MESSAGE_EVENT_CHANNEL,
    MESSAGE_EVENT_NAME,
)
from .runtime import _adapter_inputs_from_q, adapter_result_to_platform_result


class DatumLifecycleWidget:
    """
    Base class for the ergonomic datum lifecycle surface.
    """

    __slots__ = (
        "_q",
        "_state",
        "_messages",
        "_events",
        "_emit",
    )

    def __init__(
        self,
        *,
        q: Mapping[str, Any],
        emit: Callable[..., Mapping[str, Any]],
    ) -> None:
        object.__setattr__(self, "_q", q)
        object.__setattr__(self, "_state", dict(q.get("state") or {}))
        object.__setattr__(self, "_messages", [])
        object.__setattr__(self, "_events", [])
        object.__setattr__(self, "_emit", emit)

        reserved = dict(self._state.get(ADAPTER_RESERVED_STATE_KEY) or {})
        reserved.setdefault("last_precomputed_fills", {})
        self._state[ADAPTER_RESERVED_STATE_KEY] = reserved

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        state = object.__getattribute__(self, "_state")
        if name in state:
            return state[name]

        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        if hasattr(type(self), name):
            raise AttributeError(
                f"cannot overwrite class attribute/method {name!r} "
                "through lifecycle state"
            )

        self._state[name] = value

    @classmethod
    def get_class_static_decorated_config(cls) -> Dict[str, Any]:
        return dict(getattr(cls, CONFIG_KEY, {}) or {})

    def message(
        self,
        level: str,
        text: str,
        *,
        name: str = MESSAGE_EVENT_NAME,
    ) -> Mapping[str, Any]:
        level_norm = str(level or "info").strip().lower()

        msg = {
            "level": level_norm,
            "text": str(text or ""),
        }

        payload = {
            "message": msg,
        }

        emitted = self._emit(
            payload,
            name=name,
        )

        # q["emit"] is an event sink. Some sinks return the emitted packet,
        # while ordinary callback-style sinks may return None. The adapter
        # should not require a return value merely to author result messages.
        #
        # Normalize both styles into a stable local event packet.
        if isinstance(emitted, Mapping):
            ev = dict(emitted)
        else:
            ev = {
                "payload": payload,
                "name": name,
            }

        self._messages.append(msg)
        self._events.append(ev)
        return ev

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__} must override _on_mount(...) "
            "or disable lifecycle.mount_explode for this datum."
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__} must override _on_fill(...)."
        )

    def on_mount(self) -> Mapping[str, Any]:
        position, fill_data, limits, stats, _signal = _adapter_inputs_from_q(
            self._q,
            self._state,
        )

        if fill_data["changed_fills"]:
            raise ValueError(
                "mount handlers in the class adapter must see no changed_fills; "
                f"got {fill_data['changed_fills']!r}."
            )

        return adapter_result_to_platform_result(
            self,
            self._on_mount(position, fill_data, limits, stats),
        )

    def on_fill(self) -> Mapping[str, Any]:
        position, fill_data, limits, stats, signal = _adapter_inputs_from_q(
            self._q,
            self._state,
        )
        return adapter_result_to_platform_result(
            self,
            self._on_fill(signal, position, fill_data, limits, stats),
        )