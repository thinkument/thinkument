from typing import Any, Dict, Mapping, Optional

from __datomatonTM import (
    this_datum_has_a_functional_lifecycle,
    read_datum_system_flags_limits,
    KEY_DATUM_LIFECYCLE,
)

from _thinkprogram._iomicrosTM.core.api_fills import (
    datum_fill_data_meets_its_structural_micros_shell,
)

from __multiframespecTM.api import (
    span_key_v1
)

from __datomatonTM._eval import explode_datum_widget

from __datomatonTM import (
    Q_SIGNAL_MOUNT,
)

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    apply_q_mount_batch_v1,
)

from _thinkengine._app_table_engine._engine_runtime_fillspan_state_machine_mechanics.span_main_algos._span_step_related_info_and_hydration import (
        get_step_info_from_app_table_program
)

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    record_just_exploded_datums_writes,
    register_runtime_invocation_v1,
)

from ._span_multiframespec_hydration import (
    hydrate_multiframespec_for_span_v1,
    static_datum_and_scoped_fill_bundle_for_effective_multiframespec_v1,
)

from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    EXPLOSION_EVENTS_CALLBACK_KEY,
)

# every span is a vector S = (D1, .., Dk)
# where each Di is a datum with its own state
# and ability ro reexplode till satisfaction
# and from pov of one span a datum can only be monotonically
# satisfied as we step forward w fill data on the span
# and the span is satisfied when all its authritative datums are

# here we check that each datum on the span had its initial
# mounting explosion if it wanted to explode when first hit
# and any datum's first time on a span and wans to mount
# then this span has datums needing to mount explode
def does_this_datum_want_mount_and_has_yet_to_undergo_mount_explosion_on_this_span(
    *,
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    datum: Mapping[str, Any],
) -> bool:
    """
    True when a lifecycle datum has opted into mount-time reexplosion and the
    current form/frame/span mounting signal has not yet been delivered.

    Mounting is span-local:

        same datum on S1 mounts once for S1
        same datum on S2 mounts once for S2

    This is the key that lets a same logical datum id reappear on a future span
    without being blindly skipped merely because it was satisfied earlier.
    """

    #### these datums have no mount needs

    # does not even have an explosion widget fn
    if not this_datum_has_a_functional_lifecycle(datum):
        return False

    # did not even want mounting as part of its life
    # even if has widget fn that wil explode on inputs
    # as any datum w explosion widget fn
    policy = read_datum_system_flags_limits(datum)
    if not bool(policy.get("mount_explode", False)):
        return False

    ####

    # ok now onto the datums that HAVE a lifecycle fn
    # and they WANT to mount

    # do we even have a memory page (form) for this form id we are working with?
    store = state.get(KEY_DATUM_LIFECYCLE)
    forms = store.get("forms") if isinstance(store, Mapping) else None
    form_row = (
        forms.get(str(form_id or ""))
        if isinstance(forms, Mapping)
        else None
    )

    if not isinstance(form_row, Mapping):
        return True

    # we did find an engine page in memory for this form
    # aka this multiframespec flow

    # (i) but does it have this datum as a row within its datums known?
    datums = form_row.get("datums")
    row = (
        datums.get(str(datum_id))
        if isinstance(datums, Mapping)
        else None
    )
    if row is None:
        return True

    # (ii) we might have found the datum row but... does that DATUM mark
    # spans on which it has been mounted before?
    spans_that_this_datum_was_mounted_on = row.get("spans_mounted_on")
    if not isinstance(spans_that_this_datum_was_mounted_on, Mapping):
        return True

    # and is this span one on which its mounting has happened already or not?
    sk = span_key_v1(frame_id, span_id)
    if sk not in spans_that_this_datum_was_mounted_on:
        return True

    return False


def mount_datums_needing_mounting_on_the_span(
    self,
    step: Any,
    *,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Mount all datums on the span that need mounting and have not been mounted yet
    """

    hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=True,
        filter_blank_span_owns=True,
    )

    frame_id = hydrated_span["frame_id"]
    span_id = hydrated_span["span_id"]
    form_id = hydrated_span["form_id"]
    datum_widgets_on_this_span = hydrated_span["span_owns"]
    effective_multiframespec = hydrated_span["effective_multiframespec"]

    datum_and_fill_bundle = (
        static_datum_and_scoped_fill_bundle_for_effective_multiframespec_v1(
            self,
            effective_multiframespec=effective_multiframespec,
        )
    )
    datums_by_id = datum_and_fill_bundle["datums_by_id"]
    prefills_snapshot = datum_and_fill_bundle["prefills_snapshot"]
    existing_datum_fill_data = datum_and_fill_bundle[
        "existing_datum_fill_data"
    ]

    datums_that_undergo_mounting_now = []
    new_fills_data_from_reexplosion: Dict[str, Any] = {}

    for fid in datum_widgets_on_this_span:
        datum = datums_by_id.get(fid)

        # note how a datum can reexplode for mount as this span mounts even if it participated
        # on a span in the past and had its own share of "fun" (explosions) on those spans already
        if not does_this_datum_want_mount_and_has_yet_to_undergo_mount_explosion_on_this_span(
            state=self.state,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_id=fid,
            datum=datum,
        ):
            continue

        raw_fill = existing_datum_fill_data.get(fid)

        partial_fill = (dict(raw_fill) if isinstance(raw_fill, Mapping) else {})

        # any datum NEEDS its current datumspec (micros making it up)
        # to be structurally satisfied like if a micro needs a string and gets an int etc
        structurally_satisfied = bool(
            datum_fill_data_meets_its_structural_micros_shell(
                datum,
                raw_fill,
            )
        )

        # the main course for this datum's mount explosion
        ev = explode_datum_widget(
            state=self.state,
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_id=fid,
            datum=datum,
            raw_fill=raw_fill,
            partial_fill=partial_fill,
            prefill=prefills_snapshot.get(fid),
            structurally_satisfied=structurally_satisfied,
            signal_kind=Q_SIGNAL_MOUNT,
            signal_info={
                "form_id": form_id,
                "frame_id": frame_id,
                "span_id": span_id,
                "datum_id": fid,
                "datum_widgets_on_this_span": list(
                    datum_widgets_on_this_span
                ),
                "span_owns": list(datum_widgets_on_this_span),
            },
            event_sink=getattr(
                self,
                "_emit_datum_event_to_engine_session",
                None,
            ),
            event_callback=(
                dict(threaded_callbacks or {}).get(
                    EXPLOSION_EVENTS_CALLBACK_KEY
                )
            ),
        )
        datums_that_undergo_mounting_now.append(ev)

        # if datum widget explodes and gives new fills / prefills
        if ev.has_working_fill:
            new_fills_data_from_reexplosion[fid] = ev.working_fill

    if not datums_that_undergo_mounting_now:
        return None

    # some datums exploded so need to track those new datas for proper undo later
    lifecycle_undo = apply_q_mount_batch_v1(
        state=self.state,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        evaluations=list(datums_that_undergo_mounting_now),
        working_fills=new_fills_data_from_reexplosion,
    )

    # get the app table public step on program's info
    public_step_name, source_step_fn, source_fn_args = get_step_info_from_app_table_program(step)

    # any functional being called within a stepfn's own function run and return and filling of its frmespec
    # through its spans has the functional call logged
    # here we log the reexplosion
    seq = register_runtime_invocation_v1(
        self.state,
        public_step_name=public_step_name,
        step_fn=source_step_fn,
        fn_args=source_fn_args,
        invocation_kind="datum_lifecycle_mount",
    )

    # update datum vector / init the datum vector WITHIN ths span product vector space
    record_just_exploded_datums_writes(
        self.state,
        seq=seq,
        form_id=form_id,
        datum_ids=[
            ev.datum_id
            for ev in datums_that_undergo_mounting_now
        ],
        status="mount",
    )

    return {
        "undo_patch": lifecycle_undo,
        "index_seq": seq,
    }