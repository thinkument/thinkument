"""Tests for ThinkClient.connect() against cloud endpoints."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from thinkument import ThinkClient


class MockCloudServer(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if "Bearer tk_test_key" not in auth:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}')
            return

        if self.path == "/api/v1/wallet/balance/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "available_credits": 250000,
                "currency": "microcredits",
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        if "Bearer tk_test_key" not in auth:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}')
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        if self.path == "/api/v1/ops/execute/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "text": f"Cloud Relay completion for {body.get('operation')}",
                "usage": {"prompt_tokens": 12, "completion_tokens": 24},
            }).encode("utf-8"))
            return

        if self.path == "/api/v1/sessions/":
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "kind": "web_RESTful_launch_result_v1",
                "session_id": "sid_cloud_123",
                "starter_id": "starter_cloud_456",
                "public_view_role": "analyst",
                "selected": {
                    "role": "analyst",
                    "slug": "s_cloud_analyst",
                    "url": "https://thinkument.com/live/s_cloud_analyst",
                    "path": "/live/s_cloud_analyst",
                },
                "handles": {
                    "analyst": {
                        "role": "analyst",
                        "slug": "s_cloud_analyst",
                        "url": "https://thinkument.com/live/s_cloud_analyst",
                        "path": "/live/s_cloud_analyst",
                    }
                },
            }).encode("utf-8"))
            return

        if self.path == "/api/v1/blackbox/run/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "outputs": {"summary": "Completed analysis"},
                "canonical_context": {"step": 2},
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class TestSdkCloudMock(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockCloudServer)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        cls.client = ThinkClient.connect(
            api_key="tk_test_key",
            endpoint=f"http://127.0.0.1:{cls.port}",
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_cloud_ops_relay(self):
        res = self.client.ops.execute(
            operation="vendor.llm.chat_completion",
            args={"model": "gpt-4o", "prompt": "Cloud prompt"},
        )
        self.assertIn("Cloud Relay completion", res["text"])
        self.assertEqual(res["usage"]["prompt_tokens"], 12)

    def test_cloud_wallet_balance(self):
        bal = self.client.economics.get_balance()
        self.assertEqual(bal.available_credits, 250000)
        self.assertEqual(bal.currency, "microcredits")

    def test_cloud_live_create(self):
        live_run = self.client.live.create(
            P={"kind": "think_program_v1"},
            SM={"roles": {"analyst": {}}},
            public_view_role="analyst",
        )
        self.assertEqual(live_run.session_id, "sid_cloud_123")
        self.assertEqual(live_run.selected.slug, "s_cloud_analyst")
        self.assertIn("analyst", live_run.handles)

    def test_cloud_blackbox_run(self):
        job = self.client.blackbox.run(
            P={"kind": "think_program_v1"},
            C={"key": "val"},
        )
        res = job.wait()
        self.assertTrue(res.ok)
        self.assertEqual(res.outputs["summary"], "Completed analysis")

    def test_cloud_unauthorized_fails(self):
        bad_client = ThinkClient.connect(
            api_key="bad_key",
            endpoint=f"http://127.0.0.1:{self.port}",
        )
        with self.assertRaises(RuntimeError) as ctx:
            bad_client.economics.get_balance()
        self.assertIn("HTTP 401", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
