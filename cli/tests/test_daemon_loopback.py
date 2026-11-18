"""Tests for the local studio daemon REST and SSE endpoints."""
import json
import unittest

from thinkument.daemon.server import create_daemon_app
from thinkument.daemon.runner import LocalSessionRunner


class TestDaemonLoopback(unittest.TestCase):

    def setUp(self):
        self.runner = LocalSessionRunner()
        self.app = create_daemon_app(runner=self.runner)
        self.client = self.app.test_client()

    def test_healthz(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "thinkument-local-daemon")

    def test_ops_relay_endpoint(self):
        resp = self.client.post("/api/v1/ops/execute/", json={
            "operation": "vendor.llm.chat_completion",
            "modality": "llm",
            "args": {"model": "gpt-4o", "prompt": "Daemon ops relay test"},
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("[Mock gpt-4o]", data["text"])
        self.assertIn("Daemon ops relay", data["text"])
        self.assertIn("usage", data)

    def test_create_and_dispatch_session(self):
        from _thinksessions.example_reused_test_flow_setups.programs.test import demo_think_program_v1
        program = demo_think_program_v1()
        sm = {
            "roles": {"maker": {}, "reviewer": {}},
            "role_mismatch_policy": {"default": "redacted"}
        }
        c = {}

        # 1. Create session
        resp = self.client.post("/api/v1/sessions/", json={
            "P": program,
            "SM": sm,
            "C": c,
            "public_view_role": "maker",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data["kind"], "web_RESTful_launch_result_v1")
        self.assertIn("session_id", data)
        self.assertIn("maker", data["handles"])
        sid = data["session_id"]

        # 2. Get state
        state_resp = self.client.get(f"/api/v1/sessions/{sid}/?role=maker")
        self.assertEqual(state_resp.status_code, 200)

        # 3. Get events
        events_resp = self.client.get(f"/api/v1/sessions/{sid}/events/?role=maker")
        self.assertEqual(events_resp.status_code, 200)
        events_data = events_resp.get_json()
        self.assertIn("events", events_data)

        # 4. Dispatch action
        dispatch_resp = self.client.post(f"/api/v1/sessions/{sid}/dispatch/", json={
            "action": "STEP",
            "role": "maker",
            "cursor": 0,
        })
        self.assertEqual(dispatch_resp.status_code, 200)

        # 5. Delete session
        del_resp = self.client.delete(f"/api/v1/sessions/{sid}/")
        self.assertEqual(del_resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
