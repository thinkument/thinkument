"""Tests for the Universal Vendor Interceptor ('The Transcendental Mocking Seam')."""
import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

from thinkument.daemon.interceptor import (
    VendorInvocation,
    default_mock_interceptor,
    create_ollama_interceptor,
    create_webhook_interceptor,
    load_interceptor_from_file,
)


class TestVendorInterceptor(unittest.TestCase):

    def test_default_mock_interceptor_llm(self):
        inv = VendorInvocation(
            operation="vendor.llm.chat_completion",
            modality="llm",
            args={"model": "gpt-4o", "prompt": "Summarize Q3 earnings report"},
            call_key="step_1:w1:1",
        )
        res = default_mock_interceptor(inv)
        self.assertIn("[Mock gpt-4o]", res["text"])
        self.assertIn("Summarize Q3", res["text"])
        self.assertIn("usage", res)
        self.assertGreaterEqual(res["usage"]["prompt_tokens"], 1)

    def test_default_mock_interceptor_dict_input(self):
        inv_dict = {
            "operation": "vendor.llm.chat_completion",
            "modality": "llm",
            "args": {"model": "claude-3-5", "prompt": "Hello world"},
            "call_key": "step_1:w1:2",
        }
        res = default_mock_interceptor(inv_dict)
        self.assertIn("[Mock claude-3-5]", res["text"])
        self.assertIn("Hello world", res["text"])

    def test_default_mock_interceptor_other_modalities(self):
        inv_img = VendorInvocation(
            operation="vendor.image.generate",
            modality="image",
            args={"prompt": "A cat"},
            call_key="step_1:w1:img",
        )
        res_img = default_mock_interceptor(inv_img)
        self.assertTrue(res_img["image_url"].startswith("mock://"))

        inv_emb = VendorInvocation(
            operation="vendor.embeddings.create",
            modality="embeddings",
            args={"input": "test"},
            call_key="step_1:w1:emb",
        )
        res_emb = default_mock_interceptor(inv_emb)
        self.assertEqual(len(res_emb["embeddings"]), 128)

    def test_load_interceptor_from_file(self):
        code = """
def intercept_vendor_op(inv):
    return {"text": f"Custom intercept: {inv['args'].get('prompt')}", "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            handler = load_interceptor_from_file(temp_path)
            inv = VendorInvocation(
                operation="vendor.llm.chat_completion",
                modality="llm",
                args={"prompt": "Custom prompt"},
                call_key="k1",
            )
            res = handler(inv)
            self.assertEqual(res["text"], "Custom intercept: Custom prompt")
            self.assertEqual(res["usage"]["completion_tokens"], 20)
        finally:
            os.unlink(temp_path)

    def test_webhook_interceptor(self):
        received = []

        class MockWebhookServer(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                received.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"text": "webhook-mock-reply", "usage": {"units": 1}}).encode("utf-8"))

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), MockWebhookServer)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        try:
            proxy = create_webhook_interceptor(f"http://127.0.0.1:{port}/mock")
            inv = VendorInvocation(
                operation="vendor.llm.chat_completion",
                modality="llm",
                args={"model": "gpt-4o", "prompt": "Testing webhook"},
                call_key="call_99",
            )
            res = proxy(inv)
            self.assertEqual(res["text"], "webhook-mock-reply")
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["call_key"], "call_99")
            self.assertEqual(received[0]["args"]["prompt"], "Testing webhook")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
