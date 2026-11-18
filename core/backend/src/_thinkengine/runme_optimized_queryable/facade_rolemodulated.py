# think-backend/src/thinkengine/optimized_facade/interactive_controled_rolemodulated.py

from __future__ import annotations

"""
Service-facing UI/session façade for dispatcher/render integrations.

Service code is here because it needs to create/delete core sessions or
dispatch/read live UI state without importing deep engine seams directly.

Use this module as the only service-layer bridge:

    from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
        create_core_session_from_program,
        delete_core_session,
        dispatch_live_session_action,
        get_live_session_events,
        get_live_session_latest_event_seq,
        get_live_session_context,
        render_current_session_state,
        render_launch_content,
    )

UI dispatch/current-state access is the only intentionally raw core seam here.
It stays sealed inside this module and must always return renderer-agnostic
state packets, not raw snapshots/program_map/history.

Endpoint map
------------

| Endpoint | Use it when | Raw core access? | Output |
| --- | --- | --- | --- |
| normalize_service_role | Normalize persisted/request role values. | No | Optional[str] |
| get_service_public_session_api | Build the service-owned bounded public session API. | No direct raw exposure | PublicSessionAPI |
| create_core_session_from_program | Create a core session from a source/app-table program. | Via bounded public façade | Public command receipt |
| delete_core_session | Delete a core session. | Via bounded public façade | Public command receipt |
| get_live_session_context | Read role-modulated current UI context for service-side projection only. | Yes, sealed UI read seam | Internal role-modulated ctx |
| get_live_session_events | Non-destructively inspect the bounded live event queue. | Yes, sealed event read seam | list[event] |
| get_live_session_latest_event_seq | Read the canonical event high-water mark without event payloads. | Yes, sealed scalar read seam | int |
| render_current_session_state | Read already-current durable UI state. | Yes, sealed UI state seam | Renderer-agnostic state dict |
| render_launch_content | Deprecated compatibility alias for initial state. | Yes, sealed UI state seam | JSON string of state dict |
| dispatch_live_session_action | Dispatch one live UI action. | Yes, sealed UI dispatch seam | Renderer-agnostic state dict |
| UserAction | Public action enum for service validation. | No | Enum |
| service_program_map_stub | Persist a tiny service access marker instead of raw program_map. | No | Small metadata dict |

Role law
--------

Roleless means Python/JSON null:

    role is None

It must never become:

    "None"
    "null"
    ""

A role-enabled run passes a real role name string. A roleless run passes None
through to core dispatch.

Dispatch law
------------

The raw UI dispatch seam must stay sealed:

    render=True
    include_ctx=False

Every dispatch requires a non-empty higher-application ``identity_id``. The
identity is passed unchanged to the role-aware controller façade, where it is
recorded as ``dispatcher_identity_id`` on controller start/end events.

Callers receive renderer-agnostic transition packets. They must not receive raw
snapshot, program_map, multiframespec, state, globals, history, nested ctx, or
unbounded private string payloads from this module unless explicitly opting into
the internal ctx seam for immediate service-side public projection.
"""

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence

from _thinkengine._engine_interactive_flow_controller import (
    UserAction,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    dispatch_ui_action,
    get_concrete_session_api,
    get_latest_session_event_seq as _core_get_latest_session_event_seq,
    get_current_ui_events as _core_get_current_ui_events,
    get_current_ui_state as _core_get_current_ui_state,
    render_current_ui_state as _core_render_current_ui_state,
)
from _thinkengine.runme_optimized_queryable._core import (
    get_public_session_api,
)


SERVICE_SESSION_FACADE_KIND = "web_RESTful_session_facade_v1"
SERVICE_RENDER_PACKET_STRING_LIMIT = 512


def _profile_enabled() -> bool:
    return str(
        os.environ.get("web_RESTful_PROFILE", "")
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _profile_emit(
    label: str,
    elapsed: float,
    **fields: Any,
) -> None:
    if not _profile_enabled():
        return

    rendered_fields = " ".join(
        f"{key}={value!r}"
        for key, value in sorted(fields.items())
    )
    print(
        (
            f"[service-profile] {label} "
            f"elapsed_s={elapsed:.6f} {rendered_fields}"
        ),
        file=sys.stderr,
        flush=True,
    )


@contextmanager
def _timed(
    label: str,
    **fields: Any,
) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _profile_emit(
            label,
            time.perf_counter() - t0,
            **fields,
        )


def normalize_service_role(value: Any) -> Optional[str]:
    """
    Normalize an optional service role.

    Roleless access is represented by real None. String sentinels commonly
    produced by accidental formatting are treated as roleless for compatibility
    with older persisted rows and intermediate patches.
    """
    if value is None:
        return None

    if value == "":
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.lower() in {"none", "null"}:
        return None

    return text


def _coerce_user_action(
    action: str | UserAction,
) -> UserAction:
    """
    Normalize service/Celery action inputs into the core UI action enum.

    Accepts:
      - UserAction.STEP
      - "STEP"
      - enum value strings, if values ever differ from names.
    """
    if isinstance(action, UserAction):
        return action

    action_str = str(action)

    try:
        return UserAction[action_str]
    except KeyError:
        return UserAction(action_str)


def get_service_public_session_api():
    """
    Service-owned public core API.

    Service code should use this instead of raw concrete session APIs except for
    the narrow server-side UI rendering/dispatch seams in this module.
    """
    return get_public_session_api(
        raw_api=get_concrete_session_api()
    )


def create_core_session_from_program(
    *,
    program: Any,
    program_language: str,
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None,
    session_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bounded service launch seam.

    Returns a public command receipt. Does not request raw ctx/program_map.
    """
    api = get_service_public_session_api()

    with _timed(
        "core_public_create_session_from_program",
        program_language=program_language,
        manifest_len=(
            len(program)
            if hasattr(program, "__len__")
            else None
        ),
    ):
        created = api.create_session_from_program(
            program=program,
            program_language=program_language,
            initial_parameter_overrides=dict(
                initial_parameter_overrides or {}
            ),
            session_metadata=dict(session_metadata or {}),
        )

    return dict(created or {})


def delete_core_session(
    session_id: str,
) -> Dict[str, Any]:
    """
    Delete a core session through the bounded public façade.
    """
    api = get_service_public_session_api()

    with _timed(
        "core_public_delete_session",
        session_id=str(session_id),
    ):
        deleted = api.delete_session(str(session_id))

    return dict(deleted or {})


def _ctx_report_from_ctx(
    ctx: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Small service-safe context report for render snapshots.

    This is intentionally not a public HTTP projection. Public Run views still
    apply their own stricter slug/role/redaction projection before responding.
    """
    raw_cursor = ctx.get("cursor")
    cursor = (
        raw_cursor
        if isinstance(raw_cursor, Mapping)
        else {}
    )

    raw_state = ctx.get("state")
    state = (
        raw_state
        if isinstance(raw_state, Mapping)
        else {}
    )

    return {
        "kind": "ui_ctx_report_v1",
        "event_kind": ctx.get("kind"),
        "cursor": {
            "index": cursor.get("index"),
            "total": cursor.get("total"),
        },
        "form_id": ctx.get("form_id") or ctx.get("app_form_id"),
        "frame_id": ctx.get("current_frame_id"),
        "span_id": (
            ctx.get("current_span")
            or ctx.get("current_span_id")
        ),
        "datum_widgets_on_this_span_count": len(
            ctx.get("datum_widgets_on_this_span") or []
        ),
        "counts": {
            "form_prefills": state.get("form_prefills_count"),
            "form_fills": state.get("form_fills_count"),
            "forms_emitted": state.get("forms_emitted_count"),
            "datum_widget_fills": state.get(
                "datum_widget_fills_count"
            ),
        },
        "last_error": ctx.get("last_error"),
    }


def _strip_nested_ctx_from_renderer_packet(
    value: Any,
) -> Any:
    """
    Remove raw ctx and bound accidental large private payloads wherever a
    renderer packet accidentally nested them.

    The service facade's dispatch/render law is stronger than the lower
    renderer seam:

      - include_ctx=False means no raw ctx at top level;
      - renderer packets must not retain content.ctx/raw_ctx/context;
      - unbounded private strings must not cross this facade.
    """
    if isinstance(value, str):
        if len(value) <= SERVICE_RENDER_PACKET_STRING_LIMIT:
            return value

        return {
            "kind": "service_string_redacted_v1",
            "length": len(value),
            "truncated": True,
        }

    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}

        for key, child in value.items():
            key_s = str(key)

            if key_s in {"ctx", "raw_ctx", "context"}:
                if isinstance(child, Mapping):
                    out["ctx_report"] = _ctx_report_from_ctx(child)
                continue

            out[key_s] = _strip_nested_ctx_from_renderer_packet(
                child
            )

        return out

    if isinstance(value, list):
        return [
            _strip_nested_ctx_from_renderer_packet(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _strip_nested_ctx_from_renderer_packet(item)
            for item in value
        ]

    return value


def get_live_session_context(
    *,
    session_id: str,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Service-side current UI context seam.

    This exists so Django Run views do not import lower renderer/controller
    modules directly. It may return role-modulated ctx for immediate
    service-side projection, but callers must not expose it directly over HTTP.
    """
    normalized_role = normalize_service_role(role)

    with _timed(
        "core_raw_get_live_session_context",
        session_id=str(session_id),
        role=normalized_role,
    ):
        ctx = _core_get_current_ui_state(
            str(session_id),
            role=normalized_role,
        )

    return dict(ctx or {})


def get_live_session_events(
    *,
    session_id: str,
    role: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    """
    Service-side live event queue read seam.

    This is non-destructive:
      - limit=None returns the whole bounded queue;
      - limit=k returns the latest k events;
      - role=None returns the unmodulated queue view;
      - role=<name> role-modulates controller-loop payload.U for that viewer.

    The queue itself remains transient and bounded by the engine event queue
    cap. This endpoint exists so tests and higher apps do not reach down into
    engine internals to inspect live events.
    """
    normalized_role = normalize_service_role(role)

    with _timed(
        "core_raw_get_live_session_events",
        session_id=str(session_id),
        role=normalized_role,
        limit=limit,
    ):
        events = _core_get_current_ui_events(
            str(session_id),
            role=normalized_role,
            limit=limit,
        )

    return [dict(event or {}) for event in events]


def get_live_session_latest_event_seq(
    *,
    session_id: str,
) -> int:
    """
    Return the canonical session event high-water mark.

    The result is one integer and does not inspect, copy, role-project, or
    serialize event packets. It is intentionally role-independent: sequence
    movement may reveal that activity occurred, but never event content.
    """
    with _timed(
        "core_get_live_session_latest_event_seq",
        session_id=str(session_id),
    ):
        value = _core_get_latest_session_event_seq(str(session_id))

    return max(0, int(value))


def render_current_session_state(
    *,
    session_id: str,
    role: Optional[str] = None,
    include_ctx: bool = False,
) -> Dict[str, Any]:
    """
    Service-side render-current seam.

    By default this strips raw ctx and leaves only ctx_report plus rendered
    content. Service callers needing full ctx must opt in explicitly and still
    project/redact before any public response.
    """
    normalized_role = normalize_service_role(role)

    with _timed(
        "core_raw_render_current_session_state",
        session_id=str(session_id),
        role=normalized_role,
        include_ctx=bool(include_ctx),
    ):
        snapshot = _core_render_current_ui_state(
            str(session_id),
            role=normalized_role,
        )

    out = (
        dict(snapshot or {})
        if isinstance(snapshot, Mapping)
        else {}
    )

    if not include_ctx:
        raw_ctx = out.get("ctx")
        if isinstance(raw_ctx, Mapping):
            out["ctx_report"] = _ctx_report_from_ctx(raw_ctx)

        out.pop("ctx", None)
        out = _strip_nested_ctx_from_renderer_packet(out)

    return out


def render_launch_content(
    *,
    session_id: str,
    role: Optional[str],
    identity_id: str,
) -> str:
    """
    Deprecated compatibility alias for server-side initial state.

    Returns a JSON string of the renderer-agnostic launch state so older call
    sites that expected a string do not receive HTML. New code should call
    render_current_session_state(...).

    ``identity_id`` must be the higher application's already-owned dispatcher
    identity. This layer does not synthesize an identity.
    """
    normalized_role = normalize_service_role(role)

    with _timed(
        "core_raw_render_launch_state",
        session_id=str(session_id),
        role=normalized_role,
        identity_id=str(identity_id),
    ):
        snapshot = dispatch_ui_action(
            str(session_id),
            role=normalized_role,
            identity_id=str(identity_id),
            render=True,
            include_ctx=False,
        )

    if not isinstance(snapshot, Mapping):
        return ""

    sanitized = _strip_nested_ctx_from_renderer_packet(
        dict(snapshot)
    )
    return json.dumps(
        sanitized,
        separators=(",", ":"),
        default=str,
    )


def dispatch_live_session_action(
    *,
    session_id: str,
    action: str | UserAction,
    user_fill: Optional[Mapping[str, Any]] = None,
    user_signal: Optional[Mapping[str, Any]] = None,
    role: Optional[str] = None,
    identity_id: str = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Service/Celery live UI action seam.

    This is the action-time sibling of render_launch_content(...).

    The raw UI dispatch remains sealed here:

      - role is normalized here;
      - identity_id is validated here;
      - action is coerced here;
      - dotted fill keys such as {"NAME.first": "Ada"} pass through unchanged;
      - core/controller dispatch owns UI fill normalization;
      - render=True, where content is a renderer-agnostic packet;
      - include_ctx=False.

    Ordinary systematic controller failures that occur after controller start
    acquisition are returned as bounded transition packets containing a
    top-level ``system_error`` mapping. They do not expose or re-raise raw
    engine exceptions through this service seam.

    The returned mapping is the service transition snapshot. It must not include
    raw ctx/snapshot/program_map/state/globals/history, nested renderer ctx, or
    unbounded private string payloads.
    """
    normalized_role = normalize_service_role(role)
    normalized_identity_id = str(identity_id or "").strip()
    if not normalized_identity_id:
        normalized_identity_id = ""

    with _timed(
        "core_raw_dispatch_live_session_action",
        session_id=str(session_id),
        action=str(action),
        role=normalized_role,
        identity_id=normalized_identity_id,
        has_user_fill=bool(user_fill),
    ):
        snapshot = dispatch_ui_action(
            str(session_id),
            action=_coerce_user_action(action),
            user_fill=dict(user_fill or {}),
            user_signal=(
                dict(user_signal)
                if isinstance(user_signal, Mapping)
                else None
            ),
            role=normalized_role,
            identity_id=normalized_identity_id,
            render=True,
            include_ctx=False,
            threaded_callbacks=threaded_callbacks,
            dispatch_context=(
                dict(dispatch_context)
                if isinstance(dispatch_context, Mapping)
                else None
            ),
        )

    if not isinstance(snapshot, Mapping):
        return {}

    return _strip_nested_ctx_from_renderer_packet(
        dict(snapshot)
    )


def service_program_map_stub(
    *,
    role: Optional[str],
) -> Dict[str, Any]:
    """
    Tiny persisted access-handle marker.

    This deliberately replaces historical raw program_map persistence.

    Roleless must persist as JSON null, not the string "None".
    """
    normalized_role = normalize_service_role(role)

    return {
        "_server_access": {
            "kind": "session_access_handle",
            "role": normalized_role,
        },
        "_service_facade": {
            "kind": SERVICE_SESSION_FACADE_KIND,
            "raw_program_map_persisted": False,
        },
    }


__all__ = [
    "SERVICE_SESSION_FACADE_KIND",
    "UserAction",
    "create_core_session_from_program",
    "delete_core_session",
    "dispatch_live_session_action",
    "get_live_session_events",
    "get_live_session_latest_event_seq",
    "get_live_session_context",
    "get_service_public_session_api",
    "normalize_service_role",
    "render_current_session_state",
    "render_launch_content",
    "service_program_map_stub",
]