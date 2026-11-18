from __future__ import annotations

"""Generic, channel-agnostic run-level epsilon (`eps`) log and callback adapter.

Layering law (D15, D19):
  - `think-frontend` owns the generic `EpsLog` protocol, the `EpsRow` / `EpsPage`
    shapes, HMAC-SHA256 `content_hash` computation (D23), role-modulated row
    projection (D6, D21, D45), the `InMemoryEpsLog` implementation for local
    Flask / dry-run hosts, and the engine callback shim (`eps_event_callback_v1`).
  - `think-frontend` has ZERO knowledge of specific channel names, `Analytica`,
    `framework-4-services`, or Django/PostgreSQL persistence. Channel validation
    and per-channel visibility resolution are injected from higher layers when
    composed in `think-app` or `thinkument/service`.
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    Sequence,
     Set,
)

from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
    SESSION_EVENT_KIND_V1,
)
from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    effective_read_roles_for_role,
)


EPS_PAGE_KIND_V1 = "thinkument_eps_page_v1"
EPS_ROW_KIND_V1 = "thinkument_eps_row_v1"

VISIBILITY_OWNER_ONLY = "owner-only"
VISIBILITY_ALL_NO_MODULATION = "all-no-modulation"
VISIBILITY_ALL_WITH_MODULATION = "all-with-modulation"
EPS_VISIBILITIES_V1 = frozenset(
    {
        VISIBILITY_OWNER_ONLY,
        VISIBILITY_ALL_NO_MODULATION,
        VISIBILITY_ALL_WITH_MODULATION,
    }
)

EMITTER_ORIGIN_WIDGET_EXPLOSION = "widget_explosion"
EMITTER_ORIGIN_DISPATCH_RUNTIME = "dispatch_runtime"
EMITTER_ORIGIN_DELEGATED_WORKER = "delegated_worker"
EMITTER_ORIGIN_SERVICE_BACKGROUND = "service_background"
EMITTER_ORIGIN_EXTERNAL_RUNTIME = "external_runtime"
EPS_EMITTER_ORIGINS_V1 = frozenset(
    {
        EMITTER_ORIGIN_WIDGET_EXPLOSION,
        EMITTER_ORIGIN_DISPATCH_RUNTIME,
        EMITTER_ORIGIN_DELEGATED_WORKER,
        EMITTER_ORIGIN_SERVICE_BACKGROUND,
        EMITTER_ORIGIN_EXTERNAL_RUNTIME,
    }
)

DEFAULT_EPS_PAGE_LIMIT = 100
MAX_EPS_PAGE_LIMIT = 500


class EpsReplayConflictError(RuntimeError):
    """Same (run_id, event_id) replayed with different canonical identity/payload."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_eps_payload_json_v1(payload: Any) -> str:
    """Serialize an eps payload to canonical dead JSON for hashing and replay checks."""
    normalized = {} if payload is None else payload
    try:
        return json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError(f"eps payload must be dead JSON: {exc}") from exc


DEFAULT_LOCAL_EPS_SECRET_KEY_V1 = b"thinkument-local-in-memory-eps-secret-v1"


def derive_run_eps_hash_key_v1(
    secret_key: bytes | str = DEFAULT_LOCAL_EPS_SECRET_KEY_V1,
    run_id: str = "",
) -> bytes:
    """Derive a deterministic per-run HMAC key from a host secret and run_id (D23)."""
    secret_bytes = (
        secret_key
        if isinstance(secret_key, bytes)
        else str(secret_key).encode("utf-8")
    )
    run_bytes = str(run_id or "").strip().encode("utf-8")
    return hmac.new(secret_bytes, run_bytes, hashlib.sha256).digest()


def compute_eps_content_hash_v1(
    payload: Any,
    *,
    run_key: bytes | str,
) -> str:
    """Compute HMAC-SHA256 hex digest over the canonical JSON of payload (D23)."""
    key_bytes = (
        run_key
        if isinstance(run_key, bytes)
        else str(run_key).encode("utf-8")
    )
    canonical_bytes = canonical_eps_payload_json_v1(payload).encode("utf-8")
    return hmac.new(key_bytes, canonical_bytes, hashlib.sha256).hexdigest()


def _clean_role_list(raw_roles: Any) -> List[str]:
    if raw_roles is None:
        return []
    if isinstance(raw_roles, str):
        items = [raw_roles]
    elif isinstance(raw_roles, Sequence) and not isinstance(
        raw_roles, (bytes, bytearray)
    ):
        items = list(raw_roles)
    else:
        items = [raw_roles]
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def extract_datum_read_map_v1(
    *,
    roles: Mapping[str, Any] | None = None,
    program: Mapping[str, Any] | None = None,
    U: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Extract a compact, dead-JSON role & datum read-access map for a run (D16, D30, D45).

    Structure returned:
      {
          "roles": {
              "<role_name>": ["<role_name>", "<adjacent_readable_role>", ...],
          },
          "datum_roles": {
              "<frame_id>:<span_id>:<datum_id>": ["<required_role>", ...],
              "<span_id>:<datum_id>": ["<required_role>", ...],
              "<datum_id>": ["<required_role>", ...],
          },
      }
    Unguarded datums (empty required_roles) are stored as `[]` when they override
    a guarded span or omitted so the map stays compact.
    """
    resolved_roles: Dict[str, Any] = {}
    if isinstance(roles, Mapping):
        resolved_roles = dict(roles)
    elif isinstance(U, Mapping):
        meta = U.get("session_metadata") or U.get("metadata") or {}
        if isinstance(meta, Mapping) and isinstance(meta.get("roles"), Mapping):
            resolved_roles = dict(meta["roles"])

    role_effective_map: Dict[str, List[str]] = {}
    for role_name in resolved_roles:
        r_str = str(role_name or "").strip()
        if not r_str:
            continue
        try:
            eff = sorted(
                effective_read_roles_for_role(resolved_roles, role=r_str)
            )
        except Exception:
            eff = [r_str]
        role_effective_map[r_str] = eff

    datum_roles_map: Dict[str, List[str]] = {}

    def _record_datum(
        frame_id: str,
        span_id: str,
        datum_id: str,
        req_roles: List[str],
    ) -> None:
        d_id = str(datum_id or "").strip()
        if not d_id:
            return
        f_id = str(frame_id or "").strip()
        s_id = str(span_id or "").strip()
        if f_id and s_id:
            datum_roles_map[f"{f_id}:{s_id}:{d_id}"] = list(req_roles)
        if s_id:
            datum_roles_map.setdefault(f"{s_id}:{d_id}", list(req_roles))
        datum_roles_map.setdefault(d_id, list(req_roles))

    # 1. Inspect static program definition if supplied
    if isinstance(program, Mapping):
        run_block = program.get("run") if isinstance(program.get("run"), Mapping) else program
        prog_block = (
            run_block.get("program")
            if isinstance(run_block, Mapping) and isinstance(run_block.get("program"), Mapping)
            else run_block
        )
        if isinstance(prog_block, Mapping):
            widgets_raw = prog_block.get("widgets")
            widget_roles_by_id: Dict[str, List[str]] = {}
            if isinstance(widgets_raw, Mapping):
                for w_id, w_spec in widgets_raw.items():
                    if isinstance(w_spec, Mapping):
                        w_roles = _clean_role_list(
                            w_spec.get("roles")
                            if "roles" in w_spec
                            else w_spec.get("role")
                        )
                        widget_roles_by_id[str(w_id)] = w_roles
                        _record_datum("", "", str(w_id), w_roles)

            flow_raw = prog_block.get("flow")
            if isinstance(flow_raw, Sequence) and not isinstance(
                flow_raw, (str, bytes, bytearray)
            ):
                for step in flow_raw:
                    if not isinstance(step, Mapping):
                        continue
                    s_id = str(step.get("id") or step.get("span_id") or "").strip()
                    f_id = str(step.get("frame_id") or "").strip()
                    span_roles = _clean_role_list(
                        step.get("roles") if "roles" in step else step.get("role")
                    )
                    step_widgets = step.get("widgets") or step.get("datums") or []
                    if isinstance(step_widgets, Sequence) and not isinstance(
                        step_widgets, (str, bytes, bytearray)
                    ):
                        for item in step_widgets:
                            if isinstance(item, str):
                                w_id = item.strip()
                                eff_req = widget_roles_by_id.get(w_id) or span_roles
                                _record_datum(f_id, s_id, w_id, eff_req)
                            elif isinstance(item, Mapping):
                                w_id = str(
                                    item.get("datum_id")
                                    or item.get("id")
                                    or item.get("widget_id")
                                    or ""
                                ).strip()
                                item_roles = _clean_role_list(
                                    item.get("roles")
                                    if "roles" in item
                                    else item.get("role")
                                )
                                eff_req = (
                                    item_roles
                                    or widget_roles_by_id.get(w_id, [])
                                    or span_roles
                                )
                                _record_datum(f_id, s_id, w_id, eff_req)

    # 2. Inspect live unmodulated session context U if supplied
    if isinstance(U, Mapping):
        frame_id = str(U.get("frame_id") or "").strip()
        span_id = str(U.get("span_id") or "").strip()
        span_roles = _clean_role_list(
            U.get("span_roles") if "span_roles" in U else U.get("roles")
        )
        for container_key in ("datums", "widgets", "current_step_datums"):
            container = U.get(container_key)
            if isinstance(container, Mapping):
                for d_id, d_row in container.items():
                    if not isinstance(d_row, Mapping):
                        continue
                    d_roles = _clean_role_list(
                        d_row.get("roles")
                        if "roles" in d_row
                        else d_row.get("role")
                    )
                    eff_req = d_roles if d_roles else span_roles
                    _record_datum(
                        str(d_row.get("frame_id") or frame_id),
                        str(d_row.get("span_id") or span_id),
                        str(d_id),
                        eff_req,
                    )
            elif isinstance(container, Sequence) and not isinstance(
                container, (str, bytes, bytearray)
            ):
                for d_row in container:
                    if not isinstance(d_row, Mapping):
                        continue
                    d_id = str(
                        d_row.get("datum_id") or d_row.get("id") or ""
                    ).strip()
                    if not d_id:
                        continue
                    d_roles = _clean_role_list(
                        d_row.get("roles")
                        if "roles" in d_row
                        else d_row.get("role")
                    )
                    eff_req = d_roles if d_roles else span_roles
                    _record_datum(
                        str(d_row.get("frame_id") or frame_id),
                        str(d_row.get("span_id") or span_id),
                        d_id,
                        eff_req,
                    )

    return {
        "roles": role_effective_map,
        "datum_roles": datum_roles_map,
    }


def resolve_datum_required_roles_v1(
    datum_read_map: Mapping[str, Any] | None,
    *,
    frame_id: str = "",
    span_id: str = "",
    datum_id: str = "",
) -> List[str]:
    """Resolve the required read roles for a datum coordinate (D30, D45)."""
    d_id = str(datum_id or "").strip()
    if not d_id or not isinstance(datum_read_map, Mapping):
        return []
    datum_roles = datum_read_map.get("datum_roles")
    if not isinstance(datum_roles, Mapping):
        return []
    f_id = str(frame_id or "").strip()
    s_id = str(span_id or "").strip()
    for key in (
        f"{f_id}:{s_id}:{d_id}" if (f_id and s_id) else "",
        f"{s_id}:{d_id}" if s_id else "",
        d_id,
    ):
        if key and key in datum_roles:
            return _clean_role_list(datum_roles[key])
    return []


def effective_read_roles_from_map_v1(
    datum_read_map: Mapping[str, Any] | None,
    *,
    role: str | None,
) -> Set[str]:
    """Return the set of roles readable by `role` using `datum_read_map`."""
    r_str = str(role or "").strip()
    if not r_str:
        return set()
    if isinstance(datum_read_map, Mapping):
        roles_block = datum_read_map.get("roles")
        if isinstance(roles_block, Mapping) and r_str in roles_block:
            return set(_clean_role_list(roles_block[r_str])) | {r_str}
    return {r_str}


def can_role_read_eps_row_v1(
    *,
    role: str | None,
    required_roles: Sequence[str],
    datum_read_map: Mapping[str, Any] | None = None,
    effective_read_roles: Set[str] | None = None,
    unmodulated: bool = False,
) -> bool:
    """O(1) role-read check for an `all-with-modulation` eps row (D21, D30, D45)."""
    if unmodulated:
        return True
    req = {str(r).strip() for r in (required_roles or ()) if str(r or "").strip()}
    if not req:
        return True
    if role is None or not str(role).strip():
        return False
    eff = (
        effective_read_roles
        if effective_read_roles is not None
        else effective_read_roles_from_map_v1(datum_read_map, role=role)
    )
    return bool(req & eff)


def project_eps_row_v1(
    row: Mapping[str, Any],
    *,
    role: str | None = None,
    datum_read_map: Mapping[str, Any] | None = None,
    effective_read_roles: Set[str] | None = None,
    for_owner: bool = False,
    unmodulated: bool = False,
) -> Optional[Dict[str, Any]]:
    """Pure read-time projection of one stored eps row (D6, D21, D45, D49).

    Returns `None` if `visibility == 'owner-only'` and `not for_owner`.
    Otherwise returns the wire `EpsRow` dictionary (full when readable, or
    obfuscated integrity trident when `visibility == 'all-with-modulation'` and
    the viewer role cannot read `datum_id`).
    """
    visibility = str(row.get("visibility") or VISIBILITY_ALL_WITH_MODULATION)
    if visibility == VISIBILITY_OWNER_ONLY and not for_owner:
        return None

    datum_id = str(row.get("datum_id") or "").strip()
    frame_id = str(row.get("frame_id") or "").strip()
    span_id = str(row.get("span_id") or "").strip()
    form_id = str(row.get("form_id") or "").strip()

    if for_owner or unmodulated or visibility == VISIBILITY_ALL_NO_MODULATION:
        readable = True
    elif visibility == VISIBILITY_ALL_WITH_MODULATION:
        if not datum_id:
            # Fail-safe per D21: an all-with-modulation row with no datum_id
            # has no widget to gate by, so its content is obfuscated.
            readable = False
        else:
            req_roles = row.get("required_roles")
            if req_roles is None:
                req_roles = resolve_datum_required_roles_v1(
                    datum_read_map,
                    frame_id=frame_id,
                    span_id=span_id,
                    datum_id=datum_id,
                )
            readable = can_role_read_eps_row_v1(
                role=role,
                required_roles=req_roles,
                datum_read_map=datum_read_map,
                effective_read_roles=effective_read_roles,
                unmodulated=unmodulated,
            )
    else:
        readable = False

    theta_seq = row.get("theta_event_seq_at_emit")
    theta_seq_norm = None if theta_seq is None else int(theta_seq)

    return {
        "kind": EPS_ROW_KIND_V1,
        "eps_seq": int(row["eps_seq"]),
        "event_id": str(row.get("event_id") or ""),
        "channel": str(row.get("channel") or ""),
        "emitted_at": str(row.get("emitted_at") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "visibility": visibility,
        "theta_event_seq_at_emit": theta_seq_norm,
        "emitter_origin": str(
            row.get("emitter_origin") or EMITTER_ORIGIN_WIDGET_EXPLOSION
        ),
        "request_id": str(row.get("request_id") or ""),
        "trident_dispatch_id": str(row.get("trident_dispatch_id") or ""),
        "obfuscated": not readable,
        "datum_id": datum_id if readable else None,
        "frame_id": frame_id if readable else None,
        "span_id": span_id if readable else None,
        "form_id": form_id if readable else None,
        "payload": deepcopy(row.get("payload")) if readable else None,
        "event": deepcopy(row.get("payload")) if readable else None,
    }


class EpsLog(Protocol):
    """Protocol implemented by `InMemoryEpsLog` and the service Postgres `EpsLog`."""

    def append(
        self,
        *,
        run_id: str,
        event_id: str,
        channel: str,
        emitted_at: str,
        payload: Any,
        visibility: str = VISIBILITY_ALL_WITH_MODULATION,
        datum_id: str = "",
        frame_id: str = "",
        span_id: str = "",
        form_id: str = "",
        theta_event_seq_at_emit: Optional[int] = None,
        emitter_origin: str = EMITTER_ORIGIN_WIDGET_EXPLOSION,
        request_id: str = "",
        trident_dispatch_id: str = "",
        dispatcher_identity_id: str = "",
        dispatcher_role: Optional[str] = None,
        required_roles: Optional[Sequence[str]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]: ...

    def read(
        self,
        *,
        run_id: str,
        after_seq: int = 0,
        limit: int = DEFAULT_EPS_PAGE_LIMIT,
        role: Optional[str] = None,
        window: Optional[int] = None,
        for_owner: bool = False,
        unmodulated: bool = False,
    ) -> Dict[str, Any]: ...

    def head(self, *, run_id: str) -> int: ...

    def query(
        self,
        *,
        channel: Optional[str] = None,
        ref: Optional[str] = None,
        parent_ref: Optional[str] = None,
        ref_prefix: Optional[str] = None,
        ref_regex: Optional[str] = None,
        meta: Optional[Mapping[str, Any]] = None,
        all_in_run: bool = False,
        all_for_owner: bool = False,
        run_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        after_seq: int = 0,
        limit: int = DEFAULT_EPS_PAGE_LIMIT,
        caller_role: Optional[str] = None,
        for_owner: bool = False,
        allow_all: bool = False,
        emitted_from: Optional[Any] = None,
        emitted_to: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...


@dataclass
class _InMemoryRunEpsState:
    last_seq: int = 0
    rows: List[Dict[str, Any]] = field(default_factory=list)
    by_event_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    datum_read_map: Dict[str, Any] = field(default_factory=dict)


class InMemoryEpsLog:
    """Thread-safe in-memory `EpsLog` for Flask and dry-run hosts (D5, D18, D19, D23)."""

    def __init__(
        self,
        *,
        secret_key: bytes | str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret_key = (
            secrets.token_bytes(32)
            if secret_key is None
            else (
                secret_key
                if isinstance(secret_key, bytes)
                else str(secret_key).encode("utf-8")
            )
        )
        self._clock = clock
        self._lock = threading.RLock()
        self._runs: MutableMapping[str, _InMemoryRunEpsState] = {}

    def _run_state(self, run_id: str) -> _InMemoryRunEpsState:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("run_id must be non-empty")
        state = self._runs.get(rid)
        if state is None:
            state = _InMemoryRunEpsState()
            self._runs[rid] = state
        return state

    def reset(self) -> None:
        with self._lock:
            self._runs.clear()

    def release_run(self, *, run_id: str) -> None:
        rid = str(run_id or "").strip()
        with self._lock:
            self._runs.pop(rid, None)

    def register_run(
        self,
        *,
        run_id: str,
        datum_read_map: Optional[Mapping[str, Any]] = None,
    ) -> None:
        with self._lock:
            state = self._run_state(run_id)
            if isinstance(datum_read_map, Mapping):
                # Merge roles and datum_roles so dynamic step discoveries enrich the map
                existing_roles = dict(state.datum_read_map.get("roles") or {})
                existing_datum_roles = dict(
                    state.datum_read_map.get("datum_roles") or {}
                )
                if isinstance(datum_read_map.get("roles"), Mapping):
                    existing_roles.update(datum_read_map["roles"])
                if isinstance(datum_read_map.get("datum_roles"), Mapping):
                    existing_datum_roles.update(datum_read_map["datum_roles"])
                state.datum_read_map = {
                    "roles": existing_roles,
                    "datum_roles": existing_datum_roles,
                }

    def datum_read_map_for_run(self, run_id: str = "") -> Dict[str, Any]:
        with self._lock:
            state = self._runs.get(str(run_id or "").strip())
            return deepcopy(state.datum_read_map) if state is not None else {}

    def head(self, run_id: str = "") -> int:
        with self._lock:
            state = self._runs.get(str(run_id or "").strip())
            return 0 if state is None else int(state.last_seq)

    def clear(self, run_id: Optional[str] = None) -> None:
        with self._lock:
            if run_id is None:
                self._runs.clear()
            else:
                self._runs.pop(str(run_id or "").strip(), None)

    def append(
        self,
        *,
        run_id: str,
        event_id: str = "",
        channel: str,
        emitted_at: Optional[str] = None,
        payload: Any = None,
        visibility: str = VISIBILITY_ALL_WITH_MODULATION,
        datum_id: str = "",
        frame_id: str = "",
        span_id: str = "",
        form_id: str = "",
        theta_event_seq_at_emit: Optional[int] = None,
        emitter_origin: str = EMITTER_ORIGIN_WIDGET_EXPLOSION,
        request_id: str = "",
        trident_dispatch_id: str = "",
        dispatcher_identity_id: str = "",
        dispatcher_role: Optional[str] = None,
        required_roles: Optional[Sequence[str]] = None,
        ttl_seconds: Optional[int] = None,
        owner_id: str = "",
        meta: Optional[Mapping[str, Any]] = None,
        ref: Optional[str] = None,
        parent_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise ValueError("run_id must be non-empty")
        ev_id = str(event_id or "").strip()
        if not ev_id and ref:
            ev_id = str(ref).strip()
        if not ev_id:
            ev_id = str(uuid.uuid4())
        ch = str(channel or "").strip()
        if not ch:
            raise ValueError("channel must be non-empty")
        vis = str(visibility or VISIBILITY_ALL_WITH_MODULATION).strip()
        if vis not in EPS_VISIBILITIES_V1:
            raise ValueError(f"unknown eps visibility: {vis!r}")
        origin = str(emitter_origin or EMITTER_ORIGIN_WIDGET_EXPLOSION).strip()
        if origin not in EPS_EMITTER_ORIGINS_V1:
            raise ValueError(f"unknown eps emitter_origin: {origin!r}")

        payload_norm = {} if payload is None else deepcopy(payload)
        canonical_json = canonical_eps_payload_json_v1(payload_norm)
        run_key = derive_run_eps_hash_key_v1(self._secret_key, rid)
        content_hash = compute_eps_content_hash_v1(
            payload_norm,
            run_key=run_key,
        )

        d_id = str(datum_id or "").strip()
        f_id = str(frame_id or "").strip()
        s_id = str(span_id or "").strip()
        if not s_id and parent_ref:
            s_id = str(parent_ref).strip()
        fm_id = str(form_id or "").strip()
        req_id = str(request_id or "").strip()
        trident_id = str(trident_dispatch_id or "").strip()
        theta_seq = (
            None
            if theta_event_seq_at_emit is None
            else int(theta_event_seq_at_emit)
        )

        identity_signature = (
            ch,
            vis,
            d_id,
            f_id,
            s_id,
            fm_id,
            origin,
            req_id,
            trident_id,
            canonical_json,
        )

        with self._lock:
            state = self._run_state(rid)
            existing = state.by_event_id.get(ev_id)
            if existing is not None:
                if existing["_identity_signature"] != identity_signature:
                    raise EpsReplayConflictError(
                        f"eps event_id {ev_id!r} replayed with conflicting payload or metadata"
                    )
                return deepcopy(existing["row"])

            resolved_req_roles = (
                _clean_role_list(required_roles)
                if required_roles is not None
                else resolve_datum_required_roles_v1(
                    state.datum_read_map,
                    frame_id=f_id,
                    span_id=s_id,
                    datum_id=d_id,
                )
            )

            seq = state.last_seq + 1
            state.last_seq = seq
            now_ts = float(self._clock())
            expires_at_ts = (
                None
                if ttl_seconds is None
                else now_ts + float(ttl_seconds)
            )

            stored_row: Dict[str, Any] = {
                "eps_seq": seq,
                "event_id": ev_id,
                "ref": ev_id,
                "parent_ref": (s_id or None),
                "owner_id": str(owner_id or ""),
                "meta": deepcopy(dict(meta or {})),
                "run_id": rid,
                "channel": ch,
                "emitted_at": str(emitted_at or _utc_now_iso()),
                "content_hash": content_hash,
                "visibility": vis,
                "theta_event_seq_at_emit": theta_seq,
                "emitter_origin": origin,
                "request_id": req_id,
                "trident_dispatch_id": trident_id,
                "dispatcher_identity_id": str(dispatcher_identity_id or ""),
                "dispatcher_role": (
                    None if dispatcher_role in (None, "") else str(dispatcher_role)
                ),
                "datum_id": d_id,
                "frame_id": f_id,
                "span_id": s_id,
                "form_id": fm_id,
                "payload": payload_norm,
                "required_roles": resolved_req_roles,
                "expires_at_ts": expires_at_ts,
            }
            state.rows.append(stored_row)
            state.by_event_id[ev_id] = {
                "_identity_signature": identity_signature,
                "row": stored_row,
            }
            return deepcopy(stored_row)

    def read(
        self,
        *,
        run_id: str,
        after_seq: int = 0,
        limit: int = DEFAULT_EPS_PAGE_LIMIT,
        role: Optional[str] = None,
        request_id: Optional[str] = None,
        channel: Optional[str] = None,
        window: Optional[int] = None,
        for_owner: bool = False,
        unmodulated: bool = False,
    ) -> Dict[str, Any]:
        if after_seq < 0:
            raise ValueError("after_seq must be >= 0")
        clamped_limit = max(1, min(int(limit), MAX_EPS_PAGE_LIMIT))
        rid = str(run_id or "").strip()

        with self._lock:
            state = self._runs.get(rid)
            if state is None:
                return {
                    "kind": EPS_PAGE_KIND_V1,
                    "after_seq": int(after_seq),
                    "next_after_seq": int(after_seq),
                    "eps_head": 0,
                    "rows": [],
                    "events": [],
                }
            head_seq = int(state.last_seq)
            raw_rows = list(state.rows)
            datum_read_map = deepcopy(state.datum_read_map)

        now_ts = float(self._clock())
        eff_read_roles = effective_read_roles_from_map_v1(
            datum_read_map,
            role=role,
        )

        req_norm = str(request_id or "").strip()
        ch_norm = str(channel or "").strip()

        # 1. Filter out expired TTL rows, (unless for_owner) owner-only rows, and optional request/channel
        eligible_rows: List[Dict[str, Any]] = []
        for row in raw_rows:
            exp = row.get("expires_at_ts")
            if exp is not None and exp <= now_ts:
                continue
            if not for_owner and row.get("visibility") == VISIBILITY_OWNER_ONLY:
                continue
            if req_norm:
                r_req = str(row.get("request_id") or "").strip()
                r_tri = str(row.get("trident_dispatch_id") or "").strip()
                if req_norm not in (r_req, r_tri):
                    continue
            if ch_norm and str(row.get("channel") or "").strip() != ch_norm:
                continue
            eligible_rows.append(row)

        # 2. Apply optional initial wake-up `window` cap AFTER filtering out owner-only rows (D44)
        effective_after_seq = int(after_seq)
        if (
            after_seq == 0
            and window is not None
            and int(window) > 0
            and len(eligible_rows) > int(window)
        ):
            skipped_row = eligible_rows[-(int(window) + 1)]
            effective_after_seq = int(skipped_row["eps_seq"])
            eligible_rows = eligible_rows[-int(window) :]
        else:
            eligible_rows = [
                row
                for row in eligible_rows
                if int(row["eps_seq"]) > effective_after_seq
            ]

        page_source = eligible_rows[:clamped_limit]
        projected_rows: List[Dict[str, Any]] = []
        for row in page_source:
            projected = project_eps_row_v1(
                row,
                role=role,
                datum_read_map=datum_read_map,
                effective_read_roles=eff_read_roles,
                for_owner=for_owner,
                unmodulated=unmodulated,
            )
            if projected is not None:
                projected_rows.append(projected)

        if projected_rows:
            next_after = int(projected_rows[-1]["eps_seq"])
        elif not eligible_rows:
            # All rows up to head_seq have been scanned (any gap at the tail is owner-only or expired)
            next_after = max(effective_after_seq, head_seq)
        else:
            next_after = effective_after_seq

        return {
            "kind": EPS_PAGE_KIND_V1,
            "after_seq": int(after_seq),
            "next_after_seq": int(next_after),
            "eps_head": int(head_seq),
            "rows": projected_rows,
            "events": projected_rows,
        }

    def query(
        self,
        *,
        channel: Optional[str] = None,
        ref: Optional[str] = None,
        parent_ref: Optional[str] = None,
        ref_prefix: Optional[str] = None,
        ref_regex: Optional[str] = None,
        meta: Optional[Mapping[str, Any]] = None,
        all_in_run: bool = False,
        all_for_owner: bool = False,
        run_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        after_seq: int = 0,
        limit: int = DEFAULT_EPS_PAGE_LIMIT,
        caller_role: Optional[str] = None,
        for_owner: bool = False,
        allow_all: bool = False,
        emitted_from: Optional[Any] = None,
        emitted_to: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Multi-modal targeted and batch seek over stored epsilon records (Jobsian seam & Wozniakian engine)."""
        clamped_limit = max(1, min(int(limit), MAX_EPS_PAGE_LIMIT))
        now_ts = float(self._clock())

        with self._lock:
            if run_id:
                target_rid = str(run_id).strip()
                candidate_rids = [target_rid] if target_rid in self._runs else []
            else:
                candidate_rids = list(self._runs.keys())

            matches: List[Dict[str, Any]] = []

            for rid in candidate_rids:
                state = self._runs[rid]
                datum_read_map = deepcopy(state.datum_read_map)
                eff_read_roles = effective_read_roles_from_map_v1(
                    datum_read_map,
                    role=caller_role,
                )

                for row in state.rows:
                    # 1. TTL Expiration
                    exp = row.get("expires_at_ts")
                    if exp is not None and exp <= now_ts:
                        continue

                    # 2. Owner filter
                    if owner_id:
                        row_owner = str(row.get("owner_id") or "").strip()
                        if row_owner and row_owner != str(owner_id).strip():
                            continue

                    # 3. Channel filter
                    if channel:
                        if str(row.get("channel") or "").strip() != str(channel).strip():
                            continue

                    # 4. Point seek (ref / event_id)
                    if ref is not None:
                        row_ref = str(row.get("event_id") or row.get("ref") or "").strip()
                        if row_ref != str(ref).strip():
                            continue

                    # 5. Hierarchy seek (parent_ref / span_id)
                    if parent_ref is not None:
                        row_parent = str(row.get("span_id") or row.get("parent_ref") or "").strip()
                        if row_parent != str(parent_ref).strip():
                            continue

                    # 6. Sub-dir / prefix seek (ref_prefix)
                    if ref_prefix is not None:
                        row_ref = str(row.get("event_id") or row.get("ref") or "").strip()
                        if not row_ref.startswith(str(ref_prefix).strip()):
                            continue

                    # 7. Pattern regex seek (ref_regex)
                    if ref_regex is not None:
                        row_ref = str(row.get("event_id") or row.get("ref") or "").strip()
                        if not re.search(str(ref_regex), row_ref):
                            continue

                    # 8. Meta tags
                    if meta:
                        row_meta = dict(row.get("meta") or {})
                        if any(row_meta.get(k) != v for k, v in meta.items()):
                            continue

                    # 9. Sequence cursor
                    if after_seq > 0:
                        if int(row.get("eps_seq") or 0) <= int(after_seq):
                            continue

                    # 10. Emitted time filtering
                    if emitted_from is not None or emitted_to is not None:
                        try:
                            row_time = datetime.fromisoformat(str(row.get("emitted_at") or "").replace("Z", "+00:00"))
                            if emitted_from is not None:
                                ef = emitted_from if isinstance(emitted_from, datetime) else datetime.fromisoformat(str(emitted_from).replace("Z", "+00:00"))
                                if row_time < ef:
                                    continue
                            if emitted_to is not None:
                                et = emitted_to if isinstance(emitted_to, datetime) else datetime.fromisoformat(str(emitted_to).replace("Z", "+00:00"))
                                if row_time > et:
                                    continue
                        except Exception:
                            pass

                    # 11. Role modulation & visibility
                    vis = str(row.get("visibility") or VISIBILITY_ALL_WITH_MODULATION)
                    if vis == VISIBILITY_OWNER_ONLY and not for_owner and not allow_all:
                        continue

                    if for_owner or allow_all or vis == VISIBILITY_ALL_NO_MODULATION:
                        readable_payload = deepcopy(row.get("payload"))
                    elif vis == VISIBILITY_ALL_WITH_MODULATION:
                        can_read = can_role_read_eps_row_v1(
                            role=caller_role,
                            required_roles=row.get("required_roles"),
                            datum_read_map=datum_read_map,
                            effective_read_roles=eff_read_roles,
                        )
                        readable_payload = deepcopy(row.get("payload")) if can_read else None
                    else:
                        readable_payload = None

                    canonical_envelope = {
                        "ref": str(row.get("event_id") or row.get("ref") or ""),
                        "parent_ref": str(row.get("span_id")) if row.get("span_id") else (str(row.get("parent_ref")) if row.get("parent_ref") else None),
                        "channel": str(row.get("channel") or ""),
                        "payload": readable_payload,
                        "meta": deepcopy(dict(row.get("meta") or {})),
                        "eps_seq": int(row.get("eps_seq") or 0),
                        "emitted_at": str(row.get("emitted_at") or ""),
                        "run_id": str(rid or ""),
                    }
                    matches.append(canonical_envelope)
                    if ref is not None:
                        break

            return matches[:clamped_limit]


class EpsControllerAndExplosionCallbackV1:
    """Engine callback adapter that tracks active theta trident state and appends eps emissions.

    - Observes `controller_loop_event_v1` in memory ONLY to track active
      `trident_dispatch_id`, `dispatcher_identity_id`, `dispatcher_role`, and
      unmodulated `U` (never appending controller events to `EpsLog`, D36/D49).
    - Turns `datum_lifecycle_event_v1` emissions into `EpsLog.append` calls.
    """

    def __init__(
        self,
        *,
        log: InMemoryEpsLog,
        run_id: str,
        request_id: str = "",
        base_identity_id: str = "",
        base_role: Optional[str] = None,
        theta_event_seq_at_emit: Optional[int] = None,
        visibility_of: Optional[Callable[[str], str]] = None,
        channel_validator: Optional[
            Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
        ] = None,
        ttl_seconds_of: Optional[Callable[[str], Optional[int]]] = None,
        should_persist: Optional[Callable[[str], bool]] = None,
        previous_controller: Any = None,
        previous_explosion: Any = None,
    ) -> None:
        self._log = log
        self._run_id = str(run_id or "").strip()
        self._request_id = str(request_id or "").strip()
        self._base_identity_id = str(base_identity_id or "").strip()
        self._base_role = (
            None if base_role in (None, "") else str(base_role).strip()
        )
        self._theta_event_seq_at_emit = (
            None
            if theta_event_seq_at_emit is None
            else int(theta_event_seq_at_emit)
        )
        self._visibility_of = visibility_of
        self._channel_validator = channel_validator
        self._ttl_seconds_of = ttl_seconds_of
        self._should_persist = should_persist
        self._previous_controller = previous_controller
        self._previous_explosion = previous_explosion

        self._active_trident_dispatch_id: str = self._request_id
        self._active_identity_id: str = self._base_identity_id
        self._active_role: Optional[str] = self._base_role

    def observe_controller_event_v1(self, event: Mapping[str, Any]) -> Any:
        raw = dict(event or {})
        if str(raw.get("kind") or "") == "controller_loop_event_v1":
            dispatch_id = str(raw.get("dispatch_id") or "").strip()
            if dispatch_id:
                self._active_trident_dispatch_id = dispatch_id
            if "dispatcher_identity_id" in raw or "dispatcher_role" in raw:
                ident = raw.get("dispatcher_identity_id")
                role = raw.get("dispatcher_role")
                self._active_identity_id = (
                    "" if ident in (None, "") else str(ident).strip()
                )
                self._active_role = (
                    None if role in (None, "") else str(role).strip()
                )
            payload = raw.get("payload")
            if isinstance(payload, Mapping) and isinstance(
                payload.get("U"), Mapping
            ):
                self._log.register_run(
                    run_id=self._run_id,
                    datum_read_map=extract_datum_read_map_v1(U=payload["U"]),
                )
        if callable(self._previous_controller):
            return self._previous_controller(event)
        return None

    def observe_dispatch_context_v1(self, dispatch_context: Mapping[str, Any]) -> Any:
        ctx = dict(dispatch_context or {})
        ident = ctx.get("dispatcher_identity_id")
        role = ctx.get("dispatcher_role")
        before_seq = ctx.get("before_event_seq")
        if ident not in (None, ""):
            self._active_identity_id = str(ident).strip()
        if "dispatcher_role" in ctx:
            self._active_role = (
                None if role in (None, "") else str(role).strip()
            )
        if type(before_seq) is int:
            self._theta_event_seq_at_emit = int(before_seq)
        observer = getattr(
            self._previous_explosion,
            "observe_dispatch_context_v1",
            None,
        )
        if callable(observer):
            return observer(dispatch_context)
        return None

    def observe_unmodulated_context_v1(self, U: Mapping[str, Any]) -> Any:
        if isinstance(U, Mapping):
            self._log.register_run(
                run_id=self._run_id,
                datum_read_map=extract_datum_read_map_v1(U=U),
            )
        observer = getattr(
            self._previous_explosion,
            "observe_unmodulated_context_v1",
            None,
        )
        if callable(observer):
            return observer(U)
        return None

    def __call__(self, event: Mapping[str, Any]) -> Any:
        raw = dict(event or {})
        if str(raw.get("kind") or "") == SESSION_EVENT_KIND_V1:
            channel = str(raw.get("name") or "datum.event").strip()
            payload_raw = raw.get("payload")
            payload_map = (
                dict(payload_raw)
                if isinstance(payload_raw, Mapping)
                else {"value": payload_raw}
            )
            if callable(self._channel_validator):
                payload_map = dict(self._channel_validator(channel, payload_map))

            persist = (
                bool(self._should_persist(channel))
                if callable(self._should_persist)
                else True
            )
            if persist:
                visibility = (
                    str(self._visibility_of(channel))
                    if callable(self._visibility_of)
                    else VISIBILITY_ALL_WITH_MODULATION
                )
                ttl_seconds = (
                    self._ttl_seconds_of(channel)
                    if callable(self._ttl_seconds_of)
                    else None
                )
                source = str(raw.get("source") or "datum_widget").strip()
                if source in ("datum_widget", "datum_widget_result"):
                    emitter_origin = EMITTER_ORIGIN_WIDGET_EXPLOSION
                elif source == "external":
                    emitter_origin = EMITTER_ORIGIN_EXTERNAL_RUNTIME
                else:
                    emitter_origin = EMITTER_ORIGIN_DISPATCH_RUNTIME

                self._log.append(
                    run_id=self._run_id,
                    event_id=str(raw.get("event_id") or ""),
                    channel=channel,
                    emitted_at=str(raw.get("emitted_at") or _utc_now_iso()),
                    payload=payload_map,
                    visibility=visibility,
                    datum_id=str(raw.get("datum_id") or ""),
                    frame_id=str(raw.get("frame_id") or ""),
                    span_id=str(raw.get("span_id") or ""),
                    form_id=str(raw.get("form_id") or ""),
                    theta_event_seq_at_emit=self._theta_event_seq_at_emit,
                    emitter_origin=emitter_origin,
                    request_id=self._request_id,
                    trident_dispatch_id=self._active_trident_dispatch_id,
                    dispatcher_identity_id=self._active_identity_id,
                    dispatcher_role=self._active_role,
                    ttl_seconds=ttl_seconds,
                )

        if callable(self._previous_explosion):
            return self._previous_explosion(event)
        return None


def eps_callbacks_v1(
    *,
    log: InMemoryEpsLog,
    run_id: str,
    request_id: str = "",
    base_identity_id: str = "",
    base_role: Optional[str] = None,
    theta_event_seq_at_emit: Optional[int] = None,
    visibility_of: Optional[Callable[[str], str]] = None,
    channel_validator: Optional[
        Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
    ] = None,
    ttl_seconds_of: Optional[Callable[[str], Optional[int]]] = None,
    should_persist: Optional[Callable[[str], bool]] = None,
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build `threaded_callbacks` dict wiring `EpsControllerAndExplosionCallbackV1`."""
    out = dict(existing or {})
    adapter = EpsControllerAndExplosionCallbackV1(
        log=log,
        run_id=run_id,
        request_id=request_id,
        base_identity_id=base_identity_id,
        base_role=base_role,
        theta_event_seq_at_emit=theta_event_seq_at_emit,
        visibility_of=visibility_of,
        channel_validator=channel_validator,
        ttl_seconds_of=ttl_seconds_of,
        should_persist=should_persist,
        previous_controller=out.get(CONTROLLER_EVENTS_CALLBACK_KEY),
        previous_explosion=out.get(EXPLOSION_EVENTS_CALLBACK_KEY),
    )
    out[CONTROLLER_EVENTS_CALLBACK_KEY] = adapter.observe_controller_event_v1
    out[EXPLOSION_EVENTS_CALLBACK_KEY] = adapter
    return out


__all__ = [
    "DEFAULT_EPS_PAGE_LIMIT",
    "EMITTER_ORIGIN_DELEGATED_WORKER",
    "EMITTER_ORIGIN_DISPATCH_RUNTIME",
    "EMITTER_ORIGIN_EXTERNAL_RUNTIME",
    "EMITTER_ORIGIN_SERVICE_BACKGROUND",
    "EMITTER_ORIGIN_WIDGET_EXPLOSION",
    "EPS_EMITTER_ORIGINS_V1",
    "EPS_PAGE_KIND_V1",
    "EPS_ROW_KIND_V1",
    "EPS_VISIBILITIES_V1",
    "EpsControllerAndExplosionCallbackV1",
    "EpsLog",
    "EpsReplayConflictError",
    "InMemoryEpsLog",
    "MAX_EPS_PAGE_LIMIT",
    "VISIBILITY_ALL_NO_MODULATION",
    "VISIBILITY_ALL_WITH_MODULATION",
    "VISIBILITY_OWNER_ONLY",
    "can_role_read_eps_row_v1",
    "canonical_eps_payload_json_v1",
    "compute_eps_content_hash_v1",
    "derive_run_eps_hash_key_v1",
    "effective_read_roles_from_map_v1",
    "eps_callbacks_v1",
    "extract_datum_read_map_v1",
    "project_eps_row_v1",
    "resolve_datum_required_roles_v1",
]
