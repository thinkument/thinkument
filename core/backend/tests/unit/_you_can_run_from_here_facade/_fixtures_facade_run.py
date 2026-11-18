from __future__ import annotations

"""
Shared fixtures for highest-façade live-session E2E sheets.

This module contains authored test programs, registration, session creation,
and queue assertions only. It contains no tests and imports no sibling test
module. Test sheets remain independently collectible and orthogonal.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

import _thinkprogram._iomicrosTM.table_micros  # noqa: F401

from _thinksessions.libs_read_write_augmented.chainreactionTM import (
    bootstrap_chainreactiontm_defaults,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)
from _thinkprogram.thinkwidgetTM import (
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    DatumLifecycleWidget,
    Reexplode,
    signal_catcher,
    thinkwidgetTM_config,
)
from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    register_think_program_language_v1,
)
from _thinksessions.run.run_from_here import create_live_session_from_program


W_NOTE = "test.run_from_here.note.v1"
PROGRAM_ID = "test_run_from_here_highest_facade"
FUNK_NOTE = "test.run_from_here.chainreaction.v1"
DEFAULT_DISPATCHER_IDENTITY_ID = "facade-e2e-dispatcher"


def assert_controller_dispatch_actor_v1(
    event: Mapping[str, Any],
    *,
    identity_id: str,
    role: str | None,
) -> None:
    assert event["kind"] == "controller_loop_event_v1"
    assert event["dispatcher_identity_id"] == identity_id
    assert event["dispatcher_role"] == role


@thinkwidgetTM_config(
    W_NOTE,
    overwrite=True,
    enforce_no_premount_shell=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
    args={},
    wires={},
)
class NoteWidget(DatumLifecycleWidget):
    @staticmethod
    def _note_shell(position: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "id": position["datum_id"],
            "title": "Write note",
            "micros": [
                {
                    "name": "text",
                    "type": "text",
                    "required": True,
                    "validators": [],
                }
            ],
            "lifecycle": {
                "widget": W_NOTE,
                "mount_explode": True,
                "max_reexplosions": 8,
                "max_messages": 8,
                "max_proc_notes": 0,
            },
        }

    def _on_mount(self, position, fill_data, limits, stats):
        self.message("info", "note mounted")
        return Reexplode(
            next_fill_shell=self._note_shell(position),
            pre_computed_fills={"text": ""},
            prefill_hints={"text": "hello"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.text = dict(fill_data["current_fills"])["text"]
        if str(self.text).startswith("keep-open:"):
            self.message("info", "note accepted and kept open")
            return Reexplode(
                next_fill_shell=self._note_shell(position),
                pre_computed_fills={"text": self.text},
                prefill_hints={"text": self.text},
            )
        self.message("success", "note accepted")
        return True

    @signal_catcher("touch")
    def touch(self, signal, position, fill_data, limits, stats):
        current = dict(fill_data["current_fills"])
        current["text"] = "keep-open: signal-touch"
        self.last_touch = dict(signal.get("info") or {})
        self.message("info", "note touched by signal")
        return Reexplode(
            next_fill_shell=self._note_shell(position),
            pre_computed_fills=current,
            prefill_hints={"text": current["text"]},
        )


def register_facade_run_fixture_v1() -> None:
    bootstrap_chainreactiontm_defaults()

    def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return {"text": str(raw.get("text") or "hello from chainreaction")}

    def run(request: FunkTMRequest) -> FunkTMResult:
        return FunkTMResult(
            fill={
                str(row["datum_id"]): {"text": request.args["text"]}
                for row in request.pending_datums
            },
            signal=None,
            receipt={
                "kind": "run_from_here_chainreaction_receipt_v1",
                "role": request.role,
            },
        )

    register_chainreactiontm_version(
        name=FUNK_NOTE,
        run=run,
        validate_args=validate_args,
        replace=True,
    )
    receipt = pull_thinkwidget_class_into_kernel_v1(
        NoteWidget,
        overwrite=True,
    )
    assert receipt["ok"] is True

   
    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def facade_note_program_v1() -> Dict[str, Any]:
    lifecycle = {
        "mount_explode": True,
        "max_reexplosions": 8,
        "max_messages": 8,
        "max_proc_notes": 0,
    }
    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {"lifecycle": {"value": lifecycle}},
        "puppeteering": {},
        "run": {
            "program": {
                "info": {
                    "id": PROGRAM_ID,
                    "title": "run_from_here façade E2E",
                    "description": "One note widget used by highest-façade tests.",
                    "args": {},
                },
                "widgets": {
                    "note": {
                        "widget": W_NOTE,
                        "title": "Note",
                        "args": {},
                        "lifecycle": "$lifecycle",
                        "wires": {},
                        "roles": ["writer"],
                        "authoritative": True,
                        "tags": ["highest-facade"],
                        "system_flags": {},
                    }
                },
                "flow": [
                    {
                        "id": "note_step",
                        "title": "Note step",
                        "widgets": ["note"],
                        "authoritative": [True],
                        "overrides": {},
                    }
                ],
            },
            "config": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": True,
                }
            },
        },
    }


def two_note_program_v1() -> Dict[str, Any]:
    program = deepcopy(facade_note_program_v1())
    widgets = program["run"]["program"]["widgets"]
    note = deepcopy(widgets["note"])
    widgets.clear()
    widgets["alpha"] = {**deepcopy(note), "title": "Alpha"}
    widgets["beta"] = {**deepcopy(note), "title": "Beta"}
    flow = program["run"]["program"]["flow"][0]
    flow["widgets"] = ["alpha", "beta"]
    flow["authoritative"] = [True, True]
    return program


def facade_session_metadata_v1(*, chainreactioned: bool) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "roles": {
            "writer": {
                "label": "Writer",
                "read_roles": [],
                "chainreactionTM_config": (
                    {
                        "version": FUNK_NOTE,
                        "args": {"text": "generated note"},
                    }
                    if chainreactioned
                    else None
                ),
            },
            "auditor": {
                "label": "Auditor",
                "read_roles": [],
                "chainreactionTM_config": None,
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {"writer": "redacted"},
        },
    }
    if chainreactioned:
        meta["chainreactionTM_config"] = {
            "version": "chainreaction1.0",
            "roles_ordered": ["writer", "auditor"],
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": 4,
            "max_fills_e2e": 8,
            "history_tail_cap": 4,
            "history_size_cap": 25_000,
        }
    return meta


def launch_facade_note_session_v1(
    *,
    chainreactioned: bool = False,
    program: Mapping[str, Any] | None = None,
) -> str:
    register_facade_run_fixture_v1()
    created = create_live_session_from_program(
        program=dict(program or facade_note_program_v1()),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata=facade_session_metadata_v1(
            chainreactioned=chainreactioned
        ),
    )
    assert created["ok"] is True
    return str(created["session_id"])


def assert_strict_canonical_event_order_v1(
    events: list[Mapping[str, Any]],
) -> None:
    seqs = [int(event["event_seq"]) for event in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    assert all(seq > 0 for seq in seqs)
    assert all(str(event.get("event_id") or "") for event in events)
    assert all(str(event.get("emitted_at") or "") for event in events)