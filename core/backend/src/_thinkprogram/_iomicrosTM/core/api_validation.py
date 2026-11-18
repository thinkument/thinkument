from __future__ import annotations

"""Engine-facing datum/micro semantic validation.

The concrete datum owns its active validators.  The micro registry owns the
platform-known/projectable validator capability sheet V_m. Runtime legality
checks apply to built-in _iomicrosTM validators only; application-owned
validators remain valid executable semantics without central registration.
"""

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from __exceptions.engine import ValidatorReturnContractError
from _thinkprogram._iomicrosTM.core.micro_registry import (
    get_micro_type_definition,
    is_validator_allowed_for_micro,
)
from _thinkprogram._iomicrosTM.core.value_semantics import is_blank_value


ValidatorItem = Tuple[Callable[..., Any], str, Dict[str, Any]]


def resolve_dotpath_callable(path: str) -> Callable[..., Any]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"Bad callable path: {path!r}")

    if ":" in path:
        module_name, attr_path = path.split(":", 1)
    else:
        module_name, attr_path = path.rsplit(".", 1)

    module_name = module_name.strip()
    attr_path = attr_path.strip()
    if not module_name or not attr_path:
        raise ValueError(f"Bad callable path: {path!r}")

    try:
        obj: Any = importlib.import_module(module_name)
    except Exception as exc:
        raise ValueError(
            f"Cannot import module {module_name!r} for {path!r}: {exc}"
        ) from exc

    try:
        for part in attr_path.split("."):
            obj = getattr(obj, part)
    except Exception as exc:
        raise ValueError(
            f"Attribute path {attr_path!r} not found in {module_name!r} "
            f"for {path!r}: {exc}"
        ) from exc

    if not callable(obj):
        raise ValueError(f"Resolved object is not callable for {path!r}")
    return obj


def _callable_label(fn: Callable[..., Any]) -> str:
    module = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if module and name and "<locals>" not in name:
        return f"{module}:{name}"
    return getattr(fn, "__name__", "<callable>")


def _normalize_validator_result(
    result: Any,
    *,
    context: str,
    label: str,
) -> Tuple[bool, Optional[str]]:
    if isinstance(result, tuple) and len(result) == 2:
        ok, message = result
        if isinstance(ok, bool) and (message is None or isinstance(message, str)):
            return ok, message
        raise ValidatorReturnContractError(
            context=context,
            validator_label=label,
            got_type=f"({type(ok).__name__}, {type(message).__name__})",
            value_repr=repr(result),
        )

    raise ValidatorReturnContractError(
        context=context,
        validator_label=label,
        got_type=type(result).__name__,
        value_repr=repr(result),
    )


def _extract_kwargs(spec: Mapping[str, Any]) -> Dict[str, Any]:
    for key in ("args", "kwargs", "mapped_args"):
        value = spec.get(key)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise TypeError(f"validator {key!r} must be a mapping")
        return dict(value)
    return {}


def _normalize_validator_items(raw: Any) -> List[ValidatorItem]:
    items: List[ValidatorItem] = []

    def add_one(spec: Any) -> None:
        if isinstance(spec, str):
            items.append((resolve_dotpath_callable(spec), spec, {}))
            return

        if callable(spec):
            items.append((spec, _callable_label(spec), {}))
            return

        if isinstance(spec, Mapping):
            if any(key in spec for key in ("path", "dotted", "callable")):
                kwargs = _extract_kwargs(spec)
                if "path" in spec or "dotted" in spec:
                    raw_label = spec.get("path", spec.get("dotted"))
                    label = str(raw_label or "").strip()
                    if not label:
                        raise ValueError("validator path must be non-empty")
                    items.append((resolve_dotpath_callable(label), label, kwargs))
                    return

                fn = spec.get("callable")
                if not callable(fn):
                    raise TypeError("validator 'callable' must be callable")
                items.append((fn, _callable_label(fn), kwargs))
                return

            if len(spec) == 1:
                [(single_key, maybe_kwargs)] = list(spec.items())
                label = str(single_key)
                fn = resolve_dotpath_callable(label)
                if maybe_kwargs is None:
                    kwargs = {}
                elif isinstance(maybe_kwargs, Mapping):
                    kwargs = dict(maybe_kwargs)
                else:
                    raise TypeError("validator shorthand expects a mapping of args")
                items.append((fn, label, kwargs))
                return

        raise TypeError(f"Unsupported validator spec type: {type(spec).__name__}")

    if raw in (None, [], (), False):
        return items

    specs = raw if isinstance(raw, (list, tuple)) else [raw]
    for spec in specs:
        add_one(spec)
    return items


def _invoke_validator(
    fn: Callable[..., Any],
    self_obj: "DatumFillValidator",
    value: Any,
    kwargs: Dict[str, Any],
    *,
    context: str,
    label: str,
) -> Any:
    """Bind once, invoke once.

    Signature probing happens with ``inspect.Signature.bind`` before execution,
    so a TypeError raised *inside* validator code is never mistaken for an
    alternate supported calling convention and never causes a second call.
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        signature = None

    candidates = (
        ((value,), kwargs),
        ((self_obj, value), kwargs),
    )
    if context == "macro":
        candidates = tuple(reversed(candidates))

    binding_errors: List[str] = []
    for args, call_kwargs in candidates:
        if signature is not None:
            try:
                signature.bind(*args, **call_kwargs)
            except TypeError as exc:
                binding_errors.append(str(exc))
                continue
        return fn(*args, **call_kwargs)

    details = "; ".join(binding_errors) or "no supported signature"
    raise TypeError(
        f"validator {label!r} cannot be invoked as a {context} validator: {details}"
    )


def validate_micro_validator_legality(micro_spec: Mapping[str, Any]) -> None:
    """Validate platform-owned validator/type compatibility.

    The central table is intentionally not a closed-world allow-list for app
    validators. Only validators shipped from ``_thinkprogram._iomicrosTM.validators``
    are required to appear in the micro type capability sheet.
    """
    micro_type = str(micro_spec.get("type") or "text").strip().lower() or "text"
    try:
        get_micro_type_definition(micro_type)
    except KeyError as exc:
        raise ValueError(f"Unknown micro type {micro_type!r}") from exc

    raw = micro_spec.get(
        "validators",
        micro_spec.get("validator", micro_spec.get("micro_field_validation_lambdas")),
    )
    for fn, label, _kwargs in _normalize_validator_items(raw):
        canonical = _callable_label(fn)

        # Application-owned validators are ordinary executable dataspec
        # semantics. They cannot require central registry enumeration.
        if not canonical.startswith("_thinkprogram._iomicrosTM.validators."):
            continue

        if not is_validator_allowed_for_micro(
            micro_type=micro_type,
            validator_path=canonical,
        ):
            raise ValueError(
                f"Validator {label!r} is not allowed for micro type {micro_type!r}. "
                "Add it to that micro type's ValidatorPolicy capability sheet "
                "before activating it on a dataspec micro."
            )


@dataclass(frozen=True)
class DatumFillValidator:
    id: str
    title: str
    micros: Sequence[Mapping[str, Any]]
    macro_validation_lambdas: Any = None
    enforce_validator_legality: bool = False
    enforce_known_micros: bool = False

    def _micro_specs(self) -> List[Mapping[str, Any]]:
        return [micro for micro in (self.micros or []) if isinstance(micro, Mapping)]

    def _required_micro_names(self) -> List[str]:
        micros = self._micro_specs()
        if not micros:
            return ["value"]
        return [
            str(micro.get("name") or "value")
            for micro in micros
            if micro.get("required", True) is not False
        ]

    def _assert_legality(self) -> None:
        if not self.enforce_validator_legality:
            return
        for micro in self._micro_specs():
            validate_micro_validator_legality(micro)

    def parse_and_validate_fill(
        self,
        *,
        raw: Any,
        enforce_required_micros: bool = True,
        enforce_micro_lambdas: bool = True,
        enforce_macro_lambdas: bool = True,
    ) -> Any:
        micros = self._micro_specs()
        required = self._required_micro_names()
        self._assert_legality()

        if isinstance(raw, Mapping):
            macro_map: Dict[str, Any] = dict(raw)
        else:
            names = [str(m.get("name") or "value") for m in micros] if micros else ["value"]
            if names == ["value"]:
                macro_map = {"value": raw}
            else:
                raise ValueError(
                    f"Expected mapping macro fill for datum {self.id!r}; "
                    f"got {type(raw).__name__}"
                )

        if self.enforce_known_micros:
            known = {str(m.get("name") or "value") for m in micros} if micros else {"value"}
            extras = sorted(str(key) for key in macro_map if str(key) not in known)
            if extras:
                raise ValueError(f"Unknown micros for datum {self.id!r}: {extras}")

        if enforce_required_micros:
            missing = [name for name in required if is_blank_value(macro_map.get(name))]
            if missing:
                raise ValueError(f"Missing required micros: {missing} -- got: {raw}")

        if enforce_micro_lambdas:
            errors: List[str] = []
            for micro in micros:
                name = str(micro.get("name") or "value")
                required_here = micro.get("required", True) is not False
                if name not in macro_map:
                    # Required absence already failed above in full mode. Optional
                    # absence is semantically "not supplied" and has nothing to validate.
                    continue
                if is_blank_value(macro_map.get(name)):
                    # In partial mode blanks are ignored for every micro. In full
                    # mode a required blank already failed; an optional blank is absence.
                    if not enforce_required_micros or not required_here:
                        continue

                raw_validators = micro.get(
                    "validators",
                    micro.get("validator", micro.get("micro_field_validation_lambdas")),
                )
                for index, (fn, label, kwargs) in enumerate(
                    _normalize_validator_items(raw_validators),
                    start=1,
                ):
                    result = _invoke_validator(
                        fn,
                        self,
                        macro_map.get(name),
                        kwargs,
                        context="micro",
                        label=label,
                    )
                    ok, message = _normalize_validator_result(
                        result,
                        context="micro",
                        label=label,
                    )
                    if not ok:
                        errors.append(
                            f"{name}: {message or f'validator[{index}] {label} failed'}"
                        )
            if errors:
                raise ValueError("; ".join(errors))

        if enforce_macro_lambdas and self.macro_validation_lambdas not in (None, [], (), False):
            if not enforce_required_micros:
                if not any(not is_blank_value(value) for value in macro_map.values()):
                    return raw

            errors: List[str] = []
            for index, (fn, label, kwargs) in enumerate(
                _normalize_validator_items(self.macro_validation_lambdas),
                start=1,
            ):
                result = _invoke_validator(
                    fn,
                    self,
                    macro_map,
                    kwargs,
                    context="macro",
                    label=label,
                )
                ok, message = _normalize_validator_result(
                    result,
                    context="macro",
                    label=label,
                )
                if not ok:
                    errors.append(message or f"macro validator[{index}] {label} failed")
            if errors:
                raise ValueError("; ".join(errors))

        return raw


def validate_filled_macros_against_datums(
    datums: Sequence[Mapping[str, Any]],
    macros: Sequence[Mapping[str, Any]],
    *,
    enforce_required_micros: bool = True,
    enforce_micro_lambdas: bool = True,
    enforce_macro_lambdas: bool = True,
    enforce_validator_legality: bool = True,
    enforce_known_micros: bool = False,
) -> None:
    datums_list = list(datums or [])
    macros_list = list(macros or [])
    if len(datums_list) != len(macros_list):
        raise ValueError(
            f"datums/macros length mismatch: {len(datums_list)} vs {len(macros_list)}"
        )

    for index, (datum, macro) in enumerate(zip(datums_list, macros_list)):
        validator = DatumFillValidator(
            id=str(datum.get("datum_id") or datum.get("id") or f"datum_{index}"),
            title=str(datum.get("title") or datum.get("id") or f"datum_{index}"),
            micros=list(datum.get("micro_input_fields") or datum.get("micros") or []),
            macro_validation_lambdas=datum.get("macro_validation_lambdas"),
            enforce_validator_legality=bool(enforce_validator_legality),
            enforce_known_micros=bool(enforce_known_micros),
        )
        validator.parse_and_validate_fill(
            raw=dict(macro),
            enforce_required_micros=enforce_required_micros,
            enforce_micro_lambdas=enforce_micro_lambdas,
            enforce_macro_lambdas=enforce_macro_lambdas,
        )


__all__ = [
    "DatumFillValidator",
    "resolve_dotpath_callable",
    "validate_filled_macros_against_datums",
    "validate_micro_validator_legality",
]