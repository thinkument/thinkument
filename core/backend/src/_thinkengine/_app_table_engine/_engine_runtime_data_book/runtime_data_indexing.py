from __future__ import annotations

"""
Runtime Write Index V1
======================

This module is the App Table runtime's history/query spine.

Purpose
-------
Let step functions query prior runtime writes without scanning:
  - the whole program
  - all prior outputs
  - all prior form specs
  - all prior fill payloads
  - arbitrary nested JSON blobs

Core law
--------
The index stores metadata, shallow bounded scalar arg tokens, and write
references. It does NOT copy large write payloads into history.

Therefore:
  - query planning is fast
  - snapshot growth is proportional to step/write metadata, not value size
  - exact historical giant payload replay is intentionally not promised
  - exact scalar-arg equality can be supported without storing giant strings

If an app needs exact historical large payload replay, the app should write a
small stable handle into state, such as an artifact id, blob id, or content uri.
"""

import hashlib
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)


INDEX_VERSION_V1 = 1

DEFAULT_MAX_SHALLOW_ARG_KEYS_V1 = 64
DEFAULT_MAX_PREVIEW_CHARS_V1 = 160
DEFAULT_MAX_PREDICATE_EVALS_V1 = 4096
DEFAULT_MAX_RESULTS_V1 = 4096

WRITE_KIND_STATE = "state"
WRITE_KIND_FORM_PREFILL = "form_prefill"
WRITE_KIND_FORM_FILL = "form_fill"
WRITE_KIND_DATUM_LIFECYCLE = "datum_lifecycle"

_LIST_POSITIONS_KEY = "list_positions"
_INVOCATION_ORDER_POSITIONS_KEY = "__invocation_order__"
_INVOCATION_ORDER_DEAD_COUNT_KEY = (
    "__invocation_order_dead_count__"
)

_INVOCATION_ORDER_COMPACT_MIN_DEAD_V1 = 256
_INVOCATION_ORDER_COMPACT_DEAD_RATIO_V1 = 2

_MAX_INDEXED_SCALAR_STRING_PREFIX_CHARS_V1 = 64

JSON_SCALAR_TYPES = (
    str,
    int,
    float,
    bool,
    type(None),
)


# ---------------------------------------------------------------------------
# Durable snapshot projection policy
# ---------------------------------------------------------------------------
#
# The live runtime write index may carry private helper structures used for
# mutation speed:
#
#   - list_positions
#   - tombstone / tombstones
#   - sidecar / sidecars
#   - raw_value
#
# Durable snapshots must not persist those structures.
#
# Important performance law:
#
#   Do NOT recursively sanitize the entire runtime index.
#   Do NOT recursively sanitize the hot invocation/write-event tables.
#
# The runtime index contains large secondary index tables and large metadata row
# tables. A full recursive walk makes snapshot/export/persist cost proportional
# to every nested index table even when there is nothing dangerous to remove.
# That violates the complexity budget sheets.
#
# Instead, snapshot projection is schema-aware:
#
#   - drop known private top-level containers;
#   - compact invocation_order;
#   - sanitize only legacy/hostile row-shaped tables that may carry sidecars;
#   - shallow-preserve ordinary secondary indexes;
#   - shallow-preserve invocations/write_events because this module owns their
#     metadata-only schema.
#
_RUNTIME_INDEX_SNAPSHOT_TOP_LEVEL_DROP_KEYS_V1 = frozenset(
    {
        _LIST_POSITIONS_KEY,
        "sidecar",
        "sidecars",
        "tombstone",
        "tombstones",
        "raw_value",
    }
)


_RUNTIME_INDEX_SNAPSHOT_ROW_DROP_KEYS_V1 = frozenset(
    {
        _LIST_POSITIONS_KEY,
        "sidecar",
        "sidecars",
        "tombstone",
        "tombstones",
        "raw_value",
    }
)


# Only these row-shaped tables get defensive deep row sanitization.
#
# Do NOT include "invocations" or "write_events" here.
#
# Those tables are large hot-path metadata tables produced by this module. Deep
# copying/sanitizing them on every snapshot/export is the bottleneck that pushed
# the existing complexity suite over budget.
#
# If a future production writer starts storing sidecars in invocation/write-event
# rows, fix that writer. Do not make the snapshot boundary pay a full recursive
# tax over the hottest metadata tables.
_RUNTIME_INDEX_DEEP_SANITIZE_ROW_TABLE_KEYS_V1 = frozenset(
    {
        "by_ref",
        "writes",
        "rows",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeWriteQueryV1:
    public_step_name: Optional[str] = None
    step_fn: Optional[str] = None
    last_k_invocations: Optional[int] = None

    arg_name: Optional[str] = None
    any_arg_names: Tuple[str, ...] = ()
    arg_path: Optional[str] = None
    arg_value_equals: Any = None
    has_arg_value_equals: bool = False

    arg_predicate: Optional[
        Callable[[Any], bool]
    ] = None
    predicate_arg_name: Optional[str] = None
    max_predicate_evals: int = (
        DEFAULT_MAX_PREDICATE_EVALS_V1
    )

    write_kinds: Tuple[str, ...] = ()
    max_results: int = DEFAULT_MAX_RESULTS_V1
    include_values: bool = False


def _fresh_index_v1() -> Dict[str, Any]:
    return {
        "v": INDEX_VERSION_V1,
        "next_seq": 1,
        "next_event_id": 1,
        "invocations": {},
        "invocation_order": [],
        _INVOCATION_ORDER_DEAD_COUNT_KEY: 0,
        "by_public_step_name": {},
        "by_step_fn": {},
        "by_arg_name": {},
        "by_arg_path_value": {},
        "write_events": {},
        "events_by_seq": {},
        "events_by_public_step_name": {},
        "events_by_step_fn": {},
        "events_by_write_kind": {},
        _LIST_POSITIONS_KEY: {},
    }


def ensure_runtime_write_index_v1(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    raw = state.get(KEY_RUNTIME_WRITE_INDEX)
    if (
        isinstance(raw, Mapping)
        and int(raw.get("v", 0) or 0)
        == INDEX_VERSION_V1
    ):
        idx = raw  # type: ignore[assignment]

        if not isinstance(
            idx.get(_LIST_POSITIONS_KEY),
            dict,
        ):
            idx[_LIST_POSITIONS_KEY] = {}

        if (
            _INVOCATION_ORDER_DEAD_COUNT_KEY
            not in idx
        ):
            idx[
                _INVOCATION_ORDER_DEAD_COUNT_KEY
            ] = 0

        return idx  # type: ignore[return-value]

    idx = _fresh_index_v1()
    state[KEY_RUNTIME_WRITE_INDEX] = idx
    return idx


def _coerce_nonnegative_int(
    value: Any,
    *,
    default: int,
) -> int:
    if value is None:
        return max(0, int(default))
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


def _positions_root(
    idx: Dict[str, Any],
) -> Dict[str, Any]:
    root = idx.get(_LIST_POSITIONS_KEY)
    if not isinstance(root, dict):
        root = {}
        idx[_LIST_POSITIONS_KEY] = root
    return root


def _rebuild_positions_for_values(
    values: Sequence[Any],
) -> Dict[str, int]:
    out: Dict[str, int] = {}

    for i, raw in enumerate(values):
        if raw is None:
            continue

        try:
            out[str(int(raw))] = i
        except Exception:
            continue

    return out


def _invocation_order_dead_count_v1(
    idx: Mapping[str, Any],
) -> int:
    try:
        return max(
            0,
            int(
                idx.get(
                    _INVOCATION_ORDER_DEAD_COUNT_KEY,
                    0,
                )
                or 0
            ),
        )
    except Exception:
        return 0


def _set_invocation_order_dead_count_v1(
    idx: Dict[str, Any],
    count: int,
) -> None:
    idx[_INVOCATION_ORDER_DEAD_COUNT_KEY] = max(
        0,
        int(count),
    )


def _order_positions(
    idx: Dict[str, Any],
    order: List[Any],
) -> Dict[str, int]:
    root = _positions_root(idx)
    pos = root.get(
        _INVOCATION_ORDER_POSITIONS_KEY
    )
    dead = _invocation_order_dead_count_v1(idx)

    # With tombstones, the live sidecar has one entry per live slot rather
    # than one entry per physical list slot.
    if (
        not isinstance(pos, dict)
        or len(pos) + dead != len(order)
    ):
        pos = _rebuild_positions_for_values(
            order
        )
        root[
            _INVOCATION_ORDER_POSITIONS_KEY
        ] = pos

        # Repair stale legacy/malformed dead-count metadata while rebuilding.
        _set_invocation_order_dead_count_v1(
            idx,
            max(0, len(order) - len(pos)),
        )

    return pos  # type: ignore[return-value]


def _compact_invocation_order_v1(
    idx: Dict[str, Any],
    *,
    force: bool = False,
) -> None:
    """
    Remove chronological-order tombstones and rebuild its position sidecar.

    Middle deletion marks one slot dead in O(1). Compaction occurs only when
    enough dead slots have accumulated, giving amortized linear maintenance
    rather than rebuilding the complete order after every removal.
    """
    order = idx.get("invocation_order")
    if not isinstance(order, list):
        idx["invocation_order"] = []
        _set_invocation_order_dead_count_v1(
            idx,
            0,
        )
        _positions_root(idx)[
            _INVOCATION_ORDER_POSITIONS_KEY
        ] = {}
        return

    dead = _invocation_order_dead_count_v1(
        idx
    )
    if dead <= 0:
        return

    should_compact = force or (
        dead
        >= _INVOCATION_ORDER_COMPACT_MIN_DEAD_V1
        and (
            dead
            * _INVOCATION_ORDER_COMPACT_DEAD_RATIO_V1
            >= len(order)
        )
    )
    if not should_compact:
        return

    invocations = idx.get("invocations")
    live_invocations = (
        invocations
        if isinstance(invocations, Mapping)
        else {}
    )

    compacted: List[int] = []
    for raw in order:
        if raw is None:
            continue

        try:
            seq = int(raw)
        except Exception:
            continue

        # Defensive filtering: only live invocation rows belong in canonical
        # chronological order.
        if str(seq) not in live_invocations:
            continue

        compacted.append(seq)

    idx["invocation_order"] = compacted
    _set_invocation_order_dead_count_v1(
        idx,
        0,
    )
    _positions_root(idx)[
        _INVOCATION_ORDER_POSITIONS_KEY
    ] = _rebuild_positions_for_values(
        compacted
    )


def _bucket_positions_root(
    idx: Dict[str, Any],
    bucket_name: str,
) -> Dict[str, Any]:
    root = _positions_root(idx)
    bucket_pos = root.get(bucket_name)

    if not isinstance(bucket_pos, dict):
        bucket_pos = {}
        root[bucket_name] = bucket_pos

    return bucket_pos


def _bucket_key_positions(
    idx: Dict[str, Any],
    *,
    bucket_name: str,
    key: str,
    values: List[Any],
) -> Dict[str, int]:
    bucket_pos = _bucket_positions_root(
        idx,
        bucket_name,
    )
    pos = bucket_pos.get(key)

    if (
        not isinstance(pos, dict)
        or len(pos) != len(values)
    ):
        pos = _rebuild_positions_for_values(
            values
        )
        bucket_pos[key] = pos

    return pos  # type: ignore[return-value]


def _append_invocation_order(
    idx: Dict[str, Any],
    value: int,
) -> None:
    order = idx.setdefault(
        "invocation_order",
        [],
    )
    if not isinstance(order, list):
        order = []
        idx["invocation_order"] = order
        _set_invocation_order_dead_count_v1(
            idx,
            0,
        )

    pos = _order_positions(idx, order)
    value_i = int(value)
    value_s = str(value_i)

    if value_s in pos:
        return

    pos[value_s] = len(order)
    order.append(value_i)


def _remove_invocation_order_value(
    idx: Dict[str, Any],
    value: int,
) -> None:
    """
    Remove one invocation from semantic chronological order.

    Tail removal:
        O(1), including trimming already-dead tail slots.

    Middle removal:
        O(1) by tombstoning the located slot.

    Compaction:
        Occasional O(n), triggered only after substantial dead accumulation.
        Therefore repeated middle deletion is amortized linear rather than
        quadratic.
    """
    order = idx.setdefault(
        "invocation_order",
        [],
    )
    if not isinstance(order, list) or not order:
        return

    value_i = int(value)
    value_s = str(value_i)

    pos = _order_positions(idx, order)
    current_pos = pos.get(value_s)

    if (
        current_pos is None
        or current_pos < 0
        or current_pos >= len(order)
    ):
        return

    # Remove membership immediately. No later lookup should find this seq.
    pos.pop(value_s, None)

    if current_pos == len(order) - 1:
        order.pop()

        dead = _invocation_order_dead_count_v1(
            idx
        )

        # Tombstones at the new tail can now be discarded cheaply.
        while order and order[-1] is None:
            order.pop()
            if dead > 0:
                dead -= 1

        _set_invocation_order_dead_count_v1(
            idx,
            dead,
        )
        return

    # Stable chronological order forbids swap-pop. Leave a dead slot instead.
    order[current_pos] = None
    _set_invocation_order_dead_count_v1(
        idx,
        _invocation_order_dead_count_v1(idx)
        + 1,
    )

    _compact_invocation_order_v1(idx)


def _append_index_list(
    idx: Dict[str, Any],
    bucket_name: str,
    key: str,
    value: int,
) -> None:
    bucket = idx.setdefault(
        bucket_name,
        {},
    )
    if not isinstance(bucket, dict):
        bucket = {}
        idx[bucket_name] = bucket

    key_s = str(key)
    arr = bucket.get(key_s)
    if not isinstance(arr, list):
        arr = []
        bucket[key_s] = arr

    pos = _bucket_key_positions(
        idx,
        bucket_name=bucket_name,
        key=key_s,
        values=arr,
    )
    value_i = int(value)
    value_s = str(value_i)

    if value_s in pos:
        return

    pos[value_s] = len(arr)
    arr.append(value_i)


def _remove_index_list_value(
    idx: Dict[str, Any],
    bucket_name: str,
    key: str,
    value: int,
) -> None:
    """
    Remove a value from an unordered secondary membership bucket.

    Fast path:
      - if the value is already at bucket tail, pop without building/rebuilding
        the position sidecar.
      - this matters after snapshot restore because sidecars are intentionally
        omitted from snapshots.

    Otherwise use swap-pop with the sidecar.
    """
    bucket = idx.setdefault(
        bucket_name,
        {},
    )
    if not isinstance(bucket, dict):
        return

    key_s = str(key)
    arr = bucket.get(key_s)
    if not isinstance(arr, list) or not arr:
        return

    value_i = int(value)
    value_s = str(value_i)

    try:
        if int(arr[-1]) == value_i:
            arr.pop()

            bucket_pos = (
                _bucket_positions_root(
                    idx,
                    bucket_name,
                )
            )
            pos = bucket_pos.get(key_s)
            if isinstance(pos, dict):
                pos.pop(value_s, None)

            if not arr:
                bucket.pop(key_s, None)
                bucket_pos.pop(
                    key_s,
                    None,
                )

            return
    except Exception:
        pass

    pos = _bucket_key_positions(
        idx,
        bucket_name=bucket_name,
        key=key_s,
        values=arr,
    )
    current_pos = pos.get(value_s)

    if (
        current_pos is None
        or current_pos < 0
        or current_pos >= len(arr)
    ):
        pos = _rebuild_positions_for_values(
            arr
        )
        _bucket_positions_root(
            idx,
            bucket_name,
        )[key_s] = pos

        current_pos = pos.get(value_s)
        if (
            current_pos is None
            or current_pos < 0
            or current_pos >= len(arr)
        ):
            return

    last_pos = len(arr) - 1
    last_value = int(arr[last_pos])

    if current_pos != last_pos:
        arr[current_pos] = last_value
        pos[str(last_value)] = current_pos

    arr.pop()
    pos.pop(value_s, None)

    if not arr:
        bucket.pop(key_s, None)
        bucket_pos = _bucket_positions_root(
            idx,
            bucket_name,
        )
        bucket_pos.pop(key_s, None)


def _pop_index_list(
    idx: Dict[str, Any],
    bucket_name: str,
    key: str,
) -> List[int]:
    bucket = idx.setdefault(
        bucket_name,
        {},
    )
    if not isinstance(bucket, dict):
        return []

    key_s = str(key)
    arr = bucket.pop(key_s, []) or []

    bucket_pos = _bucket_positions_root(
        idx,
        bucket_name,
    )
    bucket_pos.pop(key_s, None)

    if not isinstance(arr, list):
        return []

    out: List[int] = []
    for raw in arr:
        try:
            out.append(int(raw))
        except Exception:
            continue

    return out


def _bounded_string_token_v1(
    value: str,
) -> str:
    raw = str(value)
    digest = hashlib.sha256(
        raw.encode(
            "utf-8",
            errors="surrogatepass",
        )
    ).hexdigest()
    prefix = raw[
        :_MAX_INDEXED_SCALAR_STRING_PREFIX_CHARS_V1
    ]
    prefix = (
        prefix
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return (
        f"str:{len(raw)}:"
        f"{digest}:"
        f"{prefix}"
    )


def _scalar_token(
    value: Any,
) -> Optional[str]:
    if isinstance(value, bool):
        return (
            "bool:true"
            if value
            else "bool:false"
        )

    if value is None:
        return "null:null"

    if (
        isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return f"int:{value}"

    if isinstance(value, float):
        return f"float:{value!r}"

    if isinstance(value, str):
        return _bounded_string_token_v1(
            value
        )

    if isinstance(
        value,
        (bytes, bytearray),
    ):
        raw = bytes(value)
        digest = hashlib.sha256(
            raw
        ).hexdigest()
        return (
            f"bytes:{len(raw)}:"
            f"{digest}"
        )

    return None


def _preview_value(
    value: Any,
    *,
    max_chars: int = (
        DEFAULT_MAX_PREVIEW_CHARS_V1
    ),
) -> Dict[str, Any]:
    if isinstance(
        value,
        JSON_SCALAR_TYPES,
    ):
        text = repr(value)
        return {
            "kind": type(value).__name__,
            "is_scalar": True,
            "preview": (
                text[:max_chars]
                + (
                    "…"
                    if len(text) > max_chars
                    else ""
                )
            ),
        }

    if isinstance(value, Mapping):
        keys = [
            str(k)
            for k in list(value.keys())[:16]
        ]
        return {
            "kind": "dict",
            "is_scalar": False,
            "key_count_known": len(value),
            "keys_preview": keys,
            "preview": (
                f"<dict keys={len(value)}>"
            ),
        }

    if isinstance(value, list):
        return {
            "kind": "list",
            "is_scalar": False,
            "length_known": len(value),
            "preview": (
                f"<list len={len(value)}>"
            ),
        }

    return {
        "kind": type(value).__name__,
        "is_scalar": False,
        "preview": (
            f"<{type(value).__name__}>"
        ),
    }


def _iter_arg_index_tokens(
    fn_args: Mapping[str, Any],
    *,
    max_shallow_keys: int = (
        DEFAULT_MAX_SHALLOW_ARG_KEYS_V1
    ),
) -> Iterable[Tuple[str, str]]:
    for raw_name, value in dict(
        fn_args or {}
    ).items():
        name = str(raw_name)

        tok = _scalar_token(value)
        if tok is not None:
            yield name, tok
            continue

        if isinstance(value, Mapping):
            count = 0
            for raw_child_key, child_value in dict(
                value
            ).items():
                if count >= max_shallow_keys:
                    break

                child_tok = _scalar_token(
                    child_value
                )
                if child_tok is not None:
                    yield (
                        f"{name}.{str(raw_child_key)}",
                        child_tok,
                    )

                count += 1


def register_runtime_invocation_v1(
    state: Dict[str, Any],
    *,
    public_step_name: str,
    step_fn: str,
    fn_args: Mapping[str, Any],
    invocation_kind: str = "step_fn",
) -> int:
    idx = ensure_runtime_write_index_v1(
        state
    )

    seq = int(
        idx.get("next_seq") or 1
    )
    idx["next_seq"] = seq + 1

    psn = str(public_step_name)
    sfn = str(step_fn)

    arg_names = sorted(
        str(k)
        for k in dict(
            fn_args or {}
        ).keys()
    )
    arg_previews = {
        str(k): _preview_value(v)
        for k, v in dict(
            fn_args or {}
        ).items()
    }

    row = {
        "seq": seq,
        "public_step_name": psn,
        "step_fn": sfn,
        "invocation_kind": str(
            invocation_kind
        ),
        "arg_names": arg_names,
        "arg_previews": arg_previews,
    }

    invocations = idx.setdefault(
        "invocations",
        {},
    )
    invocations[str(seq)] = row
    _append_invocation_order(idx, seq)

    _append_index_list(
        idx,
        "by_public_step_name",
        psn,
        seq,
    )
    _append_index_list(
        idx,
        "by_step_fn",
        sfn,
        seq,
    )

    for arg_name in arg_names:
        _append_index_list(
            idx,
            "by_arg_name",
            arg_name,
            seq,
        )

    arg_path_value_keys: List[str] = []
    for arg_path, token in _iter_arg_index_tokens(
        fn_args
    ):
        composite = (
            f"{arg_path}\x1f{token}"
        )
        arg_path_value_keys.append(
            composite
        )
        _append_index_list(
            idx,
            "by_arg_path_value",
            composite,
            seq,
        )

    row["arg_path_value_keys"] = (
        arg_path_value_keys
    )

    return seq


def _resolve_ref_value(
    state: Mapping[str, Any],
    ref: Mapping[str, Any],
) -> Any:
    kind = str(ref.get("kind") or "")

    if kind == WRITE_KIND_STATE:
        key = str(ref.get("key") or "")
        return state.get(key)

    if kind == WRITE_KIND_DATUM_LIFECYCLE:
        bucket = state.get(
            KEY_DATUM_LIFECYCLE
        )
        if not isinstance(bucket, Mapping):
            return None

        form_id = str(
            ref.get("form_id") or ""
        )
        datum_id = str(
            ref.get("datum_id") or ""
        )

        forms = bucket.get("forms")
        if not isinstance(forms, Mapping):
            return None

        form_row = forms.get(form_id)
        if not isinstance(
            form_row,
            Mapping,
        ):
            return None

        datums = form_row.get("datums")
        if not isinstance(datums, Mapping):
            return None

        return datums.get(datum_id)

    if kind == WRITE_KIND_FORM_PREFILL:
        bucket = state.get(
            "form_prefills"
        )
    elif kind == WRITE_KIND_FORM_FILL:
        bucket = state.get(
            "form_fills"
        )
    else:
        return None

    if not isinstance(bucket, Mapping):
        return None

    datum_id = str(
        ref.get("datum_id") or ""
    )
    if not datum_id:
        return None

    return bucket.get(datum_id)


def record_runtime_writes_v1(
    state: Dict[str, Any],
    *,
    seq: int,
    writes: Sequence[Mapping[str, Any]],
) -> List[int]:
    idx = ensure_runtime_write_index_v1(
        state
    )
    inv = dict(
        idx.get("invocations", {}).get(
            str(seq)
        )
        or {}
    )
    if not inv:
        return []

    event_ids: List[int] = []

    for raw in writes:
        if not isinstance(raw, Mapping):
            continue

        event_id = int(
            idx.get("next_event_id") or 1
        )
        idx["next_event_id"] = (
            event_id + 1
        )

        write_kind = str(
            raw.get("write_kind")
            or raw.get("kind")
            or ""
        )
        key = str(
            raw.get("key")
            or raw.get("datum_id")
            or ""
        )

        value_preview = raw.get(
            "value_preview"
        )
        if not isinstance(
            value_preview,
            Mapping,
        ):
            if "value" in raw:
                value_preview = _preview_value(
                    raw.get("value")
                )
            else:
                value_preview = {
                    "preview": "<not captured>",
                    "is_scalar": False,
                }

        value_ref = raw.get("value_ref")
        if not isinstance(
            value_ref,
            Mapping,
        ):
            value_ref = {
                "kind": write_kind,
                "key": key,
            }

        row = {
            "event_id": event_id,
            "seq": int(seq),
            "public_step_name": str(
                inv.get(
                    "public_step_name"
                )
                or ""
            ),
            "step_fn": str(
                inv.get("step_fn") or ""
            ),
            "invocation_kind": str(
                inv.get(
                    "invocation_kind"
                )
                or ""
            ),
            "write_kind": write_kind,
            "key": key,
            "value_ref": dict(value_ref),
            "value_preview": dict(
                value_preview
            ),
        }

        idx.setdefault(
            "write_events",
            {},
        )[str(event_id)] = row

        _append_index_list(
            idx,
            "events_by_seq",
            str(seq),
            event_id,
        )
        _append_index_list(
            idx,
            "events_by_public_step_name",
            row["public_step_name"],
            event_id,
        )
        _append_index_list(
            idx,
            "events_by_step_fn",
            row["step_fn"],
            event_id,
        )
        _append_index_list(
            idx,
            "events_by_write_kind",
            write_kind,
            event_id,
        )

        event_ids.append(event_id)

    return event_ids


def record_state_patch_writes_v1(
    state: Dict[str, Any],
    *,
    seq: int,
    patch: Mapping[str, Any],
    reserved_keys: Iterable[str],
) -> List[int]:
    reserved = set(
        str(k)
        for k in reserved_keys
    )
    writes: List[Mapping[str, Any]] = []

    for raw_key, value in dict(
        patch or {}
    ).items():
        key = str(raw_key)
        if key in reserved:
            continue

        writes.append(
            {
                "write_kind": WRITE_KIND_STATE,
                "key": key,
                "value_ref": {
                    "kind": WRITE_KIND_STATE,
                    "key": key,
                },
                "value_preview": (
                    _preview_value(value)
                ),
            }
        )

    return record_runtime_writes_v1(
        state,
        seq=seq,
        writes=writes,
    )


def record_form_prefill_writes_v1(
    state: Dict[str, Any],
    *,
    seq: int,
    form_id: str,
    prefills: Mapping[str, Any],
) -> List[int]:
    writes: List[Mapping[str, Any]] = []

    for raw_datum_id, value in dict(
        prefills or {}
    ).items():
        datum_id = str(raw_datum_id)
        writes.append(
            {
                "write_kind": (
                    WRITE_KIND_FORM_PREFILL
                ),
                "key": datum_id,
                "value_ref": {
                    "kind": (
                        WRITE_KIND_FORM_PREFILL
                    ),
                    "form_id": str(form_id),
                    "datum_id": datum_id,
                },
                "value_preview": (
                    _preview_value(value)
                ),
            }
        )

    return record_runtime_writes_v1(
        state,
        seq=seq,
        writes=writes,
    )


def record_form_fill_writes_v1(
    state: Dict[str, Any],
    *,
    seq: int,
    form_id: str,
    fills: Mapping[str, Any],
) -> List[int]:
    writes: List[Mapping[str, Any]] = []

    for raw_datum_id, value in dict(
        fills or {}
    ).items():
        datum_id = str(raw_datum_id)
        writes.append(
            {
                "write_kind": (
                    WRITE_KIND_FORM_FILL
                ),
                "key": datum_id,
                "value_ref": {
                    "kind": (
                        WRITE_KIND_FORM_FILL
                    ),
                    "form_id": str(form_id),
                    "datum_id": datum_id,
                },
                "value_preview": (
                    _preview_value(value)
                ),
            }
        )

    return record_runtime_writes_v1(
        state,
        seq=seq,
        writes=writes,
    )


def record_just_exploded_datums_writes(
    state: Dict[str, Any],
    *,
    seq: int,
    form_id: str,
    datum_ids: Sequence[str],
    status: str,
) -> List[int]:
    writes: List[Mapping[str, Any]] = []

    for raw_datum_id in list(
        datum_ids or []
    ):
        datum_id = str(raw_datum_id)
        writes.append(
            {
                "write_kind": (
                    WRITE_KIND_DATUM_LIFECYCLE
                ),
                "key": datum_id,
                "value_ref": {
                    "kind": (
                        WRITE_KIND_DATUM_LIFECYCLE
                    ),
                    "form_id": str(form_id),
                    "datum_id": datum_id,
                },
                "value_preview": {
                    "kind": "datum_lifecycle",
                    "is_scalar": False,
                    "preview": (
                        "<datum_lifecycle "
                        f"form={form_id} "
                        f"datum={datum_id} "
                        f"status={status}>"
                    ),
                },
            }
        )

    return record_runtime_writes_v1(
        state,
        seq=seq,
        writes=writes,
    )


def remove_runtime_invocation_v1(
    state: Dict[str, Any],
    *,
    seq: Optional[int],
) -> None:
    """
    Remove one runtime invocation and all attached write events.

    Hot-path law:
      - ordinary undo removes the most recent invocation;
      - that path should be O(events for seq + small metadata buckets);
      - do not rebuild position sidecars for missing/idempotent removals;
      - do not scan payloads.

    Middle chronological deletion is tombstoned in O(1), with occasional
    compaction after substantial dead accumulation.
    """
    if seq is None:
        return

    idx = ensure_runtime_write_index_v1(
        state
    )
    seq_i = int(seq)
    seq_s = str(seq_i)

    invocations = idx.setdefault(
        "invocations",
        {},
    )
    raw_row = invocations.pop(
        seq_s,
        None,
    )

    # Idempotent/missing removal. Still clean attached event bucket if present,
    # but avoid invocation_order repair unless the order actually mentions seq.
    if not isinstance(raw_row, Mapping):
        event_ids = _pop_index_list(
            idx,
            "events_by_seq",
            seq_s,
        )
        for eid in event_ids:
            ev = dict(
                idx.setdefault(
                    "write_events",
                    {},
                ).pop(
                    str(eid),
                    {},
                )
                or {}
            )
            if not ev:
                continue

            _remove_index_list_value(
                idx,
                "events_by_public_step_name",
                str(
                    ev.get(
                        "public_step_name"
                    )
                    or ""
                ),
                int(eid),
            )
            _remove_index_list_value(
                idx,
                "events_by_step_fn",
                str(
                    ev.get("step_fn")
                    or ""
                ),
                int(eid),
            )
            _remove_index_list_value(
                idx,
                "events_by_write_kind",
                str(
                    ev.get(
                        "write_kind"
                    )
                    or ""
                ),
                int(eid),
            )

        order = idx.get(
            "invocation_order"
        )
        if isinstance(order, list) and order:
            # Cheap tail check, skipping any existing tombstones at the end.
            tail_pos = len(order) - 1
            while (
                tail_pos >= 0
                and order[tail_pos] is None
            ):
                tail_pos -= 1

            if tail_pos >= 0:
                try:
                    if int(order[tail_pos]) == seq_i:
                        _remove_invocation_order_value(
                            idx,
                            seq_i,
                        )
                        return
                except Exception:
                    pass

            root = idx.get(
                _LIST_POSITIONS_KEY
            )
            pos = (
                root.get(
                    _INVOCATION_ORDER_POSITIONS_KEY
                )
                if isinstance(root, Mapping)
                else None
            )
            if (
                isinstance(pos, Mapping)
                and seq_s in pos
            ):
                _remove_invocation_order_value(
                    idx,
                    seq_i,
                )

        return

    row = dict(raw_row)

    _remove_invocation_order_value(
        idx,
        seq_i,
    )

    psn = str(
        row.get("public_step_name")
        or ""
    )
    sfn = str(
        row.get("step_fn")
        or ""
    )

    if psn:
        _remove_index_list_value(
            idx,
            "by_public_step_name",
            psn,
            seq_i,
        )

    if sfn:
        _remove_index_list_value(
            idx,
            "by_step_fn",
            sfn,
            seq_i,
        )

    for arg_name in list(
        row.get("arg_names") or []
    ):
        _remove_index_list_value(
            idx,
            "by_arg_name",
            str(arg_name),
            seq_i,
        )

    for composite in list(
        row.get(
            "arg_path_value_keys"
        )
        or []
    ):
        _remove_index_list_value(
            idx,
            "by_arg_path_value",
            str(composite),
            seq_i,
        )

    event_ids = _pop_index_list(
        idx,
        "events_by_seq",
        seq_s,
    )
    for eid in event_ids:
        ev = dict(
            idx.setdefault(
                "write_events",
                {},
            ).pop(
                str(eid),
                {},
            )
            or {}
        )
        if not ev:
            continue

        _remove_index_list_value(
            idx,
            "events_by_public_step_name",
            str(
                ev.get(
                    "public_step_name"
                )
                or ""
            ),
            int(eid),
        )
        _remove_index_list_value(
            idx,
            "events_by_step_fn",
            str(
                ev.get("step_fn")
                or ""
            ),
            int(eid),
        )
        _remove_index_list_value(
            idx,
            "events_by_write_kind",
            str(
                ev.get("write_kind")
                or ""
            ),
            int(eid),
        )


def _seqs_for_query(
    idx: Mapping[str, Any],
    q: RuntimeWriteQueryV1,
) -> List[int]:
    candidates: Optional[set[int]] = None

    def intersect(
        values: Iterable[Any],
    ) -> None:
        nonlocal candidates

        selected: set[int] = set()
        for raw in values:
            try:
                selected.add(int(raw))
            except Exception:
                continue

        candidates = (
            selected
            if candidates is None
            else candidates.intersection(
                selected
            )
        )

    if q.public_step_name:
        intersect(
            idx.get(
                "by_public_step_name",
                {},
            ).get(
                str(q.public_step_name),
                [],
            )
            or []
        )

    if q.step_fn:
        intersect(
            idx.get(
                "by_step_fn",
                {},
            ).get(
                str(q.step_fn),
                [],
            )
            or []
        )

    if q.arg_name:
        intersect(
            idx.get(
                "by_arg_name",
                {},
            ).get(
                str(q.arg_name),
                [],
            )
            or []
        )

    if q.any_arg_names:
        union: set[int] = set()
        by_arg = idx.get(
            "by_arg_name",
            {},
        )

        for name in q.any_arg_names:
            for raw in (
                by_arg.get(
                    str(name),
                    [],
                )
                or []
            ):
                try:
                    union.add(int(raw))
                except Exception:
                    continue

        intersect(union)

    if (
        q.arg_path
        and q.has_arg_value_equals
    ):
        tok = _scalar_token(
            q.arg_value_equals
        )
        if tok is None:
            return []

        composite = (
            f"{str(q.arg_path)}"
            f"\x1f{tok}"
        )
        intersect(
            idx.get(
                "by_arg_path_value",
                {},
            ).get(
                composite,
                [],
            )
            or []
        )

    if candidates is None:
        ordered: List[int] = []
        invocations = idx.get(
            "invocations"
        )
        live_invocations = (
            invocations
            if isinstance(
                invocations,
                Mapping,
            )
            else {}
        )

        for raw in (
            idx.get(
                "invocation_order",
                [],
            )
            or []
        ):
            if raw is None:
                continue

            try:
                seq = int(raw)
            except Exception:
                continue

            if (
                str(seq)
                not in live_invocations
            ):
                continue

            ordered.append(seq)
    else:
        ordered = sorted(
            int(x)
            for x in candidates
        )

    if q.last_k_invocations is not None:
        k = max(
            0,
            int(q.last_k_invocations),
        )
        ordered = (
            ordered[-k:]
            if k
            else []
        )

    if q.arg_predicate is not None:
        pred_arg = str(
            q.predicate_arg_name
            or q.arg_name
            or ""
        )
        if not pred_arg:
            return []

        kept: List[int] = []
        max_evals = max(
            0,
            int(q.max_predicate_evals),
        )
        evals = 0
        invocations = idx.get(
            "invocations",
            {},
        )

        for seq in ordered:
            if evals >= max_evals:
                break

            row = dict(
                invocations.get(
                    str(seq)
                )
                or {}
            )
            previews = dict(
                row.get(
                    "arg_previews"
                )
                or {}
            )
            preview = previews.get(
                pred_arg
            )
            evals += 1

            try:
                if q.arg_predicate(preview):
                    kept.append(seq)
            except Exception:
                continue

        ordered = kept

    return ordered


def query_runtime_writes_v1(
    state: Mapping[str, Any],
    query: (
        RuntimeWriteQueryV1
        | Mapping[str, Any]
    ),
) -> Dict[str, Any]:
    idx = state.get(
        KEY_RUNTIME_WRITE_INDEX
    )
    if not isinstance(idx, Mapping):
        return {
            "kind": (
                "runtime_write_query_result_v1"
            ),
            "ok": True,
            "writes": [],
            "truncated": False,
            "seq_count": 0,
            "max_results": (
                DEFAULT_MAX_RESULTS_V1
            ),
        }

    if isinstance(
        query,
        RuntimeWriteQueryV1,
    ):
        q = query
    elif isinstance(query, Mapping):
        q = RuntimeWriteQueryV1(
            public_step_name=query.get(
                "public_step_name"
            ),
            step_fn=query.get("step_fn"),
            last_k_invocations=query.get(
                "last_k_invocations"
            ),
            arg_name=query.get("arg_name"),
            any_arg_names=tuple(
                str(x)
                for x in list(
                    query.get(
                        "any_arg_names"
                    )
                    or []
                )
            ),
            arg_path=query.get("arg_path"),
            arg_value_equals=query.get(
                "arg_value_equals"
            ),
            has_arg_value_equals=(
                "arg_value_equals" in query
            ),
            write_kinds=tuple(
                str(x)
                for x in list(
                    query.get(
                        "write_kinds"
                    )
                    or []
                )
            ),
            max_results=(
                _coerce_nonnegative_int(
                    query.get(
                        "max_results",
                        None,
                    ),
                    default=(
                        DEFAULT_MAX_RESULTS_V1
                    ),
                )
            ),
            include_values=bool(
                query.get(
                    "include_values",
                    False,
                )
            ),
        )
    else:
        raise TypeError(
            "query must be "
            "RuntimeWriteQueryV1 "
            "or mapping"
        )

    seqs = _seqs_for_query(idx, q)
    write_kind_filter = set(
        str(x)
        for x in q.write_kinds
    )

    events_by_seq = idx.get(
        "events_by_seq",
        {},
    )
    write_events = idx.get(
        "write_events",
        {},
    )

    rows: List[Dict[str, Any]] = []
    max_results = max(
        0,
        int(q.max_results),
    )
    truncated = False

    if max_results == 0:
        has_matching_event = False

        for seq in seqs:
            event_ids = list(
                events_by_seq.get(
                    str(seq),
                    [],
                )
                or []
            )
            for eid in event_ids:
                ev = dict(
                    write_events.get(
                        str(eid)
                    )
                    or {}
                )
                if not ev:
                    continue

                if (
                    write_kind_filter
                    and str(
                        ev.get(
                            "write_kind"
                        )
                        or ""
                    )
                    not in write_kind_filter
                ):
                    continue

                has_matching_event = True
                break

            if has_matching_event:
                break

        return {
            "kind": (
                "runtime_write_query_result_v1"
            ),
            "ok": True,
            "writes": [],
            "truncated": bool(
                has_matching_event
            ),
            "seq_count": len(seqs),
            "max_results": max_results,
        }

    for seq in seqs:
        event_ids = list(
            events_by_seq.get(
                str(seq),
                [],
            )
            or []
        )
        for eid in event_ids:
            ev = dict(
                write_events.get(
                    str(eid)
                )
                or {}
            )
            if not ev:
                continue

            if (
                write_kind_filter
                and str(
                    ev.get("write_kind")
                    or ""
                )
                not in write_kind_filter
            ):
                continue

            if len(rows) >= max_results:
                truncated = True
                break

            row = dict(ev)
            if q.include_values:
                ref = row.get(
                    "value_ref"
                )
                row["value"] = (
                    _resolve_ref_value(
                        state,
                        (
                            ref
                            if isinstance(
                                ref,
                                Mapping,
                            )
                            else {}
                        ),
                    )
                )

            rows.append(row)

        if truncated:
            break

    return {
        "kind": (
            "runtime_write_query_result_v1"
        ),
        "ok": True,
        "writes": rows,
        "truncated": bool(truncated),
        "seq_count": len(seqs),
        "max_results": max_results,
    }


def _runtime_index_snapshot_sanitize_row_v1(value: Any) -> Any:
    """
    Return a durable view of a single runtime-index row.

    This intentionally sanitizes only selected legacy/hostile row-shaped objects,
    not the whole runtime index. The hot tables produced by this module, such as
    invocations and write_events, are already metadata-only and are shallow-kept
    by runtime_write_index_snapshot_view_v1.

    This helper is defensive for old snapshots/tests/hostile fixtures where a
    row may contain:

        sidecar
        sidecars
        tombstone
        tombstones
        raw_value
        list_positions

    Production writers should avoid putting those fields into durable rows in
    the first place, but the snapshot boundary remains the final safety net for
    explicitly deep-sanitized legacy/hostile row tables.
    """
    if isinstance(value, Mapping):
        out: Dict[Any, Any] = {}

        for k, v in value.items():
            if str(k) in _RUNTIME_INDEX_SNAPSHOT_ROW_DROP_KEYS_V1:
                continue

            out[k] = _runtime_index_snapshot_sanitize_row_v1(v)

        return out

    if isinstance(value, list):
        return [
            _runtime_index_snapshot_sanitize_row_v1(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return tuple(
            _runtime_index_snapshot_sanitize_row_v1(item)
            for item in value
        )

    return value


def _runtime_index_snapshot_sanitize_row_table_v1(value: Any) -> Any:
    """
    Sanitize a mapping/list of legacy/hostile row-shaped values.

    This is the scalable compromise:

        full-index recursive sanitize:              too expensive
        top-level-only sanitize:                    misses bad legacy rows
        schema-aware selected-row-table sanitize:   bounded and durable-safe

    Do not use this helper for invocations or write_events. Those tables are
    hot, large, module-owned metadata tables and are shallow-preserved.
    """
    if isinstance(value, Mapping):
        return {
            row_key: _runtime_index_snapshot_sanitize_row_v1(row)
            for row_key, row in value.items()
        }

    if isinstance(value, list):
        return [
            _runtime_index_snapshot_sanitize_row_v1(row)
            for row in value
        ]

    if isinstance(value, tuple):
        return tuple(
            _runtime_index_snapshot_sanitize_row_v1(row)
            for row in value
        )

    return value


def runtime_write_index_snapshot_view_v1(
    index: Any,
) -> Any:
    """
    Return a durable runtime-write-index view.

    Snapshot projection removes live-only mutation helpers while preserving the
    queryable metadata tables.

    Scalability law:

        Do not deep-copy/deep-sanitize the entire index.
        Do not deep-copy/deep-sanitize the hot invocation/write-event tables.

    The runtime write index contains large secondary indexes and large metadata
    row tables. A broad recursive sanitizer makes snapshot/export/persist paths
    pay for walking every nested table. Instead this function performs
    schema-aware projection:

        - top-level private containers are dropped;
        - invocation_order is compacted against live invocations;
        - legacy/hostile row tables are sanitized row-by-row;
        - ordinary secondary indexes are shallow-preserved;
        - invocations/write_events are shallow-preserved because this module
          owns their metadata-only schema.

    This keeps the lean-persistence guarantee without regressing complexity
    tests that depend on snapshot/query/index paths staying bounded.

    Do not replace this with a generic recursive sanitizer over the entire
    index. That looks simpler, but it makes snapshot/export/persist cost scale
    with every nested secondary index table and every hot metadata row.
    """
    if not isinstance(index, Mapping):
        return index

    invocations = index.get("invocations")
    live_invocations = (
        invocations
        if isinstance(invocations, Mapping)
        else {}
    )

    compact_order: List[int] = []
    for raw in index.get("invocation_order", []) or []:
        if raw is None:
            continue

        try:
            seq = int(raw)
        except Exception:
            continue

        if str(seq) in live_invocations:
            compact_order.append(seq)

    out: Dict[str, Any] = {}

    for k, v in index.items():
        ks = str(k)

        if ks in _RUNTIME_INDEX_SNAPSHOT_TOP_LEVEL_DROP_KEYS_V1:
            continue

        if ks == "invocation_order":
            out[ks] = compact_order
            continue

        if ks == _INVOCATION_ORDER_DEAD_COUNT_KEY:
            out[ks] = 0
            continue

        if ks in _RUNTIME_INDEX_DEEP_SANITIZE_ROW_TABLE_KEYS_V1:
            out[ks] = _runtime_index_snapshot_sanitize_row_table_v1(v)
            continue

        # Important:
        # Shallow-preserve hot metadata/index tables, especially:
        #
        #   - invocations
        #   - write_events
        #   - by_public_step_name
        #   - by_step_fn
        #   - by_arg_name
        #   - by_arg_path_value
        #   - events_by_seq
        #   - events_by_public_step_name
        #   - events_by_step_fn
        #   - events_by_write_kind
        #
        # These are already metadata-only. Recursing through them on every
        # snapshot/export is the performance regression this function avoids.
        out[ks] = v

    return out


__all__ = [
    "RuntimeWriteQueryV1",
    "WRITE_KIND_STATE",
    "WRITE_KIND_FORM_PREFILL",
    "WRITE_KIND_FORM_FILL",
    "WRITE_KIND_DATUM_LIFECYCLE",
    "ensure_runtime_write_index_v1",
    "register_runtime_invocation_v1",
    "record_runtime_writes_v1",
    "record_state_patch_writes_v1",
    "record_form_prefill_writes_v1",
    "record_form_fill_writes_v1",
    "record_just_exploded_datums_writes",
    "remove_runtime_invocation_v1",
    "query_runtime_writes_v1",
    "runtime_write_index_snapshot_view_v1",
]