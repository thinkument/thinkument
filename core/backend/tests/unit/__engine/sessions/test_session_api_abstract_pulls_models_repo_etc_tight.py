from __future__ import annotations

import unittest
from uuid import uuid4
from typing import Any, Dict, List, Optional

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    AbstractSessionAPI,
    get_concrete_session_api,
)

from _thinkengine.__persistence.models import SessionState
from _thinkengine.__persistence.repo import SessionRepo


class RepoOpaqueBytesContractTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset in-memory repo between tests
        SessionRepo._states.clear()
        SessionRepo._steppers.clear()

    def test_state_is_opaque_bytes_and_round_trips(self) -> None:
        sid = uuid4()
        blob = b"\x00\x01custom-encoding\xff"
        st = SessionState(session_id=sid, pickled_stepper=blob, session_metadata={"k": "v"})

        SessionRepo.create(st, stepper=blob)  # bytes-only engine mode
        got = SessionRepo.get(sid)

        self.assertEqual(got.session_id, sid)
        self.assertEqual(got.pickled_stepper, blob)
        self.assertEqual(got.session_metadata, {"k": "v"})

        hot = SessionRepo.get_stepper(sid)
        self.assertEqual(hot, blob)

    def test_repo_caches_any_object_as_stepper_without_serializing(self) -> None:
        sid = uuid4()
        st = SessionState(session_id=sid, pickled_stepper=b"engine-bytes", session_metadata={})

        stepper_obj = {"whatever": ["an", "engine", "wants"]}
        SessionRepo.create(st, stepper=stepper_obj)

        self.assertIs(SessionRepo.get_stepper(sid), stepper_obj)

    def test_delete_removes_state_and_stepper(self) -> None:
        sid = uuid4()
        st = SessionState(session_id=sid, pickled_stepper=b"x", session_metadata={})
        SessionRepo.create(st, stepper=b"x")

        SessionRepo.delete(sid)
        self.assertIsNone(SessionRepo.get_stepper(sid))
        with self.assertRaises(KeyError):
            SessionRepo.get(sid)


class _FakeAPI(AbstractSessionAPI):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def create_VM_session(
        self,
        *,
        manifest: List[List[Any]],
        initial_parameter_overrides: Dict[str, Any],
        session_metadata: Any = None,
        roles: Any = None,
        get_map: bool = False,
    ):
        self.calls.append(
            (
                "create_VM_session",
                {
                    "manifest": manifest,
                    "initial_parameter_overrides": initial_parameter_overrides,
                    "roles": roles,
                },
            )
        )
        return {"session_id": "S1", "ctx": {"frames": []}}

    def step_session(
        self,
        session_id: str,
        *,
        fill: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append(("step_session", {"session_id": session_id, "fill": fill}))
        return {"ok": True}

    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        self.calls.append(("undo_last_step", {"session_id": session_id}))
        return {"ok": True}

    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        self.calls.append(("get_session_context", {"session_id": session_id}))
        return {"ctx": {}}

    def get_outputs(self, session_id: str) -> Dict[str, Any]:
        self.calls.append(("get_outputs", {"session_id": session_id}))
        return {"outputs": {}}


if __name__ == "__main__":
    unittest.main()