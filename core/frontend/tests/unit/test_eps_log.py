from __future__ import annotations

import ast
from pathlib import Path

import pytest

from live_vial._json_shell.eps_log import (
    EMITTER_ORIGIN_EXTERNAL_RUNTIME,
    EMITTER_ORIGIN_WIDGET_EXPLOSION,
    EPS_PAGE_KIND_V1,
    EPS_ROW_KIND_V1,
    EpsReplayConflictError,
    InMemoryEpsLog,
    VISIBILITY_ALL_NO_MODULATION,
    VISIBILITY_ALL_WITH_MODULATION,
    VISIBILITY_OWNER_ONLY,
    compute_eps_content_hash_v1,
    derive_run_eps_hash_key_v1,
    eps_callbacks_v1,
    extract_datum_read_map_v1,
    project_eps_row_v1,
)


def test_compute_eps_content_hash_v1_is_deterministic_and_key_bound() -> None:
    key_a = derive_run_eps_hash_key_v1(run_id="run-1")
    key_b = derive_run_eps_hash_key_v1(run_id="run-2")
    payload_1 = {"b": 2, "a": 1}
    payload_2 = {"a": 1, "b": 2}

    h1 = compute_eps_content_hash_v1(payload_1, run_key=key_a)
    h2 = compute_eps_content_hash_v1(payload_2, run_key=key_a)
    h3 = compute_eps_content_hash_v1(payload_1, run_key=key_b)

    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


def test_in_memory_eps_log_append_idempotency_and_replay_conflict() -> None:
    log = InMemoryEpsLog()
    log.register_run(
        run_id="run-1",
        datum_read_map={
            "roles": {"writer": ["writer"], "viewer": ["viewer"]},
            "datum_roles": {"F:S:secret": ["writer"]},
        },
    )

    row1 = log.append(
        run_id="run-1",
        event_id="ev-1",
        channel="datum.message",
        emitted_at="2026-11-08T10:00:00Z",
        payload={"text": "hello"},
        visibility=VISIBILITY_ALL_WITH_MODULATION,
        datum_id="secret",
        frame_id="F",
        span_id="S",
        form_id="form1",
        theta_event_seq_at_emit=2,
        emitter_origin=EMITTER_ORIGIN_WIDGET_EXPLOSION,
        request_id="req-1",
        trident_dispatch_id="disp-1",
    )
    assert row1["eps_seq"] == 1
    assert row1["required_roles"] == ["writer"]

    # Idempotent replay with identical payload returns existing row without advancing eps_seq
    replay = log.append(
        run_id="run-1",
        event_id="ev-1",
        channel="datum.message",
        emitted_at="2026-11-08T10:00:00Z",
        payload={"text": "hello"},
        visibility=VISIBILITY_ALL_WITH_MODULATION,
        datum_id="secret",
        frame_id="F",
        span_id="S",
        form_id="form1",
        theta_event_seq_at_emit=2,
        emitter_origin=EMITTER_ORIGIN_WIDGET_EXPLOSION,
        request_id="req-1",
        trident_dispatch_id="disp-1",
    )
    assert replay["eps_seq"] == 1
    assert log.head("run-1") == 1

    # Conflicting payload under same event_id raises EpsReplayConflictError
    with pytest.raises(EpsReplayConflictError):
        log.append(
            run_id="run-1",
            event_id="ev-1",
            channel="datum.message",
            emitted_at="2026-11-08T10:00:00Z",
            payload={"text": "tampered"},
            visibility=VISIBILITY_ALL_WITH_MODULATION,
            datum_id="secret",
            frame_id="F",
            span_id="S",
            form_id="form1",
        )


def test_role_modulation_and_visibility_on_read() -> None:
    log = InMemoryEpsLog()
    log.register_run(
        run_id="run-mod",
        datum_read_map={
            "roles": {"writer": ["writer"], "auditor": ["auditor"]},
            "datum_roles": {"F1:S1:w_datum": ["writer"]},
        },
    )

    # 1. owner-only row
    log.append(
        run_id="run-mod",
        event_id="ev-owner",
        channel="audit-ins",
        emitted_at="2026-11-08T10:00:01Z",
        payload={"secret_metric": 42},
        visibility=VISIBILITY_OWNER_ONLY,
        datum_id="w_datum",
        frame_id="F1",
        span_id="S1",
        theta_event_seq_at_emit=1,
    )
    # 2. all-with-modulation row on w_datum
    log.append(
        run_id="run-mod",
        event_id="ev-mod",
        channel="datum.message",
        emitted_at="2026-11-08T10:00:02Z",
        payload={"text": "writer only"},
        visibility=VISIBILITY_ALL_WITH_MODULATION,
        datum_id="w_datum",
        frame_id="F1",
        span_id="S1",
        theta_event_seq_at_emit=1,
        request_id="req-A",
        trident_dispatch_id="disp-A",
    )
    # 3. all-no-modulation row
    log.append(
        run_id="run-mod",
        event_id="ev-pub",
        channel="public.banner",
        emitted_at="2026-11-08T10:00:03Z",
        payload={"banner": "open"},
        visibility=VISIBILITY_ALL_NO_MODULATION,
        datum_id="w_datum",
        frame_id="F1",
        span_id="S1",
        theta_event_seq_at_emit=1,
        request_id="req-A",
        trident_dispatch_id="disp-A",
    )

    writer_page = log.read(run_id="run-mod", after_seq=0, role="writer")
    assert writer_page["kind"] == EPS_PAGE_KIND_V1
    assert writer_page["eps_head"] == 3
    assert writer_page["next_after_seq"] == 3
    assert [r["eps_seq"] for r in writer_page["rows"]] == [2, 3]
    assert writer_page["rows"][0]["obfuscated"] is False
    assert writer_page["rows"][0]["payload"] == {"text": "writer only"}

    auditor_page = log.read(run_id="run-mod", after_seq=0, role="auditor")
    assert [r["eps_seq"] for r in auditor_page["rows"]] == [2, 3]
    obf = auditor_page["rows"][0]
    assert obf["kind"] == EPS_ROW_KIND_V1
    assert obf["obfuscated"] is True
    assert obf["datum_id"] is None
    assert obf["frame_id"] is None
    assert obf["span_id"] is None
    assert obf["payload"] is None
    assert obf["channel"] == "datum.message"
    assert obf["trident_dispatch_id"] == "disp-A"
    assert auditor_page["rows"][1]["obfuscated"] is False
    assert auditor_page["rows"][1]["payload"] == {"banner": "open"}

    owner_page = log.read(run_id="run-mod", after_seq=0, for_owner=True)
    assert [r["eps_seq"] for r in owner_page["rows"]] == [1, 2, 3]
    assert owner_page["rows"][0]["visibility"] == VISIBILITY_OWNER_ONLY
    assert owner_page["rows"][0]["payload"] == {"secret_metric": 42}


def test_window_cap_counts_only_frontend_visible_rows_after_owner_only_filter() -> None:
    log = InMemoryEpsLog()
    log.append(
        run_id="run-win",
        event_id="ev-vis-1",
        channel="datum.message",
        emitted_at="2026-11-08T10:00:00Z",
        payload={"step": 1},
        visibility=VISIBILITY_ALL_NO_MODULATION,
    )
    for idx in range(2, 12):
        log.append(
            run_id="run-win",
            event_id=f"ev-audit-{idx}",
            channel="audit-ins",
            emitted_at="2026-11-08T10:00:01Z",
            payload={"idx": idx},
            visibility=VISIBILITY_OWNER_ONLY,
        )
    log.append(
        run_id="run-win",
        event_id="ev-vis-12",
        channel="datum.message",
        emitted_at="2026-11-08T10:00:02Z",
        payload={"step": 12},
        visibility=VISIBILITY_ALL_NO_MODULATION,
    )

    # Even though 10 owner-only rows sit between eps_seq=1 and eps_seq=12,
    # a window of 2 must still return BOTH frontend-visible rows (eps_seq 1 and 12)!
    page = log.read(run_id="run-win", after_seq=0, window=2, unmodulated=True)
    assert [r["eps_seq"] for r in page["rows"]] == [1, 12]


def test_eps_callbacks_v1_tracks_controller_trident_without_appending_it() -> None:
    log = InMemoryEpsLog()
    cbs = eps_callbacks_v1(
        log=log,
        run_id="run-cb",
        request_id="req-99",
        base_identity_id="user-1",
        base_role="writer",
        theta_event_seq_at_emit=4,
    )

    cbs["controller_events_callback"](
        {
            "kind": "controller_loop_event_v1",
            "phase": "start",
            "dispatch_id": "trident-abc",
            "dispatcher_identity_id": "user-1",
            "dispatcher_role": "writer",
            "payload": {"U": {"datum_states_on_this_span": []}},
        }
    )
    assert log.head("run-cb") == 0

    cbs["explosion_events_callback"](
        {
            "kind": "datum_lifecycle_event_v1",
            "event_id": "exp-1",
            "name": "datum.message",
            "source": "datum_widget",
            "emitted_at": "2026-11-08T10:00:05Z",
            "datum_id": "D1",
            "frame_id": "F1",
            "span_id": "S1",
            "form_id": "form1",
            "payload": {"msg": "ok"},
        }
    )
    assert log.head("run-cb") == 1
    page = log.read(run_id="run-cb", after_seq=0, unmodulated=True)
    row = page["rows"][0]
    assert row["trident_dispatch_id"] == "trident-abc"
    assert row["request_id"] == "req-99"
    assert row["theta_event_seq_at_emit"] == 4
    assert row["emitter_origin"] == EMITTER_ORIGIN_WIDGET_EXPLOSION


def test_think_frontend_never_imports_higher_layers() -> None:
    src_root = Path(__file__).resolve().parents[2] / "src"
    forbidden_prefixes = (
        "ways_to_run",
        "think_app",
        "epsilinesTM_serveragnostic",
        "app_pack_mould",
        "web_RESTful",
        "_funneled_apps",
    )
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), (
                        f"{py_file} imports forbidden higher module {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden_prefixes), (
                    f"{py_file} imports forbidden higher module {node.module}"
                )
