# think-backend/src/thinkengine/_app_table_engine/engine/_engine_runtime_fillspan_state_machine_mechanics/span_main_algos/span_satisfaction.py

from __future__ import annotations

from typing import Any, Mapping, Sequence

from _thinkprogram._iomicrosTM.core.api_fills import (
    datum_fill_data_meets_its_structural_micros_shell,
)
from .span_mounting import (
    does_this_datum_want_mount_and_has_yet_to_undergo_mount_explosion_on_this_span,
)
from __datomatonTM import (
    this_datum_has_a_functional_lifecycle
)
from __datomatonTM import (
    is_this_datum_automaton_in_satisfied_sink_state,
)
from ._span_multiframespec_hydration import (
    hydrate_multiframespec_for_span_v1,
)


def is_this_datum_satisfied_for_this_span_v1(
    self,
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    datum: Any,
    datum_widget_fills: Mapping[str, Any],
) -> bool:
    """
    One datum's dynamic satisfaction law on the current span.

    Important split:

        span_owns
            means the static product vector of datums owned by this span.

        datum_widgets_on_this_span
            means only the unsatisfied/editable public subset right now.

    So if span S_AB owns ["A", "B"] and A is already satisfied by a
    multiframespec-level fill, S_AB still owns A, but A should not appear in
    datum_widgets_on_this_span.
    """

    fid = str(datum_id or "").strip()
    if not fid:
        return False

    if not isinstance(datum, Mapping):
        return False

    # wants to mount and has not even mounted yet so surely datum not satisfied
    if does_this_datum_want_mount_and_has_yet_to_undergo_mount_explosion_on_this_span(
        state=self.state,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=fid,
        datum=datum,
    ):
        return False

    # datum already past mounting, but is it in the satisfaction sink status?
    if is_this_datum_automaton_in_satisfied_sink_state(
        state=self.state,
        form_id=form_id,
        datum_id=fid,
    ):
        return True

    # datum already past mounting, not in satisfaction sink state,
    # of course would return False here BUT
    # return False <--- would be wrong
    # because datums WITHOUT lifecycle
    # simply wit a rigid multiframespec
    # and for them we do not even check the lifecycle fn status / state it is in

    # so for "widgets" (datumw lifecycle fn then yeah False)
    if this_datum_has_a_functional_lifecycle(datum):
        return False

    # but if a datum w multiframespec rigid and no lifecycle ,
    # satisfaction not thorugh lifecycle fn decision
    # we have to manually check
    # btw these types of datums are primitive and widget lifecycle preferred
    # uniformly by higher code
    try:
        return bool(
            datum_fill_data_meets_its_structural_micros_shell(
                datum,
                datum_widget_fills.get(fid),
            )
        )
    except Exception:
        return False


def datum_widgets_on_this_span_for_current_span_v1(
    self,
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    span_owns: Sequence[str],
    datums_by_id: Mapping[str, Any],
    datum_widget_fills: Mapping[str, Any],
) -> list[str]:
    """
    Dynamic pending/editable subset for the current public stop.

    This is where we keep the important semantic boundary:

        span_owns remains the whole static span vector
        needing_fills is filtered by real satisfaction now

    This keeps public/UI context clean for prefilled spans:
        owns ["A", "B"]
        A already has valid fill data
        pending is only ["B"]
    """

    out: list[str] = []

    for raw_fid in list(span_owns or []):
        fid = str(raw_fid or "").strip()
        if not fid:
            continue

        if not is_this_datum_satisfied_for_this_span_v1(
            self,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_id=fid,
            datum=datums_by_id.get(fid),
            datum_widget_fills=datum_widget_fills,
        ):
            out.append(fid)

    return out


def is_this_span_product_vector_of_datums_satisfied(
    self,
    step: Any,
) -> bool:
    

    hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=True,
        filter_blank_span_owns=True,
    )

    if not hydrated_span["has_multiframespec_mapping"]:
        return False

    frame_id = hydrated_span["frame_id"]
    span_id = hydrated_span["span_id"]
    form_id = hydrated_span["form_id"]
    datums_span_is_responsible_for = hydrated_span["span_owns"]
    datums_authoritative_on_this_span = hydrated_span["span_authoritative"]
    effective_multiframespec = hydrated_span["effective_multiframespec"]
    
    # nothing to satisfy, owns no datum
    if not datums_span_is_responsible_for:
        return True

    # for datums marked owned by span,
    # find out if had writes cached
    try:
        cache = self._get_or_compile_manual_io_cache_v1(
            multiframespec=effective_multiframespec,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_widgets_on_this_span=datums_span_is_responsible_for,
        )
    except Exception:
        # no cache hit
        return False

    # datum shells, identities and cached fills
    datums_raw = cache.get("datums_by_id") if isinstance(cache, Mapping) else {}
    datums_by_id = datums_raw if isinstance(datums_raw, Mapping) else {}
    datum_widget_fills = (
        self._cached_manual_datum_widget_fills_v1(
            cache=cache,
            multiframespec=effective_multiframespec,
            copy_values=False,
        )
    )

    # check the authoritative datums for satisfaction
    # span satisfaction <== all authoritatie datums satisfied
    #
    # We reuse the same dynamic datum satisfaction helper that public/UI context
    # uses to compute datum_widgets_on_this_span. This prevents drift between:
    #   - what the engine considers already satisfied
    #   - what the public receipt says still needs user fill
    pending_authoritative = datum_widgets_on_this_span_for_current_span_v1(
        self,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        span_owns=datums_authoritative_on_this_span,
        datums_by_id=datums_by_id,
        datum_widget_fills=datum_widget_fills,
    )

    return not pending_authoritative