"""End-to-End Test for the TypeScript/Node.js SDK against live local studio daemon."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import unittest
from werkzeug.serving import make_server

from thinkument.daemon.server import create_daemon_app
from thinkument.daemon.runner import LocalSessionRunner

ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "rav.yaml").exists()),
    Path(__file__).resolve().parents[4],
)
TS_SDK_DIR = ROOT / "thinkument" / "opensourced" / "sdks" / "typescript"


def find_free_port() -> int:
    with socket.socket(socket.AF_SOCKET if hasattr(socket, "AF_SOCKET") else socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestNodeSdkE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node.js runtime not found in PATH")

        dist_index = TS_SDK_DIR / "dist" / "index.js"
        if not dist_index.exists():
            raise RuntimeError(f"Missing compiled TypeScript SDK at {dist_index}. Use the registered CLI CI runner to build it.")

        cls.port = find_free_port()
        cls.runner = LocalSessionRunner()
        cls.app = create_daemon_app(runner=cls.runner)
        cls.server = make_server("127.0.0.1", cls.port, cls.app)

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # Wait for daemon to become healthy
        deadline = time.time() + 5.0
        ready = False
        import urllib.request
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/healthz/", timeout=0.5) as r:
                    if r.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.05)

        if not ready:
            cls.server.shutdown()
            raise RuntimeError("Local daemon failed to start within 5 seconds")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server_thread.join(timeout=2.0)

    def test_node_sdk_lifecycle_e2e(self):
        from _thinksessions.example_reused_test_flow_setups.programs.test import demo_think_program_v1
        program_json = json.dumps(demo_think_program_v1())

        node_script = f"""
import {{ ThinkClient, CloudServiceRequiredError }} from '{TS_SDK_DIR / "dist" / "index.js"}';

async function main() {{
    const client = ThinkClient.local({self.port});

    // 1. Health check
    const health = await client.health();
    if (health.status !== 'ok') {{
        throw new Error(`Health check failed: ${{JSON.stringify(health)}}`);
    }}
    console.log('  [Node.js E2E] Healthcheck OK');

    // 2. Ops execution with vendor mocking seam
    const opRes = await client.ops.execute({{
        operation: 'vendor.llm.chat_completion',
        modality: 'llm',
        args: {{ model: 'gpt-4o', prompt: 'Node.js E2E prompt' }}
    }});
    if (!opRes.text || !opRes.text.includes('[Mock gpt-4o]')) {{
        throw new Error(`Unexpected ops response: ${{JSON.stringify(opRes)}}`);
    }}
    console.log('  [Node.js E2E] Ops Execution OK');

    // 3. Live session creation and dispatch
    const program = {program_json};
    const sessionHandle = await client.live.create({{
        P: program,
        SM: {{ roles: {{ maker: {{}}, reviewer: {{}} }}, role_mismatch_policy: {{ default: 'redacted' }} }},
        public_view_role: 'maker'
    }});
    if (!sessionHandle.sessionId) {{
        throw new Error('Session ID missing from handle');
    }}
    console.log(`  [Node.js E2E] Live Session Created: ${{sessionHandle.sessionId}}`);

    const active = sessionHandle.connect('maker');
    const dispatchReceipt = await active.dispatch({{ action: 'STEP' }});
    if (dispatchReceipt.status !== 'applied') {{
        throw new Error(`Dispatch failed: ${{JSON.stringify(dispatchReceipt)}}`);
    }}
    console.log('  [Node.js E2E] Dispatch STEP OK');

    const events = await active.getEvents(0);
    if (!Array.isArray(events) || events.length === 0) {{
        throw new Error(`Expected events tape, got: ${{JSON.stringify(events)}}`);
    }}
    console.log(`  [Node.js E2E] Events received: ${{events.length}}`);

    await active.close();
    console.log('  [Node.js E2E] Session closed OK');

    // 4. Jobsian Option B Cloud Guard Check
    let cloudErrorCaught = false;
    try {{
        await client.storage.upload('dGVzdA==', 'test.txt');
    }} catch (err) {{
        if (err instanceof CloudServiceRequiredError || err.name === 'CloudServiceRequiredError') {{
            cloudErrorCaught = true;
        }} else {{
            throw new Error(`Expected CloudServiceRequiredError, got: ${{err}}`);
        }}
    }}
    if (!cloudErrorCaught) {{
        throw new Error('Cloud-only call on local client did not throw CloudServiceRequiredError');
    }}
    console.log('  [Node.js E2E] CloudServiceRequiredError guard verified OK');

    console.log('[NODE.JS E2E SUITE COMPLETED 100% GREEN]');
}}

main().catch(err => {{
    console.error('[NODE.JS E2E FAILED]:', err);
    process.exit(1);
}});
"""
        script_path = TS_SDK_DIR / "dist" / "_run_e2e.mjs"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(node_script)

        try:
            res = subprocess.run(["node", str(script_path)], capture_output=True, text=True, timeout=15)
            self.assertEqual(
                res.returncode, 0,
                f"Node.js E2E failed with exit code {res.returncode}:\n{res.stderr}\n{res.stdout}"
            )
            self.assertIn("[NODE.JS E2E SUITE COMPLETED 100% GREEN]", res.stdout)
        finally:
            if script_path.exists():
                script_path.unlink()


if __name__ == "__main__":
    unittest.main()
