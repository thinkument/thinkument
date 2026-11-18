from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from enum import Enum
from types import SimpleNamespace
from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json


def coerce_str(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, str):
        return x
    if isinstance(x, (dict, list, tuple)):
        try:
            dead = coerce_object_json(x)
            return json.dumps(
                dead,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except Exception:
            return str(x)
    return str(x)


def coerce_bool(x: Any) -> Any:
    """Strict human boolean coercion.

    Only actual bools, numeric 0/1, and common explicit lexical forms are
    accepted.  Arbitrary nonzero numbers are not silently treated as True.
    """
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, int) and not isinstance(x, bool):
        if x in (0, 1):
            return bool(x)
        raise ValueError(f"cannot coerce integer {x!r} to bool; expected 0 or 1")
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"float must be finite, got {x!r}")
        if x in (0.0, 1.0):
            return bool(int(x))
        raise ValueError(f"cannot coerce float {x!r} to bool; expected 0.0 or 1.0")
    if isinstance(x, str):
        s = x.strip().lower()
        if s in {"true", "t", "yes", "y", "1", "on"}:
            return True
        if s in {"false", "f", "no", "n", "0", "off"}:
            return False
    raise ValueError(f"cannot coerce {x!r} to bool")


def coerce_number(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, bool):
        raise ValueError("bool is not a number")
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"float must be finite, got {x!r}")
        return x
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            # Keep integer-looking values canonical as int.
            if all(ch not in s.lower() for ch in (".", "e")):
                return int(s, 10)
        except ValueError:
            pass
        try:
            out = float(s)
        except ValueError as exc:
            raise ValueError(f"cannot parse number from {x!r}") from exc
        if not math.isfinite(out):
            raise ValueError(f"float must be finite, got {out!r}")
        return out
    raise ValueError(f"cannot coerce {x!r} to number")


def coerce_integer(x: Any) -> Any:
    """Strict canonical integer coercion.

    Blank strings map to None.  Nonblank malformed strings are errors; they are
    never converted to missing data.
    """
    if x is None:
        return None
    if isinstance(x, bool):
        raise ValueError("bool is not integer")
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"float must be finite, got {x!r}")
        if x.is_integer():
            return int(x)
        raise ValueError(f"cannot coerce non-integer float {x!r} to integer")
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            return int(s, 10)
        except ValueError as exc:
            raise ValueError(f"cannot parse integer from {x!r}") from exc
    raise ValueError(f"cannot coerce {x!r} to integer")


def ensure_dead_json(x: Any, *, _path: str = "$") -> Any:
    """Normalize supported Python objects into strict dead JSON."""
    if isinstance(x, Enum):
        return ensure_dead_json(x.value, _path=_path)

    if is_dataclass(x) and not isinstance(x, type):
        return ensure_dead_json(asdict(x), _path=_path)

    if isinstance(x, SimpleNamespace):
        return ensure_dead_json(vars(x), _path=_path)

    if hasattr(x, "to_dict") and callable(getattr(x, "to_dict")):
        return ensure_dead_json(x.to_dict(), _path=_path)

    if hasattr(x, "to_object_json") and callable(getattr(x, "to_object_json")):
        return ensure_dead_json(x.to_object_json(), _path=_path)

    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"object-json requires finite float; got {x!r} at {_path}")
        return x

    if x is None or isinstance(x, (str, int, bool)):
        return x

    if isinstance(x, dict):
        out: Dict[str, Any] = {}
        for key, value in x.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"object-json requires string keys; "
                    f"got {type(key).__name__} at {_path}"
                )
            out[key] = ensure_dead_json(value, _path=f"{_path}.{key}")
        return out

    if isinstance(x, Mapping):
        out = {}
        for key, value in x.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"object-json mapping requires string keys; "
                    f"got {type(key).__name__} at {_path}"
                )
            out[key] = ensure_dead_json(value, _path=f"{_path}.{key}")
        return out

    if isinstance(x, (list, tuple)):
        return [
            ensure_dead_json(value, _path=f"{_path}[{index}]")
            for index, value in enumerate(x)
        ]

    raise ValueError(
        f"object-json cannot represent {type(x).__name__} at {_path}: {x!r}"
    )


def coerce_object_json(x: Any) -> Any:
    if x is None:
        return None

    if isinstance(x, (Mapping, list, tuple, str, int, float, bool, Enum, SimpleNamespace)):
        out = ensure_dead_json(x)
        assert_dead_json(out, path="object-json")
        return out

    for attr in ("to_json", "__json__", "to_dict", "to_object_json"):
        fn = getattr(x, attr, None)
        if callable(fn):
            out = ensure_dead_json(fn())
            assert_dead_json(out, path="object-json")
            return out

    fn = getattr(x, "json", None)
    if callable(fn):
        serialized = fn()
        if not isinstance(serialized, str):
            raise ValueError("object-json: obj.json() must return a JSON string")
        try:
            parsed = json.loads(serialized)
        except Exception as exc:
            raise ValueError(
                f"object-json: obj.json() did not return parseable JSON: {exc}"
            ) from exc
        out = ensure_dead_json(parsed)
        assert_dead_json(out, path="object-json")
        return out

    if is_dataclass(x) and not isinstance(x, type):
        out = ensure_dead_json(asdict(x))
        assert_dead_json(out, path="object-json")
        return out

    raise ValueError(
        "object-json: cannot coerce value. Provide dead-JSON data, implement "
        "to_json()/__json__(), json() returning a JSON string, or use a dataclass."
    )


def coerce_str_list(x: Any) -> list[str]:
    """Canonical list[str] coercion for multi-choice micros."""
    if x is None:
        return []
    if isinstance(x, str):
        s = x.strip()
        return [] if s == "" else [s]
    if isinstance(x, (list, tuple)):
        out: list[str] = []
        for item in x:
            if not isinstance(item, str):
                raise ValueError(
                    "list[str] micro requires string values; "
                    f"got {type(item).__name__}"
                )
            if item.strip() == "":
                raise ValueError("list[str] micro does not allow blank option values")
            out.append(item)
        return out
    raise ValueError(f"cannot coerce {type(x).__name__} to list[str]")


__all__ = [
    "coerce_bool",
    "coerce_integer",
    "coerce_number",
    "coerce_object_json",
    "coerce_str",
    "coerce_str_list",
    "ensure_dead_json",
]
