from __future__ import annotations

"""
Boutique form stack specs – JSON-typed multiframespec dataclasses
=================================================================

_multiframespec / multiframespec membrane helpers.

Purpose
-------
Keep AppTable engine internals agnostic to the concrete _multiframespec
implementation by centralizing construction, validation, casting,
normalization, and UI-context translation here.

Dependency law
--------------
This module does not depend on legacy session implementations.

App Table consumes plain dead-JSON multiframespec mappings. These dataclasses
provide authoring, canonicalization, and structural-validation boundaries.

Open span-extension law
-----------------------
App Table interprets only these structural span keys:

    id
    owns
    tags

All other dead-JSON span keys are opaque extensions owned by higher layers.
They are preserved without feature-semantic interpretation or validation.

No registry side effects and no global JSON-type registries.
"""

from dataclasses import asdict, is_dataclass
import difflib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from _thinkprogram._iomicrosTM.core.api_fills import (
    build_datum_validator,
    datum_fill_data_meets_its_structural_micros_shell,
)
from _thinkprogram._iomicrosTM.tiny_helpers import (
    JSONShapeBase,
    _is_json_safe,
    _merge_dicts,
    _safe_mapping_dict,
    _safe_str_or_none,
    norm_tags,
    shallow_dc,
)
from __exceptions.engine import FormFillsContractError
from __datomatonTM import (
    KEY_DATUM_LIFECYCLE,
    is_this_datum_automaton_in_satisfied_sink_state,
)
from __multiframespecTM.surface import (
    MultiframeSpec,
    normalize__multiframespec_json,
)
from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_APP_FORM_ID,
    CTX_CURRENT_FRAME_ID,
    CTX_CURRENT_FRAME_NAME,
    CTX_CURRENT_SPAN,
    CTX_CURRENT_SPAN_ID,
    CTX_CURSOR,
    CTX_DATUM_WIDGET_DECLS,
    CTX_DATUM_WIDGET_FILLS,
    CTX_DATUM_WIDGETS_ON_THIS_SPAN,
    CTX_FORM_ID,
    CTX_FRAMES,
    CTX_GLOBALS,
    CTX_KIND,
    CTX_LAST_ERROR,
    CTX_MULTIFRAMESPEC,
    CTX_ROLE_MISMATCH_MODULATION_INFO,
    CTX_SESSION_ID,
    CTX_SESSION_METADATA,
    CTX_SPAN_ORDER,
    CTX_SPAN_TO_DATUM_WIDGETS,
    CTX_STATE,
    CTX_STEP,
    CTX_TAGS,
)

from ._lowering import (
    _collect_datums,
    _collect_frames,
    _collect_spans,
    _datum_content_fields,
    _extract_ui_sheet,
    _lift_style_tokens,
    _micro_spec_value,
    _qualify_span_name,
    _resolve_current_span_name,
    _sealed_micro_renderer_args_v1,
    _span_id_collision_policy,
    _validate_multiframespec_ui_request,
)
from ._prefilling import (
    derive_form_id,
    normalize_prefill_validation_directive,
    validate_and_normalize_prefills,
    validate_prefill_addressing_only,
)

from __multiframespecTM.surface import MultiframeSpec


# =============================================================================
# Public _multiframespec constructors / adapters
# =============================================================================


def cast_to__multiframespec(obj: Any) -> "MultiframeSpec":
    """
    Coerce an engine-facing multiframespec object into a validated
    _multiframespec.

    Accepts:
      - _multiframespec
      - Mapping/dict

    Raises:
      - ValueError when obj is None
      - TypeError for unsupported input types
      - whatever _multiframespec._validate() raises for invalid structure
    """
    if obj is None:
        raise ValueError("_multiframespec cannot be None")

    if isinstance(obj, MultiframeSpec):
        fs = obj
    elif isinstance(obj, Mapping):
        fs = MultiframeSpec(**dict(obj))
    else:
        raise TypeError(
            "_multiframespec must be dict/_multiframespec; "
            f"got {type(obj).__name__}"
        )

    fs._validate()
    return fs


def cast__multiframespec_to_dict(
    multiframespec: Any,
    *,
    public_step_name: Optional[str] = None,
    app_public_step_name: Optional[str] = None,
    datums_responsibility: Optional[Mapping[str, Mapping[str, Any]]] = None,
    _multiframespec_obj: Any = None,
) -> Dict[str, Any]:
    """
    Cast a validated _multiframespec object to the canonical kernel-facing dict.

    With a public step name, derive ``app_form_id`` and normalize the result for
    kernel consumption.

    ``app_public_step_name`` is an engine/app-step alias.

    ``_multiframespec_obj`` selects the source object used for form-id
    derivation.
    """
    step_name = public_step_name
    if step_name is None:
        step_name = app_public_step_name

    if isinstance(multiframespec, Mapping):
        fs_dict: Dict[str, Any] = dict(multiframespec)
    elif is_dataclass(multiframespec):
        fs_dict = dict(asdict(multiframespec))
    elif hasattr(multiframespec, "model_dump"):
        fs_dict = dict(multiframespec.model_dump())
    elif hasattr(multiframespec, "dict"):
        fs_dict = dict(multiframespec.dict())
    else:
        raise TypeError(
            "_multiframespec must be mapping/dataclass/pydantic-like; "
            f"got {type(multiframespec).__name__}"
        )

    if step_name is None:
        return fs_dict

    source_obj = _multiframespec_obj
    if source_obj is None:
        source_obj = multiframespec

    form_id = derive_form_id(
        app_public_step_name=str(step_name),
        _multiframespec_obj=source_obj,
    )

    fs_dict["app_form_id"] = form_id

    return validate_and_normalize_multiframespec_for_kernel(
        multiframespec=fs_dict,
        public_step_name=str(step_name),
        datums_responsibility=datums_responsibility,
    )


def validate_and_normalize_multiframespec_for_kernel(
    *,
    multiframespec: Any,
    public_step_name: str,
    datums_responsibility: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
) -> Dict[str, Any]:
    """Normalize an engine-facing multiframespec."""
    multiframespec_dict: Dict[str, Any] = dict(multiframespec or {})

    multiframespec_dict.setdefault("app_form_id", str(public_step_name))

    multiframespec_dict = _ensure_frame_and_span_ids(
        multiframespec_dict,
        public_step_name=str(public_step_name),
    )
    multiframespec_dict = _normalize_role_aliases_for_kernel(
        multiframespec=multiframespec_dict,
    )

    _validate_mapping_fill_micro_keys(
        multiframespec=multiframespec_dict,
        public_step_name=str(public_step_name),
    )

    multiframespec_dict = _ensure_datums_cover_fills(
        multiframespec=multiframespec_dict,
        public_step_name=str(public_step_name),
        datums_responsibility=datums_responsibility,
    )

    return multiframespec_dict


def coerce_and_validate_multiframespec(
    multiframespec: Any,
) -> Optional["MultiframeSpec"]:
    """
    Coerce a multiframespec object into a validated _multiframespec.

    Engine state may still store the resulting structure as plain JSON.
    """
    if multiframespec is None:
        return None

    return cast_to__multiframespec(multiframespec)


def translate__multiframespec_to_ui_context(
    _multiframespec_like: Any,
    request: Mapping[str, Any],
    *,
    renderer_config_cls: Any = None,
) -> Dict[str, Any]:
    """
    Adapt _multiframespec and request state into a dict-only UI context.

    Contract:
      - _multiframespec_like is already a Mapping/dict
      - output is JSON-safe and dict-only
      - role mismatch state uses the universal UI-context carrier
    """
    _validate_multiframespec_ui_request(request)

    readonly = bool(request.get("readonly", False))

    if not isinstance(_multiframespec_like, Mapping):
        raise TypeError(
            "translate__multiframespec_to_ui_context requires Mapping/dict "
            f"_multiframespec; got {type(_multiframespec_like)!r}"
        )

    spec = normalize__multiframespec_json(dict(_multiframespec_like))
    frames = _collect_frames(spec)
    datums = _collect_datums(spec)

    frame_by_id = {
        str(fr.get("id")): fr
        for fr in frames
        if fr.get("id") is not None
    }
    datum_by_id = {
        str(d.get("id")): d
        for d in datums
        if d.get("id") is not None
    }

    req_frame_id = str(request["frame_id"])
    if req_frame_id not in frame_by_id:
        raise KeyError(
            "translate__multiframespec_to_ui_context: "
            f"frame_id {req_frame_id!r} not found"
        )

    qualify, _raw_span_ids = _span_id_collision_policy(frames)

    span_order: List[str] = []
    span_to_datum_widgets: Dict[str, List[str]] = {}
    span_owner_frame: Dict[str, str] = {}

    for fr in frames:
        fid = str(fr.get("id") or "")
        for sp in _collect_spans(fr):
            sid = str(sp.get("id") or "")
            if not sid:
                continue

            ui_span = _qualify_span_name(fid, sid, qualify=qualify)

            owns = sp.get("owns") or []
            if not isinstance(owns, list):
                raise TypeError("Span.owns must be a list")

            owns_ids = [str(x) for x in owns if x is not None]
            span_order.append(ui_span)
            span_to_datum_widgets[ui_span] = owns_ids
            span_owner_frame[ui_span] = fid

    current_span_name: Optional[str]
    if readonly:
        current_span_name = None
        active_frame_id = req_frame_id
    else:
        req_span_id_raw = str(request["span_id"])
        current_span_name = _resolve_current_span_name(
            request_frame_id=req_frame_id,
            request_span_id=req_span_id_raw,
            qualify=qualify,
        )

        if current_span_name not in span_to_datum_widgets:
            raise KeyError(
                "translate__multiframespec_to_ui_context: "
                f"span_id {req_span_id_raw!r} not found"
            )

        active_frame_id = span_owner_frame.get(current_span_name, req_frame_id)

    datum_args_overrides = request.get("datum_args_overrides") or {}
    micro_args_overrides = request.get("micro_args_overrides") or {}

    ui_frames: List[Dict[str, Any]] = []
    for fr in frames:
        fid = str(fr.get("id") or "")
        spans = _collect_spans(fr)

        field_ids: List[str] = []
        seen_fields: Set[str] = set()

        for sp in spans:
            owns = sp.get("owns") or []
            if not isinstance(owns, list):
                raise TypeError("Span.owns must be a list")

            for o in owns:
                if o is None:
                    continue

                s = str(o)
                if s not in seen_fields:
                    seen_fields.add(s)
                    field_ids.append(s)

        ui_frame = {
            "name": fid,
            "id": fid,
            "fillspans": [
                {
                    "name": _qualify_span_name(
                        fid,
                        str(sp.get("id") or ""),
                        qualify=qualify,
                    )
                }
                for sp in spans
                if sp.get("id") is not None
            ],
            "field_ids": field_ids,
        }
        ui_frames.append(ui_frame)

    datum_to_spans: Dict[str, List[str]] = {}
    for sp_name, owns in span_to_datum_widgets.items():
        for did in owns:
            datum_to_spans.setdefault(did, []).append(sp_name)

    datum_widget_decls: Dict[str, Dict[str, Any]] = {}
    for did, d in datum_by_id.items():
        micros = d.get("micros") or []
        if not isinstance(micros, list):
            raise TypeError("Datum.micros must be a list")

        d_structure = (
            {"structure": d.get("structure")}
            if d.get("structure") is not None
            else {}
        )
        d_content = _datum_content_fields(d)

        micro_specs: List[Dict[str, Any]] = []
        micro_names: List[str] = []

        for m in micros:
            if not isinstance(m, dict):
                continue

            mname = str(m.get("name") or "value")
            micro_names.append(mname)

            m_style = m.get("style") if isinstance(m.get("style"), dict) else {}
            sealed_renderer_args = _sealed_micro_renderer_args_v1(m)

            ms = {
                "name": mname,
                "type": str(m.get("type") or "text"),
                "required": m.get("required"),
                "placeholder": _micro_spec_value(m, "placeholder"),
                "options": _micro_spec_value(m, "options"),
                "validators": _micro_spec_value(m, "validators"),
            }

            ms = _merge_dicts(ms, sealed_renderer_args)

            if (
                isinstance(micro_args_overrides, dict)
                and did in micro_args_overrides
                and isinstance(micro_args_overrides[did], dict)
                and mname in micro_args_overrides[did]
                and isinstance(micro_args_overrides[did][mname], dict)
            ):
                ms = _merge_dicts(ms, micro_args_overrides[did][mname])

            if m_style:
                ms["style"] = dict(m_style)

            ms = _merge_dicts(ms)
            ms = {k: v for k, v in ms.items() if v is not None}
            micro_specs.append(ms)

        datum_args = _merge_dicts(
            {
                "id": did,
                "micro_input_fields": micro_specs,
            },
            d_content,
            d_structure,
        )

        if (
            isinstance(datum_args_overrides, dict)
            and did in datum_args_overrides
            and isinstance(datum_args_overrides[did], dict)
        ):
            datum_args = _merge_dicts(datum_args, datum_args_overrides[did])

        spans_for_datum = datum_to_spans.get(did, [])
        if len(spans_for_datum) == 1:
            fillspan_name: Optional[str] = spans_for_datum[0]
        else:
            fillspan_name = None

        datum_widget_decls[did] = {
            "field_id": did,
            "fillspan_name": fillspan_name,
            "datum_args": datum_args,
            "micros": micro_names,
        }

    datum_widget_fills = request.get("datum_widget_fills") or {}
    if not isinstance(datum_widget_fills, dict):
        raise TypeError(
            "multiframespecUIRequest.datum_widget_fills must be dict if provided"
        )

    if readonly:
        datum_widgets_on_this_span: List[str] = []
    else:
        pending = request.get("datum_widgets_on_this_span", None)
        if pending is None:
            datum_widgets_on_this_span = list(
                span_to_datum_widgets.get(str(current_span_name), [])
            )
        else:
            datum_widgets_on_this_span = [
                str(x)
                for x in (pending or [])
                if x is not None
            ]

    kind_default = "READONLY" if readonly else "MANUALFILLNEEDEDSTEP"

    ui_sheet = _extract_ui_sheet(spec)
    sheet_sm = ui_sheet.get("session_metadata")
    sheet_sm_map: Dict[str, Any] = (
        dict(sheet_sm)
        if isinstance(sheet_sm, Mapping)
        else {}
    )

    req_sm = request.get("session_metadata") or {}
    if req_sm is not None and not isinstance(req_sm, dict):
        raise TypeError(
            "multiframespecUIRequest.session_metadata must be dict if provided"
        )

    merged_session_metadata = dict(req_sm or {})
    merged_session_metadata.update(sheet_sm_map)

    current_frame_name = (
        _safe_str_or_none(request.get("current_frame_name"))
        or active_frame_id
    )
    app_form_id = (
        _safe_str_or_none(request.get("app_form_id"))
        or _safe_str_or_none(spec.get("app_form_id"))
    )
    form_id = _safe_str_or_none(request.get("form_id")) or app_form_id

    globals_map = _safe_mapping_dict(request.get("globals"))
    step_map = (
        _safe_mapping_dict(request.get("step"))
        or _safe_mapping_dict(merged_session_metadata.get("step"))
    )
    state_map = (
        _safe_mapping_dict(request.get("state"))
        or _safe_mapping_dict(merged_session_metadata.get("state"))
    )

    tags_raw = request.get("tags", merged_session_metadata.get("tags", []))
    tags = [str(x) for x in tags_raw] if isinstance(tags_raw, list) else []

    ctx: Dict[str, Any] = {
        CTX_FRAMES: ui_frames,
        CTX_CURRENT_SPAN: current_span_name,
        CTX_SPAN_ORDER: span_order,
        CTX_SPAN_TO_DATUM_WIDGETS: span_to_datum_widgets,
        CTX_DATUM_WIDGET_DECLS: datum_widget_decls,
        CTX_DATUM_WIDGET_FILLS: datum_widget_fills,
        CTX_DATUM_WIDGETS_ON_THIS_SPAN: datum_widgets_on_this_span,
        CTX_SESSION_METADATA: merged_session_metadata,
        CTX_LAST_ERROR: request.get("last_error"),
        CTX_CURSOR: request.get("cursor"),
        CTX_KIND: request.get("kind") or kind_default,
        CTX_SESSION_ID: _safe_str_or_none(request.get("session_id")),
        CTX_FORM_ID: form_id,
        CTX_APP_FORM_ID: app_form_id,
        CTX_CURRENT_FRAME_ID: (
            _safe_str_or_none(request.get("current_frame_id"))
            or active_frame_id
        ),
        CTX_CURRENT_FRAME_NAME: current_frame_name,
        CTX_CURRENT_SPAN_ID: current_span_name,
        CTX_GLOBALS: globals_map,
        CTX_STEP: step_map,
        CTX_STATE: state_map,
        CTX_MULTIFRAMESPEC: spec,
        CTX_TAGS: tags,
        CTX_ROLE_MISMATCH_MODULATION_INFO: None,
    }

    if not _is_json_safe(ctx):
        raise TypeError(
            "translate__multiframespec_to_ui_context produced non-JSON-safe output "
            "(dict-only contract violation)."
        )

    return ctx


# =============================================================================
# Private canonical _multiframespec normalization helpers
# =============================================================================


def _ensure_frame_and_span_ids(
    multiframespec: Mapping[str, Any],
    *,
    public_step_name: str,
) -> Dict[str, Any]:
    """
    Ensure canonical ids exist for frames and spans and remove id aliases.
    """
    fs = dict(multiframespec or {})

    frames = fs.get("frames")
    if isinstance(frames, tuple):
        frames = list(frames)

    if not isinstance(frames, list):
        return fs

    for frame_index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            continue

        frame_dict = dict(frame)

        frame_id = frame_dict.get("id")
        if not isinstance(frame_id, str) or not frame_id.strip():
            alias = frame_dict.get("frame_id")
            if isinstance(alias, str) and alias.strip():
                frame_dict["id"] = alias.strip()
            else:
                frame_dict["id"] = (
                    f"{public_step_name}.frame.{frame_index + 1}"
                )

        frame_dict.pop("frame_id", None)

        spans = frame_dict.get("spans")
        if isinstance(spans, tuple):
            spans = list(spans)

        if isinstance(spans, list):
            new_spans = []

            for span_index, span in enumerate(spans):
                if not isinstance(span, Mapping):
                    new_spans.append(span)
                    continue

                span_dict = dict(span)

                span_id = span_dict.get("id")
                if not isinstance(span_id, str) or not span_id.strip():
                    alias = span_dict.get("span_id")
                    if isinstance(alias, str) and alias.strip():
                        span_dict["id"] = alias.strip()
                    else:
                        span_dict["id"] = (
                            f"{frame_dict['id']}.span.{span_index + 1}"
                        )

                span_dict.pop("span_id", None)
                new_spans.append(span_dict)

            frame_dict["spans"] = new_spans

        frames[frame_index] = frame_dict

    fs["frames"] = frames
    return fs


def _normalize_role_aliases_for_kernel(
    *,
    multiframespec: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Normalize role assignment.

    Law:
      - scalar role maps to roles=[role]
      - roles is the plural carrier
      - span.roles are defaults
      - datum.roles override span.roles at the role-interaction layer
      - App Table treats role keys as opaque dead-JSON extensions
    """
    fs: Dict[str, Any] = dict(multiframespec or {})

    def _roles_list(raw_roles: Any, raw_role: Any) -> list[str]:
        values: list[Any] = []

        if raw_roles is not None:
            if isinstance(raw_roles, str):
                values.append(raw_roles)
            elif isinstance(raw_roles, (list, tuple, set)):
                values.extend(list(raw_roles))
            else:
                values.append(raw_roles)
        elif raw_role is not None:
            values.append(raw_role)

        out: list[str] = []
        seen: set[str] = set()

        for value in values:
            role = str(value or "").strip()
            if not role or role in seen:
                continue
            seen.add(role)
            out.append(role)

        return out

    datums = fs.get("datums")
    if isinstance(datums, list):
        new_datums: list[Any] = []

        for datum in datums:
            if not isinstance(datum, Mapping):
                new_datums.append(datum)
                continue

            datum_dict = dict(datum)
            roles = _roles_list(
                datum_dict.get("roles"),
                datum_dict.get("role"),
            )

            if roles:
                datum_dict["roles"] = roles
                datum_dict.setdefault("role", roles[0])
            else:
                datum_dict.pop("roles", None)

            new_datums.append(datum_dict)

        fs["datums"] = new_datums

    frames = fs.get("frames")
    if isinstance(frames, list):
        new_frames: list[Any] = []

        for frame in frames:
            if not isinstance(frame, Mapping):
                new_frames.append(frame)
                continue

            frame_dict = dict(frame)
            spans = frame_dict.get("spans")

            if isinstance(spans, list):
                new_spans: list[Any] = []

                for span in spans:
                    if not isinstance(span, Mapping):
                        new_spans.append(span)
                        continue

                    span_dict = dict(span)
                    roles = _roles_list(
                        span_dict.get("roles"),
                        span_dict.get("role"),
                    )

                    if roles:
                        span_dict["roles"] = roles
                        span_dict.setdefault("role", roles[0])
                    else:
                        span_dict.pop("roles", None)

                    new_spans.append(span_dict)

                frame_dict["spans"] = new_spans

            new_frames.append(frame_dict)

        fs["frames"] = new_frames

    return fs


def _datum_micro_names(datum: Mapping[str, Any]) -> set[str]:
    micros = datum.get("micros") or []
    names: set[str] = set()

    if isinstance(micros, list):
        for micro in micros:
            if not isinstance(micro, Mapping):
                continue

            raw_name = micro.get("name")
            name = (
                "value"
                if raw_name is None or not str(raw_name).strip()
                else str(raw_name).strip()
            )
            names.add(name)

    if not names:
        names.add("value")

    return names


def _validate_mapping_fill_micro_keys(
    *,
    multiframespec: Mapping[str, Any],
    public_step_name: str,
) -> None:
    """
    Require mapping fill keys to name micros declared by the target datum.
    """
    fs = dict(multiframespec or {})

    fills = fs.get("fills")
    if not isinstance(fills, Mapping):
        return

    datums = fs.get("datums")
    if datums is None:
        datums_list: list[Any] = []
    elif isinstance(datums, list):
        datums_list = list(datums)
    elif isinstance(datums, tuple):
        datums_list = list(datums)
    else:
        raise TypeError(
            f"{public_step_name}: "
            "multiframespec['datums'] must be a list if provided"
        )

    datums_by_id: Dict[str, Mapping[str, Any]] = {}
    for datum in datums_list:
        if not isinstance(datum, Mapping):
            continue

        datum_id = datum.get("id")
        if isinstance(datum_id, str) and datum_id.strip():
            datums_by_id[datum_id.strip()] = datum

    for raw_datum_id, value in fills.items():
        datum_id = str(raw_datum_id)
        datum = datums_by_id.get(datum_id)

        if datum is None:
            continue

        if not isinstance(value, Mapping):
            continue

        allowed_micro_names = _datum_micro_names(datum)

        for raw_micro_key in value.keys():
            micro_key = str(raw_micro_key)

            if micro_key not in allowed_micro_names:
                raise FormFillsContractError(
                    f"{public_step_name}: "
                    f"multiframespec['fills'][{datum_id!r}] uses "
                    f"unknown micro key {micro_key!r}; "
                    f"allowed micros: {sorted(allowed_micro_names)}"
                )


def _ensure_datums_cover_fills(
    *,
    multiframespec: Mapping[str, Any],
    public_step_name: str,
    datums_responsibility: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
) -> Dict[str, Any]:
    """
    Require every fill datum id to be declared by the multiframespec.

    Datum declarations may be supplied explicitly through
    ``datums_responsibility``.
    """
    fs: Dict[str, Any] = dict(multiframespec or {})

    fills = fs.get("fills")
    if fills is None:
        return fs

    if not isinstance(fills, Mapping):
        raise TypeError(
            f"{public_step_name}: "
            "multiframespec['fills'] must be a mapping if provided"
        )

    datums = fs.get("datums")
    if datums is None:
        datums_list: list[Any] = []
    elif isinstance(datums, tuple):
        datums_list = list(datums)
    elif isinstance(datums, list):
        datums_list = list(datums)
    else:
        raise TypeError(
            f"{public_step_name}: "
            "multiframespec['datums'] must be a list if provided"
        )

    declared_ids: set[str] = set()
    for datum in datums_list:
        if not isinstance(datum, Mapping):
            continue

        datum_id = datum.get("id")
        if isinstance(datum_id, str) and datum_id.strip():
            declared_ids.add(datum_id.strip())

    missing = [
        str(datum_id)
        for datum_id in fills.keys()
        if str(datum_id) not in declared_ids
    ]

    if not missing:
        return fs

    prepared_by_id: Dict[str, Dict[str, Any]] = {}
    if datums_responsibility is not None:
        for datum_id, datum in datums_responsibility.items():
            if (
                isinstance(datum_id, str)
                and datum_id.strip()
                and isinstance(datum, Mapping)
            ):
                prepared_by_id[datum_id.strip()] = dict(datum)

    for datum_id in list(missing):
        prepared = prepared_by_id.get(datum_id)
        if prepared is None:
            continue

        declaration = {
            "id": str(
                prepared.get("id")
                or prepared.get("datum_id")
                or datum_id
            ),
            "title": str(prepared.get("title") or datum_id),
            "micros": list(prepared.get("micros") or []),
        }

        datums_list.append(declaration)
        declared_ids.add(datum_id)

    remaining = [
        str(datum_id)
        for datum_id in fills.keys()
        if str(datum_id) not in declared_ids
    ]

    if remaining:
        raise FormFillsContractError(
            f"{public_step_name}: "
            "multiframespec['fills'] references unknown datum id(s): "
            f"{sorted(remaining)!r}. "
            "Declare these in multiframespec['datums'] "
            "(recommended) or pass datums_responsibility explicitly "
            "(opt-in)."
        )

    fs["datums"] = datums_list
    return fs


# =============================================================================
# Authoring helper utilities
# =============================================================================


def nearest(name: str, pool: set[str]) -> List[str]:
    return difflib.get_close_matches(name, sorted(pool), n=5, cutoff=0.6)


# =============================================================================
# Pure multiframespec structure helpers
# =============================================================================


_SPAN_AUTHORITATIVE_DATUM_KEYS = (
    "my_authoritative_datums",
    "authoritative_datums",
    "authoritative_owns",
    "authoritative",
)


def collect_multiframespec_datum_ids(
    multiframespec: Mapping[str, Any],
) -> set[str]:
    """Return datum ids declared by ``multiframespec['datums']``."""
    out: set[str] = set()

    datums = multiframespec.get("datums") or []
    if not isinstance(datums, list):
        return out

    for datum in datums:
        if not isinstance(datum, Mapping):
            continue

        datum_id = str(datum.get("id") or "").strip()
        if datum_id:
            out.add(datum_id)

    return out


def resolve_multiframespec_span_authoritative_datum_ids(
    span: Mapping[str, Any],
) -> List[str]:
    """
    Return datum ids controlling span satisfaction.

    An absent authoritative declaration means all owned datums.
    A declared set must be a non-empty subset of ``owns``.
    """
    owns_norm = [
        str(item).strip()
        for item in list(span.get("owns") or [])
        if str(item or "").strip()
    ]
    owns_set = set(owns_norm)

    raw_value = None
    found = False
    for key in _SPAN_AUTHORITATIVE_DATUM_KEYS:
        if key in span:
            raw_value = span.get(key)
            found = True
            break

    if not found:
        return owns_norm

    if isinstance(raw_value, str):
        raw_ids = [raw_value]
    elif isinstance(raw_value, Sequence) and not isinstance(
        raw_value,
        (str, bytes, bytearray),
    ):
        raw_ids = list(raw_value)
    else:
        raise ValueError(
            "span authoritative datums must be a non-empty list of owned datum ids"
        )

    out: List[str] = []
    seen: set[str] = set()

    for raw in raw_ids:
        datum_id = str(raw or "").strip()
        if not datum_id:
            continue

        if datum_id not in owns_set:
            raise ValueError(
                "span authoritative datum must be owned by the span: "
                f"{datum_id!r} not in {owns_norm!r}"
            )

        if datum_id in seen:
            continue

        seen.add(datum_id)
        out.append(datum_id)

    if not out:
        raise ValueError(
            "span authoritative datums must be non-empty when declared"
        )

    return out


def collect_multiframespec_span_records(
    multiframespec: Mapping[str, Any],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Return normalized span records keyed by ``(frame_id, span_id)``."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for frame in list(multiframespec.get("frames") or []):
        if not isinstance(frame, Mapping):
            continue

        frame_id = str(frame.get("id") or frame.get("name") or "").strip()
        if not frame_id:
            continue

        for span in list(frame.get("spans") or []):
            if not isinstance(span, Mapping):
                continue

            span_id = str(span.get("id") or span.get("name") or "").strip()
            if not span_id:
                continue

            owns = [
                str(item).strip()
                for item in list(span.get("owns") or [])
                if str(item or "").strip()
            ]

            authoritative = resolve_multiframespec_span_authoritative_datum_ids(
                span,
            )

            out[(frame_id, span_id)] = {
                "frame_id": frame_id,
                "span_id": span_id,
                "span": dict(span),
                "owns": owns,
                "authoritative": authoritative,
            }

    return out


def choose_multiframespec_initial_span_target(
    *,
    multiframespec: Mapping[str, Any],
    preferred_frame_id: Optional[str] = None,
    preferred_span_id: Optional[str] = None,
    preferred_datum_ids: Optional[Tuple[str, ...]] = None,
) -> Tuple[str, str, Tuple[str, ...]]:
    """Return a valid frame/span/target-datum triple."""
    frames_raw = multiframespec.get("frames") or ()
    frames = [frame for frame in frames_raw if isinstance(frame, Mapping)]
    if not frames:
        raise ValueError(
            "Cannot choose multiframespec initial span target: "
            "multiframespec has no frames"
        )

    def _frame_id(frame: Mapping[str, Any]) -> str:
        return str(frame.get("id") or frame.get("name") or "").strip()

    def _span_id(span: Mapping[str, Any]) -> str:
        return str(span.get("id") or span.get("name") or "").strip()

    chosen_frame: Optional[Mapping[str, Any]] = None
    preferred_frame_id_norm = str(preferred_frame_id or "").strip()

    if preferred_frame_id_norm:
        for frame in frames:
            if _frame_id(frame) == preferred_frame_id_norm:
                chosen_frame = frame
                break

    if chosen_frame is None:
        for frame in frames:
            if _frame_id(frame):
                chosen_frame = frame
                break

    if chosen_frame is None:
        raise ValueError(
            "Cannot choose multiframespec initial span target: "
            "no frame has a non-empty id/name"
        )

    frame_id = _frame_id(chosen_frame)

    spans_raw = chosen_frame.get("spans") or ()
    spans = [span for span in spans_raw if isinstance(span, Mapping)]

    chosen_span: Optional[Mapping[str, Any]] = None
    preferred_span_id_norm = str(preferred_span_id or "").strip()

    if preferred_span_id_norm:
        for span in spans:
            if _span_id(span) == preferred_span_id_norm:
                chosen_span = span
                break

    if chosen_span is None:
        for span in spans:
            if _span_id(span):
                chosen_span = span
                break

    if chosen_span is None:
        for frame in frames:
            candidate_frame_id = _frame_id(frame)
            if not candidate_frame_id:
                continue

            for span in frame.get("spans") or ():
                if isinstance(span, Mapping) and _span_id(span):
                    chosen_frame = frame
                    chosen_span = span
                    frame_id = candidate_frame_id
                    break

            if chosen_span is not None:
                break

    if chosen_span is None:
        raise ValueError(
            "Cannot choose multiframespec initial span target: "
            "no span has a non-empty id/name"
        )

    span_id = _span_id(chosen_span)

    if preferred_datum_ids:
        target_datum_ids = tuple(
            str(item).strip()
            for item in preferred_datum_ids
            if str(item).strip()
        )
    else:
        owns = (
            chosen_span.get("owns")
            or chosen_span.get("fields")
            or chosen_span.get("fields_responsible_for")
            or ()
        )
        target_datum_ids = tuple(
            str(item).strip()
            for item in owns
            if str(item).strip()
        )

    return frame_id, span_id, target_datum_ids


def resolve_multiframespec_frame(
    *,
    multiframespec: Mapping[str, Any],
    frame_id: Any,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Resolve a frame id against ``multiframespec['frames']``."""
    frame_id_norm = str(frame_id or "").strip()
    if not frame_id_norm:
        return None, None, {}

    frames = multiframespec.get("frames")
    if not isinstance(frames, list):
        return frame_id_norm, None, {}

    for frame in frames:
        if not isinstance(frame, Mapping):
            continue

        candidate_frame_id = str(
            frame.get("id") or frame.get("name") or ""
        ).strip()
        if candidate_frame_id != frame_id_norm:
            continue

        return (
            candidate_frame_id,
            str(
                frame.get("name")
                or frame.get("title")
                or candidate_frame_id
            ),
            dict(frame),
        )

    return frame_id_norm, None, {}


# =============================================================================
# Multiframespec-scoped fill values and fillspan planning
# =============================================================================


def build_multiframespec_scoped_datum_fill_map(
    *,
    multiframespec: Mapping[str, Any],
    external_prefills_by_datum_id: Mapping[str, Any],
    external_fills_by_datum_id: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Build fill values scoped to datums declared by a multiframespec.

    Merge order:
      1. multiframespec-local fills
      2. external prefills
      3. external fills
    """
    datum_ids = collect_multiframespec_datum_ids(multiframespec)

    out: Dict[str, Any] = {}

    local_fills = multiframespec.get("fills")
    if isinstance(local_fills, Mapping):
        for raw_datum_id, value in local_fills.items():
            datum_id = str(raw_datum_id)
            if not datum_ids or datum_id in datum_ids:
                out[datum_id] = value

    for raw_datum_id, value in dict(
        external_prefills_by_datum_id or {}
    ).items():
        datum_id = str(raw_datum_id)
        if datum_id in datum_ids:
            if (
                datum_id in out
                and isinstance(out.get(datum_id), Mapping)
                and isinstance(value, Mapping)
            ):
                merged = dict(out.get(datum_id) or {})
                merged.update(dict(value))
                out[datum_id] = merged
            else:
                out[datum_id] = value

    for raw_datum_id, value in dict(
        external_fills_by_datum_id or {}
    ).items():
        datum_id = str(raw_datum_id)
        if datum_id in datum_ids:
            if (
                datum_id in out
                and isinstance(out.get(datum_id), Mapping)
                and isinstance(value, Mapping)
            ):
                merged = dict(out.get(datum_id) or {})
                merged.update(dict(value))
                out[datum_id] = merged
            else:
                out[datum_id] = value

    return out


def plan_multiframespec_fillspan_steps(
    *,
    multiframespec: Mapping[str, Any],
    existing_fill_values_by_datum_id: Mapping[str, Any],
    datum_lifecycle_state: Optional[Mapping[str, Any]] = None,
    form_id: str = "",
) -> List[Dict[str, Any]]:
    """Compute MANUAL fillspan step payloads required by a multiframespec."""
    fs = cast_to__multiframespec(multiframespec)

    effective_fill_values_by_datum_id: Dict[str, Any] = {}
    if isinstance(multiframespec.get("fills"), Mapping):
        effective_fill_values_by_datum_id.update(
            dict(multiframespec.get("fills") or {})
        )

    for datum_id, macro_fill in dict(
        existing_fill_values_by_datum_id or {}
    ).items():
        key = str(datum_id)
        if (
            key in effective_fill_values_by_datum_id
            and isinstance(effective_fill_values_by_datum_id.get(key), Mapping)
            and isinstance(macro_fill, Mapping)
        ):
            merged = dict(effective_fill_values_by_datum_id.get(key) or {})
            merged.update(dict(macro_fill or {}))
            effective_fill_values_by_datum_id[key] = merged
        else:
            effective_fill_values_by_datum_id[key] = macro_fill

    datums_by_id: Dict[str, Dict[str, Any]] = {}
    for datum in fs.datums or []:
        if isinstance(datum, Mapping):
            datums_by_id[str(datum.get("id"))] = dict(datum)

    inserted_payloads: List[Dict[str, Any]] = []
    span_records = collect_multiframespec_span_records(multiframespec)

    for frame in fs.frames or []:
        if not isinstance(frame, Mapping):
            continue

        frame_id = str(frame.get("id") or frame.get("name") or "").strip()
        if not frame_id:
            continue

        for span in frame.get("spans") or []:
            if not isinstance(span, Mapping):
                continue

            span_id = str(span.get("id") or span.get("name") or "").strip()
            if not span_id:
                continue

            owns = list(span.get("owns") or [])
            span_record = span_records.get((frame_id, span_id), {})
            authoritative = list(
                span_record.get("authoritative")
                or [str(item) for item in owns]
            )

            all_ok = True
            target_datum_ids: List[str] = []

            for raw_datum_id in authoritative:
                datum_id = str(raw_datum_id)
                datum = datums_by_id.get(datum_id)

                if datum is None:
                    all_ok = False
                    target_datum_ids.append(datum_id)
                    continue

                macro_fill = effective_fill_values_by_datum_id.get(
                    datum_id,
                    None,
                )

                if datum_lifecycle_state is not None:
                    if is_this_datum_automaton_in_satisfied_sink_state(
                        state={
                            "_datum_lifecycle_v1": datum_lifecycle_state,
                        },
                        form_id=str(
                            form_id
                            or multiframespec.get("app_form_id")
                            or ""
                        ),
                        datum_id=datum_id,
                    ):
                        continue

                ok = datum_fill_data_meets_its_structural_micros_shell(
                    datum,
                    macro_fill,
                )
                if not ok:
                    all_ok = False
                    target_datum_ids.append(datum_id)

            if all_ok:
                continue

            inserted_payloads.append(
                {
                    "frame_id": frame_id,
                    "span_id": span_id,
                    "span_owns": [str(item) for item in owns],
                    "span_authoritative": [
                        str(item)
                        for item in authoritative
                    ],
                    "datum_widgets_on_this_span": target_datum_ids,
                }
            )

    return inserted_payloads


# =============================================================================
# Datum-level Q/lifecycle fill coercion
# =============================================================================


def coerce_datum_partial_fill_for_datum_widget_explosion(
    datum: Mapping[str, Any],
    partial_fill: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return the semantic partial fill used for Q widget evaluation."""
    out: Dict[str, Any] = dict(partial_fill or {})

    micros = datum.get("micros") or datum.get("micro_input_fields") or []
    if not isinstance(micros, Sequence) or isinstance(
        micros,
        (str, bytes, bytearray),
    ):
        return out

    type_by_name: Dict[str, str] = {}

    for micro in micros:
        if not isinstance(micro, Mapping):
            continue

        name = micro.get("name")
        typ = micro.get("type")

        if name is not None and typ is not None:
            type_by_name[str(name)] = str(typ)

    for key, typ in type_by_name.items():
        if key not in out:
            continue

        val = out[key]

        if typ == "number":
            if val is None or (
                isinstance(val, (int, float))
                and not isinstance(val, bool)
            ):
                continue

            if isinstance(val, str):
                text_value = val.strip()
                if text_value == "":
                    continue

                try:
                    if any(ch in text_value for ch in (".", "e", "E")):
                        out[key] = float(text_value)
                    else:
                        out[key] = int(text_value)
                except ValueError:
                    continue

            continue

        if typ == "bool":
            if isinstance(val, bool) or val is None:
                continue

            if isinstance(val, str):
                text_value = val.strip().lower()

                if text_value in {"true", "t", "yes", "y", "1", "on"}:
                    out[key] = True
                elif text_value in {"false", "f", "no", "n", "0", "off"}:
                    out[key] = False

            continue

        if typ == "text":
            if val is None or isinstance(val, str):
                continue

            if isinstance(val, (int, float, bool)):
                out[key] = str(val)

            continue

    return out


# =============================================================================
# Multiframespec UI lowering and reusable manual-render artifacts
# =============================================================================


def lower_multiframespec_to_ui_context(
    *,
    multiframespec: Mapping[str, Any],
    render_request: Mapping[str, Any],
    include_full_multiframespec: bool = False,
) -> Dict[str, Any]:
    """
    Lower a multiframespec into renderer-agnostic UI context.

    The full multiframespec is omitted unless explicitly requested.
    """
    ui_ctx = translate__multiframespec_to_ui_context(
        multiframespec,
        dict(render_request),
        renderer_config_cls=None,
    )

    def _current_frame_lookup() -> Tuple[
        Optional[str],
        Optional[str],
        Dict[str, Any],
    ]:
        frame_id_req = render_request.get("frame_id")
        frame_id_str = (
            str(frame_id_req).strip()
            if frame_id_req is not None
            else None
        )

        frames = multiframespec.get("frames")
        if not isinstance(frames, list):
            return frame_id_str, None, {}

        for frame in frames:
            if not isinstance(frame, Mapping):
                continue

            frame_id = str(
                frame.get("id") or frame.get("name") or ""
            ).strip()
            if not frame_id:
                continue

            if frame_id_str and frame_id == frame_id_str:
                return (
                    frame_id,
                    str(frame.get("name") or frame.get("title") or frame_id),
                    dict(frame),
                )

        return frame_id_str, None, {}

    frame_id_norm, frame_name_norm, _current_frame_obj = (
        _current_frame_lookup()
    )

    span_id_req = render_request.get("span_id")
    session_id_req = render_request.get("session_id")

    if frame_id_norm is not None:
        ui_ctx[CTX_CURRENT_FRAME_ID] = str(frame_id_norm)

    if frame_name_norm is not None:
        ui_ctx[CTX_CURRENT_FRAME_NAME] = str(frame_name_norm)

    if span_id_req is not None:
        ui_ctx[CTX_CURRENT_SPAN_ID] = str(span_id_req)

    if session_id_req is not None:
        ui_ctx[CTX_SESSION_ID] = str(session_id_req)

    form_id = multiframespec.get("app_form_id")
    if form_id is not None:
        ui_ctx[CTX_APP_FORM_ID] = str(form_id)
        ui_ctx.setdefault(CTX_FORM_ID, str(form_id))

    tags: List[str] = []
    try:
        boxed = multiframespec.get("boxed")
        ui = boxed.get("ui") if isinstance(boxed, Mapping) else None
        raw_tags = ui.get("tags") if isinstance(ui, Mapping) else None

        if isinstance(raw_tags, list):
            tags = [
                str(tag).strip()
                for tag in raw_tags
                if tag is not None and str(tag).strip()
            ]
    except Exception:
        tags = []

    if tags:
        ui_ctx[CTX_TAGS] = list(tags)

        session_metadata = ui_ctx.get("session_metadata")
        session_metadata_out: Dict[str, Any] = (
            dict(session_metadata)
            if isinstance(session_metadata, Mapping)
            else {}
        )

        root_data = session_metadata_out.get("root_data")
        root_data_out: Dict[str, str] = (
            dict(root_data)
            if isinstance(root_data, Mapping)
            else {}
        )

        root_data_out["tags"] = "[" + ",".join(tags) + "]"
        session_metadata_out["root_data"] = root_data_out
        ui_ctx["session_metadata"] = session_metadata_out

    if include_full_multiframespec:
        ui_ctx[CTX_MULTIFRAMESPEC] = dict(multiframespec)
    else:
        ui_ctx.pop(CTX_MULTIFRAMESPEC, None)
        ui_ctx.pop("multiframespec", None)

    return ui_ctx


def compile_multiframespec_manual_render_bundle(
    *,
    multiframespec: Mapping[str, Any],
    form_id: str,
    session_id: Optional[str] = None,
    datum_fill_values: Optional[Mapping[str, Any]] = None,
    frame_id: Optional[str] = None,
    span_id: Optional[str] = None,
    target_datum_ids: Optional[Tuple[str, ...]] = None,
    render_metadata: Optional[Mapping[str, Any]] = None,
    kind: str = "MANUALFILLNEEDEDSTEP",
    include_full_multiframespec: bool = False,
) -> Dict[str, Any]:
    """
    Compile reusable manual-render artifacts from a multiframespec.

    ``base_ui_ctx`` is compact unless the full multiframespec is requested.
    """
    fs = cast_to__multiframespec(multiframespec)

    datums_by_id: Dict[str, Dict[str, Any]] = {}
    validators_by_id: Dict[str, Any] = {}

    for datum in fs.datums or []:
        if not isinstance(datum, Mapping):
            continue

        datum_id = str(datum.get("id") or "").strip()
        if not datum_id:
            continue

        datum_dict = dict(datum)
        datums_by_id[datum_id] = datum_dict

        try:
            validators_by_id[datum_id] = build_datum_validator(datum_dict)
        except Exception:
            validators_by_id[datum_id] = None

    seed_frame_id, seed_span_id, seed_target_datum_ids = (
        choose_multiframespec_initial_span_target(
            multiframespec=multiframespec,
            preferred_frame_id=frame_id,
            preferred_span_id=span_id,
            preferred_datum_ids=target_datum_ids,
        )
    )

    render_request: Dict[str, Any] = {
        "frame_id": seed_frame_id,
        "span_id": seed_span_id,
        "readonly": False,
        "datum_widget_fills": dict(datum_fill_values or {}),
        "datum_widgets_on_this_span": list(seed_target_datum_ids),
        "last_error": None,
        "session_metadata": dict(render_metadata or {}),
        "cursor": {"index": None, "total": None},
        "kind": str(kind),
    }

    if session_id is not None:
        render_request["session_id"] = str(session_id)

    base_ui_ctx = lower_multiframespec_to_ui_context(
        multiframespec=multiframespec,
        render_request=render_request,
        include_full_multiframespec=include_full_multiframespec,
    )

    frames = base_ui_ctx.get("frames")
    span_order = base_ui_ctx.get("span_order")
    span_to_datum_widgets = base_ui_ctx.get("span_to_datum_widgets")
    datum_widget_decls = base_ui_ctx.get("datum_widget_decls")

    return {
        "kind": "manual_io_runtime_cache_v1",
        "form_id": str(form_id),
        "seed_frame_id": seed_frame_id,
        "seed_span_id": seed_span_id,
        "multiframespec_ref": multiframespec,
        "datums_by_id": datums_by_id,
        "validators_by_id": validators_by_id,
        "base_ui_ctx": (
            dict(base_ui_ctx)
            if isinstance(base_ui_ctx, Mapping)
            else {}
        ),
        "frames": (
            list(frames or [])
            if isinstance(frames, list)
            else []
        ),
        "span_order": (
            list(span_order or [])
            if isinstance(span_order, list)
            else []
        ),
        "span_to_datum_widgets": (
            dict(span_to_datum_widgets or {})
            if isinstance(span_to_datum_widgets, Mapping)
            else {}
        ),
        "datum_widget_decls": (
            dict(datum_widget_decls or {})
            if isinstance(datum_widget_decls, Mapping)
            else {}
        ),
    }


def overlay_multiframespec_manual_render_context(
    *,
    render_bundle: Mapping[str, Any],
    multiframespec: Mapping[str, Any],
    render_request: Mapping[str, Any],
    include_full_multiframespec: bool = False,
) -> Dict[str, Any]:
    """
    Build the current manual-render UI context from a compiled render bundle.

    The full multiframespec is omitted unless explicitly requested.
    """
    base = render_bundle.get("base_ui_ctx")
    ui_ctx: Dict[str, Any] = (
        dict(base or {})
        if isinstance(base, Mapping)
        else {}
    )

    frame_id = render_request.get("frame_id")
    span_id = render_request.get("span_id")

    frame_id_norm, frame_name_norm, _current_frame_obj = (
        resolve_multiframespec_frame(
            multiframespec=multiframespec,
            frame_id=frame_id,
        )
    )

    ui_ctx["current_span"] = span_id
    ui_ctx["current_span_id"] = span_id
    ui_ctx[CTX_CURRENT_SPAN_ID] = span_id

    resolved_frame_id = (
        frame_id_norm
        if frame_id_norm is not None
        else frame_id
    )
    ui_ctx["current_frame_id"] = resolved_frame_id
    ui_ctx[CTX_CURRENT_FRAME_ID] = resolved_frame_id

    if frame_name_norm is not None:
        ui_ctx[CTX_CURRENT_FRAME_NAME] = frame_name_norm

    ui_ctx["datum_widgets_on_this_span"] = list(
        render_request.get("datum_widgets_on_this_span") or []
    )
    ui_ctx["datum_widget_fills"] = dict(
        render_request.get("datum_widget_fills") or {}
    )
    ui_ctx["last_error"] = render_request.get("last_error")
    ui_ctx["session_metadata"] = dict(
        render_request.get("session_metadata") or {}
    )
    ui_ctx["cursor"] = dict(render_request.get("cursor") or {})
    ui_ctx["kind"] = render_request.get("kind")

    session_id_req = render_request.get("session_id")
    if session_id_req is not None:
        ui_ctx[CTX_SESSION_ID] = str(session_id_req)

    form_id = multiframespec.get("app_form_id")
    if form_id is not None:
        ui_ctx[CTX_APP_FORM_ID] = str(form_id)
        ui_ctx.setdefault(CTX_FORM_ID, str(form_id))

    if "frames" not in ui_ctx and isinstance(
        render_bundle.get("frames"),
        list,
    ):
        ui_ctx["frames"] = render_bundle.get("frames")

    if "span_order" not in ui_ctx and isinstance(
        render_bundle.get("span_order"),
        list,
    ):
        ui_ctx["span_order"] = render_bundle.get("span_order")

    if "span_to_datum_widgets" not in ui_ctx and isinstance(
        render_bundle.get("span_to_datum_widgets"),
        Mapping,
    ):
        ui_ctx["span_to_datum_widgets"] = render_bundle.get(
            "span_to_datum_widgets"
        )

    if "datum_widget_decls" not in ui_ctx and isinstance(
        render_bundle.get("datum_widget_decls"),
        Mapping,
    ):
        ui_ctx["datum_widget_decls"] = render_bundle.get(
            "datum_widget_decls"
        )

    if include_full_multiframespec:
        ui_ctx[CTX_MULTIFRAMESPEC] = (
            multiframespec
            if isinstance(multiframespec, dict)
            else dict(multiframespec)
        )
    else:
        ui_ctx.pop(CTX_MULTIFRAMESPEC, None)
        ui_ctx.pop("multiframespec", None)

    return ui_ctx


def span_key_v1(
    frame_id: str,
    span_id: str,
) -> str:
    return f"{str(frame_id)}\x1f{str(span_id)}"


__all__ = [
    "MultiframeSpec",
    "cast_to__multiframespec",
    "cast__multiframespec_to_dict",
    "normalize__multiframespec_json",
    "validate_and_normalize_multiframespec_for_kernel",
    "coerce_and_validate_multiframespec",
    "translate__multiframespec_to_ui_context",
    "nearest",
]