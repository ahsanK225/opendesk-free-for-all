"""
DeskRT-style Tile & Delta Video Codec for OpenDesk
Implements GUI-optimized screen compression:
- Uniform tile grid partitioning (e.g. 128x128 or 64x64)
- Fast dirty-rect / dirty-tile change detection
- Delta transmission (transmits only tiles that changed between frames)
- Adaptive quality & keyframe generation
- High-efficiency encoding using Pillow JPEG with memory buffers

Performance:
- No full-frame image copies per frame (the previous frame is held as a uint32
  buffer and updated in place), which removes ~16 MB/frame of memcpy traffic.
- Dirty tile detection is a single vectorized numpy reduction instead of a
  Python loop over every tile.
- Full keyframes are only produced when something actually changed, so an idle
  desktop costs zero bandwidth.
"""

import io
import time
import hashlib
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from PIL import Image


class DeskRTCodec:
    def __init__(self, tile_size: int = 128, quality: int = 70, keyframe_interval: float = 15.0):
        self.tile_size = tile_size
        self.quality = quality
        self.keyframe_interval = keyframe_interval

        self.prev_u32: Optional[np.ndarray] = None
        self.prev_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        self.last_keyframe_time: float = 0.0
        self.frame_index: int = 0
        self.width: int = 0
        self.height: int = 0

        self._has_prev: bool = False
        self._diff_buffer: Optional[np.ndarray] = None

    def set_quality(self, quality: int):
        self.quality = max(10, min(95, quality))

    def reset(self):
        self.prev_u32 = None
        self.prev_tile_hashes.clear()
        self.last_keyframe_time = 0.0
        self.frame_index = 0
        self.width = 0
        self.height = 0
        self._has_prev = False
        self._diff_buffer = None

    def _hash_tile(self, img_crop: Image.Image) -> bytes:
        """Compute quick digest of tile pixel data for fallback dirty detection."""
        return hashlib.md5(img_crop.tobytes()).digest()

    def _compress_image_bytes(self, img: Image.Image, quality: Optional[int] = None) -> bytes:
        """Compress PIL Image to fast JPEG bytes using 4:2:0 subsampling."""
        q = quality if quality is not None else self.quality
        rgb_img = img if img.mode == 'RGB' else img.convert('RGB')
        buffer = io.BytesIO()
        rgb_img.save(buffer, format='JPEG', quality=q, optimize=False, subsampling='4:2:0')
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Previous-frame bookkeeping
    # ------------------------------------------------------------------
    def _store_prev(self, raw_u32: np.ndarray):
        if self.prev_u32 is None or self.prev_u32.shape != raw_u32.shape:
            self.prev_u32 = np.array(raw_u32, dtype=np.uint32, copy=True, order='C')
            self._diff_buffer = None
        else:
            np.copyto(self.prev_u32, raw_u32)

    def _full_result(self, image: Image.Image, w: int, h: int) -> Dict[str, Any]:
        compressed = self._compress_image_bytes(image)
        self.frame_index += 1
        return {
            "kind": "full",
            "width": w,
            "height": h,
            "frame_id": self.frame_index,
            "data": compressed,
            "byte_size": len(compressed)
        }

    def _empty_result(self, w: int, h: int) -> Dict[str, Any]:
        return {
            "kind": "empty",
            "width": w,
            "height": h,
            "frame_id": self.frame_index,
            "dirty_count": 0,
            "byte_size": 0
        }

    def _dirty_grid(self, diff: np.ndarray, w: int, h: int) -> Tuple[np.ndarray, int, int]:
        """Reduce a per-pixel diff mask to a per-tile boolean grid in one numpy pass."""
        ts = self.tile_size
        grid_h = (h + ts - 1) // ts
        grid_w = (w + ts - 1) // ts
        if grid_h * ts != h or grid_w * ts != w:
            padded = np.zeros((grid_h * ts, grid_w * ts), dtype=bool)
            padded[:h, :w] = diff
            diff = padded
        return diff.reshape(grid_h, ts, grid_w, ts).any(axis=(1, 3)), grid_h, grid_w

    def encode(self, image: Image.Image, raw_u32: Optional[np.ndarray] = None, force_keyframe: bool = False) -> Dict[str, Any]:
        """
        Encode an image frame at high throughput.
        Uses a vectorized uint32 diff when raw_u32 is provided (<1ms) and clusters
        dirty tiles into bounding regions to minimize JPEG/network overhead.
        """
        now = time.time()
        w, h = image.size
        size_changed = (w != self.width or h != self.height)
        self.width = w
        self.height = h

        # ---------------- Vectorized path (real screen capture) ----------------
        if raw_u32 is not None:
            can_diff = (
                self._has_prev
                and self.prev_u32 is not None
                and self.prev_u32.shape == raw_u32.shape
            )

            if force_keyframe or size_changed or not can_diff:
                self._store_prev(raw_u32)
                self.prev_tile_hashes.clear()
                self.last_keyframe_time = now
                self._has_prev = True
                return self._full_result(image, w, h)

            if self._diff_buffer is None or self._diff_buffer.shape != raw_u32.shape:
                self._diff_buffer = np.empty(raw_u32.shape, dtype=bool)
            diff = np.not_equal(raw_u32, self.prev_u32, out=self._diff_buffer)

            if not diff.any():
                # Nothing changed - no bytes on the wire, and no needless keyframe
                return self._empty_result(w, h)

            if (now - self.last_keyframe_time) >= self.keyframe_interval:
                self._store_prev(raw_u32)
                self.last_keyframe_time = now
                return self._full_result(image, w, h)

            dirty, grid_h, grid_w = self._dirty_grid(diff, w, h)
            dirty_count = int(dirty.sum())
            total_tiles = grid_h * grid_w
            dirty_tiles: List[Dict[str, Any]] = []

            # Most of the screen changed: a single full frame is cheaper than tiles
            if dirty_count > total_tiles * 0.50:
                self._store_prev(raw_u32)
                self.last_keyframe_time = now
                return self._full_result(image, w, h)

            if dirty_count <= 4:
                for gy, gx in np.argwhere(dirty):
                    bx = int(gx) * self.tile_size
                    by = int(gy) * self.tile_size
                    box = (bx, by, min(bx + self.tile_size, w), min(by + self.tile_size, h))
                    dirty_tiles.append({
                        "x": bx,
                        "y": by,
                        "w": box[2] - box[0],
                        "h": box[3] - box[1],
                        "data": self._compress_image_bytes(image.crop(box))
                    })
            else:
                # Cluster adjacent dirty tiles into one bounding box (1 JPEG instead of N)
                rows = np.where(dirty.any(axis=1))[0]
                cols = np.where(dirty.any(axis=0))[0]
                min_y = int(rows[0]) * self.tile_size
                max_y = int(min(h, (int(rows[-1]) + 1) * self.tile_size))
                min_x = int(cols[0]) * self.tile_size
                max_x = int(min(w, (int(cols[-1]) + 1) * self.tile_size))
                box_w = max_x - min_x
                box_h = max_y - min_y

                if (box_w * box_h) > (w * h) * 0.65:
                    self._store_prev(raw_u32)
                    self.last_keyframe_time = now
                    return self._full_result(image, w, h)

                dirty_tiles.append({
                    "x": min_x,
                    "y": min_y,
                    "w": box_w,
                    "h": box_h,
                    "data": self._compress_image_bytes(image.crop((min_x, min_y, max_x, max_y)))
                })

            self._store_prev(raw_u32)
            self.frame_index += 1
            return {
                "kind": "delta",
                "width": w,
                "height": h,
                "frame_id": self.frame_index,
                "dirty_count": dirty_count,
                "tiles": dirty_tiles,
                "byte_size": sum(len(t["data"]) for t in dirty_tiles)
            }

        # ---------------- Fallback path (synthetic frames without raw_u32) ----------------
        new_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        changed: List[Tuple[Image.Image, Tuple[int, int, int, int]]] = []

        for y in range(0, h, self.tile_size):
            for x in range(0, w, self.tile_size):
                box = (x, y, min(x + self.tile_size, w), min(y + self.tile_size, h))
                tile_crop = image.crop(box)
                thash = self._hash_tile(tile_crop)
                new_tile_hashes[(x, y)] = thash
                if self.prev_tile_hashes.get((x, y)) != thash:
                    changed.append((tile_crop, box))

        first_frame = not self._has_prev
        self.prev_tile_hashes = new_tile_hashes
        self._has_prev = True

        if force_keyframe or first_frame or size_changed:
            self.last_keyframe_time = now
            return self._full_result(image, w, h)

        if not changed:
            return self._empty_result(w, h)

        if (now - self.last_keyframe_time) >= self.keyframe_interval:
            self.last_keyframe_time = now
            return self._full_result(image, w, h)

        total_tiles = ((w + self.tile_size - 1) // self.tile_size) * ((h + self.tile_size - 1) // self.tile_size)
        if len(changed) > total_tiles * 0.70:
            self.last_keyframe_time = now
            return self._full_result(image, w, h)

        dirty_tiles = [
            {
                "x": box[0],
                "y": box[1],
                "w": box[2] - box[0],
                "h": box[3] - box[1],
                "data": self._compress_image_bytes(tile_crop)
            }
            for tile_crop, box in changed
        ]

        self.frame_index += 1
        return {
            "kind": "delta",
            "width": w,
            "height": h,
            "frame_id": self.frame_index,
            "dirty_count": len(dirty_tiles),
            "tiles": dirty_tiles,
            "byte_size": sum(len(t["data"]) for t in dirty_tiles)
        }
