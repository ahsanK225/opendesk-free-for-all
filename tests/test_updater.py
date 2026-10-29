import os
import sys
import unittest
import io
import tempfile
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.updater import (
    parse_version,
    is_newer_version,
    check_for_updates,
    download_update_file,
    APP_VERSION
)

class TestUpdater(unittest.TestCase):
    def test_version_parsing(self):
        self.assertEqual(parse_version("1.2.0"), (1, 2, 0))
        self.assertEqual(parse_version("v1.2.1"), (1, 2, 1))
        self.assertEqual(parse_version("2.0"), (2, 0, 0))
        self.assertEqual(parse_version("v10.5.12-beta"), (10, 5, 12))

    def test_version_comparison(self):
        self.assertTrue(is_newer_version("1.2.1", "1.2.0"))
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))
        self.assertTrue(is_newer_version("1.3.0", "1.2.9"))
        self.assertFalse(is_newer_version("1.2.0", "1.2.0"))
        self.assertFalse(is_newer_version("1.1.9", "1.2.0"))
        self.assertFalse(is_newer_version("1.0.0", "1.2.0"))

    @patch("urllib.request.urlopen")
    def test_check_for_updates_available(self, mock_urlopen):
        sample_manifest = {
            "version": "1.3.0",
            "release_date": "2026-11-01",
            "download_url": "https://example.com/OpenDesk.exe",
            "installer_url": "https://example.com/OpenDesk_Setup.exe",
            "changelog": ["Feature A", "Feature B"]
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(sample_manifest).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_for_updates(current_version="1.2.0", manifest_url="http://fake.url")
        self.assertIsNotNone(result)
        self.assertTrue(result["available"])
        self.assertEqual(result["version"], "1.3.0")
        self.assertIn("Feature A", result["changelog"])

    @patch("urllib.request.urlopen")
    def test_check_for_updates_up_to_date(self, mock_urlopen):
        sample_manifest = {
            "version": APP_VERSION,
            "release_date": "2026-10-29",
            "download_url": "https://example.com/OpenDesk.exe",
            "changelog": []
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(sample_manifest).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_for_updates(current_version=APP_VERSION, manifest_url="http://fake.url")
        self.assertIsNotNone(result)
        self.assertFalse(result["available"])

    @patch("urllib.request.urlopen")
    def test_download_update_file(self, mock_urlopen):
        content = b"TEST_BINARY_DATA_FOR_OPENDESK"
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(content))}
        mock_resp.read.side_effect = [content, b""]
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        progress_calls = []
        def on_prog(d, t):
            progress_calls.append((d, t))

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            dest = tf.name

        try:
            success = download_update_file("http://fake.url/OpenDesk.exe", dest, progress_callback=on_prog)
            self.assertTrue(success)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), content)
            self.assertTrue(len(progress_calls) > 0)
            self.assertEqual(progress_calls[-1], (len(content), len(content)))
        finally:
            if os.path.exists(dest):
                os.remove(dest)

if __name__ == "__main__":
    unittest.main()
