from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from __datomatonTM import (
    Q_SIGNAL_FILL,
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KIND_MANUAL,
    KEY_FORM_FILLS,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    record_just_exploded_datums_writes,
    record_form_fill_writes_v1,
    register_runtime_invocation_v1,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_prefills,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_writing import (
    _apply_mapping_item_patch,
)
from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    apply_q_done_batch_v1,
    apply_q_reexplode_batch_v1,
)
from __datomatonTM import (
    this_datum_has_a_functional_lifecycle,
)
from __datomatonTM import (
    explode_datum_widget,
)
from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
)
from _thinkengine._app_table_engine._engine_runtime_fillspan_state_machine_mechanics.span_main_algos._span_step_related_info_and_hydration import (
    get_step_info_from_app_table_program,
)

from ._span_multiframespec_hydration import (
    hydrate_multiframespec_for_span_v1,
    manual_io_cache_bundle_for_hydrated_span_v1,
)
from ._span_fills_structural_and_semantic_gating import (
    _invalidate_fill_basic_logistical_problems,
    _manual_datum_validators_backend_for_span_v1,
    _partially_validate_manual_datum_fill_for_transition_v1,
    _fully_validate_manual_datum_fill_for_commit_v1,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    EXPLOSION_EVENTS_CALLBACK_KEY,
)

def transition_fillspan_on_incoming_filldata(
    self,
    step: Any,
    *,
    fill: Optional[Dict[str, Any]],
    signal: Optional[Dict[str, Any]] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> bool:
    """
    Transition one MANUAL span on an incoming fill packet.

    Algorithm shape:

        1. Hydrate the current span and compile its current-effective datum shells.
        2. Mount any lifecycle datums that must explode before fill processing.
        3. Logistically gate the submitted fill packet.
        4. For each touched datum:
             - merge submitted fill with existing working/current fill;
             - run partial semantic validation;
             - coerce accepted partial fill into canonical micro values;
             - compute structural required-micro satisfaction;
             - either commit plain datums or invoke lifecycle datums.
        5. If any lifecycle datum reexploded, commit the new current-effective
           datum shells and reinsert the same manual span.
        6. Otherwise, commit completed fills, record lifecycle done state, and
           either advance or reinsert the span if still incomplete.

    Important validation law:

        Partial transition validation tolerates missing required micros, but it
        still validates every provided nonblank micro and macro rule attached to
        the current-effective datum shell.

        Accepted partial fills are canonicalized through datum micros and the
        central MICRO_TYPES registry before being sent to datomaton widgets.

        Final commit validation requires both:
            - structural requiredness;
            - semantic validator success;
            - canonical micro-type coercion success.
    """

    # ---------------------------------------------------------------------
    # 1. Hydrate the span-side world.
    #
    # The transition operates on the current effective multiframespec:
    # static shell + latest committed fills + lifecycle reexploded shells.
    #
    # Keep historical transition behavior: form_id comes from KEY_PENDING_FORM_ID
    # only here, not from app_form_id fallback.
    # ---------------------------------------------------------------------
    hydrated_span = hydrate_multiframespec_for_span_v1(
        self,
        step,
        form_id_fallback_to_multiframespec=False,
        filter_blank_span_owns=False,
    )

    effective_multiframespec = hydrated_span["effective_multiframespec"]
    frame_id = hydrated_span["frame_id"]
    span_id = hydrated_span["span_id"]
    form_id = hydrated_span["form_id"]
    datum_widgets_on_this_span = hydrated_span["span_owns"]
    authoritative_datum_widgets_on_this_span = hydrated_span[
        "span_authoritative"
    ]

    public_step_name, source_step_fn, source_fn_args = (
        get_step_info_from_app_table_program(step)
    )

    # ---------------------------------------------------------------------
    # 2. Compute the dirty subset.
    #
    # span_owns is the static product vector.
    # touched_datum_widgets_that_indeed_need_fills is the submitted subset that
    # is still pending/editable and is allowed to receive data now.
    # ---------------------------------------------------------------------
    touched_datum_widgets_that_indeed_need_fills = list(
        self._filter_pending_datum_set_to_dirtied_subset_given_fills(
            fill=fill,
            datum_widgets_on_this_span=datum_widgets_on_this_span,
            signal=signal,
        )
    )

    signal_row = dict(signal or {}) if isinstance(signal, Mapping) else {}
    signal_target = str(signal_row.get("datum_id") or "").strip()
    signal_kind = str(signal_row.get("kind") or "").strip()
    signal_info = (
        dict(signal_row.get("info") or {})
        if isinstance(signal_row.get("info"), Mapping)
        else {}
    )

    if fill is None and signal_target:
        fill = {}

    # ---------------------------------------------------------------------
    # 3. Deliver mount explosions before fill transition.
    #
    # Mount is span-local. A lifecycle datum can replace its shell before first
    # public render or before this fill is processed. The mount record is also
    # needed for undo bookkeeping if this transition commits.
    # ---------------------------------------------------------------------
    mount_record = self.mount_datums_needing_mounting_on_the_span(
        step,
        threaded_callbacks=threaded_callbacks,
    )

    # ---------------------------------------------------------------------
    # 4. Compile the manual IO/cache bundle from the current-effective shell.
    #
    # datums_by_id contains the datum shells that are authoritative for this
    # transition. Validators are built from those shells, not from historical
    # shells and not auto-injected from the micro registry.
    # ---------------------------------------------------------------------
    cache_bundle = manual_io_cache_bundle_for_hydrated_span_v1(
        self,
        hydrated_span=hydrated_span,
        datum_widgets_on_this_span=datum_widgets_on_this_span,
        copy_values=False,
    )
    cache = cache_bundle["cache"]
    datums_by_id = cache_bundle["datums_by_id"]

    validators_by_id = _manual_datum_validators_backend_for_span_v1(
        cache=cache,
        datums_by_id=datums_by_id,
    )

    # ---------------------------------------------------------------------
    # 5. Cheap packet-level gate.
    #
    # This checks the fill envelope before datum-level semantics:
    # missing payload, wrong type, dead-JSON membrane, extraneous datum ids,
    # and attempts to fill datums that do not currently need input.
    # ---------------------------------------------------------------------
    logistically_valid = _invalidate_fill_basic_logistical_problems(
        self,
        fill,
        datum_widgets_on_this_span,
        touched_datum_widgets_that_indeed_need_fills,
        signal=signal,
    )

    if not logistically_valid:
        return False

    # ---------------------------------------------------------------------
    # 6. Mark lifecycle datums as actively processing.
    #
    # This allows surrounding engine/session machinery to know which lifecycle
    # datums are being evaluated during this transition.
    # ---------------------------------------------------------------------
    lifecycle_touched = [
        str(fid)
        for fid in touched_datum_widgets_that_indeed_need_fills
        if isinstance(datums_by_id.get(str(fid)), Mapping)
        and this_datum_has_a_functional_lifecycle(datums_by_id.get(str(fid)))
    ]

    begin_processing = getattr(
        self,
        "_begin_datum_lifecycle_processing_v1",
        None,
    )
    end_processing = getattr(
        self,
        "_end_datum_lifecycle_processing_v1",
        None,
    )

    processing_token = None
    if lifecycle_touched and callable(begin_processing):
        processing_token = begin_processing(lifecycle_touched)

    # ---------------------------------------------------------------------
    # 7. Establish the candidate-fill base.
    #
    # existing_base comes from the render/cache view.
    # overlays are latest same-span working data, such as fills preserved across
    # a reexplode. New submitted values are merged per datum later.
    # ---------------------------------------------------------------------
    existing_base = cache_bundle["datum_widget_fills"]
    overlays = self.manual_get_latest_engine_form_page_data_read(
        form_id=str(form_id),
        frame_id=frame_id,
        span_id=span_id,
    )

    if overlays:
        existing = dict(existing_base)
        existing.update(overlays)
    else:
        existing = existing_base

    committed: Dict[str, Any] = {}
    working_fills: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    datum_widget_explosions = []
    reexplode_evals = []
    prefills_snapshot = get_form_prefills(self.state)

    try:
        # -----------------------------------------------------------------
        # 8. Process each touched datum independently.
        #
        # Each datum uses its own current-effective shell and validator backend.
        # A bad datum records an error but does not stop sibling inspection.
        # -----------------------------------------------------------------
        for fid in touched_datum_widgets_that_indeed_need_fills:
            datum = datums_by_id.get(fid)
            if datum is None:
                errors[fid] = "unknown datum id"
                continue

            try:
                validator = validators_by_id.get(fid)

                # ---------------------------------------------------------
                # 8a. Build, partially validate, and canonicalize this datum.
                #
                # This is the semantic seam:
                #   existing + submitted -> candidate
                #   candidate -> partial validator pass on raw data
                #   accepted raw -> micro-type coercion via datum micros
                #   canonical partial -> validator pass again
                #   canonical partial -> structural satisfaction bool
                #
                # Missing required micros are tolerated here, but provided
                # nonblank values still run their micro/macro validators.
                #
                # After this helper returns:
                #   - candidate is the raw merged input;
                #   - partially_validated is canonical/coerced accepted data.
                # ---------------------------------------------------------
                validation_bundle = (
                    _partially_validate_manual_datum_fill_for_transition_v1(
                        fid=fid,
                        datum=datum,
                        validator=validator,
                        fill=fill,
                        existing=existing,
                    )
                )
                candidate = validation_bundle["candidate"]
                partially_validated = validation_bundle[
                    "partially_validated"
                ]
                structurally_satisfied = validation_bundle[
                    "structurally_satisfied"
                ]

                # ---------------------------------------------------------
                # 8b. Plain datum path.
                #
                # Plain datums do not mediate partial micro progress through a
                # lifecycle widget. If their required micros are not complete,
                # the datum remains unaccepted for this tick.
                # ---------------------------------------------------------
                if not this_datum_has_a_functional_lifecycle(datum):
                    if fid == signal_target and fid not in dict(fill or {}):
                        errors[fid] = (
                            "signal-only action requires a lifecycle datum"
                        )
                        continue

                    if not structurally_satisfied:
                        errors[fid] = "required fields missing"
                        continue

                    validated = _fully_validate_manual_datum_fill_for_commit_v1(
                        fid=fid,
                        datum=datum,
                        validator=validator,
                        partially_validated=partially_validated,
                    )
                    committed[fid] = validated
                    working_fills[fid] = validated
                    continue

                # ---------------------------------------------------------
                # 8c. Lifecycle datum path.
                #
                # The widget observes:
                #   - raw_fill: the raw merged candidate;
                #   - partial_fill: accepted + canonical/coerced data;
                #   - structurally_satisfied: required-micro completeness.
                #
                # The widget decides whether this datum is blocked, done, or
                # wants to reexplode into a new shell.
                # ---------------------------------------------------------
                datum_widget_explosion = explode_datum_widget(
                    state=self.state,
                    form_id=str(form_id),
                    frame_id=str(frame_id),
                    span_id=str(span_id),
                    datum_id=str(fid),
                    datum=datum,
                    raw_fill=candidate,
                    partial_fill=partially_validated,
                    prefill=prefills_snapshot.get(fid),
                    structurally_satisfied=bool(structurally_satisfied),
                    signal_kind=(
                        signal_kind
                        if fid == signal_target and signal_kind
                        else Q_SIGNAL_FILL
                    ),
                    signal_info=(
                        {
                            **signal_info,
                            "source": "controller_action",
                            "datum_id": fid,
                        }
                        if fid == signal_target and signal_kind
                        else {}
                    ),
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
                datum_widget_explosions.append(datum_widget_explosion)

                # Widget says: keep the same shell public and surface an error.
                if datum_widget_explosion.status == Q_STATUS_BLOCKED:
                    errors[fid] = (
                        datum_widget_explosion.message.get("text")
                        or "datum blocked"
                    )
                    continue

                # Widget says: replace the current-effective shell.
                #
                # The working fill either comes from result["fill"] or, if the
                # widget omitted it, from the canonical partially validated
                # candidate.
                if datum_widget_explosion.status == Q_STATUS_REEXPLODE:
                    reexplode_evals.append(datum_widget_explosion)
                    working_fills[fid] = (
                        datum_widget_explosion.working_fill
                        if datum_widget_explosion.has_working_fill
                        else partially_validated
                    )
                    continue

                # Widget says: commit this datum.
                #
                # Normal done still runs full required+semantic validation.
                # forced_done is the explicit lifecycle escape hatch. Even then,
                # partial validation has already canonicalized the value.
                if datum_widget_explosion.status == Q_STATUS_DONE:
                    if datum_widget_explosion.forced_done:
                        committed[fid] = partially_validated
                    else:
                        validated = _fully_validate_manual_datum_fill_for_commit_v1(
                            fid=fid,
                            datum=datum,
                            validator=validator,
                            partially_validated=partially_validated,
                        )
                        committed[fid] = validated

                    working_fills[fid] = committed[fid]
                    continue

                errors[fid] = (
                    "unknown datum lifecycle status: "
                    f"{datum_widget_explosion.status!r}"
                )

            except DeadJSONError as e:
                errors[fid] = (
                    "validated fill became non-JSON: "
                    f"{e}"
                )
            except ValueError as e:
                errors[fid] = str(e)

    finally:
        if processing_token is not None and callable(end_processing):
            end_processing(processing_token)

    # ---------------------------------------------------------------------
    # 9. Any datum-level error rejects this transition.
    #
    # No fills or lifecycle replacements are committed when the transition has
    # errors. The same public span remains active with last_error populated.
    # ---------------------------------------------------------------------
    if errors:
        self.last_error = dict(errors)
        return False

    # ---------------------------------------------------------------------
    # 10. Reexplode branch.
    #
    # At least one lifecycle datum authored a replacement datum shell. Commit
    # those current-effective shells, preserve working fills, clear stale cache,
    # record the lifecycle write, and reinsert the same manual span.
    # ---------------------------------------------------------------------
    if reexplode_evals:
        lifecycle_undo = apply_q_reexplode_batch_v1(
            state=self.state,
            form_id=str(form_id),
            frame_id=str(frame_id),
            span_id=str(span_id),
            evaluations=list(reexplode_evals),
            working_fills=working_fills,
        )

        clear_cache = getattr(
            self,
            "clear_manual_io_cache_v1",
            None,
        )
        if callable(clear_cache):
            clear_cache()

        seq = register_runtime_invocation_v1(
            self.state,
            public_step_name=public_step_name,
            step_fn=source_step_fn,
            fn_args=source_fn_args,
            invocation_kind="datum_lifecycle_reexplode",
        )

        record_just_exploded_datums_writes(
            self.state,
            seq=seq,
            form_id=str(form_id),
            datum_ids=[
                ev.datum_id
                for ev in reexplode_evals
            ],
            status="reexplode",
        )

        replacement = type(step)(
            kind=KIND_MANUAL,
            payload=dict(step.payload),
        )
        self.program[
            self.cursor + 1 : self.cursor + 1
        ] = [replacement]

        from _thinkengine._app_table_engine.engine_class import ExecRecord

        self.exec_records[self.cursor] = ExecRecord(
            undo_patch=(
                dict(mount_record.get("undo_patch") or {})
                if isinstance(mount_record, Mapping)
                else lifecycle_undo
            ),
            inserted_steps=1,
            index_seq=seq,
            redo_action={
                "kind": "manual_step",
                "fill": dict(fill),
                "signal": dict(signal or {}) if isinstance(signal, Mapping) else None,
            },
        )
        return True

    # ---------------------------------------------------------------------
    # 11. Done/no-reexplode branch.
    #
    # Lifecycle datums that returned done write their current lifecycle state.
    # Plain and lifecycle datum fills that passed full validation are now
    # candidates for durable form_fills.
    # ---------------------------------------------------------------------
    lifecycle_done_undo = {}
    if datum_widget_explosions:
        lifecycle_done_undo = apply_q_done_batch_v1(
            state=self.state,
            form_id=str(form_id),
            frame_id=str(frame_id),
            span_id=str(span_id),
            evaluations=list(datum_widget_explosions),
        )

    datum_widget_fills_after_attempt = dict(existing)
    datum_widget_fills_after_attempt.update(committed)

    # ---------------------------------------------------------------------
    # 12. Decide whether the whole span product vector is complete.
    #
    # This check uses the same current-effective datum satisfaction semantics
    # as rendering. It prevents drift between what the UI says is pending and
    # what the engine considers complete.
    # ---------------------------------------------------------------------
    span_complete = (
        self._span_satisfied_without_untouched_datum_widget_explosion_v1(
            form_id=str(form_id),
            span_owns=datum_widgets_on_this_span,
            span_authoritative=authoritative_datum_widgets_on_this_span,
            datums_by_id=datums_by_id,
            datum_widget_fills=datum_widget_fills_after_attempt,
        )
    )

    # ---------------------------------------------------------------------
    # 13. If the span is complete, force/commit any remaining completion fills.
    #
    # This handles non-authoritative or previously satisfied members of the span
    # product vector so final form_fills are coherent at completion.
    #
    # The helper is given the same final validation function used above, so any
    # forced completion commits can also be canonicalized by datum micro type.
    # ---------------------------------------------------------------------
    if span_complete:
        completion_commits = (
            self._commit_completion_of_spans_including_forcing_non_authoritative_datum_doneness(
                span_owns=datum_widgets_on_this_span,
                datums_by_id=datums_by_id,
                validators_by_id=validators_by_id,
                datum_widget_fills=datum_widget_fills_after_attempt,
                already_committed=committed,
                fully_validate_manual_datum_fill_for_commit_v1=(
                    _fully_validate_manual_datum_fill_for_commit_v1
                ),
            )
        )
        if completion_commits:
            committed.update(completion_commits)
            datum_widget_fills_after_attempt.update(
                completion_commits
            )

    # ---------------------------------------------------------------------
    # 14. Persist durable form fills.
    #
    # Only committed datum fills enter KEY_FORM_FILLS. Working fills used during
    # reexplode live through lifecycle/manual-page overlays, not this bucket.
    # ---------------------------------------------------------------------
    if committed:
        fill_undo = _apply_mapping_item_patch(
            self.state,
            bucket_key=KEY_FORM_FILLS,
            items=committed,
        )
    else:
        fill_undo = {}

    # ---------------------------------------------------------------------
    # 15. Build undo patch.
    #
    # A single public manual tick may include normal fills, lifecycle done state,
    # and mount side effects. Undo must restore all of them together.
    # ---------------------------------------------------------------------
    undo = dict(fill_undo)

    if datum_widget_explosions:
        undo[
            "__datum_lifecycle_done_undo_v1__"
        ] = lifecycle_done_undo

    if isinstance(mount_record, Mapping):
        mount_undo = dict(mount_record.get("undo_patch") or {})
        if mount_undo:
            undo["__datum_lifecycle_mount_undo_v1__"] = mount_undo

    # ---------------------------------------------------------------------
    # 16. Record the manual fill invocation.
    # ---------------------------------------------------------------------
    seq = register_runtime_invocation_v1(
        self.state,
        public_step_name=public_step_name,
        step_fn=source_step_fn,
        fn_args=source_fn_args,
        invocation_kind="manual_fill",
    )

    # ---------------------------------------------------------------------
    # 17. Reinsert the same span if the product vector is still incomplete.
    #
    # This is normal partial-span progress: some datums may have committed while
    # other authoritative datums on the same span still need input.
    # ---------------------------------------------------------------------
    inserted_steps = 0
    if not span_complete:
        replacement = type(step)(
            kind=KIND_MANUAL,
            payload=dict(step.payload),
        )
        self.program[
            self.cursor + 1 : self.cursor + 1
        ] = [replacement]
        inserted_steps = 1

    # ---------------------------------------------------------------------
    # 18. Refresh manual IO cache and write index.
    # ---------------------------------------------------------------------
    self._update_manual_cache_datum_widget_fills_v1(
        cache=cache,
        committed=committed,
    )

    record_form_fill_writes_v1(
        self.state,
        seq=seq,
        form_id=str(form_id),
        fills=committed,
    )

    if datum_widget_explosions:
        record_just_exploded_datums_writes(
            self.state,
            seq=seq,
            form_id=str(form_id),
            datum_ids=[
                ev.datum_id
                for ev in datum_widget_explosions
            ],
            status="done",
        )

    # ---------------------------------------------------------------------
    # 19. Finalize redo/undo metadata for this public manual tick.
    # ---------------------------------------------------------------------
    from _thinkengine._app_table_engine.engine_class import ExecRecord

    self.exec_records[self.cursor] = ExecRecord(
        undo_patch=undo,
        inserted_steps=inserted_steps,
        index_seq=seq,
        redo_action={
            "kind": "manual_step",
            "fill": dict(fill),
            "signal": dict(signal or {}) if isinstance(signal, Mapping) else None,
        },
    )
    return True