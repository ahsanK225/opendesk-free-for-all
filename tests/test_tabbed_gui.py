import os
import sys
import unittest
import tempfile
import json
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from opendesk_app import OpenDeskGUI
import common.config as config_mod

class TestTabbedGUI(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_config_file = os.path.join(self.temp_dir.name, "config.json")
        self.patcher = patch.object(config_mod, "CONFIG_FILE", self.temp_config_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_gui_tab_lifecycle(self):
        # Override _start_services to avoid background network threads in unit test
        original_start = OpenDeskGUI._start_services
        OpenDeskGUI._start_services = lambda self: None
        try:
            app = OpenDeskGUI(self.root, port=18080)
            
            # 1. Verify Home tab
            self.assertEqual(len(app.tabs), 1)
            self.assertEqual(app.tabs[0]["id"], "home")
            self.assertEqual(app.active_tab_id, "home")

            # 2. Test format ID
            self.assertEqual(app._format_id("780363657"), "780 363 657")
            self.assertEqual(app._format_id("123"), "123")

            # 3. Launch a session tab
            app._launch_session("999 888 777")
            self.assertEqual(len(app.tabs), 2)
            self.assertEqual(app.tabs[1]["id"], "999888777")
            self.assertEqual(app.active_tab_id, "999888777")

            # 4. Switch back to home
            app.switch_tab("home")
            self.assertEqual(app.active_tab_id, "home")

            # 5. Switch back to session tab
            app.switch_tab("999888777")
            self.assertEqual(app.active_tab_id, "999888777")

            # 6. Close the session tab
            app.close_tab("999888777")
            self.assertEqual(len(app.tabs), 1)
            self.assertEqual(app.active_tab_id, "home")

        finally:
            OpenDeskGUI._start_services = original_start

    def test_recent_sessions_and_favorites(self):
        config_mod.add_recent_session("111 222 333", alias="Test Workstation")
        recents = config_mod.get_recent_sessions()
        matched = next((r for r in recents if "111" in r.get("id", "")), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.get("alias"), "Test Workstation")
        self.assertFalse(matched.get("favorite", False))

        # Toggle favorite
        is_fav = config_mod.toggle_favorite("111222333")
        self.assertTrue(is_fav)

        # Toggle back
        is_fav_again = config_mod.toggle_favorite("111222333")
        self.assertFalse(is_fav_again)

if __name__ == "__main__":
    unittest.main()
