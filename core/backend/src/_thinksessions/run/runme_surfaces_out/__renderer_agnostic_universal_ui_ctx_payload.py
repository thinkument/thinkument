# think-backend/src/_thinkengine/runme/runme_surfaces_in/__renderer_agnostic_universal_ui_ctx_payload.py
from __future__ import annotations

"""
UI Session Context Contract (DICT-ONLY)
======================================

This module is the single source of truth for the payload shape the
Thinkument UI consumes from a session backend.

Public interactive ctx is current-frame scoped. It contains the whole current
frame needed by a renderer, but not future frames, future spans, or future datum
surfaces.

Hard rule: dict-only membrane
-----------------------------
A UI context payload MUST contain only JSON-safe primitives:

    dict | list | str | int | float | bool | None

No engine/session objects may cross this boundary.

This file intentionally provides:
- TypedDict schemas for context payload shape
- A read-only view (UIContextView) that validates and exposes values
  strictly as dict-only JSON-safe primitives
- No role semantics, no role derivation, no renderer policy execution

"""

from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, TypedDict

from _thinkprogram._iomicrosTM.tiny_helpers import JSONValue


CTX_FRAMES = "frames"
CTX_CURRENT_SPAN = "current_span"
CTX_SPAN_ORDER = "span_order"

CTX_SPAN_TO_DATUM_WIDGETS = "span_to_datum_widgets"
CTX_DATUM_WIDGET_DECLS = "datum_widget_decls"
CTX_DATUM_WIDGET_FILLS = "datum_widget_fills"
CTX_DATUM_WIDGETS_ON_THIS_SPAN = "datum_widgets_on_this_span"
CTX_DATUM_STATES_ON_THIS_SPAN = "datum_states_on_this_span"

CTX_SESSION_METADATA = "session_metadata"
CTX_LAST_ERROR = "last_error"
CTX_CURSOR = "cursor"
CTX_KIND = "kind"

CTX_SESSION_ID = "session_id"
CTX_FORM_ID = "form_id"
CTX_APP_FORM_ID = "app_form_id"
CTX_CURRENT_FRAME_ID = "current_frame_id"
CTX_CURRENT_FRAME_NAME = "current_frame_name"
CTX_CURRENT_SPAN_ID = "current_span_id"
CTX_GLOBALS = "globals"
CTX_STEP = "step"
CTX_STATE = "state"
CTX_MULTIFRAMESPEC = "multiframespec"
CTX_TAGS = "tags"

CTX_ROLE_MISMATCH_MODULATION_INFO = "role_mismatch_modulation_info"


class UIFillSpan(TypedDict, total=False):
    name: str


class UIFrame(TypedDict, total=False):
    name: str
    id: str
    fillspans: list[UIFillSpan]
    field_ids: list[str]


class UIFieldDecl(TypedDict, total=False):
    field_id: str
    datum_args: Dict[str, Any] | None
    fillspan_name: str | None
    default: Any | None
    appearance: Dict[str, Any] | None
    extras: Dict[str, Any] | None
    hierarchy_prefix: str
    micros: list[str]
    micro_names: list[str]


class UIDatumState(TypedDict, total=False):
    kind: str
    datum_id: str
    form_id: str
    frame_id: str
    span_id: str
    is_authoritative: bool
    is_pending: bool
    shell: Dict[str, Any]
    micros: list[Dict[str, Any]]
    micro_names: list[str]
    args: Dict[str, Any]
    fill: Any
    has_fill: bool
    semantic_validation: Dict[str, Any]
    lifecycle: Dict[str, Any]
    originating_step: Dict[str, Any]
    role_mismatch_obfuscated: bool


class UIContextContract(TypedDict, total=False):
    frames: list[UIFrame]
    current_span: Optional[str]
    span_order: list[str]
    span_to_datum_widgets: Dict[str, list[str]]
    datum_widget_decls: Dict[str, UIFieldDecl]
    datum_widget_fills: Dict[str, Any]
    datum_widgets_on_this_span: list[str]
    datum_states_on_this_span: list[UIDatumState]
    session_metadata: Dict[str, Any]
    last_error: Optional[Dict[str, str]]
    cursor: Any
    kind: Any

    session_id: Optional[str]
    form_id: Optional[str]
    app_form_id: Optional[str]
    current_frame_id: Optional[str]
    current_frame_name: Optional[str]
    current_span_id: Optional[str]
    globals: Dict[str, Any]
    step: Dict[str, Any]
    state: Dict[str, Any]
    multiframespec: Dict[str, Any]
    tags: list[str]

    role_mismatch_modulation_info: Optional[Dict[str, Any]]


def _json_validate(obj: Any, *, path: str) -> JSONValue:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            raise TypeError(f"UI context contains non-JSON-safe bytes at {path}")

    if isinstance(obj, Mapping):
        out: Dict[str, JSONValue] = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"UI context contains non-string dict key at {path}: {k!r}"
                )
            out[k] = _json_validate(v, path=f"{path}.{k}")
        return out

    if isinstance(obj, list):
        return [
            _json_validate(v, path=f"{path}[{i}]")
            for i, v in enumerate(obj)
        ]

    if isinstance(obj, tuple):
        raise TypeError(f"UI context contains tuple at {path} (must be list)")

    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        raise TypeError(
            f"UI context contains non-list sequence at {path}: {type(obj)!r}"
        )

    raise TypeError(
        f"UI context contains non-JSON-safe value at {path}: {type(obj)!r}"
    )


def _as_mapping_strict(ctx: Any) -> Mapping[str, Any]:
    if not isinstance(ctx, Mapping):
        raise TypeError(
            f"UIContextView requires a Mapping/dict, got: {type(ctx)!r}"
        )
    return ctx


def _mget(ctx: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return ctx.get(key, default)
    except Exception:
        return default


def _normalize_frame(frame: Any) -> UIFrame:
    f = _json_validate(frame, path="frames[]")
    if not isinstance(f, dict):
        raise TypeError("UI frame must be a dict")

    raw_id = f.get("id")
    fid = str(raw_id) if raw_id is not None else None

    name = f.get("name") or fid or "<frame>"

    spans = f.get("fillspans") or []
    spans_out: list[UIFillSpan] = []
    if not isinstance(spans, list):
        raise TypeError("UIFrame.fillspans must be a list")

    for sp in spans:
        spj = _json_validate(sp, path="frames[].fillspans[]")
        if isinstance(spj, dict):
            sname = spj.get("name") or "<span>"
            spans_out.append(UIFillSpan(name=str(sname)))
        elif isinstance(spj, str):
            spans_out.append(UIFillSpan(name=spj))
        else:
            raise TypeError("UIFillSpan must be dict or str")

    field_ids = f.get("field_ids") or []
    if not isinstance(field_ids, list):
        raise TypeError("UIFrame.field_ids must be a list")

    out = UIFrame(
        name=str(name),
        fillspans=spans_out,
        field_ids=[str(x) for x in field_ids],
    )
    if fid is not None:
        out["id"] = fid
    return out


def _coerce_field_decl_to_dict(v: Any) -> Dict[str, Any] | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        return None
    out = _json_validate(v, path="datum_widget_decls[]")
    return dict(out) if isinstance(out, dict) else None


def _first_matching_frame(
    *,
    frames: Sequence[UIFrame],
    frame_id: Optional[str],
    current_span: Optional[str],
) -> Optional[UIFrame]:
    if frame_id:
        for fr in frames:
            if str(fr.get("id") or "") == str(frame_id):
                return fr

    if current_span:
        for fr in frames:
            for sp in list(fr.get("fillspans") or []):
                if str(sp.get("name") or "") == str(current_span):
                    return fr

    return None


def ui_context_contract_sheet_v1() -> Dict[str, Any]:

    rows = [
        {
            "key": CTX_FRAMES,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "list[UIFrame]",
            "meaning": "Renderable current-frame projection. Future frames are not public ctx.",
        },
        {
            "key": CTX_CURRENT_SPAN,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "str|None",
            "meaning": "Current span id/name being filled now.",
        },
        {
            "key": CTX_SPAN_ORDER,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "list[str]",
            "meaning": "Global span traversal order for the current form.",
        },
        {
            "key": CTX_SPAN_TO_DATUM_WIDGETS,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "dict[str, list[str]]",
            "meaning": "Current-frame span id -> datum ids owned by that span.",
        },
        {
            "key": CTX_DATUM_WIDGET_DECLS,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "dict[str, UIFieldDecl]",
            "meaning": "Datum declarations for current-frame fields only.",
        },
        {
            "key": CTX_DATUM_WIDGET_FILLS,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "dict[str, Any]",
            "meaning": "Authoritative merged field values.",
        },
        {
            "key": CTX_DATUM_WIDGETS_ON_THIS_SPAN,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "list[str]",
            "meaning": "Fields editable now for the current manual stop.",
        },
        {
            "key": CTX_DATUM_STATES_ON_THIS_SPAN,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "list[UIDatumState]",
            "meaning": (
                "Static span-owned datum vector in ownership order. Each row "
                "joins the latest effective shell, micros, authored semantic "
                "validator specs, fill, lifecycle state, authority, pending "
                "status, and originating step arguments."
            ),
        },
        {
            "key": CTX_SESSION_METADATA,
            "tier": "core",
            "required_for_manual_ui": True,
            "shape": "dict[str, Any]",
            "meaning": "Session/page/chrome metadata surface.",
        },
        {
            "key": CTX_LAST_ERROR,
            "tier": "core",
            "required_for_manual_ui": False,
            "shape": "dict[str, str]|None",
            "meaning": "Latest validation or manual fill errors.",
        },
        {
            "key": CTX_CURSOR,
            "tier": "core",
            "required_for_manual_ui": False,
            "shape": "dict|scalar|None",
            "meaning": "Engine cursor position info.",
        },
        {
            "key": CTX_KIND,
            "tier": "core",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Current engine/runtime kind.",
        },
        {
            "key": CTX_SESSION_ID,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Session id for the current runtime instance.",
        },
        {
            "key": CTX_FORM_ID,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Current emitted form id in session scope.",
        },
        {
            "key": CTX_APP_FORM_ID,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "App/public form id for the pending form.",
        },
        {
            "key": CTX_CURRENT_FRAME_ID,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Current frame id selected by the manual stop.",
        },
        {
            "key": CTX_CURRENT_FRAME_NAME,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Human/name alias for current frame.",
        },
        {
            "key": CTX_CURRENT_SPAN_ID,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "str|None",
            "meaning": "Alias of current_span for explicitness.",
        },
        {
            "key": CTX_GLOBALS,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "dict[str, Any]",
            "meaning": "Application globals view.",
        },
        {
            "key": CTX_STEP,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "dict[str, Any]",
            "meaning": "Current manual/runtime step payload.",
        },
        {
            "key": CTX_STATE,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "dict[str, Any]",
            "meaning": "Cheap runtime state summary.",
        },
        {
            "key": CTX_MULTIFRAMESPEC,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "dict[str, Any]",
            "meaning": "Current-frame projection of the pending normalized multiframespec.",
        },
        {
            "key": CTX_TAGS,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "list[str]",
            "meaning": "UI contract tags.",
        },
        {
            "key": CTX_ROLE_MISMATCH_MODULATION_INFO,
            "tier": "harmonized",
            "required_for_manual_ui": False,
            "shape": "dict|None",
            "meaning": (
                "Role-modulation report attached by the role-aware boundary. "
                "The base UI ctx contract remains roleless."
            ),
        },
    ]

    return {
        "v": 1,
        "core_keys": [
            CTX_FRAMES,
            CTX_CURRENT_SPAN,
            CTX_SPAN_ORDER,
            CTX_SPAN_TO_DATUM_WIDGETS,
            CTX_DATUM_WIDGET_DECLS,
            CTX_DATUM_WIDGET_FILLS,
            CTX_DATUM_WIDGETS_ON_THIS_SPAN,
            CTX_DATUM_STATES_ON_THIS_SPAN,
            CTX_SESSION_METADATA,
            CTX_LAST_ERROR,
            CTX_CURSOR,
            CTX_KIND,
        ],
        "harmonized_keys": [
            CTX_SESSION_ID,
            CTX_FORM_ID,
            CTX_APP_FORM_ID,
            CTX_CURRENT_FRAME_ID,
            CTX_CURRENT_FRAME_NAME,
            CTX_CURRENT_SPAN_ID,
            CTX_GLOBALS,
            CTX_STEP,
            CTX_STATE,
            CTX_MULTIFRAMESPEC,
            CTX_TAGS,
            CTX_ROLE_MISMATCH_MODULATION_INFO,
        ],
        "rows": rows,
        "derived_views": [
            {
                "name": "build_ctx_manifest_sheet_v1(ctx)",
                "shape": "dict",
                "meaning": "Centralized manifest/provenance view.",
            },
            {
                "name": "build_ctx_navigation_model_v1(ctx)",
                "shape": "dict",
                "meaning": "Centralized progress/sidebar/header navigation model.",
            },
        ],
        "test_assertions": [
            "ctx must remain dict/list/scalar only",
            "ctx.current_span_id must equal ctx.current_span when present",
            "ctx.current_frame_name should resolve from frames/current_frame_id when possible",
            "ctx.multiframespec.app_form_id should match ctx.app_form_id when both are present",
            "ctx.datum_widget_fills must be the authoritative merged values surface",
            "public interactive ctx must not expose future frames",
            "public interactive ctx must not expose future spans",
            "public interactive ctx must not expose future datum declarations/fills",
            (
                "ctx.datum_states_on_this_span must contain one row per "
                "current-span owned datum in span ownership order"
            ),
            (
                "the datum-state vector is static ownership, while "
                "datum_widgets_on_this_span is the dynamic pending subset"
            ),
            "each readable datum-state shell must be the latest effective shell",
            (
                "each readable datum-state shell must equal the corresponding "
                "ctx.multiframespec.datums row exactly"
            ),
            (
                "compiled renderer-cache defaults must not drift the public "
                "datum-state shell from the effective multiframespec shell"
            ),
            (
                "role=None is the privileged canonical read; named roles are "
                "role-projected reads"
            ),
            "role projection must obfuscate unreadable datum-state rows",
            (
                "an obfuscated datum-state row must not expose shell, micros, "
                "arguments, fill, semantic validation, lifecycle, or step "
                "provenance"
            ),
        ],
    }


def build_ctx_manifest_sheet_v1(ctx: Any) -> Dict[str, Any]:
    """
    Canonical manifest/provenance sheet for UI authors.
    """
    v = ctx if isinstance(ctx, UIContextView) else UIContextView(ctx)
    prov = v.session_metadata.get("provenance") or {}
    if not isinstance(prov, Mapping):
        prov = {}

    return {
        "v": 1,
        "source_program_language": prov.get("source_program_language"),
        "source_program": prov.get("source_program"),
        "highest_manifest": prov.get("highest_manifest"),
        "thinkument_higher_program": prov.get("thinkument_higher_program"),
        "thinkument_manifest": prov.get("thinkument_manifest"),
        "normalized_thinkument_manifest": prov.get("normalized_thinkument_manifest"),
        "app_table_manifest": prov.get("app_table_manifest"),
        "compile_artifacts": prov.get("compile_artifacts"),
        "lowering_chain": list(prov.get("lowering_chain") or []),
    }


def _steps_from_app_table_manifest(app_table_manifest: Any) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    raw_steps = None

    if isinstance(app_table_manifest, list):
        raw_steps = app_table_manifest
    elif isinstance(app_table_manifest, Mapping):
        maybe = app_table_manifest.get("steps")
        if isinstance(maybe, list):
            raw_steps = maybe

    for i, st in enumerate(raw_steps or []):
        if not isinstance(st, Mapping):
            continue

        public_step_name = str(st.get("public_step_name") or "").strip()
        if not public_step_name:
            continue

        step_fn = str(st.get("step_fn") or "").strip()
        out.append(
            {
                "index": i,
                "public_step_name": public_step_name,
                "label": (
                    public_step_name.replace("_", " ").replace(".", " ").strip()
                    or public_step_name
                ),
                "step_fn": step_fn,
            }
        )

    return out


def build_ctx_navigation_model_v1(ctx: Any) -> Dict[str, Any]:
    """
    Canonical centralized navigation/progress model.
    """
    v = ctx if isinstance(ctx, UIContextView) else UIContextView(ctx)
    manifest_sheet = build_ctx_manifest_sheet_v1(v)
    app_steps = _steps_from_app_table_manifest(
        manifest_sheet.get("app_table_manifest")
    )

    state = v.state
    forms_emitted_order_raw = (
        state.get("forms_emitted_order")
        if isinstance(state, Mapping)
        else []
    )
    forms_emitted_order = (
        [str(x) for x in forms_emitted_order_raw]
        if isinstance(forms_emitted_order_raw, list)
        else []
    )

    current_program_step_name = (
        str(v.step.get("public_step_name") or "").strip()
        or str(v.app_form_id or v.form_id or "").strip()
    ) or None

    current_program_step_index = None
    for row in app_steps:
        if str(row.get("public_step_name")) == str(current_program_step_name):
            current_program_step_index = int(row.get("index"))
            break

    steps_out: list[Dict[str, Any]] = []
    total_steps = len(app_steps)

    for row in app_steps:
        nm = str(row["public_step_name"])
        idx = int(row["index"])
        is_current = nm == current_program_step_name
        is_emitted = nm in forms_emitted_order

        status = "upcoming"
        if is_current:
            status = "current"
        elif is_emitted:
            status = "visited"

        steps_out.append(
            {
                "index": idx,
                "ordinal": idx + 1,
                "public_step_name": nm,
                "label": str(row.get("label") or nm),
                "step_fn": str(row.get("step_fn") or ""),
                "status": status,
                "is_current": is_current,
                "is_emitted": is_emitted,
                "is_complete": bool(is_emitted and not is_current),
            }
        )

    completed_n = 0
    for st in steps_out:
        if st["is_complete"]:
            completed_n += 1

    if current_program_step_name:
        percent = (
            int(round(((completed_n + 1) / total_steps) * 100.0))
            if total_steps > 0
            else 0
        )
    else:
        percent = (
            int(round((completed_n / total_steps) * 100.0))
            if total_steps > 0
            else 0
        )

    return {
        "v": 1,
        "source": "app_table_manifest" if steps_out else "frames_fallback",
        "source_program_language": manifest_sheet.get("source_program_language"),
        "total_steps": total_steps,
        "completed_steps": completed_n,
        "current_program_step_name": current_program_step_name,
        "current_program_step_index": current_program_step_index,
        "current_frame_id": v.current_frame_id,
        "current_frame_name": v.current_frame_name,
        "current_span_id": v.current_span_id,
        "current_form_id": v.form_id,
        "current_app_form_id": v.app_form_id,
        "forms_emitted_order": list(forms_emitted_order),
        "percent": max(0, min(100, percent)),
        "steps": steps_out,
    }


class UIContextView(Mapping[str, Any]):
    """
    Read-only dict-only view over a raw context.

    This class validates and exposes context shape. It does not infer role
    mismatch semantics.
    """

    def __init__(self, raw: Any):
        self._raw = raw
        self._m = _as_mapping_strict(raw)

    @property
    def session_metadata(self) -> Dict[str, Any]:
        meta = _json_validate(
            _mget(self._m, CTX_SESSION_METADATA, {}) or {},
            path="session_metadata",
        )
        return dict(meta) if isinstance(meta, dict) else {}

    @property
    def session_id(self) -> Optional[str]:
        v = _json_validate(
            _mget(self._m, CTX_SESSION_ID, None),
            path="session_id",
        )
        return str(v) if v is not None else None

    @property
    def form_id(self) -> Optional[str]:
        v = _json_validate(
            _mget(self._m, CTX_FORM_ID, None),
            path="form_id",
        )
        return str(v) if v is not None else None

    @property
    def app_form_id(self) -> Optional[str]:
        v = _json_validate(
            _mget(self._m, CTX_APP_FORM_ID, None),
            path="app_form_id",
        )
        if v is not None:
            return str(v)

        fs = self.multiframespec
        if isinstance(fs, Mapping):
            vv = fs.get("app_form_id")
            if vv is not None:
                return str(vv)

        return None

    @property
    def frames(self) -> list[UIFrame]:
        frames = _mget(self._m, CTX_FRAMES, []) or []
        frames_j = _json_validate(frames, path="frames")
        if not isinstance(frames_j, list):
            raise TypeError("frames must be a list")
        return [_normalize_frame(f) for f in frames_j]

    @property
    def current_span(self) -> Optional[str]:
        span = _mget(self._m, CTX_CURRENT_SPAN, None)
        span_j = _json_validate(span, path="current_span")
        return str(span_j) if span_j is not None else None

    @property
    def current_span_id(self) -> Optional[str]:
        span = _mget(self._m, CTX_CURRENT_SPAN_ID, None)
        span_j = _json_validate(span, path="current_span_id")
        if span_j is not None:
            return str(span_j)
        return self.current_span

    @property
    def current_frame_id(self) -> Optional[str]:
        raw = _mget(self._m, CTX_CURRENT_FRAME_ID, None)
        raw_j = _json_validate(raw, path="current_frame_id")
        if raw_j is not None:
            return str(raw_j)

        fr = _first_matching_frame(
            frames=self.frames,
            frame_id=None,
            current_span=self.current_span,
        )
        if isinstance(fr, Mapping):
            fid = fr.get("id")
            return str(fid) if fid is not None else None

        return None

    @property
    def current_frame_name(self) -> Optional[str]:
        raw = _mget(self._m, CTX_CURRENT_FRAME_NAME, None)
        raw_j = _json_validate(raw, path="current_frame_name")
        if raw_j is not None:
            return str(raw_j)

        fr = _first_matching_frame(
            frames=self.frames,
            frame_id=self.current_frame_id,
            current_span=self.current_span,
        )
        if isinstance(fr, Mapping):
            name = fr.get("name") or fr.get("id")
            return str(name) if name is not None else None

        return None

    @property
    def span_order(self) -> list[str]:
        order = _json_validate(
            _mget(self._m, CTX_SPAN_ORDER, []) or [],
            path="span_order",
        )
        if not isinstance(order, list):
            raise TypeError("span_order must be a list")
        return [str(x) for x in order]

    @property
    def span_to_datum_widgets(self) -> Dict[str, list[str]]:
        m = _json_validate(
            _mget(self._m, CTX_SPAN_TO_DATUM_WIDGETS, {}) or {},
            path="span_to_datum_widgets",
        )
        if not isinstance(m, dict):
            raise TypeError("span_to_datum_widgets must be a dict")

        out: Dict[str, list[str]] = {}
        for k, v in m.items():
            if isinstance(v, list):
                out[str(k)] = [str(x) for x in v]
            else:
                raise TypeError(f"span_to_datum_widgets[{k!r}] must be a list")

        return out

    @property
    def datum_widget_decls(self) -> Dict[str, Dict[str, Any]]:
        raw = _mget(self._m, CTX_DATUM_WIDGET_DECLS, {}) or {}
        if not isinstance(raw, Mapping):
            raise TypeError("datum_widget_decls must be a dict/mapping")

        out: Dict[str, Dict[str, Any]] = {}
        for k, v in raw.items():
            kk = str(k)
            dv = _coerce_field_decl_to_dict(v)
            if isinstance(dv, dict):
                out[kk] = dv

        return out

    @property
    def datum_widget_fills(self) -> Dict[str, Any]:
        m = _mget(self._m, CTX_DATUM_WIDGET_FILLS, {}) or {}
        mj = _json_validate(m, path="datum_widget_fills")
        return dict(mj) if isinstance(mj, dict) else {}

    @property
    def datum_widgets_on_this_span(self) -> list[str]:
        p = _json_validate(
            _mget(self._m, CTX_DATUM_WIDGETS_ON_THIS_SPAN, []) or [],
            path="datum_widgets_on_this_span",
        )
        if not isinstance(p, list):
            raise TypeError("datum_widgets_on_this_span must be a list")
        return [str(x) for x in p]

    @property
    def datum_states_on_this_span(self) -> list[Dict[str, Any]]:
        raw = _json_validate(
            _mget(
                self._m,
                CTX_DATUM_STATES_ON_THIS_SPAN,
                [],
            )
            or [],
            path="datum_states_on_this_span",
        )
        if not isinstance(raw, list):
            raise TypeError(
                "datum_states_on_this_span must be a list"
            )

        return [
            dict(row)
            for row in raw
            if isinstance(row, dict)
        ]

    @property
    def datum_states_on_this_span_by_id(self) -> Dict[str, Dict[str, Any]]:
        """
        Convenience index over the canonical ownership-order vector.

        The list remains the contract authority because it preserves span
        product-vector order. This mapping is a read-only derived view and
        creates no second datum-state authority.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for row in self.datum_states_on_this_span:
            datum_id = str(row.get("datum_id") or "").strip()
            if not datum_id:
                raise ValueError(
                    "datum_states_on_this_span row has an empty datum_id"
                )
            if datum_id in out:
                raise ValueError(
                    "datum_states_on_this_span contains duplicate datum id: "
                    f"{datum_id!r}"
                )
            out[datum_id] = dict(row)
        return out

    @property
    def datum_widgets_on_this_span_provided(self) -> bool:
        try:
            return CTX_DATUM_WIDGETS_ON_THIS_SPAN in self._m
        except Exception:
            return False

    @property
    def globals(self) -> Dict[str, Any]:
        g = _json_validate(
            _mget(self._m, CTX_GLOBALS, {}) or {},
            path="globals",
        )
        return dict(g) if isinstance(g, dict) else {}

    @property
    def step(self) -> Dict[str, Any]:
        s = _json_validate(
            _mget(self._m, CTX_STEP, {}) or {},
            path="step",
        )
        return dict(s) if isinstance(s, dict) else {}

    @property
    def state(self) -> Dict[str, Any]:
        s = _json_validate(
            _mget(self._m, CTX_STATE, {}) or {},
            path="state",
        )
        return dict(s) if isinstance(s, dict) else {}

    @property
    def multiframespec(self) -> Dict[str, Any]:
        fs = _json_validate(
            _mget(self._m, CTX_MULTIFRAMESPEC, {}) or {},
            path="multiframespec",
        )
        return dict(fs) if isinstance(fs, dict) else {}

    @property
    def tags(self) -> list[str]:
        tg = _json_validate(
            _mget(self._m, CTX_TAGS, []) or [],
            path="tags",
        )
        if not isinstance(tg, list):
            return []
        return [str(x) for x in tg]

    @property
    def role_mismatch_modulation_info(self) -> Optional[Dict[str, Any]]:
        rm = _json_validate(
            _mget(self._m, CTX_ROLE_MISMATCH_MODULATION_INFO, None),
            path="role_mismatch_modulation_info",
        )
        if rm is None:
            return None
        if not isinstance(rm, dict):
            raise TypeError(
                "role_mismatch_modulation_info must be a dict if provided"
            )
        return dict(rm)

    @property
    def last_error(self) -> Optional[Dict[str, str]]:
        le = _json_validate(
            _mget(self._m, CTX_LAST_ERROR, None),
            path="last_error",
        )
        if le is None:
            return None
        if not isinstance(le, dict):
            raise TypeError("last_error must be a dict if provided")

        out: Dict[str, str] = {}
        for k, v in le.items():
            if v is None:
                continue
            out[str(k)] = str(v)

        return out

    @property
    def cursor(self) -> Any:
        return _json_validate(
            _mget(self._m, CTX_CURSOR, None),
            path="cursor",
        )

    @property
    def kind(self) -> Any:
        return _json_validate(
            _mget(self._m, CTX_KIND, None),
            path="kind",
        )

    def __getitem__(self, key: str) -> Any:
        if key == CTX_FRAMES:
            return self.frames
        if key == CTX_CURRENT_SPAN:
            return self.current_span
        if key == CTX_SPAN_ORDER:
            return self.span_order
        if key == CTX_SPAN_TO_DATUM_WIDGETS:
            return self.span_to_datum_widgets
        if key == CTX_DATUM_WIDGET_DECLS:
            return self.datum_widget_decls
        if key == CTX_DATUM_WIDGET_FILLS:
            return self.datum_widget_fills
        if key == CTX_DATUM_WIDGETS_ON_THIS_SPAN:
            return self.datum_widgets_on_this_span
        if key == CTX_DATUM_STATES_ON_THIS_SPAN:
            return self.datum_states_on_this_span
        if key == CTX_SESSION_METADATA:
            return self.session_metadata
        if key == CTX_LAST_ERROR:
            return self.last_error
        if key == CTX_CURSOR:
            return self.cursor
        if key == CTX_KIND:
            return self.kind

        if key == CTX_SESSION_ID:
            return self.session_id
        if key == CTX_FORM_ID:
            return self.form_id
        if key == CTX_APP_FORM_ID:
            return self.app_form_id
        if key == CTX_CURRENT_FRAME_ID:
            return self.current_frame_id
        if key == CTX_CURRENT_FRAME_NAME:
            return self.current_frame_name
        if key == CTX_CURRENT_SPAN_ID:
            return self.current_span_id
        if key == CTX_GLOBALS:
            return self.globals
        if key == CTX_STEP:
            return self.step
        if key == CTX_STATE:
            return self.state
        if key == CTX_MULTIFRAMESPEC:
            return self.multiframespec
        if key == CTX_TAGS:
            return self.tags

        if key == CTX_ROLE_MISMATCH_MODULATION_INFO:
            return self.role_mismatch_modulation_info

        return _json_validate(
            _mget(self._m, key),
            path=f"ctx[{key}]",
        )

    def __iter__(self) -> Iterator[str]:
        canon = [
            CTX_FRAMES,
            CTX_CURRENT_SPAN,
            CTX_SPAN_ORDER,
            CTX_SPAN_TO_DATUM_WIDGETS,
            CTX_DATUM_WIDGET_DECLS,
            CTX_DATUM_WIDGET_FILLS,
            CTX_DATUM_WIDGETS_ON_THIS_SPAN,
            CTX_DATUM_STATES_ON_THIS_SPAN,
            CTX_SESSION_METADATA,
            CTX_LAST_ERROR,
            CTX_CURSOR,
            CTX_KIND,
            CTX_SESSION_ID,
            CTX_FORM_ID,
            CTX_APP_FORM_ID,
            CTX_CURRENT_FRAME_ID,
            CTX_CURRENT_FRAME_NAME,
            CTX_CURRENT_SPAN_ID,
            CTX_GLOBALS,
            CTX_STEP,
            CTX_STATE,
            CTX_MULTIFRAMESPEC,
            CTX_TAGS,
            CTX_ROLE_MISMATCH_MODULATION_INFO,
        ]

        yielded = set()
        for k in canon:
            yielded.add(k)
            yield k

        for k in self._m.keys():
            ks = str(k)
            if ks not in yielded:
                yield ks

    def __len__(self) -> int:
        return max(12, len(self._m))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            v = self[key]
            return default if v is None else v
        except Exception:
            return default


def validate_minimal(ctx: Any) -> None:
    """
    Validate the minimum shape needed for UI FORM_FILL rendering.
    """
    view = ctx if isinstance(ctx, UIContextView) else UIContextView(ctx)

    missing: list[str] = []
    if not view.frames:
        missing.append(CTX_FRAMES)
    if not view.span_to_datum_widgets:
        missing.append(CTX_SPAN_TO_DATUM_WIDGETS)
    if not view.span_order:
        missing.append(CTX_SPAN_ORDER)
    if not isinstance(view.datum_widget_decls, Mapping) or not view.datum_widget_decls:
        missing.append(CTX_DATUM_WIDGET_DECLS)
    if not isinstance(view.datum_widget_fills, Mapping):
        missing.append(CTX_DATUM_WIDGET_FILLS)
    if not isinstance(view.datum_widgets_on_this_span, list):
        missing.append(CTX_DATUM_WIDGETS_ON_THIS_SPAN)
    if not isinstance(view.datum_states_on_this_span, list):
        missing.append(CTX_DATUM_STATES_ON_THIS_SPAN)

    if missing:
        raise AssertionError(
            "UI context missing required keys/shape: " + ", ".join(missing)
        )


__all__ = [
    "UIFillSpan",
    "UIFrame",
    "UIFieldDecl",
    "UIDatumState",
    "UIContextContract",
    "UIContextView",
    "validate_minimal",
    "CTX_FRAMES",
    "CTX_CURRENT_SPAN",
    "CTX_SPAN_ORDER",
    "CTX_SPAN_TO_DATUM_WIDGETS",
    "CTX_DATUM_WIDGET_DECLS",
    "CTX_DATUM_WIDGET_FILLS",
    "CTX_DATUM_WIDGETS_ON_THIS_SPAN",
    "CTX_DATUM_STATES_ON_THIS_SPAN",
    "CTX_SESSION_METADATA",
    "CTX_LAST_ERROR",
    "CTX_CURSOR",
    "CTX_KIND",
    "CTX_SESSION_ID",
    "CTX_FORM_ID",
    "CTX_APP_FORM_ID",
    "CTX_CURRENT_FRAME_ID",
    "CTX_CURRENT_FRAME_NAME",
    "CTX_CURRENT_SPAN_ID",
    "CTX_GLOBALS",
    "CTX_STEP",
    "CTX_STATE",
    "CTX_MULTIFRAMESPEC",
    "CTX_TAGS",
    "CTX_ROLE_MISMATCH_MODULATION_INFO",
    "ui_context_contract_sheet_v1",
    "build_ctx_manifest_sheet_v1",
    "build_ctx_navigation_model_v1",
]