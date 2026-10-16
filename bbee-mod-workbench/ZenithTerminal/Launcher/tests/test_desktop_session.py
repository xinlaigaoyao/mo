"""Synthetic WTS headers only; no desktop, account or live session queries."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER.parents[1] / "scripts"))
import desktop_session as desktop


class DesktopSessionTests(unittest.TestCase):
    def inspect(self, flags, *, level=1, actual=7, connection=0):
        header = struct.pack("<I4xIIi", level, actual, connection, flags)
        with patch("desktop_session._supported_platform", return_value=True), \
             patch("desktop_session._query_header", return_value=(7, header)):
            return desktop.inspect_session()

    def test_unlocked_current_active_session_is_required(self):
        result = self.inspect(1)
        self.assertEqual(result["status"], "unlocked")
        self.assertTrue(result["unlocked"])
        self.assertFalse(result["locked"])

    def test_locked_session_cannot_be_reported_as_unlocked(self):
        result = self.inspect(0)
        self.assertEqual(result["status"], "locked")
        self.assertTrue(result["locked"])
        self.assertFalse(result["unlocked"])

    def test_unknown_flag_is_not_assumed_unlocked(self):
        for flag in (-1, 2):
            with self.subTest(flag=flag):
                result = self.inspect(flag)
                self.assertEqual(result["status"], "unknown")
                self.assertFalse(result["unlocked"])

    def test_other_session_header_is_rejected(self):
        result = self.inspect(1, actual=8)
        self.assertEqual(result["reason"], "session_mismatch")
        self.assertFalse(result["unlocked"])

    def test_api_failure_is_sanitized_and_blocks_prepare(self):
        with patch("desktop_session._supported_platform", return_value=True), \
             patch("desktop_session._query_header", side_effect=OSError("PRIVATE-ACCOUNT-MARKER")):
            result = desktop.inspect_session()
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["reason"], "session_query_failed")
            self.assertNotIn("PRIVATE-ACCOUNT-MARKER", str(result))
            with self.assertRaises(desktop.DesktopSessionError):
                desktop.require_unlocked()

    def test_unrecognized_level_and_inactive_session_are_not_unlocked(self):
        self.assertEqual(self.inspect(1, level=2)["reason"], "unsupported_information_level")
        self.assertEqual(self.inspect(1, connection=4)["reason"], "session_not_active")

    def test_unsupported_platform_never_queries_wts(self):
        with patch("desktop_session._supported_platform", return_value=False), \
             patch("desktop_session._query_header") as query:
            self.assertEqual(desktop.inspect_session()["reason"], "unsupported_platform")
            query.assert_not_called()

    def test_short_header_is_unknown(self):
        with patch("desktop_session._supported_platform", return_value=True), \
             patch("desktop_session._query_header", return_value=(7, b"short")):
            self.assertEqual(desktop.inspect_session()["reason"], "malformed_response")


if __name__ == "__main__":
    unittest.main()
