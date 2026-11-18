from __future__ import annotations

"""
Read-only App Table state helpers.

This module is for App Table step-function authors and higher layers that need
cheap normalized reads over AppTableProgramEngine state.

Design laws
-----------
- no hidden mutation;
- no renderer or UI coupling;
- no viewer, role, authorization, or policy concepts;
- form specifications remain plain dead JSON;
- span extension keys are opaque;
- callers may explicitly request arbitrary span keys when resolving the active
  span.

Terminology
-----------
- prefills: values emitted by step functions through `multiframespec["fills"]`;
- fills: values provided through a manual-fill engine boundary;
- merged: prefills first, then manual fills override at the macro datum id.

Naming clarity
--------------
- `get_form_fills(...)` returns the raw global fills mapping;
- `get_form_fill_info(...)` returns a structured per-form view;
- pending-form helpers expose the currently active form surface.
"""

from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_FORMS_EMITTED,
    KEY_FORM_FILLS,
    KEY_FORM_PREFILLS,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
    KEY_RUNTIME_WRITE_INDEX,
    RESERVED_STATE_KEYS,
)


APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG = (
    "__app_table_session_ctx__"
)


# ---------------------------------------------------------------------------
# Current-form accessors
# ---------------------------------------------------------------------------


def get_pending_multiframespec_id(
    state: Mapping[str, Any],
) -> Optional[str]:
    value = state.get(
        KEY_PENDING_FORM_ID
    )
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def get_pending_multiframespec(
    state: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    value = state.get(KEY_PENDING_FORM)
    return (
        dict(value)
        if isinstance(value, Mapping)
        else None
    )


def get_pending_multiframespec_raw(
    state: Mapping[str, Any],
) -> Any:
    """Return the raw pending form object, without normalization."""
    return state.get(KEY_PENDING_FORM)


def get_forms_emitted(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    value = (
        state.get(KEY_FORMS_EMITTED)
        or {}
    )
    return (
        dict(value)
        if isinstance(value, Mapping)
        else {}
    )


def get_form_emitted(
    state: Mapping[str, Any],
    form_id: str,
) -> Optional[Dict[str, Any]]:
    forms = get_forms_emitted(state)
    multiframespec = forms.get(
        str(form_id)
    )
    return (
        dict(multiframespec)
        if isinstance(
            multiframespec,
            Mapping,
        )
        else None
    )


# ---------------------------------------------------------------------------
# Raw global fills and prefills
# ---------------------------------------------------------------------------


def get_form_prefills(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return the raw global prefill mapping."""
    value = (
        state.get(KEY_FORM_PREFILLS)
        or {}
    )
    return (
        dict(value)
        if isinstance(value, Mapping)
        else {}
    )


def get_form_fills(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return the raw global manual-fill mapping."""
    value = (
        state.get(KEY_FORM_FILLS)
        or {}
    )
    return (
        dict(value)
        if isinstance(value, Mapping)
        else {}
    )


def get_globals(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return application globals without reserved engine keys."""
    out: Dict[str, Any] = {}

    for key, value in state.items():
        normalized_key = str(key)
        if (
            normalized_key
            in RESERVED_STATE_KEYS
        ):
            continue
        out[normalized_key] = value

    return out


def read_stepfn_runtime_session_ctx_from_kwargs(
    kwargs: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Read the reserved invocation-time engine context bridge.

    Generic App Table step functions ordinarily receive authored state and
    authored arguments only. Runtimes that need the live engine context pass it
    through one reserved internal keyword.
    """
    if not isinstance(
        kwargs,
        Mapping,
    ):
        return {}

    raw = kwargs.get(
        APP_TABLE_STEP_FN_RUNTIME_SESSION_CTX_KWARG
    )
    return (
        dict(raw or {})
        if isinstance(raw, Mapping)
        else {}
    )


# ---------------------------------------------------------------------------
# Runtime write-history queries
# ---------------------------------------------------------------------------


def get_runtime_write_index_summary(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return bounded write-index diagnostics without large values."""
    index = state.get(
        KEY_RUNTIME_WRITE_INDEX
    )
    if not isinstance(index, Mapping):
        return {
            "kind": (
                "runtime_write_index_"
                "summary_v1"
            ),
            "present": False,
            "invocation_count": 0,
            "write_event_count": 0,
        }

    return {
        "kind": (
            "runtime_write_index_"
            "summary_v1"
        ),
        "present": True,
        "version": index.get("v"),
        "invocation_count": len(
            index.get("invocations")
            or {}
        ),
        "write_event_count": len(
            index.get("write_events")
            or {}
        ),
        "public_step_names": sorted(
            list(
                (
                    index.get(
                        "by_public_step_name"
                    )
                    or {}
                ).keys()
            )
        ),
        "step_fns": sorted(
            list(
                (
                    index.get("by_step_fn")
                    or {}
                ).keys()
            )
        ),
        "arg_names": sorted(
            list(
                (
                    index.get("by_arg_name")
                    or {}
                ).keys()
            )
        ),
        "write_kinds": sorted(
            list(
                (
                    index.get(
                        "events_by_write_kind"
                    )
                    or {}
                ).keys()
            )
        ),
    }


def query_runtime_writes(
    state: Mapping[str, Any],
    query: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Query previous runtime writes through the engine-maintained index.

    Large values are omitted unless requested by the query. Value resolution is
    current-state/reference based rather than historical payload replay.
    """
    from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
        query_runtime_writes_v1,
    )

    return query_runtime_writes_v1(
        state,
        query,
    )


# ---------------------------------------------------------------------------
# Form-shape collection
# ---------------------------------------------------------------------------


def _collect_form_datums(
    multiframespec: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    out: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for datum in (
        multiframespec.get("datums") or []
    ):
        if not isinstance(
            datum,
            Mapping,
        ):
            continue

        datum_id = str(
            datum.get("id") or ""
        )
        if datum_id:
            out[datum_id] = dict(datum)

    return out


def _collect_form_spans(
    multiframespec: Mapping[str, Any],
) -> Dict[
    Tuple[str, str],
    List[str],
]:
    """
    Return:

        (frame_id, span_id) -> owned datum ids
    """
    out: Dict[
        Tuple[str, str],
        List[str],
    ] = {}

    for frame in (
        multiframespec.get("frames") or []
    ):
        if not isinstance(
            frame,
            Mapping,
        ):
            continue

        frame_id = str(
            frame.get("id") or ""
        )

        for span in (
            frame.get("spans") or []
        ):
            if not isinstance(
                span,
                Mapping,
            ):
                continue

            span_id = str(
                span.get("id") or ""
            )
            owns = [
                str(value)
                for value in (
                    span.get("owns")
                    or []
                )
            ]
            out[
                (frame_id, span_id)
            ] = owns

    return out


def get_form_prefills_for_form(
    state: Mapping[str, Any],
    form_id: str,
) -> Dict[str, Any]:
    """Return prefills restricted to datum ids on one form."""
    multiframespec = get_form_emitted(
        state,
        form_id,
    )
    if not multiframespec:
        return {}

    datums = _collect_form_datums(
        multiframespec
    )
    prefills = get_form_prefills(
        state
    )

    return {
        datum_id: prefills[datum_id]
        for datum_id in datums
        if datum_id in prefills
    }


def get_form_fills_for_form(
    state: Mapping[str, Any],
    form_id: str,
) -> Dict[str, Any]:
    """Return manual fills restricted to datum ids on one form."""
    multiframespec = get_form_emitted(
        state,
        form_id,
    )
    if not multiframespec:
        return {}

    datums = _collect_form_datums(
        multiframespec
    )
    fills = get_form_fills(state)

    return {
        datum_id: fills[datum_id]
        for datum_id in datums
        if datum_id in fills
    }


# ---------------------------------------------------------------------------
# Structured form-fill views
# ---------------------------------------------------------------------------


def _datum_micros(
    datum: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    micros = datum.get("micros") or []

    if not isinstance(micros, list):
        try:
            micros = list(micros)
        except Exception:
            micros = []

    out: List[Dict[str, Any]] = []
    for micro in micros:
        if isinstance(
            micro,
            Mapping,
        ):
            out.append(dict(micro))

    return out


def _macro_to_micro_value(
    macro: Any,
    micro_name: str,
) -> Any:
    if isinstance(macro, Mapping):
        return macro.get(micro_name)

    if micro_name == "value":
        return macro

    return None


def _classify_sources(
    *,
    prefills_for_form: Mapping[
        str,
        Any,
    ],
    fills_for_form: Mapping[
        str,
        Any,
    ],
    datum_id: str,
) -> Dict[str, bool]:
    """
    Classify whether one datum was supplied through prefills, manual IO, or
    both.
    """
    in_prefills = (
        datum_id
        in prefills_for_form
    )
    in_fills = (
        datum_id
        in fills_for_form
    )

    return {
        "is_prefill_only": bool(
            in_prefills
            and not in_fills
        ),
        "is_io_only": bool(
            in_fills
            and not in_prefills
        ),
        "is_mixed": bool(
            in_prefills
            and in_fills
        ),
        "has_any": bool(
            in_prefills
            or in_fills
        ),
    }


def get_form_fill_info(
    state: Mapping[str, Any],
    form_id: str,
) -> Dict[str, Any]:
    """
    Return a structured browsable fill view for one emitted form.
    """
    multiframespec = get_form_emitted(
        state,
        form_id,
    )
    if not multiframespec:
        return {
            "form_id": str(form_id),
            "datums": {},
        }

    datums = _collect_form_datums(
        multiframespec
    )
    prefills = (
        get_form_prefills_for_form(
            state,
            form_id,
        )
    )
    fills = get_form_fills_for_form(
        state,
        form_id,
    )

    out: Dict[str, Any] = {
        "form_id": str(form_id),
        "datums": {},
    }

    for datum_id, datum in datums.items():
        prefill = prefills.get(
            datum_id
        )
        fill = fills.get(datum_id)

        merged = prefill
        if datum_id in fills:
            merged = fill

        micros = _datum_micros(
            datum
        )
        if not micros:
            micros = [
                {
                    "name": "value",
                }
            ]

        micros_out: Dict[str, Any] = {}
        for micro_spec in micros:
            micro_name = str(
                micro_spec.get("name")
                or "value"
            )
            micros_out[micro_name] = {
                "spec": dict(
                    micro_spec
                ),
                "prefill": (
                    _macro_to_micro_value(
                        prefill,
                        micro_name,
                    )
                ),
                "fill": (
                    _macro_to_micro_value(
                        fill,
                        micro_name,
                    )
                ),
                "merged": (
                    _macro_to_micro_value(
                        merged,
                        micro_name,
                    )
                ),
            }

        out["datums"][datum_id] = {
            "datum": dict(datum),
            "micros": micros_out,
            "prefill": prefill,
            "fill": fill,
            "merged": merged,
            "sources": (
                _classify_sources(
                    prefills_for_form=(
                        prefills
                    ),
                    fills_for_form=fills,
                    datum_id=datum_id,
                )
            ),
        }

    return out


get_form_fills_info = (
    get_form_fill_info
)


def get_form_fills_by_datum(
    state: Mapping[str, Any],
    form_id: str,
    datum_id: str,
    *,
    assert_was_prefill: bool = False,
    assert_was_io_fill: bool = False,
    assert_was_mixed_filled: bool = False,
) -> Dict[str, Any]:
    info = get_form_fill_info(
        state,
        form_id,
    )
    normalized_id = str(datum_id)

    datums = info.get("datums")
    datum = (
        datums.get(normalized_id)
        if isinstance(
            datums,
            Mapping,
        )
        else None
    )
    if not isinstance(
        datum,
        Mapping,
    ):
        return {}

    sources = datum.get("sources") or {}

    if (
        assert_was_prefill
        and not bool(
            sources.get(
                "is_prefill_only"
            )
        )
    ):
        raise AssertionError(
            f"{normalized_id} was "
            "not prefill-only"
        )

    if (
        assert_was_io_fill
        and not bool(
            sources.get("is_io_only")
        )
    ):
        raise AssertionError(
            f"{normalized_id} was "
            "not io-only"
        )

    if (
        assert_was_mixed_filled
        and not bool(
            sources.get("is_mixed")
        )
    ):
        raise AssertionError(
            f"{normalized_id} was "
            "not mixed-filled"
        )

    return dict(datum)


def get_form_fills_by_micro(
    state: Mapping[str, Any],
    form_id: str,
    datum_id: str,
    micro_id: str,
    *,
    assert_was_prefill: bool = False,
    assert_was_io_fill: bool = False,
    assert_was_mixed_filled: bool = False,
) -> Dict[str, Any]:
    datum = get_form_fills_by_datum(
        state,
        form_id,
        datum_id,
        assert_was_prefill=(
            assert_was_prefill
        ),
        assert_was_io_fill=(
            assert_was_io_fill
        ),
        assert_was_mixed_filled=(
            assert_was_mixed_filled
        ),
    )

    micros = datum.get("micros") or {}
    if not isinstance(
        micros,
        Mapping,
    ):
        return {}

    micro = micros.get(
        str(micro_id)
    )
    return (
        dict(micro)
        if isinstance(micro, Mapping)
        else {}
    )


def get_form_fills_by_span(
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    *,
    assert_was_prefill: bool = False,
    assert_was_io_fill: bool = False,
    assert_was_mixed_filled: bool = False,
) -> Dict[str, Any]:
    multiframespec = get_form_emitted(
        state,
        form_id,
    )
    if not multiframespec:
        return {
            "form_id": str(form_id),
            "frame_id": str(frame_id),
            "span_id": str(span_id),
            "datums": {},
        }

    spans = _collect_form_spans(
        multiframespec
    )
    owns = spans.get(
        (
            str(frame_id),
            str(span_id),
        ),
        [],
    )

    info = get_form_fill_info(
        state,
        form_id,
    )
    datums = info.get("datums") or {}

    out: Dict[str, Any] = {
        "form_id": str(form_id),
        "frame_id": str(frame_id),
        "span_id": str(span_id),
        "datums": {},
    }

    if not isinstance(
        datums,
        Mapping,
    ):
        return out

    for datum_id in owns:
        datum = datums.get(datum_id)
        if not isinstance(
            datum,
            Mapping,
        ):
            continue

        sources = (
            datum.get("sources") or {}
        )

        if (
            assert_was_prefill
            and not bool(
                sources.get(
                    "is_prefill_only"
                )
            )
        ):
            raise AssertionError(
                f"{datum_id} was "
                "not prefill-only"
            )

        if (
            assert_was_io_fill
            and not bool(
                sources.get(
                    "is_io_only"
                )
            )
        ):
            raise AssertionError(
                f"{datum_id} was "
                "not io-only"
            )

        if (
            assert_was_mixed_filled
            and not bool(
                sources.get(
                    "is_mixed"
                )
            )
        ):
            raise AssertionError(
                f"{datum_id} was "
                "not mixed-filled"
            )

        out["datums"][datum_id] = (
            dict(datum)
        )

    return out


def get_form_fills_by_frame(
    state: Mapping[str, Any],
    form_id: str,
    frame_id: str,
    *,
    assert_was_prefill: bool = False,
    assert_was_io_fill: bool = False,
    assert_was_mixed_filled: bool = False,
) -> Dict[str, Any]:
    multiframespec = get_form_emitted(
        state,
        form_id,
    )
    if not multiframespec:
        return {
            "form_id": str(form_id),
            "frame_id": str(frame_id),
            "spans": {},
        }

    spans = _collect_form_spans(
        multiframespec
    )
    out: Dict[str, Any] = {
        "form_id": str(form_id),
        "frame_id": str(frame_id),
        "spans": {},
    }

    for (
        candidate_frame_id,
        candidate_span_id,
    ), _owns in spans.items():
        if (
            candidate_frame_id
            != str(frame_id)
        ):
            continue

        out["spans"][
            candidate_span_id
        ] = get_form_fills_by_span(
            state,
            form_id,
            candidate_frame_id,
            candidate_span_id,
            assert_was_prefill=(
                assert_was_prefill
            ),
            assert_was_io_fill=(
                assert_was_io_fill
            ),
            assert_was_mixed_filled=(
                assert_was_mixed_filled
            ),
        )

    return out


# ---------------------------------------------------------------------------
# Generic active-span resolution
# ---------------------------------------------------------------------------


_ACTIVE_SPAN_RECORD_CORE_KEYS = frozenset(
    {
        "current_span",
        "frame_id",
        "span_id",
        "qualified_span_id",
        "owns",
        "span",
    }
)


def _normalize_requested_span_keys(
    include_span_keys: Iterable[str],
) -> Tuple[str, ...]:
    """
    Normalize arbitrary caller-requested span extension keys.

    Requested keys are copied without semantic interpretation. They may not
    overwrite the normalized structural record.
    """
    out: List[str] = []
    seen: set[str] = set()

    for raw_key in include_span_keys:
        key = str(raw_key).strip()
        if not key:
            raise ValueError(
                "include_span_keys contains "
                "an empty key"
            )

        if (
            key
            in _ACTIVE_SPAN_RECORD_CORE_KEYS
        ):
            raise ValueError(
                "include_span_keys may not "
                "override normalized active-"
                f"span key {key!r}"
            )

        if key in seen:
            continue

        seen.add(key)
        out.append(key)

    return tuple(out)


def get_active_span_record_from_ctx(
    ctx: Mapping[str, Any],
    *,
    include_span_keys: Iterable[str] = (),
) -> Optional[Dict[str, Any]]:
    """
    Resolve the currently active span from a UI/session context.

    App Table normalizes only its structural information:

        {
            "current_span": "FRAME:S1" | "S1",
            "frame_id": "FRAME",
            "span_id": "S1",
            "qualified_span_id": "FRAME:S1",
            "owns": [...],
            "span": {...},
        }

    Higher layers may request arbitrary opaque span-extension keys:

        get_active_span_record_from_ctx(
            ctx,
            include_span_keys=(
                "some_extension",
                "another_extension",
            ),
        )

    The returned record then also contains:

        {
            "some_extension": span.get("some_extension"),
            "another_extension": span.get("another_extension"),
        }

    This helper does not know the meaning, type, or policy associated with any
    requested extension key.

    Returns None when there is no active span or no compatible form specification.
    """
    if not isinstance(ctx, Mapping):
        return None

    requested_keys = (
        _normalize_requested_span_keys(
            include_span_keys
        )
    )

    current_span = str(
        ctx.get("current_span")
        or ctx.get(
            "current_span_id"
        )
        or ""
    ).strip()
    if not current_span:
        return None

    multiframespec = ctx.get("multiframespec")
    if not isinstance(
        multiframespec,
        Mapping,
    ):
        return None

    for frame in list(
        multiframespec.get("frames") or []
    ):
        if not isinstance(
            frame,
            Mapping,
        ):
            continue

        frame_id = str(
            frame.get("id")
            or frame.get("name")
            or ""
        ).strip()

        for span in list(
            frame.get("spans") or []
        ):
            if not isinstance(
                span,
                Mapping,
            ):
                continue

            span_id = str(
                span.get("id") or ""
            ).strip()
            if not span_id:
                continue

            qualified_span_id = (
                f"{frame_id}:{span_id}"
                if frame_id
                else span_id
            )

            if current_span not in {
                span_id,
                qualified_span_id,
            }:
                continue

            owns = [
                str(value)
                for value in list(
                    span.get("owns")
                    or []
                )
                if str(
                    value or ""
                ).strip()
            ]

            record: Dict[str, Any] = {
                "current_span": (
                    current_span
                ),
                "frame_id": frame_id,
                "span_id": span_id,
                "qualified_span_id": (
                    qualified_span_id
                ),
                "owns": owns,
                "span": dict(span),
            }

            for key in requested_keys:
                record[key] = span.get(key)

            return record

    return None


# ---------------------------------------------------------------------------
# Public fill snapshot
# ---------------------------------------------------------------------------


def get_fills_snapshot_from_app_table_state(
    state: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Return the current merged macro fill snapshot.

    Prefills are applied first. Manual fills override them.
    """
    merged: Dict[str, Any] = {}

    if not isinstance(
        state,
        Mapping,
    ):
        return merged

    prefills = state.get(
        KEY_FORM_PREFILLS
    )
    if isinstance(prefills, Mapping):
        merged.update(
            {
                str(key): value
                for key, value
                in dict(prefills).items()
            }
        )

    fills = state.get(
        KEY_FORM_FILLS
    )
    if isinstance(fills, Mapping):
        merged.update(
            {
                str(key): value
                for key, value
                in dict(fills).items()
            }
        )

    return merged
