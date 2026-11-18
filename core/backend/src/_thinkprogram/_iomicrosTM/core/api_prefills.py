from __future__ import annotations

"""Surface-agnostic canonical prefill/fill wire.

Canonical boxed leaf:
    {
        "__boxed__": true,
        "value": ...,
        "micro_type": "...",
        "kind": "prefill" | "fill"
    }

Canonical layer:
    {"values": {sink_id: {micro_name: boxed_leaf}}}

Plain mappings are data/macros, never boxes by shape. Explicit boxing keeps
transport metadata disjoint from arbitrary JSON-object atoms.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from __exceptions.engine import FormFillsAPIError, FormFillsContractError
from _thinkprogram._iomicrosTM.core.api_coercion import can_coerce_micro, coerce_micro_value
from _thinkprogram._iomicrosTM.core.api_fills import (
    DeadJSONError,
    assert_dead_json,
    build_datum_validator,
    coerce_accepted_macro_fill_for_datum,
    datum_fill_data_meets_its_structural_micros_shell,
    datum_micro_names,
    datum_required_micro_names,
    is_blank_value,
    macro_micro_value,
    merge_macro_values,
    parse_and_validate_macro_fill,
    parse_validate_and_coerce_macro_fill,
)
from _thinkprogram._iomicrosTM.core.micro_registry import get_micro_type_definition
from _thinkprogram._iomicrosTM.core.value_semantics import BOX_MARKER, unbox_leaf

FillKind = str
MicroTypeResolution = Union[str, Tuple[str, ...]]
MicroResolver = Callable[[str, str], MicroTypeResolution]


_BOX_KEYS = {BOX_MARKER, "value", "micro_type", "kind", "source", "meta"}


def _is_boxed_leaf(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if value.get(BOX_MARKER) is not True:
        return False
    if "value" not in value or "micro_type" not in value:
        return False
    return set(str(key) for key in value).issubset(_BOX_KEYS)


def _box_micro_type(value: Any) -> Optional[str]:
    if not _is_boxed_leaf(value):
        return None
    raw = value.get("micro_type")
    name = str(raw or "").strip().lower()
    return name or None


def _coerce_typed_value(micro_type: str, raw_value: Any) -> Any:
    try:
        definition = get_micro_type_definition(micro_type)
    except Exception as exc:
        raise FormFillsAPIError(f"unknown micro type {micro_type!r}") from exc

    value = unbox_leaf(raw_value)
    if value is None:
        return None
    try:
        out = definition.coerce(value) if callable(definition.coerce) else value
    except Exception as exc:
        raise FormFillsAPIError(
            f"cannot coerce {value!r} to micro type {micro_type!r}: {exc}"
        ) from exc

    allowed = tuple(definition.python_types or ())
    if out is not None and allowed and not isinstance(out, allowed):
        raise FormFillsAPIError(
            f"micro type {micro_type!r} produced {type(out).__name__}; "
            f"expected {[t.__name__ for t in allowed]}"
        )
    assert_dead_json(out, path=f"fill[{micro_type}]")
    return out


def _box_value(*, value: Any, micro_type: str, kind: FillKind) -> Dict[str, Any]:
    box = {
        BOX_MARKER: True,
        "value": value,
        "micro_type": micro_type,
        "kind": kind,
    }
    assert_dead_json(box, path="boxed_fill")
    return box


def _normalize_layer_input(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {"values": {}}
    if not isinstance(raw, Mapping):
        raise FormFillsAPIError(f"unsupported fills layer type: {type(raw).__name__}")
    if "values" in raw:
        values = raw.get("values")
        if not isinstance(values, Mapping):
            raise FormFillsAPIError("fills 'values' must be a mapping")
        return {"values": dict(values)}
    return {"values": dict(raw)}


def _bag_to_authoring_macro(bag: Mapping[str, Mapping[str, Any]]) -> Any:
    if not bag:
        return None
    if set(bag) == {"value"}:
        return unbox_leaf(bag.get("value"))
    return {str(name): unbox_leaf(box) for name, box in bag.items()}


def _normalize_allowed_micro_types(value: MicroTypeResolution) -> Tuple[str, ...]:
    if isinstance(value, str):
        name = value.strip().lower()
        return (name,) if name else ("text",)
    if isinstance(value, (list, tuple, set)):
        out = tuple(
            dict.fromkeys(
                str(item).strip().lower()
                for item in value
                if item is not None and str(item).strip()
            )
        )
        return out or ("text",)
    return ("text",)


def _infer_micro_type_from_typed_scalar(
    *,
    allowed: Tuple[str, ...],
    raw_value: Any,
) -> Optional[str]:
    value = unbox_leaf(raw_value)
    if value is None or isinstance(value, str):
        return None

    matches: list[str] = []
    for micro_type in allowed:
        try:
            python_types = tuple(get_micro_type_definition(micro_type).python_types or ())
        except Exception:
            continue
        if isinstance(value, bool):
            if bool in python_types:
                matches.append(micro_type)
        elif isinstance(value, python_types):
            matches.append(micro_type)
    return matches[0] if len(matches) == 1 else None


def _resolve_micro_type(
    *,
    resolver: Optional[MicroResolver],
    sink_id: str,
    micro_name: str,
    box_micro_type: Optional[str],
    raw_value: Any = None,
) -> str:
    # Without a destination contract, an explicit box may author its own type.
    # Untyped convenience input defaults to text and is still canonicalized.
    if resolver is None:
        if box_micro_type:
            try:
                get_micro_type_definition(box_micro_type)
            except Exception as exc:
                raise FormFillsAPIError(
                    f"boxed value declares unknown micro type {box_micro_type!r}"
                ) from exc
            return box_micro_type
        return "text"

    allowed = _normalize_allowed_micro_types(resolver(sink_id, micro_name))
    for micro_type in allowed:
        try:
            get_micro_type_definition(micro_type)
        except Exception as exc:
            raise FormFillsAPIError(
                f"resolver returned unknown micro type {micro_type!r} for "
                f"{sink_id!r}.{micro_name}"
            ) from exc

    if box_micro_type:
        if box_micro_type not in allowed:
            raise FormFillsAPIError(
                f"boxed micro_type {box_micro_type!r} is not allowed for "
                f"{sink_id!r}.{micro_name}; allowed={list(allowed)}"
            )
        return box_micro_type
    if len(allowed) == 1:
        return allowed[0]

    inferred = _infer_micro_type_from_typed_scalar(
        allowed=allowed,
        raw_value=raw_value,
    )
    if inferred:
        return inferred
    raise FormFillsAPIError(
        f"ambiguous micro type for {sink_id!r}.{micro_name}; allowed={list(allowed)}. "
        f"Provide an explicit {BOX_MARKER!r} boxed value with 'micro_type'."
    )


def _parse_ref(ref: str) -> Tuple[str, str]:
    raw = str(ref or "").strip()
    if not raw:
        raise FormFillsAPIError("empty ref")
    if "." not in raw:
        return raw, "value"
    sink, micro = raw.split(".", 1)
    sink = sink.strip()
    micro = micro.strip() or "value"
    if not sink:
        raise FormFillsAPIError(f"invalid ref {ref!r}: missing sink id")
    return sink, micro


@dataclass
class FormFillsLayerV1:
    kind: FillKind
    values: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def from_any(
        cls,
        raw: Any,
        *,
        kind: FillKind,
        micro_resolver: Optional[MicroResolver] = None,
    ) -> "FormFillsLayerV1":
        norm = _normalize_layer_input(raw)
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for sink_raw, macro_value in (norm.get("values") or {}).items():
            sink_id = str(sink_raw)
            if not sink_id:
                continue

            if _is_boxed_leaf(macro_value) or not isinstance(macro_value, Mapping):
                micro_type = _resolve_micro_type(
                    resolver=micro_resolver,
                    sink_id=sink_id,
                    micro_name="value",
                    box_micro_type=_box_micro_type(macro_value),
                    raw_value=macro_value,
                )
                value = _coerce_typed_value(micro_type, macro_value)
                out.setdefault(sink_id, {})["value"] = _box_value(
                    value=value,
                    micro_type=micro_type,
                    kind=kind,
                )
                continue

            bag: Dict[str, Dict[str, Any]] = {}
            for micro_raw, micro_value in macro_value.items():
                micro_name = str(micro_raw)
                if not micro_name:
                    continue
                micro_type = _resolve_micro_type(
                    resolver=micro_resolver,
                    sink_id=sink_id,
                    micro_name=micro_name,
                    box_micro_type=_box_micro_type(micro_value),
                    raw_value=micro_value,
                )
                value = _coerce_typed_value(micro_type, micro_value)
                bag[micro_name] = _box_value(
                    value=value,
                    micro_type=micro_type,
                    kind=kind,
                )
            if bag:
                out[sink_id] = bag

        return cls(kind=kind, values=out)

    def to_json(self) -> Dict[str, Any]:
        wire = {"values": self.values}
        assert_dead_json(wire, path="fills_layer")
        return wire

    def to_authoring_values(self) -> Dict[str, Any]:
        return {
            str(sink_id): macro
            for sink_id, bag in self.values.items()
            if (macro := _bag_to_authoring_macro(bag)) is not None
        }

    def get_box(self, sink_id: str, micro: str = "value") -> Optional[Dict[str, Any]]:
        return (self.values.get(str(sink_id)) or {}).get(str(micro))

    def get_value(self, sink_id: str, micro: str = "value", default: Any = None) -> Any:
        box = self.get_box(sink_id, micro=micro)
        return unbox_leaf(box) if box is not None else default

    def set_value(
        self,
        sink_id: str,
        micro: str,
        *,
        value: Any,
        micro_type: str,
    ) -> None:
        sink = str(sink_id)
        name = str(micro or "value")
        mtype = str(micro_type).strip().lower() or "text"
        canonical = _coerce_typed_value(mtype, value)
        self.values.setdefault(sink, {})[name] = _box_value(
            value=canonical,
            micro_type=mtype,
            kind=self.kind,
        )

    def merge_over(self, lower: "FormFillsLayerV1") -> "FormFillsLayerV1":
        out = FormFillsLayerV1(kind=self.kind)
        for sink_id, bag in lower.values.items():
            out.values[sink_id] = dict(bag)
        for sink_id, bag in self.values.items():
            out.values.setdefault(sink_id, {}).update(dict(bag))
        return out


@dataclass
class FormFillsBundleV1:
    prefills: FormFillsLayerV1
    fills: FormFillsLayerV1

    @classmethod
    def from_any(
        cls,
        *,
        prefills: Any = None,
        fills: Any = None,
        micro_resolver: Optional[MicroResolver] = None,
    ) -> "FormFillsBundleV1":
        return cls(
            prefills=FormFillsLayerV1.from_any(
                prefills,
                kind="prefill",
                micro_resolver=micro_resolver,
            ),
            fills=FormFillsLayerV1.from_any(
                fills,
                kind="fill",
                micro_resolver=micro_resolver,
            ),
        )

    def effective_layer(self) -> FormFillsLayerV1:
        return self.fills.merge_over(self.prefills)

    def get_effective_value(self, sink_id: str, micro: str = "value", default: Any = None) -> Any:
        return self.effective_layer().get_value(sink_id, micro=micro, default=default)

    def to_authoring_prefills(self) -> Dict[str, Any]:
        return self.prefills.to_authoring_values()

    def to_authoring_effective_values(self) -> Dict[str, Any]:
        return self.effective_layer().to_authoring_values()


def _resolve_transfer_destination_type(
    *,
    src_type: str,
    allowed: Tuple[str, ...],
    destination_ref: str,
) -> str:
    if src_type in allowed:
        return src_type
    candidates = [
        dst_type
        for dst_type in allowed
        if can_coerce_micro(src_micro_type=src_type, dst_micro_type=dst_type)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FormFillsAPIError(
            f"cannot transfer source micro_type {src_type!r} to {destination_ref!r}; "
            f"destination allows {list(allowed)}"
        )
    raise FormFillsAPIError(
        f"ambiguous coercion transferring {src_type!r} to {destination_ref!r}; "
        f"compatible destination types={candidates}"
    )


def transfer_values_by_ref_map(
    *,
    src: FormFillsBundleV1,
    dst: FormFillsBundleV1,
    ref_map: Mapping[str, str],
    src_resolver: MicroResolver,
    dst_resolver: MicroResolver,
    allow_prefills: bool = True,
    allow_fills: bool = True,
) -> FormFillsBundleV1:
    del src_resolver  # source boxes are authoritative about their actual type.
    if not isinstance(ref_map, Mapping) or not ref_map:
        return dst

    def transfer_layer(source: FormFillsLayerV1, destination: FormFillsLayerV1) -> None:
        for dst_ref, src_ref in ref_map.items():
            dst_sink, dst_micro = _parse_ref(str(dst_ref))
            src_sink, src_micro = _parse_ref(str(src_ref))
            box = source.get_box(src_sink, micro=src_micro)
            if box is None:
                continue
            src_type = str(box.get("micro_type") or "").strip().lower()
            if not src_type:
                raise FormFillsAPIError(f"source box missing micro_type at {src_ref!r}")

            allowed = _normalize_allowed_micro_types(dst_resolver(dst_sink, dst_micro))
            dst_type = _resolve_transfer_destination_type(
                src_type=src_type,
                allowed=allowed,
                destination_ref=str(dst_ref),
            )
            try:
                value = coerce_micro_value(
                    src_micro_type=src_type,
                    dst_micro_type=dst_type,
                    raw=unbox_leaf(box),
                )
            except Exception as exc:
                raise FormFillsAPIError(
                    f"failed transfer {src_ref!r} -> {dst_ref!r}: {exc}"
                ) from exc
            destination.set_value(
                dst_sink,
                dst_micro,
                value=value,
                micro_type=dst_type,
            )

    if allow_prefills:
        transfer_layer(src.prefills, dst.prefills)
    if allow_fills:
        transfer_layer(src.fills, dst.fills)
    return dst


__all__ = [
    "FormFillsAPIError",
    "FormFillsContractError",
    "FillKind",
    "MicroResolver",
    "MicroTypeResolution",
    "unbox_leaf",
    "FormFillsLayerV1",
    "FormFillsBundleV1",
    "transfer_values_by_ref_map",
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
    "coerce_accepted_macro_fill_for_datum",
    "parse_validate_and_coerce_macro_fill",
]
