
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Set, Tuple


StepFnReturn = Tuple[Dict[str, Any], Any] | Dict[str, Any]


@dataclass(frozen=True)
class StepFnSpec:
    name: str
    fn: Callable[..., StepFnReturn]
    required_args: Set[str]
    optional_args: Set[str] = None
    raise_if_extra_args: bool = True


    def validate_args(self, fn_args: Mapping[str, Any]) -> None:
        if not isinstance(fn_args, Mapping):
            raise TypeError(f"{self.name}: fn_args must be a mapping")

        missing = [k for k in self.required_args if k not in fn_args]
        if missing:
            raise ValueError(f"{self.name}: missing required args: {sorted(missing)}")

        optionals = self.optional_args or {}
        unknown = [k for k in fn_args.keys() if k not in self.required_args and k not in optionals]
        if unknown and self.raise_if_extra_args:
            raise ValueError(f"{self.name}: unknown args: {sorted(unknown)}")


class StepFnregistry:
    """
    Forever-scalable registry of step fns.

    Design:
      - static dict mapping names to StepFnSpec
      - constant-time lookups
      - cheap validation

    Safety:
      - registration does NOT silently override by default
      - explicit overwrite is available for tests / controlled hot-reload scenarios
    """

    _REG: Dict[str, StepFnSpec] = {}

    @classmethod
    def clear(cls) -> None:
        cls._REG.clear()

    @classmethod
    def has(cls, name: str) -> bool:
        return str(name).strip() in cls._REG

    @classmethod
    def register(
        cls,
        *,
        name: str,
        fn: Callable[..., StepFnReturn],
        required_args: Optional[Set[str]] = None,
        optional_args: Optional[Set[str]] = None,
        overwrite: bool = False,
        raise_if_extra_args: bool = True,
    ) -> None:
        
        nm = str(name).strip()
        if not nm:
            raise ValueError("step fn name must be non-empty")
        if not callable(fn):
            raise TypeError("step fn must be callable")
        if nm in cls._REG and not overwrite:
            raise ValueError(f"step fn already registered: {nm}")

        cls._REG[nm] = StepFnSpec(
            name=nm,
            fn=fn,
            required_args=set(required_args or set()),
            optional_args=set(optional_args or set()),
            raise_if_extra_args=bool(raise_if_extra_args),
        )

    @classmethod
    def get(cls, name: str) -> StepFnSpec:
        nm = str(name).strip()
        try:
            return cls._REG[nm]
        except KeyError as e:
            raise KeyError(f"unknown step fn: {nm}") from e

    @classmethod
    def list_names(cls) -> list[str]:
        return sorted(cls._REG.keys())


def register_step_fn(
    name: str,
    *,
    required_args: Optional[Set[str]] = None,
    optional_args: Optional[Set[str]] = None,
    overwrite: bool = False,
) -> Callable[[Callable[..., StepFnReturn]], Callable[..., StepFnReturn]]:
    """
    Decorator:
        @register_step_fn("my_step", required_args={"x"}, optional_args={"y"})
        def my_step(state, x, y=None): ...

    overwrite=True is intended primarily for test environments that reload modules.
    """
    def _decorator(fn: Callable[..., StepFnReturn]) -> Callable[..., StepFnReturn]:
        StepFnregistry.register(
            name=name,
            fn=fn,
            required_args=required_args,
            optional_args=optional_args,
            overwrite=overwrite,
        )
        return fn

    return _decorator
