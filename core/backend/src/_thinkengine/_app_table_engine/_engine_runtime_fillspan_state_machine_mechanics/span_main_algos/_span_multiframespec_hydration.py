from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from __multiframespecTM.api import (
    build_multiframespec_scoped_datum_fill_map,
)
from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fills,
    get_form_prefills,
)


def hydrate_multiframespec_for_span_v1(
    self,
    step: Any,
    *,
    form_id_fallback_to_multiframespec: bool = True,
    coerce_non_mapping_multiframespec_to_empty: bool = False,
    filter_blank_span_owns: bool = True,
) -> Dict[str, Any]:
    """
    Common multiframespec hydration/extraction helper for span-side algorithms.

    This is intentionally one helper, not many tiny helpers, because downstream
    span code repeatedly needs the same bundle:

        raw pending multiframespec
        effective hydrated multiframespec
        form/frame/span identifiers
        static span ownership vector
        authoritative datum subset

    It does not decide business logic such as whether a non-mapping pending
    multiframespec is fatal, false, or renderable as an empty shell. Callers keep
    those existing semantics by choosing the flags above and by checking
    has_multiframespec_mapping when they need to.
    """

    multiframespec_raw = self.state.get(KEY_PENDING_FORM)
    has_multiframespec_mapping = isinstance(multiframespec_raw, Mapping)

    if has_multiframespec_mapping:
        multiframespec_for_hydration = multiframespec_raw
        multiframespec_for_form_id = multiframespec_raw
    elif coerce_non_mapping_multiframespec_to_empty:
        multiframespec_for_hydration = {}
        multiframespec_for_form_id = {}
    else:
        multiframespec_for_hydration = multiframespec_raw
        multiframespec_for_form_id = {}

    frame_id = str(step.payload.get("frame_id") or "").strip()
    span_id = str(step.payload.get("span_id") or "").strip()

    if form_id_fallback_to_multiframespec:
        form_id = str(
            self.state.get(KEY_PENDING_FORM_ID)
            or multiframespec_for_form_id.get("app_form_id")
            or ""
        ).strip()
    else:
        form_id = str(self.state.get(KEY_PENDING_FORM_ID) or "")

    span_owns = []
    for raw_fid in list(step.payload.get("span_owns") or []):
        fid = str(raw_fid)
        if filter_blank_span_owns and not str(fid or "").strip():
            continue
        span_owns.append(fid)

    span_authoritative = [
        str(x)
        for x in list(step.payload.get("span_authoritative") or [])
        if str(x or "").strip()
    ]
    if not span_authoritative:
        span_authoritative = list(span_owns)

    effective_multiframespec = (
        hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
            multiframespec=multiframespec_for_hydration,
            state=self.state,
            form_id=str(form_id),
        )
    )

    return {
        "multiframespec_raw": multiframespec_raw,
        "has_multiframespec_mapping": has_multiframespec_mapping,
        "effective_multiframespec": effective_multiframespec,
        "form_id": form_id,
        "frame_id": frame_id,
        "span_id": span_id,
        "span_owns": span_owns,
        "span_authoritative": span_authoritative,
    }


def manual_io_cache_bundle_for_hydrated_span_v1(
    self,
    *,
    hydrated_span: Mapping[str, Any],
    datum_widgets_on_this_span: Optional[Sequence[str]] = None,
    copy_values: bool = False,
    suppress_cache_errors: bool = False,
) -> Dict[str, Any]:
    """
    Shared manual-IO cache extraction for span algorithms.

    Span algorithms usually do not only need the render/cache object. They need
    the same downstream bundle over and over:

        compiled manual IO cache
        datum shells by id
        current cached fill data

    Callers can pass a dynamic/static datum vector when they intentionally want
    the cache scoped differently from hydrated_span["span_owns"].
    """

    effective_multiframespec = hydrated_span["effective_multiframespec"]
    form_id = hydrated_span["form_id"]
    frame_id = hydrated_span["frame_id"]
    span_id = hydrated_span["span_id"]

    if datum_widgets_on_this_span is None:
        datum_widgets_on_this_span = hydrated_span["span_owns"]

    try:
        cache = self._get_or_compile_manual_io_cache_v1(
            multiframespec=effective_multiframespec,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_widgets_on_this_span=list(datum_widgets_on_this_span or []),
        )
    except Exception as e:
        if not suppress_cache_errors:
            raise
        return {
            "cache": None,
            "datums_by_id": {},
            "datum_widget_fills": {},
            "cache_error": e,
        }

    datums_raw = (
        cache.get("datums_by_id")
        if isinstance(cache, Mapping)
        else {}
    )
    datums_by_id = (
        datums_raw
        if isinstance(datums_raw, Mapping)
        else {}
    )

    datum_widget_fills = (
        self._cached_manual_datum_widget_fills_v1(
            cache=cache,
            multiframespec=effective_multiframespec,
            copy_values=copy_values,
        )
    )

    return {
        "cache": cache,
        "datums_by_id": datums_by_id,
        "datum_widget_fills": datum_widget_fills,
        "cache_error": None,
    }


def hydrate_and_compile_manual_io_span_bundle_v1(
    self,
    step: Any,
    *,
    form_id_fallback_to_multiframespec: bool = True,
    coerce_non_mapping_multiframespec_to_empty: bool = False,
    filter_blank_span_owns: bool = True,
    datum_widgets_on_this_span: Optional[Sequence[str]] = None,
    copy_values: bool = False,
    suppress_cache_errors: bool = False,
) -> Dict[str, Any]:
    """
    One semantic bundle for the common span wire pattern:

        pending raw multiframespec
            -> hydrated effective multiframespec
            -> compiled manual IO cache
            -> datum shells and fill map

    This keeps main span algorithm files readable as algorithms instead of
    repeating mechanical cache/datum/fill extraction blocks.
    """

    hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=(
            form_id_fallback_to_multiframespec
        ),
        coerce_non_mapping_multiframespec_to_empty=(
            coerce_non_mapping_multiframespec_to_empty
        ),
        filter_blank_span_owns=filter_blank_span_owns,
    )

    cache_bundle = manual_io_cache_bundle_for_hydrated_span_v1(
        self,
        hydrated_span=hydrated_span,
        datum_widgets_on_this_span=datum_widgets_on_this_span,
        copy_values=copy_values,
        suppress_cache_errors=suppress_cache_errors,
    )

    out = dict(hydrated_span)
    out.update(cache_bundle)
    return out


def static_datum_and_scoped_fill_bundle_for_effective_multiframespec_v1(
    self,
    *,
    effective_multiframespec: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Shared mounting-side static datum/fill bundle.

    Mounting needs the current hydrated datum shells plus the scoped fill data
    assembled from multiframespec defaults, external prefills, and committed
    fills. Keeping that extraction here lets mount_datums_needing_mounting_on_the_span
    read as the mount algorithm rather than as data plumbing.
    """

    datums_by_id: Dict[str, Dict[str, Any]] = {}
    for d in list(effective_multiframespec.get("datums") or []):
        if not isinstance(d, Mapping):
            continue

        did = str(d.get("id") or "").strip()
        if did:
            datums_by_id[did] = dict(d)

    fills_snapshot = get_form_fills(self.state)
    prefills_snapshot = get_form_prefills(self.state)

    existing_datum_fill_data = build_multiframespec_scoped_datum_fill_map(
        multiframespec=effective_multiframespec,
        external_prefills_by_datum_id=prefills_snapshot,
        external_fills_by_datum_id=fills_snapshot,
    )

    return {
        "datums_by_id": datums_by_id,
        "fills_snapshot": fills_snapshot,
        "prefills_snapshot": prefills_snapshot,
        "existing_datum_fill_data": existing_datum_fill_data,
    }