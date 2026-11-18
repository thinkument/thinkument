from __future__ import annotations

"""
Thinkument bounded public interactive session API for app-table programs.

You are here because you are writing an app-table program, creating a
Thinkument session from it, stepping that session with user/app fills, and
reading bounded reports/results back.

Use this module as the interactive app-facing façade

The raw engine can internally build large ctx/snapshot/output/program/UI
structures. This façade deliberately does not expose those by default. It
returns small, stable public envelopes that are safe for apps, services, tests,
and developer tooling.

Return envelopes
----------------

S = session_command_receipt_v1
    Tiny command/mutation receipt.

G = session_report_v1
    Tiny bounded session/output/progress report.

G* = session_query_result_v1
    Explicit bounded query result for developer inspection.

Endpoint map
------------

| Endpoint | Kind | Use it when | Main inputs | Main output |
| --- | --- | --- | --- | --- |
| register_step_fn | authoring | Register Python step fns used by app-table manifests. | step fn name/function | Registry side effect |
| create_session | S | Start a session from an app-table manifest. | manifest, initial_parameter_overrides?, session_metadata? | session_id receipt |
| create_session_from_program | S | Start from a higher-level source program that lowers to app-table. | program, program_language, initial_parameter_overrides?, session_metadata? | session_id receipt |
| step_session | S | Advance to the next durable public stop, optionally submitting fills/signals. | session_id, fill?, signal? | current stop receipt |
| undo_last_step | S | Rewind one durable public action. | session_id | current stop receipt |
| redo_last_step | S | Replay one undone durable public action. | session_id | current stop receipt |
| delete_session | S | Delete the session from the public API/repo. | session_id | delete receipt |
| current_report | G | Ask “where is this session now?” | session_id | cursor, pending span/datum metadata, counts |
| progress_report | G | Alias for current_report for progress-oriented callers. | session_id | current report |
| outputs_report | G | Ask “what output buckets/keys exist?” without raw values. | session_id | counts and bounded key previews |
| query_session(current_report) | G* | Wrap current_report in the query envelope. | session_id, query_kind | result.current_report |
| query_session(outputs_report) | G* | Wrap outputs_report in the query envelope. | session_id, query_kind | result.outputs_report |
| query_session(runtime_write_index_summary) | G* | See what indexed write facts exist. | session_id | write-kind/count summary |
| query_session(runtime_writes) | G* | Retrieve bounded write rows; opt into values explicitly. | write_kinds?, include_values?, max_results? | capped write rows |
| query_session(program_trace_table) | G* | Read a compact developer trace: app calls, spans, datum IO, Q windows. | include_fn_args?, include_datum_values?, include_q_lifecycle?, include_topology?, max_results? | capped table rows |


|
Fill grammar
------------

step_session accepts ordinary JSON fill mappings. Dotted datum/micro keys are
normalized at the public boundary:

    step_session(sid, fill={"NAME.first": "Ada", "NAME.last": "Lovelace"})
    step_session(sid, fill={"AGE.value": 36})

Default safety law
------------------

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

Higher interactive apps should import this module, not concrete engine modules.
"""

from typing import Any, Dict, Mapping, Optional

from _thinkengine.runme_optimized_queryable._core import (
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
    PublicSessionAPI,
    PublicSessionCaps,
    get_public_session_api,
    public_command_receipt_from_ctx_v1,
    public_create_receipt_v1,
    public_delete_receipt_v1,
    public_session_report_from_ctx_v1,
    register_step_fn,
)


def create_session(
    *,
    manifest: Any,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Any = None,
) -> Dict[str, Any]:
    """
    Create a session from an app-table manifest.

    Returns S with session_id. Does not return program_map or raw ctx.
    """
    return get_public_session_api().create_session(
        manifest=manifest,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
    )


def create_session_from_program(
    *,
    program: Any,
    program_language: str,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Any = None,
) -> Dict[str, Any]:
    """
    Lower a source program to app-table and create a bounded public session.
    """
    return get_public_session_api().create_session_from_program(
        program=program,
        program_language=program_language,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
    )


def step_session(
    session_id: str,
    *,
    fill: Optional[Dict[str, Any]] = None,
    signal: Optional[Dict[str, Any]] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Advance to the next durable public stop.

    fill may use datum-level or dotted datum.micro keys.
    """
    return get_public_session_api().step_session(
        session_id,
        fill=fill,
        signal=signal,
        threaded_callbacks=threaded_callbacks,
    )


def undo_last_step(
    session_id: str,
) -> Dict[str, Any]:
    """
    Undo one durable public action.
    """
    return get_public_session_api().undo_last_step(session_id)


def redo_last_step(
    session_id: str,
) -> Dict[str, Any]:
    """
    Redo one undone durable action.
    """
    return get_public_session_api().redo_last_step(session_id)


def current_report(
    session_id: str,
) -> Dict[str, Any]:
    """
    Return bounded G for the current session stop.
    """
    return get_public_session_api().current_report(session_id)


def outputs_report(
    session_id: str,
) -> Dict[str, Any]:
    """
    Return bounded G for output bucket counts and key previews.
    """
    return get_public_session_api().outputs_report(session_id)


def progress_report(
    session_id: str,
) -> Dict[str, Any]:
    """
    Alias for current_report.
    """
    return get_public_session_api().progress_report(session_id)


def query_session(
    session_id: str,
    *,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run an explicit bounded G* query.

    Supported query_kind:
        current_report
        outputs_report
        runtime_write_index_summary
        runtime_writes
        program_trace_table
    """
    return get_public_session_api().query_session(
        session_id,
        query_kind=query_kind,
        query=query,
    )


def delete_session(
    session_id: str,
) -> Dict[str, Any]:
    """
    Delete a public session.
    """
    return get_public_session_api().delete_session(session_id)


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
    "current_report",
    "create_session",
    "create_session_from_program",
    "delete_session",
    "get_public_session_api",
    "outputs_report",
    "progress_report",
    "public_command_receipt_from_ctx_v1",
    "public_create_receipt_v1",
    "public_delete_receipt_v1",
    "public_session_report_from_ctx_v1",
    "query_session",
    "redo_last_step",
    "step_session",
    "undo_last_step",
]