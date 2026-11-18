from __future__ import annotations

from typing import Any, Dict, Mapping

from __exceptions.engine import FatalEngineError
from _thinkengine._parsing.app_table_program_parser import DeadJSONError, assert_dead_json

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import RESERVED_PATCH_KEYS, _MISSING


_INCREMENTAL_MAPPING_UNDO_KIND_V1 = "__app_table_mapping_items_undo_v1__"
_APPEND_LIST_UNDO_KIND_V1 = "__app_table_list_append_undo_v1__"


def _apply_patch(state: Dict[str, Any], patch: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Apply a top-level patch into state, returning an undo patch.

    This remains the generic path for ordinary step-fn writes.
    """
    undo: Dict[str, Any] = {}
    for k, v in patch.items():
        if k in state:
            undo[k] = state[k]
        else:
            undo[k] = _MISSING
        state[k] = v
    return undo


def _apply_mapping_item_patch(
    state: Dict[str, Any],
    *,
    bucket_key: str,
    items: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Incrementally update a mapping-valued state bucket and return a JSON-safe undo patch.

    This is the hot-path helper for manual fills.

    Why:
      old manual fill path:
        new_bucket = dict(all_previous_form_fills)
        new_bucket.update(current_fill)
        _apply_patch(...)

      That is O(total historical manual fills) per accepted fill.

      new path:
        mutate only submitted datum ids
        record only previous values for those datum ids

      This is O(fields submitted this turn).

    Undo format is intentionally JSON-safe so engine snapshots remain stable.
    """
    key = str(bucket_key)
    if not items:
        return {}

    bucket = state.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        state[key] = bucket

    undo_items = []
    for raw_k, v in dict(items).items():
        k = str(raw_k)
        if k in bucket:
            undo_items.append({"k": k, "missing": False, "v": bucket[k]})
        else:
            undo_items.append({"k": k, "missing": True, "v": None})
        bucket[k] = v

    return {
        key: {
            "kind": _INCREMENTAL_MAPPING_UNDO_KIND_V1,
            "items": undo_items,
        }
    }


def _append_list_item_patch(
    state: Dict[str, Any],
    *,
    bucket_key: str,
    value: Any,
) -> Dict[str, Any]:
    """
    Append one item to a list-valued state bucket and return a tiny undo patch.

    This replaces the old pattern:

        new_list = list(old_list)
        new_list.append(value)
        _apply_patch(...)

    because that makes every undo record carry the whole previous list.

    Complexity:
        apply: O(1)
        undo: O(1) amortized, truncating to the previous length
        storage: O(1) metadata plus the appended value already being stored
    """
    key = str(bucket_key)
    bucket = state.get(key)
    if not isinstance(bucket, list):
        bucket = []
        state[key] = bucket

    previous_len = len(bucket)
    bucket.append(value)

    return {
        key: {
            "kind": _APPEND_LIST_UNDO_KIND_V1,
            "previous_len": previous_len,
        }
    }


def _undo_patch(state: Dict[str, Any], undo: Mapping[str, Any]) -> None:
    for k, prev in undo.items():
        if (
            isinstance(prev, Mapping)
            and str(prev.get("kind") or "") == _APPEND_LIST_UNDO_KIND_V1
        ):
            bucket = state.get(str(k))
            if not isinstance(bucket, list):
                state[str(k)] = []
                continue

            try:
                previous_len = max(0, int(prev.get("previous_len", 0) or 0))
            except Exception:
                previous_len = 0

            del bucket[previous_len:]
            continue

        if (
            isinstance(prev, Mapping)
            and str(prev.get("kind") or "") == _INCREMENTAL_MAPPING_UNDO_KIND_V1
        ):
            bucket = state.get(str(k))
            if not isinstance(bucket, dict):
                bucket = {}
                state[str(k)] = bucket

            for row in list(prev.get("items") or []):
                if not isinstance(row, Mapping):
                    continue
                kk = str(row.get("k") or "")
                if not kk:
                    continue
                if bool(row.get("missing", False)):
                    bucket.pop(kk, None)
                else:
                    bucket[kk] = row.get("v")
            continue

        if prev is _MISSING:
            state.pop(k, None)
        else:
            state[k] = prev


def _validate_patch(app_step: Any, patch: dict) -> None:
    # Membrane: step-fn patch must be dead JSON.
    try:
        assert_dead_json(patch, path=f"stepfn_patch[{app_step.step_fn}]")
    except DeadJSONError as e:
        raise FatalEngineError(f"{app_step.step_fn} returned non-JSON patch: {e}") from e

    # Prevent step fns from mutating engine-owned keys.
    bad = sorted([k for k in patch.keys() if str(k) in RESERVED_PATCH_KEYS])
    if bad:
        raise FatalEngineError(
            f"{app_step.step_fn} attempted to patch reserved engine keys: {bad}. "
            f"Reserved keys are engine-owned; use the returned multiframespec to drive forms."
        )


__all__ = [
    "_apply_patch",
    "_apply_mapping_item_patch",
    "_append_list_item_patch",
    "_undo_patch",
    "_validate_patch",
]