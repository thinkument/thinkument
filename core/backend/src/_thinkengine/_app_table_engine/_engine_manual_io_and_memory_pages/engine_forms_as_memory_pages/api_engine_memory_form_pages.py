from __future__ import annotations

from typing import Any, Dict, Mapping

# global libs
from __datomatonTM import (
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    KEY_DATUM_LIFECYCLE,
)

from __datomatonTM import (
    this_datum_has_a_functional_lifecycle,
)

from __datomatonTM import read_datum_system_flags_limits

from __multiframespecTM.api import (
    span_key_v1
)


# local imports
from ._undo_form_page_changes import undo_lifecycle_patch_v1

from ._apply_form_page_changes import (
    apply_q_done_batch_v1,
    apply_q_mount_batch_v1,
    apply_q_reexplode_batch_v1
)

from ._create_new_form_page_rows import (
    ensure_datum_lifecycle_store_v1,
    _form_row_v1,
    _datum_row_v1
)

from ._undo_form_page_changes import (
    undo_lifecycle_patch_v1,
)


def get_engine_form_page_epoch_from_id(
    state: Mapping[str, Any],
    form_id: str,
) -> int:
    store = state.get(KEY_DATUM_LIFECYCLE)
    if not isinstance(store, Mapping):
        return 0
    forms = store.get("forms")
    if not isinstance(forms, Mapping):
        return 0
    row = forms.get(str(form_id or ""))
    if not isinstance(row, Mapping):
        return 0
    try:
        return int(row.get("epoch", 0) or 0)
    except Exception:
        return 0


def get_engine_form_page_structural_epoch_from_id(
    state: Mapping[str, Any],
    form_id: str,
) -> int:
    """
    Epoch for structural manual-IO cache invalidation.

    Q done/blocked changes lifecycle semantics but does not change the datum
    shell or rendered field topology. Q reexplode does.

    Manual UI structural cache keys must use this epoch, not the general
    lifecycle mutation epoch, or every Q done forces an unnecessary recompile.
    """
    store = state.get(KEY_DATUM_LIFECYCLE)
    if not isinstance(store, Mapping):
        return 0
    forms = store.get("forms")
    if not isinstance(forms, Mapping):
        return 0
    row = forms.get(str(form_id or ""))
    if not isinstance(row, Mapping):
        return 0
    try:
        return int(row.get("structural_epoch", 0) or 0)
    except Exception:
        return 0


def get_latest_engine_form_page_data_read(
    *,
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
) -> Dict[str, Any]:
    store = state.get(KEY_DATUM_LIFECYCLE)
    forms = store.get("forms") if isinstance(store, Mapping) else None
    form_row = (
        forms.get(str(form_id or ""))
        if isinstance(forms, Mapping)
        else None
    )

    if not isinstance(form_row, Mapping):
        return {}

    sk = span_key_v1(frame_id, span_id)
    out: Dict[str, Any] = {}

    wf = form_row.get("working_fills_by_span")
    if isinstance(wf, Mapping):
        row = wf.get(sk)
        if isinstance(row, Mapping):
            out.update(dict(row))

    wp = form_row.get("working_prefills_by_span")
    if isinstance(wp, Mapping):
        row = wp.get(sk)
        if isinstance(row, Mapping):
            for k, v in dict(row).items():
                out.setdefault(str(k), v)

    return out


def hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
    *,
    multiframespec: Mapping[str, Any],
    state: Mapping[str, Any],
    form_id: str,
) -> Dict[str, Any]:
    fs = dict(multiframespec or {})

    store = state.get(KEY_DATUM_LIFECYCLE)
    forms = store.get("forms") if isinstance(store, Mapping) else None
    form_row = (
        forms.get(str(form_id or ""))
        if isinstance(forms, Mapping)
        else None
    )
    datums_row = (
        form_row.get("datums")
        if isinstance(form_row, Mapping)
        else None
    )

    if not isinstance(datums_row, Mapping):
        return fs

    changed = False
    out_datums: List[Any] = []

    for d in list(fs.get("datums") or []):
        if not isinstance(d, Mapping):
            out_datums.append(d)
            continue

        did = str(d.get("id") or "")
        row = datums_row.get(did)
        cur = row.get("current_datum") if isinstance(row, Mapping) else None

        if isinstance(cur, Mapping):
            dd = dict(cur)
            dd.setdefault("id", did)
            out_datums.append(dd)
            changed = True
        else:
            out_datums.append(d)

    if changed:
        fs["datums"] = out_datums

    return fs

