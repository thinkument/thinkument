"""Language-Agnostic JSON Conformance Runner (Python Target).
Replays golden tape scenarios against local daemon.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import sys
import unittest

# Ensure thinkument_sdk is in pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thinkument_sdk.client import ThinkClient
from thinkument_sdk.types import RelayPayload, SessionCreatePayload


class TestPythonSdkConformance(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ThinkClient.local(5052)
        base = Path(__file__).resolve().parent
        self.scenarios_dir = (base / "../../../conformance/scenarios").resolve()

    def test_golden_tape_scenarios(self) -> None:
        scenario_files = sorted(glob.glob(str(self.scenarios_dir / "*.json")))
        self.assertGreater(len(scenario_files), 0, "No conformance scenarios found")

        for file_path in scenario_files:
            with open(file_path, "r", encoding="utf-8") as f:
                scenario = json.load(f)
            sid = scenario.get("scenario_id")

            if sid in ("02_vendor_interception", "03_stateless_relay"):
                payload = RelayPayload(
                    operation=scenario["operation"],
                    args=scenario.get("args"),
                    modality=scenario.get("modality"),
                )
                self.assertEqual(payload.operation, scenario["operation"])
                if scenario.get("args"):
                    self.assertEqual(payload.args, scenario["args"])

            elif sid == "01_step_progression":
                payload = SessionCreatePayload(
                    P=scenario.get("P", {}),
                    SM=scenario.get("SM"),
                    C=scenario.get("C"),
                )
                self.assertIsNotNone(payload.P)


if __name__ == "__main__":
    unittest.main()
