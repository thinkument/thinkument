# think-backend/src/thinkengine/_app_table_engine/engine/main.py

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID, uuid4

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.stepfn_outputs_router import (
    StepFnOutputRoutingMixin,
)
from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.manual_io_into_engine_forms_mixin import (
    ManualIOTapeMechanicsMixin,
)
from _thinkengine._app_table_engine._engine_runtime_fillspan_state_machine_mechanics.fillspan_generation_from_stepfn_multiframespec_mixin import (
    StepFnMultiframespecReturnedExpansionMixin,
)
from _thinkengine._app_table_engine._engine_runtime_fillspan_state_machine_mechanics.fillspan_state_machine_mixin import (
    FillspanLifecycleMixin,
)
from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    SessionEventsMixin,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG,
    get_fills_snapshot_from_app_table_state,
    get_form_fills,
    get_form_prefills,
    get_globals,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KIND_ATCOMPLETE,
    KIND_ATSTART,
    KIND_FORMEXPAND,
    KIND_MANUAL,
    KIND_STEPFN,
    KEY_FORM_FILLS,
    KEY_FORM_PREFILLS,
    KEY_FORMS_EMITTED,
    KEY_FORMS_EMITTED_ORDER,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
    KEY_RUNTIME_WRITE_INDEX,
    KEY_SESSION_ID,
    _MISSING,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    ensure_runtime_write_index_v1,
    remove_runtime_invocation_v1,
    runtime_write_index_snapshot_view_v1,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_writing import (
    _undo_patch,
)

from _thinkprogram._iomicrosTM.tiny_helpers import (
    _json_compact_dumps,
    _json_sanitize,
    _json_loads_bytes,
    _coerce_nonnegative_int_v1,
    _callable_accepts_kwarg_v1,
    assert_dead_json,
    DeadJSONError,
)
from __exceptions.engine import (
    FatalEngineError,
    ProgramEndReachedError,
    ProgramStartReachedError,
    RedoUnavailableError,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._parsing.app_table_program_parser import (
    StepSpec,
)

RUNTIME_CTX_PROFILE_SLIM_V1 = "slim"
RUNTIME_CTX_PROFILE_FULL_V1 = "full"

DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1 = 32
DEFAULT_EVENTS_SNAPSHOT_WINDOW_V1 = 32
DEFAULT_REDO_MAX_DEPTH_V1 = 64
DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1 = 200_000


def _session_metadata_runtime_ctx_profile_v1(
    meta: Mapping[str, Any],
) -> str:
    """
    Runtime ctx profile for reserved step-fn injection.

    Default is deliberately slim.

    Full ctx is allowed only by explicit metadata opt-in:

        session_metadata["runtime_session_ctx"] = {
            "profile": "full"
        }

    or legacy-friendly:

        session_metadata["include_full_runtime_session_ctx"] = True

    Full means snapshot + outputs.
    Slim means no snapshot, no get_outputs, no hydrate.
    """
    if not isinstance(meta, Mapping):
        return RUNTIME_CTX_PROFILE_SLIM_V1

    row = meta.get("runtime_session_ctx")
    if isinstance(row, Mapping):
        profile = str(dict(row).get("profile") or "").strip().lower()
        if profile == RUNTIME_CTX_PROFILE_FULL_V1:
            return RUNTIME_CTX_PROFILE_FULL_V1
        return RUNTIME_CTX_PROFILE_SLIM_V1

    if meta.get("include_full_runtime_session_ctx") is True:
        return RUNTIME_CTX_PROFILE_FULL_V1

    return RUNTIME_CTX_PROFILE_SLIM_V1


def _ctx_slim_for_runtime_stepfn_v1(
    *,
    session_id: str,
    ctx: Mapping[str, Any],
    session_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Minimal live runtime ctx injected into step functions by default.

    Hard law:
        This function must not call:
            - to_snapshot()
            - get_outputs()

    It carries only cheap public progress/state facts.
    """
    cursor = (
        dict(ctx.get("cursor") or {})
        if isinstance(ctx.get("cursor"), Mapping)
        else {}
    )
    state = (
        dict(ctx.get("state") or {})
        if isinstance(ctx.get("state"), Mapping)
        else {}
    )
    step = (
        dict(ctx.get("step") or {})
        if isinstance(ctx.get("step"), Mapping)
        else {}
    )

    out: Dict[str, Any] = {
        "kind": str(ctx.get("kind") or ""),
        "session_id": str(session_id),
        "cursor": {
            "index": cursor.get("index"),
            "total": cursor.get("total"),
        },
        "step": step,
        "datum_widgets_on_this_span": list(
            ctx.get("datum_widgets_on_this_span") or []
        ),
        "current_frame_id": ctx.get("current_frame_id"),
        "current_span": (
            ctx.get("current_span")
            or ctx.get("current_span_id")
        ),
        "form_id": ctx.get("form_id"),
        "state": {
            "pending_multiframespec": bool(
                state.get("pending_multiframespec")
            ),
            "pending_multiframespec_id": state.get(
                "pending_multiframespec_id"
            ),
            "form_prefills_keys": list(
                state.get("form_prefills_keys") or []
            ),
            "form_fills_keys": list(
                state.get("form_fills_keys") or []
            ),
            "forms_emitted_order": list(
                state.get("forms_emitted_order") or []
            ),
            "datum_lifecycle_epoch": state.get(
                "datum_lifecycle_epoch"
            ),
        },
        "runtime_write_index": {
            "present": True,
            "exposes_full_index": False,
        },
        "session_metadata": {
            "keys": sorted(
                str(k)
                for k in dict(session_metadata or {}).keys()
            ),
            "runtime_session_ctx": {
                "profile": RUNTIME_CTX_PROFILE_SLIM_V1,
            },
        },
    }

    return _json_sanitize(out)  # type: ignore[return-value]


@dataclass
class ProgramStep:
    kind: str
    payload: Dict[str, Any]


@dataclass
class ExecRecord:
    """
    Minimal reversible record for one executed runtime step.

    Distinct concepts
    -----------------
    inserted_steps:
        Number of runtime program steps inserted immediately after this step.
        Undo uses this only to remove those steps.

    index_seq:
        Runtime-write-index invocation sequence created by this execution.

    redo_action:
        Optional bounded manual replay payload. The engine may set this to
        None when the submitted fill exceeds the configured session-storage
        redo payload cap. Redo is a convenience surface, not a reason to keep
        arbitrary historical giant values forever.
    """

    undo_patch: Dict[str, Any]
    inserted_steps: int = 0
    index_seq: Optional[int] = None
    redo_action: Optional[Dict[str, Any]] = None


class AppTableProgramEngine(
    StepFnOutputRoutingMixin,
    ManualIOTapeMechanicsMixin,
    StepFnMultiframespecReturnedExpansionMixin,
    FillspanLifecycleMixin,
    SessionEventsMixin,
):
    """
    In-memory engine for an App Table session.

    Cursor semantics:
      - self.cursor points to the CURRENT step context.
      - Internal steps execute when you arrive on them.
      - MANUAL steps require a fill payload to execute.

    Forms lifecycle:
      - pending_multiframespec must exist whenever cursor is on a MANUAL step.
      - Clear pending_multiframespec only at safe non-manual boundaries, e.g.
        STEPFNSTEP, so UNDO back onto a MANUAL step still has a renderable
        context.
    """

    SNAPSHOT_VERSION = 1

    def __init__(
        self,
        *,
        steps: List[StepSpec],
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        try:
            assert_dead_json(
                initial_parameter_overrides or {},
                path="initial_parameter_overrides",
            )
            assert_dead_json(
                session_metadata or {},
                path="session_metadata",
            )
        except DeadJSONError as e:
            raise FatalEngineError(str(e)) from e

        self.session_id = session_id or str(uuid4())
        self.steps = steps
        self.session_metadata: Dict[str, Any] = dict(
            session_metadata or {}
        )

        self.state: Dict[str, Any] = dict(
            initial_parameter_overrides or {}
        )
        self.state[KEY_SESSION_ID] = self.session_id

        self.state.setdefault(KEY_PENDING_FORM, None)
        self.state.setdefault(KEY_PENDING_FORM_ID, None)
        self.state.setdefault(KEY_FORMS_EMITTED, {})
        self.state.setdefault(KEY_FORMS_EMITTED_ORDER, [])
        self.state.setdefault(KEY_FORM_PREFILLS, {})
        self.state.setdefault(KEY_FORM_FILLS, {})
        ensure_runtime_write_index_v1(self.state)

        self.program: List[ProgramStep] = [
            ProgramStep(
                kind=KIND_ATSTART,
                payload={"at": 0},
            )
        ]
        for i, s in enumerate(self.steps):
            self.program.append(
                ProgramStep(
                    kind=KIND_STEPFN,
                    payload={
                        "app_index": i,
                        "public_step_name": s.public_step_name,
                        "step_fn": s.step_fn,
                        "fn_args": dict(s.fn_args),
                    },
                )
            )
            self.program.append(
                ProgramStep(
                    kind=KIND_FORMEXPAND,
                    payload={
                        "app_index": i,
                        "public_step_name": s.public_step_name,
                    },
                )
            )

        self.program.append(
            ProgramStep(
                kind=KIND_ATCOMPLETE,
                payload={"at": len(self.program)},
            )
        )

        self.cursor: int = 0
        self.exec_records: Dict[int, ExecRecord] = {}
        self.last_error: Optional[Dict[str, str]] = None

        self.init_manual_io_runtime_state_v1()
        self._init_session_events_runtime_state_v1()

        self._redo_stack_v1: List[Dict[str, Any]] = []
        self._is_replaying_redo_v1 = False

    def _snapshot_state_v1(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        for k, v in self.state.items():
            ks = str(k)
            if ks == KEY_RUNTIME_WRITE_INDEX:
                out[ks] = runtime_write_index_snapshot_view_v1(v)
            else:
                out[ks] = v

        policy = self._session_storage_policy_v1()
        window = int(
            policy.get(
                "forms_emitted_snapshot_window",
                32,
            )
            or 0
        )

        forms = out.get(KEY_FORMS_EMITTED)
        order = out.get(KEY_FORMS_EMITTED_ORDER)
        pending_id = str(out.get(KEY_PENDING_FORM_ID) or "")

        if isinstance(forms, Mapping):
            keep_ids: list[str] = []

            if isinstance(order, list) and window > 0:
                keep_ids.extend(
                    str(x)
                    for x in order[-window:]
                )

            if pending_id:
                keep_ids.append(pending_id)

            seen: set[str] = set()
            compact_forms: Dict[str, Any] = {}
            compact_order: list[str] = []
            for fid in keep_ids:
                if fid in seen:
                    continue
                seen.add(fid)
                if fid in forms:
                    compact_forms[fid] = forms[fid]
                    compact_order.append(fid)

            out[KEY_FORMS_EMITTED] = compact_forms
            out[KEY_FORMS_EMITTED_ORDER] = compact_order

            pending_multiframespec = out.get(KEY_PENDING_FORM)
            if (
                pending_id
                and pending_id in compact_forms
                and pending_multiframespec
                == compact_forms[pending_id]
            ):
                out[KEY_PENDING_FORM] = None

        return out

    @staticmethod
    def _serialize_undo_patch_v1(
        patch: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Encode ``_MISSING`` without allowing the private sentinel to cross the
        dead-JSON snapshot membrane.
        """
        out: List[Dict[str, Any]] = []
        for key, value in dict(patch or {}).items():
            if value is _MISSING:
                out.append(
                    {
                        "k": str(key),
                        "missing": True,
                    }
                )
            else:
                out.append(
                    {
                        "k": str(key),
                        "missing": False,
                        "v": value,
                    }
                )
        return out

    def to_snapshot(self) -> Dict[str, Any]:
        self._ensure_session_events_runtime_state_v1()
        snap = {
            "v": self.SNAPSHOT_VERSION,
            "session_id": self.session_id,
            "steps": [
                {
                    "public_step_name": s.public_step_name,
                    "step_fn": s.step_fn,
                    "fn_args": dict(s.fn_args),
                }
                for s in self.steps
            ],
            "state": self._snapshot_state_v1(),
            "program": [
                {
                    "kind": ps.kind,
                    "payload": dict(ps.payload),
                }
                for ps in self.program
            ],
            "cursor": int(self.cursor),
            "exec_records": {
                str(idx): {
                    "undo_patch": self._serialize_undo_patch_v1(
                        rec.undo_patch
                    ),
                    "inserted_steps": int(rec.inserted_steps),
                    "index_seq": rec.index_seq,
                    "redo_action": (
                        dict(rec.redo_action)
                        if isinstance(
                            rec.redo_action,
                            Mapping,
                        )
                        else None
                    ),
                }
                for idx, rec in self.exec_records.items()
            },
            "last_error": (
                dict(self.last_error)
                if isinstance(self.last_error, dict)
                else None
            ),
            "session_metadata": dict(self.session_metadata),
            "redo_stack_v1": list(
                getattr(
                    self,
                    "_redo_stack_v1",
                    [],
                )
                or []
            ),
            "session_events_v1": [
                dict(event)
                for event in self.peek_events_from_session()
            ],
            "next_session_event_seq_v1": int(
                self._next_session_event_seq_v1
            ),
        }

        try:
            assert_dead_json(
                snap,
                path="engine_snapshot",
            )
        except DeadJSONError as e:
            raise FatalEngineError(
                "engine snapshot contains non-JSON values: "
                f"{e}"
            ) from e

        return snap

    @classmethod
    def from_snapshot(
        cls,
        snap: Mapping[str, Any],
    ) -> "AppTableProgramEngine":
        if not isinstance(snap, Mapping):
            raise TypeError(
                "engine snapshot must be a mapping"
            )
        if int(snap.get("v", 0)) != cls.SNAPSHOT_VERSION:
            raise ValueError(
                "unsupported engine snapshot version: "
                f"{snap.get('v')}"
            )

        steps_raw = snap.get("steps") or []
        steps: List[StepSpec] = []
        for i, obj in enumerate(
            steps_raw
            if isinstance(steps_raw, list)
            else []
        ):
            if not isinstance(obj, Mapping):
                raise TypeError(
                    f"snapshot.steps[{i}] must be mapping"
                )
            steps.append(
                StepSpec(
                    public_step_name=str(
                        obj.get(
                            "public_step_name",
                            "",
                        )
                    ),
                    step_fn=str(
                        obj.get(
                            "step_fn",
                            "",
                        )
                    ),
                    fn_args=dict(
                        obj.get("fn_args") or {}
                    ),
                )
            )

        eng = cls.__new__(cls)

        eng.session_id = str(
            snap.get("session_id")
            or str(uuid4())
        )
        eng.steps = steps

        eng.session_metadata = dict(
            snap.get("session_metadata") or {}
        )
        eng.state = dict(
            snap.get("state") or {}
        )
        eng.state.setdefault(
            KEY_SESSION_ID,
            eng.session_id,
        )
        eng.state.setdefault(
            KEY_PENDING_FORM,
            None,
        )
        eng.state.setdefault(
            KEY_PENDING_FORM_ID,
            None,
        )
        eng.state.setdefault(
            KEY_FORMS_EMITTED,
            {},
        )
        eng.state.setdefault(
            KEY_FORMS_EMITTED_ORDER,
            [],
        )
        eng.state.setdefault(
            KEY_FORM_PREFILLS,
            {},
        )
        eng.state.setdefault(
            KEY_FORM_FILLS,
            {},
        )
        ensure_runtime_write_index_v1(
            eng.state
        )

        if (
            eng.state.get(KEY_PENDING_FORM) is None
            and eng.state.get(KEY_PENDING_FORM_ID)
            is not None
        ):
            forms = eng.state.get(KEY_FORMS_EMITTED)
            fid = str(
                eng.state.get(KEY_PENDING_FORM_ID)
                or ""
            )
            if (
                isinstance(forms, Mapping)
                and fid in forms
            ):
                restored = forms.get(fid)
                if isinstance(restored, Mapping):
                    eng.state[
                        KEY_PENDING_FORM
                    ] = dict(restored)

        program_raw = snap.get("program") or []
        eng.program = []
        for i, obj in enumerate(
            program_raw
            if isinstance(program_raw, list)
            else []
        ):
            if not isinstance(obj, Mapping):
                raise TypeError(
                    f"snapshot.program[{i}] must be mapping"
                )
            eng.program.append(
                ProgramStep(
                    kind=str(obj.get("kind")),
                    payload=dict(
                        obj.get("payload") or {}
                    ),
                )
            )

        eng.cursor = int(
            snap.get("cursor", 0)
        )

        def _de_undo_patch(
            items: Any,
        ) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for it in (
                items
                if isinstance(items, list)
                else []
            ):
                if not isinstance(it, Mapping):
                    continue
                k = str(it.get("k"))
                missing = bool(
                    it.get("missing", False)
                )
                out[k] = (
                    _MISSING
                    if missing
                    else it.get("v")
                )
            return out

        eng.exec_records = {}
        er_raw = snap.get("exec_records") or {}
        if isinstance(er_raw, Mapping):
            for k, v in er_raw.items():
                try:
                    idx = int(k)
                except Exception:
                    continue

                if not isinstance(v, Mapping):
                    continue

                undo_patch = _de_undo_patch(
                    v.get("undo_patch")
                )

                eng.exec_records[idx] = ExecRecord(
                    undo_patch=undo_patch,
                    inserted_steps=int(
                        v.get(
                            "inserted_steps",
                            0,
                        )
                    ),
                    index_seq=(
                        int(v["index_seq"])
                        if v.get("index_seq")
                        is not None
                        else None
                    ),
                    redo_action=(
                        dict(v.get("redo_action"))
                        if isinstance(
                            v.get("redo_action"),
                            Mapping,
                        )
                        else None
                    ),
                )

        le = snap.get("last_error", None)
        eng.last_error = (
            dict(le)
            if isinstance(le, Mapping)
            else None
        )

        eng.init_manual_io_runtime_state_v1()

        events_raw = snap.get("session_events_v1") or []
        eng._session_events_v1 = [
            dict(event)
            for event in events_raw
            if isinstance(event, Mapping)
        ]
        try:
            eng._next_session_event_seq_v1 = int(
                snap.get(
                    "next_session_event_seq_v1",
                    1,
                )
            )
        except Exception:
            eng._next_session_event_seq_v1 = 1
        eng._ensure_session_events_runtime_state_v1()

        redo_raw = snap.get(
            "redo_stack_v1"
        ) or []
        eng._redo_stack_v1 = [
            dict(x)
            for x in redo_raw
            if isinstance(x, Mapping)
        ]
        eng._is_replaying_redo_v1 = False

        return eng

    def to_bytes(self) -> bytes:
        return _json_compact_dumps(
            self.to_snapshot()
        )

    @classmethod
    def from_bytes(
        cls,
        blob: bytes,
    ) -> "AppTableProgramEngine":
        if blob is None:
            raise ValueError(
                "cannot load engine from None blob"
            )
        snap = _json_loads_bytes(
            blob
            if isinstance(
                blob,
                (bytes, bytearray),
            )
            else bytes(blob)
        )
        return cls.from_snapshot(snap)

    def _redo_policy_v1(
        self,
    ) -> Dict[str, Any]:
        meta = (
            self.session_metadata
            if isinstance(
                self.session_metadata,
                Mapping,
            )
            else {}
        )
        raw = meta.get("redo")
        row = (
            dict(raw or {})
            if isinstance(raw, Mapping)
            else {}
        )

        storage = meta.get("session_storage")
        storage_row = (
            dict(storage or {})
            if isinstance(storage, Mapping)
            else {}
        )

        max_depth = _coerce_nonnegative_int_v1(
            row.get(
                "max_depth",
                storage_row.get(
                    "redo_max_depth",
                    DEFAULT_REDO_MAX_DEPTH_V1,
                ),
            ),
            DEFAULT_REDO_MAX_DEPTH_V1,
        )

        return {
            "max_depth": max(
                0,
                max_depth,
            )
        }

    def _session_storage_policy_v1(
        self,
    ) -> Dict[str, Any]:
        meta = (
            self.session_metadata
            if isinstance(
                self.session_metadata,
                Mapping,
            )
            else {}
        )
        raw = meta.get("session_storage")
        row = (
            dict(raw or {})
            if isinstance(raw, Mapping)
            else {}
        )

        return {
            "events_snapshot_window": (
                _coerce_nonnegative_int_v1(
                    row.get(
                        "events_snapshot_window"
                    ),
                    DEFAULT_EVENTS_SNAPSHOT_WINDOW_V1,
                )
            ),
            "forms_emitted_snapshot_window": (
                _coerce_nonnegative_int_v1(
                    row.get(
                        "forms_emitted_snapshot_window"
                    ),
                    DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1,
                )
            ),
            "redo_max_depth": (
                _coerce_nonnegative_int_v1(
                    row.get(
                        "redo_max_depth"
                    ),
                    DEFAULT_REDO_MAX_DEPTH_V1,
                )
            ),
            "redo_action_max_payload_chars": (
                _coerce_nonnegative_int_v1(
                    row.get(
                        "redo_action_max_payload_chars"
                    ),
                    DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1,
                )
            ),
        }

    def _bounded_redo_action_v1(
        self,
        action: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Keep redo useful without letting it become an unbounded historical
        payload log.

        This does not compress. It either keeps a JSON action as-is or drops it
        when it exceeds the declared storage policy.
        """
        if not isinstance(action, Mapping):
            return None

        cleaned = dict(action)
        try:
            assert_dead_json(
                cleaned,
                path="redo_action",
            )
            size = len(
                _json_compact_dumps(cleaned)
            )
        except Exception:
            return None

        cap = int(
            self._session_storage_policy_v1().get(
                "redo_action_max_payload_chars",
                DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1,
            )
            or 0
        )
        if cap > 0 and size > cap:
            return None

        return cleaned

    def _clear_redo_stack_v1(
        self,
    ) -> None:
        try:
            self._redo_stack_v1.clear()
        except Exception:
            self._redo_stack_v1 = []

    def _manual_record_is_auto_skip_v1(
        self,
        idx: int,
    ) -> bool:
        """
        True when a MANUAL program step was skipped because it was already
        satisfied before entry.

        These records are internal no-op progress markers. They must not become
        public undo/redo surfaces.
        """
        rec = self.exec_records.get(
            int(idx)
        )
        if rec is None:
            return False

        return (
            not bool(rec.undo_patch)
            and rec.inserted_steps == 0
            and rec.index_seq is None
            and rec.redo_action is None
        )

    def _advance_over_satisfied_manual_steps_v1(
        self,
    ) -> None:
        """
        Dynamically skip stale MANUAL steps.
        """
        checker = getattr(
            self,
            "is_this_span_product_vector_of_datums_satisfied",
            None,
        )
        if not callable(checker):
            return

        while 0 <= self.cursor < len(self.program):
            step = self._get_current_step()
            if step.kind != KIND_MANUAL:
                return

            try:
                satisfied = bool(
                    checker(step)
                )
            except Exception:
                return

            if not satisfied:
                return

            self.exec_records.setdefault(
                self.cursor,
                ExecRecord(
                    undo_patch={}
                ),
            )

            if self.cursor >= len(self.program) - 1:
                return

            self.cursor += 1

            next_step = self._get_current_step()
            if next_step.kind != KIND_MANUAL:
                if (
                    self.cursor
                    not in self.exec_records
                ):
                    self._execute_step(
                        next_step,
                        fill=None,
                    )
                return

    def _push_redo_action_v1(
        self,
        action: Mapping[str, Any],
    ) -> None:
        if not isinstance(action, Mapping):
            return

        bounded = self._bounded_redo_action_v1(
            action
        )
        if bounded is None:
            return

        max_depth = int(
            self._redo_policy_v1().get(
                "max_depth",
                64,
            )
            or 0
        )
        if max_depth <= 0:
            return

        stack = getattr(
            self,
            "_redo_stack_v1",
            None,
        )
        if not isinstance(stack, list):
            stack = []
            self._redo_stack_v1 = stack

        stack.append(
            dict(bounded)
        )
        if len(stack) > max_depth:
            del stack[
                0 : len(stack) - max_depth
            ]

    def _globals_view(
        self,
    ) -> Dict[str, Any]:
        return get_globals(
            self.state
        )

    def _ctx_base(
        self,
        kind: str,
    ) -> Dict[str, Any]:
        ctx = {
            "session_id": self.session_id,
            "kind": kind,
            "cursor": {
                "index": self.cursor,
                "total": len(self.program),
            },
            "session_metadata": dict(
                self.session_metadata
            ),
            "last_error": self.last_error,
            "globals": self._globals_view(),
        }

        return ctx

    def _nonmanual_ctx_state_summary_v1(
        self,
    ) -> Dict[str, Any]:
        """
        Cheap state summary for non-manual ctx.
        """
        policy = self.manual_io_policy_v1()

        include_global_fill_keys = bool(
            policy.get(
                "include_global_fill_keys_in_ctx",
                False,
            )
        )
        include_forms_emitted_order = bool(
            policy.get(
                "include_forms_emitted_order_in_ctx",
                True,
            )
        )

        prefills = get_form_prefills(
            self.state
        )
        fills = get_form_fills(
            self.state
        )

        out: Dict[str, Any] = {
            "pending_multiframespec": bool(
                self.state.get(
                    KEY_PENDING_FORM
                )
            ),
            "pending_multiframespec_id": (
                self.state.get(
                    KEY_PENDING_FORM_ID
                )
            ),
            "form_prefills_count": len(
                prefills
            ),
            "form_fills_count": len(
                fills
            ),
            "forms_emitted_count": len(
                self.state.get(
                    KEY_FORMS_EMITTED_ORDER
                )
                or []
            ),
        }

        if include_global_fill_keys:
            out["form_prefills_keys"] = sorted(
                str(k)
                for k in prefills.keys()
            )
            out["form_fills_keys"] = sorted(
                str(k)
                for k in fills.keys()
            )
        else:
            out["form_prefills_keys"] = []
            out["form_fills_keys"] = []

        if include_forms_emitted_order:
            out["forms_emitted_order"] = list(
                self.state.get(
                    KEY_FORMS_EMITTED_ORDER
                )
                or []
            )
        else:
            out["forms_emitted_order"] = []

        return out

    def _get_current_step(
        self,
    ) -> ProgramStep:
        try:
            return self.program[
                self.cursor
            ]
        except Exception as e:
            raise FatalEngineError(
                f"cursor out of range: {self.cursor}"
            ) from e

    def _undo_return_context_v1(
        self,
        *,
        render_context: bool,
    ) -> Dict[str, Any]:
        if render_context:
            return self.get_context()

        try:
            step = self._get_current_step()
            kind = step.kind
        except Exception:
            kind = ""

        return {
            "session_id": self.session_id,
            "kind": kind,
            "cursor": {
                "index": self.cursor,
                "total": len(self.program),
            },
            "session_metadata": dict(
                self.session_metadata
            ),
            "last_error": self.last_error,
        }

    def _refresh_current_manual_cache_after_local_undo_v1(
        self,
        *,
        rec: Optional[ExecRecord] = None,
    ) -> None:
        """
        Repair only cache-held values touched by one local manual undo.
        """
        try:
            step = self._get_current_step()
        except Exception:
            return

        if step.kind != KIND_MANUAL:
            return

        multiframespec = self.state.get(
            KEY_PENDING_FORM
        )
        if not isinstance(
            multiframespec,
            Mapping,
        ):
            return

        frame_id = str(
            step.payload.get("frame_id")
            or ""
        ).strip()
        span_id = str(
            step.payload.get("span_id")
            or ""
        ).strip()
        form_id = str(
            self.state.get(
                KEY_PENDING_FORM_ID
            )
            or multiframespec.get(
                "app_form_id"
            )
            or ""
        ).strip()

        if (
            not frame_id
            or not span_id
            or not form_id
        ):
            return

        cache_store = getattr(
            self,
            "_manual_io_cache_v1",
            None,
        )
        if not isinstance(
            cache_store,
            dict,
        ):
            return

        cache_key = self.manual_io_cache_key_v1(
            form_id=form_id,
            multiframespec=multiframespec,
        )
        cache = cache_store.get(
            cache_key
        )
        if not isinstance(
            cache,
            Mapping,
        ):
            return

        base = cache.get(
            "base_ui_ctx"
        )
        if not isinstance(
            base,
            dict,
        ):
            self.clear_manual_io_cache_v1()
            return

        datum_widget_fills = base.get(
            "datum_widget_fills"
        )
        if not isinstance(
            datum_widget_fills,
            dict,
        ):
            datum_widget_fills = {}
            base[
                "datum_widget_fills"
            ] = datum_widget_fills

        touched: set[str] = set()

        if (
            rec is not None
            and isinstance(
                rec.undo_patch,
                Mapping,
            )
        ):
            fill_undo = rec.undo_patch.get(
                KEY_FORM_FILLS
            )
            if isinstance(
                fill_undo,
                Mapping,
            ):
                if (
                    str(
                        fill_undo.get(
                            "kind"
                        )
                        or ""
                    )
                    == "__app_table_mapping_items_undo_v1__"
                ):
                    for row in list(
                        fill_undo.get(
                            "items"
                        )
                        or []
                    ):
                        if not isinstance(
                            row,
                            Mapping,
                        ):
                            continue

                        datum_id = str(
                            row.get("k")
                            or ""
                        ).strip()
                        if datum_id:
                            touched.add(
                                datum_id
                            )

            lifecycle_undo = rec.undo_patch.get(
                "__datum_lifecycle_done_undo_v1__"
            )
            if isinstance(
                lifecycle_undo,
                Mapping,
            ):
                datum_rows = lifecycle_undo.get(
                    "datum_rows"
                )
                if isinstance(
                    datum_rows,
                    Mapping,
                ):
                    touched.update(
                        str(datum_id)
                        for datum_id
                        in datum_rows.keys()
                        if str(datum_id)
                    )

        if not touched:
            touched.update(
                str(x)
                for x in list(
                    step.payload.get(
                        "span_owns"
                    )
                    or []
                )
                if str(x or "").strip()
            )

            if not touched:
                touched.update(
                    str(x)
                    for x in list(
                        step.payload.get(
                            "datum_widgets_on_this_span"
                        )
                        or []
                    )
                    if str(x or "").strip()
                )

        global_fills = self.state.get(
            KEY_FORM_FILLS
        )
        if not isinstance(
            global_fills,
            Mapping,
        ):
            global_fills = {}

        global_prefills = self.state.get(
            KEY_FORM_PREFILLS
        )
        if not isinstance(
            global_prefills,
            Mapping,
        ):
            global_prefills = {}

        local_prefills = multiframespec.get(
            "fills"
        )
        if not isinstance(
            local_prefills,
            Mapping,
        ):
            local_prefills = {}

        overlays = (
            self.manual_get_latest_engine_form_page_data_read(
                form_id=form_id,
                frame_id=frame_id,
                span_id=span_id,
            )
        )

        for datum_id in touched:
            if datum_id in overlays:
                datum_widget_fills[
                    datum_id
                ] = overlays[datum_id]
            elif datum_id in global_fills:
                datum_widget_fills[
                    datum_id
                ] = global_fills[datum_id]
            elif datum_id in global_prefills:
                datum_widget_fills[
                    datum_id
                ] = global_prefills[datum_id]
            elif datum_id in local_prefills:
                datum_widget_fills[
                    datum_id
                ] = local_prefills[datum_id]
            else:
                datum_widget_fills.pop(
                    datum_id,
                    None,
                )

    def get_context(
        self,
        *,
        threaded_callbacks: Optional[
            Mapping[str, Any]
        ] = None,
    ) -> Dict[str, Any]:
        """
        Return the current public engine context.

        Building a MANUAL context may mount lifecycle datums before the
        universal UI context is assembled. When this context is produced as
        part of a live controller dispatch, the active callback bag must be
        forwarded so mount-time events remain in that dispatch's event
        timeline.

        Ordinary read-only callers omit ``threaded_callbacks`` and retain the
        historical behavior.
        """
        step = self._get_current_step()
        kind = step.kind

        if kind == KIND_MANUAL:
            return (
                self.output_fillspan_universal_ui_context(
                    step,
                    threaded_callbacks=threaded_callbacks,
                )
            )

        ctx = self._ctx_base(kind)
        ctx["step"] = dict(
            step.payload
        )
        ctx["state"] = (
            self._nonmanual_ctx_state_summary_v1()
        )
        return ctx

    def step(
        self,
        fill: Optional[
            Dict[str, Any]
        ] = None,
        signal: Optional[
            Dict[str, Any]
        ] = None,
        threaded_callbacks: Optional[
            Mapping[str, Any]
        ] = None,
    ) -> Dict[str, Any]:
        cur = self._get_current_step()

        if cur.kind == KIND_ATCOMPLETE:
            raise ProgramEndReachedError(
                "program already completed"
            )

        if cur.kind == KIND_MANUAL:
            self.last_error = None
            ok = (
                self.transition_fillspan_on_incoming_filldata(
                    cur,
                    fill=fill,
                    signal=signal,
                    threaded_callbacks=threaded_callbacks,
                )
            )
            if not ok:
                return self.get_context(
                    threaded_callbacks=threaded_callbacks,
                )

            if (
                fill is not None
                and not bool(
                    getattr(
                        self,
                        "_is_replaying_redo_v1",
                        False,
                    )
                )
            ):
                self._clear_redo_stack_v1()

            if (
                self.cursor
                >= len(self.program) - 1
            ):
                raise ProgramEndReachedError(
                    "program already completed"
                )

            self.cursor += 1
            self._advance_over_satisfied_manual_steps_v1()

            nxt = self._get_current_step()
            if (
                nxt.kind != KIND_MANUAL
                and self.cursor
                not in self.exec_records
            ):
                self._execute_step(
                    nxt,
                    fill=None,
                )

            return self.get_context(
                threaded_callbacks=threaded_callbacks,
            )

        if (
            self.cursor
            >= len(self.program) - 1
        ):
            raise ProgramEndReachedError(
                "program already completed"
            )

        self.last_error = None
        self.cursor += 1
        step = self._get_current_step()

        if step.kind != KIND_MANUAL:
            self._execute_step(
                step,
                fill=None,
            )

        self._advance_over_satisfied_manual_steps_v1()
        return self.get_context(
            threaded_callbacks=threaded_callbacks,
        )

    def redo(
        self,
    ) -> Dict[str, Any]:
        stack = getattr(
            self,
            "_redo_stack_v1",
            None,
        )
        if (
            not isinstance(stack, list)
            or not stack
        ):
            raise RedoUnavailableError(
                "no redoable manual action"
            )

        action = dict(
            stack[-1]
        )
        kind = str(
            action.get("kind")
            or ""
        )
        if kind != "manual_step":
            raise RedoUnavailableError(
                "unsupported redo action kind: "
                f"{kind!r}"
            )

        fill = action.get("fill")
        if not isinstance(
            fill,
            Mapping,
        ):
            raise RedoUnavailableError(
                "redo manual action has no fill mapping"
            )

        signal = action.get("signal")
        if (
            signal is not None
            and not isinstance(
                signal,
                Mapping,
            )
        ):
            raise RedoUnavailableError(
                "redo manual action signal is not a mapping"
            )

        self._is_replaying_redo_v1 = True
        try:
            ctx = self.step(
                fill=dict(fill),
                signal=(
                    dict(signal)
                    if isinstance(
                        signal,
                        Mapping,
                    )
                    else None
                ),
                threaded_callbacks=None,
            )
        finally:
            self._is_replaying_redo_v1 = False

        stack.pop()
        return ctx

    def undo(
        self,
        *,
        render_context: bool = True,
    ) -> Dict[str, Any]:
        if self.cursor <= 0:
            raise ProgramStartReachedError(
                "already at start"
            )

        self.last_error = None

        cur_idx = int(
            self.cursor
        )
        cur_step = self._get_current_step()
        cur_rec = self.exec_records.get(
            cur_idx
        )

        if cur_rec is not None:
            local_manual_undo = (
                cur_step.kind
                == KIND_MANUAL
            )

            self._undo_step_at(
                cur_idx,
                clear_manual_cache=(
                    not local_manual_undo
                ),
            )

            if local_manual_undo:
                self._refresh_current_manual_cache_after_local_undo_v1(
                    rec=cur_rec,
                )

                return self._undo_return_context_v1(
                    render_context=render_context
                )

            self.cursor -= 1

            while self.cursor > 0:
                prev = self._get_current_step()
                if prev.kind != KIND_MANUAL:
                    break

                if not self._manual_record_is_auto_skip_v1(
                    self.cursor
                ):
                    break

                self._undo_step_at(
                    self.cursor,
                    clear_manual_cache=False,
                )
                self.cursor -= 1

            self.clear_manual_io_cache_v1()
            return self._undo_return_context_v1(
                render_context=render_context
            )

        self.cursor -= 1

        try:
            prev_step = (
                self._get_current_step()
            )
        except Exception:
            self.clear_manual_io_cache_v1()
            return self._undo_return_context_v1(
                render_context=render_context
            )

        if (
            prev_step.kind == KIND_MANUAL
            and self.cursor
            in self.exec_records
        ):
            prev_rec = self.exec_records.get(
                self.cursor
            )

            self._undo_step_at(
                self.cursor,
            )

            self._refresh_current_manual_cache_after_local_undo_v1(
                rec=prev_rec,
            )
        else:
            self.clear_manual_io_cache_v1()

        return self._undo_return_context_v1(
            render_context=render_context
        )

    def _execute_step(
        self,
        step: ProgramStep,
        *,
        fill: Optional[
            Dict[str, Any]
        ],
    ) -> None:
        self.last_error = None

        if step.kind == KIND_ATSTART:
            self.exec_records[
                self.cursor
            ] = ExecRecord(
                undo_patch={}
            )
            return

        if step.kind == KIND_STEPFN:
            self._exec_stepfn(step)
            return

        if step.kind == KIND_FORMEXPAND:
            self.expand_stepfn_multiframespec_out_to_fillspan_steps(
                step
            )
            return

        if step.kind == KIND_MANUAL:
            self.transition_fillspan_on_incoming_filldata(
                step,
                fill=fill,
                signal=None,
            )
            return

        if step.kind == KIND_ATCOMPLETE:
            self.exec_records[
                self.cursor
            ] = ExecRecord(
                undo_patch={}
            )
            return

        raise FatalEngineError(
            "unknown program step kind: "
            f"{step.kind}"
        )

    def _ctx(
        self,
        ctx: Mapping[str, Any],
    ) -> Dict[str, Any]:
        out = dict(ctx or {})
        out.setdefault(
            "session_metadata",
            {},
        )

        if isinstance(
            out["session_metadata"],
            Mapping,
        ):
            sm = dict(
                out["session_metadata"]
            )
            sm["runtime_session_ctx"] = {
                "profile": (
                    RUNTIME_CTX_PROFILE_FULL_V1
                )
            }
            out["session_metadata"] = sm

        return _json_sanitize(
            out
        )  # type: ignore[return-value]

    def _runtime_session_ctx_for_stepfn_v1(
        self,
        *,
        ctx: Mapping[str, Any],
    ) -> Dict[str, Any]:
        profile = (
            _session_metadata_runtime_ctx_profile_v1(
                self.session_metadata
            )
        )
        if (
            profile
            == RUNTIME_CTX_PROFILE_FULL_V1
        ):
            return self._ctx(ctx)

        return _ctx_slim_for_runtime_stepfn_v1(
            session_id=self.session_id,
            ctx=ctx,
            session_metadata=(
                self.session_metadata
            ),
        )

    def _undo_step_at(
        self,
        idx: int,
        *,
        clear_manual_cache: bool = True,
    ) -> None:
        rec = self.exec_records.get(idx)
        if rec is None:
            return

        remove_runtime_invocation_v1(
            self.state,
            seq=rec.index_seq,
        )

        if isinstance(
            rec.redo_action,
            Mapping,
        ):
            self._push_redo_action_v1(
                rec.redo_action
            )

        if rec.inserted_steps:
            start = idx + 1
            end = (
                start
                + rec.inserted_steps
            )
            if end <= len(self.program):
                del self.program[
                    start:end
                ]

        lifecycle_undo = None
        undo_patch = dict(
            rec.undo_patch
            or {}
        )

        if (
            str(
                undo_patch.get("kind")
                or ""
            )
            == "__datum_lifecycle_incremental_undo_v1__"
        ):
            lifecycle_undo = dict(
                undo_patch
            )
            undo_patch = {}

        if isinstance(
            undo_patch.get(
                "__datum_lifecycle_done_undo_v1__"
            ),
            Mapping,
        ):
            lifecycle_undo = undo_patch.pop(
                "__datum_lifecycle_done_undo_v1__"
            )

        if isinstance(
            undo_patch.get(
                "__datum_lifecycle_mount_undo_v1__"
            ),
            Mapping,
        ):
            lifecycle_undo = undo_patch.pop(
                "__datum_lifecycle_mount_undo_v1__"
            )

        if undo_patch:
            _undo_patch(
                self.state,
                undo_patch,
            )

        if isinstance(
            lifecycle_undo,
            Mapping,
        ):
            self.undo_lifecycle_patch_v1(
                lifecycle_undo,
            )

        self.exec_records.pop(
            idx,
            None,
        )

        if clear_manual_cache:
            self.clear_manual_io_cache_v1()

    def _exec_stepfn(
        self,
        step: ProgramStep,
    ) -> None:
        app_index = int(
            step.payload[
                "app_index"
            ]
        )
        app_step = self.steps[
            app_index
        ]

        spec = StepFnregistry.get(
            app_step.step_fn
        )
        fn = spec.fn

        try:
            fn_args = dict(
                app_step.fn_args
            )
            if _callable_accepts_kwarg_v1(
                fn,
                APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG,
            ):
                runtime_session_ctx = (
                    self._runtime_session_ctx_for_stepfn_v1(
                        ctx=self.get_context()
                    )
                )
                fn_args[
                    APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG
                ] = runtime_session_ctx

            ret = fn(
                dict(self.state),
                **fn_args,
            )
        except Exception as e:
            raise FatalEngineError(
                f"step fn {app_step.step_fn} raised: "
                f"{type(e).__name__}: {e}"
            ) from e

        self._handle_stepfn_returns(
            app_step=app_step,
            returns=ret,
        )

    def get_outputs(
        self,
    ) -> Dict[str, Any]:
        raw_merged_fills = dict(
            get_fills_snapshot_from_app_table_state(
                self.state
            )
        )

        semantic_merged_fills = dict(
            raw_merged_fills
        )

        out: Dict[str, Any] = {
            "globals": get_globals(
                self.state
            ),
            "form_prefills": dict(
                get_form_prefills(
                    self.state
                )
            ),
            "form_fills": dict(
                get_form_fills(
                    self.state
                )
            ),
            "merged_fills": dict(
                semantic_merged_fills
            ),
            "raw_merged_fills": dict(
                raw_merged_fills
            ),
        }
        return out

    def session_uuid(
        self,
    ) -> UUID:
        return UUID(
            str(self.session_id)
        )