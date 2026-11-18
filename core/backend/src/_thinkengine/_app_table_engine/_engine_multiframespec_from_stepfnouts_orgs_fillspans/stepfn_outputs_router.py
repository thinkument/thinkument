from __future__ import annotations

"""
Step-function output routing surface.

A step function must return a Mapping. The router splits that mapping into:

1. Ordinary state patch
   - Any key not recognized as a router/sentinel key remains in
     RoutedStepFnOutputs.state_patch.
   - The patch is validated and applied to engine.state.
   - Each step-fn run clears KEY_PENDING_FORM and KEY_PENDING_FORM_ID before an
     optional new multiframespec is installed.

2. "multiframespec"
   - Optional Mapping or None; missing is normalized to None.
   - A Mapping is compiled with compile_pending_multiframespec(...).
   - On success, installs KEY_PENDING_FORM / KEY_PENDING_FORM_ID, records the
     emitted form in KEY_FORMS_EMITTED and KEY_FORMS_EMITTED_ORDER, and merges
     validated prefills into KEY_FORM_PREFILLS.
   - Duplicate form_id is fatal.

3. "session_metadata_update"
   - Optional Mapping or None.
   - Validated/coerced by coerce_and_validate_session_metadata_update(...).
   - Applied with merge_session_metadata(...), affecting future runtime policy.

4. "multiframespec_PREFILL_VALIDATE_VALUES"
   - Optional; default True.
   - Removed from ordinary state patch and passed as the multiframespec prefill
     validation directive.
   - Meaningful only when "multiframespec" is emitted.

Recognized special keys:
    "multiframespec"
    "session_metadata_update"
    "multiframespec_PREFILL_VALIDATE_VALUES"

All other keys are ordinary state patch keys.

Invalid step-fn returns:
    any non-Mapping value, e.g. None, list, str, int.

Example:
    return {
        "customer_id": "cus_123",
        "multiframespec": {...},
        "session_metadata_update": {...},
        "multiframespec_PREFILL_VALIDATE_VALUES": True,
    }
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from _thinkprogram._iomicrosTM.tiny_helpers import _json_compact_dumps
from __exceptions.engine import FormFillsContractError
from __exceptions.engine import (
    FatalEngineError,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_FORMS_EMITTED,
    KEY_FORMS_EMITTED_ORDER,
    KEY_FORM_PREFILLS,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
    RESERVED_STATE_KEYS,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    record_form_prefill_writes_v1,
    record_state_patch_writes_v1,
    register_runtime_invocation_v1,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_writing import (
    _append_list_item_patch,
    _apply_mapping_item_patch,
    _apply_patch,
    _validate_patch,
)

from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    coerce_and_validate_session_metadata_update,
    merge_session_metadata,
)


from __multiframespecTM.api import (
    coerce_and_validate_multiframespec, 
    cast__multiframespec_to_dict,
    normalize_prefill_validation_directive,
    validate_and_normalize_prefills,
    validate_prefill_addressing_only,
)

def validate_and_normalize_prefills_for_engine(
    *,
    fs_dict: Mapping[str, Any],
    prefills: Mapping[str, Any],
    directive: Any,
) -> Dict[str, Any]:
    """
    Step-output-facing helper: validate/normalize multiframespec prefills before they
    enter engine state.
    """
    fs_for_validation = coerce_and_validate_multiframespec(fs_dict)

    if fs_for_validation is None:
        raise ValueError("multiframespec validation produced None")

    validate_prefill_addressing_only(
        fs=fs_for_validation,
        prefills=dict(prefills),
    )

    directive_norm = normalize_prefill_validation_directive(directive)
    validated_new_prefills = validate_and_normalize_prefills(
        fs=fs_for_validation,
        prefills=dict(prefills),
        directive=directive_norm,
    )
    return dict(validated_new_prefills)




def compile_pending_multiframespec(
    *,
    app_public_step_name: str,
    multiframespec: Any,
    prefill_validation_directive: Any,
    datums_responsibility: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Step-output compiler for pending multiframespecs.

    This lives with step-output routing because only step-function returns emit
    new pending multiframespecs. Shared _multiframespec membrane/normalization remains
    in the multiframespec spec module.
    """
    if multiframespec is None:
        raise ValueError("multiframespec cannot be None")

    if not isinstance(multiframespec, Mapping):
        raise TypeError(
            "multiframespec must be mapping/dict-like; "
            f"got {type(multiframespec).__name__}"
        )

    fs = coerce_and_validate_multiframespec(multiframespec)
    if fs is None:
        raise ValueError("multiframespec validation produced None (unexpected)")

    fs_dict = cast__multiframespec_to_dict(
        fs,
        public_step_name=str(app_public_step_name),
        datums_responsibility=datums_responsibility,
        _multiframespec_obj=multiframespec,
    )

    form_id = str(fs_dict.get("app_form_id") or "")
    if not form_id:
        raise ValueError(
            "multiframespec normalization did not produce app_form_id"
        )

    new_prefills_raw = fs_dict.get("fills") or {}
    if not isinstance(new_prefills_raw, Mapping):
        raise TypeError(
            "_multiframespec['fills'] must be a mapping when present"
        )

    validated_new_prefills = validate_and_normalize_prefills_for_engine(
        fs_dict=fs_dict,
        prefills=dict(new_prefills_raw),
        directive=prefill_validation_directive,
    )

    return form_id, fs_dict, dict(validated_new_prefills)


######################
KNOWN_STEPFN_OUTPUT_ROUTES: Dict[str, Callable[..., None]] = {}


@dataclass(frozen=True, slots=True)
class RoutedStepFnOutputs:
    state_patch: Dict[str, Any]
    multiframespec: Any
    metadata_update: Dict[str, Any]
    prefill_validation_directive: Any


def register_step_fn_output_behavior(key: str):
    def _wrap(fn: Callable[..., None]) -> Callable[..., None]:
        KNOWN_STEPFN_OUTPUT_ROUTES[str(key)] = fn
        return fn

    return _wrap


@register_step_fn_output_behavior("session_metadata_update")
def _handle_session_metadata_update(
    *,
    routed: Dict[str, Any],
    value: Any,
) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise FatalEngineError(
            "session_metadata_update must be a mapping (dict-like)"
        )

    try:
        routed["metadata_update"] = (
            coerce_and_validate_session_metadata_update(value)
        )
    except (KeyError, ValueError, TypeError) as e:
        raise FatalEngineError(
            f"invalid session_metadata_update: {e}"
        ) from e


@register_step_fn_output_behavior("multiframespec")
def _handle_direct_compiled_framespec(
    *,
    routed: Dict[str, Any],
    value: Any,
) -> None:
    if value is None:
        routed["multiframespec"] = None
        return
    if not isinstance(value, Mapping):
        raise FatalEngineError(
            "multiframespec must be a mapping/dict or None; "
            f"got {type(value).__name__}"
        )
    routed["multiframespec"] = dict(value)
################################

def route_step_fn_outputs(
    *,
    engine: Any,
    app_step: Any,
    patch: Mapping[str, Any],
) -> RoutedStepFnOutputs:
    if not isinstance(patch, Mapping):
        raise TypeError("patch must be a mapping")

    remaining: Dict[str, Any] = dict(patch)

    routed: Dict[str, Any] = {
        "multiframespec": None,
        "metadata_update": {},
    }

    prefill_directive = remaining.pop(
        "multiframespec_PREFILL_VALIDATE_VALUES",
        True,
    )

    for key in list(remaining.keys()):
        if key in KNOWN_STEPFN_OUTPUT_ROUTES:
            val = remaining.pop(key)
            KNOWN_STEPFN_OUTPUT_ROUTES[key](routed=routed, value=val)

    multiframespec: Any = routed.get("multiframespec")

    metadata_update = routed.get("metadata_update") or {}
    if not isinstance(metadata_update, dict):
        raise FatalEngineError(
            "router produced non-dict metadata_update "
            "(internal invariant)"
        )

    return RoutedStepFnOutputs(
        state_patch=remaining,
        multiframespec=multiframespec,
        metadata_update=metadata_update,
        prefill_validation_directive=prefill_directive,
    )


class StepFnOutputRoutingMixin:
    def _normalize_stepfn_returns(
        self,
        app_step: Any,
        returns: Any,
    ) -> Dict[str, Any]:
        ret = returns

        if isinstance(ret, Mapping):
            patch = dict(ret)

            if "multiframespec" not in patch:
                patch["multiframespec"] = None
                return patch

            fs_val = patch.get("multiframespec")
            if isinstance(fs_val, Mapping):
                patch["multiframespec"] = dict(fs_val)

            return patch

        raise FatalEngineError(
            f"{app_step.step_fn} returned invalid type: "
            f"{type(ret).__name__}"
        )

    def _handle_stepfn_returns(
        self,
        app_step: Any,
        returns: Any,
    ) -> None:
        patch = self._normalize_stepfn_returns(app_step, returns)

        routed = route_step_fn_outputs(
            engine=self,
            app_step=app_step,
            patch=patch,
        )

        _validate_patch(app_step, routed.state_patch)

        if routed.metadata_update:
            self.session_metadata = merge_session_metadata(
                self.session_metadata,
                routed.metadata_update,
            )

        state_patch: Dict[str, Any] = dict(routed.state_patch)
        state_patch[KEY_PENDING_FORM] = None
        state_patch[KEY_PENDING_FORM_ID] = None

        form_write_report = self._apply_multiframespec_from_routed(
            app_step=app_step,
            multiframespec=routed.multiframespec,
            state_patch=state_patch,
            prefill_validation_directive=(
                routed.prefill_validation_directive
            ),
        )

        undo = _apply_patch(self.state, state_patch)

        if isinstance(form_write_report, Mapping):
            form_id = str(form_write_report.get("form_id") or "")
            fs_dict = form_write_report.get("multiframespec")
            prefills = dict(form_write_report.get("prefills") or {})

            if form_id and isinstance(fs_dict, Mapping):
                undo.update(
                    _apply_mapping_item_patch(
                        self.state,
                        bucket_key=KEY_FORMS_EMITTED,
                        items={form_id: dict(fs_dict)},
                    )
                )
                undo.update(
                    _append_list_item_patch(
                        self.state,
                        bucket_key=KEY_FORMS_EMITTED_ORDER,
                        value=form_id,
                    )
                )

            if prefills:
                undo.update(
                    _apply_mapping_item_patch(
                        self.state,
                        bucket_key=KEY_FORM_PREFILLS,
                        items=prefills,
                    )
                )

        seq = register_runtime_invocation_v1(
            self.state,
            public_step_name=str(app_step.public_step_name),
            step_fn=str(app_step.step_fn),
            fn_args=dict(app_step.fn_args or {}),
            invocation_kind="step_fn",
        )

        record_state_patch_writes_v1(
            self.state,
            seq=seq,
            patch=routed.state_patch,
            reserved_keys=RESERVED_STATE_KEYS,
        )

        if isinstance(form_write_report, Mapping):
            record_form_prefill_writes_v1(
                self.state,
                seq=seq,
                form_id=str(
                    form_write_report.get("form_id") or ""
                ),
                prefills=dict(
                    form_write_report.get("prefills") or {}
                ),
            )

        from _thinkengine._app_table_engine.engine_class import ExecRecord
        self.exec_records[self.cursor] = ExecRecord(
            undo_patch=undo,
            index_seq=seq,
        )

    def _apply_multiframespec_from_routed(
        self,
        *,
        app_step: Any,
        multiframespec: Any,
        state_patch: Dict[str, Any],
        prefill_validation_directive: Any,
    ) -> Dict[str, Any]:
        if multiframespec is None:
            return {}

        try:
            (
                form_id,
                fs_dict,
                validated_new_prefills,
            ) = compile_pending_multiframespec(
                app_public_step_name=str(
                    app_step.public_step_name
                ),
                multiframespec=multiframespec,
                prefill_validation_directive=(
                    prefill_validation_directive
                ),
            )
        except FormFillsContractError as e:
            raise FatalEngineError(
                f"{app_step.public_step_name}: "
                f"invalid multiframespec prefills: {e}"
            ) from e
        except Exception as e:
            raise FatalEngineError(
                f"{app_step.public_step_name}: "
                "invalid multiframespec/_multiframespec object: "
                f"{type(e).__name__}: {e}"
            ) from e

        forms_emitted = self.state.get(KEY_FORMS_EMITTED) or {}
        if isinstance(forms_emitted, Mapping) and form_id in forms_emitted:
            raise FatalEngineError(
                f"duplicate form_id emitted in session: {form_id!r}"
            )

        try:
            _json_compact_dumps(fs_dict)
        except Exception as e:
            raise FatalEngineError(
                f"_multiframespec for {form_id!r} "
                f"contains non-JSON values: {e}"
            ) from e

        clear_cache = getattr(
            self,
            "clear_manual_io_cache_v1",
            None,
        )
        if callable(clear_cache):
            clear_cache()

        state_patch[KEY_PENDING_FORM] = fs_dict
        state_patch[KEY_PENDING_FORM_ID] = form_id

        return {
            "form_id": form_id,
            "multiframespec": dict(fs_dict),
            "prefills": dict(validated_new_prefills),
        }