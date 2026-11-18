from __future__ import annotations

from typing import Any, Dict, List, Mapping


from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    undo_lifecycle_patch_v1,
    get_latest_engine_form_page_data_read,
    get_engine_form_page_structural_epoch_from_id,
    get_engine_form_page_epoch_from_id,
)



from __datomatonTM import explode_datum_widget

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)

from __exceptions.engine import FatalEngineError
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_FORM_FILLS,
    KEY_FORM_PREFILLS,
    KEY_FORMS_EMITTED_ORDER,
    KEY_PENDING_FORM_ID,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fills,
    get_form_prefills,
)

from __multiframespecTM.api import (
    build_multiframespec_scoped_datum_fill_map,
    compile_multiframespec_manual_render_bundle,
)


from __multiframespecTM.api import (
    collect_multiframespec_datum_ids,
)


class ManualIOTapeMechanicsMixin:
    """
    Manual-step IO implementation and runtime-only manual-IO state.

    Runtime-only fields owned by this mixin:
      - _manual_io_cache_v1
      - engine_datums_on_span_inflight

    These are intentionally not durable state. They are initialized by the
    concrete engine during construction and snapshot restore.
    """

    def _ensure_manual_io_runtime_state_v1(self) -> None:
        """
        Defensive repair for engines created by older restore paths/tests.

        The normal path calls init_manual_io_runtime_state_v1(), but this keeps
        the mixin robust if a test uses cls.__new__ or a legacy snapshot restore
        skipped transient initialization.
        """
        if not isinstance(
            getattr(self, "_manual_io_cache_v1", None),
            dict,
        ):
            self._manual_io_cache_v1 = {}

        if not isinstance(
            getattr(
                self,
                "engine_datums_on_span_inflight",
                None,
            ),
            set,
        ):
            self.engine_datums_on_span_inflight = set()

    def _begin_datum_lifecycle_processing_v1(
        self,
        datum_ids: List[str],
    ) -> tuple[str, ...]:
        self._ensure_manual_io_runtime_state_v1()

        ids = tuple(
            sorted(
                {
                    str(x)
                    for x in list(datum_ids or [])
                    if str(x)
                }
            )
        )
        if not ids:
            return ()

        overlap = sorted(
            set(ids).intersection(
                self.engine_datums_on_span_inflight
            )
        )
        if overlap:
            raise FatalEngineError(
                "datum lifecycle reexplosion already in progress for datum(s): "
                f"{overlap}"
            )

        self.engine_datums_on_span_inflight.update(ids)
        return ids

    def _end_datum_lifecycle_processing_v1(
        self,
        token: tuple[str, ...],
    ) -> None:
        self._ensure_manual_io_runtime_state_v1()

        ids = tuple(
            str(x)
            for x in list(token or [])
            if str(x)
        )
        if not ids:
            return

        for datum_id in ids:
            self.engine_datums_on_span_inflight.discard(
                datum_id
            )

    def _get_or_compile_manual_io_cache_v1(
        self,
        *,
        multiframespec: Mapping[str, Any],
        form_id: str,
        frame_id: str,
        span_id: str,
        datum_widgets_on_this_span: List[str],
    ) -> Mapping[str, Any]:
        """
        Return the runtime-only compiled manual IO cache.
        """
        cache_store = getattr(
            self,
            "_manual_io_cache_v1",
            None,
        )
        if not isinstance(cache_store, dict):
            cache_store = {}
            setattr(self, "_manual_io_cache_v1", cache_store)

        cache_key = self.manual_io_cache_key_v1(
            form_id=form_id,
            multiframespec=multiframespec,
        )
        cache = cache_store.get(cache_key)

        if isinstance(cache, Mapping):
            return cache

        effective_multiframespec = (
            hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
                multiframespec=multiframespec,
                state=self.state,
                form_id=str(form_id),
            )
        )

        fv = build_multiframespec_scoped_datum_fill_map(
            multiframespec=effective_multiframespec,
            external_prefills_by_datum_id=get_form_prefills(self.state),
            external_fills_by_datum_id=get_form_fills(self.state),
        )

        fv.update(
            self.manual_get_latest_engine_form_page_data_read(
                form_id=str(form_id),
                frame_id=str(frame_id),
                span_id=str(span_id),
            )
        )

        cache = compile_multiframespec_manual_render_bundle(
            multiframespec=effective_multiframespec,
            form_id=form_id,
            session_id=str(self.session_id),
            datum_fill_values=fv,
            frame_id=frame_id,
            span_id=span_id,
            target_datum_ids=tuple(datum_widgets_on_this_span),
            render_metadata=dict(self.session_metadata),
            kind="MANUALFILLNEEDEDSTEP",
        )
        cache_store[cache_key] = cache
        return cache

    def _cached_manual_datum_widget_fills_v1(
        self,
        *,
        cache: Mapping[str, Any],
        multiframespec: Mapping[str, Any],
        copy_values: bool = True,
    ) -> Dict[str, Any] | Mapping[str, Any]:
        base = cache.get("base_ui_ctx")
        if isinstance(base, Mapping):
            fv = base.get("datum_widget_fills")
            if isinstance(fv, Mapping):
                return dict(fv) if copy_values else fv

        built = build_multiframespec_scoped_datum_fill_map(
            multiframespec=(
                hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
                    multiframespec=multiframespec,
                    state=self.state,
                    form_id=str(
                        self.state.get(KEY_PENDING_FORM_ID)
                        or multiframespec.get("app_form_id")
                        or ""
                    ),
                )
            ),
            external_prefills_by_datum_id=get_form_prefills(self.state),
            external_fills_by_datum_id=get_form_fills(self.state),
        )
        return dict(built) if copy_values else built

    def _update_manual_cache_datum_widget_fills_v1(
        self,
        *,
        cache: Mapping[str, Any],
        committed: Mapping[str, Any],
    ) -> None:
        if not committed or not isinstance(cache, Mapping):
            return

        base = cache.get("base_ui_ctx")
        if not isinstance(base, dict):
            return

        fv = base.get("datum_widget_fills")
        if not isinstance(fv, dict):
            fv = {}
            base["datum_widget_fills"] = fv

        for k, v in committed.items():
            fv[str(k)] = v

    def _refresh_manual_cache_datum_widget_fills_v1(
        self,
        *,
        cache: Mapping[str, Any],
        multiframespec: Mapping[str, Any],
        form_id: str,
        frame_id: str,
        span_id: str,
    ) -> Dict[str, Any]:
        effective_multiframespec = (
            hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
                multiframespec=multiframespec,
                state=self.state,
                form_id=str(form_id),
            )
        )

        fv = build_multiframespec_scoped_datum_fill_map(
            multiframespec=effective_multiframespec,
            external_prefills_by_datum_id=get_form_prefills(self.state),
            external_fills_by_datum_id=get_form_fills(self.state),
        )

        fv.update(
            self.manual_get_latest_engine_form_page_data_read(
                form_id=str(form_id),
                frame_id=frame_id,
                span_id=span_id,
            )
        )

        if isinstance(cache, Mapping):
            base = cache.get("base_ui_ctx")
            if isinstance(base, dict):
                base["datum_widget_fills"] = dict(fv)

        return dict(fv)

    def _manual_ctx_state_summary_v1(
        self,
        *,
        pending_multiframespec: Mapping[str, Any],
        datum_widget_fills: Mapping[str, Any],
    ) -> Dict[str, Any]:
        policy_fn = getattr(self, "manual_io_policy_v1", None)
        policy = policy_fn() if callable(policy_fn) else {}

        include_global_fill_keys = bool(
            policy.get(
                "include_global_fill_keys_in_ctx",
                False,
            )
        )
        include_field_value_keys = bool(
            policy.get(
                "include_field_value_keys_in_ctx",
                False,
            )
        )
        include_forms_emitted_order = bool(
            policy.get(
                "include_forms_emitted_order_in_ctx",
                True,
            )
        )

        if include_global_fill_keys:
            prefill_keys = sorted(
                str(k)
                for k in get_form_prefills(self.state).keys()
            )
            fill_keys = sorted(
                str(k)
                for k in get_form_fills(self.state).keys()
            )
        else:
            current_ids = collect_multiframespec_datum_ids(
                pending_multiframespec
            )
            prefills = get_form_prefills(self.state)
            fills = get_form_fills(self.state)

            prefill_keys = [
                fid
                for fid in current_ids
                if fid in prefills
            ]
            fill_keys = [
                fid
                for fid in current_ids
                if fid in fills
            ]

        forms_order_raw = (
            self.state.get(KEY_FORMS_EMITTED_ORDER) or []
        )
        forms_order = (
            list(forms_order_raw)
            if isinstance(forms_order_raw, list)
            else []
        )

        out: Dict[str, Any] = {
            "pending_multiframespec": True,
            "pending_multiframespec_id": self.state.get(
                KEY_PENDING_FORM_ID
            ),
            "form_prefills_keys": prefill_keys,
            "form_fills_keys": fill_keys,
            "datum_widget_fills_count": len(datum_widget_fills),
            "forms_emitted_count": len(forms_order),
            "datum_lifecycle_epoch": (
                get_engine_form_page_epoch_from_id(
                    self.state,
                    str(
                        self.state.get(KEY_PENDING_FORM_ID)
                        or pending_multiframespec.get("app_form_id")
                        or ""
                    ),
                )
            ),
        }

        if include_field_value_keys:
            out["datum_widget_fills_keys"] = sorted(
                str(k)
                for k in datum_widget_fills.keys()
            )

        if include_forms_emitted_order:
            out["forms_emitted_order"] = forms_order

        return out
    
    def init_manual_io_runtime_state_v1(self) -> None:
        """
        Initialize transient/manual-IO-only runtime state.

        This must be called by the concrete engine from:
          - __init__
          - from_snapshot after cls.__new__(cls)

        None of these fields belongs in persisted state or snapshots.
        """
        self._manual_io_cache_v1: Dict[str, Any] = {}
        self.engine_datums_on_span_inflight: set[str] = set()

    def clear_manual_io_cache_v1(self) -> None:
        """
        Clear runtime-only compiled manual UI/cache state.

        This is intentionally owned by the manual-IO mixin because only the
        manual rendering/fill/lifecycle path understands the cache contents.
        """
        try:
            self._manual_io_cache_v1.clear()
        except Exception:
            self._manual_io_cache_v1 = {}

    def manual_io_policy_v1(self) -> Dict[str, Any]:
        """
        Manual-IO policy parsed from session_metadata["manual_io"].

        Kept in this mixin because all consumers are manual-IO render/fill/cache
        paths, plus thin engine context summaries that delegate to this policy.
        
        For the surface defiition, see: 
        think-backend/src/surfaces/flow_controlled_session_args/sesh_metadata_surface.py
        """
        meta = (
            self.session_metadata
            if isinstance(self.session_metadata, Mapping)
            else {}
        )
        raw = meta.get("manual_io")
        row = (
            dict(raw or {})
            if isinstance(raw, Mapping)
            else {}
        )

        persistence = (
            str(row.get("persistence") or "boundary")
            .strip()
            .lower()
            or "boundary"
        )
        if persistence not in {
            "eager",
            "boundary",
            "disabled",
        }:
            persistence = "boundary"

        def _bool(
            key: str,
            default: bool,
        ) -> bool:
            return bool(row.get(key, default))

        def _cap_int(
            key: str,
            default: int,
        ) -> int:
            raw_v = row.get(key, default)
            if raw_v is None:
                return 0
            try:
                iv = int(raw_v)
            except Exception:
                iv = int(default)
            return max(0, iv)

        return {
            "include_full_multiframespec_in_ctx": _bool(
                "include_full_multiframespec_in_ctx",
                True,
            ),
            "persistence": persistence,
            "profile": _bool(
                "profile",
                False,
            ),
            "include_global_fill_keys_in_ctx": _bool(
                "include_global_fill_keys_in_ctx",
                False,
            ),
            "include_field_value_keys_in_ctx": _bool(
                "include_field_value_keys_in_ctx",
                False,
            ),
            "include_forms_emitted_order_in_ctx": _bool(
                "include_forms_emitted_order_in_ctx",
                True,
            ),
            "max_fields_per_submit": _cap_int(
                "max_fields_per_submit",
                1024,
            ),
            "max_payload_chars": _cap_int(
                "max_payload_chars",
                2_000_000,
            ),
        }

    def manual_get_latest_engine_form_page_data_read(
        self,
        *,
        form_id: str,
        frame_id: str,
        span_id: str,
    ) -> Dict[str, Any]:
        """
        Engine-facing IO boundary for datum-lifecycle working value overlays.

        The engine owns cursor/undo orchestration, but it should not import
        lower lifecycle helpers directly. Keep lifecycle read semantics behind
        the manual-IO mixin so the engine depends only on the mixin contract.
        """
        return get_latest_engine_form_page_data_read(
            state=self.state,
            form_id=str(form_id),
            frame_id=str(frame_id),
            span_id=str(span_id),
        )

    def undo_lifecycle_patch_v1(
        self,
        undo: Mapping[str, Any],
    ) -> None:
        """
        Engine-facing IO boundary for undoing datum-lifecycle patches.
        """
        undo_lifecycle_patch_v1(
            self.state,
            undo,
        )

    def manual_io_cache_key_v1(
        self,
        *,
        form_id: str,
        multiframespec: Mapping[str, Any],
    ) -> str:
        """
        Runtime-only cache key for active pending form structure.
        """
        fid = (
            str(form_id or "").strip()
            or str(multiframespec.get("app_form_id") or "__pending__")
        )
        structural_epoch = (
            get_engine_form_page_structural_epoch_from_id(
                self.state,
                fid,
            )
        )
        return f"{fid}:qstruct:{structural_epoch}"
