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
from PIL import Image

class DeskRTCodec:
    def __init__(self, tile_size: int = 128, quality: int = 70, keyframe_interval: float = 5.0):
        self.tile_size = tile_size
        self.quality = quality
        self.keyframe_interval = keyframe_interval
        
        self.prev_image: Optional[Image.Image] = None
        self.prev_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        self.last_keyframe_time: float = 0.0
        self.frame_index: int = 0
        self.width: int = 0
        self.height: int = 0

    def set_quality(self, quality: int):
        self.quality = max(10, min(95, quality))

    def reset(self):
        self.prev_image = None
        self.prev_tile_hashes.clear()
        self.last_keyframe_time = 0.0
        self.frame_index = 0

    def _hash_tile(self, img_crop: Image.Image) -> bytes:
        """Compute quick digest of tile pixel data for dirty detection."""
        # Using md5 or sha256 on raw bytes is fast in C-native hashlib
        return hashlib.md5(img_crop.tobytes()).digest()

    def _compress_image_bytes(self, img: Image.Image, quality: Optional[int] = None) -> bytes:
        """Compress PIL Image to JPEG bytes."""
        q = quality if quality is not None else self.quality
        # Convert RGBA to RGB for JPEG
        if img.mode != 'RGB':
            rgb_img = img.convert('RGB')
        else:
            rgb_img = img
            
        buffer = io.BytesIO()
        rgb_img.save(buffer, format='JPEG', quality=q, optimize=False)
        return buffer.getvalue()

    def encode(self, image: Image.Image, force_keyframe: bool = False) -> Dict[str, Any]:
        """
        Encode an image frame.
        Returns a dictionary with full frame or delta tile updates.
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
            
            # Recalculate all tile hashes
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

        # Otherwise, calculate dirty tiles (DeskRT delta)
        dirty_tiles: List[Dict[str, Any]] = []
        new_tile_hashes: Dict[Tuple[int, int], bytes] = {}
        
        for y in range(0, h, self.tile_size):
            for x in range(0, w, self.tile_size):
                box = (x, y, min(x + self.tile_size, w), min(y + self.tile_size, h))
                tile_crop = image.crop(box)
                thash = self._hash_tile(tile_crop)
                new_tile_hashes[(x, y)] = thash
                
                prev_h = self.prev_tile_hashes.get((x, y))
                if prev_h != thash:
                    # Dirty tile!
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

        # If more than 70% of tiles changed, fallback to full frame for better efficiency
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
