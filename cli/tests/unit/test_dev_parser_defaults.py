import unittest

from thinkument.cli import build_parser


class TestDevParserDefaults(unittest.TestCase):
    def test_dev_defaults_to_local_mock_mode(self):
        args = build_parser().parse_args(["dev"])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 5052)
        self.assertEqual(args.mode, "mock")
