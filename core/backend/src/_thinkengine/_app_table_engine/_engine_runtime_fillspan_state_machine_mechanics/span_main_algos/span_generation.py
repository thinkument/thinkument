from __future__ import annotations

from typing import Any, Dict, List, Mapping

from __exceptions.engine import FatalEngineError


from __multiframespecTM.api import coerce_and_validate_multiframespec

from __multiframespecTM.api import (
    build_multiframespec_scoped_datum_fill_map,
    plan_multiframespec_fillspan_steps,
)


from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KIND_MANUAL,
    KEY_DATUM_LIFECYCLE,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fills,
    get_form_prefills,
)


def expand_stepfn_multiframespec_out_to_fillspan_steps(
    self,
    step: Any,
) -> None:
    
    # current eitted multiframespec (by last stepfn executed by engine)
    multiframespec_raw = self.state.get(KEY_PENDING_FORM)

    # for error reporting 
    public_step_name = str(step.payload.get("public_step_name") or "")

    # no pending multiframespec
    if multiframespec_raw is None:
        from _thinkengine._app_table_engine.engine_class import ExecRecord
        self.exec_records[self.cursor] = ExecRecord(
            undo_patch={}
        )
        return

    # bad base type
    if not isinstance(multiframespec_raw, Mapping):
        raise FatalEngineError(
            "pending_multiframespec must be a dict when present"
        )

    # validate multiframespec which is a ergonomic contract 
    # to creating engine memory form pages 
    # of the right shape for the flow as frames of datums, spaned
    try:
        coerce_and_validate_multiframespec(multiframespec_raw)
    except Exception as e:
        raise FatalEngineError(
            f"{public_step_name}: "
            "invalid pending_multiframespec: "
            f"{type(e).__name__}: {e}"
        ) from e

    # the engine memory page (form) name 
    # no matter the number of frames, spans, datums,
    # this interaction is on one engine memory page (form)
    # like one engine memory "form" per stepfn exec
    form_id = str(
        self.state.get(KEY_PENDING_FORM_ID)
        or multiframespec_raw.get("app_form_id")
        or ""
    )


    # generate the spans from the multiframespec definition
    # where multiframespec has datums, framed, spanned, 
    # each datum spanned atomically possibly w other datums 
    # each span will only be satisfied when all authoritative datums 
    # on it are satisfied (see ./span_satisfaction.py)
    new_spans_generated = plan_multiframespec_fillspan_steps(
        multiframespec=multiframespec_raw,
        existing_fill_values_by_datum_id={},
        datum_lifecycle_state=self.state.get(KEY_DATUM_LIFECYCLE),
        form_id=form_id,
    )

    # push those in as engine new program steps 
    # injected right after the stepfn execution step 
    # that released tht mltiframespec onto the planner
    inserted_engine_steps: List[Any] = []
    insert_at = self.cursor + 1

    app_index = int(step.payload.get("app_index", -1))
    source_step_fn = ""
    source_fn_args: Dict[str, Any] = {}

    if 0 <= app_index < len(getattr(self, "steps", []) or []):
        src = self.steps[app_index]
        source_step_fn = str(src.step_fn)
        source_fn_args = dict(src.fn_args or {})

    for payload in new_spans_generated:
        pp = dict(payload)
        pp["public_step_name"] = public_step_name
        pp["source_step_fn"] = source_step_fn
        pp["source_fn_args"] = source_fn_args

        inserted_engine_steps.append(
            type(step)(
                kind=KIND_MANUAL,
                payload=pp,
            )
        )

    if inserted_engine_steps:
        self.program[insert_at:insert_at] = inserted_engine_steps

    # this marks the end of the current stepfn execution and planing 
    # around its multiframespec so ready to log it 
    from _thinkengine._app_table_engine.engine_class import ExecRecord
    self.exec_records[self.cursor] = ExecRecord(
        undo_patch={},
        inserted_steps=len(inserted_engine_steps),
    )