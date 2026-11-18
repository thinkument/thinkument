from __future__ import annotations

from copy import deepcopy

import pytest

import ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher as subject


def test_materialize_routes_c_over_program_and_session_metadata(monkeypatch) -> None:
    calls = {}

    def fake_route(*, surfaces, initial_parameter_overrides):
        calls["surfaces"] = deepcopy(surfaces)
        calls["C"] = deepcopy(initial_parameter_overrides)
        return {
            "program": {"kind": "routed-program"},
            "session_metadata": {"kind": "routed-sm", "symbol": "$resolved"},
        }

    def fake_bind(session_metadata):
        calls["bind"] = deepcopy(session_metadata)
        return {"kind": "bound-sm", "symbol": "resolved"}

    monkeypatch.setattr(
        subject,
        "_route_joint_symbol_surfaces_v1",
        fake_route,
    )
    monkeypatch.setattr(
        subject,
        "_bind_session_metadata_symbols_v1",
        fake_bind,
    )

    tape = subject.live_run_tape_v1(
        program={"kind": "P", "symbols": {"p": {"value": 1}}},
        session_metadata={"kind": "SM", "symbols": {"sm": {"value": 2}}},
        initial_parameter_overrides={"p": 10, "sm": 20},
    )

    effective = subject.materialize_joint_p_sm_c_v1(tape)

    assert calls["surfaces"] == {
        "program": {"kind": "P", "symbols": {"p": {"value": 1}}},
        "session_metadata": {
            "kind": "SM",
            "symbols": {"sm": {"value": 2}},
        },
    }
    assert calls["C"] == {"p": 10, "sm": 20}
    assert calls["bind"] == {
        "kind": "routed-sm",
        "symbol": "$resolved",
    }
    assert effective.program == {"kind": "routed-program"}
    assert effective.session_metadata == {
        "kind": "bound-sm",
        "symbol": "resolved",
    }


def test_materialize_without_c_still_binds_sm_and_does_not_mutate_tape(
    monkeypatch,
) -> None:
    original_program = {"kind": "P", "nested": {"x": 1}}
    original_sm = {"kind": "SM", "nested": {"y": 2}}

    def forbidden_route(**kwargs):
        raise AssertionError(f"router must not run for empty C: {kwargs!r}")

    def fake_bind(session_metadata):
        session_metadata["nested"]["y"] = 99
        return session_metadata

    monkeypatch.setattr(
        subject,
        "_route_joint_symbol_surfaces_v1",
        forbidden_route,
    )
    monkeypatch.setattr(
        subject,
        "_bind_session_metadata_symbols_v1",
        fake_bind,
    )

    tape = subject.live_run_tape_v1(
        program=original_program,
        session_metadata=original_sm,
        initial_parameter_overrides=None,
    )

    effective = subject.materialize_joint_p_sm_c_v1(tape)

    assert effective.program == original_program
    assert effective.session_metadata == {
        "kind": "SM",
        "nested": {"y": 99},
    }
    assert tape.P == original_program
    assert tape.SM == original_sm


def test_materialize_rejects_non_mapping_resolved_sm(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_bind_session_metadata_symbols_v1",
        lambda value: [value],
    )

    tape = subject.live_run_tape_v1(
        program={"kind": "P"},
        session_metadata={"kind": "SM"},
    )

    with pytest.raises(TypeError, match="resolved SM must be a mapping"):
        subject.materialize_joint_p_sm_c_v1(tape)
