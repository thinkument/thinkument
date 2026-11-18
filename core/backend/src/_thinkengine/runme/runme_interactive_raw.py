# think-backend/src/thinkengine/_app_table_engine/useme/runme.py

from __future__ import annotations

"""
UI-agnostic App Table session API implementation.

This module owns both the reusable session contract and the concrete App Table
implementation:

- the session-creation return type;
- the abstract lifecycle and execution contract;
- convenience aliases over that contract;
- generic lowered-program session-surface merging;
- generic program-provenance metadata attachment;
- App Table manifest parsing and validation;
- App Table engine construction;
- durable-boundary stepping, undo, and redo;
- context and output access;
- snapshot import and export;
- repository persistence;
- the process-local concrete API singleton;
- roleless module-level convenience functions.

It does not understand viewers, roles, authorization, role mismatch, or HTML.
Feature-specific configuration travels through the generic dead-JSON
`session_metadata` envelope.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from uuid import UUID

from _thinkprogram._iomicrosTM.tiny_helpers import (
    _deep_merge_mapping_values,
    _mapping_from_any,
)
from _thinkengine._parsing.app_table_program_parser import (
    DeadJSONError,
    assert_dead_json,
)
from _thinkengine._app_table_engine.engine_class import (
    AppTableProgramEngine,
)
from _thinkengine.runme._runme_progress_contract import (
    PROGRAM_AUTO_ADVANCE_KINDS_V1,
    PROGRAM_DURABLE_STOP_KINDS,
    PROGRAM_UNDO_DURABLE_STOP_KINDS_V1,
    derived_program_budget_v1,
    raise_budget_exhausted_v1,
    raise_no_progress_v1,
    program_progress_signature_v1,
)
from _thinkengine.__persistence.config import (
    get_session_repo,
)
from _thinkengine.__persistence.models import (
    SessionState,
)


CreateSessionReturn = (
    Dict[str, Any]
    | Tuple[Dict[str, Any], Dict[str, Any]]
)

################
# reexports as the top surface
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    register_step_fn,
    StepFnregistry,
)

from _thinkengine._parsing.app_table_program_parser import (
    parse_and_validate_app_table,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_active_span_record_from_ctx,
    get_form_fill_info,
    get_runtime_write_index_summary,
    query_runtime_writes,
)

from __exceptions.engine import (
    AppTableParserValidatorError,
)
##############


def _session_surface_metadata(
    session_surface: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Convert a lowered program's session surface into generic metadata.

    `initial_parameter_overrides` remains a dedicated creation input.
    `session_metadata` is used as the initial metadata mapping.
    Every other top-level session-surface key is treated as an extension and
    merged into that mapping.

    This allows lowering languages to add declarative session features without
    expanding the abstract creation signature.
    """

    metadata = _mapping_from_any(
        session_surface.get(
            "session_metadata"
        )
    )

    extensions = {
        str(key): value
        for key, value in session_surface.items()
        if key not in {
            "initial_parameter_overrides",
            "session_metadata",
        }
    }

    return _deep_merge_mapping_values(
        metadata,
        extensions,
    )


class AbstractSessionAPI(ABC):
    """
    Generic session lifecycle and execution contract.

    Implementations may use any engine or persistence strategy. The public
    contract remains independent of viewers, roles, rendering, and concrete
    runtime layout.
    """

    @abstractmethod
    def create_VM_session(
        self,
        *,
        manifest: Any,
        initial_parameter_overrides: Dict[str, Any],
        session_metadata: Any = None,
        coercer_of_session_metadata: Optional[Callable[[Any], Any]] = None,
        get_map: bool = False,
    ) -> CreateSessionReturn:
        raise NotImplementedError

    def create_VM_session_from_program(
        self,
        *,
        program: Any,
        program_language: str,
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Any = None,
        coercer_of_session_metadata: Optional[Callable[[Any], Any]] = None,
        get_map: bool = False,
    ) -> CreateSessionReturn:
        """
        Lower a source program and delegate generic session creation.

        Language lowering may contribute:
        - an executable manifest;
        - initial globals;
        - generic session metadata and extension keys;
        - lowering provenance.

        Explicit caller globals override lowered globals. Explicit caller
        metadata is deep-merged over lowered metadata.
        """

        from _thinkengine._parsing._higher_lang_grammars._langs_core import (
            lower_program_to_app_table_bundle,
        )

        bundle = lower_program_to_app_table_bundle(
            program_language=program_language,
            program=program,
            initial_parameter_overrides=dict(
                initial_parameter_overrides or {}
            ),
        )

        session_surface = _mapping_from_any(
            getattr(
                bundle,
                "session_surface",
                None,
            )
        )

        merged_initial_parameter_overrides = _mapping_from_any(
            session_surface.get(
                "initial_parameter_overrides"
            )
        )
        merged_initial_parameter_overrides.update(
            dict(initial_parameter_overrides or {})
        )

        merged_metadata = _session_surface_metadata(
            session_surface
        )
        merged_metadata = _deep_merge_mapping_values(
            merged_metadata,
            _mapping_from_any(
                session_metadata
            ),
        )

        return self.create_VM_session(
            manifest=bundle.app_table_manifest,
            initial_parameter_overrides=merged_initial_parameter_overrides,
            session_metadata=merged_metadata,
            coercer_of_session_metadata=coercer_of_session_metadata,
            get_map=get_map,
        )

    @abstractmethod
    def step_session(
        self,
        session_id: str,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def redo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_session_context(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_outputs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def export_session_snapshot(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "export_session_snapshot(...)"
        )

    def drain_session_events(
        self,
        session_id: str,
    ) -> list[Dict[str, Any]]:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "drain_session_events(...)"
        )

    def get_session_events(
        self,
        session_id: str,
        *,
        limit: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "get_session_events(...)"
        )

    def get_latest_session_event_seq(
        self,
        session_id: str,
    ) -> int:
        raise NotImplementedError(
            f"{type(self).__name__} does not support "
            "get_latest_session_event_seq(...)"
        )

    def emit_session_event(
        self,
        session_id: str,
        *,
        form_id: Optional[str] = None,
        frame_id: Optional[str] = None,
        span_id: Optional[str] = None,
        datum_id: str,
        payload: Any = None,
        name: str = "datum.external",
        event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "emit_session_event(...)"
        )

    def import_session_snapshot(
        self,
        session_id: str,
        *,
        snapshot: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "import_session_snapshot(...)"
        )

    def delete_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{type(self).__name__} "
            "does not support "
            "delete_session(...)"
        )

    def step(
        self,
        session_id: str,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.step_session(
            session_id,
            fill=fill,
            signal=signal,
            threaded_callbacks=threaded_callbacks,
        )

    def undo(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self.undo_last_step(
            session_id
        )

    def redo(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self.redo_last_step(
            session_id
        )

    def ctx(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self.get_session_context(
            session_id
        )

    def outputs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self.get_outputs(
            session_id
        )


class AppTableSessionAPI(AbstractSessionAPI):
    """
    Concrete App Table session implementation.

    One public operation may cross internal execution states but stops at the
    appropriate durable session boundary.

    Repository binding
    ------------------
    A concrete API instance captures the configured repository when it is
    constructed. Long-lived process singletons may be constructed before a
    framework integration such as Django has completed application startup.

    ``install_session_repo`` is therefore the explicit integration seam for
    rebinding such an existing instance after the service repository has been
    installed globally.
    """

    _UI_STOP_KINDS = set(
        PROGRAM_DURABLE_STOP_KINDS
    )
    _UI_UNDO_STOP_KINDS = set(
        PROGRAM_UNDO_DURABLE_STOP_KINDS_V1
    )
    _AUTO_ADVANCE_KINDS = set(
        PROGRAM_AUTO_ADVANCE_KINDS_V1
    )

    def __init__(
        self,
        *,
        enable_persistence: bool = True,
    ) -> None:
        self._sessions: Dict[
            str,
            AppTableProgramEngine,
        ] = {}
        self._repo_cls = (
            get_session_repo()
            if enable_persistence
            else None
        )
        self._transient_scopes_checked: set[str] = set()

    def install_session_repo(
        self,
        repo_cls: Any,
    ) -> None:
        """
        Install the repository used by this concrete API instance.

        This is primarily used by framework bootstraps that install their
        durable repository after the process-local concrete API singleton has
        already been imported.

        Passing ``None`` disables persistence for this instance.
        """

        self._repo_cls = repo_cls

    def evict_session_runtime(
        self,
        session_id: str,
    ) -> None:
        """
        Forget only the process-local materialized runtime for one session.

        This operation performs no repository or database deletion. It is the
        hosting rollback/reload seam used when durable storage remains
        authoritative but an already-materialized engine may contain state
        produced by an aborted transaction.

        After this method returns, the next ordinary session access must
        reconstruct the engine through the configured repository.
        """
        normalized_id = str(session_id)
        self._sessions.pop(
            normalized_id,
            None,
        )
        self._transient_scopes_checked.discard(
            normalized_id
        )

    def checkpoint_session_runtime(
        self,
        session_id: str,
    ) -> None:
        """
        Force one complete opaque-runtime persistence checkpoint.

        This is a hosting transaction seam, not an ordinary manual-I/O
        persistence-policy decision.

        A server coordinator that claims atomic session dispatch must call this
        after the complete logical dispatch has mutated the live runtime and
        before it commits its outer transaction. The checkpoint deliberately
        ignores ``manual_io.persistence`` because that policy controls ordinary
        standalone core operations; it cannot suppress the server's required
        transaction commit of the authoritative runtime.

        The persisted SessionState contains one coherent version of:

        - the engine/program state;
        - the retained canonical event queue;
        - the queue's next sequence position;
        - the canonical latest-event high-water; and
        - existing hosting-owned additional JSON.

        If the surrounding hosting transaction aborts, the host must evict the
        materialized runtime before any subsequent access.
        """
        eng = self._get(
            str(session_id)
        )
        self._persist(eng)

    def _persist_latest_event_seq_v1(
        self,
        eng: AppTableProgramEngine,
        seq: int,
    ) -> None:
        repo = self._repo_cls
        saver = getattr(repo, "save_latest_event_seq", None)
        if repo is None or not callable(saver):
            return
        saver(UUID(str(eng.session_id)), int(seq))

    def _bind_engine_runtime_hooks_v1(
        self,
        eng: AppTableProgramEngine,
    ) -> AppTableProgramEngine:
        """
        Bind process-local hooks that must never enter snapshots.

        Every canonical queue append updates one tiny persisted high-water
        scalar. This keeps the polling endpoint independent of event payload
        volume and avoids loading/deserializing the engine blob on a cold read.
        """
        eng._session_event_seq_advanced_callback_v1 = (
            lambda seq, _eng=eng: self._persist_latest_event_seq_v1(
                _eng,
                int(seq),
            )
        )
        return eng

    # ------------------------------------------------------------------
    # Profiling and persistence policy
    # ------------------------------------------------------------------

    def _manual_io_profile_enabled_v1(
        self,
        eng: AppTableProgramEngine,
    ) -> bool:
        metadata = (
            getattr(
                eng,
                "session_metadata",
                {},
            )
            or {}
        )
        config = (
            metadata.get("manual_io")
            if isinstance(
                metadata,
                Mapping,
            )
            else None
        )
        config = (
            config
            if isinstance(
                config,
                Mapping,
            )
            else {}
        )

        return bool(
            config.get(
                "profile",
                False,
            )
        )

    def _with_manual_io_profile_last_call_v1(
        self,
        *,
        out: Mapping[str, Any],
        operation: str,
        profile: Mapping[str, float],
        fill: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = dict(out)
        metadata = dict(
            result.get(
                "session_metadata"
            )
            or {}
        )

        metadata[
            "manual_io_profile_last_call_v1"
        ] = {
            "operation": str(operation),
            "kind": result.get("kind"),
            "fill_keys": sorted(
                str(key)
                for key in dict(
                    fill or {}
                ).keys()
            ),
            "timings": dict(profile),
            "total_s": sum(
                float(value)
                for value in profile.values()
            ),
        }

        result["session_metadata"] = metadata
        return result

    def _persist(
        self,
        eng: AppTableProgramEngine,
    ) -> None:
        """
        Persist the engine while preserving feature-owned SessionState JSON.

        ``additional_json`` is an extension envelope shared by facilities . Ordinary engine persistence owns the engine blob and
        session metadata, but it must not erase pockets written by independent
        session features.

        Repositories may expose an existing SessionState or may not yet contain
        one. A missing row therefore falls back to an empty extension mapping.
        """
        if self._repo_cls is None:
            return

        session_id = UUID(
            str(eng.session_id)
        )
        blob = eng.to_bytes()

        additional_json: Dict[str, Any] = {}

        try:
            existing = self._repo_cls.get(
                session_id
            )
        except (KeyError, LookupError):
            existing = None

        if isinstance(existing, SessionState):
            raw_additional_json = getattr(
                existing,
                "additional_json",
                None,
            )
            if isinstance(
                raw_additional_json,
                Mapping,
            ):
                additional_json = dict(
                    raw_additional_json
                )

        self._repo_cls.save_stepper(
            session_id,
            blob,
        )
        self._repo_cls.save_state(
            SessionState(
                session_id=session_id,
                pickled_stepper=blob,
                session_metadata=dict(
                    eng.session_metadata
                ),
                additional_json=additional_json,
                latest_event_seq=eng.latest_session_event_seq_v1(),
            )
        )

    def _manual_io_persistence_policy_v1(
        self,
        eng: AppTableProgramEngine,
    ) -> str:
        metadata = (
            getattr(
                eng,
                "session_metadata",
                {},
            )
            or {}
        )
        config = (
            metadata.get("manual_io")
            if isinstance(
                metadata,
                Mapping,
            )
            else None
        )
        config = (
            config
            if isinstance(
                config,
                Mapping,
            )
            else {}
        )

        policy = str(
            config.get("persistence")
            or "boundary"
        ).strip().lower()

        if policy not in {
            "eager",
            "boundary",
            "disabled",
        }:
            return "boundary"

        return policy

    def _should_persist_after_step_v1(
        self,
        *,
        eng: AppTableProgramEngine,
        ctx: Mapping[str, Any],
    ) -> bool:
        policy = self._manual_io_persistence_policy_v1(
            eng
        )

        if policy == "disabled":
            return False

        if policy == "eager":
            return True

        return (
            str(ctx.get("kind") or "")
            != "MANUALFILLNEEDEDSTEP"
        )

    def _should_persist_after_mutation_v1(
        self,
        *,
        eng: AppTableProgramEngine,
        ctx: Mapping[str, Any],
    ) -> bool:
        policy = self._manual_io_persistence_policy_v1(
            eng
        )

        if policy == "disabled":
            return False

        if policy == "eager":
            return True

        return (
            str(ctx.get("kind") or "")
            != "MANUALFILLNEEDEDSTEP"
        )

    # ------------------------------------------------------------------
    # Creation and lookup
    # ------------------------------------------------------------------

    def create_VM_session(
        self,
        *,
        manifest: Any,
        initial_parameter_overrides: Dict[str, Any],
        session_metadata: Any = None,
        coercer_of_session_metadata: Optional[Callable[[Any], Any]] = None,
        get_map: bool = False,
    ) -> CreateSessionReturn:
        try:
            assert_dead_json(
                initial_parameter_overrides or {},
                path="initial_parameter_overrides",
            )
        except DeadJSONError as exc:
            raise ValueError(
                str(exc)
            ) from exc

        try:
            metadata = (
                coercer_of_session_metadata(
                    session_metadata
                )
                if coercer_of_session_metadata is not None
                else session_metadata
            )
            assert_dead_json(
                metadata,
                path="session_metadata",
            )
        except DeadJSONError as exc:
            raise ValueError(
                str(exc)
            ) from exc

        from _thinkengine._parsing.app_table_program_parser import (
            parse_and_validate_app_table,
        )

        steps = parse_and_validate_app_table(
            manifest
        )

        eng = AppTableProgramEngine(
            steps=steps,
            initial_parameter_overrides=dict(
                initial_parameter_overrides or {}
            ),
            session_metadata=(
                dict(metadata)
                if metadata is not None
                else {}
            ),
        )
        self._bind_engine_runtime_hooks_v1(eng)

        self._sessions[
            eng.session_id
        ] = eng

        if self._repo_cls is not None:
            session_id = UUID(
                str(eng.session_id)
            )
            blob = eng.to_bytes()

            self._repo_cls.create(
                SessionState(
                    session_id=session_id,
                    pickled_stepper=blob,
                    session_metadata=dict(
                        eng.session_metadata
                    ),
                    latest_event_seq=0,
                ),
                stepper=blob,
            )

        state = {
            "session_id": eng.session_id,
        }

        if get_map:
            from _thinkengine._parsing.app_table_program_parser import (
                build_program_map,
            )

            return (
                state,
                build_program_map(steps),
            )

        return state

    def _get(
        self,
        session_id: str,
    ) -> AppTableProgramEngine:
        normalized_id = str(
            session_id
        )

        existing = self._sessions.get(
            normalized_id
        )
        if existing is not None:
            return existing

        if self._repo_cls is not None:
            state = self._repo_cls.get(
                UUID(normalized_id)
            )
            blob = getattr(
                state,
                "pickled_stepper",
                None,
            )

            if (
                isinstance(
                    blob,
                    (bytes, bytearray),
                )
                and blob
            ):
                eng = AppTableProgramEngine.from_bytes(
                    bytes(blob)
                )
                self._bind_engine_runtime_hooks_v1(eng)
                self._sessions[
                    eng.session_id
                ] = eng
                return eng

        raise KeyError(
            "unknown session_id: "
            f"{normalized_id}"
        )

    # ------------------------------------------------------------------
    # Internal durable-boundary progression
    # ------------------------------------------------------------------

    def _ctx_progress_signature_v1(
        self,
        eng: AppTableProgramEngine,
        ctx: Mapping[str, Any],
    ) -> tuple[Any, ...]:
        return (
            int(
                getattr(
                    eng,
                    "cursor",
                    -1,
                )
            ),
            len(
                getattr(
                    eng,
                    "program",
                    (),
                )
                or ()
            ),
            *program_progress_signature_v1(
                ctx
            ),
        )

    def _derived_internal_step_limit(
        self,
        eng: AppTableProgramEngine,
        requested_limit: int,
    ) -> int:
        if requested_limit > 0:
            return requested_limit

        return derived_program_budget_v1(
            program_len=len(
                getattr(
                    eng,
                    "program",
                    (),
                )
                or ()
            ),
            default_max_steps=16,
            floor=16,
            per_program_step=4,
            cap=4096,
        )

    def _step_until_ui_stop(
        self,
        eng: AppTableProgramEngine,
        *,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        max_internal_steps: int = 0,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = eng.get_context()
        current_kind = str(
            current.get("kind") or ""
        )

        if (
            fill is None
            and signal is None
            and current_kind in self._UI_STOP_KINDS
        ):
            return dict(current)

        ctx = eng.step(
            fill=fill,
            signal=signal,
            threaded_callbacks=threaded_callbacks,
        )
        limit = self._derived_internal_step_limit(
            eng,
            max_internal_steps,
        )
        previous_signature = self._ctx_progress_signature_v1(
            eng,
            ctx,
        )

        for _ in range(limit):
            kind = str(
                ctx.get("kind") or ""
            )

            if kind in self._UI_STOP_KINDS:
                return dict(ctx)

            if kind not in self._AUTO_ADVANCE_KINDS:
                return dict(ctx)

            ctx = eng.step(
                fill=None,
                signal=None,
                threaded_callbacks=threaded_callbacks,
            )
            signature = self._ctx_progress_signature_v1(
                eng,
                ctx,
            )

            if signature == previous_signature:
                raise_no_progress_v1(
                    label=(
                        "AppTableSessionAPI."
                        "step_session"
                    ),
                    stop_kinds=(
                        PROGRAM_DURABLE_STOP_KINDS
                    ),
                    ctx=ctx,
                    mode=(
                        "auto-advance internal "
                        "engine steps"
                    ),
                )

            previous_signature = signature

        raise_budget_exhausted_v1(
            label=(
                "AppTableSessionAPI."
                "step_session"
            ),
            max_steps=limit,
            stop_kinds=(
                PROGRAM_DURABLE_STOP_KINDS
            ),
            ctx=ctx,
        )

    def _undo_until_ui_stop(
        self,
        eng: AppTableProgramEngine,
        *,
        max_internal_steps: int = 0,
    ) -> Dict[str, Any]:
        before = eng.get_context()
        before_kind = str(
            before.get("kind") or ""
        )

        if before_kind == "ATCOMPLETION":
            try:
                ctx = eng.undo(
                    render_context=False
                )
            except TypeError:
                ctx = eng.undo()

            if (
                str(
                    ctx.get("kind") or ""
                )
                == "MANUALFILLNEEDEDSTEP"
            ):
                ctx = eng.undo()
        else:
            ctx = eng.undo()

        limit = self._derived_internal_step_limit(
            eng,
            max_internal_steps,
        )
        previous_signature = self._ctx_progress_signature_v1(
            eng,
            ctx,
        )

        for _ in range(limit):
            kind = str(
                ctx.get("kind") or ""
            )

            if kind in self._UI_UNDO_STOP_KINDS:
                return dict(ctx)

            if kind not in self._AUTO_ADVANCE_KINDS:
                return dict(ctx)

            ctx = eng.undo()
            signature = self._ctx_progress_signature_v1(
                eng,
                ctx,
            )

            if signature == previous_signature:
                raise_no_progress_v1(
                    label=(
                        "AppTableSessionAPI."
                        "undo_last_step"
                    ),
                    stop_kinds=(
                        PROGRAM_UNDO_DURABLE_STOP_KINDS_V1
                    ),
                    ctx=ctx,
                    mode=(
                        "auto-rewind internal "
                        "engine steps"
                    ),
                )

            previous_signature = signature

        raise_budget_exhausted_v1(
            label=(
                "AppTableSessionAPI."
                "undo_last_step"
            ),
            max_steps=limit,
            stop_kinds=(
                PROGRAM_UNDO_DURABLE_STOP_KINDS_V1
            ),
            ctx=ctx,
        )

    def _redo_until_ui_stop(
        self,
        eng: AppTableProgramEngine,
        *,
        max_internal_steps: int = 0,
    ) -> Dict[str, Any]:
        ctx = eng.redo()
        limit = self._derived_internal_step_limit(
            eng,
            max_internal_steps,
        )
        previous_signature = self._ctx_progress_signature_v1(
            eng,
            ctx,
        )

        for _ in range(limit):
            kind = str(
                ctx.get("kind") or ""
            )

            if kind in self._UI_STOP_KINDS:
                return dict(ctx)

            if kind not in self._AUTO_ADVANCE_KINDS:
                return dict(ctx)

            ctx = eng.step(
                fill=None,
                signal=None,
            )
            signature = self._ctx_progress_signature_v1(
                eng,
                ctx,
            )

            if signature == previous_signature:
                raise_no_progress_v1(
                    label=(
                        "AppTableSessionAPI."
                        "redo_last_step"
                    ),
                    stop_kinds=(
                        PROGRAM_DURABLE_STOP_KINDS
                    ),
                    ctx=ctx,
                    mode=(
                        "auto-advance internal "
                        "engine steps after redo"
                    ),
                )

            previous_signature = signature

        raise_budget_exhausted_v1(
            label=(
                "AppTableSessionAPI."
                "redo_last_step"
            ),
            max_steps=limit,
            stop_kinds=(
                PROGRAM_DURABLE_STOP_KINDS
            ),
            ctx=ctx,
        )

    # ------------------------------------------------------------------
    # Public roleless session operations
    # ------------------------------------------------------------------

    def step_session(
        self,
        session_id: str,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        eng = self._get(
            session_id
        )
        profile_enabled = self._manual_io_profile_enabled_v1(
            eng
        )
        profile: Dict[str, float] = {}

        started = time.perf_counter()
        ctx = self._step_until_ui_stop(
            eng,
            fill=fill,
            signal=signal,
            threaded_callbacks=threaded_callbacks,
        )

        if profile_enabled:
            profile[
                "step_until_ui_stop_s"
            ] = (
                time.perf_counter()
                - started
            )

        started = time.perf_counter()
        should_persist = self._should_persist_after_step_v1(
            eng=eng,
            ctx=ctx,
        )

        if profile_enabled:
            profile[
                "persist_decision_s"
            ] = (
                time.perf_counter()
                - started
            )

        if should_persist:
            started = time.perf_counter()
            self._persist(
                eng
            )

            if profile_enabled:
                profile["persist_s"] = (
                    time.perf_counter()
                    - started
                )

        if profile_enabled:
            return self._with_manual_io_profile_last_call_v1(
                out=ctx,
                operation="step_session",
                profile=profile,
                fill=fill,
            )

        return ctx

    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        eng = self._get(
            session_id
        )
        profile_enabled = self._manual_io_profile_enabled_v1(
            eng
        )
        profile: Dict[str, float] = {}

        started = time.perf_counter()
        ctx = self._undo_until_ui_stop(
            eng
        )

        if profile_enabled:
            profile[
                "undo_until_ui_stop_s"
            ] = (
                time.perf_counter()
                - started
            )

        started = time.perf_counter()
        should_persist = self._should_persist_after_mutation_v1(
            eng=eng,
            ctx=ctx,
        )

        if profile_enabled:
            profile[
                "persist_decision_s"
            ] = (
                time.perf_counter()
                - started
            )

        if should_persist:
            started = time.perf_counter()
            self._persist(
                eng
            )

            if profile_enabled:
                profile["persist_s"] = (
                    time.perf_counter()
                    - started
                )

        if profile_enabled:
            return self._with_manual_io_profile_last_call_v1(
                out=ctx,
                operation="undo_last_step",
                profile=profile,
            )

        return ctx

    def redo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        eng = self._get(
            session_id
        )
        profile_enabled = self._manual_io_profile_enabled_v1(
            eng
        )
        profile: Dict[str, float] = {}

        started = time.perf_counter()
        ctx = self._redo_until_ui_stop(
            eng
        )

        if profile_enabled:
            profile[
                "redo_until_ui_stop_s"
            ] = (
                time.perf_counter()
                - started
            )

        started = time.perf_counter()
        should_persist = self._should_persist_after_mutation_v1(
            eng=eng,
            ctx=ctx,
        )

        if profile_enabled:
            profile[
                "persist_decision_s"
            ] = (
                time.perf_counter()
                - started
            )

        if should_persist:
            started = time.perf_counter()
            self._persist(
                eng
            )

            if profile_enabled:
                profile["persist_s"] = (
                    time.perf_counter()
                    - started
                )

        if profile_enabled:
            return self._with_manual_io_profile_last_call_v1(
                out=ctx,
                operation="redo_last_step",
                profile=profile,
            )

        return ctx

    def get_session_context(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self._get(
            session_id
        ).get_context()

    def get_outputs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self._get(
            session_id
        ).get_outputs()

    def drain_session_events(
        self,
        session_id: str,
    ) -> list[Dict[str, Any]]:
        eng = self._get(
            session_id
        )
        return eng.drain_events_from_session()

    def get_session_events(
        self,
        session_id: str,
        *,
        limit: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        eng = self._get(
            session_id
        )
        return eng.peek_events_from_session(limit=limit)

    def get_latest_session_event_seq(
        self,
        session_id: str,
    ) -> int:
        """
        Return the session event high-water mark without reading event payloads.

        Hot sessions read the engine scalar. Cold persisted sessions use the
        repository scalar when the adapter supports it, avoiding engine blob
        loading and snapshot deserialization.
        """
        normalized_id = str(session_id)
        eng = self._sessions.get(normalized_id)
        if eng is not None:
            return eng.latest_session_event_seq_v1()

        repo = self._repo_cls
        getter = getattr(repo, "get_latest_event_seq", None)
        if repo is not None and callable(getter):
            return max(0, int(getter(UUID(normalized_id))))

        return self._get(normalized_id).latest_session_event_seq_v1()

    def record_session_event(
        self,
        session_id: str,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        eng = self._get(session_id)
        return eng.record_event_to_engine_session(event)

    def emit_session_event(
        self,
        session_id: str,
        *,
        form_id: Optional[str] = None,
        frame_id: Optional[str] = None,
        span_id: Optional[str] = None,
        datum_id: str,
        payload: Any = None,
        name: str = "datum.external",
        event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        UI-agnostic legal artificial event pathway.

        This is for webhooks/frontends/higher session servers. It does not
        mutate durable engine state. It sends the same live event packet through
        the same engine-local sink and global callback as widget emissions.
        """

        eng = self._get(
            session_id
        )

        step_payload: Dict[str, Any] = {}
        try:
            cur = eng._get_current_step()
            if isinstance(
                cur.payload,
                Mapping,
            ):
                step_payload = dict(
                    cur.payload
                )
        except Exception:
            step_payload = {}

        resolved_form_id = str(
            form_id
            or eng.state.get("pending_multiframespec_id")
            or eng.state.get("app_form_id")
            or ""
        ).strip()
        resolved_frame_id = str(
            frame_id
            or step_payload.get("frame_id")
            or ""
        ).strip()
        resolved_span_id = str(
            span_id
            or step_payload.get("span_id")
            or ""
        ).strip()

        if (
            not resolved_form_id
            or not resolved_frame_id
            or not resolved_span_id
        ):
            raise ValueError(
                "emit_session_event requires form_id/frame_id/span_id, "
                "or a current manual step payload from which they can be "
                "inferred"
            )

        return eng.emit_datum_event_to_engine_session(
            form_id=resolved_form_id,
            frame_id=resolved_frame_id,
            span_id=resolved_span_id,
            datum_id=str(datum_id),
            payload=payload,
            name=name,
            event_callback=event_callback,
        )

    def get_session_storage_report(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Tiny diagnostic report for session weight profiling.

        This does not expose the raw snapshot.
        """

        eng = self._get(
            session_id
        )
        blob = eng.to_bytes()
        snapshot = eng.to_snapshot()
        state = (
            snapshot.get("state")
            if isinstance(
                snapshot,
                Mapping,
            )
            else {}
        )
        state = (
            state
            if isinstance(
                state,
                Mapping,
            )
            else {}
        )

        return {
            "kind": "session_storage_report_v1",
            "session_id": str(session_id),
            "snapshot_bytes": len(blob),
            "program_steps": len(
                snapshot.get("program")
                or []
            ),
            "exec_records": len(
                snapshot.get("exec_records")
                or {}
            ),
            "redo_stack": len(
                snapshot.get("redo_stack_v1")
                or []
            ),
            "forms_emitted": len(
                state.get("forms_emitted")
                or {}
            ),
            "form_prefills": len(
                state.get("form_prefills")
                or {}
            ),
            "form_fills": len(
                state.get("form_fills")
                or {}
            ),
        }

    # ------------------------------------------------------------------
    # Snapshot lifecycle
    # ------------------------------------------------------------------

    def export_session_snapshot(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        snapshot = self._get(
            session_id
        ).to_snapshot()

        if not isinstance(
            snapshot,
            dict,
        ):
            raise TypeError(
                "engine snapshot must "
                "be a dict"
            )

        return snapshot

    def import_session_snapshot(
        self,
        session_id: str,
        *,
        snapshot: Mapping[str, Any],
    ) -> None:
        if not isinstance(
            snapshot,
            Mapping,
        ):
            raise TypeError(
                "snapshot must be a mapping"
            )

        snapshot_session_id = str(
            snapshot.get("session_id")
            or ""
        )

        if (
            snapshot_session_id
            and snapshot_session_id != str(session_id)
        ):
            raise ValueError(
                "snapshot.session_id "
                "mismatch: "
                f"expected {session_id!r}, "
                f"got {snapshot_session_id!r}"
            )

        eng = AppTableProgramEngine.from_snapshot(
            snapshot
        )

        if str(eng.session_id) != str(session_id):
            raise ValueError(
                "restored "
                "engine.session_id "
                "mismatch: "
                f"expected {session_id!r}, "
                f"got {eng.session_id!r}"
            )

        normalized_id = str(
            session_id
        )
        self._sessions[
            normalized_id
        ] = eng
        self._bind_engine_runtime_hooks_v1(eng)
        self._transient_scopes_checked.discard(
            normalized_id
        )

        self._persist(
            eng
        )

    def delete_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        normalized_id = str(
            session_id
        )

        self._sessions.pop(
            normalized_id,
            None,
        )
        self._transient_scopes_checked.discard(
            normalized_id
        )

        if self._repo_cls is not None:
            self._repo_cls.delete(
                UUID(normalized_id)
            )

        return {
            "kind": (
                "thinkument_session_"
                "delete_report_v1"
            ),
            "session_id": normalized_id,
            "ok": True,
        }


_CONCRETE_SESSION_API = AppTableSessionAPI()


def create_VM_session(
    *,
    manifest: Any,
    initial_parameter_overrides: Dict[str, Any],
    session_metadata: Any = None,
    coercer_of_session_metadata: Optional[Callable[[Any], Any]] = None,
    get_map: bool = False,
) -> CreateSessionReturn:
    return _CONCRETE_SESSION_API.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
        coercer_of_session_metadata=coercer_of_session_metadata,
        get_map=get_map,
    )


def create_VM_session_from_program(
    *,
    program: Any,
    program_language: str,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Any = None,
    coercer_of_session_metadata: Optional[Callable[[Any], Any]] = None,
    get_map: bool = False,
) -> CreateSessionReturn:
    return _CONCRETE_SESSION_API.create_VM_session_from_program(
        program=program,
        program_language=program_language,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
        coercer_of_session_metadata=coercer_of_session_metadata,
        get_map=get_map,
    )


def step_session(
    session_id: str,
    fill: Optional[Dict[str, Any]] = None,
    signal: Optional[Dict[str, Any]] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.step_session(
        session_id,
        fill=fill,
        signal=signal,
        threaded_callbacks=threaded_callbacks,
    )


def undo_last_step(
    session_id: str,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.undo_last_step(
        session_id
    )


def redo_last_step(
    session_id: str,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.redo_last_step(
        session_id
    )


def get_session_context(
    session_id: str,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.get_session_context(
        session_id
    )


def get_outputs(
    session_id: str,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.get_outputs(
        session_id
    )


def drain_session_events(
    session_id: str,
) -> list[Dict[str, Any]]:
    return _CONCRETE_SESSION_API.drain_session_events(
        session_id
    )


def get_session_events(
    session_id: str,
    *,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    return _CONCRETE_SESSION_API.get_session_events(
        session_id,
        limit=limit,
    )


def get_latest_session_event_seq(
    session_id: str,
) -> int:
    return _CONCRETE_SESSION_API.get_latest_session_event_seq(
        session_id
    )


def emit_session_event(
    session_id: str,
    *,
    form_id: Optional[str] = None,
    frame_id: Optional[str] = None,
    span_id: Optional[str] = None,
    datum_id: str,
    payload: Any = None,
    name: str = "datum.external",
    event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.emit_session_event(
        session_id,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
        payload=payload,
        name=name,
        event_callback=event_callback,
    )


def get_session_storage_report(
    session_id: str,
) -> Dict[str, Any]:
    return _CONCRETE_SESSION_API.get_session_storage_report(
        session_id
    )


def get_concrete_session_api(
    **kwargs: Any,
) -> AppTableSessionAPI:
    """
    Return the process-local concrete App Table session API singleton.

    ``kwargs`` is retained for compatibility with callers that previously
    supplied concrete API construction options. The process-local singleton
    has already been constructed, so such options do not alter it.
    """

    del kwargs
    return _CONCRETE_SESSION_API


def evict_session_runtime(
    session_id: str,
) -> None:
    """
    Forget one materialized process-local engine without deleting persistence.

    Hosting transaction coordinators use this after rollback and before a
    forced cold restore from their authoritative durable row.
    """
    _CONCRETE_SESSION_API.evict_session_runtime(
        str(session_id)
    )


def checkpoint_session_runtime(
    session_id: str,
) -> None:
    """
    Force a complete opaque-runtime persistence checkpoint.

    Hosting transaction coordinators use this after a logical dispatch and
    before committing their engine-state, high-water, staleness-index, and
    immutable-receipt transaction.
    """
    _CONCRETE_SESSION_API.checkpoint_session_runtime(
        str(session_id)
    )


__all__ = [
    "CreateSessionReturn",
    "AbstractSessionAPI",
    "AppTableSessionAPI",
    "get_concrete_session_api",
    "evict_session_runtime",
    "checkpoint_session_runtime",
    "create_VM_session",
    "create_VM_session_from_program",
    "step_session",
    "undo_last_step",
    "redo_last_step",
    "get_session_context",
    "get_outputs",
    "drain_session_events",
    "get_session_events",
    "get_latest_session_event_seq",
    "emit_session_event",
    "get_session_storage_report",
]