"""
Unit Tests for DeskRT Tile & Delta Codec
"""

import unittest
from PIL import Image, ImageDraw
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from opendesk.common.codec import DeskRTCodec

class TestDeskRTCodec(unittest.TestCase):
    def setUp(self):
        self.codec = DeskRTCodec(tile_size=128, quality=70)
        self.width = 1920
        self.height = 1080
        # Create solid background image
        self.base_image = Image.new("RGB", (self.width, self.height), color=(30, 30, 40))

    def test_keyframe_generation(self):
        res = self.codec.encode(self.base_image, force_keyframe=True)
        self.assertEqual(res["kind"], "full")
        self.assertEqual(res["width"], self.width)
        self.assertEqual(res["height"], self.height)
        self.assertGreater(res["byte_size"], 1000)

    def test_static_frame_empty_delta(self):
        # First frame: keyframe
        self.codec.encode(self.base_image, force_keyframe=True)
        # Second frame: identical image
        res = self.codec.encode(self.base_image)
        self.assertEqual(res["kind"], "empty")
        self.assertEqual(res["dirty_count"], 0)
        self.assertEqual(res["byte_size"], 0)

    def test_single_tile_delta(self):
        # 1. First keyframe
        full_res = self.codec.encode(self.base_image, force_keyframe=True)
        full_bytes = full_res["byte_size"]
        
        # 2. Modify only a small 20x20 region at (100, 100)
        modified = self.base_image.copy()
        draw = ImageDraw.Draw(modified)
        draw.rectangle([100, 100, 120, 120], fill=(255, 0, 0))
        
        # 3. Delta encode
        delta_res = self.codec.encode(modified)
        self.assertEqual(delta_res["kind"], "delta")
        self.assertEqual(delta_res["dirty_count"], 1)
        self.assertEqual(len(delta_res["tiles"]), 1)
        
        tile = delta_res["tiles"][0]
        self.assertEqual(tile["x"], 0)
        self.assertEqual(tile["y"], 0)
        
        # Bandwidth saving verification: delta tile must be much smaller than full frame
        self.assertLess(delta_res["byte_size"], full_bytes * 0.1)

if __name__ == "__main__":
    unittest.main()
