from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)

from ._constants import (
    KERNEL_HISTORY_QUERY_SELECT_ALL_V1,
    KERNEL_HISTORY_QUERY_SELECT_LATEST_V1,
)
from ._contracts import kernel_widget_contract_v1


def kernel_history_query_cache_key_v1(spec: Mapping[str, Any]) -> tuple[Any, ...]:
    """
    The cache key contains only fields that affect fetching candidate rows.

    `required` and `select` are intentionally not part of this key: they affect
    post-query interpretation, not which runtime rows are fetched.
    """
    return (
        str(spec.get("from_step") or ""),
        str(spec.get("datum_id") or ""),
        str(spec.get("write_kind") or WRITE_KIND_DATUM_LIFECYCLE),
        bool(spec.get("include_value", True)),
        int(spec.get("max_results") or 128),
    )


def resolve_kernel_history_queries_v1(
    state: Mapping[str, Any],
    kernel: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Scalable centralized per-step history query.

    Contract:
      - zero history_queries => zero runtime-write queries;
      - duplicate aliases for the same prior fact => one runtime-write query;
      - many datums sharing an alias => one runtime-write query;
      - select=latest returns one row or None;
      - select=all returns a list of matching rows;
      - include_value controls materialization explicitly.
    """
    history_queries = dict(kernel.get("history_queries") or {})
    resolved: Dict[str, Any] = {}
    cache: Dict[tuple[Any, ...], list[Dict[str, Any]]] = {}

    for alias, spec_raw in history_queries.items():
        spec = dict(spec_raw or {})
        cache_key = kernel_history_query_cache_key_v1(spec)

        if cache_key not in cache:
            from_step = str(spec["from_step"])
            datum_id = str(spec["datum_id"])
            include_value = bool(spec.get("include_value", True))

            q = query_runtime_writes_v1(
                state,
                {
                    "public_step_name": from_step,
                    "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
                    "include_values": include_value,
                    "max_results": int(spec.get("max_results") or 128),
                },
            )

            matches: list[Dict[str, Any]] = []
            for row in list(q.get("writes") or []):
                if str(row.get("key") or "") != datum_id:
                    continue
                ref = row.get("value_ref") or {}
                if isinstance(ref, Mapping) and str(ref.get("datum_id") or "") != datum_id:
                    continue
                matches.append(dict(row))

            cache[cache_key] = matches

        matches = cache[cache_key]
        select = str(spec.get("select") or KERNEL_HISTORY_QUERY_SELECT_LATEST_V1)

        if select == KERNEL_HISTORY_QUERY_SELECT_ALL_V1:
            value: Any = list(matches)
        else:
            value = matches[-1] if matches else None

        empty = value == [] or value is None
        if empty and bool(spec.get("required", False)):
            raise RuntimeError(
                f"required kernel history query {alias!r} found no datum "
                f"{spec.get('from_step')}.{spec.get('datum_id')}"
            )

        resolved[str(alias)] = value

    return resolved


def build_kernel_past_wires_for_datum_v1(
    *,
    datum: Mapping[str, Any],
    resolved_history_queries: Mapping[str, Any],
) -> Dict[str, Any]:
    widget = str(datum["widget"])
    contract = kernel_widget_contract_v1(widget)

    out: Dict[str, Any] = {}

    for wire_name, aliases_raw in dict(datum.get("past_wires") or {}).items():
        aliases = list(aliases_raw or [])
        spec = dict(dict(contract.get("past_wires") or {})[str(wire_name)])
        multiplicity = str(spec.get("multiplicity") or "one")

        collected: list[Any] = []
        for alias in aliases:
            value = resolved_history_queries.get(str(alias))
            if value is None:
                continue
            if isinstance(value, list):
                collected.extend(value)
            else:
                collected.append(value)

        if multiplicity == "one":
            if len(collected) != 1:
                raise RuntimeError(
                    f"wire {wire_name!r} expected exactly one resolved row, "
                    f"got {len(collected)}"
                )
            out[str(wire_name)] = collected[0]
        else:
            out[str(wire_name)] = collected

    return out