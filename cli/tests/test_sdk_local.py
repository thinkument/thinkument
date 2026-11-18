"""End-to-end integration tests for ThinkClient.local() against the local studio daemon."""
import threading
import unittest
from werkzeug.serving import make_server

from _thinksessions.example_reused_test_flow_setups.programs.test import demo_think_program_v1
from thinkument import ThinkClient
from thinkument.daemon.runner import LocalSessionRunner
from thinkument.daemon.server import create_daemon_app


class TestSdkLocal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.runner = LocalSessionRunner()
        cls.app = create_daemon_app(runner=cls.runner)
        cls.server = make_server("127.0.0.1", 0, cls.app)
        cls.port = cls.server.port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        cls.client = ThinkClient.local(port=cls.port, host="127.0.0.1")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_local_sdk_lifecycle(self):
        program = demo_think_program_v1()
        sm = {
            "roles": {"maker": {}, "reviewer": {}},
            "role_mismatch_policy": {"default": "redacted"},
        }

        # 1. Create live session via SDK
        live_run = self.client.live.create(
            P=program,
            SM=sm,
            C={},
            public_view_role="maker",
            metadata={"title": "Local E2E SDK Test"},
        )
        self.assertTrue(live_run.session_id)
        self.assertIn("maker", live_run.handles)
        self.assertTrue(live_run.selected.url.startswith("http://127.0.0.1"))

        # 2. Connect ActiveSession poller-dispatcher
        active = live_run.connect("maker")
        self.assertEqual(active.role, "maker")

        # 3. Dispatch action
        outcome = active.dispatch(action="STEP")
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.status, "applied")

        # 4. Read events
        events = active.get_events()
        self.assertGreater(len(events), 0)
        self.assertTrue(any("controller" in ev.event_kind or "step" in ev.event_kind for ev in events))

        # 5. Read Trident tape
        tape = active.get_tape()
        self.assertGreater(len(tape.events), 0)

        # 6. Execute ops relay
        res = self.client.ops.execute(
            operation="vendor.llm.chat_completion",
            args={"model": "claude-3-5", "prompt": "Synthesize summary"},
        )
        self.assertIn("[Mock claude-3-5]", res["text"])

        # 7. Validate catalogue
        report = self.client.catalogue.validate(program)
        self.assertTrue(report.valid)
        self.assertEqual(report.kind, "think_program_v1")

        # 8. Clean up
        active.close()


if __name__ == "__main__":
    unittest.main()
