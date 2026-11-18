from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


ValidatorResult = Tuple[bool, Optional[str]]


@dataclass(frozen=True)
class ArgCombo:
    args: Dict[str, Any]
    valid_examples: Tuple[Any, ...]
    invalid_examples: Tuple[Any, ...]
    modality: str


@dataclass
class ValidatorMeta:
    dotted_path: str
    fn: Callable[..., ValidatorResult]
    guidance_fn: Optional[Callable[..., Dict[str, Any]]] = None
    arg_combos: Tuple[ArgCombo, ...] = field(default_factory=tuple)
    description: Optional[str] = None


class _Registry:
    def __init__(self) -> None:
        self._validators: Dict[str, ValidatorMeta] = {}
        self._guidance: Dict[str, Callable[..., Dict[str, Any]]] = {}

    def register_validator(
        self,
        fn: Callable[..., ValidatorResult],
        *,
        arg_combos: Optional[Iterable[Dict[str, Any]]] = None,
        description: Optional[str] = None,
    ) -> ValidatorMeta:
        dotted = f"{fn.__module__}:{fn.__name__}"
        if dotted in self._validators:
            raise ValueError(f"Validator already registered: {dotted}")

        combos: List[ArgCombo] = []
        for raw in arg_combos or ():
            modality = str(raw.get("modality") or "").strip()
            if not modality:
                raise ValueError(f"validator {dotted} arg combo requires modality")
            combos.append(
                ArgCombo(
                    args=dict(raw.get("args") or {}),
                    valid_examples=tuple(raw.get("valid_examples") or ()),
                    invalid_examples=tuple(raw.get("invalid_examples") or ()),
                    modality=modality,
                )
            )

        meta = ValidatorMeta(
            dotted_path=dotted,
            fn=_enforce_contract(fn, dotted),
            arg_combos=tuple(combos),
            description=str(description) if description is not None else None,
        )
        if dotted in self._guidance:
            meta.guidance_fn = self._guidance[dotted]
        self._validators[dotted] = meta
        return meta

    def register_guidance(
        self,
        *,
        module: str,
        target_name: str,
        fn: Callable[..., Dict[str, Any]],
    ) -> None:
        key = f"{module}:{target_name}"

        @wraps(fn)
        def wrapped(**kwargs: Any) -> Dict[str, Any]:
            out = fn(**kwargs)
            if not isinstance(out, dict):
                raise TypeError(f"Guidance for {key} must return a dict")
            message = out.get("message")
            if not isinstance(message, str) or not message.strip():
                raise TypeError(
                    f"Guidance for {key} must return a non-blank 'message' string"
                )
            return out

        self._guidance[key] = wrapped
        if key in self._validators:
            self._validators[key].guidance_fn = wrapped

    def get(self, dotted_path: str) -> ValidatorMeta:
        try:
            return self._validators[str(dotted_path)]
        except KeyError as exc:
            raise KeyError(f"Unknown validator: {dotted_path}") from exc

    def all(self) -> List[ValidatorMeta]:
        return [self._validators[path] for path in sorted(self._validators)]

    def paths(self) -> Tuple[str, ...]:
        return tuple(sorted(self._validators))


registry = _Registry()


def validator(
    *,
    arg_combos: Optional[Iterable[Dict[str, Any]]] = None,
    description: Optional[str] = None,
):
    """Register ``fn(value, **args) -> (bool, str|None)`` with publication metadata."""

    def decorate(fn: Callable[..., ValidatorResult]):
        registry.register_validator(
            fn,
            arg_combos=arg_combos,
            description=description,
        )
        return fn

    return decorate


def guidance_for(target_name: str):
    """Register an args-only guidance function for a same-module validator."""

    def decorate(fn: Callable[..., Dict[str, Any]]):
        registry.register_guidance(
            module=fn.__module__,
            target_name=str(target_name),
            fn=fn,
        )
        return fn

    return decorate


def get_callable_by_path(path: str) -> Callable[..., Any]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"Bad callable path: {path!r}")
    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)
    if not module_name or not attr_path:
        raise ValueError(f"Bad callable path: {path!r}")
    obj: Any = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise ValueError(f"Resolved object is not callable for {path!r}")
    return obj


def run_validation_by_path(
    path: str,
    value: Any,
    **kwargs: Any,
) -> ValidatorResult:
    fn = get_callable_by_path(path)
    return _enforce_contract(fn, path)(value, **kwargs)


def build_guidance_by_path(path: str, **kwargs: Any) -> Dict[str, Any]:
    fn = get_callable_by_path(path)
    out = fn(**kwargs)
    if not isinstance(out, dict):
        raise TypeError(f"Guidance {path!r} must return a dict")
    message = out.get("message")
    if not isinstance(message, str) or not message.strip():
        raise TypeError(f"Guidance {path!r} must contain a non-blank message")
    return out


def all_validators() -> List[ValidatorMeta]:
    return registry.all()


def registered_validator_paths() -> Tuple[str, ...]:
    return registry.paths()


def assert_registered_validator_integrity() -> None:
    for meta in all_validators():
        if meta.guidance_fn is None:
            raise AssertionError(f"validator lacks guidance: {meta.dotted_path}")
        if not meta.description or not meta.description.strip():
            raise AssertionError(f"validator lacks description: {meta.dotted_path}")
        get_callable_by_path(meta.dotted_path)
        module, name = meta.dotted_path.split(":", 1)
        get_callable_by_path(f"{module}:{name}_guidance")


def _enforce_contract(
    fn: Callable[..., Any],
    label: str,
) -> Callable[..., ValidatorResult]:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> ValidatorResult:
        result = fn(*args, **kwargs)
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[0], bool)
            and (result[1] is None or isinstance(result[1], str))
        ):
            return result
        if isinstance(result, bool):
            raise TypeError(f"{label} must return (bool, str|None), got bare bool")
        raise TypeError(
            f"{label} must return (bool, str|None), got {type(result).__name__}: {result!r}"
        )

    return wrapped


__all__ = [
    "ArgCombo",
    "ValidatorMeta",
    "ValidatorResult",
    "all_validators",
    "assert_registered_validator_integrity",
    "build_guidance_by_path",
    "get_callable_by_path",
    "guidance_for",
    "registered_validator_paths",
    "registry",
    "run_validation_by_path",
    "validator",
]
