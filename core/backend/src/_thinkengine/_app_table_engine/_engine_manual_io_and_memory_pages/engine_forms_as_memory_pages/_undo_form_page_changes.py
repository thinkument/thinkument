from __future__ import annotations

import copy

from typing import Any, Dict, List, Mapping

# global libs
from __datomatonTM import (
    KEY_DATUM_LIFECYCLE,
)

from __multiframespecTM.api import (
    span_key_v1
)

# local imports
from ._create_new_form_page_rows import (
    ensure_datum_lifecycle_store_v1,
)


_LIFECYCLE_INCREMENTAL_UNDO_KIND_V1 = (
    "__datum_lifecycle_incremental_undo_v1__"
)


def _make_lifecycle_incremental_undo_v1(
    *,
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_ids: List[str],
) -> Dict[str, Any]:
    fid = str(form_id or "")
    sk = span_key_v1(frame_id, span_id)
    ids = [
        str(x)
        for x in list(datum_ids or [])
        if str(x)
    ]

    store = state.get(KEY_DATUM_LIFECYCLE)
    store_missing = not isinstance(store, Mapping)

    forms = store.get("forms") if isinstance(store, Mapping) else None
    form_row = forms.get(fid) if isinstance(forms, Mapping) else None
    form_missing = not isinstance(form_row, Mapping)

    wf_missing = True
    wf_value = None
    wp_missing = True
    wp_value = None
    form_epoch = 0
    structural_epoch = 0
    datum_rows: Dict[str, Any] = {}

    if isinstance(form_row, Mapping):
        try:
            form_epoch = int(form_row.get("epoch", 0) or 0)
        except Exception:
            form_epoch = 0

        try:
            structural_epoch = int(
                form_row.get("structural_epoch", 0) or 0
            )
        except Exception:
            structural_epoch = 0

        wf_root = form_row.get("working_fills_by_span")
        if isinstance(wf_root, Mapping) and sk in wf_root:
            wf_missing = False
            wf_value = copy.deepcopy(wf_root.get(sk))

        wp_root = form_row.get("working_prefills_by_span")
        if isinstance(wp_root, Mapping) and sk in wp_root:
            wp_missing = False
            wp_value = copy.deepcopy(wp_root.get(sk))

        datums = form_row.get("datums")
        if isinstance(datums, Mapping):
            for did in ids:
                if (
                    did in datums
                    and isinstance(datums.get(did), Mapping)
                ):
                    datum_rows[did] = {
                        "missing": False,
                        "row": copy.deepcopy(datums.get(did)),
                    }
                else:
                    datum_rows[did] = {
                        "missing": True,
                        "row": None,
                    }
        else:
            for did in ids:
                datum_rows[did] = {
                    "missing": True,
                    "row": None,
                }
    else:
        for did in ids:
            datum_rows[did] = {
                "missing": True,
                "row": None,
            }

    return {
        "kind": _LIFECYCLE_INCREMENTAL_UNDO_KIND_V1,
        "store_missing": bool(store_missing),
        "form_id": fid,
        "form_missing": bool(form_missing),
        "form_epoch": form_epoch,
        "structural_epoch": structural_epoch,
        "span_key": sk,
        "working_fill": {
            "missing": bool(wf_missing),
            "value": wf_value,
        },
        "working_prefill": {
            "missing": bool(wp_missing),
            "value": wp_value,
        },
        "datum_rows": datum_rows,
    }


def undo_lifecycle_patch_v1(
    state: Dict[str, Any],
    undo: Mapping[str, Any],
) -> None:
    if str(undo.get("kind") or "") == _LIFECYCLE_INCREMENTAL_UNDO_KIND_V1:
        if bool(undo.get("store_missing", False)):
            state.pop(KEY_DATUM_LIFECYCLE, None)
            return

        store = ensure_datum_lifecycle_store_v1(state)
        forms = store.setdefault("forms", {})
        fid = str(undo.get("form_id") or "")

        if bool(undo.get("form_missing", False)):
            forms.pop(fid, None)
            return

        form_row = forms.get(fid)
        if not isinstance(form_row, dict):
            form_row = {
                "epoch": 0,
                "structural_epoch": 0,
                "datums": {},
                "working_fills_by_span": {},
                "working_prefills_by_span": {},
            }
            forms[fid] = form_row

        form_row["epoch"] = int(undo.get("form_epoch", 0) or 0)
        form_row["structural_epoch"] = int(
            undo.get("structural_epoch", 0) or 0
        )

        sk = str(undo.get("span_key") or "")

        wf_root = form_row.setdefault("working_fills_by_span", {})
        if isinstance(wf_root, dict):
            wf = undo.get("working_fill")
            if isinstance(wf, Mapping):
                if bool(wf.get("missing", False)):
                    wf_root.pop(sk, None)
                else:
                    wf_root[sk] = copy.deepcopy(wf.get("value"))

        wp_root = form_row.setdefault("working_prefills_by_span", {})
        if isinstance(wp_root, dict):
            wp = undo.get("working_prefill")
            if isinstance(wp, Mapping):
                if bool(wp.get("missing", False)):
                    wp_root.pop(sk, None)
                else:
                    wp_root[sk] = copy.deepcopy(wp.get("value"))

        datums = form_row.setdefault("datums", {})
        if isinstance(datums, dict):
            rows = undo.get("datum_rows")
            if isinstance(rows, Mapping):
                for did_raw, row_undo in dict(rows).items():
                    did = str(did_raw)
                    if not isinstance(row_undo, Mapping):
                        continue

                    if bool(row_undo.get("missing", False)):
                        datums.pop(did, None)
                    else:
                        row = row_undo.get("row")
                        datums[did] = (
                            copy.deepcopy(row)
                            if isinstance(row, Mapping)
                            else {}
                        )
        return

    if KEY_DATUM_LIFECYCLE not in undo:
        return

    if bool(undo.get("__missing__", False)):
        state.pop(KEY_DATUM_LIFECYCLE, None)
    else:
        state[KEY_DATUM_LIFECYCLE] = undo.get(KEY_DATUM_LIFECYCLE)