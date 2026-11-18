from __future__ import annotations

from typing import Any

from __datomatonTM import register_datum_widget_v1

from .compiler import compile_datum_widget_class
from .constants import CONFIG_KEY


def thinkwidgetTM_config(
    name: str,
    *,
    overwrite: bool = False,
    **config: Any,
):
    """
    Configure, compile, and register a DatumLifecycleWidget class.

    This is the single class decorator for the thinkwidgetTM class adapter.

    Example:
        @thinkwidgetTM_config(
            "my.widget",
            overwrite=True,
            missing_signal_handler_outcome="fallback_to_fill_handler",
        )
        class MyWidget(DatumLifecycleWidget):
            ...
    """
    name_norm = str(name or "").strip()
    if not name_norm:
        raise ValueError("thinkwidgetTM_config requires a non-empty widget name")

    def _decorate(cls):
        static_config = dict(config or {})
        setattr(cls, CONFIG_KEY, static_config)

        fn = compile_datum_widget_class(cls)
        register_datum_widget_v1(name_norm, fn, overwrite=overwrite)

        setattr(cls, "__datum_widget_registered_name_v1__", name_norm)
        setattr(cls, "__datum_widget_compiled_fn_v1__", fn)
        return cls

    return _decorate


def signal_catcher(signal_name: str, **free_info: Any):
    signal_name_norm = str(signal_name or "").strip()
    if not signal_name_norm:
        raise ValueError("signal_catcher requires a non-empty signal_name")

    def _decorate(fn):
        setattr(
            fn,
            "__datum_widget_signal_catcher_v1__",
            {
                "signal_name": signal_name_norm,
                "free_info": dict(free_info or {}),
            },
        )
        return fn

    return _decorate