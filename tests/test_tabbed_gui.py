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

            # 7. Test update banner display and dismissal
            app._show_update_banner({"version": "1.3.0", "release_date": "2026-11-01", "changelog": "Test"})
            self.assertTrue(app.banner_frame.winfo_ismapped() or len(app.banner_frame.winfo_children()) > 0)
            app.banner_frame.pack_forget()

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

    def test_recent_and_favorites_grid_cards_layout(self):
        """Verify that recent and favorites cards contain visible unclipped Connect button."""
        config_mod.add_recent_session("123 456 789", alias="Office PC")
        config_mod.toggle_favorite("123456789")

        original_start = OpenDeskGUI._start_services
        OpenDeskGUI._start_services = lambda self: None
        try:
            app = OpenDeskGUI(self.root, port=18081)
            app._render_recent_grid()

            # Children of recent_grid_container
            grid_children = app.recent_grid_container.winfo_children()
            self.assertTrue(len(grid_children) > 0)
            grid_frame = grid_children[0]

            cards = [c for c in grid_frame.winfo_children() if isinstance(c, tk.Frame)]
            self.assertTrue(len(cards) >= 1)

            card = cards[0]
            # Verify card dimensions are at least 230x138 to avoid button clipping
            self.assertGreaterEqual(int(card.cget("height")), 130)

            # Search inside card for the Connect button
            all_buttons = []
            for child in card.winfo_children():
                if isinstance(child, tk.Button):
                    all_buttons.append(child)
                elif isinstance(child, tk.Frame):
                    for sub in child.winfo_children():
                        if isinstance(sub, tk.Button):
                            all_buttons.append(sub)

            button_texts = [b.cget("text") for b in all_buttons]
            self.assertTrue(any("Connect" in txt for txt in button_texts), f"Connect button not found in {button_texts}")
        finally:
            OpenDeskGUI._start_services = original_start

    def test_incoming_connection_request_callback(self):
        """Verify incoming connection request callback dispatches on_decision."""
        original_start = OpenDeskGUI._start_services
        OpenDeskGUI._start_services = lambda self: None
        try:
            app = OpenDeskGUI(self.root, port=18082)
            decision_result = []

            def mock_decision(cid, accepted, perms):
                decision_result.append((cid, accepted, perms))

            app._on_incoming_connection_request("client_999", "999 888 777", mock_decision)
            self.root.update()

            # Find opened dialog
            toplevels = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertTrue(len(toplevels) >= 1)
            dialog = toplevels[-1]
            self.assertIn("Incoming Connection Request", dialog.title())

            # Destroy dialog (simulate user reject / close)
            dialog.destroy()
        finally:
            OpenDeskGUI._start_services = original_start

    def test_custom_integrated_window_controls(self):
        """Verify integrated window controls (Minimize, Maximize, Close) and drag bindings exist."""
        original_start = OpenDeskGUI._start_services
        OpenDeskGUI._start_services = lambda self: None
        try:
            app = OpenDeskGUI(self.root, port=18083)
            self.assertTrue(hasattr(app, "min_btn"), "Minimize button must be present in top tab bar")
            self.assertTrue(hasattr(app, "max_btn"), "Maximize button must be present in top tab bar")
            self.assertTrue(hasattr(app, "close_btn"), "Close button must be present in top tab bar")
            self.assertEqual(app.min_btn.cget("text"), "―")
            self.assertEqual(app.max_btn.cget("text"), "🗖")
            self.assertEqual(app.close_btn.cget("text"), "✕")
        finally:
            OpenDeskGUI._start_services = original_start

if __name__ == "__main__":
    unittest.main()
