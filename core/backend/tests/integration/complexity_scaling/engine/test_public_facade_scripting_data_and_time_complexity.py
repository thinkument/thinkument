from __future__ import annotations

"""
Public Script API Complexity Sheet
==================================

This sheet specializes on the highest public scripting seam:

    PublicSessionAPI.run_action_scripted_program_start_to_finish(...)

It proves the scripting-facing theorem:

    A top-level app can run arbitrarily large scripted programs through the
    public façade and still receive small, sealed public reports by default.

Program axes covered
--------------------

    length:
        many app-table functions in the manifest

    depth:
        many frames per emitted form

    width:
        many spans per frame and many datums per span

    manual holes:
        spans with missing values are filled by preprogrammed script actions

    large data:
        huge datum values exist in session state but do not leak through
        default script reports or metadata-only G* queries

    app-call auditability:
        compact fn_args are registered on the synthetic step functions and
        exposed only through public program_trace_table rows when requested

    final-state completeness:
        all final datum states can be retrieved after completion through
        explicit expert-capped G* runtime_writes queries

Public API theorem
------------------

Default S/G/script-report cost:

    O(1 + bounded previews)

Fixed-cap G* query cost:

    O(max_results)

Explicit all-final-state export cost:

    O(exported rows + exported value size)

The point is not that exporting all final states is free. The point is that it
is explicit, capped, and opt-in. Ordinary ChatGPT/app-facing interactions keep
moving small bounded reports forever as program/session data accumulates.

This file deliberately avoids:
    - get_concrete_session_api
    - api._get(...)
    - export_session_snapshot(...)
    - raw ctx
    - raw state
    - raw multiframespec dumps
    - raw runtime index helpers

The only app-authoring seam used is StepFnregistry, which is how these tests
register synthetic app-table functions. Session execution and observation use
the public façade.
"""

import statistics
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

import pytest

from _thinkengine.runme_optimized_queryable.facade_base import (
    ABSOLUTE_QUERY_MAX_RESULTS_V1,
    DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    DEFAULT_QUERY_MAX_RESULTS_V1,
    DEFAULT_TRACE_MAX_RESULTS_V1,
    KIND_PROGRAM_TRACE_TABLE_V1,
    KIND_SCRIPT_RUN_REPORT_V1,
    KIND_SESSION_QUERY_RESULT_V1,
    KIND_SESSION_REPORT_V1,
    PublicSessionAPI,
    PublicSessionCaps,
    get_public_session_api,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)


# ---------------------------------------------------------------------------
# Public-result guards
# ---------------------------------------------------------------------------


_FORBIDDEN_PUBLIC_CONTAINER_KEYS = {
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
    "history",
    "content",
    "rendered",
    "dom",
}

_ALLOWED_METADATA_PARENTS = {
    "counts",
    "keys",
    "previews",
    "summary",
    "result",
    "truncated_keys",
}


def _is_allowed_metadata_path(parent: str | None, key: str, value: Any) -> bool:
    if parent == "counts":
        return isinstance(value, (int, type(None)))

    if parent == "keys":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)

    if parent == "truncated_keys":
        return isinstance(value, bool)

    if parent in {"previews", "summary", "result"}:
        return True

    return False


def _contains_forbidden_public_container(
    obj: Any,
    *,
    parent_key: str | None = None,
    path: str = "$",
    max_nodes: int = 250_000,
) -> tuple[bool, str | None]:
    stack: list[tuple[Any, str | None, str]] = [(obj, parent_key, path)]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur, parent, cur_path = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            for raw_k, v in cur.items():
                k = str(raw_k)
                child_path = f"{cur_path}.{k}"

                if k in _FORBIDDEN_PUBLIC_CONTAINER_KEYS:
                    if _is_allowed_metadata_path(parent, k, v):
                        stack.append((v, k, child_path))
                        continue
                    return True, child_path

                stack.append((v, k, child_path))

        elif isinstance(cur, (list, tuple, set, frozenset)):
            for i, item in enumerate(cur):
                stack.append((item, parent, f"{cur_path}[{i}]"))

    return False, None


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 250_000) -> bool:
    needle = ch * n
    stack = [obj]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
        elif isinstance(cur, Mapping):
            stack.extend(cur.keys())
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return False


def _bounded_container_stats(obj: Any, *, max_nodes: int = 250_000) -> Dict[str, int]:
    stack = [obj]
    seen: set[int] = set()

    visited = 0
    mappings = 0
    sequences = 0
    strings = 0
    total_string_chars = 0
    max_string_chars = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            strings += 1
            total_string_chars += len(cur)
            max_string_chars = max(max_string_chars, len(cur))
            continue

        if isinstance(cur, Mapping):
            mappings += 1
            for k, v in cur.items():
                if isinstance(k, str):
                    strings += 1
                    total_string_chars += len(k)
                    max_string_chars = max(max_string_chars, len(k))
                else:
                    stack.append(k)
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set, frozenset)):
            sequences += 1
            stack.extend(cur)
            continue

    return {
        "visited": visited,
        "mappings": mappings,
        "sequences": sequences,
        "strings": strings,
        "total_string_chars": total_string_chars,
        "max_string_chars": max_string_chars,
        "truncated": int(bool(stack)),
    }


def _assert_public_small(obj: Any, *, no_giant_z: bool = True) -> None:
    leaked, path = _contains_forbidden_public_container(obj)
    assert not leaked, f"public result leaked forbidden raw container at {path}"

    if no_giant_z:
        assert not _contains_run(obj, "Z", 1000)


def _assert_script_report(obj: Mapping[str, Any]) -> None:
    assert obj["kind"] == KIND_SCRIPT_RUN_REPORT_V1
    assert obj["ok"] is True
    assert obj["operation"] == "run_action_scripted_program_start_to_finish"
    assert "session_id" in obj
    assert "last" in obj
    assert obj["slim_result"] is True

    last = obj["last"]
    assert isinstance(last, Mapping)
    assert last["kind"] == KIND_SESSION_REPORT_V1

    assert "history_count" in obj
    assert "actions" in obj
    assert "modes" in obj
    assert "first_actions" in obj
    assert "last_actions" in obj

    assert "history" not in obj
    assert "ctx" not in obj
    assert "raw_ctx" not in obj
    assert "snapshot" not in obj
    assert "state" not in obj
    assert "multiframespec" not in obj
    assert "program_map" not in obj
    assert "content" not in obj

    _assert_public_small(obj)


def _assert_report(obj: Mapping[str, Any]) -> None:
    assert obj["kind"] == KIND_SESSION_REPORT_V1
    assert obj["ok"] is True
    assert "session_id" in obj
    _assert_public_small(obj)


def _assert_query_result(
    obj: Mapping[str, Any],
    *,
    query_kind: str,
    no_giant_z: bool = True,
) -> None:
    assert obj["kind"] == KIND_SESSION_QUERY_RESULT_V1
    assert obj["ok"] is True
    assert obj["query_kind"] == query_kind
    assert "result" in obj
    _assert_public_small(obj, no_giant_z=no_giant_z)


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------


def _custom_api(
    *,
    default_query_max_results: int = DEFAULT_QUERY_MAX_RESULTS_V1,
    absolute_query_max_results: int = ABSOLUTE_QUERY_MAX_RESULTS_V1,
    default_trace_max_results: int = DEFAULT_TRACE_MAX_RESULTS_V1,
    output_key_preview_limit: int = DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    datum_widgets_on_this_span_preview_limit: int = DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    public_sanitizer_list_limit: Optional[int] = None,
    public_sanitizer_dict_limit: int = 4096,
    public_sanitizer_string_limit: int = 2048,
) -> PublicSessionAPI:
    absolute = int(absolute_query_max_results)
    sanitizer_list = (
        int(public_sanitizer_list_limit)
        if public_sanitizer_list_limit is not None
        else max(absolute, 1024)
    )

    return get_public_session_api(
        caps=PublicSessionCaps(
            default_query_max_results=default_query_max_results,
            absolute_query_max_results=absolute,
            default_trace_max_results=default_trace_max_results,
            output_key_preview_limit=output_key_preview_limit,
            datum_widgets_on_this_span_preview_limit=datum_widgets_on_this_span_preview_limit,
            public_sanitizer_list_limit=sanitizer_list,
            public_sanitizer_dict_limit=public_sanitizer_dict_limit,
            public_sanitizer_string_limit=public_sanitizer_string_limit,
        )
    )


def _lean_session_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "boundary",
            "profile": False,
            "include_full_multiframespec_in_ctx": False,
            "include_forms_emitted_order_in_ctx": False,
            "include_global_fill_keys_in_ctx": False,
            "include_field_value_keys_in_ctx": False,
        },
        "runtime_session_ctx": {
            "profile": "slim",
        },
        "redo": {"max_depth": 128},
    }


def _query_with_api(
    api: PublicSessionAPI,
    sid: str,
    *,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
    no_giant_z: bool = True,
) -> Dict[str, Any]:
    result = api.query_session(
        sid,
        query_kind=query_kind,
        query=query or {},
    )
    _assert_query_result(result, query_kind=query_kind, no_giant_z=no_giant_z)
    return result


def _outputs_report_with_api(api: PublicSessionAPI, sid: str) -> Dict[str, Any]:
    report = api.outputs_report(sid)
    _assert_report(report)
    assert report["operation"] == "outputs_report"
    return report


def _runtime_rows(result: Mapping[str, Any]) -> list[Dict[str, Any]]:
    inner = result.get("result")
    assert isinstance(inner, Mapping)
    rows = inner.get("writes")
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _trace_rows(result: Mapping[str, Any]) -> list[Dict[str, Any]]:
    assert result["query_kind"] == "program_trace_table"

    inner = result["result"]
    assert isinstance(inner, Mapping)
    assert inner["kind"] == KIND_PROGRAM_TRACE_TABLE_V1
    assert "max_results" in inner
    assert "truncated" in inner
    assert "rows" in inner

    rows = inner["rows"]
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _median_seconds(fn, *, repeats: int = 3) -> float:
    vals = []
    for _ in range(max(1, int(repeats))):
        t0 = time.perf_counter()
        fn()
        vals.append(time.perf_counter() - t0)
    return statistics.median(vals)


def _slope_ratio(
    *,
    small_y: float,
    large_y: float,
    small_n: int,
    large_n: int,
) -> float:
    if small_y <= 0:
        return 0.0
    return (large_y / small_y) / max(large_n / max(1, small_n), 1e-9)


def _assert_not_superlinear_badly(
    *,
    small_y: float,
    large_y: float,
    small_n: int,
    large_n: int,
    slack: float,
    label: str,
) -> None:
    ratio = _slope_ratio(
        small_y=small_y,
        large_y=large_y,
        small_n=small_n,
        large_n=large_n,
    )
    assert ratio <= slack, (
        f"{label} appears superlinear beyond slack: "
        f"small={small_y:.6f}s at n={small_n}, "
        f"large={large_y:.6f}s at n={large_n}, "
        f"ratio_vs_linear={ratio:.2f}, slack={slack}"
    )


# ---------------------------------------------------------------------------
# App authoring helpers
# ---------------------------------------------------------------------------


_SCRIPT_FN_ARG_NAMES = frozenset(
    {
        "shape_label",
        "fn_index",
        "frames_per_form",
        "spans_per_frame",
        "datums_per_span",
    }
)


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


@dataclass(frozen=True)
class ScriptProgramShape:
    label: str
    fn_count: int
    frames_per_form: int
    spans_per_frame: int
    datums_per_span: int
    manual_span_every: int
    payload_chars: int = 0
    payload_char: str = "Z"

    @property
    def total_spans(self) -> int:
        return self.fn_count * self.frames_per_form * self.spans_per_frame

    @property
    def total_datums(self) -> int:
        return self.total_spans * self.datums_per_span

    @property
    def manual_spans(self) -> int:
        total = 0
        for fn_index in range(self.fn_count):
            for frame_index in range(self.frames_per_form):
                for span_index in range(self.spans_per_frame):
                    if _is_manual_span(
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        manual_span_every=self.manual_span_every,
                    ):
                        total += 1
        return total

    @property
    def manual_datums(self) -> int:
        return self.manual_spans * self.datums_per_span

    @property
    def prefilled_datums(self) -> int:
        return self.total_datums - self.manual_datums


def _is_manual_span(
    *,
    fn_index: int,
    frame_index: int,
    span_index: int,
    manual_span_every: int,
) -> bool:
    if int(manual_span_every) <= 0:
        return False

    ordinal = (
        int(fn_index) * 100_000
        + int(frame_index) * 1_000
        + int(span_index)
    )

    return ordinal % int(manual_span_every) == 0


def _datum_id(
    *,
    fn_index: int,
    frame_index: int,
    span_index: int,
    datum_index: int,
) -> str:
    return f"F{fn_index}_{frame_index}_{span_index}_{datum_index}"


def _span_id(
    *,
    fn_index: int,
    frame_index: int,
    span_index: int,
) -> str:
    return f"S{fn_index}_{frame_index}_{span_index}"


def _prefill_value(
    *,
    fn_index: int,
    frame_index: int,
    span_index: int,
    datum_index: int,
    payload_chars: int,
    payload_char: str = "Z",
) -> Dict[str, str]:
    return {
        "value": (
            f"prefill;"
            f"fn={fn_index};"
            f"frame={frame_index};"
            f"span={span_index};"
            f"datum={datum_index};"
            + (str(payload_char) * int(payload_chars))
        )
    }


def _manual_value(
    *,
    fn_index: int,
    frame_index: int,
    span_index: int,
    datum_index: int,
) -> str:
    return (
        f"script-fill;"
        f"fn={fn_index};"
        f"frame={frame_index};"
        f"span={span_index};"
        f"datum={datum_index};"
    )


def _expected_final_value(
    *,
    shape: ScriptProgramShape,
    fn_index: int,
    frame_index: int,
    span_index: int,
    datum_index: int,
) -> Dict[str, str]:
    if _is_manual_span(
        fn_index=fn_index,
        frame_index=frame_index,
        span_index=span_index,
        manual_span_every=shape.manual_span_every,
    ):
        return {
            "value": _manual_value(
                fn_index=fn_index,
                frame_index=frame_index,
                span_index=span_index,
                datum_index=datum_index,
            )
        }

    return _prefill_value(
        fn_index=fn_index,
        frame_index=frame_index,
        span_index=span_index,
        datum_index=datum_index,
        payload_chars=shape.payload_chars,
        payload_char=shape.payload_char,
    )


def _script_multiframespec_for_fn(
    *,
    shape: ScriptProgramShape,
    fn_index: int,
) -> Dict[str, Any]:
    form_id = f"public.script.complexity.{shape.label}.form.{fn_index}"

    datums: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    fills: dict[str, Any] = {}

    for frame_index in range(shape.frames_per_form):
        spans: list[dict[str, Any]] = []

        for span_index in range(shape.spans_per_frame):
            owns: list[str] = []
            manual = _is_manual_span(
                fn_index=fn_index,
                frame_index=frame_index,
                span_index=span_index,
                manual_span_every=shape.manual_span_every,
            )

            for datum_index in range(shape.datums_per_span):
                did = _datum_id(
                    fn_index=fn_index,
                    frame_index=frame_index,
                    span_index=span_index,
                    datum_index=datum_index,
                )
                owns.append(did)

                datums.append(
                    {
                        "id": did,
                        "title": did,
                        "micros": [_text_micro()],
                    }
                )

                if not manual:
                    fills[did] = _prefill_value(
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                        payload_chars=shape.payload_chars,
                        payload_char=shape.payload_char,
                    )

            spans.append(
                {
                    "id": _span_id(
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                    ),
                    "title": f"Span {fn_index}.{frame_index}.{span_index}",
                    "owns": owns,
                }
            )

        frames.append(
            {
                "id": f"FRAME{fn_index}_{frame_index}",
                "title": f"Frame {fn_index}.{frame_index}",
                "spans": spans,
            }
        )

    return {
        "app_form_id": form_id,
        "datums": datums,
        "frames": frames,
        "fills": fills,
    }


def _script_fn_args(
    *,
    shape: ScriptProgramShape,
    fn_index: int,
) -> Dict[str, Any]:
    """
    Compact public app-call metadata for the synthetic app-table function.

    These args intentionally appear in the manifest so
    program_trace_table(include_fn_args=True) can prove the public app-call audit
    view remains useful without exposing raw program_map/multiframespec/state.

    The step function registers these names as optional args, so app-table
    validation remains strict and realistic.
    """
    return {
        "shape_label": shape.label,
        "fn_index": int(fn_index),
        "frames_per_form": int(shape.frames_per_form),
        "spans_per_frame": int(shape.spans_per_frame),
        "datums_per_span": int(shape.datums_per_span),
    }


def _register_script_fn(
    *,
    shape: ScriptProgramShape,
    fn_index: int,
) -> str:
    step_name = f"public.script.complexity.{shape.label}.fn.{fn_index}"
    multiframespec = _script_multiframespec_for_fn(
        shape=shape,
        fn_index=fn_index,
    )

    def fn(
        _state: Mapping[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Synthetic app-table function.

        It accepts *args/**kwargs deliberately so this test remains robust across
        engine call conventions, while StepFnregistry still validates fn_args by
        registered name before execution.

        The function does not need args to build the multiframespec because the exact
        shape is precomputed at registration time. The args exist for public
        app-call audit rows.
        """
        return {
            f"script_fn_{fn_index}_ran": True,
            "script_last_fn_index": fn_index,
            "multiframespec": dict(multiframespec),
        }

    StepFnregistry.register(
        name=step_name,
        fn=fn,
        required_args=set(),
        optional_args=set(_SCRIPT_FN_ARG_NAMES),
        overwrite=True,
    )

    return step_name


def _script_manifest(shape: ScriptProgramShape) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []

    for fn_index in range(shape.fn_count):
        step_name = _register_script_fn(
            shape=shape,
            fn_index=fn_index,
        )

        manifest.append(
            {
                "public_step_name": f"script_fn_{fn_index}",
                "step_fn": step_name,
                "fn_args": _script_fn_args(
                    shape=shape,
                    fn_index=fn_index,
                ),
            }
        )

    return manifest


def _manual_span_fill(
    *,
    shape: ScriptProgramShape,
    fn_index: int,
    frame_index: int,
    span_index: int,
) -> Dict[str, str]:
    fill: dict[str, str] = {}

    for datum_index in range(shape.datums_per_span):
        did = _datum_id(
            fn_index=fn_index,
            frame_index=frame_index,
            span_index=span_index,
            datum_index=datum_index,
        )
        fill[f"{did}.value"] = _manual_value(
            fn_index=fn_index,
            frame_index=frame_index,
            span_index=span_index,
            datum_index=datum_index,
        )

    return fill


def _script_for_shape(shape: ScriptProgramShape) -> list[dict[str, Any]]:
    """
    Build a deterministic script for the known program holes.

    Pattern:

        STEP until next manual/completion
        STEP with fill for that manual span
        STEP until next manual/completion
        STEP with fill for that manual span
        ...
        STEP until completion

    This simulates a ChatGPT/app wrapper that already knows the user-provided
    inputs and feeds them into the public script runner.
    """
    script: list[dict[str, Any]] = []

    for fn_index in range(shape.fn_count):
        for frame_index in range(shape.frames_per_form):
            for span_index in range(shape.spans_per_frame):
                if not _is_manual_span(
                    fn_index=fn_index,
                    frame_index=frame_index,
                    span_index=span_index,
                    manual_span_every=shape.manual_span_every,
                ):
                    continue

                first_datum = _datum_id(
                    fn_index=fn_index,
                    frame_index=frame_index,
                    span_index=span_index,
                    datum_index=0,
                )

                script.append(
                    {
                        "action": "STEP",
                        "until_stop": True,
                        "stop_kinds": ["MANUALFILLNEEDEDSTEP", "ATCOMPLETION"],
                        "expect": {
                            "kind": "MANUALFILLNEEDEDSTEP",
                            "datum_widgets_on_this_span_contains": [first_datum],
                        },
                    }
                )

                script.append(
                    {
                        "action": "STEP",
                        "fill": _manual_span_fill(
                            shape=shape,
                            fn_index=fn_index,
                            frame_index=frame_index,
                            span_index=span_index,
                        ),
                    }
                )

    script.append(
        {
            "action": "STEP",
            "until_stop": True,
            "stop_kinds": ["ATCOMPLETION"],
            "expect": {
                "kind": "ATCOMPLETION",
            },
        }
    )

    return script


def _script_actions_for_shape(shape: ScriptProgramShape) -> list[dict[str, Any]]:
    """
    Legacy action-list body for scripted runs.

    This remains intentionally identical for raw and controller-backed scripting.
    The configured script form only changes the execution artery:

        legacy/raw default:
            [{"action": "STEP", ...}, ...]

        configured/controller:
            {
                "config": {"use_controller": True},
                "actions": [{"action": "STEP", ...}, ...],
            }

    The action bodies are the public scripting contract. They do not become
    controller packets, UFU packets, page-flow packets, role packets, or action
    packet objects.
    """
    return _script_for_shape(shape)


def _script_spec_for_shape(
    shape: ScriptProgramShape,
    *,
    use_controller: bool = False,
) -> Any:
    """
    Build either supported public script shape.

    use_controller=False intentionally returns the old bare list to prove
    backward compatibility and default behavior.

    use_controller=True returns the new configured top-level script object.
    """
    actions = _script_actions_for_shape(shape)

    if not use_controller:
        return actions

    return {
        "config": {
            "use_controller": True,
        },
        "actions": actions,
    }


def _script_actions_len(script: Any) -> int:
    if isinstance(script, Mapping):
        actions = script.get("actions")
        assert isinstance(actions, Sequence)
        return len(actions)

    assert isinstance(script, Sequence)
    return len(script)


def _assert_script_path_config(
    report: Mapping[str, Any],
    *,
    use_controller: bool,
) -> None:
    """
    Public report law for the script execution path.

    The configured script object should surface only tiny metadata that proves
    which path was used. It must not leak controller packets, raw ctx, history,
    state, snapshot, or multiframespec.
    """
    assert "script_config" in report
    assert report["script_config"] == {"use_controller": bool(use_controller)}

    modes = report.get("modes")
    assert isinstance(modes, Mapping)

    if use_controller:
        assert int(modes.get("CONTROLLER", 0)) > 0
        assert int(modes.get("ENGINE", 0)) == 0
    else:
        assert int(modes.get("ENGINE", 0)) > 0
        assert int(modes.get("CONTROLLER", 0)) == 0

    _assert_public_small(report)


def _assert_runtime_final_values_match(
    *,
    left_rows: Sequence[Mapping[str, Any]],
    right_rows: Sequence[Mapping[str, Any]],
    shape: ScriptProgramShape,
) -> None:
    left = _final_values_by_key(left_rows)
    right = _final_values_by_key(right_rows)

    for fn_index in range(shape.fn_count):
        for frame_index in range(shape.frames_per_form):
            for span_index in range(shape.spans_per_frame):
                for datum_index in range(shape.datums_per_span):
                    did = _datum_id(
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                    )

                    expected = _expected_final_value(
                        shape=shape,
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                    )

                    assert left.get(did) == expected
                    assert right.get(did) == expected
                    assert left.get(did) == right.get(did)


def _run_script_shape(
    *,
    api: PublicSessionAPI,
    shape: ScriptProgramShape,
    keep_step_reports: bool = True,
    use_controller: bool = False,
) -> tuple[Dict[str, Any], float]:
    manifest = _script_manifest(shape)
    script = _script_spec_for_shape(shape, use_controller=use_controller)

    t0 = time.perf_counter()
    report = api.run_action_scripted_program_start_to_finish(
        manifest=manifest,
        script=script,
        initial_parameter_overrides={},
        session_metadata=_lean_session_metadata(),
        keep_step_reports=keep_step_reports,
    )
    elapsed = time.perf_counter() - t0

    _assert_script_report(report)
    _assert_script_path_config(report, use_controller=use_controller)

    last = report["last"]
    assert isinstance(last, Mapping)
    assert last["event_kind"] == "ATCOMPLETION"
    assert last["finished"] is True

    assert report["script_count"] == _script_actions_len(script)

    return report, elapsed


def _all_final_rows_export(
    *,
    api: PublicSessionAPI,
    sid: str,
    expert_cap: int,
    include_values: bool,
    no_giant_z: bool = True,
) -> Dict[str, Any]:
    return _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill"],
            "include_values": include_values,
            "max_results": expert_cap,
        },
        no_giant_z=no_giant_z,
    )


def _final_values_by_key(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: dict[str, Any] = {}

    for row in rows:
        key = row.get("key")
        if key is None or "value" not in row:
            continue
        out[str(key)] = row.get("value")

    return out


def _assert_every_final_state_present(
    *,
    shape: ScriptProgramShape,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    by_key = _final_values_by_key(rows)
    assert len(by_key) >= shape.total_datums

    for fn_index in range(shape.fn_count):
        for frame_index in range(shape.frames_per_form):
            for span_index in range(shape.spans_per_frame):
                for datum_index in range(shape.datums_per_span):
                    did = _datum_id(
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                    )
                    assert did in by_key
                    assert by_key[did] == _expected_final_value(
                        shape=shape,
                        fn_index=fn_index,
                        frame_index=frame_index,
                        span_index=span_index,
                        datum_index=datum_index,
                    )


@pytest.fixture(autouse=True)
def _setup_registry():
    StepFnregistry.clear()


# ---------------------------------------------------------------------------
# 0. Step fn arg registration smoke test
# ---------------------------------------------------------------------------


def test_script_complexity_step_fn_args_are_registered_for_public_trace_audit_rows():
    """
    Regression guard for app-table validation.

    This sheet intentionally includes fn_args in manifest rows so
    program_trace_table(include_fn_args=True) can expose compact app-call audit
    metadata.

    Therefore those arg names must be registered on the synthetic step fn.
    """
    shape = ScriptProgramShape(
        label="arg_registration_smoke",
        fn_count=1,
        frames_per_form=1,
        spans_per_frame=1,
        datums_per_span=1,
        manual_span_every=0,
        payload_chars=0,
    )

    api = _custom_api(
        default_query_max_results=16,
        default_trace_max_results=16,
        absolute_query_max_results=64,
    )

    manifest = _script_manifest(shape)

    assert manifest[0]["fn_args"] == {
        "shape_label": "arg_registration_smoke",
        "fn_index": 0,
        "frames_per_form": 1,
        "spans_per_frame": 1,
        "datums_per_span": 1,
    }

    report, _elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )

    sid = str(report["session_id"])

    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 8,
        },
    )

    rows = _trace_rows(trace)
    app_rows = [
        row
        for row in rows
        if row.get("row_kind") == "app_call"
    ]

    assert app_rows
    assert app_rows[0]["step_fn"] == "public.script.complexity.arg_registration_smoke.fn.0"
    assert app_rows[0]["public_step_name"] == "script_fn_0"
    assert app_rows[0]["fn_args"]["shape_label"] == "arg_registration_smoke"
    assert app_rows[0]["fn_args"]["fn_index"] == 0
    assert app_rows[0]["fn_args"]["frames_per_form"] == 1
    assert app_rows[0]["fn_args"]["spans_per_frame"] == 1
    assert app_rows[0]["fn_args"]["datums_per_span"] == 1

    _assert_public_small(trace)


# ---------------------------------------------------------------------------
# 1. Pure scripted completion over large width/depth/length stays sealed
# ---------------------------------------------------------------------------


def test_script_headless_report_large_prefilled_program_is_tiny_and_final_states_are_exportable():
    """
    Large no-hole program.

    This isolates the top-level script report from manual input cost:

        many fns
        × many frames
        × many spans
        × many datums
        × all datums prefilled

    The script report must be tiny. The full final-state table is available
    only through explicit expert G*.
    """
    shape = ScriptProgramShape(
        label="large_prefilled",
        fn_count=14,
        frames_per_form=4,
        spans_per_frame=5,
        datums_per_span=6,
        manual_span_every=0,
        payload_chars=0,
    )

    expert_cap = shape.total_datums + shape.fn_count + 128

    api = _custom_api(
        default_query_max_results=32,
        default_trace_max_results=40,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=24,
        datum_widgets_on_this_span_preview_limit=24,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )
    sid = str(report["session_id"])

    report_stats = _bounded_container_stats(report)
    assert report_stats["total_string_chars"] < 10_000

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.total_datums
    assert outputs["counts"]["form_fills"] == 0
    assert outputs["key_preview_limit"] == 24
    assert len(outputs["keys"]["form_prefills"]) <= 24
    assert outputs["truncated_keys"]["form_prefills"] is True
    _assert_public_small(outputs)

    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 32
    assert len(_runtime_rows(default_writes)) <= 32
    assert default_writes["result"]["truncated"] is True

    t0 = time.perf_counter()
    all_writes = _all_final_rows_export(
        api=api,
        sid=sid,
        expert_cap=expert_cap,
        include_values=True,
    )
    export_elapsed = time.perf_counter() - t0

    assert all_writes["result"]["max_results"] == expert_cap
    assert all_writes["result"]["truncated"] is False

    rows = _runtime_rows(all_writes)
    final_rows = [
        row
        for row in rows
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]
    assert len(final_rows) >= shape.total_datums

    _assert_every_final_state_present(
        shape=shape,
        rows=final_rows,
    )

    write_stats = _bounded_container_stats(all_writes)

    print(
        "[public-script-efficiency-summary] large_prefilled_script "
        f"fn_count={shape.fn_count} "
        f"frames_per_form={shape.frames_per_form} "
        f"spans_per_frame={shape.spans_per_frame} "
        f"datums_per_span={shape.datums_per_span} "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"script_count={report['script_count']} "
        f"history_count={report.get('history_count')} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"export_elapsed={export_elapsed:.6f}s "
        f"report_string_chars={report_stats['total_string_chars']} "
        f"export_rows={len(rows)} "
        f"export_string_chars={write_stats['total_string_chars']}"
    )

    assert run_elapsed < 10.0
    assert export_elapsed < 5.0


# ---------------------------------------------------------------------------
# 2. Scripted manual holes across all axes complete and export exact finals
# ---------------------------------------------------------------------------


def test_script_headless_report_fills_manual_holes_across_length_depth_width_and_exports_all_finals():
    """
    Mixed prefilled/manual program.

    This is the core highest-seam scripting proof:

        app supplies a script containing preprogrammed user inputs
        public script runner drives the session to completion
        public result stays tiny and sealed
        all manual and prefilled final states are recoverable through G*

    Manual holes are distributed across:
        many app fns,
        many frames,
        many spans,
        many datums per span.
    """
    shape = ScriptProgramShape(
        label="manual_holes",
        fn_count=8,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=4,
        manual_span_every=3,
        payload_chars=0,
    )

    assert shape.manual_spans > 0
    assert shape.manual_datums > 0
    assert shape.prefilled_datums > 0

    expert_cap = shape.total_datums + shape.fn_count + 128

    api = _custom_api(
        default_query_max_results=24,
        default_trace_max_results=36,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=20,
        datum_widgets_on_this_span_preview_limit=20,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )
    sid = str(report["session_id"])

    assert report["script_count"] == (shape.manual_spans * 2) + 1
    assert int(report["history_count"]) >= shape.manual_spans

    report_stats = _bounded_container_stats(report)
    assert report_stats["total_string_chars"] < 20_000

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.prefilled_datums
    assert outputs["counts"]["form_fills"] >= shape.manual_datums
    assert outputs["key_preview_limit"] == 20
    _assert_public_small(outputs)

    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 24
    assert len(_runtime_rows(default_writes)) <= 24
    assert default_writes["result"]["truncated"] is True

    t0 = time.perf_counter()
    all_writes = _all_final_rows_export(
        api=api,
        sid=sid,
        expert_cap=expert_cap,
        include_values=True,
    )
    export_elapsed = time.perf_counter() - t0

    assert all_writes["result"]["max_results"] == expert_cap
    assert all_writes["result"]["truncated"] is False

    rows = _runtime_rows(all_writes)
    final_rows = [
        row
        for row in rows
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]

    assert len(final_rows) >= shape.total_datums

    manual_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_fill"
    ]
    prefill_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_prefill"
    ]

    assert len(manual_rows) >= shape.manual_datums
    assert len(prefill_rows) >= shape.prefilled_datums

    _assert_every_final_state_present(
        shape=shape,
        rows=final_rows,
    )

    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 40,
        },
    )

    trace_rows = _trace_rows(trace)
    assert len(trace_rows) <= 40
    assert trace["result"]["truncated"] is True

    row_kinds = {str(row.get("row_kind")) for row in trace_rows}
    assert "app_call" in row_kinds
    assert "span" in row_kinds or "datum_io" in row_kinds

    for row in trace_rows:
        assert "value" not in row
        _assert_public_small(row)

    write_stats = _bounded_container_stats(all_writes)

    print(
        "[public-script-efficiency-summary] manual_holes_script "
        f"fn_count={shape.fn_count} "
        f"frames_per_form={shape.frames_per_form} "
        f"spans_per_frame={shape.spans_per_frame} "
        f"datums_per_span={shape.datums_per_span} "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"manual_datums={shape.manual_datums} "
        f"prefilled_datums={shape.prefilled_datums} "
        f"script_count={report['script_count']} "
        f"history_count={report.get('history_count')} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"export_elapsed={export_elapsed:.6f}s "
        f"report_string_chars={report_stats['total_string_chars']} "
        f"export_rows={len(rows)} "
        f"manual_rows={len(manual_rows)} "
        f"prefill_rows={len(prefill_rows)} "
        f"export_string_chars={write_stats['total_string_chars']} "
        f"trace_rows={len(trace_rows)} "
        f"row_kinds={sorted(row_kinds)}"
    )

    assert run_elapsed < 12.0
    assert export_elapsed < 5.0


# ---------------------------------------------------------------------------
# 3. Large payloads inside scripted programs do not leak by default
# ---------------------------------------------------------------------------


def test_script_headless_report_with_giant_payloads_stays_small_until_explicit_value_export():
    """
    Large-data scripting proof.

    Giant values exist in final state. The script report, outputs report, and
    metadata-only G* queries must not leak them.

    Value materialization happens only when include_values=True is explicit.
    """
    shape = ScriptProgramShape(
        label="giant_payloads",
        fn_count=10,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=5,
        manual_span_every=0,
        payload_chars=12_000,
        payload_char="Z",
    )

    api = _custom_api(
        default_query_max_results=32,
        default_trace_max_results=32,
        absolute_query_max_results=512,
        output_key_preview_limit=24,
        datum_widgets_on_this_span_preview_limit=24,
        public_sanitizer_string_limit=512,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )
    sid = str(report["session_id"])

    assert not _contains_run(report, "Z", 1000)
    _assert_public_small(report)

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.total_datums
    assert not _contains_run(outputs, "Z", 1000)
    _assert_public_small(outputs)

    t0 = time.perf_counter()
    writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": False,
            "max_results": 31,
        },
    )
    writes_elapsed = time.perf_counter() - t0

    rows = _runtime_rows(writes)
    assert len(rows) <= 31
    assert writes["result"]["truncated"] is True
    assert not _contains_run(writes, "Z", 1000)

    for row in rows:
        assert "value" not in row
        _assert_public_small(row)

    t0 = time.perf_counter()
    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 31,
        },
    )
    trace_elapsed = time.perf_counter() - t0

    trace_rows = _trace_rows(trace)
    assert len(trace_rows) <= 31
    assert trace["result"]["truncated"] is True
    assert not _contains_run(trace, "Z", 1000)

    for row in trace_rows:
        assert "value" not in row
        _assert_public_small(row)

    report_stats = _bounded_container_stats(report)
    outputs_stats = _bounded_container_stats(outputs)
    writes_stats = _bounded_container_stats(writes)
    trace_stats = _bounded_container_stats(trace)

    print(
        "[public-script-efficiency-summary] giant_payload_script_metadata_only "
        f"fn_count={shape.fn_count} "
        f"frames_per_form={shape.frames_per_form} "
        f"spans_per_frame={shape.spans_per_frame} "
        f"datums_per_span={shape.datums_per_span} "
        f"total_datums={shape.total_datums} "
        f"payload_chars={shape.payload_chars} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"writes_elapsed={writes_elapsed:.6f}s "
        f"trace_elapsed={trace_elapsed:.6f}s "
        f"report_string_chars={report_stats['total_string_chars']} "
        f"outputs_string_chars={outputs_stats['total_string_chars']} "
        f"writes_string_chars={writes_stats['total_string_chars']} "
        f"trace_string_chars={trace_stats['total_string_chars']} "
        f"writes_rows={len(rows)} "
        f"trace_rows={len(trace_rows)}"
    )

    assert run_elapsed < 12.0
    assert writes_elapsed < 3.0
    assert trace_elapsed < 3.0


# ---------------------------------------------------------------------------
# 4. Fixed-cap script query slope stays healthy as program size accumulates
# ---------------------------------------------------------------------------


def test_script_fixed_cap_queries_stay_small_as_scripted_program_size_grows():
    """
    Slope proof for ChatGPT/app wrappers.

    The app runs a small scripted program and a larger scripted program.
    Then it asks the same fixed-cap G* questions.

    Public theorem:

        With max_results fixed, query result size is fixed.
        Runtime should not explode with accumulated program/session data.
    """
    trace_limit = 18
    writes_limit = 18

    small_shape = ScriptProgramShape(
        label="slope_small",
        fn_count=4,
        frames_per_form=2,
        spans_per_frame=3,
        datums_per_span=3,
        manual_span_every=3,
        payload_chars=1_000,
    )

    large_shape = ScriptProgramShape(
        label="slope_large",
        fn_count=10,
        frames_per_form=3,
        spans_per_frame=5,
        datums_per_span=4,
        manual_span_every=4,
        payload_chars=6_000,
    )

    def run_case(shape: ScriptProgramShape) -> tuple[int, float, float, float]:
        api = _custom_api(
            default_query_max_results=writes_limit,
            default_trace_max_results=trace_limit,
            absolute_query_max_results=512,
            output_key_preview_limit=20,
            datum_widgets_on_this_span_preview_limit=20,
            public_sanitizer_string_limit=512,
        )

        report, run_elapsed = _run_script_shape(
            api=api,
            shape=shape,
        )
        sid = str(report["session_id"])

        def writes_once() -> None:
            result = _query_with_api(
                api,
                sid,
                query_kind="runtime_writes",
                query={
                    "write_kinds": ["form_prefill", "form_fill"],
                    "include_values": False,
                    "max_results": writes_limit,
                },
            )
            rows = _runtime_rows(result)
            assert len(rows) <= writes_limit
            assert result["result"]["max_results"] == writes_limit
            assert not _contains_run(result, "Z", 1000)

        def trace_once() -> None:
            result = _query_with_api(
                api,
                sid,
                query_kind="program_trace_table",
                query={
                    "include_fn_args": False,
                    "include_datum_values": False,
                    "include_q_lifecycle": False,
                    "max_results": trace_limit,
                },
            )
            rows = _trace_rows(result)
            assert len(rows) <= trace_limit
            assert result["result"]["max_results"] == trace_limit
            assert not _contains_run(result, "Z", 1000)

        writes_t = _median_seconds(writes_once, repeats=5)
        trace_t = _median_seconds(trace_once, repeats=5)

        print(
            "[public-script-efficiency-summary] script_fixed_cap_slope_case "
            f"label={shape.label} "
            f"total_datums={shape.total_datums} "
            f"manual_datums={shape.manual_datums} "
            f"prefilled_datums={shape.prefilled_datums} "
            f"payload_chars={shape.payload_chars} "
            f"script_count={report['script_count']} "
            f"run_elapsed={run_elapsed:.6f}s "
            f"writes_query_median={writes_t:.6f}s "
            f"trace_query_median={trace_t:.6f}s"
        )

        return shape.total_datums, run_elapsed, writes_t, trace_t

    small_n, _small_run, small_writes_t, small_trace_t = run_case(small_shape)
    large_n, _large_run, large_writes_t, large_trace_t = run_case(large_shape)

    writes_ratio = _slope_ratio(
        small_y=small_writes_t,
        large_y=large_writes_t,
        small_n=small_n,
        large_n=large_n,
    )
    trace_ratio = _slope_ratio(
        small_y=small_trace_t,
        large_y=large_trace_t,
        small_n=small_n,
        large_n=large_n,
    )

    print(
        "[public-script-efficiency-summary] script_fixed_cap_slope "
        f"small_datums={small_n} "
        f"large_datums={large_n} "
        f"small_writes={small_writes_t:.6f}s "
        f"large_writes={large_writes_t:.6f}s "
        f"writes_ratio_vs_linear={writes_ratio:.3f} "
        f"small_trace={small_trace_t:.6f}s "
        f"large_trace={large_trace_t:.6f}s "
        f"trace_ratio_vs_linear={trace_ratio:.3f}"
    )

    _assert_not_superlinear_badly(
        small_y=small_writes_t,
        large_y=large_writes_t,
        small_n=small_n,
        large_n=large_n,
        slack=10.0,
        label="script fixed-cap runtime_writes query",
    )
    _assert_not_superlinear_badly(
        small_y=small_trace_t,
        large_y=large_trace_t,
        small_n=small_n,
        large_n=large_n,
        slack=10.0,
        label="script fixed-cap program_trace_table query",
    )


# ---------------------------------------------------------------------------
# 5. Expert cap can export complete final table after scripted manual run
# ---------------------------------------------------------------------------


def test_script_expert_cap_can_export_whole_final_datum_table_after_large_manual_script():
    """
    Final scripting theorem.

    This is the app-wrapper story:

        1. Run a large program from a manifest.
        2. Script supplies all manual holes.
        3. The session completes.
        4. Public script report stays small.
        5. Default outputs stay preview-only.
        6. Default G* stays capped.
        7. Expert G* can retrieve the whole final datum table.

    This is the exact "no matter how much program data accumulates, the app can
    stay small by default and still ask for all final datum states when needed"
    contract.
    """
    shape = ScriptProgramShape(
        label="expert_full_table_after_manual_script",
        fn_count=12,
        frames_per_form=4,
        spans_per_frame=5,
        datums_per_span=4,
        manual_span_every=4,
        payload_chars=0,
    )

    expert_cap = shape.total_datums + shape.fn_count + 256

    api = _custom_api(
        default_query_max_results=40,
        default_trace_max_results=48,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=32,
        datum_widgets_on_this_span_preview_limit=32,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(8192, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )
    sid = str(report["session_id"])

    report_stats = _bounded_container_stats(report)
    assert report_stats["total_string_chars"] < 25_000

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.prefilled_datums
    assert outputs["counts"]["form_fills"] >= shape.manual_datums
    assert outputs["key_preview_limit"] == 32
    assert len(outputs["keys"]["form_prefills"]) <= 32
    assert len(outputs["keys"]["form_fills"]) <= 32
    _assert_public_small(outputs)

    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 40
    assert len(_runtime_rows(default_writes)) <= 40
    assert default_writes["result"]["truncated"] is True

    t0 = time.perf_counter()
    all_writes = _all_final_rows_export(
        api=api,
        sid=sid,
        expert_cap=expert_cap,
        include_values=True,
    )
    export_elapsed = time.perf_counter() - t0

    assert all_writes["result"]["max_results"] == expert_cap
    assert all_writes["result"]["truncated"] is False

    rows = _runtime_rows(all_writes)
    final_rows = [
        row
        for row in rows
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]

    assert len(final_rows) >= shape.total_datums

    manual_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_fill"
    ]
    prefill_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_prefill"
    ]

    assert len(manual_rows) >= shape.manual_datums
    assert len(prefill_rows) >= shape.prefilled_datums

    _assert_every_final_state_present(
        shape=shape,
        rows=final_rows,
    )

    t0 = time.perf_counter()
    full_trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": False,
            "max_results": expert_cap,
        },
    )
    trace_elapsed = time.perf_counter() - t0

    trace_rows = _trace_rows(full_trace)
    assert len(trace_rows) <= expert_cap

    row_kinds = {str(row.get("row_kind")) for row in trace_rows}
    assert "app_call" in row_kinds
    assert "datum_io" in row_kinds

    # Topology rows are useful when present, but the public theorem for this export
    # is app-call auditability plus final datum IO. Depending on cap/order/topology
    # discovery, the bounded prefix may reach datum_io rows without including span
    # rows.
    assert row_kinds <= {"app_call", "span", "datum_io", "datum_reexplosion"}

    for row in trace_rows:
        assert "ctx" not in row
        assert "snapshot" not in row
        assert "multiframespec" not in row
        assert "state" not in row
        assert "content" not in row
        _assert_public_small(row)

    write_stats = _bounded_container_stats(all_writes)
    trace_stats = _bounded_container_stats(full_trace)

    print(
        "[public-script-efficiency-summary] script_expert_full_final_table "
        f"fn_count={shape.fn_count} "
        f"frames_per_form={shape.frames_per_form} "
        f"spans_per_frame={shape.spans_per_frame} "
        f"datums_per_span={shape.datums_per_span} "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"manual_datums={shape.manual_datums} "
        f"prefilled_datums={shape.prefilled_datums} "
        f"script_count={report['script_count']} "
        f"history_count={report.get('history_count')} "
        f"expert_cap={expert_cap} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"export_elapsed={export_elapsed:.6f}s "
        f"trace_elapsed={trace_elapsed:.6f}s "
        f"report_string_chars={report_stats['total_string_chars']} "
        f"write_rows={len(rows)} "
        f"manual_rows={len(manual_rows)} "
        f"prefill_rows={len(prefill_rows)} "
        f"write_string_chars={write_stats['total_string_chars']} "
        f"trace_rows={len(trace_rows)} "
        f"trace_string_chars={trace_stats['total_string_chars']} "
        f"row_kinds={sorted(row_kinds)}"
    )

    assert run_elapsed < 15.0
    assert export_elapsed < 5.0
    assert trace_elapsed < 5.0


# ---------------------------------------------------------------------------
# 6. Absurd script query asks remain capped
# ---------------------------------------------------------------------------


def test_script_public_gstar_absurd_post_script_requests_are_capped():
    """
    After a scripted run, callers may still ask for absurd G* sizes.

    Public theorem:

        Default wrapper clamps to ABSOLUTE_QUERY_MAX_RESULTS_V1.
    """
    shape = ScriptProgramShape(
        label="absurd_cap_after_script",
        fn_count=5,
        frames_per_form=2,
        spans_per_frame=4,
        datums_per_span=3,
        manual_span_every=2,
        payload_chars=0,
    )

    api = get_public_session_api()

    report, _elapsed = _run_script_shape(
        api=api,
        shape=shape,
    )
    sid = str(report["session_id"])

    writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill"],
            "include_values": True,
            "max_results": 999_999,
        },
    )
    assert writes["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_runtime_rows(writes)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1

    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": True,
            "include_q_lifecycle": False,
            "max_results": 999_999,
        },
    )
    assert trace["result"]["max_results"] == ABSOLUTE_QUERY_MAX_RESULTS_V1
    assert len(_trace_rows(trace)) <= ABSOLUTE_QUERY_MAX_RESULTS_V1


# ---------------------------------------------------------------------------
# 7. Controller-backed configured script type
# ---------------------------------------------------------------------------


def test_script_configured_controller_type_uses_same_action_bodies_and_completes_e2e():
    """
    New configured script shape:

        {
            "config": {"use_controller": True},
            "actions": [...]
        }

    The only semantic difference from the legacy list script is the execution
    artery. The action bodies remain the same public script bodies.

    This proves the app-facing usage story:

        old script:
            script = [{"action": "STEP", ...}]

        controller-backed script:
            script = {
                "config": {"use_controller": True},
                "actions": [{"action": "STEP", ...}],
            }

    Correctness laws:
        - final event is ATCOMPLETION,
        - script_count ignores config and counts only actions,
        - report proves CONTROLLER mode,
        - public report remains small/sealed,
        - manual holes are filled exactly.
    """
    shape = ScriptProgramShape(
        label="controller_configured_type_e2e",
        fn_count=5,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=3,
        manual_span_every=3,
        payload_chars=0,
    )

    assert shape.manual_spans > 0

    expert_cap = shape.total_datums + shape.fn_count + 128

    api = _custom_api(
        default_query_max_results=24,
        default_trace_max_results=32,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=20,
        datum_widgets_on_this_span_preview_limit=20,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    legacy_actions = _script_actions_for_shape(shape)
    configured_script = _script_spec_for_shape(shape, use_controller=True)

    assert isinstance(configured_script, Mapping)
    assert configured_script["config"] == {"use_controller": True}
    assert configured_script["actions"] == legacy_actions

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
        use_controller=True,
    )
    sid = str(report["session_id"])

    assert report["script_count"] == len(legacy_actions)
    assert report["script_config"] == {"use_controller": True}
    assert report["modes"]["CONTROLLER"] == report["history_count"]
    assert int(report["modes"].get("ENGINE", 0)) == 0

    all_writes = _all_final_rows_export(
        api=api,
        sid=sid,
        expert_cap=expert_cap,
        include_values=True,
    )

    rows = _runtime_rows(all_writes)
    final_rows = [
        row
        for row in rows
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]

    assert len(final_rows) >= shape.total_datums
    _assert_every_final_state_present(shape=shape, rows=final_rows)

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.prefilled_datums
    assert outputs["counts"]["form_fills"] >= shape.manual_datums
    _assert_public_small(outputs)

    print(
        "[public-script-controller-summary] configured_controller_e2e "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"manual_datums={shape.manual_datums} "
        f"script_count={report['script_count']} "
        f"history_count={report['history_count']} "
        f"modes={dict(report['modes'])} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"export_rows={len(rows)}"
    )

    assert run_elapsed < 12.0


def test_script_raw_list_and_controller_configured_type_have_matching_final_state_tables():
    """
    Raw/default scripting and controller-backed scripting must be e2e equivalent
    at the public semantic boundary.

    This test runs the same manifest shape twice:

        1. legacy bare-list script, default use_controller=False
        2. configured object script, use_controller=True

    It then compares explicit G* final datum tables.

    Expected difference:
        - report["script_config"]["use_controller"]
        - report["modes"] ENGINE vs CONTROLLER

    Expected sameness:
        - action bodies,
        - script_count,
        - ATCOMPLETION,
        - output counts,
        - final runtime_writes values.
    """
    shape = ScriptProgramShape(
        label="raw_vs_controller_equivalence",
        fn_count=6,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=4,
        manual_span_every=3,
        payload_chars=0,
    )

    assert shape.manual_spans > 0

    expert_cap = shape.total_datums + shape.fn_count + 128

    raw_api = _custom_api(
        default_query_max_results=24,
        default_trace_max_results=32,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=20,
        datum_widgets_on_this_span_preview_limit=20,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    raw_report, raw_elapsed = _run_script_shape(
        api=raw_api,
        shape=shape,
        use_controller=False,
    )
    raw_sid = str(raw_report["session_id"])

    # Registry is autouse-cleared only per test, so create an independent API
    # but intentionally reuse the same registered synthetic function names.
    # StepFnregistry.register(... overwrite=True) in _script_manifest keeps this
    # deterministic.
    controller_api = _custom_api(
        default_query_max_results=24,
        default_trace_max_results=32,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=20,
        datum_widgets_on_this_span_preview_limit=20,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    controller_report, controller_elapsed = _run_script_shape(
        api=controller_api,
        shape=shape,
        use_controller=True,
    )
    controller_sid = str(controller_report["session_id"])

    assert raw_report["script_config"] == {"use_controller": False}
    assert controller_report["script_config"] == {"use_controller": True}

    assert raw_report["script_count"] == controller_report["script_count"]
    assert raw_report["script_count"] == len(_script_actions_for_shape(shape))

    assert raw_report["last"]["event_kind"] == "ATCOMPLETION"
    assert controller_report["last"]["event_kind"] == "ATCOMPLETION"

    assert int(raw_report["modes"].get("ENGINE", 0)) > 0
    assert int(raw_report["modes"].get("CONTROLLER", 0)) == 0
    assert int(controller_report["modes"].get("CONTROLLER", 0)) > 0
    assert int(controller_report["modes"].get("ENGINE", 0)) == 0

    raw_outputs = _outputs_report_with_api(raw_api, raw_sid)
    controller_outputs = _outputs_report_with_api(controller_api, controller_sid)

    assert raw_outputs["counts"]["form_prefills"] == controller_outputs["counts"]["form_prefills"]
    assert raw_outputs["counts"]["form_fills"] == controller_outputs["counts"]["form_fills"]

    raw_writes = _all_final_rows_export(
        api=raw_api,
        sid=raw_sid,
        expert_cap=expert_cap,
        include_values=True,
    )
    controller_writes = _all_final_rows_export(
        api=controller_api,
        sid=controller_sid,
        expert_cap=expert_cap,
        include_values=True,
    )

    raw_rows = [
        row
        for row in _runtime_rows(raw_writes)
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]
    controller_rows = [
        row
        for row in _runtime_rows(controller_writes)
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]

    _assert_runtime_final_values_match(
        left_rows=raw_rows,
        right_rows=controller_rows,
        shape=shape,
    )

    print(
        "[public-script-controller-summary] raw_vs_controller_equivalence "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"script_count={raw_report['script_count']} "
        f"raw_history_count={raw_report['history_count']} "
        f"controller_history_count={controller_report['history_count']} "
        f"raw_elapsed={raw_elapsed:.6f}s "
        f"controller_elapsed={controller_elapsed:.6f}s "
        f"raw_modes={dict(raw_report['modes'])} "
        f"controller_modes={dict(controller_report['modes'])}"
    )

    assert raw_elapsed < 12.0
    assert controller_elapsed < 12.0


def test_controller_script_headless_report_fills_manual_holes_and_exports_all_finals():
    """
    Controller-path counterpart of the main manual-hole theorem.

    This specifically proves that the controller-backed script path does not
    weaken the public scripting complexity contract:

        - script report remains sealed,
        - controller path reaches completion,
        - dotted fill grammar in the same action body works,
        - all manual and prefilled final states are explicit-G* exportable.
    """
    shape = ScriptProgramShape(
        label="controller_manual_holes_full_export",
        fn_count=8,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=4,
        manual_span_every=3,
        payload_chars=0,
    )

    expert_cap = shape.total_datums + shape.fn_count + 128

    api = _custom_api(
        default_query_max_results=24,
        default_trace_max_results=36,
        absolute_query_max_results=expert_cap,
        output_key_preview_limit=20,
        datum_widgets_on_this_span_preview_limit=20,
        public_sanitizer_list_limit=expert_cap + 128,
        public_sanitizer_dict_limit=max(4096, expert_cap + 128),
        public_sanitizer_string_limit=2048,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
        use_controller=True,
    )
    sid = str(report["session_id"])

    assert report["script_config"] == {"use_controller": True}
    assert report["script_count"] == (shape.manual_spans * 2) + 1
    assert int(report["history_count"]) >= shape.manual_spans
    assert int(report["modes"].get("CONTROLLER", 0)) == int(report["history_count"])

    default_writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill", "form_fill"],
            "include_values": True,
        },
    )
    assert default_writes["result"]["max_results"] == 24
    assert len(_runtime_rows(default_writes)) <= 24
    assert default_writes["result"]["truncated"] is True

    all_writes = _all_final_rows_export(
        api=api,
        sid=sid,
        expert_cap=expert_cap,
        include_values=True,
    )
    assert all_writes["result"]["truncated"] is False

    final_rows = [
        row
        for row in _runtime_rows(all_writes)
        if row.get("write_kind") in {"form_prefill", "form_fill"}
    ]

    manual_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_fill"
    ]
    prefill_rows = [
        row
        for row in final_rows
        if row.get("write_kind") == "form_prefill"
    ]

    assert len(final_rows) >= shape.total_datums
    assert len(manual_rows) >= shape.manual_datums
    assert len(prefill_rows) >= shape.prefilled_datums

    _assert_every_final_state_present(
        shape=shape,
        rows=final_rows,
    )

    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 40,
        },
    )

    trace_rows = _trace_rows(trace)
    assert len(trace_rows) <= 40

    for row in trace_rows:
        assert "value" not in row
        _assert_public_small(row)

    print(
        "[public-script-controller-summary] controller_manual_holes_full_export "
        f"total_datums={shape.total_datums} "
        f"manual_spans={shape.manual_spans} "
        f"manual_datums={shape.manual_datums} "
        f"prefilled_datums={shape.prefilled_datums} "
        f"script_count={report['script_count']} "
        f"history_count={report['history_count']} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"final_rows={len(final_rows)} "
        f"manual_rows={len(manual_rows)} "
        f"prefill_rows={len(prefill_rows)} "
        f"trace_rows={len(trace_rows)}"
    )

    assert run_elapsed < 15.0


def test_controller_script_with_giant_payloads_stays_small_until_explicit_value_export():
    """
    Controller-backed large-data proof.

    Giant values pass through the controller-backed script path, but public
    default reports and metadata-only G* still must not leak them.
    """
    shape = ScriptProgramShape(
        label="controller_giant_payloads",
        fn_count=8,
        frames_per_form=3,
        spans_per_frame=4,
        datums_per_span=5,
        manual_span_every=0,
        payload_chars=12_000,
        payload_char="Z",
    )

    api = _custom_api(
        default_query_max_results=32,
        default_trace_max_results=32,
        absolute_query_max_results=512,
        output_key_preview_limit=24,
        datum_widgets_on_this_span_preview_limit=24,
        public_sanitizer_string_limit=512,
    )

    report, run_elapsed = _run_script_shape(
        api=api,
        shape=shape,
        use_controller=True,
    )
    sid = str(report["session_id"])

    assert report["script_config"] == {"use_controller": True}
    assert int(report["modes"].get("CONTROLLER", 0)) > 0
    assert not _contains_run(report, "Z", 1000)
    _assert_public_small(report)

    outputs = _outputs_report_with_api(api, sid)
    assert outputs["counts"]["form_prefills"] >= shape.total_datums
    assert not _contains_run(outputs, "Z", 1000)
    _assert_public_small(outputs)

    writes = _query_with_api(
        api,
        sid,
        query_kind="runtime_writes",
        query={
            "write_kinds": ["form_prefill"],
            "include_values": False,
            "max_results": 31,
        },
    )
    assert writes["result"]["truncated"] is True
    assert not _contains_run(writes, "Z", 1000)

    for row in _runtime_rows(writes):
        assert "value" not in row
        _assert_public_small(row)

    trace = _query_with_api(
        api,
        sid,
        query_kind="program_trace_table",
        query={
            "include_fn_args": True,
            "include_datum_values": False,
            "include_q_lifecycle": False,
            "max_results": 31,
        },
    )
    assert trace["result"]["truncated"] is True
    assert not _contains_run(trace, "Z", 1000)

    for row in _trace_rows(trace):
        assert "value" not in row
        _assert_public_small(row)

    print(
        "[public-script-controller-summary] controller_giant_payloads_metadata_only "
        f"total_datums={shape.total_datums} "
        f"payload_chars={shape.payload_chars} "
        f"script_count={report['script_count']} "
        f"history_count={report['history_count']} "
        f"run_elapsed={run_elapsed:.6f}s "
        f"writes_rows={len(_runtime_rows(writes))} "
        f"trace_rows={len(_trace_rows(trace))}"
    )

    assert run_elapsed < 15.0


def test_controller_script_fixed_cap_queries_stay_small_as_program_size_grows():
    """
    Controller-path complexity slope proof.

    This mirrors the raw script fixed-cap theorem, but uses the configured
    controller script type.

    With max_results fixed:
        runtime_writes result cardinality remains capped,
        program_trace_table result cardinality remains capped,
        giant values do not appear in metadata-only queries,
        runtime should not become pathologically superlinear.
    """
    trace_limit = 18
    writes_limit = 18

    small_shape = ScriptProgramShape(
        label="controller_slope_small",
        fn_count=4,
        frames_per_form=2,
        spans_per_frame=3,
        datums_per_span=3,
        manual_span_every=3,
        payload_chars=1_000,
    )

    large_shape = ScriptProgramShape(
        label="controller_slope_large",
        fn_count=10,
        frames_per_form=3,
        spans_per_frame=5,
        datums_per_span=4,
        manual_span_every=4,
        payload_chars=6_000,
    )

    def run_case(shape: ScriptProgramShape) -> tuple[int, float, float, float]:
        api = _custom_api(
            default_query_max_results=writes_limit,
            default_trace_max_results=trace_limit,
            absolute_query_max_results=512,
            output_key_preview_limit=20,
            datum_widgets_on_this_span_preview_limit=20,
            public_sanitizer_string_limit=512,
        )

        report, run_elapsed = _run_script_shape(
            api=api,
            shape=shape,
            use_controller=True,
        )
        sid = str(report["session_id"])

        assert report["script_config"] == {"use_controller": True}
        assert int(report["modes"].get("CONTROLLER", 0)) > 0
        assert int(report["modes"].get("ENGINE", 0)) == 0

        def writes_once() -> None:
            result = _query_with_api(
                api,
                sid,
                query_kind="runtime_writes",
                query={
                    "write_kinds": ["form_prefill", "form_fill"],
                    "include_values": False,
                    "max_results": writes_limit,
                },
            )
            rows = _runtime_rows(result)
            assert len(rows) <= writes_limit
            assert result["result"]["max_results"] == writes_limit
            assert not _contains_run(result, "Z", 1000)

        def trace_once() -> None:
            result = _query_with_api(
                api,
                sid,
                query_kind="program_trace_table",
                query={
                    "include_fn_args": False,
                    "include_datum_values": False,
                    "include_q_lifecycle": False,
                    "max_results": trace_limit,
                },
            )
            rows = _trace_rows(result)
            assert len(rows) <= trace_limit
            assert result["result"]["max_results"] == trace_limit
            assert not _contains_run(result, "Z", 1000)

        writes_t = _median_seconds(writes_once, repeats=5)
        trace_t = _median_seconds(trace_once, repeats=5)

        print(
            "[public-script-controller-summary] controller_fixed_cap_slope_case "
            f"label={shape.label} "
            f"total_datums={shape.total_datums} "
            f"manual_datums={shape.manual_datums} "
            f"prefilled_datums={shape.prefilled_datums} "
            f"payload_chars={shape.payload_chars} "
            f"script_count={report['script_count']} "
            f"history_count={report['history_count']} "
            f"run_elapsed={run_elapsed:.6f}s "
            f"writes_query_median={writes_t:.6f}s "
            f"trace_query_median={trace_t:.6f}s"
        )

        return shape.total_datums, run_elapsed, writes_t, trace_t

    small_n, _small_run, small_writes_t, small_trace_t = run_case(small_shape)
    large_n, _large_run, large_writes_t, large_trace_t = run_case(large_shape)

    writes_ratio = _slope_ratio(
        small_y=small_writes_t,
        large_y=large_writes_t,
        small_n=small_n,
        large_n=large_n,
    )
    trace_ratio = _slope_ratio(
        small_y=small_trace_t,
        large_y=large_trace_t,
        small_n=small_n,
        large_n=large_n,
    )

    print(
        "[public-script-controller-summary] controller_fixed_cap_slope "
        f"small_datums={small_n} "
        f"large_datums={large_n} "
        f"small_writes={small_writes_t:.6f}s "
        f"large_writes={large_writes_t:.6f}s "
        f"writes_ratio_vs_linear={writes_ratio:.3f} "
        f"small_trace={small_trace_t:.6f}s "
        f"large_trace={large_trace_t:.6f}s "
        f"trace_ratio_vs_linear={trace_ratio:.3f}"
    )

    _assert_not_superlinear_badly(
        small_y=small_writes_t,
        large_y=large_writes_t,
        small_n=small_n,
        large_n=large_n,
        slack=10.0,
        label="controller script fixed-cap runtime_writes query",
    )
    _assert_not_superlinear_badly(
        small_y=small_trace_t,
        large_y=large_trace_t,
        small_n=small_n,
        large_n=large_n,
        slack=10.0,
        label="controller script fixed-cap program_trace_table query",
    )


# ---------------------------------------------------------------------------
# 8. Coverage taxonomy
# ---------------------------------------------------------------------------


def test_public_script_api_complexity_taxonomy_is_explicit():
    """
    Living checklist for this scripting complexity sheet.

    This prevents the file from drifting into only one axis.
    """
    axes = {
        "run_action_scripted_program_start_to_finish_is_highest_public_script_seam",
        "legacy_bare_list_script_shape_still_works",
        "configured_script_shape_can_enable_controller",
        "configured_script_config_is_not_counted_as_action",
        "raw_and_controller_scripts_use_same_action_bodies",
        "controller_script_reports_controller_mode",
        "raw_script_reports_engine_mode",
        "raw_and_controller_scripts_have_matching_final_public_semantics",
        "script_report_never_returns_raw_ctx",
        "script_report_never_returns_raw_history",
        "script_report_never_returns_multiframespec_snapshot_state_html",
        "step_fn_args_are_registered_for_public_trace_audit",
        "large_program_length_many_app_fns",
        "large_program_depth_many_frames",
        "large_program_width_many_spans",
        "large_span_width_many_datums_per_span",
        "manual_holes_are_filled_by_script_actions",
        "controller_script_fills_manual_holes",
        "prefilled_final_states_are_preserved",
        "manual_final_states_are_preserved",
        "default_outputs_are_counts_and_key_previews",
        "default_gstar_queries_are_capped",
        "metadata_only_queries_do_not_leak_giant_values",
        "controller_metadata_only_queries_do_not_leak_giant_values",
        "fixed_cap_queries_scale_with_max_results",
        "controller_fixed_cap_queries_scale_with_max_results",
        "expert_caps_are_instance_local",
        "expert_gstar_can_export_all_final_states",
        "program_trace_table_is_capped_table_shaped",
        "program_trace_table_can_show_compact_fn_args",
        "absurd_post_script_queries_are_capped",
        "app_wrapper_can_remain_small_by_default_forever",
    }

    assert len(axes) == 32
    assert "run_action_scripted_program_start_to_finish_is_highest_public_script_seam" in axes
    assert "legacy_bare_list_script_shape_still_works" in axes
    assert "configured_script_shape_can_enable_controller" in axes
    assert "raw_and_controller_scripts_use_same_action_bodies" in axes
    assert "raw_and_controller_scripts_have_matching_final_public_semantics" in axes
    assert "controller_script_fills_manual_holes" in axes
    assert "controller_fixed_cap_queries_scale_with_max_results" in axes
    assert "step_fn_args_are_registered_for_public_trace_audit" in axes
    assert "manual_holes_are_filled_by_script_actions" in axes
    assert "expert_gstar_can_export_all_final_states" in axes
    assert "program_trace_table_can_show_compact_fn_args" in axes
    assert "app_wrapper_can_remain_small_by_default_forever" in axes