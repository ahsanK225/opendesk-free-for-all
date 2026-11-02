"""
Windows Screen Capture Engine for OpenDesk
Uses low-level Win32 GDI DIBSection capture with OpenInputDesktop/SetThreadDesktop
for direct access to the active user's desktop session.

Performance notes:
- The input desktop is attached once per capture thread (not on every frame), which
  removes a per-frame Win32 call and stops the handle leak that used to accumulate
  one desktop handle per captured frame.
- Optional output scaling is done by StretchBlt inside GDI, so a scaled capture is a
  single fast blit instead of a full-resolution copy followed by a CPU resize.
"""

import sys
import ctypes
import threading
import time
from ctypes import wintypes
from typing import Tuple
import numpy as np
from PIL import Image

SRCCOPY = 0x00CC0020
DESKTOP_ALL_ACCESS = 0x01FF
COLORONCOLOR = 3
DI_NORMAL = 0x0003
CURSOR_SHOWING = 0x0001
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_CXCURSOR = 13
SM_CYCURSOR = 14


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


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('hCursor', wintypes.HANDLE),
        ('ptScreenPos', wintypes.POINT),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ('fIcon', wintypes.BOOL),
        ('xHotspot', wintypes.DWORD),
        ('yHotspot', wintypes.DWORD),
        ('hbmMask', wintypes.HANDLE),
        ('hbmColor', wintypes.HANDLE),
    ]


class WindowsScreenCapturer:
    def __init__(self, scale: float = 1.0):
        if sys.platform != "win32":
            raise RuntimeError("WindowsScreenCapturer is only supported on Windows")

        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        self._configure_prototypes()

        self.width = 0
        self.height = 0
        self.out_width = 0
        self.out_height = 0
        self.hdc_screen = None
        self.hdc_mem = None
        self.hbm = None
        self.ppv_bits = ctypes.c_void_p()
        self.h_desktop = None

        self._scale = max(0.25, min(1.0, float(scale)))
        self._thread_id = None
        self._desktop_checked_at = 0.0
        self._screen_w = 0
        self._screen_h = 0

        self._swap_buffers()

    # ------------------------------------------------------------------
    # Win32 prototypes (64-bit safe - default c_int return truncates handles)
    # ------------------------------------------------------------------
    def _configure_prototypes(self):
        u, g = self.user32, self.gdi32

        u.GetSystemMetrics.argtypes = [ctypes.c_int]
        u.GetSystemMetrics.restype = ctypes.c_int
        u.GetDC.argtypes = [wintypes.HWND]
        u.GetDC.restype = wintypes.HDC
        u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        u.ReleaseDC.restype = ctypes.c_int
        u.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        u.OpenInputDesktop.restype = wintypes.HANDLE
        u.SetThreadDesktop.argtypes = [wintypes.HANDLE]
        u.SetThreadDesktop.restype = wintypes.BOOL
        u.CloseDesktop.argtypes = [wintypes.HANDLE]
        u.CloseDesktop.restype = wintypes.BOOL
        u.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
        u.GetCursorInfo.restype = wintypes.BOOL
        u.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
        u.GetIconInfo.restype = wintypes.BOOL
        u.DrawIconEx.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE,
            ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT
        ]
        u.DrawIconEx.restype = wintypes.BOOL

        g.CreateCompatibleDC.argtypes = [wintypes.HDC]
        g.CreateCompatibleDC.restype = wintypes.HDC
        g.DeleteDC.argtypes = [wintypes.HDC]
        g.DeleteDC.restype = wintypes.BOOL
        g.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD
        ]
        g.CreateDIBSection.restype = wintypes.HBITMAP
        g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        g.SelectObject.restype = wintypes.HGDIOBJ
        g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        g.DeleteObject.restype = wintypes.BOOL
        g.BitBlt.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD
        ]
        g.BitBlt.restype = wintypes.BOOL
        g.StretchBlt.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.DWORD
        ]
        g.StretchBlt.restype = wintypes.BOOL
        g.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
        g.SetStretchBltMode.restype = ctypes.c_int

    # ------------------------------------------------------------------
    # Desktop attachment
    # ------------------------------------------------------------------
    def _init_desktop(self, force: bool = False):
        """Attach the calling thread to the active input desktop.

        SetThreadDesktop is thread-affine (and fails for threads owning windows), so
        this only runs when the capture thread changes or after a recovery request.
        """
        now = time.monotonic()
        same_thread = self._thread_id == threading.get_ident()
        if not force and same_thread and (now - self._desktop_checked_at) < 2.0:
            return
        self._thread_id = threading.get_ident()
        self._desktop_checked_at = now

        handle = self.user32.OpenInputDesktop(0, False, DESKTOP_ALL_ACCESS)
        if handle:
            if self.h_desktop and self.h_desktop != handle:
                self.user32.CloseDesktop(self.h_desktop)
            self.h_desktop = handle
            self.user32.SetThreadDesktop(handle)

    # ------------------------------------------------------------------
    # Buffers
    # ------------------------------------------------------------------
    def _swap_buffers(self):
        self._release_buffers()

        self._screen_w = self.user32.GetSystemMetrics(SM_CXSCREEN)
        self._screen_h = self.user32.GetSystemMetrics(SM_CYSCREEN)
        self.width = self._screen_w
        self.height = self._screen_h
        self.out_width = max(1, int(round(self._screen_w * self._scale)))
        self.out_height = max(1, int(round(self._screen_h * self._scale)))

        self.hdc_screen = self.user32.GetDC(None)
        self.hdc_mem = self.gdi32.CreateCompatibleDC(self.hdc_screen)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = self.out_width
        bmi.biHeight = -self.out_height  # Negative height for top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        self.ppv_bits = ctypes.c_void_p()
        self.hbm = self.gdi32.CreateDIBSection(
            self.hdc_screen,
            ctypes.byref(bmi),
            0,
            ctypes.byref(self.ppv_bits),
            None,
            0
        )
        self.gdi32.SelectObject(self.hdc_mem, self.hbm)
        self.gdi32.SetStretchBltMode(self.hdc_mem, COLORONCOLOR)

    def _release_buffers(self):
        if self.hbm:
            self.gdi32.DeleteObject(self.hbm)
            self.hbm = None
        if self.hdc_mem:
            self.gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = None
        if self.hdc_screen:
            self.user32.ReleaseDC(None, self.hdc_screen)
            self.hdc_screen = None
        self.ppv_bits = ctypes.c_void_p()

    @property
    def scale(self) -> float:
        return self._scale

    def set_scale(self, scale: float):
        """Change capture output scale (0.25 - 1.0). Triggers a buffer reallocation."""
        scale = max(0.25, min(1.0, float(scale)))
        if abs(scale - self._scale) < 0.005:
            return
        self._scale = scale
        self._swap_buffers()

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def _blit(self) -> bool:
        if self._scale >= 0.999:
            return bool(self.gdi32.BitBlt(
                self.hdc_mem, 0, 0, self.out_width, self.out_height,
                self.hdc_screen, 0, 0, SRCCOPY
            ))
        return bool(self.gdi32.StretchBlt(
            self.hdc_mem, 0, 0, self.out_width, self.out_height,
            self.hdc_screen, 0, 0, self._screen_w, self._screen_h, SRCCOPY
        ))

    def _draw_cursor(self):
        try:
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if not self.user32.GetCursorInfo(ctypes.byref(ci)):
                return
            if not (ci.flags & CURSOR_SHOWING) or not ci.hCursor:
                return

            x = ci.ptScreenPos.x
            y = ci.ptScreenPos.y
            if not (0 <= x < self._screen_w and 0 <= y < self._screen_h):
                return

            hotspot_x = hotspot_y = 0
            icon_info = ICONINFO()
            if self.user32.GetIconInfo(ci.hCursor, ctypes.byref(icon_info)):
                hotspot_x = int(icon_info.xHotspot)
                hotspot_y = int(icon_info.yHotspot)
                if icon_info.hbmMask:
                    self.gdi32.DeleteObject(icon_info.hbmMask)
                if icon_info.hbmColor:
                    self.gdi32.DeleteObject(icon_info.hbmColor)

            scale = self._scale
            cur_x = int(x * scale) - int(hotspot_x * scale)
            cur_y = int(y * scale) - int(hotspot_y * scale)
            cur_w = int(self.user32.GetSystemMetrics(SM_CXCURSOR) * scale)
            cur_h = int(self.user32.GetSystemMetrics(SM_CYCURSOR) * scale)

            self.user32.DrawIconEx(
                self.hdc_mem, cur_x, cur_y, ci.hCursor,
                cur_w, cur_h, 0, None, DI_NORMAL
            )
        except Exception:
            pass

    def grab_frame(self) -> Tuple[Image.Image, np.ndarray]:
        """
        Capture current screen contents returning:
        1. PIL Image referencing the DIB buffer (no extra copy)
        2. uint32 NumPy 2D view for fast diff computation
        Output dimensions honor the configured scale factor.
        """
        curr_w = self.user32.GetSystemMetrics(SM_CXSCREEN)
        curr_h = self.user32.GetSystemMetrics(SM_CYSCREEN)
        if curr_w != self._screen_w or curr_h != self._screen_h:
            self._swap_buffers()

        self._init_desktop()

        if not self._blit():
            # Desktop changed (lock screen, UAC, session switch) - reattach and retry once
            self._init_desktop(force=True)
            self._swap_buffers()
            self._blit()

        self._draw_cursor()

        buffer_size = self.out_width * self.out_height * 4
        raw_bytes = (ctypes.c_char * buffer_size).from_address(self.ppv_bits.value)
        arr_u32 = np.frombuffer(raw_bytes, dtype=np.uint32).reshape((self.out_height, self.out_width))
        img = Image.frombuffer(
            'RGB', (self.out_width, self.out_height), raw_bytes, 'raw', 'BGRX', 0, 1
        )
        return img, arr_u32

    def grab(self) -> Image.Image:
        """Capture current screen contents as a PIL Image."""
        img, _ = self.grab_frame()
        return img

    def close(self):
        self._release_buffers()
        if self.h_desktop:
            try:
                self.user32.CloseDesktop(self.h_desktop)
            except Exception:
                pass
            self.h_desktop = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
