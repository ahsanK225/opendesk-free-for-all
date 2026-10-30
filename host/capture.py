"""
Windows Screen Capture Engine for OpenDesk
Uses low-level Win32 GDI DIBSection capture with OpenInputDesktop/SetThreadDesktop
for direct access to the active user's desktop session.
"""

import sys
import ctypes
import time
from typing import Tuple, Optional
import numpy as np
from PIL import Image

class WindowsScreenCapturer:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("WindowsScreenCapturer is only supported on Windows")
            
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        
        # Structure for 32-bit DIB Section
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32),
                ('biWidth', ctypes.c_int32),
                ('biHeight', ctypes.c_int32),
                ('biPlanes', ctypes.c_uint16),
                ('biBitCount', ctypes.c_uint16),
                ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32),
                ('biXPelsPerMeter', ctypes.c_int32),
                ('biYPelsPerMeter', ctypes.c_int32),
                ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32),
            ]
        self.BITMAPINFOHEADER = BITMAPINFOHEADER
        
        self.width = 0
        self.height = 0
        self.hdc_screen = None
        self.hdc_mem = None
        self.hbm = None
        self.ppv_bits = ctypes.c_void_p()
        self.h_desktop = None
        
        self._init_desktop()
        self._allocate_buffers()

    def _init_desktop(self):
        """Attach thread to active user desktop."""
        try:
            # 0x01FF = DESKTOP_ALL_ACCESS
            self.h_desktop = self.user32.OpenInputDesktop(0, False, 0x01FF)
            if self.h_desktop:
                self.user32.SetThreadDesktop(self.h_desktop)
        except Exception:
            pass

    def _allocate_buffers(self):
        """Allocate compatible DC and DIB section."""
        self._release_buffers()
        
        # 0 = SM_CXSCREEN, 1 = SM_CYSCREEN
        self.width = self.user32.GetSystemMetrics(0)
        self.height = self.user32.GetSystemMetrics(1)
        
        self.hdc_screen = self.user32.GetDC(0)
        self.hdc_mem = self.gdi32.CreateCompatibleDC(self.hdc_screen)
        
        bmi = self.BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(self.BITMAPINFOHEADER)
        bmi.biWidth = self.width
        bmi.biHeight = -self.height  # Negative height for top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0
        
        self.ppv_bits = ctypes.c_void_p()
        self.hbm = self.gdi32.CreateDIBSection(
            self.hdc_screen,
            ctypes.byref(bmi),
            0,
            ctypes.byref(self.ppv_bits),
            0,
            0
        )
        self.gdi32.SelectObject(self.hdc_mem, self.hbm)

    def _release_buffers(self):
        """Free Win32 GDI objects."""
        if self.hbm and self.gdi32:
            self.gdi32.DeleteObject(self.hbm)
            self.hbm = None
        if self.hdc_mem and self.gdi32:
            self.gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = None
        if self.hdc_screen and self.user32:
            self.user32.ReleaseDC(0, self.hdc_screen)
            self.hdc_screen = None

    def grab_frame(self) -> Tuple[Image.Image, np.ndarray]:
        """
        Capture current screen contents returning:
        1. PIL Image (referencing low-level DIB buffer without 8MB duplicate copy)
        2. Zero-copy uint32 NumPy 2D array view for ultra-fast diff computation (<0.5ms)
        """
        curr_w = self.user32.GetSystemMetrics(0)
        curr_h = self.user32.GetSystemMetrics(1)
        if curr_w != self.width or curr_h != self.height:
            self._allocate_buffers()

        self._init_desktop()
        
        # 0x00CC0020 = SRCCOPY
        res = self.gdi32.BitBlt(
            self.hdc_mem, 0, 0, self.width, self.height,
            self.hdc_screen, 0, 0, 0x00CC0020
        )
        
        if not res:
            self._allocate_buffers()
            self.gdi32.BitBlt(
                self.hdc_mem, 0, 0, self.width, self.height,
                self.hdc_screen, 0, 0, 0x00CC0020
            )

        buffer_size = self.width * self.height * 4
        raw_bytes = (ctypes.c_char * buffer_size).from_address(self.ppv_bits.value)
        # Direct zero-copy uint32 NumPy view (height, width)
        arr_u32 = np.frombuffer(raw_bytes, dtype=np.uint32).reshape((self.height, self.width))
        # Zero-copy direct RGB PIL image view (reads 32-bit BGRX into RGB without RGBA conversion overhead)
        img = Image.frombuffer('RGB', (self.width, self.height), raw_bytes, 'raw', 'BGRX', 0, 1)
        return img, arr_u32

    def grab(self) -> Image.Image:
        """Capture current screen contents as a PIL Image."""
        img, _ = self.grab_frame()
        return img

    def close(self):
        self._release_buffers()
        if self.h_desktop and self.user32:
            self.user32.CloseDesktop(self.h_desktop)
            self.h_desktop = None

    def __del__(self):
        self.close()
