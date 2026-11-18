# think-backend/src/thinkengine/_app_table_engine/engine/_engine_runtime_fillspan_state_machine_mechanics/fillspan_lifecycle.py

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from _thinkprogram._iomicrosTM.core.api_fills import (
    build_datum_validator,
    datum_fill_data_meets_its_structural_micros_shell,
)
from _thinkprogram._iomicrosTM.tiny_helpers import _json_compact_dumps

from __multiframespecTM.api import (
    build_multiframespec_scoped_datum_fill_map,
)

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    apply_q_mount_batch_v1,
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)

from __datomatonTM import (
    this_datum_has_a_functional_lifecycle,
)

from __datomatonTM._eval import explode_datum_widget

from __datomatonTM import (
    Q_SIGNAL_MOUNT,
    is_this_datum_automaton_in_satisfied_sink_state,
)

from __exceptions.engine import (
    FatalEngineError,
    InvalidExternalFillError,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    record_just_exploded_datums_writes,
    register_runtime_invocation_v1,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fills,
    get_form_prefills,
)
from _thinkengine._parsing.app_table_program_parser import (
    DeadJSONError,
    assert_dead_json,
)

from .span_main_algos.span_satisfaction import (
    is_this_span_product_vector_of_datums_satisfied,
)

from .span_main_algos.span_mounting import (
    mount_datums_needing_mounting_on_the_span,
)


class FillspanLifecycleMixin:
    """
    Manual fillspan rendering, span satisfaction, incoming fill validation,
    datum lifecycle mount/reexplode/done handling, and manual-step completion.

    This mixin expects ManualIOTapeMechanicsMixin to also be present on the
    concrete engine.
    """

    # QQQQQQQQ
    def _enforce_manual_fill_size_limits(
        self,
        *,
        fill: Mapping[str, Any],
    ) -> None:
        policy_fn = getattr(
            self,
            "manual_io_policy_v1",
            None,
        )
        policy = policy_fn() if callable(policy_fn) else {}

        max_fields = int(
            policy.get("max_fields_per_submit") or 0
        )
        if max_fields > 0 and len(fill) > max_fields:
            raise InvalidExternalFillError(
                "manual fill payload has too many top-level fields: "
                f"{len(fill)} > {max_fields}. "
                "This guard prevents accidental wide-form or "
                "adversarial submits. If this is intentional, set "
                "session_metadata['manual_io']"
                "['max_fields_per_submit']=0."
            )

        max_payload_chars = int(
            policy.get("max_payload_chars") or 0
        )
        if max_payload_chars > 0:
            try:
                payload_chars = len(
                    _json_compact_dumps(dict(fill))
                )
            except Exception as e:
                raise InvalidExternalFillError(
                    "manual fill payload is not compact-JSON-"
                    f"serializable: {e}"
                ) from e

            if payload_chars > max_payload_chars:
                raise InvalidExternalFillError(
                    "manual fill payload is too large for the "
                    "default manual-IO artery: "
                    f"{payload_chars} chars > "
                    f"{max_payload_chars}. "
                    "Large values are allowed only by explicit "
                    "opt-in because they scale real validation/"
                    "state/storage work. If intentional, set "
                    "session_metadata['manual_io']"
                    "['max_payload_chars']=0 or raise the cap."
                )

    def _filter_pending_datum_set_to_dirtied_subset_given_fills(
        self,
        *,
        fill: Optional[Mapping[str, Any]],
        datum_widgets_on_this_span: Sequence[str],
        signal: Optional[Mapping[str, Any]] = None,
    ) -> List[str]:
        pending = [
            str(x)
            for x in list(datum_widgets_on_this_span or [])
            if str(x or "").strip()
        ]

        signal_target = ""
        if isinstance(signal, Mapping):
            signal_target = str(signal.get("datum_id") or "").strip()

        if not fill and not signal_target:
            return pending

        if fill is not None and not isinstance(fill, Mapping):
            raise InvalidExternalFillError(
                "manual fill payload is not a mapping"
            )

        fill_ids = {
            str(k)
            for k in dict(fill or {}).keys()
        }
        if signal_target:
            fill_ids.add(signal_target)

        out = [
            fid
            for fid in pending
            if fid in fill_ids
        ]

        return out

    def _span_satisfied_without_untouched_datum_widget_explosion_v1(
        self,
        *,
        form_id: str,
        span_owns: Sequence[str],
        span_authoritative: Sequence[str],
        datums_by_id: Mapping[str, Any],
        datum_widget_fills: Mapping[str, Any],
    ) -> bool:
        authoritative = [
            str(x)
            for x in list(span_authoritative or span_owns or [])
            if str(x or "").strip()
        ]
        if not authoritative:
            return False

        for fid in authoritative:
            datum = datums_by_id.get(fid)
            if not isinstance(datum, Mapping):
                return False

            if is_this_datum_automaton_in_satisfied_sink_state(
                state=self.state,
                form_id=str(form_id),
                datum_id=str(fid),
            ):
                continue

            if this_datum_has_a_functional_lifecycle(datum):
                return False

            try:
                if datum_fill_data_meets_its_structural_micros_shell(
                    datum,
                    datum_widget_fills.get(fid),
                ):
                    continue
            except Exception:
                return False

            return False

        return True

    def _commit_completion_of_spans_including_forcing_non_authoritative_datum_doneness(
        self,
        *,
        span_owns: Sequence[str],
        datums_by_id: Mapping[str, Any],
        validators_by_id: Dict[str, Any],
        datum_widget_fills: Mapping[str, Any],
        already_committed: Mapping[str, Any],
        fully_validate_manual_datum_fill_for_commit_v1=None,
    ) -> Dict[str, Any]:
        """
        When the whole span is complete, force/commit coherent fills for plain
        non-lifecycle datums that are structurally satisfied but were not
        explicitly committed in this manual tick.

        This is mainly for product-vector spans where some plain datums may
        already be satisfied through prior same-span working/current fills.

        Canonicalization note:
        If fully_validate_manual_datum_fill_for_commit_v1 is supplied, this
        helper uses the same final commit gate as directly touched datums:

            required validation
            -> accepted-fill coercion through datum micros + MICRO_TYPES
            -> validator re-run on canonical values
            -> dead-JSON check

        If the helper is omitted, the fallback preserves the older behavior:
        validator-only final validation without the new explicit coercion step.
        """
        out: Dict[str, Any] = {}
        global_fills = get_form_fills(self.state)

        for raw_fid in list(span_owns or []):
            fid = str(raw_fid)
            if not fid:
                continue
            if fid in already_committed or fid in out:
                continue
            if fid in global_fills:
                continue

            datum = datums_by_id.get(fid)
            if not isinstance(datum, Mapping):
                raise FatalEngineError(
                    "manual span owns unknown datum id: "
                    f"{fid!r}"
                )

            # Lifecycle datums are committed through their own DONE path.
            if this_datum_has_a_functional_lifecycle(datum):
                continue

            candidate = datum_widget_fills.get(fid, None)

            try:
                if not datum_fill_data_meets_its_structural_micros_shell(
                    datum,
                    candidate,
                ):
                    continue

                validator = validators_by_id.get(fid)
                if validator is None:
                    validator = build_datum_validator(datum)
                    validators_by_id[fid] = validator

                if callable(
                    fully_validate_manual_datum_fill_for_commit_v1
                ):
                    validated = (
                        fully_validate_manual_datum_fill_for_commit_v1(
                            fid=fid,
                            datum=datum,
                            validator=validator,
                            partially_validated=candidate,
                        )
                    )
                else:
                    validated = validator.parse_and_validate_fill(
                        raw=candidate,
                        enforce_required_micros=True,
                        enforce_micro_lambdas=True,
                        enforce_macro_lambdas=True,
                    )

                assert_dead_json(
                    validated,
                    path=(
                        "manual_completion_validated"
                        f"[{fid}]"
                    ),
                )
                out[fid] = validated

            except DeadJSONError:
                raise
            except Exception:
                continue

        return out

    def mount_datums_needing_mounting_on_the_span(
        self,
        step: Any,
        *,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Deliver mount-time lifecycle signals before the first render of a span.

        Current behavior is opt-in:

            datum.lifecycle.mount_explode == True

        Existing datums without this setting do not run this path.
        """
        return mount_datums_needing_mounting_on_the_span(
            self,
            step,
            threaded_callbacks=threaded_callbacks,
        )

    def is_this_span_product_vector_of_datums_satisfied(
        self,
        step: Any,
    ) -> bool:
        return is_this_span_product_vector_of_datums_satisfied(
            self,
            step,
        )

    def transition_fillspan_on_incoming_filldata(
        self,
        step: Any,
        *,
        fill: Optional[Dict[str, Any]],
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        from .span_main_algos.span_transition import (
            transition_fillspan_on_incoming_filldata,
        )

        return transition_fillspan_on_incoming_filldata(
            self,
            step,
            fill=fill,
            signal=signal,
            threaded_callbacks=threaded_callbacks,
        )

    def output_fillspan_universal_ui_context(
        self,
        step: Any,
        *,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .span_main_algos.span_output_context import (
            output_fillspan_universal_ui_context,
        )

        return output_fillspan_universal_ui_context(
            self,
            step,
            threaded_callbacks=threaded_callbacks,
        )