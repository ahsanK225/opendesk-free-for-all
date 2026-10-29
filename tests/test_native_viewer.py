import os
import sys
import unittest
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from client.viewer import NativeSessionViewer

class TestNativeViewer(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_viewer_initialization(self):
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        self.assertEqual(viewer.target_id, "780363657")
        self.assertIsNotNone(viewer.win)
        self.assertTrue(viewer.win.winfo_exists())
        self.assertEqual(viewer._map_tk_keysym_to_js("Return"), "Enter")
        self.assertEqual(viewer._map_tk_keysym_to_js("BackSpace"), "Backspace")
        self.assertEqual(viewer._map_tk_keysym_to_js("a"), "KeyA")
        viewer._on_close()

if __name__ == "__main__":
    unittest.main()
