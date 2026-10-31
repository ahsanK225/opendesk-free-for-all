"""
test_session_management.py - Comprehensive Unit Tests for OpenDesk Session Management
Covers:
- rename_recent_session
- edit_recent_session
- delete_recent_session
- clear_recent_sessions
- GUI card rendering and prompt dialog creation
"""

import unittest
import os
import sys
import tempfile
import json
import tkinter as tk

# Ensure opendesk is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import common.config as config
from opendesk_app import OpenDeskGUI


class TestSessionManagementConfig(unittest.TestCase):
    """Test configuration-level session management functions."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_config_file = config.CONFIG_FILE
        config.CONFIG_FILE = os.path.join(self.tmp_dir.name, "test_config.json")
        # Initialize test sessions
        self.initial_sessions = [
            {"id": "111 222 333", "alias": "Workstation A", "favorite": True, "last_seen": "Oct 30, 10:00"},
            {"id": "444 555 666", "alias": "Laptop B", "favorite": False, "last_seen": "Oct 30, 12:00"},
            {"id": "777 888 999", "alias": "Server C", "favorite": True, "last_seen": "Oct 31, 01:00"}
        ]
        cfg = {"recent_sessions": list(self.initial_sessions)}
        config.save_config(cfg)

    def tearDown(self):
        config.CONFIG_FILE = self.orig_config_file
        self.tmp_dir.cleanup()

    def test_rename_recent_session_success(self):
        """Verify renaming an existing session updates the alias."""
        res = config.rename_recent_session("111 222 333", "Primary Workstation")
        self.assertTrue(res)

        sessions = config.get_recent_sessions()
        matched = [s for s in sessions if s["id"].replace(" ", "") == "111222333"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["alias"], "Primary Workstation")

    def test_rename_recent_session_spacing_tolerance(self):
        """Verify renaming works with or without spaces/dashes in target ID."""
        res = config.rename_recent_session("444-555-666", "Ultra Laptop")
        self.assertTrue(res)

        sessions = config.get_recent_sessions()
        matched = [s for s in sessions if s["id"].replace(" ", "") == "444555666"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["alias"], "Ultra Laptop")

    def test_rename_recent_session_nonexistent(self):
        """Verify renaming nonexistent session returns False."""
        res = config.rename_recent_session("000 000 000", "Ghost Machine")
        self.assertFalse(res)

    def test_edit_recent_session_full(self):
        """Verify editing session ID, alias, and favorite status."""
        res = config.edit_recent_session("444 555 666", "444 555 777", "Upgraded Laptop", favorite=True)
        self.assertTrue(res)

        sessions = config.get_recent_sessions()
        old_matched = [s for s in sessions if s["id"].replace(" ", "") == "444555666"]
        self.assertEqual(len(old_matched), 0)

        new_matched = [s for s in sessions if s["id"].replace(" ", "") == "444555777"]
        self.assertEqual(len(new_matched), 1)
        self.assertEqual(new_matched[0]["alias"], "Upgraded Laptop")
        self.assertTrue(new_matched[0]["favorite"])

    def test_edit_recent_session_autoformat_9digit(self):
        """Verify 9-digit unformatted input is cleanly formatted with spaces."""
        res = config.edit_recent_session("777 888 999", "999888777", "New Server")
        self.assertTrue(res)

        sessions = config.get_recent_sessions()
        new_matched = [s for s in sessions if s["id"] == "999 888 777"]
        self.assertEqual(len(new_matched), 1)
        self.assertEqual(new_matched[0]["alias"], "New Server")

    def test_delete_recent_session(self):
        """Verify deleting an existing session removes it completely."""
        res = config.delete_recent_session("444 555 666")
        self.assertTrue(res)

        sessions = config.get_recent_sessions()
        self.assertEqual(len(sessions), 2)
        remaining_ids = [s["id"].replace(" ", "") for s in sessions]
        self.assertNotIn("444555666", remaining_ids)

    def test_delete_recent_session_nonexistent(self):
        """Verify deleting nonexistent session returns False."""
        res = config.delete_recent_session("999 999 999")
        self.assertFalse(res)

    def test_clear_recent_sessions(self):
        """Verify clearing all sessions empties the list."""
        res = config.clear_recent_sessions()
        self.assertTrue(res)
        sessions = config.get_recent_sessions()
        self.assertEqual(len(sessions), 0)


class TestSessionManagementGUI(unittest.TestCase):
    """Test GUI integration for session card rendering and dialogs."""

    def setUp(self):
        os.environ["OPENDESK_SILENT_TEST"] = "1"
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_config_file = config.CONFIG_FILE
        config.CONFIG_FILE = os.path.join(self.tmp_dir.name, "test_config_gui.json")
        cfg = {
            "recent_sessions": [
                {"id": "524 819 301", "alias": "Studio Workstation", "favorite": True, "last_seen": "Today, 14:20"},
                {"id": "902 411 658", "alias": "Office Laptop", "favorite": False, "last_seen": "Yesterday"}
            ]
        }
        config.save_config(cfg)

        self.orig_start_services = OpenDeskGUI._start_services
        OpenDeskGUI._start_services = lambda s: None

        self.root = tk.Tk()
        self.root.withdraw()
        self.app = OpenDeskGUI(self.root, port=18080)

    def tearDown(self):
        OpenDeskGUI._start_services = self.orig_start_services
        os.environ.pop("OPENDESK_SILENT_TEST", None)
        try:
            for after_id in self.root.tk.eval('after info').split():
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
            self.root.destroy()
        except Exception:
            pass
        config.CONFIG_FILE = self.orig_config_file
        self.tmp_dir.cleanup()

    def test_grid_rendering_all_and_favorites(self):
        """Verify _render_recent_grid creates cards and filters correctly."""
        self.app.recent_filter_var.set("all")
        self.app._render_recent_grid()
        self.root.update_idletasks()
        children = self.app.recent_grid_container.winfo_children()
        self.assertTrue(len(children) > 0)

        # Filter by favorites
        self.app.recent_filter_var.set("favorites")
        self.app._render_recent_grid()
        self.root.update_idletasks()
        fav_children = self.app.recent_grid_container.winfo_children()
        self.assertTrue(len(fav_children) > 0)

    def test_prompt_rename_session_dialog(self):
        """Verify Rename dialog can be instantiated and dismissed."""
        self.app._prompt_rename_session("524 819 301", "Studio Workstation")
        self.root.update_idletasks()

        # Find toplevel dialog
        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialog = dialogs[0]
        self.assertEqual(dialog.title(), "Rename Session")
        dialog.destroy()

    def test_prompt_edit_session_dialog(self):
        """Verify Edit dialog can be instantiated and dismissed."""
        self.app._prompt_edit_session("902 411 658", "Office Laptop", False)
        self.root.update_idletasks()

        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialog = dialogs[0]
        self.assertEqual(dialog.title(), "Edit Session Details")
        dialog.destroy()

    def test_prompt_delete_session_dialog(self):
        """Verify Delete dialog can be instantiated and dismissed."""
        self.app._prompt_delete_session("524 819 301", "Studio Workstation")
        self.root.update_idletasks()

        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        dialog = dialogs[0]
        self.assertEqual(dialog.title(), "Delete Session")
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
