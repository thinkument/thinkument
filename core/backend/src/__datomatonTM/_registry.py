from __future__ import annotations

from typing import Any, Dict, Mapping

from ._globals import (
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
)

from ._surface_specs import (
    DatumWidgetFnV1,
)


_WIDGET_REGISTRY_V1: Dict[str, DatumWidgetFnV1] = {}


def register_datum_widget_v1(
    name: str,
    fn: DatumWidgetFnV1,
    *,
    overwrite: bool = False,
) -> None:
    nm = str(name or "").strip()
    if not nm:
        raise ValueError(
            "datum widget name must be non-empty"
        )
    if not callable(fn):
        raise TypeError(
            "datum widget fn must be callable"
        )
    if nm in _WIDGET_REGISTRY_V1 and not overwrite:
        raise ValueError(
            f"datum widget already registered: {nm}"
        )
    _WIDGET_REGISTRY_V1[nm] = fn


def _default_one_shot_lifecycle_widget(
    q: Mapping[str, Any],
) -> Dict[str, Any]:
    if not bool(q.get("structurally_satisfied")):
        return {
            "status": Q_STATUS_BLOCKED,
            "message": {
                "level": "error",
                "text": "required fields missing",
            },
            "state": dict(q.get("state") or {}),
        }

    return {
        "status": Q_STATUS_DONE,
        "message": {
            "level": "success",
            "text": "",
        },
        "state": dict(q.get("state") or {}),
    }


__all__ = [
    "_WIDGET_REGISTRY_V1",
    "register_datum_widget_v1",
    "_default_one_shot_lifecycle_widget",
]