from __future__ import annotations

"""
Shared public vocabulary for the bounded session façade.

This file is intentionally boring:

- public API version;
- public envelope kind strings;
- default public caps;
- the PublicSessionCaps dataclass;
- forbidden/raw container names used by sanitizers.

It has no raw session API dependency and no stepping/query behavior.
"""

from dataclasses import dataclass
from typing import Any


PUBLIC_API_VERSION_V1 = 1

KIND_COMMAND_RECEIPT_V1 = "session_command_receipt_v1"
KIND_SESSION_REPORT_V1 = "session_report_v1"
KIND_SESSION_QUERY_RESULT_V1 = "session_query_result_v1"
KIND_SCRIPT_RUN_REPORT_V1 = "session_script_run_report_v1"
KIND_PROGRAM_TRACE_TABLE_V1 = "program_trace_table_v1"

DEFAULT_QUERY_MAX_RESULTS_V1 = 64
ABSOLUTE_QUERY_MAX_RESULTS_V1 = 512
DEFAULT_TRACE_MAX_RESULTS_V1 = 128

DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1 = 128
DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1 = 128

DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1 = ABSOLUTE_QUERY_MAX_RESULTS_V1
DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1 = 256
DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1 = 240

DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1 = 32
DEFAULT_REDO_MAX_DEPTH_V1 = 64
DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1 = 200_000

DEFAULT_FRONTEND_INCLUDE_CTX_V1 = False


_PUBLIC_FORBIDDEN_CONTAINER_KEYS_V1 = frozenset(
    {
        "ctx",
        "raw_ctx",
        "context",
        "multiframespec",
        "program_map",
        "snapshot",
        "state",
        "globals",
        "outputs",
        "form_prefills",
        "form_fills",
        "forms_emitted",
        "datum_widget_fills",
        "datum_widget_decls",
        "frames",
        "datums",
        "merged_fills",
        "raw_merged_fills",
        "html",
        "rendered",
        "dom",
    }
)

_PUBLIC_ALLOWED_METADATA_PARENTS_V1 = frozenset(
    {
        "counts",
        "keys",
        "previews",
        "summary",
        "result",
        "truncated_keys",
    }
)


def _nonnegative_int_or_default_v1(value: Any, default: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)
    return max(0, out)


@dataclass(frozen=True)
class PublicSessionCaps:
    """
    Per-wrapper public caps.

    Apps usually do not need to set this. Use it when embedding the API in a
    service that wants smaller previews, stricter query caps, or different
    public sanitizer limits.
    """

    default_query_max_results: int = DEFAULT_QUERY_MAX_RESULTS_V1
    absolute_query_max_results: int = ABSOLUTE_QUERY_MAX_RESULTS_V1
    default_trace_max_results: int = DEFAULT_TRACE_MAX_RESULTS_V1

    output_key_preview_limit: int = DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1
    datum_widgets_on_this_span_preview_limit: int = (
        DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1
    )

    public_sanitizer_list_limit: int = DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1
    public_sanitizer_dict_limit: int = DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1
    public_sanitizer_string_limit: int = DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1

    forms_emitted_snapshot_window: int = DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1
    redo_max_depth: int = DEFAULT_REDO_MAX_DEPTH_V1
    redo_action_max_payload_chars: int = DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1

    def __post_init__(self) -> None:
        def pos(value: Any, default: int) -> int:
            try:
                out = int(value)
            except Exception:
                return int(default)
            return out if out > 0 else int(default)

        absolute = pos(
            self.absolute_query_max_results,
            ABSOLUTE_QUERY_MAX_RESULTS_V1,
        )

        object.__setattr__(self, "absolute_query_max_results", absolute)
        object.__setattr__(
            self,
            "default_query_max_results",
            min(
                pos(self.default_query_max_results, DEFAULT_QUERY_MAX_RESULTS_V1),
                absolute,
            ),
        )
        object.__setattr__(
            self,
            "default_trace_max_results",
            min(
                pos(self.default_trace_max_results, DEFAULT_TRACE_MAX_RESULTS_V1),
                absolute,
            ),
        )
        object.__setattr__(
            self,
            "output_key_preview_limit",
            pos(
                self.output_key_preview_limit,
                DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
            ),
        )
        object.__setattr__(
            self,
            "datum_widgets_on_this_span_preview_limit",
            pos(
                self.datum_widgets_on_this_span_preview_limit,
                DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
            ),
        )
        object.__setattr__(
            self,
            "public_sanitizer_list_limit",
            max(
                pos(
                    self.public_sanitizer_list_limit,
                    DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1,
                ),
                absolute,
            ),
        )
        object.__setattr__(
            self,
            "public_sanitizer_dict_limit",
            pos(
                self.public_sanitizer_dict_limit,
                DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1,
            ),
        )
        object.__setattr__(
            self,
            "public_sanitizer_string_limit",
            pos(
                self.public_sanitizer_string_limit,
                DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1,
            ),
        )
        object.__setattr__(
            self,
            "forms_emitted_snapshot_window",
            _nonnegative_int_or_default_v1(
                self.forms_emitted_snapshot_window,
                DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1,
            ),
        )
        object.__setattr__(
            self,
            "redo_max_depth",
            _nonnegative_int_or_default_v1(
                self.redo_max_depth,
                DEFAULT_REDO_MAX_DEPTH_V1,
            ),
        )
        object.__setattr__(
            self,
            "redo_action_max_payload_chars",
            _nonnegative_int_or_default_v1(
                self.redo_action_max_payload_chars,
                DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1,
            ),
        )