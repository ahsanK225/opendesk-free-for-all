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

    def test_vectorized_diff_and_clustering(self):
        import numpy as np
        # 1. Base frame with uint32 array
        arr1 = np.full((self.height, self.width), 0xFF202028, dtype=np.uint32)
        res1 = self.codec.encode(self.base_image, raw_u32=arr1, force_keyframe=True)
        self.assertEqual(res1["kind"], "full")

        # 2. Identical frame -> empty delta in <1ms
        res_empty = self.codec.encode(self.base_image, raw_u32=arr1)
        self.assertEqual(res_empty["kind"], "empty")

        # 3. Clustered 8 tiles changed (e.g. window moved or discord popup)
        arr2 = arr1.copy()
        arr2[200:500, 300:700] = 0xFFFF0000
        modified = self.base_image.copy()
        draw = ImageDraw.Draw(modified)
        draw.rectangle([300, 200, 700, 500], fill=(255, 0, 0))

        res_cluster = self.codec.encode(modified, raw_u32=arr2)
        self.assertEqual(res_cluster["kind"], "delta")
        self.assertGreaterEqual(res_cluster["dirty_count"], 5)
        # Verify bounding box was clustered into 1 efficient tile update
        self.assertEqual(len(res_cluster["tiles"]), 1)
        cluster_tile = res_cluster["tiles"][0]
        self.assertEqual(cluster_tile["x"], 256)
        self.assertEqual(cluster_tile["y"], 128)
        self.assertEqual(cluster_tile["w"], 512)
        self.assertEqual(cluster_tile["h"], 384)

if __name__ == "__main__":
    unittest.main()
