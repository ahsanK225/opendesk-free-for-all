import os
import sys
import unittest
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from client.viewer import NativeSessionViewer, EmbeddedSessionView
from host.input_controller import WindowsInputController

class TestNativeViewer(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            for after_id in self.root.tk.eval('after info').split():
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
            self.root.destroy()
        except Exception:
            pass

    def test_viewer_initialization(self):
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        self.assertEqual(viewer.target_id, "780363657")
        self.assertIsNotNone(viewer.win)
        self.assertTrue(viewer.win.winfo_exists())
        self.assertEqual(viewer.view.view_mode, "fit")
        self.assertEqual(viewer.view.zoom_level, 1.0)
        self.assertEqual(viewer.view.pan_x, 0)
        self.assertEqual(viewer.view.pan_y, 0)
        self.assertEqual(viewer._map_tk_keysym_to_js("Return"), "Enter")
        self.assertEqual(viewer._map_tk_keysym_to_js("BackSpace"), "Backspace")
        self.assertEqual(viewer._map_tk_keysym_to_js("a"), "KeyA")
        viewer._on_close()

    def test_display_modes_and_switching(self):
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view

        # Default is fit
        self.assertEqual(view.view_mode, "fit")

        # Switch to stretch
        view.set_view_mode("stretch")
        self.assertEqual(view.view_mode, "stretch")

        # Switch to original
        view.set_view_mode("original")
        self.assertEqual(view.view_mode, "original")

        # Invalid mode should be ignored
        view.set_view_mode("invalid_mode")
        self.assertEqual(view.view_mode, "original")

        # Switch back to fit via wrapper
        viewer.set_view_mode("fit")
        self.assertEqual(view.view_mode, "fit")

        viewer._on_close()

    def test_zoom_controls_and_clamping(self):
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view

        # Initial zoom 1.0
        self.assertEqual(view.zoom_level, 1.0)

        # Zoom in (+0.25)
        viewer.zoom_in(0.25)
        self.assertEqual(view.zoom_level, 1.25)

        # Zoom in again
        viewer.zoom_in(0.25)
        self.assertEqual(view.zoom_level, 1.5)

        # Zoom out (-0.25)
        viewer.zoom_out(0.25)
        self.assertEqual(view.zoom_level, 1.25)

        # Reset zoom
        viewer.reset_zoom()
        self.assertEqual(view.zoom_level, 1.0)
        self.assertEqual(view.pan_x, 0)
        self.assertEqual(view.pan_y, 0)

        # Clamping upper bound at 3.0
        view.set_zoom(5.0)
        self.assertEqual(view.zoom_level, 3.0)

        # Clamping lower bound at 0.5
        view.set_zoom(0.1)
        self.assertEqual(view.zoom_level, 0.5)

        viewer._on_close()

    def test_coordinate_normalization_fit_mode(self):
        """
        Verify coordinate mapping in Fit mode with letterboxing/pillarboxing.
        Remote: 1920x1080. Canvas: 1000x600.
        Scale = min(1000/1920=0.5208, 600/1080=0.5555) = 0.520833
        Rendered dw = int(1920 * 0.520833) = 1000.
        Rendered dh = int(1080 * 0.520833) = 562.
        Offset X = 0. Offset Y = (600 - 562) // 2 = 19.
        """
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view
        view.view_mode = "fit"
        view.zoom_level = 1.0
        view.pan_x = 0
        view.pan_y = 0
        view.remote_width = 1920
        view.remote_height = 1080
        view.display_width = 1000
        view.display_height = 562
        view.offset_x = 0
        view.offset_y = 19

        # Clicks inside top/bottom black bars should return None (no stray clicks sent)
        self.assertEqual(view._normalize_coords(500, 5), (None, None))
        self.assertEqual(view._normalize_coords(500, 595), (None, None))

        # Click at top-left of remote image (0, 19)
        nx, ny = view._normalize_coords(0, 19)
        self.assertAlmostEqual(nx, 0.0, places=3)
        self.assertAlmostEqual(ny, 0.0, places=3)

        # Click at center of remote image (500, 19 + 281 = 300)
        nx, ny = view._normalize_coords(500, 300)
        self.assertAlmostEqual(nx, 0.5, places=3)
        self.assertAlmostEqual(ny, 0.5, places=3)

        # Click at bottom-right of remote image (1000, 19 + 562 = 581)
        nx, ny = view._normalize_coords(1000, 581)
        self.assertAlmostEqual(nx, 1.0, places=3)
        self.assertAlmostEqual(ny, 1.0, places=3)

        viewer._on_close()

    def test_coordinate_normalization_stretch_mode(self):
        """
        Verify Stretch to Fill mode eliminates black bars and maps full canvas to 0.0..1.0.
        Canvas: 1200x700. Remote: 1920x1080.
        dw = 1200, dh = 700. offset_x = 0, offset_y = 0.
        """
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view
        view.view_mode = "stretch"
        view.zoom_level = 1.0
        view.pan_x = 0
        view.pan_y = 0
        view.remote_width = 1920
        view.remote_height = 1080
        view.display_width = 1200
        view.display_height = 700
        view.offset_x = 0
        view.offset_y = 0

        # Entire canvas is active, zero black bars
        nx, ny = view._normalize_coords(0, 0)
        self.assertAlmostEqual(nx, 0.0, places=3)
        self.assertAlmostEqual(ny, 0.0, places=3)

        nx, ny = view._normalize_coords(600, 350)
        self.assertAlmostEqual(nx, 0.5, places=3)
        self.assertAlmostEqual(ny, 0.5, places=3)

        nx, ny = view._normalize_coords(1200, 700)
        self.assertAlmostEqual(nx, 1.0, places=3)
        self.assertAlmostEqual(ny, 1.0, places=3)

        viewer._on_close()

    def test_coordinate_normalization_zoomed_and_panned(self):
        """
        Verify Zoomed (e.g. 200%) mode with Pan offset transforms accurately.
        dw = 2000, dh = 1000. offset_x = -500, offset_y = -200 (panned).
        frame_left = -500, frame_top = -200.
        """
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view
        view.view_mode = "fit"
        view.zoom_level = 2.0
        view.display_width = 2000
        view.display_height = 1000
        view.offset_x = 0
        view.offset_y = 0
        view.pan_x = -500
        view.pan_y = -200

        # Point at canvas (500, 300):
        # local_x = 500 - (-500) = 1000 -> nx = 1000 / 2000 = 0.5
        # local_y = 300 - (-200) = 500  -> ny = 500 / 1000 = 0.5
        nx, ny = view._normalize_coords(500, 300)
        self.assertAlmostEqual(nx, 0.5, places=3)
        self.assertAlmostEqual(ny, 0.5, places=3)

        viewer._on_close()

    def test_host_backward_compatibility_coordinate_invariance(self):
        """
        Verify backward compatibility: An older host agent receiving normalized coordinates
        scales them via `int(norm_x * host_width), int(norm_y * host_height)`.
        Assert the pixel targeted on the client maps to the exact host pixel.
        """
        host_width = 1920
        host_height = 1080

        # Simulate client canvas click normalized output
        viewer = NativeSessionViewer(parent=self.root, relay_url="ws://127.0.0.1:8999/ws", target_id="780 363 657")
        view = viewer.view
        view.view_mode = "stretch"
        view.display_width = 1366
        view.display_height = 768
        view.offset_x = 0
        view.offset_y = 0
        view.pan_x = 0
        view.pan_y = 0

        # Click at 25% of client screen
        client_click_x = int(1366 * 0.25)
        client_click_y = int(768 * 0.25)
        nx, ny = view._normalize_coords(client_click_x, client_click_y)

        # Host calculates absolute screen position
        host_target_x = int(nx * host_width)
        host_target_y = int(ny * host_height)

        expected_host_x = int(1920 * 0.25)
        expected_host_y = int(1080 * 0.25)

        self.assertAlmostEqual(host_target_x, expected_host_x, delta=2)
        self.assertAlmostEqual(host_target_y, expected_host_y, delta=2)

        viewer._on_close()

if __name__ == "__main__":
    unittest.main()
