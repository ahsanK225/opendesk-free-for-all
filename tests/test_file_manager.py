"""
Unit Tests for Remote File Manager
"""

import unittest
import os
import shutil
import tempfile
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from opendesk.host.file_manager import FileManager

class TestFileManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.fm = FileManager(root_dir=self.test_dir)
        
        # Create test sample file
        self.sample_file = os.path.join(self.test_dir, "test.txt")
        with open(self.sample_file, "w") as f:
            f.write("Hello OpenDesk Remote Desktop!\n" * 100)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_list_directory(self):
        res = self.fm.list_directory(self.test_dir)
        self.assertNotIn("error", res)
        self.assertEqual(len(res["entries"]), 1)
        self.assertEqual(res["entries"][0]["name"], "test.txt")
        self.assertFalse(res["entries"][0]["is_dir"])

    def test_chunked_download(self):
        chunk_res = self.fm.read_file_chunk(self.sample_file, 0)
        self.assertNotIn("error", chunk_res)
        self.assertEqual(chunk_res["filename"], "test.txt")
        self.assertEqual(chunk_res["chunk_index"], 0)
        self.assertTrue(chunk_res["is_last"])
        self.assertGreater(len(chunk_res["data"]), 0)

    def test_chunked_upload(self):
        upload_id = "test_up_1"
        content = b"Binary Payload for Remote Upload" * 50
        import base64
        b64_content = base64.b64encode(content).decode("ascii")

        # 1. Start upload
        start_res = self.fm.start_upload(upload_id, self.test_dir, "uploaded.bin", 1, len(content))
        self.assertEqual(start_res["status"], "ready")

        # 2. Write chunk
        chunk_res = self.fm.write_upload_chunk(upload_id, 0, b64_content)
        self.assertEqual(chunk_res["status"], "complete")
        
        # 3. Verify on disk
        dest_path = os.path.join(self.test_dir, "uploaded.bin")
        self.assertTrue(os.path.exists(dest_path))
        with open(dest_path, "rb") as f:
            self.assertEqual(f.read(), content)

if __name__ == "__main__":
    unittest.main()
