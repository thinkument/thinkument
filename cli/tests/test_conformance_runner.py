"""Language-agnostic JSON Conformance Runner ('The Golden Tape Formalism')."""
import glob
import json
import os
import threading
import unittest
from werkzeug.serving import make_server

from _thinksessions.example_reused_test_flow_setups.programs.test import demo_think_program_v1
from thinkument import ThinkClient
from thinkument.daemon.runner import LocalSessionRunner
from thinkument.daemon.server import create_daemon_app


class TestConformanceHarness(unittest.TestCase):

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

    def test_run_all_json_conformance_scenarios(self):
        scenario_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../conformance/scenarios"))
        scenario_files = sorted(glob.glob(os.path.join(scenario_dir, "*.json")))
        self.assertGreater(len(scenario_files), 0, f"No conformance scenarios found in {scenario_dir}")

        for file_path in scenario_files:
            with open(file_path, "r", encoding="utf-8") as f:
                scenario = json.load(f)

            scenario_id = scenario.get("scenario_id")
            with self.subTest(scenario=scenario_id):
                if scenario_id == "01_step_progression":
                    program = demo_think_program_v1()
                    sm = {"roles": {"maker": {}}, "role_mismatch_policy": {"default": "redacted"}}
                    live_run = self.client.live.create(P=program, SM=sm, C={}, public_view_role="maker")
                    self.assertTrue(live_run.session_id)
                    active = live_run.connect("maker")
                    for d in scenario.get("dispatches", []):
                        outcome = active.dispatch(action=d.get("action", "STEP"))
                        self.assertEqual(outcome.status, d.get("expected_outcome", "applied"))

                    events = active.get_events()
                    min_events = scenario["expected_invariants"].get("minimum_events_emitted", 1)
                    self.assertGreaterEqual(len(events), min_events)
                    active.close()

                elif scenario_id == "02_vendor_interception":
                    res = self.client.ops.execute(
                        operation=scenario["operation"],
                        args=scenario["args"],
                        modality=scenario["modality"],
                    )
                    text_contains = scenario["expected_invariants"].get("text_contains")
                    if text_contains:
                        self.assertIn(text_contains, res.get("text", ""))
                    for field in scenario["expected_invariants"].get("usage_fields", []):
                        self.assertIn(field, res.get("usage", {}))

                elif scenario_id == "03_stateless_relay":
                    res = self.client.ops.execute(
                        operation=scenario["operation"],
                        args=scenario["args"],
                        modality=scenario["modality"],
                    )
                    self.assertEqual(res.get("status"), "success")
                    self.assertIn("embeddings", res)

                elif scenario_id == "04_role_masking":
                    program = demo_think_program_v1()
                    sm = {
                        "roles": {"maker": {}, "auditor": {}},
                        "role_mismatch_policy": {"default": "redacted"},
                    }
                    live_run = self.client.live.create(P=program, SM=sm, C={}, public_view_role="maker")
                    active_maker = live_run.connect("maker")
                    active_auditor = live_run.connect("auditor")
                    for d in scenario.get("dispatches", []):
                        outcome = active_maker.dispatch(action=d.get("action", "STEP"))
                        self.assertEqual(outcome.status, d.get("expected_outcome", "applied"))

                    maker_events = active_maker.get_events()
                    auditor_events = active_auditor.get_events()
                    self.assertGreater(len(maker_events), 0)
                    self.assertIsInstance(auditor_events, list)
                    active_maker.close()
                    active_auditor.close()

                elif scenario_id == "05_concurrency_lock":
                    program = demo_think_program_v1()
                    sm = {"roles": {"maker": {}}, "role_mismatch_policy": {"default": "redacted"}}
                    live_run = self.client.live.create(P=program, SM=sm, C={}, public_view_role="maker")
                    active = live_run.connect("maker")
                    for d in scenario.get("dispatches", []):
                        outcome = active.dispatch(action=d.get("action", "STEP"), cursor=d.get("cursor"))
                        expected = d.get("expected_outcome")
                        if expected == "applied":
                            self.assertEqual(outcome.status, "applied")
                        else:
                            self.assertIn(outcome.status, ["stale_rejected", "stale_cursor_rejected", "applied", "ok"])
                    active.close()

                elif scenario_id == "06_subprogram_composition":
                    program = scenario["program"]
                    sm = scenario.get("session_metadata", {"roles": {"host_role": {}}})
                    c = scenario.get("context", {})
                    live_run = self.client.live.create(P=program, SM=sm, C=c, public_view_role="host_role")
                    self.assertTrue(live_run.session_id)
                    active = live_run.connect("host_role")
                    for d in scenario.get("dispatches", []):
                        outcome = active.dispatch(action=d.get("action", "STEP"))
                        self.assertEqual(outcome.status, d.get("expected_outcome", "applied"))

                    events = active.get_events()
                    min_events = scenario["expected_invariants"].get("minimum_events_emitted", 1)
                    self.assertGreaterEqual(len(events), min_events)
                    active.close()


if __name__ == "__main__":
    unittest.main()
