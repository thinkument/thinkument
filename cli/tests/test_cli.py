"""Tests for the Thinkument Unified CLI."""
import json
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from thinkument.cli import build_parser, main


class TestCli(unittest.TestCase):

    def test_parser_subcommands(self):
        parser = build_parser()
        args = parser.parse_args(["dev", "--port", "5055", "--mode", "mock"])
        self.assertEqual(args.command, "dev")
        self.assertEqual(args.port, 5055)
        self.assertEqual(args.mode, "mock")

        args = parser.parse_args(["validate", "test.json"])
        self.assertEqual(args.command, "validate")
        self.assertEqual(args.manifest, "test.json")

        args = parser.parse_args(["publish", "widget.json", "--api-key", "tk_test_123"])
        self.assertEqual(args.command, "publish")
        self.assertEqual(args.api_key, "tk_test_123")

        args = parser.parse_args(["run", "prog.json", "--context", "ctx.json", "--cloud"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.context, "ctx.json")
        self.assertTrue(args.cloud)

        args = parser.parse_args(["balance", "--api-key", "tk_test_123"])
        self.assertEqual(args.command, "balance")

    def test_validate_command_valid(self):
        widget = {
            "kind": "json_widget_v1",
            "name": "test.valid_widget",
            "declaration": {"inputs": {}, "outputs": {}},
            "signals": {"mount": {}},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(widget, f)
            path = f.name

        try:
            with patch("sys.stdout", new=StringIO()) as out:
                code = main(["validate", path])
                self.assertEqual(code, 0)
                self.assertIn("Valid Thinkument json_widget_v1", out.getvalue())
        finally:
            os.unlink(path)

    def test_validate_command_invalid(self):
        invalid_widget = {"kind": "json_widget_v1"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(invalid_widget, f)
            path = f.name

        try:
            with patch("sys.stderr", new=StringIO()) as err:
                code = main(["validate", path])
                self.assertEqual(code, 1)
                self.assertIn("Invalid manifest", err.getvalue())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
