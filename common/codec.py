"""
DeskRT-style Tile & Delta Video Codec for OpenDesk
Implements GUI-optimized screen compression:
- Uniform tile grid partitioning (e.g. 128x128 or 64x64)
- Fast dirty-rect / dirty-tile change detection
- Delta transmission (transmits only tiles that changed between frames)
- Adaptive quality & keyframe generation
- High-efficiency encoding using Pillow JPEG with memory buffers
"""

import io
import time
import hashlib
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from PIL import Image

class DeskRTCodec:
    def __init__(self, tile_size: int = 128, quality: int = 65, keyframe_interval: float = 5.0):
        self.tile_size = tile_size
        self.quality = quality
        self.keyframe_interval = keyframe_interval
        
        self.prev_image: Optional[Image.Image] = None
        self.prev_u32: Optional[np.ndarray] = None
        self.prev_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        self.last_keyframe_time: float = 0.0
        self.frame_index: int = 0
        self.width: int = 0
        self.height: int = 0

    def set_quality(self, quality: int):
        self.quality = max(10, min(95, quality))

    def reset(self):
        self.prev_image = None
        self.prev_u32 = None
        self.prev_tile_hashes.clear()
        self.last_keyframe_time = 0.0
        self.frame_index = 0

    def _hash_tile(self, img_crop: Image.Image) -> bytes:
        """Compute quick digest of tile pixel data for fallback dirty detection."""
        return hashlib.md5(img_crop.tobytes()).digest()

    def _compress_image_bytes(self, img: Image.Image, quality: Optional[int] = None) -> bytes:
        """Compress PIL Image to fast JPEG bytes using 4:2:0 subsampling."""
        q = quality if quality is not None else self.quality
        if img.mode != 'RGB':
            rgb_img = img.convert('RGB')
        else:
            rgb_img = img
            
        buffer = io.BytesIO()
        rgb_img.save(buffer, format='JPEG', quality=q, optimize=False, subsampling='4:2:0')
        return buffer.getvalue()

    def encode(self, image: Image.Image, raw_u32: Optional[np.ndarray] = None, force_keyframe: bool = False) -> Dict[str, Any]:
        """
        Encode an image frame at high throughput (30-60 FPS).
        Uses zero-copy uint32 vectorized diff when raw_u32 is provided (<1ms),
        and clusters adjacent dirty tiles into merged bounding regions to minimize
        JPEG compression overhead and network serialization.
        """
        now = time.time()
        self.frame_index += 1
        w, h = image.size
        
        # Check if resolution changed or keyframe interval elapsed
        is_keyframe = (
            force_keyframe or 
            self.prev_image is None or 
            (w != self.width or h != self.height) or
            (now - self.last_keyframe_time >= self.keyframe_interval)
        )
        
        self.width = w
        self.height = h

        if is_keyframe:
            self.last_keyframe_time = now
            self.prev_image = image.copy()
            if raw_u32 is not None:
                self.prev_u32 = raw_u32.copy()
            else:
                self.prev_u32 = None
                # Recalculate tile hashes for fallback
                self.prev_tile_hashes.clear()
                for y in range(0, h, self.tile_size):
                    for x in range(0, w, self.tile_size):
                        box = (x, y, min(x + self.tile_size, w), min(y + self.tile_size, h))
                        tile_crop = image.crop(box)
                        self.prev_tile_hashes[(x, y)] = self._hash_tile(tile_crop)

            compressed = self._compress_image_bytes(image)
            return {
                "kind": "full",
                "width": w,
                "height": h,
                "frame_id": self.frame_index,
                "data": compressed,
                "byte_size": len(compressed)
            }

        # --- High-Performance Vectorized Path (when raw_u32 is provided) ---
        if raw_u32 is not None and self.prev_u32 is not None and self.prev_u32.shape == raw_u32.shape:
            # 1. Zero-copy screen difference (<1.5ms)
            diff = (raw_u32 != self.prev_u32)
            if not diff.any():
                return {
                    "kind": "empty",
                    "width": w,
                    "height": h,
                    "frame_id": self.frame_index,
                    "dirty_count": 0,
                    "byte_size": 0
                }

            # 2. Vectorized block check
            grid_h = (h + self.tile_size - 1) // self.tile_size
            grid_w = (w + self.tile_size - 1) // self.tile_size
            dirty = np.zeros((grid_h, grid_w), dtype=bool)
            for gy in range(grid_h):
                y1 = gy * self.tile_size
                y2 = min(h, y1 + self.tile_size)
                for gx in range(grid_w):
                    x1 = gx * self.tile_size
                    x2 = min(w, x1 + self.tile_size)
                    if diff[y1:y2, x1:x2].any():
                        dirty[gy, gx] = True

            dirty_count = int(dirty.sum())
            total_tiles = grid_h * grid_w

            # If more than 50% changed, send full frame
            if dirty_count > total_tiles * 0.50:
                compressed = self._compress_image_bytes(image)
                self.last_keyframe_time = now
                self.prev_image = image.copy()
                self.prev_u32 = raw_u32.copy()
                return {
                    "kind": "full",
                    "width": w,
                    "height": h,
                    "frame_id": self.frame_index,
                    "data": compressed,
                    "byte_size": len(compressed)
                }

            # For small number of dirty tiles (<= 4), send separate tiles
            dirty_tiles: List[Dict[str, Any]] = []
            if dirty_count <= 4:
                for gy in range(grid_h):
                    for gx in range(grid_w):
                        if dirty[gy, gx]:
                            bx = gx * self.tile_size
                            by = gy * self.tile_size
                            box = (bx, by, min(bx + self.tile_size, w), min(by + self.tile_size, h))
                            crop_img = image.crop(box)
                            tile_bytes = self._compress_image_bytes(crop_img)
                            dirty_tiles.append({
                                "x": bx,
                                "y": by,
                                "w": box[2] - box[0],
                                "h": box[3] - box[1],
                                "data": tile_bytes
                            })
            else:
                # Clustered updates: merge into bounding box to minimize JPEG and base64 overhead
                rows = np.where(dirty.any(axis=1))[0]
                cols = np.where(dirty.any(axis=0))[0]
                min_y, max_y = int(rows[0] * self.tile_size), int(min(h, (rows[-1] + 1) * self.tile_size))
                min_x, max_x = int(cols[0] * self.tile_size), int(min(w, (cols[-1] + 1) * self.tile_size))
                box_w = max_x - min_x
                box_h = max_y - min_y

                # If bounding box covers vast majority of screen, fallback to full frame
                if (box_w * box_h) > (w * h) * 0.65:
                    compressed = self._compress_image_bytes(image)
                    self.last_keyframe_time = now
                    self.prev_image = image.copy()
                    self.prev_u32 = raw_u32.copy()
                    return {
                        "kind": "full",
                        "width": w,
                        "height": h,
                        "frame_id": self.frame_index,
                        "data": compressed,
                        "byte_size": len(compressed)
                    }

                box = (min_x, min_y, max_x, max_y)
                crop_img = image.crop(box)
                box_bytes = self._compress_image_bytes(crop_img)
                dirty_tiles.append({
                    "x": min_x,
                    "y": min_y,
                    "w": box_w,
                    "h": box_h,
                    "data": box_bytes
                })

            self.prev_image = image.copy()
            self.prev_u32 = raw_u32.copy()
            total_bytes = sum(len(t["data"]) for t in dirty_tiles)
            return {
                "kind": "delta",
                "width": w,
                "height": h,
                "frame_id": self.frame_index,
                "dirty_count": dirty_count,
                "tiles": dirty_tiles,
                "byte_size": total_bytes
            }

        # --- Fallback Path (e.g. synthetic test images without raw_u32) ---
        dirty_tiles = []
        new_tile_hashes = {}
        
        for y in range(0, h, self.tile_size):
            for x in range(0, w, self.tile_size):
                box = (x, y, min(x + self.tile_size, w), min(y + self.tile_size, h))
                tile_crop = image.crop(box)
                thash = self._hash_tile(tile_crop)
                new_tile_hashes[(x, y)] = thash
                
                prev_h = self.prev_tile_hashes.get((x, y))
                if prev_h != thash:
                    tile_bytes = self._compress_image_bytes(tile_crop)
                    dirty_tiles.append({
                        "x": x,
                        "y": y,
                        "w": box[2] - box[0],
                        "h": box[3] - box[1],
                        "data": tile_bytes
                    })

        self.prev_image = image.copy()
        self.prev_tile_hashes = new_tile_hashes

        if not dirty_tiles:
            return {
                "kind": "empty",
                "width": w,
                "height": h,
                "frame_id": self.frame_index,
                "dirty_count": 0,
                "byte_size": 0
            }

        total_tiles = ((w + self.tile_size - 1) // self.tile_size) * ((h + self.tile_size - 1) // self.tile_size)
        if len(dirty_tiles) > total_tiles * 0.70:
            compressed = self._compress_image_bytes(image)
            self.last_keyframe_time = now
            return {
                "kind": "full",
                "width": w,
                "height": h,
                "frame_id": self.frame_index,
                "data": compressed,
                "byte_size": len(compressed)
            }

        total_bytes = sum(len(t["data"]) for t in dirty_tiles)
        return {
            "kind": "delta",
            "width": w,
            "height": h,
            "frame_id": self.frame_index,
            "dirty_count": len(dirty_tiles),
            "tiles": dirty_tiles,
            "byte_size": total_bytes
        }
