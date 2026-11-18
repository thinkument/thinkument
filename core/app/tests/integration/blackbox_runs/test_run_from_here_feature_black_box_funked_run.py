from __future__ import annotations

from copy import deepcopy

import pytest

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMResult,
    register_chainreactiontm_version,
)
from _thinksessions.run.run_from_here import (
    FunkedBlackBoxContractError,
    FunkedBlackBoxRunIncompleteError,
    delete_live_session,
    run_funked_black_box_from_program,
)
from bootstrap_higher_app.higher_bootstrap import (
    activate_installed_thinkument_composition_v1,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program12__funked_puzzle_generation_and_completion import (
    PROGRAM_FUNKED_AND_HUMAN_COLLABORATION,
    PROGRAM_MANY_WIDGETS_MANY_ROLES,
    PROGRAM_START_TO_FINISH,
    SESSION_METADATA_FUNKED_AND_HUMAN_COLLABORATION,
    SESSION_METADATA_MANY_WIDGETS_MANY_ROLES,
    SESSION_METADATA_START_TO_FINISH,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (
    register_dry_run_lib_widgets_flows_v1,
)


NOOP_FUNK_VERSION = "tests.run_from_here.black_box.noop.v1"


@pytest.fixture(scope="module", autouse=True)
def _activate_composition():
    activate_installed_thinkument_composition_v1()

    receipt = register_dry_run_lib_widgets_flows_v1()
    assert receipt["ok"] is True

    register_chainreactiontm_version(
        name=NOOP_FUNK_VERSION,
        run=lambda request: FunkTMResult(
            fill={},
            signal=None,
            receipt={"kind": "black_box_noop_test_receipt_v1"},
        ),
        validate_args=lambda raw: dict(raw or {}),
        replace=True,
    )


def test_black_box_many_roles_completes_without_manual_io_and_cleans_up():
    result = run_funked_black_box_from_program(
        program=PROGRAM_MANY_WIDGETS_MANY_ROLES,
        program_language=LANG_THINK_PROGRAM_V1,
        session_metadata=SESSION_METADATA_MANY_WIDGETS_MANY_ROLES,
        identity_id="blackbox-proof",
        retain_session=False,
    )

    assert result["ok"] is True
    assert result["kind"] == "funked_black_box_run_result_v1"
    assert result["final_context"]["kind"] == "ATCOMPLETION"
    assert result["final_context_kind"] == "ATCOMPLETION"
    assert result["session_retained"] is False
    assert result["contract"]["unfunkable_program_roles"] == []
    assert result["chain_stopped_reason"] == "program_complete_or_not_manual"
    assert (
        result["dispatch_result"]["chainreactionTM_receipt"][
            "generated_dispatches_e2e"
        ]
        >= 3
    )
    assert result["latest_event_seq"] >= len(result["events"])
    assert "delete_report" in result


def test_black_box_rejects_authored_human_barrier_in_static_preflight():
    with pytest.raises(FunkedBlackBoxContractError) as excinfo:
        run_funked_black_box_from_program(
            program=PROGRAM_FUNKED_AND_HUMAN_COLLABORATION,
            program_language=LANG_THINK_PROGRAM_V1,
            session_metadata=SESSION_METADATA_FUNKED_AND_HUMAN_COLLABORATION,
            identity_id="blackbox-human-barrier-proof",
        )

    assert excinfo.value.report["ok"] is False
    assert excinfo.value.report["unfunkable_program_roles"] == [
        "human_reviewer"
    ]


def test_black_box_static_contract_can_pass_but_runtime_noop_is_incomplete():
    metadata = deepcopy(SESSION_METADATA_START_TO_FINISH)
    metadata["roles"]["solver"]["chainreactionTM_config"] = {
        "version": NOOP_FUNK_VERSION,
        "args": {},
    }

    with pytest.raises(FunkedBlackBoxRunIncompleteError) as excinfo:
        run_funked_black_box_from_program(
            program=PROGRAM_START_TO_FINISH,
            program_language=LANG_THINK_PROGRAM_V1,
            session_metadata=metadata,
            identity_id="blackbox-noop-proof",
            retain_session=False,
        )

    report = excinfo.value.report
    assert report["contract"]["ok"] is True
    assert report["ok"] is False
    assert report["final_context_kind"] == "MANUALFILLNEEDEDSTEP"
    assert report["chain_stopped_reason"] == "chainreaction_version_returned_noop"
    assert report["session_retained"] is False
    assert "delete_report" in report


def test_black_box_can_retain_completed_session_for_host_inspection():
    result = run_funked_black_box_from_program(
        program=PROGRAM_START_TO_FINISH,
        program_language=LANG_THINK_PROGRAM_V1,
        session_metadata=SESSION_METADATA_START_TO_FINISH,
        identity_id="blackbox-retain-proof",
        retain_session=True,
    )

    assert result["ok"] is True
    assert result["session_retained"] is True
    assert "delete_report" not in result

    delete_report = delete_live_session(session_id=result["session_id"])
    assert dict(delete_report or {}).get("ok", True) is True
