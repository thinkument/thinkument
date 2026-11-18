from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from ._globals import (
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    DEFAULT_EXHAUSTED_MEANS_SATISFIED_V1,
    DEFAULT_MAX_BAGGAGE_V1,
    DEFAULT_MAX_MESSAGES_V1,
    DEFAULT_MAX_REEXPLOSIONS_V1,
    DEFAULT_MOUNT_EXPLODE_V1,
    KEY_DATUM_LIFECYCLE,
)

from ._registry import (
    _WIDGET_REGISTRY_V1,
    _default_one_shot_lifecycle_widget,
)

from ._surface_specs import (
    DatumWidgetFnV1,
)


DATUM_RUNTIME_STATE_SURFACE_KIND_V1 = (
    "universal_ui_datum_state_v1"
)


def read_datum_lifecycle_runtime_row_v1(
    state: Mapping[str, Any],
    *,
    form_id: str,
    datum_id: str,
) -> Dict[str, Any] | None:
    """
    Return one datum's latest committed lifecycle-memory row.

    This is a read-only dead-JSON projection over the canonical lifecycle
    store. It does not create a second lifecycle authority and does not mutate
    engine state.
    """
    if not isinstance(state, Mapping):
        return None

    store = state.get(KEY_DATUM_LIFECYCLE)
    if not isinstance(store, Mapping):
        return None

    forms = store.get("forms")
    if not isinstance(forms, Mapping):
        return None

    form_row = forms.get(str(form_id or ""))
    if not isinstance(form_row, Mapping):
        return None

    datums = form_row.get("datums")
    if not isinstance(datums, Mapping):
        return None

    row = datums.get(str(datum_id or ""))
    if not isinstance(row, Mapping):
        return None

    return deepcopy(dict(row))


def _semantic_validator_fields_v1(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Extract authored semantic-validation fields without interpreting them.

    Datum and micro shells are dead JSON. Validator implementations may evolve
    their exact authored key names, so this projection retains every field
    whose key explicitly identifies validation or lambda semantics.

    The complete source shell remains available alongside this extraction.
    """
    out: Dict[str, Any] = {}

    for raw_key, raw_value in dict(value or {}).items():
        key = str(raw_key)
        normalized = key.lower()

        if (
            "validat" not in normalized
            and "lambda" not in normalized
        ):
            continue

        out[key] = deepcopy(raw_value)

    return out


def build_universal_ui_datum_state_v1(
    *,
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    datum: Mapping[str, Any],
    fill: Any,
    has_fill: bool,
    is_authoritative: bool,
    is_pending: bool,
    originating_step: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Build the canonical renderer-agnostic current datum observation ``Di``.

    Source authority remains elsewhere:

      shell
          current effective hydrated multiframespec datum;

      fill
          current merged/manual render fill surface;

      lifecycle.runtime
          canonical datum lifecycle memory row;

      authority/pending
          current span vectors;

      originating_step
          current MANUAL step's source-step provenance.

    This function only joins those existing sources into one dead-JSON reader
    surface. It performs no lifecycle transition and no role projection.
    """
    did = str(datum_id or "").strip()
    shell = deepcopy(dict(datum or {}))

    args_raw = shell.get("args")
    args = (
        deepcopy(dict(args_raw))
        if isinstance(args_raw, Mapping)
        else {}
    )

    micros_raw = shell.get("micros")
    micros = (
        [
            deepcopy(dict(micro))
            for micro in micros_raw
            if isinstance(micro, Mapping)
        ]
        if isinstance(micros_raw, list)
        else []
    )

    semantic_micros = []
    for micro in micros:
        semantic_micros.append(
            {
                "name": str(micro.get("name") or ""),
                "spec": deepcopy(dict(micro)),
                "validator_fields": (
                    _semantic_validator_fields_v1(micro)
                ),
            }
        )

    lifecycle_runtime = read_datum_lifecycle_runtime_row_v1(
        state,
        form_id=str(form_id),
        datum_id=did,
    )

    policy = read_datum_system_flags_limits(shell)

    return {
        "kind": DATUM_RUNTIME_STATE_SURFACE_KIND_V1,
        "datum_id": did,
        "form_id": str(form_id),
        "frame_id": str(frame_id),
        "span_id": str(span_id),
        "is_authoritative": bool(is_authoritative),
        "is_pending": bool(is_pending),
        "shell": shell,
        "micros": micros,
        "micro_names": [
            str(micro.get("name") or "")
            for micro in micros
            if str(micro.get("name") or "").strip()
        ],
        "args": args,
        "fill": deepcopy(fill),
        "has_fill": bool(has_fill),
        "semantic_validation": {
            "datum_validator_fields": (
                _semantic_validator_fields_v1(shell)
            ),
            "micros": semantic_micros,
        },
        "lifecycle": {
            "enabled": this_datum_has_a_functional_lifecycle(shell),
            "policy": deepcopy(policy),
            "runtime": lifecycle_runtime,
        },
        "originating_step": {
            "public_step_name": str(
                originating_step.get("public_step_name")
                or ""
            ),
            "source_step_fn": str(
                originating_step.get("source_step_fn")
                or ""
            ),
            "source_fn_args": (
                deepcopy(
                    dict(
                        originating_step.get("source_fn_args")
                        or {}
                    )
                )
                if isinstance(
                    originating_step.get("source_fn_args"),
                    Mapping,
                )
                else {}
            ),
        },
    }


def read_datum_system_flags_limits(
    datum: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = datum.get("lifecycle") if isinstance(datum, Mapping) else None
    row = dict(raw or {}) if isinstance(raw, Mapping) else {}

    def _cap(
        key: str,
        default: int,
    ) -> int:
        value = row.get(key, default)
        if value is None:
            return 0
        try:
            return max(0, int(value))
        except Exception:
            return int(default)

    return {
        "widget": str(row.get("widget") or "default"),
        "initial_state": (
            dict(row.get("state") or {})
            if isinstance(row.get("state"), Mapping)
            else {}
        ),
        "mount_explode": bool(
            row.get("mount_explode", DEFAULT_MOUNT_EXPLODE_V1)
        ),
        "max_reexplosions": _cap(
            "max_reexplosions",
            DEFAULT_MAX_REEXPLOSIONS_V1,
        ),
        "exhausted_means_satisfied": bool(
            row.get(
                "exhausted_means_satisfied",
                DEFAULT_EXHAUSTED_MEANS_SATISFIED_V1,
            )
        ),
        "max_proc_notes": _cap(
            "max_proc_notes",
            DEFAULT_MAX_BAGGAGE_V1,
        ),
        "max_messages": _cap(
            "max_messages",
            DEFAULT_MAX_MESSAGES_V1,
        ),
    }


def resolve_datum_widget_v1(
    widget_ref: Any,
) -> DatumWidgetFnV1:
    ref = str(widget_ref or "default").strip() or "default"
    if ref == "default":
        return _default_one_shot_lifecycle_widget
    if ref in _WIDGET_REGISTRY_V1:
        return _WIDGET_REGISTRY_V1[ref]
    raise NotImplementedError


def is_this_datum_automaton_in_satisfied_sink_state(
    *,
    state: Mapping[str, Any],
    form_id: str,
    datum_id: str,
) -> bool:
    store = state.get(KEY_DATUM_LIFECYCLE)
    if not isinstance(store, Mapping):
        return False
    forms = store.get("forms")
    if not isinstance(forms, Mapping):
        return False
    form_row = forms.get(str(form_id or ""))
    if not isinstance(form_row, Mapping):
        return False
    datums = form_row.get("datums")
    if not isinstance(datums, Mapping):
        return False
    row = datums.get(str(datum_id))
    if not isinstance(row, Mapping):
        return False

    return str(row.get("status") or "") in {
        DATUM_LIFECYCLE_STATUS_DONE,
        DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    }


def this_datum_has_a_functional_lifecycle(
    datum: Mapping[str, Any],
) -> bool:
    return (
        isinstance(datum, Mapping)
        and isinstance(datum.get("lifecycle"), Mapping)
    )


__all__ = [
    "DATUM_RUNTIME_STATE_SURFACE_KIND_V1",
    "read_datum_lifecycle_runtime_row_v1",
    "build_universal_ui_datum_state_v1",
    "read_datum_system_flags_limits",
    "resolve_datum_widget_v1",
    "is_this_datum_automaton_in_satisfied_sink_state",
    "this_datum_has_a_functional_lifecycle",
]