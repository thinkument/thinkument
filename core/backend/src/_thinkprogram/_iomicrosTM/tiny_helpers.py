from __future__ import annotations

from dataclasses import asdict
from dataclasses import fields
from dataclasses import fields as dataclass_fields, is_dataclass
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from enum import Enum

import inspect
import json
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from _thinkprogram._iomicrosTM.core.api_fills import DeadJSONError, assert_dead_json

JSON_SCALARS: Tuple[type, ...] = (str, int, float, bool, type(None))
JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, Dict[str, "JSONValue"], List["JSONValue"]]

_JSON_LEAF_TYPES: Tuple[type, ...] = (str, int, float, bool, type(None))
_JSON_PRIMITIVES: Tuple[type, ...] = _JSON_LEAF_TYPES


# -----------------------------------------------------------------------------
# A) Mapping / string / int / time helpers
# -----------------------------------------------------------------------------

def mapping2dict(x: Any) -> Dict:
    if isinstance(x, Mapping):
        return dict(x)
    return {}


def _mapping_from_any(value: Any) -> Dict[str, Any]:
    return mapping2dict(value)



def json_sanitize_v1(obj: Any) -> JSONValue:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")

    for meth in ("as_dict", "to_dict"):
        try:
            fn = getattr(obj, meth, None)
            if callable(fn):
                return json_sanitize_v1(fn())
        except Exception:
            pass

    if isinstance(obj, Mapping):
        return {str(k): json_sanitize_v1(v) for k, v in dict(obj).items()}

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [json_sanitize_v1(x) for x in obj]

    try:
        return repr(obj)
    except Exception:
        return "<unserializable>"


def mapping_from_any_v1(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    sanitized = json_sanitize_v1(obj)
    return dict(sanitized) if isinstance(sanitized, Mapping) else {}



def _safe_mapping_dict(x: Any) -> Dict[str, Any]:
    return mapping2dict(x)


def _maybe_str(x: Any) -> Optional[str]:
    """Return stripped string or None."""
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def _safe_str_or_none(x: Any) -> Optional[str]:
    return _maybe_str(x)


def _safe_optional_mapping(x: Any, *, where: str) -> Optional[Dict[str, Any]]:
    if x is None:
        return None
    if not isinstance(x, Mapping):
        raise TypeError(f"{where} must be a dict/mapping if provided")
    return dict(x)


def as_mapping(x: Any, *, what: str) -> Dict[str, Any]:
    """
    Coerce a value to a plain dict (or {} if None).

    Keep integration surfaces strict and predictable:
      - None => {}
      - non-mapping => TypeError
      - mapping => dict(mapping)
    """
    if x is None:
        return {}
    if not isinstance(x, Mapping):
        raise TypeError(f"{what} must be a mapping")
    return dict(x)


def _coerce_nonnegative_int_v1(value: Any, default: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)
    return max(0, out)


def _utc_now_iso_v1() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# -----------------------------------------------------------------------------
# B) JSON helpers
# -----------------------------------------------------------------------------

def _is_json_safe(x: Any) -> bool:
    if x is None or isinstance(x, _JSON_PRIMITIVES):
        return True
    if isinstance(x, list):
        return all(_is_json_safe(i) for i in x)
    if isinstance(x, dict):
        return all(isinstance(k, str) and _is_json_safe(v) for k, v in x.items())
    return False


def is_dead_json_scalar_like(x: Any) -> bool:
    """
    Broad predicate: "could plausibly be JSON-ish".

    This is intentionally permissive and used only as a *shape* check.
    It does NOT guarantee dead-json immutability or full serializability.
    """
    return x is None or isinstance(x, (str, int, float, bool, list, tuple, Mapping))


def _json_str_enum(x: Any) -> Any:
    """Render Enums as their `.value` for JSON surfaces."""
    if isinstance(x, Enum):
        return x.value
    return x


def _json_compact_dumps(obj: Any) -> bytes:
    """
    Strict JSON serialization (no default=str).
    Anything non-serializable is an invariant violation at the membrane.
    """
    try:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except Exception as e:
        raise ValueError(f"engine snapshot is not JSON-serializable: {type(e).__name__}: {e}") from e


def _json_loads_bytes(blob: bytes) -> Any:
    return json.loads(blob.decode("utf-8"))


def callable_path(obj: Any) -> Optional[str]:
    if obj is None:
        return None

    mod = getattr(obj, "__module__", None)
    qual = getattr(obj, "__qualname__", None) or getattr(obj, "__name__", None)

    if mod and qual:
        return f"{mod}:{qual}"

    return str(obj)


def type_name(tp: Any) -> str:
    return getattr(tp, "__name__", str(tp))


def json_roundtripable(obj: Any) -> Any:
    """
    Best-effort conversion to a JSON-safe value.

    This is intentionally conservative:
    - primitive JSON values pass through
    - mappings get stringified keys
    - lists/tuples/sets become lists
    - dataclasses become dictionaries
    - classes/callables become stable-ish import paths
    - unknown objects fall back to repr()
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, Mapping):
        return {str(k): json_roundtripable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [json_roundtripable(v) for v in obj]

    if is_dataclass(obj):
        return {
            str(f.name): json_roundtripable(getattr(obj, f.name))
            for f in dataclass_fields(obj)
        }

    if inspect.isclass(obj):
        return callable_path(obj)

    if callable(obj):
        return callable_path(obj)

    return repr(obj)


def assert_json_roundtripable(obj: Any) -> None:
    """
    Raise if the normalized object cannot actually be JSON serialized.

    Useful in tests where you want enforcement rather than best-effort conversion.
    """
    json.dumps(json_roundtripable(obj), sort_keys=True)


def _jsonish(value: Any) -> Any:
    """
    Best-effort JSON-safe view for terminal/debug payloads.

    This is intentionally only for local debug printing and response packaging.
    It is not a persistence or runtime serialization contract.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Mapping):
        return {str(k): _jsonish(v) for k, v in dict(value).items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonish(x) for x in list(value)]

    for meth in ("to_dict", "as_dict"):
        fn = getattr(value, meth, None)
        if callable(fn):
            try:
                return _jsonish(fn())
            except Exception:
                pass

    return repr(value)


def _json_sanitize(obj: Any) -> JSONValue:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)

    try:
        if is_dataclass(obj):
            out_dc: Dict[str, JSONValue] = {}
            for f in dc_fields(obj):
                try:
                    out_dc[str(f.name)] = _json_sanitize(getattr(obj, f.name))
                except Exception:
                    out_dc[str(f.name)] = None
            return out_dc
    except Exception:
        pass

    if isinstance(obj, Mapping):
        out_map: Dict[str, JSONValue] = {}
        for k, v in obj.items():
            out_map[str(k)] = _json_sanitize(v)
        return out_map

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_json_sanitize(x) for x in obj]

    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        try:
            return [_json_sanitize(x) for x in list(obj)]
        except Exception:
            pass

    try:
        return repr(obj)
    except Exception:
        return "<unserializable>"


def kill_generic_mapping_to_dead_json(obj: Any) -> Any:
    """
    Recursively JSON-sanitize `obj`.

    Rules:
      - Mapping -> recurse values (keys forced to str)
      - list/tuple/set -> list of sanitized
      - dataclass -> dict(field->sanitized)
      - plain objects with __dict__ -> shallow public attr scrape
      - otherwise -> str(obj)
    """
    if obj is None or isinstance(obj, _JSON_LEAF_TYPES):
        return obj

    if isinstance(obj, Mapping):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            out[str(k)] = kill_generic_mapping_to_dead_json(v)
        return out

    if isinstance(obj, (list, tuple, set)):
        return [kill_generic_mapping_to_dead_json(x) for x in obj]

    if is_dataclass(obj):
        try:
            return {
                f.name: kill_generic_mapping_to_dead_json(getattr(obj, f.name))
                for f in dc_fields(obj)
            }
        except Exception:
            return str(obj)

    d = getattr(obj, "__dict__", None)

    if isinstance(d, dict):
        snap: Dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            try:
                snap[str(k)] = kill_generic_mapping_to_dead_json(v)
            except Exception:
                snap[str(k)] = str(v)
        return snap

    return str(obj)


# -----------------------------------------------------------------------------
# C) List / set / tag helpers
# -----------------------------------------------------------------------------

def ensure_list(x: Any) -> List[Any]:
    """
    Loose list coercion:
      - None => []
      - list => itself
      - iterable => list(iterable)
      - otherwise => []
    """
    if x is None:
        return []
    if isinstance(x, list):
        return x
    try:
        return list(x)
    except Exception:
        return []


def _as_list(x: Any) -> List[Any]:
    """
    Stricter list coercion:
      - list/tuple => list(x)
      - otherwise => []
    """
    return list(x or []) if isinstance(x, (list, tuple)) else []


def sorted_unique_strs(xs: Iterable[Any]) -> List[str]:
    out = {str(x) for x in xs if str(x).strip()}
    return sorted(out)


def norm_tags(val: Any) -> List[str]:
    """
    Normalize tags to a clean list[str].
    Accepts str | list/tuple/set | None.
    """
    if val is None:
        return []
    if isinstance(val, str):
        val = [val]
    out: List[str] = []
    if isinstance(val, (list, tuple, set)):
        for t in val:
            if t is None:
                continue
            s = str(t).strip()
            if s:
                out.append(s)
    return out


def is_seq(x: Any) -> Sequence[Any] | None:
    if isinstance(x, (list, tuple)):
        return x
    return None


# -----------------------------------------------------------------------------
# D) Dict merge / strip helpers
# -----------------------------------------------------------------------------

def _merge_dicts(*ds: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Shallow merge mappings into a plain dict.

    Rules:
      - later mappings win
      - None values are skipped
      - keys are coerced to str
      - falsy mappings are ignored
    """
    out: Dict[str, Any] = {}
    for d in ds:
        for k, v in (d or {}).items():
            if v is not None:
                out[str(k)] = v
    return out


def strip_none(obj: Any) -> Any:
    """
    Recursively remove None entries from dicts/lists.
    Leaves JSON primitives untouched.
    """
    if obj is None or isinstance(obj, _JSON_LEAF_TYPES):
        return obj
    if isinstance(obj, list):
        out = []
        for v in obj:
            sv = strip_none(v)
            if sv is not None:
                out.append(sv)
        return out
    if isinstance(obj, dict):
        out2: Dict[str, Any] = {}
        for k, v in obj.items():
            sv = strip_none(v)
            if sv is not None:
                out2[k] = sv
        return out2
    return obj


def deep_merge(a: Any, b: Any) -> Dict[str, Any]:
    """
    Dead-simple deep merge for dict-only trees.
    Overlay (b) wins. Non-dicts replace entirely.
    """
    base = dict(a) if isinstance(a, Mapping) else {}
    over = dict(b) if isinstance(b, Mapping) else {}
    out: Dict[str, Any] = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], Mapping) and isinstance(v, Mapping):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _deep_merge_mapping_values(
    base: Mapping[str, Any],
    update: Mapping[str, Any],
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base or {})
    for raw_key, raw_value in dict(update or {}).items():
        key = str(raw_key)
        current = out.get(key)
        if isinstance(current, Mapping) and isinstance(raw_value, Mapping):
            out[key] = _deep_merge_mapping_values(dict(current), dict(raw_value))
        else:
            out[key] = raw_value
    return out


def _deep_merge_jsonish_mappings(
    base: Mapping[str, Any],
    update: Mapping[str, Any],
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base or {})
    for k, v in dict(update or {}).items():
        ks = str(k)
        cur = out.get(ks)
        if isinstance(cur, Mapping) and isinstance(v, Mapping):
            out[ks] = _deep_merge_jsonish_mappings(dict(cur), dict(v))
        else:
            out[ks] = v
    return out


# -----------------------------------------------------------------------------
# E) Object / dataclass helpers
# -----------------------------------------------------------------------------

def shallow_dc(obj: Any) -> Dict[str, Any]:
    """
    Shallow dematerializer:
      - None -> {}
      - dict -> dict(obj)
      - dataclass -> {field: value}
      - generic object -> public non-callable attrs via dir()

    Used for permissive app-dev inputs, then normalized downstream.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if is_dataclass(obj):
        return {f.name: getattr(obj, f.name) for f in dc_fields(obj)}
    out: Dict[str, Any] = {}
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except Exception:
            continue
        if callable(v):
            continue
        out[k] = v
    return out


def _to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    try:
        if is_dataclass(obj):
            return asdict(obj)
    except Exception:
        pass
    out: Dict[str, Any] = {}
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except Exception:
            continue
        if callable(v):
            continue
        out[k] = v
    return out


def _maybe_object_json(x: Any) -> Any:
    """
    Accept either a strongly-typed spec object with `to_object_json()`
    OR a dead-JSON dict that is already in object-json form.
    """
    if x is None:
        return None
    to_obj = getattr(x, "to_object_json", None)
    if callable(to_obj):
        return to_obj()
    if isinstance(x, dict):
        return dict(x)
    raise TypeError(f"Expected object-json dict or to_object_json()-capable object, got {type(x)!r}")


def _template_to_object_json(template: Any) -> Any:
    """
    App-dev stability rule:
      - templates are allowed to be either a TemplateSpec-like object with .to_object_json()
        OR already-dead-JSON dicts coming directly from manifests/tests.
    """
    if template is None:
        return None
    to_json = getattr(template, "to_object_json", None)
    if callable(to_json):
        return to_json()
    if isinstance(template, Mapping):
        return dict(template)
    raise TypeError(f"Invalid template type for object_json: {type(template)!r}")


# -----------------------------------------------------------------------------
# F) Signature / callable helpers
# -----------------------------------------------------------------------------

def _callable_accepts_kwarg_v1(fn: Any, kwarg_name: str) -> bool:
    """
    Safe opt-in kwarg injection check.

    Why this is needed:
    - we want to inject the live engine session ctx into runtimes that know how
      to consume it
    - but we must not break unrelated step functions that do not accept the
      reserved kwarg
    """
    try:
        sig = inspect.signature(fn)
    except Exception:
        return False

    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

    return kwarg_name in sig.parameters


def simple_class_name(dotted_or_cls: Any) -> str:
    if isinstance(dotted_or_cls, str):
        tail = dotted_or_cls.rsplit(":", 1)[-1]
        return tail.rsplit(".", 1)[-1]

    return getattr(dotted_or_cls, "__name__", str(dotted_or_cls))


def signature_to_json(fn: Any) -> Dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except Exception:
        return {"rendered": "<unavailable>"}

    params: List[Dict[str, Any]] = []

    for p in sig.parameters.values():
        params.append(
            {
                "name": str(p.name),
                "kind": str(p.kind),
                "default": None
                if p.default is inspect._empty
                else json_roundtripable(p.default),
                "annotation": None
                if p.annotation is inspect._empty
                else str(p.annotation),
            }
        )

    return {
        "rendered": str(sig),
        "parameters": params,
        "return_annotation": None
        if sig.return_annotation is inspect._empty
        else str(sig.return_annotation),
    }


# -----------------------------------------------------------------------------
# G) Dead-JSON validation / base classes
# -----------------------------------------------------------------------------

def require_dead_json_mapping(x: Any, *, where: str) -> None:
    """
    Assert x (if provided) is a mapping and dead-json safe.

    Raises:
      - TypeError if not mapping or not dead-json safe.
    """
    if x is None:
        return
    if not isinstance(x, Mapping):
        raise TypeError(f"{where} must be a mapping if provided")
    try:
        assert_dead_json(dict(x), path=where)
    except DeadJSONError as e:
        raise TypeError(f"{where} must be dead-json safe: {e}") from e


class JSONShapeBase:
    """
    Small base for typed JSON-shape objects.

    - `.validate()` calls optional `_validate()` if present.
    - `.to_json()` uses authoritative forms-layer sanitizer (`kill_generic_mapping_to_dead_json`),
      which handles style objects / custom objects / etc.
    """

    def validate(self) -> None:
        fn = getattr(self, "_validate", None)
        if callable(fn):
            fn()


T = TypeVar("T", bound="AdapterFromDict")


class AdapterFromDict:
    """
    Option B: allow constructing from dict and/or kwargs, and capture unknown keys
    into an `extra` field (if present).

    Also supports a simple construction switch:
      _allow_stray_args=False -> unknown keys are dropped (and extra will be empty).
      _allow_stray_args=True  -> unknown keys are captured into .extra.
    """

    @classmethod
    @overload
    def from_dict(cls: Type[T], data: Mapping[str, Any], *, _allow_stray_args: bool = True) -> T: ...

    @classmethod
    @overload
    def from_dict(cls: Type[T], *, _allow_stray_args: bool = True, **kwargs: Any) -> T: ...

    @classmethod
    def from_dict(
        cls: Type[T],
        data: Mapping[str, Any] | None = None,
        *,
        _allow_stray_args: bool = True,
        **kwargs: Any,
    ) -> T:
        merged: Dict[str, Any] = {}
        if data is not None:
            merged.update(dict(data))
        merged.update(kwargs)

        allowed = {f.name for f in fields(cls)}

        # Never accept the control flag as a constructor key.
        merged.pop("_allow_stray_args", None)

        known: Dict[str, Any] = {
            k: v for k, v in merged.items() if k in allowed and k != "extra"
        }

        if "extra" in allowed:
            if _allow_stray_args:
                known["extra"] = {k: v for k, v in merged.items() if k not in allowed}
            else:
                known["extra"] = {}

        return cls(**known)  # type: ignore[misc]


__all__ = [
    "AdapterFromDict",
    "JSONScalar",
    "JSONShapeBase",
    "JSONValue",
    "_as_list",
    "_callable_accepts_kwarg_v1",
    "_coerce_nonnegative_int_v1",
    "_deep_merge_jsonish_mappings",
    "_deep_merge_mapping_values",
    "_is_json_safe",
    "_json_compact_dumps",
    "_json_loads_bytes",
    "_json_sanitize",
    "_json_str_enum",
    "_jsonish",
    "_mapping_from_any",
    "_maybe_object_json",
    "_maybe_str",
    "_merge_dicts",
    "_safe_mapping_dict",
    "_safe_optional_mapping",
    "_safe_str_or_none",
    "_template_to_object_json",
    "_to_dict",
    "_utc_now_iso_v1",
    "as_mapping",
    "assert_json_roundtripable",
    "callable_path",
    "deep_merge",
    "ensure_list",
    "is_dead_json_scalar_like",
    "json_roundtripable",
    "kill_generic_mapping_to_dead_json",
    "mapping2dict",
    "norm_tags",
    "require_dead_json_mapping",
    "shallow_dc",
    "signature_to_json",
    "simple_class_name",
    "sorted_unique_strs",
    "strip_none",
    "type_name",
]