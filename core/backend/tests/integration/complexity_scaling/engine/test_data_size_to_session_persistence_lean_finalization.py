"""
Data-weight regression tests for session persistence lean-finalization.

These tests are intentionally focused on *shape* and *growth law*, not exact byte
counts. The purpose is to catch regressions where live/persisted sessions start
carrying historical full copies of forms, prefills, context, or emitted-form
maps in undo records, redo records, runtime indexes, or snapshots.

Core invariants covered here:

1. Emitting many forms must not cause exec_records to retain historical full
   forms_emitted / forms_emitted_order / form_prefills buckets.

2. Persisted snapshot-like payload size should grow approximately linearly with
   emitted topology and submitted values, not quadratically from repeated
   whole-bucket undo patches.

3. Snapshot state should keep only a bounded forms_emitted topology window when
   session_storage.forms_emitted_snapshot_window is configured.

4. Runtime write index snapshots must remain lean and must not persist heavy
   sidecars, tombstones, raw values, or position sidecars.

5. Redo stack payloads should be bounded by session_storage policy.

Important boundary note:

These tests deliberately model the multiframespec-emission storage law with small
helpers rather than constructing a full runtime program for every case. They
test the data contract at the storage boundary:

    current state may hold the current live topology;
    undo history must not hold historical whole-bucket copies;
    durable snapshot projection must trim runtime-only/heavy structures.

Pedagogical law:

    Incremental undo may store affected keys.
    Incremental undo must not store historical full buckets or heavy values.

For example, this is acceptable and necessary:

    {"k": "form_0000.field_0", "missing": true, "v": null}

The key tells undo what to delete. The scalable win is that the undo record does
not carry the full previous form_prefills bucket, multiframespec body, label/help text,
metadata payload, or prefill value body.
"""

from __future__ import annotations

import json
import pickle
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Dict, List, Tuple

from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_FORM_FILLS,
    KEY_FORM_PREFILLS,
    KEY_FORMS_EMITTED,
    KEY_FORMS_EMITTED_ORDER,
    KEY_PENDING_FORM,
    KEY_PENDING_FORM_ID,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_writing import (
    _append_list_item_patch,
    _apply_mapping_item_patch,
    _apply_patch,
    _undo_patch,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    runtime_write_index_snapshot_view_v1,
)


def _compact_json_size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), sort_keys=True, default=repr))


def _recursive_size(obj: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()

    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)

    total = sys.getsizeof(obj)

    if isinstance(obj, Mapping):
        for key, value in obj.items():
            total += _recursive_size(key, seen)
            total += _recursive_size(value, seen)
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for item in obj:
            total += _recursive_size(item, seen)
    elif hasattr(obj, "__dict__"):
        total += _recursive_size(vars(obj), seen)

    return total


def _make_multiframespec(
    form_id: str,
    field_count: int = 3,
    payload_chars: int = 64,
) -> Dict[str, Any]:
    fields = []
    for idx in range(field_count):
        fields.append(
            {
                "id": f"{form_id}.field_{idx}",
                "label": f"Field {idx}",
                "type": "text",
                "required": False,
                "help": "h" * payload_chars,
            }
        )

    return {
        "id": form_id,
        "title": f"Form {form_id}",
        "fields": fields,
        "metadata": {
            "source": "test",
            "payload": "m" * payload_chars,
        },
    }


def _make_prefills(
    form_id: str,
    field_count: int = 3,
    payload_chars: int = 64,
) -> Dict[str, Any]:
    return {
        f"{form_id}.field_{idx}": {
            "value": "v" * payload_chars,
            "source": "test",
        }
        for idx in range(field_count)
    }


def _bucket_projection(state: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Compare only the durable emission buckets governed by the incremental
    mapping/list undo helpers.

    Pending-form cursor fields are live-controller state. In production they are
    handled by the surrounding state patch and snapshot rehydration policy; this
    storage-law sheet isolates the heavy historical bucket issue.
    """

    return {
        KEY_FORMS_EMITTED: json.loads(json.dumps(state.get(KEY_FORMS_EMITTED) or {})),
        KEY_FORMS_EMITTED_ORDER: json.loads(json.dumps(state.get(KEY_FORMS_EMITTED_ORDER) or [])),
        KEY_FORM_PREFILLS: json.loads(json.dumps(state.get(KEY_FORM_PREFILLS) or {})),
    }


def _emit_form_incrementally(
    state: Dict[str, Any],
    form_id: str,
    *,
    field_count: int = 3,
    payload_chars: int = 64,
) -> Dict[str, Any]:
    """
    Model the patched routed multiframespec-emission storage law:

    - forms_emitted is updated by mapping-item patch.
    - forms_emitted_order is updated by append-list patch.
    - form_prefills is updated by mapping-item patch.

    The returned undo object is intentionally what the heavy bucket part of an
    ExecRecord undo_patch should carry. It must not retain previous whole
    forms_emitted / forms_emitted_order / form_prefills buckets.
    """

    multiframespec = _make_multiframespec(form_id, field_count=field_count, payload_chars=payload_chars)
    prefills = _make_prefills(form_id, field_count=field_count, payload_chars=payload_chars)

    undo: Dict[str, Any] = {}

    undo.update(
        _apply_mapping_item_patch(
            state,
            bucket_key=KEY_FORMS_EMITTED,
            items={form_id: multiframespec},
        )
    )
    undo.update(
        _append_list_item_patch(
            state,
            bucket_key=KEY_FORMS_EMITTED_ORDER,
            value=form_id,
        )
    )
    undo.update(
        _apply_mapping_item_patch(
            state,
            bucket_key=KEY_FORM_PREFILLS,
            items=prefills,
        )
    )

    # Live cursor fields are kept in state so snapshot-window tests can model
    # pending-form retention. They are intentionally outside this incremental
    # bucket undo model.
    state[KEY_PENDING_FORM_ID] = form_id
    state[KEY_PENDING_FORM] = multiframespec

    return undo


def _emit_form_naively_whole_bucket(
    state: Dict[str, Any],
    form_id: str,
    *,
    field_count: int = 3,
    payload_chars: int = 64,
) -> Dict[str, Any]:
    """
    Reference model for the pre-patch anti-pattern.

    This is not desired behavior. It exists to keep the regression test honest:
    full-bucket state patches grow undo records with previous copies of
    forms_emitted / forms_emitted_order / form_prefills.
    """

    multiframespec = _make_multiframespec(form_id, field_count=field_count, payload_chars=payload_chars)
    prefills = _make_prefills(form_id, field_count=field_count, payload_chars=payload_chars)

    forms_emitted = dict(state.get(KEY_FORMS_EMITTED) or {})
    forms_emitted[form_id] = multiframespec

    order = list(state.get(KEY_FORMS_EMITTED_ORDER) or [])
    order.append(form_id)

    merged_prefills = dict(state.get(KEY_FORM_PREFILLS) or {})
    merged_prefills.update(prefills)

    patch = {
        KEY_FORMS_EMITTED: forms_emitted,
        KEY_FORMS_EMITTED_ORDER: order,
        KEY_FORM_PREFILLS: merged_prefills,
        KEY_PENDING_FORM_ID: form_id,
        KEY_PENDING_FORM: multiframespec,
    }
    return _apply_patch(state, patch)


def _build_exec_records(
    emitter: Callable[..., Dict[str, Any]],
    count: int,
    *,
    field_count: int = 3,
    payload_chars: int = 64,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state: Dict[str, Any] = {}
    undo_records: List[Dict[str, Any]] = []

    for idx in range(count):
        form_id = f"form_{idx:04d}"
        undo_records.append(
            emitter(
                state,
                form_id,
                field_count=field_count,
                payload_chars=payload_chars,
            )
        )

    return state, undo_records


def _snapshot_state_with_window(state: Dict[str, Any], window: int) -> Dict[str, Any]:
    """
    Local model of Engine._snapshot_state_v1 forms-window behavior.

    It validates the data law without requiring a fixture-heavy runtime program.
    """

    out = dict(state)

    forms = dict(out.get(KEY_FORMS_EMITTED) or {})
    order = list(out.get(KEY_FORMS_EMITTED_ORDER) or [])

    pending_multiframespec_id = out.get(KEY_PENDING_FORM_ID)
    keep_ids = list(order[-max(window, 0) :]) if window > 0 else []

    if pending_multiframespec_id and pending_multiframespec_id not in keep_ids:
        keep_ids.append(pending_multiframespec_id)

    compact_forms = {fid: forms[fid] for fid in keep_ids if fid in forms}
    compact_order = [fid for fid in order if fid in compact_forms]

    out[KEY_FORMS_EMITTED] = compact_forms
    out[KEY_FORMS_EMITTED_ORDER] = compact_order

    pending = out.get(KEY_PENDING_FORM)
    if pending_multiframespec_id and pending == compact_forms.get(pending_multiframespec_id):
        out[KEY_PENDING_FORM] = None

    return out


def _make_runtime_write_index_with_sidecars() -> Dict[str, Any]:
    """
    Build a deliberately hostile runtime index.

    Production rows should already be lean, but the snapshot projection boundary
    should still be defensive: no nested sidecars, tombstones, raw values, or
    position indexes should survive into the durable view.
    """

    return {
        "version": 1,
        "by_ref": {
            "frame:alpha": {
                "ref": "frame:alpha",
                "field": "alpha",
                "preview": "small",
                "sidecar": {
                    "raw_value": "x" * 10_000,
                    "ctx": {"huge": "y" * 10_000},
                },
                "tombstone": False,
            }
        },
        "sidecars": {
            "frame:alpha": {
                "raw_value": "z" * 10_000,
            }
        },
        "tombstones": {
            "old": {
                "raw_value": "dead" * 10_000,
            }
        },
        "list_positions": {
            "__invocation_order__": {
                "1": 0,
            }
        },
    }


def _assert_forbidden_keys_absent(obj: Any, forbidden: set[str]) -> None:
    stack = [obj]
    seen: set[int] = set()

    while stack:
        cur = stack.pop()
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            for key, value in cur.items():
                assert str(key) not in forbidden
                stack.append(value)
            continue

        if isinstance(cur, Sequence) and not isinstance(cur, (str, bytes, bytearray)):
            stack.extend(cur)


def _walk_mapping_undo_items(obj: Any) -> List[Mapping[str, Any]]:
    """
    Return every item stored by the incremental mapping-item undo representation.

    The expected lean shape is item metadata like:

        {"k": "...", "missing": true, "v": null}

    The key is allowed and necessary. For newly inserted keys, the previous value
    should be absent/null rather than a heavy form/prefill value.
    """

    found: List[Mapping[str, Any]] = []
    stack = [obj]
    seen: set[int] = set()

    while stack:
        cur = stack.pop()
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            if cur.get("kind") == "__app_table_mapping_items_undo_v1__":
                items = cur.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, Mapping):
                            found.append(item)

            stack.extend(cur.values())
            continue

        if isinstance(cur, Sequence) and not isinstance(cur, (str, bytes, bytearray)):
            stack.extend(cur)

    return found


def _assert_incremental_undo_contains_no_heavy_previous_values(
    undo: Mapping[str, Any],
) -> None:
    """
    Incremental undo may carry affected keys. It must not carry full previous
    values for newly inserted forms/prefills.

    This is the key teaching point of the sheet:

        "form_0000.field_0" is okay.
        {"value": "...", "source": "..."} is not okay.
        multiframespec labels/help/metadata/payloads are not okay.
    """

    rendered = json.dumps(undo, sort_keys=True, default=repr)

    assert KEY_FORMS_EMITTED in rendered
    assert KEY_FORMS_EMITTED_ORDER in rendered
    assert KEY_FORM_PREFILLS in rendered

    assert "__app_table_mapping_items_undo_v1__" in rendered
    assert "__app_table_list_append_undo_v1__" in rendered

    # Heavy multiframespec/value-content signals are forbidden in undo history.
    assert "Field 0" not in rendered
    assert '"label"' not in rendered
    assert '"help"' not in rendered
    assert '"metadata"' not in rendered
    assert '"payload"' not in rendered
    assert '"value"' not in rendered
    assert '"source"' not in rendered

    # For this test's new insertions, all mapping undo rows should delete keys on
    # undo rather than restore prior heavy values.
    for item in _walk_mapping_undo_items(undo):
        assert "k" in item
        assert item.get("missing") is True
        assert item.get("v") is None


def test_snapshot_exec_records_do_not_store_full_historical_forms_or_prefills() -> None:
    """
    The patched multiframespec bucket path should store tiny incremental undo records.

    Important nuance:

    Incremental undo must retain affected keys such as "form_0000.field_0";
    otherwise undo could not delete newly inserted prefill entries. The scalable
    law is that undo records must not retain multiframespec payloads, prefill values,
    or historical whole-bucket copies.
    """

    form_count = 80
    field_count = 4
    payload_chars = 96

    lean_state, lean_undos = _build_exec_records(
        _emit_form_incrementally,
        form_count,
        field_count=field_count,
        payload_chars=payload_chars,
    )
    naive_state, naive_undos = _build_exec_records(
        _emit_form_naively_whole_bucket,
        form_count,
        field_count=field_count,
        payload_chars=payload_chars,
    )

    assert len(lean_state[KEY_FORMS_EMITTED]) == form_count
    assert len(naive_state[KEY_FORMS_EMITTED]) == form_count

    lean_undo_bytes = _compact_json_size(lean_undos)
    naive_undo_bytes = _compact_json_size(naive_undos)

    # The exact ratio is intentionally loose. The invariant is shape/growth law,
    # not a brittle byte count.
    assert lean_undo_bytes < naive_undo_bytes * 0.20

    for undo in lean_undos:
        _assert_incremental_undo_contains_no_heavy_previous_values(undo)

    rendered_all = json.dumps(lean_undos, sort_keys=True, default=repr)

    # Keys are expected and necessary.
    assert "form_0000.field_0" in rendered_all

    # Heavy historical multiframespec/value bodies are not.
    assert "Form form_0000" not in rendered_all
    assert "Field 0" not in rendered_all
    assert '"payload"' not in rendered_all
    assert '"value"' not in rendered_all


def test_incremental_undo_restores_form_emission_buckets_exactly() -> None:
    """
    The lean undo representation must still be correct for the storage buckets it
    owns.

    Pending-form cursor fields are tested by snapshot rehydration/integration
    paths; the incremental helpers own the emitted/prefill/order buckets.
    """

    state: Dict[str, Any] = {}

    before = _bucket_projection(state)
    undo_a = _emit_form_incrementally(state, "form_a", field_count=2, payload_chars=16)

    after_a = _bucket_projection(state)
    undo_b = _emit_form_incrementally(state, "form_b", field_count=2, payload_chars=16)

    assert list(state[KEY_FORMS_EMITTED_ORDER]) == ["form_a", "form_b"]
    assert "form_a" in state[KEY_FORMS_EMITTED]
    assert "form_b" in state[KEY_FORMS_EMITTED]

    _undo_patch(state, undo_b)

    assert _bucket_projection(state) == after_a

    _undo_patch(state, undo_a)

    assert _bucket_projection(state) == before


def test_persisted_snapshot_growth_is_not_quadratic_in_emitted_forms() -> None:
    """
    Snapshot-like persisted payload growth must remain approximately linear.

    This test models the persisted shape as:

    - current state
    - exec_records containing undo patches

    The old full-bucket undo behavior has quadratic growth because every new
    emission stores copies of all previous forms/prefills. The patched behavior
    stores only item-level undo metadata.
    """

    sizes: List[Tuple[int, int]] = []

    for count in (20, 40, 80, 160):
        state, undos = _build_exec_records(
            _emit_form_incrementally,
            count,
            field_count=4,
            payload_chars=128,
        )

        snapshot_like = {
            "state": _snapshot_state_with_window(state, window=32),
            "exec_records": [
                {
                    "step_id": f"step_{idx}",
                    "undo_patch": undo,
                    "inserted_steps": [],
                    "index_seq": idx,
                    "redo_action": None,
                }
                for idx, undo in enumerate(undos)
            ],
            "redo_stack_v1": [],
            "program": [],
        }

        sizes.append((count, _compact_json_size(snapshot_like)))

    by_count = dict(sizes)

    growth_20_to_40 = by_count[40] / by_count[20]
    growth_40_to_80 = by_count[80] / by_count[40]
    growth_80_to_160 = by_count[160] / by_count[80]

    assert growth_20_to_40 < 2.75
    assert growth_40_to_80 < 2.75
    assert growth_80_to_160 < 2.75

    assert growth_80_to_160 < growth_40_to_80 + 0.50


def test_forms_emitted_snapshot_window_keeps_recent_topology_and_pending_multiframespec() -> None:
    """
    Snapshot state should retain a bounded emitted-form topology window.

    Live state can hold all emitted forms needed by the running controller.
    Persistence should not have to carry every historical multiframespec forever.
    """

    state, _undos = _build_exec_records(
        _emit_form_incrementally,
        50,
        field_count=3,
        payload_chars=80,
    )

    state[KEY_PENDING_FORM_ID] = "form_0010"
    state[KEY_PENDING_FORM] = state[KEY_FORMS_EMITTED]["form_0010"]

    compact = _snapshot_state_with_window(state, window=8)

    forms = compact[KEY_FORMS_EMITTED]
    order = compact[KEY_FORMS_EMITTED_ORDER]

    assert len(forms) == 9
    assert "form_0010" in forms
    assert order[-8:] == [f"form_{idx:04d}" for idx in range(42, 50)]

    assert compact[KEY_PENDING_FORM_ID] == "form_0010"
    assert compact[KEY_PENDING_FORM] is None


def test_forms_emitted_snapshot_window_zero_keeps_only_pending_multiframespec() -> None:
    """
    A zero window is a valid aggressive policy.

    Even with zero historical topology, the pending form must remain resumable.
    """

    state, _undos = _build_exec_records(
        _emit_form_incrementally,
        12,
        field_count=2,
        payload_chars=24,
    )

    state[KEY_PENDING_FORM_ID] = "form_0007"
    state[KEY_PENDING_FORM] = state[KEY_FORMS_EMITTED]["form_0007"]

    compact = _snapshot_state_with_window(state, window=0)

    assert list(compact[KEY_FORMS_EMITTED]) == ["form_0007"]
    assert compact[KEY_FORMS_EMITTED_ORDER] == ["form_0007"]
    assert compact[KEY_PENDING_FORM] is None


def test_runtime_write_index_snapshot_view_drops_sidecars_tombstones_and_raw_values() -> None:
    """
    Runtime write index persistence must keep refs/previews, not heavy sidecars.

    This guards the backend session blob from retaining full values through the
    index when only lookup summaries are needed.

    The fixture intentionally places forbidden runtime-only fields at multiple
    depths. Snapshot projection should deep-strip them defensively.
    """

    raw = _make_runtime_write_index_with_sidecars()
    compact = runtime_write_index_snapshot_view_v1(raw)

    rendered = json.dumps(compact, sort_keys=True, default=repr)

    assert "frame:alpha" in rendered
    assert "preview" in rendered

    _assert_forbidden_keys_absent(
        compact,
        {
            "sidecar",
            "sidecars",
            "tombstone",
            "tombstones",
            "raw_value",
            "list_positions",
        },
    )

    assert "x" * 256 not in rendered
    assert "y" * 256 not in rendered
    assert "z" * 256 not in rendered
    assert "dead" * 64 not in rendered


def test_redo_payload_policy_drops_oversized_manual_payloads() -> None:
    """
    Local policy-level regression test for redo payload bounding.

    The engine patch should use the same law: JSON-dead action payloads larger
    than session_storage.redo_action_max_payload_chars are not retained in undo
    history or redo stacks.
    """

    cap = 1_024

    small_action = {
        "kind": "manual_step",
        "fill": {
            "field": "small",
            "value": "ok",
        },
    }
    large_action = {
        "kind": "manual_step",
        "fill": {
            "field": "large",
            "value": "x" * (cap * 4),
        },
    }

    def bounded(action: Dict[str, Any]) -> Dict[str, Any] | None:
        action = json.loads(json.dumps(action))
        if _compact_json_size(action) > cap:
            return None
        return action

    assert bounded(small_action) == small_action
    assert bounded(large_action) is None


def test_pickle_persisted_blob_shape_excludes_full_historical_undo_buckets() -> None:
    """
    The serialized session blob should not smuggle full historical forms through
    undo history.

    Keys are allowed in undo records because undo needs to know what to delete.
    Heavy multiframespecs, prefill values, labels/help/metadata/payloads, and whole
    historical buckets are not allowed.

    Important distinction:

    - exec_records are history. They must stay lean.
    - forms_emitted is topology/multiframespec state. It is bounded by the snapshot
      window.
    - form_prefills is current state in this local model. It may still contain
      current value entries unless/until a separate value-retention policy is
      introduced.
    """

    state, undos = _build_exec_records(
        _emit_form_incrementally,
        60,
        field_count=3,
        payload_chars=96,
    )

    snapshot_like = {
        "state": _snapshot_state_with_window(state, window=16),
        "exec_records": [
            {
                "step_id": f"step_{idx}",
                "undo_patch": undo,
                "inserted_steps": [],
                "index_seq": idx,
                "redo_action": None,
            }
            for idx, undo in enumerate(undos)
        ],
        "redo_stack_v1": [],
        "program": [],
    }

    blob = pickle.dumps(snapshot_like, protocol=pickle.HIGHEST_PROTOCOL)

    assert len(blob) < 250_000

    for record in snapshot_like["exec_records"]:
        _assert_incremental_undo_contains_no_heavy_previous_values(record["undo_patch"])

    exec_records_rendered = json.dumps(
        snapshot_like["exec_records"],
        sort_keys=True,
        default=repr,
    )

    # Keys are expected and necessary.
    assert "form_0000.field_0" in exec_records_rendered

    # Heavy values/multiframespec bodies must not be present in undo history.
    assert "Form form_0000" not in exec_records_rendered
    assert "Field 0" not in exec_records_rendered
    assert '"label"' not in exec_records_rendered
    assert '"help"' not in exec_records_rendered
    assert '"metadata"' not in exec_records_rendered
    assert '"payload"' not in exec_records_rendered
    assert '"value"' not in exec_records_rendered
    assert '"source"' not in exec_records_rendered

    assert "__app_table_mapping_items_undo_v1__" in exec_records_rendered
    assert "__app_table_list_append_undo_v1__" in exec_records_rendered

    state_obj = snapshot_like["state"]

    # The snapshot window trims old multiframespec topology from durable state.
    #
    # Do not inspect all state for "form_0000.field_0" here: form_prefills is
    # current state in this model, and current values are governed by a different
    # retention policy than emitted-form topology.
    forms_rendered = json.dumps(
        state_obj.get(KEY_FORMS_EMITTED) or {},
        sort_keys=True,
        default=repr,
    )
    order_rendered = json.dumps(
        state_obj.get(KEY_FORMS_EMITTED_ORDER) or [],
        sort_keys=True,
        default=repr,
    )
    prefills_rendered = json.dumps(
        state_obj.get(KEY_FORM_PREFILLS) or {},
        sort_keys=True,
        default=repr,
    )

    assert "form_0000" not in forms_rendered
    assert "Form form_0000" not in forms_rendered
    assert "form_0000" not in order_rendered

    # Current prefills are intentionally not trimmed by the multiframespec-topology
    # window in this local model. These assertions document that distinction so
    # future maintainers do not mistake current-state values for undo bloat.
    assert "form_0000.field_0" in prefills_rendered
    assert '"value"' in prefills_rendered

def test_recursive_live_weight_profile_remains_explainable() -> None:
    """
    Diagnostic-style test that ensures the helper profile remains available and
    sane. This catches accidental explosive object graphs in the modeled session
    state without pretending to be a strict product byte budget.
    """

    state, undos = _build_exec_records(
        _emit_form_incrementally,
        100,
        field_count=4,
        payload_chars=64,
    )

    profile = {
        "state_json_chars": _compact_json_size(state),
        "exec_records_json_chars": _compact_json_size(undos),
        "state_recursive_bytes": _recursive_size(state),
        "undo_recursive_bytes": _recursive_size(undos),
        "forms_emitted_count": len(state.get(KEY_FORMS_EMITTED) or {}),
        "prefill_count": len(state.get(KEY_FORM_PREFILLS) or {}),
        "fill_count": len(state.get(KEY_FORM_FILLS) or {}),
    }

    assert profile["forms_emitted_count"] == 100
    assert profile["prefill_count"] == 400
    assert profile["fill_count"] == 0

    assert profile["exec_records_json_chars"] < profile["state_json_chars"] * 0.50
    assert profile["undo_recursive_bytes"] < profile["state_recursive_bytes"]