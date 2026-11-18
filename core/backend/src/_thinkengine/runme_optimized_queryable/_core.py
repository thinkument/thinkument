# think-backend/src/runme_optimized_queryable/_core.py
from __future__ import annotations

"""
Shared bounded public session API core for Thinkument app-table programs.

Keep endpoint-specific module-level functions in those façade modules. Keep the
shared PublicSessionAPI wrapper, singleton wiring, bounded query/report logic,
and public constants here.

Public boundary law
-------------------

S/G surfaces never intentionally return raw ctx, raw outputs, raw snapshot,
program_map, multiframespec, full globals, full history, datum_widget_fills,
or HTML.

Bounded metadata is allowed:

    {"counts": {"form_fills": 2}}
    {"keys": {"form_fills": ["NAME", "AGE"]}}

Explicit G* queries may return bounded rows with values only when requested,
for example runtime_writes(include_values=True) or
program_trace_table(include_datum_values=True). Even then, max_results is
capped by this public API.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from _thinkengine.runme._script_contract import (
    normalize_session_fill_json_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
    get_runtime_write_index_summary,
    query_runtime_writes,
    register_step_fn,  # re-exported by public façades
)

from _thinkengine.runme_optimized_queryable._globals import (
    ABSOLUTE_QUERY_MAX_RESULTS_V1,
    DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1,
    DEFAULT_FRONTEND_INCLUDE_CTX_V1,
    DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1,
    DEFAULT_QUERY_MAX_RESULTS_V1,
    DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1,
    DEFAULT_REDO_MAX_DEPTH_V1,
    DEFAULT_TRACE_MAX_RESULTS_V1,
    KIND_COMMAND_RECEIPT_V1,
    KIND_PROGRAM_TRACE_TABLE_V1,
    KIND_SCRIPT_RUN_REPORT_V1,
    KIND_SESSION_QUERY_RESULT_V1,
    KIND_SESSION_REPORT_V1,
    PUBLIC_API_VERSION_V1,
    PublicSessionCaps,
)
from _thinkengine.runme_optimized_queryable._helpers import (
    _coerce_public_caps_v1,
    _merge_public_session_storage_policy_v1,
    _outputs_report_from_outputs_v1,
    _strip_forbidden_public_keys,
    public_command_receipt_from_ctx_v1,
    public_create_receipt_v1,
    public_delete_receipt_v1,
    public_session_report_from_ctx_v1,
)
from _thinkengine.runme_optimized_queryable._specs import (
    _compact_manifest_call_rows_v1,
    _normalize_runtime_write_query_v1,
    _program_trace_table_v1,
    _public_script_action_summary_v1,
)


@dataclass
class PublicSessionAPI:
    """
    Bounded app-facing session API.

    Instantiate this class directly only when a service/test needs its own
    raw_api or PublicSessionCaps.
    """

    raw_api: "AbstractSessionAPI"
    caps: PublicSessionCaps = field(default_factory=PublicSessionCaps)
    _manifest_call_rows_by_session_id: Dict[str, list[Dict[str, Any]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.caps = _coerce_public_caps_v1(self.caps)

    def create_session(
        self,
        *,
        manifest: Any,
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Any = None,
    ) -> Dict[str, Any]:
        created = self.raw_api.create_VM_session(
            manifest=manifest,
            initial_parameter_overrides=dict(initial_parameter_overrides or {}),
            session_metadata=_merge_public_session_storage_policy_v1(
                session_metadata,
                caps=self.caps,
            ),
            get_map=False,
        )
        receipt = public_create_receipt_v1(
            created,
            operation="create_session",
            caps=self.caps,
        )

        sid = str(receipt.get("session_id") or "")
        if sid:
            self._manifest_call_rows_by_session_id[sid] = (
                _compact_manifest_call_rows_v1(
                    manifest,
                    include_fn_args=True,
                )
            )

        return receipt

    def create_session_from_program(
        self,
        *,
        program: Any,
        program_language: str,
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Any = None,
    ) -> Dict[str, Any]:
        created = self.raw_api.create_VM_session_from_program(
            program=program,
            program_language=program_language,
            initial_parameter_overrides=dict(initial_parameter_overrides or {}),
            session_metadata=_merge_public_session_storage_policy_v1(
                session_metadata,
                caps=self.caps,
            ),
            get_map=False,
        )
        receipt = public_create_receipt_v1(
            created,
            operation="create_session_from_program",
            caps=self.caps,
        )

        sid = str(receipt.get("session_id") or "")
        if sid:
            self._manifest_call_rows_by_session_id[sid] = [
                {
                    "row_kind": "app_call",
                    "call_index": 0,
                    "public_step_name": None,
                    "step_fn": None,
                    "program_language": str(program_language),
                }
            ]

        return receipt

    def step_session(
        self,
        session_id: str,
        *,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_fill = normalize_session_fill_json_v1(fill)
        callback_bag = dict(threaded_callbacks or {})

        ctx = self.raw_api.step_session(
            str(session_id),
            fill=normalized_fill,
            signal=(dict(signal) if isinstance(signal, Mapping) else None),
            threaded_callbacks=callback_bag,
        )
        return public_command_receipt_from_ctx_v1(
            ctx,
            operation="step_session",
            session_id=str(session_id),
            accepted=True,
            caps=self.caps,
        )

    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ctx = self.raw_api.undo_last_step(str(session_id))
        return public_command_receipt_from_ctx_v1(
            ctx,
            operation="undo_last_step",
            session_id=str(session_id),
            accepted=True,
            caps=self.caps,
        )

    def redo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ctx = self.raw_api.redo_last_step(str(session_id))
        return public_command_receipt_from_ctx_v1(
            ctx,
            operation="redo_last_step",
            session_id=str(session_id),
            accepted=True,
            caps=self.caps,
        )

    def delete_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        raw = self.raw_api.delete_session(str(session_id))
        self._manifest_call_rows_by_session_id.pop(str(session_id), None)
        return public_delete_receipt_v1(
            raw,
            session_id=str(session_id),
            caps=self.caps,
        )

    def current_report(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ctx = self.raw_api.get_session_context(str(session_id))
        return public_session_report_from_ctx_v1(
            ctx,
            session_id=str(session_id),
            operation="current_report",
            caps=self.caps,
        )

    def outputs_report(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        outputs = self.raw_api.get_outputs(str(session_id))

        if not isinstance(outputs, Mapping):
            raise TypeError(
                "raw get_outputs returned "
                f"{type(outputs).__name__}, expected mapping"
            )

        return _outputs_report_from_outputs_v1(
            outputs,
            session_id=str(session_id),
            caps=self.caps,
        )

    def progress_report(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        return self.current_report(str(session_id))

    def query_session(
        self,
        session_id: str,
        *,
        query_kind: str,
        query: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Explicit bounded G* query endpoint.

        query_kind values:
            current_report
            outputs_report
            runtime_write_index_summary
            runtime_writes
            program_trace_table
        """
        q = dict(query or {})
        kind = str(query_kind or "").strip()

        if kind == "current_report":
            return _strip_forbidden_public_keys(
                {
                    "kind": KIND_SESSION_QUERY_RESULT_V1,
                    "v": PUBLIC_API_VERSION_V1,
                    "ok": True,
                    "session_id": str(session_id),
                    "query_kind": kind,
                    "result": self.current_report(str(session_id)),
                },
                caps=self.caps,
            )

        if kind == "outputs_report":
            return _strip_forbidden_public_keys(
                {
                    "kind": KIND_SESSION_QUERY_RESULT_V1,
                    "v": PUBLIC_API_VERSION_V1,
                    "ok": True,
                    "session_id": str(session_id),
                    "query_kind": kind,
                    "result": self.outputs_report(str(session_id)),
                },
                caps=self.caps,
            )

        if kind in {
            "runtime_writes",
            "runtime_write_index_summary",
            "program_trace_table",
        }:
            snapshot = self.raw_api.export_session_snapshot(str(session_id))

            if not isinstance(snapshot, Mapping):
                raise TypeError(
                    "raw export_session_snapshot returned "
                    f"{type(snapshot).__name__}, expected mapping"
                )

            state = snapshot.get("state")
            if not isinstance(state, Mapping):
                state = {}

            if kind == "runtime_write_index_summary":
                result = get_runtime_write_index_summary(state)

            elif kind == "runtime_writes":
                result = query_runtime_writes(
                    state,
                    _normalize_runtime_write_query_v1(q, caps=self.caps),
                )

            else:
                outputs = self.raw_api.get_outputs(str(session_id))
                if not isinstance(outputs, Mapping):
                    outputs = {}

                raw_manifest_rows = self._manifest_call_rows_by_session_id.get(
                    str(session_id),
                    [],
                )

                include_fn_args = bool(q.get("include_fn_args", False))
                manifest_rows: list[Dict[str, Any]] = []
                for row in raw_manifest_rows:
                    copied = dict(row)
                    if not include_fn_args:
                        copied.pop("fn_args", None)
                    manifest_rows.append(copied)

                result = _program_trace_table_v1(
                    session_id=str(session_id),
                    manifest_rows=manifest_rows,
                    outputs=outputs,
                    snapshot=snapshot,
                    query=q,
                    caps=self.caps,
                )

            return _strip_forbidden_public_keys(
                {
                    "kind": KIND_SESSION_QUERY_RESULT_V1,
                    "v": PUBLIC_API_VERSION_V1,
                    "ok": True,
                    "session_id": str(session_id),
                    "query_kind": kind,
                    "result": result,
                },
                caps=self.caps,
            )

        raise ValueError(
            "unknown query_kind for public session query: "
            f"{kind!r}"
        )

    def run_action_scripted_program_start_to_finish(
        self,
        *,
        manifest: Any,
        script: Any,
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Any = None,
        keep_step_reports: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a session, run a script, and return a bounded script report.
        """
        del keep_step_reports

        from _thinkengine.runme.runme_offline_debug_against_actionscript import (
            normalize_offline_script_spec_v1,
            run_session_against_script_headless,
        )

        script_config, script_actions = normalize_offline_script_spec_v1(script)

        result = run_session_against_script_headless(
            manifest=manifest,
            initial_parameter_overrides=dict(initial_parameter_overrides or {}),
            session_metadata=_merge_public_session_storage_policy_v1(
                session_metadata,
                caps=self.caps,
            ),
            script={
                "config": {
                    "use_controller": script_config.use_controller,
                },
                "actions": script_actions,
            },
            api=self.raw_api,
            keep_full_history=False,
        )

        last_ctx = result.ctx if isinstance(result.ctx, Mapping) else {}
        action_summary = _public_script_action_summary_v1(
            getattr(result, "history", None)
        )

        sid = str(result.session_id)
        if sid and sid not in self._manifest_call_rows_by_session_id:
            self._manifest_call_rows_by_session_id[sid] = (
                _compact_manifest_call_rows_v1(
                    manifest,
                    include_fn_args=True,
                )
            )

        out = {
            "kind": KIND_SCRIPT_RUN_REPORT_V1,
            "v": PUBLIC_API_VERSION_V1,
            "ok": True,
            "operation": "run_action_scripted_program_start_to_finish",
            "scripting_path": "start_to_finish",
            "session_scope": "new_session",
            "session_id": sid,
            "script_config": {
                "use_controller": bool(script_config.use_controller),
            },
            "last": public_session_report_from_ctx_v1(
                last_ctx,
                session_id=sid,
                operation="run_action_scripted_program_start_to_finish",
                caps=self.caps,
            ),
            "script_count": len(script_actions),
            "slim_result": True,
            **action_summary,
        }

        return _strip_forbidden_public_keys(out, caps=self.caps)

    def run_action_scripted_program_from_program_start_to_finish(
        self,
        *,
        program: Any,
        program_language: str,
        script: Any,
        initial_parameter_overrides: Optional[Dict[str, Any]] = None,
        session_metadata: Any = None,
        require_completion: bool = True,
        delete_after: bool = True,
    ) -> Dict[str, Any]:
        """
        Highest-language one-shot offline script run.

        This is public scripting path Y:

            program_language + program + script
                -> create a transient session through the normal program lowerer
                -> run the same action-script grammar used by existing sessions
                -> capture bounded final report and bounded outputs report
                -> optionally delete the transient session before returning

        Public law:
            - no raw ctx;
            - no raw history;
            - no raw snapshot/state/program_map/multiframespec/html;
            - script items are passed through unchanged to the lower script
              runner, so newly recognized script action types do not require
              Django/service rewrites.

        Use run_action_script_onto_existing_session(...) instead when the caller
        wants a reusable/persistent session after the script completes.
        """
        from _thinkengine.runme.runme_offline_debug_against_actionscript import (
            normalize_offline_script_spec_v1,
        )

        script_config, script_actions = normalize_offline_script_spec_v1(script)
        script_spec = {
            "config": {
                "use_controller": script_config.use_controller,
            },
            "actions": [
                dict(item)
                for item in script_actions
            ],
        }

        created = self.create_session_from_program(
            program=program,
            program_language=program_language,
            initial_parameter_overrides=dict(initial_parameter_overrides or {}),
            session_metadata=session_metadata,
        )
        sid = str(created["session_id"])

        public_report = self.run_action_script_onto_existing_session(
            sid,
            script=script_spec,
            require_completion=require_completion,
        )

        outputs_report: Dict[str, Any] | None = None
        outputs_error: str | None = None
        try:
            outputs_report = self.outputs_report(sid)
        except (
            AssertionError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            outputs_error = str(exc)
            outputs_report = {
                "kind": KIND_SESSION_REPORT_V1,
                "v": PUBLIC_API_VERSION_V1,
                "ok": False,
                "session_id": sid,
                "operation": "outputs_report",
                "error": outputs_error,
            }

        cleanup_report: Dict[str, Any] | None = None
        cleanup_error: str | None = None
        if delete_after:
            try:
                cleanup_report = self.delete_session(sid)
            except (
                AssertionError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                cleanup_error = str(exc)
                cleanup_report = {
                    "kind": KIND_COMMAND_RECEIPT_V1,
                    "v": PUBLIC_API_VERSION_V1,
                    "ok": False,
                    "operation": "delete_session",
                    "session_id": sid,
                    "error": cleanup_error,
                }

        base_ok = bool(public_report.get("ok"))
        cleanup_ok = (
            True
            if cleanup_report is None
            else bool(cleanup_report.get("ok"))
        )
        outputs_ok = (
            True
            if outputs_report is None
            else bool(outputs_report.get("ok", True))
        )

        error = (
            public_report.get("error")
            or outputs_error
            or cleanup_error
        )

        out = {
            "kind": KIND_SCRIPT_RUN_REPORT_V1,
            "v": PUBLIC_API_VERSION_V1,
            "ok": bool(base_ok and cleanup_ok and outputs_ok),
            "operation": (
                "run_action_scripted_program_from_program_start_to_finish"
            ),
            "scripting_path": "start_to_finish",
            "session_scope": "transient_session",
            "session_id": sid,
            "script_config": {
                "use_controller": bool(script_config.use_controller),
            },
            "last": public_report.get("last"),
            "outputs_report": outputs_report,
            "script_count": len(script_actions),
            "steps_executed": int(public_report.get("steps_executed") or 0),
            "history_count": int(public_report.get("history_count") or 0),
            "actions": dict(public_report.get("actions") or {}),
            "modes": dict(public_report.get("modes") or {}),
            "first_actions": list(public_report.get("first_actions") or []),
            "last_actions": list(public_report.get("last_actions") or []),
            "reached_completion": bool(public_report.get("reached_completion")),
            "error": error,
            "slim_result": True,
            "ephemeral_session": bool(delete_after),
            "cleanup_report": cleanup_report,
            "public_report": public_report,
        }

        return _strip_forbidden_public_keys(out, caps=self.caps)

    def run_action_script_onto_existing_session(
        self,
        session_id: str,
        *,
        script: Any,
        require_completion: bool = False,
    ) -> Dict[str, Any]:
        """
        Run a script against an existing session and return bounded G.

        Public law:
            - never expose raw result.ctx;
            - never expose raw result.history rows;
            - never expose raw multiframespec/globals/snapshot/html;
            - return final public report plus bounded action-count metadata.
        """
        from _thinkengine.runme.runme_offline_debug_against_actionscript import (
            SessionProgramScriptedHeadlessRunner,
            normalize_offline_script_spec_v1,
        )

        sid = str(session_id)
        script_config, script_actions = normalize_offline_script_spec_v1(script)

        runner = SessionProgramScriptedHeadlessRunner(
            sid,
            api=self.raw_api,
            keep_full_history=False,
            use_controller=script_config.use_controller,
        )

        try:
            result = runner.run_script(
                {
                    "config": {
                        "use_controller": script_config.use_controller,
                    },
                    "actions": script_actions,
                }
            )
        except (
            AssertionError,
            KeyError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            try:
                final_ctx = self.raw_api.get_session_context(sid)
            except Exception:
                final_ctx = {}

            out = {
                "kind": KIND_SCRIPT_RUN_REPORT_V1,
                "v": PUBLIC_API_VERSION_V1,
                "ok": False,
                "operation": "run_action_script_onto_existing_session",
                "scripting_path": "existing_session",
                "session_scope": "existing_session",
                "session_id": sid,
                "script_config": {
                    "use_controller": bool(script_config.use_controller),
                },
                "last": public_session_report_from_ctx_v1(
                    final_ctx if isinstance(final_ctx, Mapping) else {},
                    session_id=sid,
                    operation="run_action_script_onto_existing_session",
                    caps=self.caps,
                ),
                "script_count": len(script_actions),
                "steps_executed": 0,
                "reached_completion": False,
                "error": str(exc),
                "slim_result": True,
                **_public_script_action_summary_v1(
                    getattr(runner, "history", None)
                ),
            }
            return _strip_forbidden_public_keys(out, caps=self.caps)

        last_ctx = result.ctx if isinstance(result.ctx, Mapping) else {}
        reached_completion = str(last_ctx.get("kind") or "") == "ATCOMPLETION"

        ok = True
        error: str | None = None
        if require_completion and not reached_completion:
            ok = False
            error = "script did not reach ATCOMPLETION"

        out = {
            "kind": KIND_SCRIPT_RUN_REPORT_V1,
            "v": PUBLIC_API_VERSION_V1,
            "ok": ok,
            "operation": "run_action_script_onto_existing_session",
            "scripting_path": "existing_session",
            "session_scope": "existing_session",
            "session_id": sid,
            "script_config": {
                "use_controller": bool(script_config.use_controller),
            },
            "last": public_session_report_from_ctx_v1(
                last_ctx,
                session_id=sid,
                operation="run_action_script_onto_existing_session",
                caps=self.caps,
            ),
            "script_count": len(script_actions),
            "steps_executed": len(list(result.history or [])),
            "reached_completion": reached_completion,
            "error": error,
            "slim_result": True,
            **_public_script_action_summary_v1(
                getattr(result, "history", None)
            ),
        }
        return _strip_forbidden_public_keys(out, caps=self.caps)


_PUBLIC_SESSION_API: Optional[PublicSessionAPI] = None


def get_public_session_api(
    *,
    raw_api: Optional["AbstractSessionAPI"] = None,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> PublicSessionAPI:
    """
    Return the process-local bounded public API.

    Pass raw_api or caps to get a fresh wrapper instead of the singleton.
    """
    global _PUBLIC_SESSION_API

    if raw_api is not None or caps is not None:
        return PublicSessionAPI(
            raw_api=raw_api or get_concrete_session_api(),
            caps=_coerce_public_caps_v1(caps),
        )

    if _PUBLIC_SESSION_API is None:
        _PUBLIC_SESSION_API = PublicSessionAPI(
            raw_api=get_concrete_session_api(),
            caps=PublicSessionCaps(),
        )

    return _PUBLIC_SESSION_API


__all__ = [
    "ABSOLUTE_QUERY_MAX_RESULTS_V1",
    "DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1",
    "DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1",
    "DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1",
    "DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1",
    "DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1",
    "DEFAULT_QUERY_MAX_RESULTS_V1",
    "DEFAULT_TRACE_MAX_RESULTS_V1",
    "DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1",
    "DEFAULT_REDO_MAX_DEPTH_V1",
    "DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1",
    "DEFAULT_FRONTEND_INCLUDE_CTX_V1",
    "KIND_COMMAND_RECEIPT_V1",
    "KIND_PROGRAM_TRACE_TABLE_V1",
    "KIND_SCRIPT_RUN_REPORT_V1",
    "KIND_SESSION_QUERY_RESULT_V1",
    "KIND_SESSION_REPORT_V1",
    "PUBLIC_API_VERSION_V1",
    "register_step_fn",
    "PublicSessionAPI",
    "PublicSessionCaps",
    "get_public_session_api",
    "public_command_receipt_from_ctx_v1",
    "public_create_receipt_v1",
    "public_delete_receipt_v1",
    "public_session_report_from_ctx_v1",
]