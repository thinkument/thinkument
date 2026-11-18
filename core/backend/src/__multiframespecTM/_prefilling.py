from __future__ import annotations

"""
multiframespec Fills / Prefills Policy
================================

multiframespec-specific layer over the generic fills contract.

This module owns:
- multiframespec prefill directive normalization
- multiframespec prefill addressing validation
- multiframespec value-validation policy
- multiframespec indexing / resolver adapters
- form id derivation
- multiframespec-to-multiframespec transfer helper
"""

import difflib
from typing import Any, Dict, Mapping, Optional, Set

from _thinkprogram._iomicrosTM.core.api_prefills import (
    DeadJSONError,
    FillKind,
    FormFillsAPIError,
    FormFillsBundleV1,
    FormFillsContractError,
    FormFillsLayerV1,
    MicroResolver,
    MicroTypeResolution,
    assert_dead_json,
    build_datum_validator,
    datum_micro_names,
    datum_required_micro_names,
    datum_fill_data_meets_its_structural_micros_shell,
    is_blank_value,
    macro_micro_value,
    merge_macro_values,
    parse_and_validate_macro_fill,
    transfer_values_by_ref_map,
    unbox_leaf,
)


def _nearest_id(name: str, pool: Set[str]) -> Optional[str]:
    if not pool:
        return None
    ms = difflib.get_close_matches(name, sorted(pool), n=1, cutoff=0.65)
    return ms[0] if ms else None


def _index_datums(fs: "_multiframespec") -> Dict[str, Dict[str, Any]]:
    """
    Index datums by id from a _multiframespec into plain mapping dicts.
    """
    out: Dict[str, Dict[str, Any]] = {}

    for d in fs.datums or []:
        if isinstance(d, Mapping):
            did = str(d.get("id") or "")
            if did:
                out[did] = dict(d)
        else:
            try:
                did = str(getattr(d, "id", "") or "")
            except Exception:
                did = ""

            if did:
                out[did] = {
                    "id": did,
                    "micros": getattr(d, "micros", []),
                }

    return out


def index_multiframespec(fs: "_multiframespec") -> Dict[str, Dict[str, str]]:
    """
    Return:
      datum_id -> {micro_name -> micro_type}
    """
    out: Dict[str, Dict[str, str]] = {}

    for d in fs.datums or []:
        if not isinstance(d, Mapping):
            continue

        did = str(d.get("id") or "")
        if not did:
            continue

        micro_map: Dict[str, str] = {}
        micros = d.get("micros") or []

        if isinstance(micros, list):
            for m in micros:
                if not isinstance(m, Mapping):
                    continue

                mname = str(m.get("name") or "value")
                mtype = str(m.get("type") or "text").strip().lower() or "text"
                micro_map[mname] = mtype

        if not micro_map:
            micro_map["value"] = "text"

        out[did] = micro_map

    return out


def _multiframespec_resolver_from_index(idx: Dict[str, Dict[str, str]]) -> MicroResolver:
    def _r(sink_id: str, micro_name: str) -> MicroTypeResolution:
        micro_map = idx.get(str(sink_id)) or {}
        if not micro_map:
            return "text"

        mn = str(micro_name or "value")
        return micro_map.get(mn) or micro_map.get("value") or "text"

    return _r


def multiframespec_micro_resolver(fs: "_multiframespec") -> MicroResolver:
    """
    Build a generic MicroResolver from a multiframespec.
    """
    return _multiframespec_resolver_from_index(index_multiframespec(fs))


def form_fills_layer_from_multiframespec(
    raw: Any,
    *,
    kind: FillKind,
    fs: "_multiframespec",
) -> FormFillsLayerV1:
    """
    multiframespec adapter around the generic FormFillsLayerV1 constructor.
    """
    return FormFillsLayerV1.from_any(
        raw,
        kind=kind,
        micro_resolver=multiframespec_micro_resolver(fs),
    )


def form_fills_bundle_from_multiframespec(
    *,
    fs: "_multiframespec",
    prefills: Any = None,
    fills: Any = None,
    prefer_multiframespec_prefills: bool = True,
) -> FormFillsBundleV1:
    """
    multiframespec adapter around the generic FormFillsBundleV1 constructor.

    If prefills is None and prefer_multiframespec_prefills=True, uses fs.fills.
    """
    if prefills is None and prefer_multiframespec_prefills:
        prefills = fs.fills or {}

    return FormFillsBundleV1.from_any(
        prefills=prefills,
        fills=fills,
        micro_resolver=multiframespec_micro_resolver(fs),
    )


def validate_fills_layer_against_multiframespec(
    layer: FormFillsLayerV1,
    *,
    fs: "_multiframespec",
    enforce_micro_lambdas: bool = True,
    enforce_macro_lambdas: bool = True,
    complete_only: bool = False,
) -> None:
    """
    Validate a generic fills layer against multiframespec datum validators.

    complete_only:
      - True: validate only datums satisfied by contract
      - False: validate all datums present in this layer strictly
    """
    idx = {
        str(d.get("id")): d
        for d in (fs.datums or [])
        if isinstance(d, Mapping) and d.get("id") is not None
    }

    for did, bag in (layer.values or {}).items():
        datum = idx.get(did)
        if datum is None:
            raise FormFillsAPIError(f"fills reference unknown datum id {did!r}")

        macro_map: Dict[str, Any] = {}
        for mname, box in (bag or {}).items():
            macro_map[str(mname)] = unbox_leaf(box)

        if complete_only and not datum_fill_data_meets_its_structural_micros_shell(datum, macro_map):
            continue

        parse_and_validate_macro_fill(
            datum=datum,
            raw=dict(macro_map),
            enforce_micro_lambdas=enforce_micro_lambdas,
            enforce_macro_lambdas=enforce_macro_lambdas,
        )


def transfer_values(
    *,
    src_fs: "_multiframespec",
    src: FormFillsBundleV1,
    dst_fs: "_multiframespec",
    dst: Optional[FormFillsBundleV1] = None,
    allow_prefills: bool = True,
    allow_fills: bool = True,
) -> FormFillsBundleV1:
    """
    Transfer values from src -> dst by datum_id + micro_name,
    only when micro types match.
    """
    dst_bundle = dst or form_fills_bundle_from_multiframespec(
        fs=dst_fs,
        prefills=None,
        fills=None,
    )

    src_idx = index_multiframespec(src_fs)
    dst_idx = index_multiframespec(dst_fs)

    def _transfer_layer(
        src_layer: FormFillsLayerV1,
        dst_layer: FormFillsLayerV1,
    ) -> None:
        for did, bag in (src_layer.values or {}).items():
            if did not in src_idx or did not in dst_idx:
                continue

            for mname, box in (bag or {}).items():
                mt_src = src_idx[did].get(
                    mname,
                    src_idx[did].get("value", "text"),
                )
                mt_dst = dst_idx[did].get(
                    mname,
                    dst_idx[did].get("value", "text"),
                )

                if mt_src != mt_dst:
                    continue

                dst_layer.set_value(
                    did,
                    mname,
                    value=unbox_leaf(box),
                    micro_type=mt_dst,
                )

    if allow_prefills:
        _transfer_layer(src.prefills, dst_bundle.prefills)

    if allow_fills:
        _transfer_layer(src.fills, dst_bundle.fills)

    return dst_bundle


def normalize_prefill_validation_directive(raw: Any) -> Dict[str, Any]:
    """
    Normalize multiframespec "prefill validation" directives into a stable shape.

    Supported directive forms:
      - None / False: disabled
      - True: enabled, complete_only
      - "complete_only" / "strict"
      - list/tuple/set: subset of datum ids to validate, complete_only
      - mapping:
          * {"mode": "...", "fields": ...}
          * OR {datum_id: truthy, ...}, treated as subset
    """
    if raw is None or raw is False:
        return {"enabled": False, "mode": "complete_only", "fields": None}

    if raw is True:
        return {"enabled": True, "mode": "complete_only", "fields": None}

    if isinstance(raw, str):
        mode = raw.strip().lower()
        if mode in ("complete_only", "strict"):
            return {"enabled": True, "mode": mode, "fields": None}
        return {"enabled": True, "mode": "complete_only", "fields": None}

    if isinstance(raw, (list, tuple, set)):
        return {
            "enabled": True,
            "mode": "complete_only",
            "fields": {str(x) for x in raw if x is not None},
        }

    if isinstance(raw, Mapping):
        if "mode" in raw or "fields" in raw:
            mode = str(raw.get("mode", "complete_only")).strip().lower()
            if mode not in ("complete_only", "strict"):
                mode = "complete_only"

            fields_raw = raw.get("fields", None)
            if fields_raw is None:
                fields = None
            elif isinstance(fields_raw, (list, tuple, set)):
                fields = {str(x) for x in fields_raw if x is not None}
            else:
                fields = {str(fields_raw)}

            return {
                "enabled": True,
                "mode": mode,
                "fields": fields,
            }

        fields2 = {str(k) for k, v in raw.items() if bool(v)}
        return {
            "enabled": True,
            "mode": "complete_only",
            "fields": fields2,
        }

    return {"enabled": True, "mode": "complete_only", "fields": None}


def validate_prefill_addressing_only(
    *,
    fs: "_multiframespec",
    prefills: Mapping[str, Any],
) -> None:
    """
    Validate only that multiframespec prefills:
      - reference known datum ids
      - use only known micro keys when providing mapping macro fills
    """
    datums_by_id = _index_datums(fs)
    known_ids = set(datums_by_id.keys())

    for fid_raw, val in (prefills or {}).items():
        fid = str(fid_raw)

        datum = datums_by_id.get(fid)
        if datum is None:
            near = _nearest_id(fid, known_ids)
            hint = f" (did you mean {near!r}?)" if near else ""
            raise FormFillsContractError(
                f"multiframespec prefills reference unknown datum id: {fid!r}{hint}"
            )

        micro_names: Set[str] = set(datum_micro_names(datum))
        if isinstance(val, Mapping):
            for mk in val.keys():
                mks = str(mk)
                if mks not in micro_names:
                    raise FormFillsContractError(
                        f"multiframespec prefill for {fid!r} uses unknown micro "
                        f"{mks!r}; allowed micros: {sorted(micro_names)}"
                    )


def validate_and_normalize_prefills(
    *,
    fs: "_multiframespec",
    prefills: Mapping[str, Any],
    directive: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Validate + normalize multiframespec prefills according to the forms-layer directive.

    Directive logic:
      - enabled=False -> addressing-only validation
      - enabled=True:
          - mode="strict": always validate provided values
            partial-safe: required micros are not enforced
          - mode="complete_only": validate only if datum is satisfied
      - fields subset: restrict to those datum ids
    """
    validate_prefill_addressing_only(fs=fs, prefills=prefills)

    enabled = bool(directive.get("enabled", False))
    mode = str(directive.get("mode") or "complete_only")

    fields_subset = directive.get("fields", None)
    if fields_subset is not None:
        fields_subset = set(fields_subset)

    datums_by_id = _index_datums(fs)
    out: Dict[str, Any] = dict(prefills)

    for fid_raw, val in (prefills or {}).items():
        fid = str(fid_raw)
        datum = datums_by_id.get(fid)

        if datum is None:
            raise FormFillsContractError(
                f"multiframespec prefills reference unknown datum id: {fid!r}"
            )

        if not enabled:
            continue

        if fields_subset is not None and fid not in fields_subset:
            continue

        should_full_validate = (
            mode == "strict"
            or (
                mode == "complete_only"
                and datum_fill_data_meets_its_structural_micros_shell(datum, val)
            )
        )

        if not should_full_validate:
            continue

        # Strict prefills must be partial-safe: validate provided values,
        # but do not require required micros to exist.
        enforce_required = not (mode == "strict")

        try:
            validated = parse_and_validate_macro_fill(
                datum=datum,
                raw=val,
                enforce_required_micros=enforce_required,
            )
            out[fid] = validated
        except DeadJSONError as e:
            raise FormFillsContractError(
                f"multiframespec prefill validation produced non-JSON for {fid!r}: {e}"
            ) from e
        except Exception as e:
            raise FormFillsContractError(
                f"multiframespec prefill validation failed for {fid!r}: {e}"
            ) from e

    return out


def derive_form_id(
    *,
    app_public_step_name: str,
    _multiframespec_obj: Any,
) -> str:
    """
    Derive a stable form id string for UI/runtime surfaces.

    Preference order:
      - _multiframespec_obj["app_form_id"] / ["form_id"] when provided
      - else app_public_step_name
      - else "FORM"
    """
    if isinstance(_multiframespec_obj, Mapping):
        for k in ("app_form_id", "form_id"):
            v = _multiframespec_obj.get(k)

            if isinstance(v, str) and v.strip():
                return v.strip()

            if v is not None and str(v).strip():
                return str(v).strip()

    return str(app_public_step_name).strip() or "FORM"


__all__ = [
    # imported/re-exported public errors
    "FormFillsAPIError",
    "FormFillsContractError",

    # imported/re-exported generic fill contract
    "FillKind",
    "MicroResolver",
    "MicroTypeResolution",
    "unbox_leaf",
    "FormFillsLayerV1",
    "FormFillsBundleV1",
    "transfer_values_by_ref_map",

    # multiframespec adapters
    "index_multiframespec",
    "multiframespec_micro_resolver",
    "form_fills_layer_from_multiframespec",
    "form_fills_bundle_from_multiframespec",
    "validate_fills_layer_against_multiframespec",
    "transfer_values",

    # imported/re-exported engine-facing core contract
    "DeadJSONError",
    "assert_dead_json",
    "merge_macro_values",
    "is_blank_value",
    "datum_required_micro_names",
    "datum_micro_names",
    "macro_micro_value",
    "datum_fill_data_meets_its_structural_micros_shell",
    "build_datum_validator",
    "parse_and_validate_macro_fill",

    # multiframespec-layer policy
    "normalize_prefill_validation_directive",
    "validate_prefill_addressing_only",
    "validate_and_normalize_prefills",
    "derive_form_id",
]