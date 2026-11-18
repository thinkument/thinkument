"""The public credential contract is pure, strict and safe to represent."""
from datetime import datetime, timezone
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from serviceCredsTM import AccountSpec, CredentialError, load_credentials


class CredentialContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = AccountSpec('INTEGRATION', api_key=True)
        self.values = dict(zip(self.spec.fields, ['ci', 'ci@example.test', 'public', 'very-secret', '2035-01-01T00:00:00Z']))

    def test_pure_import_and_redacted_representation(self):
        result = load_credentials(self.spec, self.values)
        self.assertNotIn('very-secret', repr(result))
        self.assertNotIn('ci@example.test', repr(result))
        self.assertEqual(result.expires_at, datetime(2035, 1, 1, tzinfo=timezone.utc))
        code = "import serviceCredsTM,sys; assert 'django' not in sys.modules"
        import os
        subprocess.run([sys.executable, '-c', code], check=True,
                       env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]/'src')})

    def test_missing_fields_and_errors_do_not_echo_values(self):
        for key in self.spec.fields:
            with self.subTest(key=key):
                values = {**self.values, key: ''}
                with self.assertRaises(CredentialError) as error:
                    load_credentials(self.spec, values)
                self.assertIn(key, str(error.exception))
                self.assertNotIn('very-secret', str(error.exception))

    def test_expiry_is_absolute_utc_and_never_slides(self):
        for timestamp in ['2035-01-01', '2035-01-01T00:00:00+00:00', '2035-99-01T00:00:00Z', '2000-01-01T00:00:00Z']:
            with self.subTest(timestamp=timestamp), self.assertRaises(CredentialError):
                load_credentials(self.spec, {**self.values, 'CUSKEY_INTEGRATION__APIKEY_EXPIRES_AT': timestamp})
        first = load_credentials(self.spec, self.values, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        second = load_credentials(self.spec, self.values, now=datetime(2028, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(first.expires_at, second.expires_at)

    def test_header_delimiters_and_line_breaks_are_rejected(self):
        for value in ['secret:extra', 'secret extra', 'secret\nextra']:
            with self.subTest(value=value), self.assertRaises(CredentialError):
                load_credentials(self.spec, {**self.values, 'CUSKEY_INTEGRATION__APIKEY_SECRET': value})
