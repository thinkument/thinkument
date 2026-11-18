from __future__ import annotations

from typing import Any, Dict, Mapping


# global imports

from __datomatonTM import (
    KEY_DATUM_LIFECYCLE,
)

from __datomatonTM import (
    read_datum_system_flags_limits,
)


def fresh_datum_lifecycle_store_v1() -> Dict[str, Any]:
    return {
        "v": 1,
        "forms": {},
    }


def ensure_datum_lifecycle_store_v1(
    state: Dict[str, Any],
) -> Dict[str, Any]:
    raw = state.get(KEY_DATUM_LIFECYCLE)
    if (
        isinstance(raw, Mapping)
        and int(raw.get("v", 0) or 0) == 1
    ):
        if not isinstance(raw.get("forms"), dict):
            raw = dict(raw)
            raw["forms"] = {}
            state[KEY_DATUM_LIFECYCLE] = raw
        return raw  # type: ignore[return-value]

    store = fresh_datum_lifecycle_store_v1()
    state[KEY_DATUM_LIFECYCLE] = store
    return store


def _form_row_v1(
    store: Dict[str, Any],
    form_id: str,
) -> Dict[str, Any]:
    forms = store.setdefault("forms", {})
    fid = str(form_id or "")
    row = forms.get(fid)

    if not isinstance(row, dict):
        row = {
            "epoch": 0,
            "structural_epoch": 0,
            "datums": {},
            "working_fills_by_span": {},
            "working_prefills_by_span": {},
        }
        forms[fid] = row
    else:
        row.setdefault("epoch", 0)
        row.setdefault("structural_epoch", 0)
        row.setdefault("datums", {})
        row.setdefault("working_fills_by_span", {})
        row.setdefault("working_prefills_by_span", {})

    return row


def _datum_row_v1(
    form_row: Dict[str, Any],
    datum_id: str,
    datum: Mapping[str, Any],
) -> Dict[str, Any]:
    datums = form_row.setdefault("datums", {})
    did = str(datum_id)
    row = datums.get(did)

    if not isinstance(row, dict):
        policy = read_datum_system_flags_limits(datum)
        row = {
            "epoch": 0,
            "status": None,
            "reexplode_count": 0,
            "state": dict(policy["initial_state"]),
            "current_datum": None,
            "messages": [],
            "proc_notes": [],
            "forced_done": False,
            "spans_mounted_on": {},
        }
        datums[did] = row
    else:
        row.setdefault("spans_mounted_on", {})
        row.setdefault("messages", [])
        row.setdefault("proc_notes", [])

    return row




