from __future__ import annotations

from dataclasses import dataclass

import pytest

from _thinksessions.run._funked_black_box import (
    FunkedBlackBoxContractError,
    think_program_role_names_v1,
    validate_funked_black_box_contract_v1,
)


PROGRAM = {
    "run": {
        "program": {
            "widgets": {
                "a": {"roles": ["maker"]},
                "b": {"roles": ["reviewer"]},
            },
            "flow": [],
        }
    }
}


PROGRAM_WITH_STEP_ROLE_SURFACES = {
    "run": {
        "program": {
            "widgets": {
                "a": {"role": "maker"},
            },
            "flow": [
                {
                    "id": "s1",
                    "widgets": ["a"],
                    "roles": ["step_reader"],
                    "overrides": {
                        "roles": {
                            "a": ["reviewer", "maker"],
                        },
                        "role": {
                            "a": "approver",
                        },
                    },
                }
            ],
        }
    }
}


@dataclass
class Config:
    enabled: bool
    flat_roles_ordered: tuple[str, ...]
    role_configs: dict


def test_program_role_extraction_is_stable_unique_and_scans_step_overrides():
    assert think_program_role_names_v1(PROGRAM) == ["maker", "reviewer"]
    assert think_program_role_names_v1(PROGRAM_WITH_STEP_ROLE_SURFACES) == [
        "approver",
        "maker",
        "reviewer",
        "step_reader",
    ]


def test_black_box_contract_requires_chainreaction_enabled():
    cfg = Config(
        enabled=False,
        flat_roles_ordered=("maker", "reviewer"),
        role_configs={"maker": {"version": "x"}, "reviewer": {"version": "y"}},
    )
    with pytest.raises(FunkedBlackBoxContractError) as excinfo:
        validate_funked_black_box_contract_v1(
            program=PROGRAM,
            resolved_session_metadata={"roles": {"maker": {}, "reviewer": {}}},
            normalized_chainreaction_config=cfg,
        )
    assert excinfo.value.report["chainreaction_enabled"] is False
    assert excinfo.value.report["ok"] is False


def test_black_box_contract_requires_every_program_role_on_sm():
    cfg = Config(
        enabled=True,
        flat_roles_ordered=("maker", "reviewer"),
        role_configs={"maker": {"version": "x"}, "reviewer": {"version": "y"}},
    )
    with pytest.raises(FunkedBlackBoxContractError) as excinfo:
        validate_funked_black_box_contract_v1(
            program=PROGRAM,
            resolved_session_metadata={"roles": {"maker": {}}},
            normalized_chainreaction_config=cfg,
        )
    assert excinfo.value.report["missing_program_roles_from_session_metadata"] == [
        "reviewer"
    ]


def test_black_box_contract_requires_every_program_role_on_schedule():
    cfg = Config(
        enabled=True,
        flat_roles_ordered=("maker",),
        role_configs={"maker": {"version": "x"}, "reviewer": {"version": "y"}},
    )
    with pytest.raises(FunkedBlackBoxContractError) as excinfo:
        validate_funked_black_box_contract_v1(
            program=PROGRAM,
            resolved_session_metadata={"roles": {"maker": {}, "reviewer": {}}},
            normalized_chainreaction_config=cfg,
        )
    assert excinfo.value.report[
        "missing_program_roles_from_chainreaction_schedule"
    ] == ["reviewer"]


def test_black_box_contract_requires_every_program_role_funkable():
    cfg = Config(
        enabled=True,
        flat_roles_ordered=("maker", "reviewer"),
        role_configs={"maker": {"version": "x"}, "reviewer": None},
    )
    with pytest.raises(FunkedBlackBoxContractError) as excinfo:
        validate_funked_black_box_contract_v1(
            program=PROGRAM,
            resolved_session_metadata={"roles": {"maker": {}, "reviewer": {}}},
            normalized_chainreaction_config=cfg,
        )
    assert excinfo.value.report["unfunkable_program_roles"] == ["reviewer"]


def test_black_box_contract_accepts_complete_role_sheet_and_preserves_schedule_order():
    cfg = Config(
        enabled=True,
        flat_roles_ordered=("reviewer", "maker", "reviewer"),
        role_configs={
            "maker": {"version": "x"},
            "reviewer": {"version": "y"},
        },
    )
    report = validate_funked_black_box_contract_v1(
        program=PROGRAM,
        resolved_session_metadata={
            "roles": {
                "maker": {},
                "reviewer": {},
                "unused_sm_role": {},
            }
        },
        normalized_chainreaction_config=cfg,
    )
    assert report["ok"] is True
    assert report["scheduled_roles"] == ["reviewer", "maker"]
    assert report["extra_session_metadata_roles"] == ["unused_sm_role"]
    assert report["extra_scheduled_roles"] == []
