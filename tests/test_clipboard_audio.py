import os
import sys
import unittest
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.config import get_persistent_host_id, load_config, save_config
from host.audio import AudioEngine
from host.input_controller import WindowsInputController

class TestConfigAndFeatures(unittest.TestCase):
    def test_persistent_host_id(self):
        host_id = get_persistent_host_id()
        self.assertIsNotNone(host_id)
        clean = host_id.replace(" ", "")
        self.assertEqual(len(clean), 9)
        # Calling again should return the exact same ID
        host_id_2 = get_persistent_host_id()
        self.assertEqual(host_id, host_id_2)

    def test_audio_device_detection(self):
        engine = AudioEngine()
        dev = engine._find_best_input_device()
        # Should return an integer index or None if no device
        if dev is not None:
            self.assertIsInstance(dev, int)

    def test_input_controller_shortcuts(self):
        controller = WindowsInputController()
        # Verify controller has execute_shortcut method without crashing
        self.assertTrue(hasattr(controller, "execute_shortcut"))
        # We don't simulate real keybd_event during automated CI if possible,
        # but the method should exist and accept 'paste' and 'copy'
        self.assertTrue(callable(controller.execute_shortcut))

if __name__ == "__main__":
    unittest.main()
