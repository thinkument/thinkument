# think-backend/src/thinkengine/_app_table_engine/engine/
# _engine_runtime_fillspan_state_machine_mechanics/
# span_main_algos/span_output_context.py

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from __exceptions.engine import FatalEngineError

from __multiframespecTM.api import (
    overlay_multiframespec_manual_render_context,
)

from __datomatonTM import (
    build_universal_ui_datum_state_v1,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KIND_MANUAL,
    KEY_PENDING_FORM_ID,
)

from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_APP_FORM_ID,
    CTX_CURSOR,
    CTX_DATUM_STATES_ON_THIS_SPAN,
    CTX_DATUM_WIDGET_FILLS,
    CTX_DATUM_WIDGETS_ON_THIS_SPAN,
    CTX_FORM_ID,
    CTX_GLOBALS,
    CTX_KIND,
    CTX_LAST_ERROR,
    CTX_SESSION_ID,
    CTX_SESSION_METADATA,
    CTX_STATE,
    CTX_STEP,
)

from .span_satisfaction import (
    datum_widgets_on_this_span_for_current_span_v1,
)
from ._span_multiframespec_hydration import (
    hydrate_multiframespec_for_span_v1,
    manual_io_cache_bundle_for_hydrated_span_v1,
)


def output_fillspan_universal_ui_context(
    self,
    step: Any,
    *,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the universal UI context for the current manual fillspan.

    Entering a manual span may deliver mount-time lifecycle signals. A mount
    explosion may structurally replace one or more active datum shells, so any
    span/multiframespec hydration obtained before mounting is invalid for
    rendering after mounting.

    The rendering law is therefore:

        hydrate addressing
        -> mount lifecycle datums
        -> rehydrate structural state
        -> compile/read render cache
        -> calculate dynamic pending datums
        -> release U

    Dispatch-scoped callbacks are forwarded to mounting so lifecycle events
    participate in the same controller timeline:

        controller.loop.start
        zero or more datum lifecycle events
        controller.loop.end
    """

    # ------------------------------------------------------------------
    # Pre-mount hydration
    # ------------------------------------------------------------------
    #
    # This hydration provides the addressing required to locate and mount the
    # active form/frame/span. It must not be reused for rendering after mount,
    # because mount-time Reexplode may replace datum micros, titles, lifecycle
    # configuration, prefills, or other structural shell data.
    pre_mount_hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=True,
        coerce_non_mapping_multiframespec_to_empty=True,
        filter_blank_span_owns=True,
    )

    # Mount is part of entering/rendering a manual span. Forward the active
    # callback bag so mount lifecycle packets are captured synchronously by
    # integrations.
    self.mount_datums_needing_mounting_on_the_span(
        step,
        threaded_callbacks=threaded_callbacks,
    )

    # ------------------------------------------------------------------
    # Post-mount hydration
    # ------------------------------------------------------------------
    #
    # Mount may have applied a lifecycle structural patch. Rehydrate from the
    # canonical engine memory before compiling or reading any render artifacts.
    # This guarantees that controller-end U contains the shell produced by the
    # mount explosion rather than the authored pre-mount shell.
    hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=True,
        coerce_non_mapping_multiframespec_to_empty=True,
        filter_blank_span_owns=True,
    )

    frame_id = hydrated_span["frame_id"]
    span_id = hydrated_span["span_id"]
    form_id = hydrated_span["form_id"]

    # Static ownership is the complete product vector for the span. It is not
    # necessarily the subset still requiring external input.
    datums_span_is_responsible_for = hydrated_span["span_owns"]
    authoritative_datums = hydrated_span["span_authoritative"]
    effective_multiframespec = hydrated_span["effective_multiframespec"]

    # Build/read the cache only after post-mount hydration. The cache key's
    # structural epoch then corresponds to the shell that will actually be
    # exposed in U.
    cache_bundle = manual_io_cache_bundle_for_hydrated_span_v1(
        self,
        hydrated_span=hydrated_span,
        datum_widgets_on_this_span=datums_span_is_responsible_for,
        copy_values=True,
    )
    cache = cache_bundle["cache"]
    fv = dict(cache_bundle["datum_widget_fills"])
    datums_by_id = cache_bundle["datums_by_id"]

    # Di shell authority is the latest effective hydrated multiframespec,
    # not the compiled renderer cache.
    #
    # The render cache is allowed to normalize declarations and micro records
    # for rendering, for example by inserting empty tags/default fields.
    # U.multiframespec and U.datum_states_on_this_span must nevertheless expose
    # one exact common shell object value for the same effective datum.
    effective_datums_raw = effective_multiframespec.get("datums")
    if effective_datums_raw is None:
        effective_datums_raw = []
    if not isinstance(effective_datums_raw, list):
        raise FatalEngineError(
            "effective multiframespec datums must be a list"
        )

    effective_datums_by_id: Dict[str, Mapping[str, Any]] = {}
    for datum_index, raw_datum in enumerate(effective_datums_raw):
        if not isinstance(raw_datum, Mapping):
            raise FatalEngineError(
                "effective multiframespec datum must be a mapping: "
                f"datums[{datum_index}]"
            )

        effective_datum_id = str(
            raw_datum.get("id")
            or ""
        ).strip()
        if not effective_datum_id:
            raise FatalEngineError(
                "effective multiframespec datum has an empty id: "
                f"datums[{datum_index}]"
            )
        if effective_datum_id in effective_datums_by_id:
            raise FatalEngineError(
                "effective multiframespec contains duplicate datum id: "
                f"{effective_datum_id!r}"
            )

        effective_datums_by_id[effective_datum_id] = raw_datum

    # Dynamic pending/editable subset:
    #
    # span_owns may be ["A", "B"], while only B still needs input. Keep the full
    # structural declarations in the render bundle, but expose only currently
    # pending datums through datum_widgets_on_this_span.
    datum_widgets_on_this_span = (
        datum_widgets_on_this_span_for_current_span_v1(
            self,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            span_owns=datums_span_is_responsible_for,
            datums_by_id=datums_by_id,
            datum_widget_fills=fv,
        )
    )

    pending_ids = {
        str(value)
        for value in datum_widgets_on_this_span
    }
    authoritative_ids = {
        str(value)
        for value in authoritative_datums
    }

    datum_states_on_this_span = []
    for raw_datum_id in datums_span_is_responsible_for:
        datum_id = str(raw_datum_id)
        datum = effective_datums_by_id.get(datum_id)
        if not isinstance(datum, Mapping):
            raise FatalEngineError(
                "manual span owns a datum absent from the latest effective "
                f"multiframespec: {datum_id!r}"
            )

        datum_states_on_this_span.append(
            build_universal_ui_datum_state_v1(
                state=self.state,
                form_id=str(form_id),
                frame_id=str(frame_id),
                span_id=str(span_id),
                datum_id=datum_id,
                datum=datum,
                fill=fv.get(datum_id),
                has_fill=datum_id in fv,
                is_authoritative=(
                    datum_id in authoritative_ids
                ),
                is_pending=datum_id in pending_ids,
                originating_step=step.payload,
            )
        )

    expected_datum_ids = [
        str(value)
        for value in datums_span_is_responsible_for
    ]
    actual_datum_ids = [
        str(row.get("datum_id") or "")
        for row in datum_states_on_this_span
    ]
    if actual_datum_ids != expected_datum_ids:
        raise FatalEngineError(
            "datum_states_on_this_span must be a one-to-one ownership-order "
            "projection of span_owns: "
            f"expected={expected_datum_ids!r}, actual={actual_datum_ids!r}"
        )

    req = {
        "frame_id": frame_id,
        "span_id": span_id,
        "readonly": False,
        CTX_DATUM_WIDGET_FILLS: fv,
        CTX_DATUM_WIDGETS_ON_THIS_SPAN: datum_widgets_on_this_span,
        CTX_DATUM_STATES_ON_THIS_SPAN: (
            datum_states_on_this_span
        ),
        CTX_LAST_ERROR: self.last_error,
        CTX_SESSION_METADATA: dict(self.session_metadata),
        CTX_CURSOR: {
            "index": self.cursor,
            "total": len(self.program),
        },
        CTX_KIND: KIND_MANUAL,
        CTX_SESSION_ID: str(self.session_id),
    }

    policy_fn = getattr(self, "manual_io_policy_v1", None)
    policy = policy_fn() if callable(policy_fn) else {}

    include_full_multiframespec = bool(
        policy.get(
            "include_full_multiframespec_in_ctx",
            True,
        )
    )

    ui_ctx = overlay_multiframespec_manual_render_context(
        render_bundle=cache,
        multiframespec=effective_multiframespec,
        render_request=req,
        include_full_multiframespec=include_full_multiframespec,
    )

    # The overlay may reuse values from the compiled render bundle. Reassert
    # values owned by this runtime layer:
    #
    # - the current merged working fills;
    # - the current dynamically pending/editable datum subset;
    # - the complete static current-span datum observation vector.
    ui_ctx[CTX_DATUM_WIDGET_FILLS] = fv
    ui_ctx[CTX_DATUM_WIDGETS_ON_THIS_SPAN] = (
        datum_widgets_on_this_span
    )
    ui_ctx[CTX_DATUM_STATES_ON_THIS_SPAN] = (
        datum_states_on_this_span
    )

    ui_ctx[CTX_SESSION_ID] = self.session_id
    ui_ctx[CTX_FORM_ID] = self.state.get(KEY_PENDING_FORM_ID)
    ui_ctx[CTX_APP_FORM_ID] = self.state.get(KEY_PENDING_FORM_ID)
    ui_ctx[CTX_STEP] = dict(step.payload)
    ui_ctx[CTX_STATE] = self._manual_ctx_state_summary_v1(
        pending_multiframespec=effective_multiframespec,
        datum_widget_fills=fv,
    )
    ui_ctx[CTX_GLOBALS] = self._globals_view()

    return ui_ctx