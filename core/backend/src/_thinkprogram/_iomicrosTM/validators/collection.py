from __future__ import annotations

from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


def _list(value: Any) -> list[Any] | None:
    value = unwrap(value)
    return value if isinstance(value, list) else None


@validator(
    arg_combos=[{
        "args": {"min_items": 1},
        "valid_examples": [["a"], [1, 2], {"__boxed__": True, "value": ["x"]}],
        "invalid_examples": [[], None, "a"],
        "modality": "multi_select",
    }],
    description="List must contain at least N items.",
)
def min_items(value: Any, *, min_items: int) -> tuple[bool, str | None]:
    items = _list(value)
    minimum = int(min_items)
    ok = items is not None and minimum >= 0 and len(items) >= minimum
    return ok, None if ok else f"must contain at least {minimum} items"


@guidance_for("min_items")
def min_items_guidance(*, min_items: int) -> Dict[str, Any]:
    minimum = int(min_items)
    return {
        "message": f"Choose at least {minimum} items.",
        "args": {"min_items": minimum},
        "modality": "multi_select",
    }


@validator(
    arg_combos=[{
        "args": {"max_items": 2},
        "valid_examples": [[], ["a"], [1, 2], {"__boxed__": True, "value": ["x", "y"]}],
        "invalid_examples": [[1, 2, 3], None, "a"],
        "modality": "multi_select",
    }],
    description="List must contain at most N items.",
)
def max_items(value: Any, *, max_items: int) -> tuple[bool, str | None]:
    items = _list(value)
    maximum = int(max_items)
    ok = items is not None and maximum >= 0 and len(items) <= maximum
    return ok, None if ok else f"must contain at most {maximum} items"


@guidance_for("max_items")
def max_items_guidance(*, max_items: int) -> Dict[str, Any]:
    maximum = int(max_items)
    return {
        "message": f"Choose no more than {maximum} items.",
        "args": {"max_items": maximum},
        "modality": "multi_select",
    }


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [[], ["a"], ["a", "b"], {"__boxed__": True, "value": [1, 2]}],
        "invalid_examples": [["a", "a"], [1, 1], None, "a"],
        "modality": "multi_select",
    }],
    description="List items must be pairwise distinct by equality.",
)
def unique_items(value: Any) -> tuple[bool, str | None]:
    items = _list(value)
    if items is None:
        return False, "must be a list"
    for index, item in enumerate(items):
        if any(item == prior for prior in items[:index]):
            return False, "list items must be unique"
    return True, None


@guidance_for("unique_items")
def unique_items_guidance() -> Dict[str, Any]:
    return {"message": "Do not select the same item twice.", "modality": "multi_select"}


__all__ = [
    "min_items",
    "min_items_guidance",
    "max_items",
    "max_items_guidance",
    "unique_items",
    "unique_items_guidance",
]
