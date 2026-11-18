from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Mapping

from .base import DatumLifecycleWidget
from .constants import (
    CONFIG_KEY,
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    MISSING_SIGNAL_RAISE,
    SIGNAL_CATCHERS_KEY,
)
from .runtime import _adapter_inputs_from_q, adapter_result_to_platform_result


def _unwrap_static_descriptor(value: Any) -> Any:
    """
    Return the function object behind ordinary static/classmethod descriptors.

    signal_catcher is intended for normal instance methods, but this helper
    keeps metadata discovery deterministic if a descriptor appears.
    """
    if isinstance(value, (staticmethod, classmethod)):
        return value.__func__
    return value


def _collect_signal_catchers(cls) -> Dict[str, str]:
    """
    Collect @signal_catcher methods using Python MRO semantics.

    Law:
        - base catchers are inherited;
        - subclass catchers are added;
        - subclass catchers for the same signal name override base catchers;
        - collection does not depend on dir() alphabetical order;
        - collection does not invoke descriptors/properties.
    """
    out: Dict[str, str] = {}

    for klass in reversed(cls.__mro__):
        if not issubclass(klass, DatumLifecycleWidget):
            continue

        for method_name, raw_value in vars(klass).items():
            value = _unwrap_static_descriptor(raw_value)
            meta = getattr(value, "__datum_widget_signal_catcher_v1__", None)
            if not isinstance(meta, Mapping):
                continue

            signal_name = str(meta.get("signal_name") or "").strip()
            if not signal_name:
                continue

            out[signal_name] = str(method_name)

    return out


def _class_resolves_base_handler(cls, name: str) -> bool:
    """
    True iff cls resolves the handler to DatumLifecycleWidget's abstract base
    implementation rather than to an inherited/concrete override.
    """
    resolved = inspect.getattr_static(cls, name, None)
    base = inspect.getattr_static(DatumLifecycleWidget, name, None)
    return resolved is base


def compile_datum_widget_class(
    cls,
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    if not issubclass(cls, DatumLifecycleWidget):
        raise TypeError("datum widget class must inherit DatumLifecycleWidget")

    if _class_resolves_base_handler(cls, "_on_mount"):
        raise TypeError(
            f"{cls.__name__} must implement _on_mount(...) directly or inherit "
            "a concrete _on_mount(...) implementation from a DatumLifecycleWidget "
            "subclass."
        )

    if _class_resolves_base_handler(cls, "_on_fill"):
        raise TypeError(
            f"{cls.__name__} must implement _on_fill(...) directly or inherit "
            "a concrete _on_fill(...) implementation from a DatumLifecycleWidget "
            "subclass."
        )

    signal_catchers = _collect_signal_catchers(cls)
    config = cls.get_class_static_decorated_config()
    missing_signal = str(
        config.get("missing_signal_handler_outcome", MISSING_SIGNAL_RAISE)
    )

    if missing_signal not in {
        MISSING_SIGNAL_RAISE,
        MISSING_SIGNAL_FALLBACK_TO_FILL,
    }:
        raise ValueError(
            "missing_signal_handler_outcome must be "
            f"{MISSING_SIGNAL_RAISE!r} or {MISSING_SIGNAL_FALLBACK_TO_FILL!r}"
        )

    def _lifecycle_fn(q: Mapping[str, Any]) -> Mapping[str, Any]:
        emit = q.get("emit")
        if not callable(emit):
            raise TypeError("adapter requires q['emit'] to be callable")

        instance = cls(q=q, emit=emit)
        signal_kind = str(
            q.get("signal_kind")
            or dict(q.get("signal") or {}).get("kind")
            or "fill"
        )

        if signal_kind == "mount":
            return instance.on_mount()

        if signal_kind == "fill":
            return instance.on_fill()

        if signal_kind in signal_catchers:
            position, fill_data, limits, stats, signal = _adapter_inputs_from_q(
                q,
                instance._state,
            )
            method = getattr(instance, signal_catchers[signal_kind])
            return adapter_result_to_platform_result(
                instance,
                method(signal, position, fill_data, limits, stats),
            )

        if missing_signal == MISSING_SIGNAL_FALLBACK_TO_FILL:
            return instance.on_fill()

        raise NotImplementedError(
            f"{cls.__name__} has no @signal_catcher for signal {signal_kind!r}; "
            "set @thinkwidgetTM_config(missing_signal_handler_outcome="
            "'fallback_to_fill_handler') to delegate custom signals to _on_fill."
        )

    setattr(_lifecycle_fn, "__datum_widget_class_v1__", cls)
    setattr(_lifecycle_fn, SIGNAL_CATCHERS_KEY, signal_catchers)
    setattr(_lifecycle_fn, CONFIG_KEY, config)
    return _lifecycle_fn