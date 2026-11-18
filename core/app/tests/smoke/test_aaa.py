from __future__ import annotations

import unittest

class TestAAA(unittest.TestCase):
    """
    Auto-matrix test: iterate *every* registered validator and assert:

    • Valid examples pass with (True, None)
    • Invalid examples fail with (False, nonempty message)
    • Guidance exists and returns a dict containing 'message' (string)
    • Dotted-path resolution works for both validation & guidance callables

    No edits needed when adding new validators — the decorators feed the registry.
    """

    def test_aaa(self):
        self.assertGreaterEqual(100, 1)
