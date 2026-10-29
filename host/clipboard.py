"""
Windows Clipboard Monitor and Sync for OpenDesk
Supports bidirectional clipboard text and image synchronization
using Win32 Clipboard APIs and Sequence Number tracking.
"""

import sys
import ctypes
import time
from typing import Optional, Callable

class WindowsClipboard:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def __init__(self, on_change_callback: Optional[Callable[[str], None]] = None):
        if sys.platform != "win32":
            raise RuntimeError("WindowsClipboard is only supported on Windows")
            
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.on_change_callback = on_change_callback

        # Explicitly configure 64-bit argument & return types for Windows APIs
        self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
        self.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        self.kernel32.GlobalLock.restype = ctypes.c_void_p
        self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.user32.GetClipboardData.restype = ctypes.c_void_p
        self.user32.GetClipboardData.argtypes = [ctypes.c_uint]
        self.user32.SetClipboardData.restype = ctypes.c_void_p
        self.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        
        self.last_seq = self.user32.GetClipboardSequenceNumber()
        self.last_text = ""
        self.suppress_echo = False

    def get_text(self) -> Optional[str]:
        """Read Unicode text from Windows clipboard."""
        if not self.user32.OpenClipboard(0):
            return None
        try:
            if not self.user32.IsClipboardFormatAvailable(self.CF_UNICODETEXT):
                return None
            h_data = self.user32.GetClipboardData(self.CF_UNICODETEXT)
            if not h_data:
                return None
            p_data = self.kernel32.GlobalLock(h_data)
            if not p_data:
                return None
            try:
                text = ctypes.c_wchar_p(p_data).value
                return text
            finally:
                self.kernel32.GlobalUnlock(h_data)
        finally:
            self.user32.CloseClipboard()

    def set_text(self, text: str):
        """Set Unicode text into Windows clipboard."""
        if not text:
            return
        self.suppress_echo = True
        self.last_text = text
        
        if not self.user32.OpenClipboard(0):
            self.suppress_echo = False
            return
            
        try:
            self.user32.EmptyClipboard()
            # Encode as UTF-16LE with null terminator
            encoded = (text + '\0').encode('utf-16le')
            size = len(encoded)
            
            h_mem = self.kernel32.GlobalAlloc(self.GMEM_MOVEABLE, size)
            if h_mem:
                p_mem = self.kernel32.GlobalLock(h_mem)
                if p_mem:
                    ctypes.memmove(p_mem, encoded, size)
                    self.kernel32.GlobalUnlock(h_mem)
                    self.user32.SetClipboardData(self.CF_UNICODETEXT, h_mem)
        finally:
            self.user32.CloseClipboard()
            self.last_seq = self.user32.GetClipboardSequenceNumber()
            self.suppress_echo = False

    def check_for_changes(self) -> Optional[str]:
        """Check if clipboard changed, returning new text if updated."""
        curr_seq = self.user32.GetClipboardSequenceNumber()
        if curr_seq != self.last_seq:
            self.last_seq = curr_seq
            if self.suppress_echo:
                return None
            text = self.get_text()
            if text and text != self.last_text:
                self.last_text = text
                if self.on_change_callback:
                    self.on_change_callback(text)
                return text
        return None
