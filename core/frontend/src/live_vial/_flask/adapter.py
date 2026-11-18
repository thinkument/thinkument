from __future__ import annotations

import json
import secrets
import threading
import warnings
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    url_for,
)
from werkzeug.exceptions import HTTPException

from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    delete_live_session,
    dispatch_live_session_action,
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_context,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
)
from live_vial._json_shell.html_shell_rendering import (
    build_thinkument_client_config,
    render_shell_html,
)

from live_vial._json_shell.eps_log import (
    InMemoryEpsLog,
    eps_callbacks_v1,
    extract_datum_read_map_v1,
)
from __staticfiles_mgmt.globals import (
    BLUEPRINT_NAME,
    LOCAL_FLASK_RUNTIME_PROFILE,
    LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY,
    STATIC_PACKAGE,
    STATIC_SUBDIR,
    STATIC_URL_PATH,
    WEB_SHIM_FILENAME,
    select_opinionation_module_filename,
)
from live_vial._flask.static_blueprint import (
    AggregatedStaticBlueprint,
)


TYPED_EXCEPTION_KIND_V1 = "thinkument_local_flask_typed_exception_v1"


def formreacttm_client_extra_v1(
    *,
    overrides: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "formreactTM": {
            "archiveCap": 512,
            "seenEventCap": 2048,
            "pageMessageCap": 128,
            "datumMessageCap": 64,
            **dict(overrides or {}),
        }
    }


__all__ = [
    "formreacttm_client_extra_v1",
]


class HTTPError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
    ):
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)


LOCAL_FLASK_CREATE_PAYLOAD_KEYS = frozenset(
    {
        "start_on_create",
    }
)

LOCAL_FLASK_DISPATCH_PAYLOAD_KEYS = frozenset(
    {
        "action",
        "chainreactionTM_config",
        "identity_id",
        "my_current_event_seq_number",
        "request_id",
        "role",
        "user_fill",
        "user_signal",
    }
)


def _parse_payload() -> Dict[str, Any]:
    try:
        data = json.loads(
            request.get_data().decode() or "{}"
        )
    except Exception as exc:
        raise HTTPError(
            400,
            f"invalid JSON: {exc}",
        ) from exc

    if not isinstance(data, Mapping):
        raise HTTPError(
            400,
            "request body must be an object",
        )

    return dict(data)


def _mapping(
    value: Any,
    *,
    field: str,
) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise HTTPError(
            400,
            f"{field} must be an object",
        )
    return dict(value)


def _optional_mapping(
    value: Any,
    *,
    field: str,
) -> Optional[Dict[str, Any]]:
    if value in (None, ""):
        return None
    return _mapping(
        value,
        field=field,
    )


def _parse_int(
    value: Any,
    *,
    field: str,
    default: int,
    minimum: int = 0,
    maximum: int = 1000,
) -> int:
    if value in (None, ""):
        return int(default)

    if isinstance(value, bool):
        raise HTTPError(
            400,
            f"{field} must be an integer, not boolean",
        )

    if type(value) is not int:
        raise HTTPError(
            400,
            f"{field} must be an exact integer",
        )

    if value < minimum:
        raise HTTPError(
            400,
            f"{field} must be >= {minimum}",
        )
    if value > maximum:
        raise HTTPError(
            400,
            f"{field} must be <= {maximum}",
        )

    return value


def _parse_query_int(
    value: Any,
    *,
    field: str,
    default: int,
    minimum: int = 0,
    maximum: int = 1000,
) -> int:
    if value in (None, ""):
        return default

    text = str(value)
    if not text.isascii() or not text.isdecimal():
        raise HTTPError(
            400,
            f"{field} must be a canonical base-10 "
            "non-negative integer",
        )

    if len(text) > 1 and text.startswith("0"):
        raise HTTPError(
            400,
            f"{field} must be a canonical base-10 "
            "non-negative integer",
        )

    parsed = int(text)
    if parsed < minimum or parsed > maximum:
        raise HTTPError(
            400,
            f"{field} must be between {minimum} and {maximum}",
        )
    return parsed


def _normalize_role(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip() or None


@dataclass(frozen=True)
class _AccessHandle:
    access_id: str
    session_id: str
    role: Optional[str]


_ACCESS_HANDLES: Dict[str, _AccessHandle] = {}
_ACCESS_LOCK = threading.RLock()
_EPS_LOG = InMemoryEpsLog()
_SESSION_EPS_HOOKS: Dict[str, Dict[str, Any]] = {}


def reset_access_handles() -> None:
    with _ACCESS_LOCK:
        _ACCESS_HANDLES.clear()
        _SESSION_EPS_HOOKS.clear()
    _EPS_LOG.clear()


def _new_token(prefix: str) -> str:
    return (
        f"{prefix}-"
        f"{secrets.token_urlsafe(18).replace('-', '_')}"
    )


def _register_access_handle(
    *,
    session_id: str,
    role: Optional[str],
) -> _AccessHandle:
    handle = _AccessHandle(
        access_id=_new_token("run"),
        session_id=str(session_id),
        role=_normalize_role(role),
    )
    with _ACCESS_LOCK:
        _ACCESS_HANDLES[handle.access_id] = handle
    return handle


def _get_access_handle(
    access_id: str,
) -> _AccessHandle:
    with _ACCESS_LOCK:
        try:
            return _ACCESS_HANDLES[str(access_id)]
        except KeyError as exc:
            raise HTTPError(
                404,
                f"unknown access handle {access_id!r}",
            ) from exc


def release_local_session(
    *,
    session_id: str,
) -> Dict[str, Any]:
    """Delete one local session and every process-local facade handle."""
    sid = str(session_id)
    with _ACCESS_LOCK:
        removed_handles = [
            access_id
            for access_id, handle in _ACCESS_HANDLES.items()
            if handle.session_id == sid
        ]
        for access_id in removed_handles:
            _ACCESS_HANDLES.pop(access_id, None)
        _SESSION_EPS_HOOKS.pop(sid, None)
    _EPS_LOG.clear(run_id=sid)

    delete_report = delete_live_session(session_id=sid)
    return {
        "kind": "thinkument_local_flask_session_release_v1",
        "session_id": sid,
        "removed_access_handles": len(removed_handles),
        "delete_report": dict(delete_report or {}),
    }


def _assert_payload_role(
    payload_role: Any,
    handle_role: Optional[str],
) -> None:
    if payload_role is None:
        return

    if (
        _normalize_role(payload_role)
        != _normalize_role(handle_role)
    ):
        raise HTTPError(
            400,
            "payload role does not match the sealed "
            "access-handle role",
        )


def _selected_role(
    roles: Mapping[str, Any],
    public_view_role: Any,
) -> Optional[str]:
    names = sorted(str(name) for name in roles)
    selected = _normalize_role(public_view_role)

    if not names:
        if selected is not None:
            raise HTTPError(
                400,
                "public_view_role requires declared roles",
            )
        return None

    if selected is None:
        if len(names) != 1:
            raise HTTPError(
                400,
                "public_view_role is required when "
                "multiple roles exist",
            )
        return names[0]

    if selected not in roles:
        raise HTTPError(
            400,
            f"public_view_role must be one of {names}",
        )

    return selected


def create_access_bundle(
    *,
    launch_spec: Mapping[str, Any],
) -> Dict[str, Any]:
    roles = _mapping(
        launch_spec.get("roles"),
        field="roles",
    )
    selected_role = _selected_role(
        roles,
        launch_spec.get("public_view_role"),
    )

    created = create_live_session_from_program(
        program=launch_spec["program"],
        program_language=str(launch_spec["program_language"]),
        session_metadata=_mapping(
            launch_spec.get("session_metadata"),
            field="session_metadata",
        ),
        roles=roles,
        role_mismatch_policy=_mapping(
            launch_spec.get("role_mismatch_policy"),
            field="role_mismatch_policy",
        ),
    )
    session_id = str(created["session_id"])

    try:
        if roles:
            role_handles = {
                name: _register_access_handle(
                    session_id=session_id,
                    role=name,
                )
                for name in roles
            }
            selected_handle = role_handles[str(selected_role)]
            access_ids = {
                "default": selected_handle.access_id,
                **{
                    name: handle.access_id
                    for name, handle in role_handles.items()
                },
            }
        else:
            selected_handle = _register_access_handle(
                session_id=session_id,
                role=None,
            )
            access_ids = {"default": selected_handle.access_id}

        unmodulated_handle: Optional[_AccessHandle] = None
        if bool(launch_spec.get("include_unmodulated_access", False)):
            if selected_handle.role is None:
                unmodulated_handle = selected_handle
            else:
                unmodulated_handle = _register_access_handle(
                    session_id=session_id,
                    role=None,
                )

        datum_read_map = extract_datum_read_map_v1(
            roles=roles,
            program=launch_spec["program"],
        )
        eps_hooks = {
            "visibility_of": launch_spec.get("eps_visibility_of"),
            "channel_validator": launch_spec.get("eps_channel_validator"),
            "ttl_seconds_of": launch_spec.get("eps_ttl_seconds_of"),
            "should_persist": launch_spec.get("eps_should_persist"),
        }
        with _ACCESS_LOCK:
            _SESSION_EPS_HOOKS[session_id] = eps_hooks
        _EPS_LOG.register_run(
            run_id=session_id,
            datum_read_map=datum_read_map,
        )

        if bool(launch_spec.get("start_on_create", True)):
            bootstrap_identity = _new_token("bootstrap")
            dispatch_live_session_action(
                session_id=session_id,
                action=UserAction.STEP,
                role=selected_handle.role,
                identity_id=bootstrap_identity,
                events_only=True,
                my_current_event_seq_number=0,
                threaded_callbacks=eps_callbacks_v1(
                    log=_EPS_LOG,
                    run_id=session_id,
                    request_id=bootstrap_identity,
                    base_identity_id=bootstrap_identity,
                    base_role=selected_handle.role,
                    theta_event_seq_at_emit=0,
                    **eps_hooks,
                ),
            )
    except Exception:
        release_local_session(session_id=session_id)
        raise

    return {
        "session_id": session_id,
        "public_view_role": selected_role,
        "selected_access_id": (
            selected_handle.access_id
        ),
        "access_ids": access_ids,
        "unmodulated_access_id": (
            None
            if unmodulated_handle is None
            else unmodulated_handle.access_id
        ),
        "launch_state": dict(created),
    }


def _static_root() -> str:
    return STATIC_SUBDIR


def build_access_handle_urls(
    *,
    access_ids: Mapping[str, str],
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    for key, access_id in dict(access_ids).items():
        handle = _get_access_handle(
            str(access_id)
        )
        values = {
            "role": handle.role,
            "context": url_for(
                f"{BLUEPRINT_NAME}.run_public",
                access_id=access_id,
            ),
            "latestEventSeq": url_for(
                f"{BLUEPRINT_NAME}.run_latest_event_seq",
                access_id=access_id,
            ),
            "events": url_for(
                f"{BLUEPRINT_NAME}.run_events",
                access_id=access_id,
            ),
            "eps": url_for(
                f"{BLUEPRINT_NAME}.run_eps",
                access_id=access_id,
            ),
            "dispatch": url_for(
                f"{BLUEPRINT_NAME}.run_dispatch",
                access_id=access_id,
            ),
            "dispatchFunked": url_for(
                f"{BLUEPRINT_NAME}."
                "run_dispatch_funked",
                access_id=access_id,
            ),
            "page": url_for(
                f"{BLUEPRINT_NAME}.run_page",
                access_id=access_id,
            ),
        }
        out[key] = values

    return out


def _public_state(
    handle: _AccessHandle,
) -> Dict[str, Any]:
    ctx = get_live_session_context(
        session_id=handle.session_id,
        role=handle.role,
    )
    event_kind = str(
        ctx.get("kind") or "ATSTART"
    )

    return {
        "kind": (
            "thinkument_live_session_public_state_v1"
        ),
        "access_id": handle.access_id,
        "role": handle.role,
        "ctx": dict(ctx),
        "event_kind": event_kind,
        "finished": event_kind == "ATCOMPLETION",
        "last_error": ctx.get("last_error"),
    }


def _public_dispatch_before_event_seq(
    result: Mapping[str, Any],
    *,
    funked: bool,
    server_before_event_seq: int,
) -> int:
    """
    Select the public operation's concurrency entry position.

    Direct dispatch is serialized by the highest-façade session write lane.
    Its core concurrency receipt therefore owns the authoritative entry
    position. In a conflicting-thread race, the losing request enters that
    lane only after the winning request has committed.

    Funked dispatch may create chain-continuation events before an inner core
    dispatch. Its public interval must instead begin at the outer server
    boundary captured before the complete chain operation.

    Structured pre-controller rejections, such as permission denial, have no
    core concurrency pocket and use the unchanged outer server position.
    """
    if funked:
        return int(server_before_event_seq)

    concurrency = result.get("dispatch_concurrency")
    if not isinstance(concurrency, Mapping):
        return int(server_before_event_seq)

    before = concurrency.get("before_event_seq")
    if type(before) is not int:
        return int(server_before_event_seq)

    return before


def _flask_dispatch_concurrency_receipt_v1(
    result: Mapping[str, Any],
    *,
    request_id: str,
    before_event_seq: int,
) -> Dict[str, Any]:
    """
    Return the exact public concurrency pocket for local Flask.

    ``before_event_seq`` is selected by the caller according to operation
    shape: serialized-lane admission for direct dispatch, or the outer hosting
    boundary for funked dispatch and pre-controller rejection.

    Core accepted receipts normally contain ``after_event_seq``. Preflight
    rejection receipts may omit it, so their observed canonical high-water is
    used as the unchanged after position.
    """
    core = (
        dict(result.get("dispatch_concurrency") or {})
        if isinstance(
            result.get("dispatch_concurrency"),
            Mapping,
        )
        else {}
    )
    staleness = (
        dict(result.get("dispatch_staleness") or {})
        if isinstance(
            result.get("dispatch_staleness"),
            Mapping,
        )
        else {}
    )

    observed_value = staleness.get("observed_event_seq")
    observed = (
        observed_value
        if type(observed_value) is int
        else int(before_event_seq)
    )

    after_value = core.get("after_event_seq")
    after = (
        after_value
        if type(after_value) is int
        else observed
    )

    return {
        "kind": "live_session_dispatch_concurrency_receipt_v1",
        "applied": bool(result.get("applied")),
        "rejected": bool(result.get("rejected")),
        "reason": (
            str(result.get("rejection_kind"))
            if result.get("rejection_kind")
            else None
        ),
        "stale_policy": "highest_facade_optional_cursor_v1",
        "before_event_seq": int(before_event_seq),
        "after_event_seq": int(after),
        "request_id": str(request_id),
        "idempotent_replay": False,
        "coordination_layer": "flask_single_process",
        "guarding": (
            "server_session_boundary_plus_highest_facade"
        ),
    }


def _permission_rejection_result_v1(
    *,
    handle: _AccessHandle,
    supplied_event_seq: int,
    observed_event_seq: int,
    error: PermissionError,
) -> Dict[str, Any]:
    """
    Return a structured, eventless public permission rejection.

    Permission denial is a normally finalized hosting operation. It is not a
    transaction abort: no controller dispatch was admitted, no canonical event
    was produced, and the result is safe to publish through dispatch progress.
    """
    del error

    return {
        "kind": "live_session_dispatch_rejected_v1",
        "ok": False,
        "applied": False,
        "rejected": True,
        "rejection_kind": "permission_denied",
        "dispatch_outcome": "permission_rejected",
        "write_committed": False,
        "events_only": True,
        "session_id": str(handle.session_id),
        "dispatcher_identity_id": None,
        "dispatcher_role": None,
        "event_kind": None,
        "finished": False,
        "last_error": None,
        "system_error": None,
        "dispatch_staleness": {
            "kind": (
                "live_session_dispatch_staleness_receipt_v1"
            ),
            "checked": False,
            "outcome": "not_checked",
            "reason": "permission_denied",
            "supplied_event_seq": int(supplied_event_seq),
            "observed_event_seq": int(observed_event_seq),
            "scope_last_changed_seq": 0,
            "target_last_changed_seq": 0,
            "target_count": 0,
        },
    }


def _complete_public_dispatch_blanket_v1(
    result: Mapping[str, Any],
    *,
    handle: _AccessHandle,
) -> Dict[str, Any]:
    """
    Complete the shared Flask/Django public dispatch blanket.

    Permission denial can reach this adapter in either of two equivalent
    highest-facade forms:

    * a raised ``PermissionError``; or
    * a returned structured ``permission_denied`` rejection.

    The raised form is already converted by
    ``_permission_rejection_result_v1``.  The returned form may intentionally
    omit nullable transport-facing fields that are not owned by core.  Flask
    owns the public HTTP membrane, so it completes those fields here instead
    of forcing higher applications to branch on the lower representation.

    This helper does not alter accepted, semantic-rejected, stale-rejected, or
    system-error semantics.  It only supplies the exact public fields whose
    values are mechanically determined at the hosting boundary.
    """
    packet = dict(result or {})

    packet.setdefault(
        "session_id",
        str(handle.session_id),
    )
    packet.setdefault("dispatcher_identity_id", None)
    packet.setdefault("dispatcher_role", None)
    packet.setdefault("event_kind", None)
    packet.setdefault("finished", False)
    packet.setdefault("last_error", None)
    packet.setdefault("system_error", None)

    if packet.get("rejection_kind") == "permission_denied":
        packet["kind"] = "live_session_dispatch_rejected_v1"
        packet["ok"] = False
        packet["applied"] = False
        packet["rejected"] = True
        packet["dispatch_outcome"] = "permission_rejected"
        packet["write_committed"] = False
        packet["events_only"] = True

    return packet


def _dispatch(
    access_id: str,
    *,
    funked: bool,
) -> Response:
    handle = _get_access_handle(access_id)
    payload = _parse_payload()
    _assert_payload_role(
        payload.get("role"),
        handle.role,
    )

    unexpected = sorted(
        set(payload) - LOCAL_FLASK_DISPATCH_PAYLOAD_KEYS
    )
    if unexpected:
        raise HTTPError(
            400,
            "unknown dispatch payload keys: "
            f"{unexpected}",
        )
    if not funked and "chainreactionTM_config" in payload:
        raise HTTPError(
            400,
            "chainreactionTM_config is valid only for dispatch-funked",
        )

    action_name = str(
        payload.get("action") or "STEP"
    ).strip().upper()
    try:
        action = UserAction[action_name]
    except KeyError as exc:
        raise HTTPError(
            400,
            f"unknown action {action_name!r}",
        ) from exc

    identity_id = str(
        payload.get("identity_id") or ""
    ).strip()
    if not identity_id:
        raise HTTPError(
            400,
            "identity_id is required",
        )

    raw_request_id = payload.get("request_id")
    if type(raw_request_id) is not str:
        raise HTTPError(
            400,
            "request_id must be a non-empty string",
        )
    request_id = raw_request_id.strip()
    if not request_id:
        raise HTTPError(
            400,
            "request_id must be a non-empty string",
        )

    user_fill = _mapping(
        payload.get("user_fill"),
        field="user_fill",
    )
    user_signal = _optional_mapping(
        payload.get("user_signal"),
        field="user_signal",
    )

    if "my_current_event_seq_number" not in payload:
        raise HTTPError(
            400,
            "my_current_event_seq_number is required",
        )

    cursor = _parse_int(
        payload["my_current_event_seq_number"],
        field="my_current_event_seq_number",
        default=0,
        minimum=0,
        maximum=2**63 - 1,
    )

    kwargs = {
        "session_id": handle.session_id,
        "action": action,
        "user_fill": user_fill,
        "user_signal": user_signal,
        "role": handle.role,
        "identity_id": identity_id,
        "events_only": True,
        "my_current_event_seq_number": cursor,
    }
    if funked and "chainreactionTM_config" in payload:
        kwargs["chainreactionTM_config"] = payload.get(
            "chainreactionTM_config"
        )

    server_before_event_seq = (
        get_live_session_latest_event_seq(
            session_id=handle.session_id,
        )
    )

    with _ACCESS_LOCK:
        eps_hooks = dict(_SESSION_EPS_HOOKS.get(handle.session_id) or {})

    kwargs["threaded_callbacks"] = eps_callbacks_v1(
        log=_EPS_LOG,
        run_id=handle.session_id,
        request_id=request_id,
        base_identity_id=identity_id,
        base_role=handle.role,
        theta_event_seq_at_emit=server_before_event_seq,
        **eps_hooks,
    )

    try:
        result = (
            dispatch_live_session_action_with_chain_reaction(
                **kwargs
            )
            if funked
            else dispatch_live_session_action(
                **kwargs
            )
        )
        result = _complete_public_dispatch_blanket_v1(
            dict(result or {}),
            handle=handle,
        )
    except PermissionError as exc:
        observed_event_seq = (
            get_live_session_latest_event_seq(
                session_id=handle.session_id,
            )
        )
        result = _permission_rejection_result_v1(
            handle=handle,
            supplied_event_seq=cursor,
            observed_event_seq=observed_event_seq,
            error=exc,
        )

    public_before_event_seq = (
        _public_dispatch_before_event_seq(
            result,
            funked=funked,
            server_before_event_seq=server_before_event_seq,
        )
    )

    # Flask has no durable idempotency repository. request_id is therefore
    # transport correlation metadata here, but it is still an exact required
    # field and must be echoed on every accepted or rejected dispatch receipt.
    result["request_id"] = request_id
    result["dispatch_concurrency"] = (
        _flask_dispatch_concurrency_receipt_v1(
            result,
            request_id=request_id,
            before_event_seq=public_before_event_seq,
        )
    )

    status = (
        403
        if result.get("rejection_kind") == "permission_denied"
        else 409
        if result.get("rejected")
        else 200
    )

    return jsonify(result), status


def thinkument_blueprint(
    *,
    launch_spec: Mapping[str, Any],
    url_prefix: str = "",
) -> Blueprint:
    # Static roots are process/package composition. The active opinionation is
    # a launch selection inside that immutable aggregate namespace. Absence of
    # the key means "use installed default"; an explicit null disables it.
    opinionation_module = select_opinionation_module_filename(
        explicit=launch_spec.get("opinionation_module"),
        use_installed_default=("opinionation_module" not in launch_spec),
    )

    bp = AggregatedStaticBlueprint(
        BLUEPRINT_NAME,
        __name__,
        url_prefix=url_prefix,
        static_folder=_static_root(),
        static_url_path=STATIC_URL_PATH,
    )

    @bp.errorhandler(HTTPError)
    def _http_error(error: HTTPError):
        return jsonify(
            {"error": error.message}
        ), error.status_code

    if bool(launch_spec.get("expose_typed_exceptions", False)):

        @bp.errorhandler(Exception)
        def _typed_unhandled_exception(error: Exception):
            if isinstance(error, HTTPException):
                return error
            return jsonify(
                {
                    "kind": TYPED_EXCEPTION_KIND_V1,
                    "exception_type": type(error).__name__,
                    "message": str(error),
                }
            ), 500

    @bp.after_request
    def _local_capability_headers(response: Response):
        response.headers["Cache-Control"] = (
            "no-store, private, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Robots-Tag"] = (
            "noindex, nofollow, noarchive"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers[
            "X-Thinkument-Runtime-Profile"
        ] = LOCAL_FLASK_RUNTIME_PROFILE
        return response

    @bp.route(
        "/create",
        methods=["POST"],
    )
    def create_action():
        payload = _parse_payload()
        unexpected = sorted(
            set(payload)
            - LOCAL_FLASK_CREATE_PAYLOAD_KEYS
        )
        if unexpected:
            raise HTTPError(
                400,
                "local Flask run creation accepts only start_on_create; "
                "the launcher program, program language, roles, session "
                "metadata, role policy, public role, and ThinkProgramTM "
                f"parameters are fixed (unexpected keys: {unexpected})",
            )

        effective = {
            **dict(launch_spec),
            "start_on_create": bool(
                payload.get(
                    "start_on_create",
                    launch_spec.get(
                        "start_on_create",
                        True,
                    ),
                )
            ),
        }

        bundle = create_access_bundle(
            launch_spec=effective
        )
        session_ids = current_app.extensions.setdefault(
            LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY,
            set(),
        )
        session_ids.add(str(bundle["session_id"]))

        handles = build_access_handle_urls(
            access_ids=bundle["access_ids"]
        )
        selected = _get_access_handle(
            str(bundle["selected_access_id"])
        )

        return jsonify(
            {
                "kind": (
                    "thinkument_local_flask_"
                    "launch_result_v1"
                ),
                "session_id": bundle["session_id"],
                "selected_access_id": (
                    selected.access_id
                ),
                "public_view_role": (
                    bundle["public_view_role"]
                ),
                "handles": handles,
                "unmodulated_access_id": bundle.get(
                    "unmodulated_access_id"
                ),
                "launch_state": (
                    bundle["launch_state"]
                ),
                "state": _public_state(selected),
            }
        )

    @bp.route(
        "/run/<access_id>",
        methods=["GET"],
    )
    def run_public(access_id: str):
        return jsonify(
            _public_state(
                _get_access_handle(access_id)
            )
        )

    @bp.route(
        "/run/<access_id>/latest-event-seq/",
        methods=["GET"],
    )
    def run_latest_event_seq(access_id: str):
        handle = _get_access_handle(access_id)
        return jsonify(
            {
                "kind": "thinkument_latest_event_seq_v1",
                "access_id": handle.access_id,
                "event_seq": (
                    get_live_session_latest_event_seq(
                        session_id=handle.session_id,
                    )
                ),
            }
        )

    @bp.route(
        "/run/<access_id>/events/",
        methods=["GET"],
    )
    def run_events(access_id: str):
        handle = _get_access_handle(access_id)
        identity_id = str(
            request.args.get("identity_id") or ""
        ).strip()
        if not identity_id:
            raise HTTPError(
                400,
                "identity_id is required",
            )

        try:
            page = get_live_session_events_since(
                session_id=handle.session_id,
                identity_id=identity_id,
                role=handle.role,
                after_event_seq=_parse_query_int(
                    request.args.get("after_event_seq"),
                    field="after_event_seq",
                    default=0,
                    maximum=2**63 - 1,
                ),
                limit=_parse_query_int(
                    request.args.get("limit"),
                    field="limit",
                    default=100,
                    minimum=1,
                    maximum=500,
                ),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPError(400, str(exc)) from exc

        return jsonify(page)

    @bp.route(
        "/run/<access_id>/eps/",
        methods=["GET"],
    )
    def run_eps(access_id: str):
        handle = _get_access_handle(access_id)
        raw_window = request.args.get("window")
        window = (
            None
            if raw_window in (None, "")
            else _parse_query_int(
                raw_window,
                field="window",
                default=512,
                minimum=1,
                maximum=10000,
            )
        )
        return jsonify(
            _EPS_LOG.read(
                run_id=handle.session_id,
                after_seq=_parse_query_int(
                    request.args.get("after_seq")
                    or request.args.get("after_eps_seq")
                    or request.args.get("after_provisional_seq"),
                    field="after_seq",
                    default=0,
                    maximum=2**63 - 1,
                ),
                limit=_parse_query_int(
                    request.args.get("limit"),
                    field="limit",
                    default=100,
                    minimum=1,
                    maximum=500,
                ),
                role=handle.role,
                request_id=request.args.get("request_id"),
                channel=request.args.get("channel"),
                window=window,
                unmodulated=(handle.role is None),
            )
        )

    @bp.route(
        "/run/<access_id>/dispatch/",
        methods=["POST"],
    )
    def run_dispatch(access_id: str):
        return _dispatch(
            access_id,
            funked=False,
        )

    @bp.route(
        "/run/<access_id>/dispatch-funked/",
        methods=["POST"],
    )
    def run_dispatch_funked(access_id: str):
        return _dispatch(
            access_id,
            funked=True,
        )

    @bp.route(
        "/run/<access_id>/page/",
        methods=["GET"],
    )
    def run_page(access_id: str):
        handle = _get_access_handle(access_id)
        identity_id = _new_token("web")

        initial_event_seq = (
            get_live_session_latest_event_seq(
                session_id=handle.session_id,
            )
        )
        endpoints = build_access_handle_urls(
            access_ids={
                "selected": access_id,
            }
        )["selected"]

        opinionation_module_url = (
            ""
            if opinionation_module is None
            else url_for(
                f"{BLUEPRINT_NAME}.static",
                filename=opinionation_module,
            )
        )

        config = build_thinkument_client_config(
            root_id=(
                f"thinkument-root-{access_id}"
            ),
            identity_id=identity_id,
            role=handle.role,
            endpoints=endpoints,
            initial_state=_public_state(handle),
            initial_event_seq=initial_event_seq,
            opinionation_module_url=opinionation_module_url,
            extra=formreacttm_client_extra_v1(),
        )

        return Response(
            render_shell_html(
                title="Thinkument Run",
                client_config=config,
                shim_url=url_for(
                    f"{BLUEPRINT_NAME}.static",
                    filename=WEB_SHIM_FILENAME,
                ),
            ),
            mimetype="text/html",
        )

    return bp


__all__ = [
    "LOCAL_FLASK_CREATE_PAYLOAD_KEYS",
    "LOCAL_FLASK_DISPATCH_PAYLOAD_KEYS",
    "TYPED_EXCEPTION_KIND_V1",
    "build_access_handle_urls",
    "create_access_bundle",
    "release_local_session",
    "reset_access_handles",
    "thinkument_blueprint",
]
