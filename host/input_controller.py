"""
Windows Input Injection Controller for OpenDesk
Handles bidirectional mouse movements, button clicks, scrolling,
keyboard events, and system shortcuts using user32.dll Win32 APIs.
"""

import sys
import ctypes
import time
from typing import Dict, Any, Optional

class WindowsInputController:
    # Mouse Event Flags
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x01000
    MOUSEEVENTF_ABSOLUTE = 0x8000

    # Key Event Flags
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    # Common Virtual Key Codes
    VK_MAP = {
        "Backspace": 0x08, "Tab": 0x09, "Enter": 0x0D, "Shift": 0x10, "ShiftLeft": 0x10, "ShiftRight": 0x10,
        "Control": 0x11, "ControlLeft": 0x11, "ControlRight": 0x11,
        "Alt": 0x12, "AltLeft": 0x12, "AltRight": 0x12,
        "Pause": 0x13, "CapsLock": 0x14, "Escape": 0x1B, "Space": 0x20,
        "PageUp": 0x21, "PageDown": 0x22, "End": 0x23, "Home": 0x24,
        "ArrowLeft": 0x25, "ArrowUp": 0x26, "ArrowRight": 0x27, "ArrowDown": 0x28,
        "PrintScreen": 0x2C, "Insert": 0x2D, "Delete": 0x2E,
        "Meta": 0x5B, "MetaLeft": 0x5B, "MetaRight": 0x5C, # Windows Key
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
        "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    }

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("WindowsInputController is only supported on Windows")
            
        self.user32 = ctypes.windll.user32
        self.width = self.user32.GetSystemMetrics(0)
        self.height = self.user32.GetSystemMetrics(1)
        self.enabled = True

    def update_screen_size(self, width: int, height: int):
        self.width = width
        self.height = height

    def move_mouse(self, norm_x: float, norm_y: float):
        """Move cursor to normalized coordinates (0.0 to 1.0)."""
        if not self.enabled:
            return
        target_x = max(0, min(self.width - 1, int(norm_x * self.width)))
        target_y = max(0, min(self.height - 1, int(norm_y * self.height)))
        self.user32.SetCursorPos(target_x, target_y)

    def mouse_down(self, button: int = 0, norm_x: Optional[float] = None, norm_y: Optional[float] = None):
        """Button: 0=Left, 1=Middle, 2=Right."""
        if not self.enabled:
            return
        if norm_x is not None and norm_y is not None:
            self.move_mouse(norm_x, norm_y)
            
        flag = self.MOUSEEVENTF_LEFTDOWN
        if button == 1:
            flag = self.MOUSEEVENTF_MIDDLEDOWN
        elif button == 2:
            flag = self.MOUSEEVENTF_RIGHTDOWN
            
        self.user32.mouse_event(flag, 0, 0, 0, 0)

    def mouse_up(self, button: int = 0, norm_x: Optional[float] = None, norm_y: Optional[float] = None):
        """Button: 0=Left, 1=Middle, 2=Right."""
        if not self.enabled:
            return
        if norm_x is not None and norm_y is not None:
            self.move_mouse(norm_x, norm_y)
            
        flag = self.MOUSEEVENTF_LEFTUP
        if button == 1:
            flag = self.MOUSEEVENTF_MIDDLEUP
        elif button == 2:
            flag = self.MOUSEEVENTF_RIGHTUP
            
        self.user32.mouse_event(flag, 0, 0, 0, 0)

    def mouse_scroll(self, delta_x: float, delta_y: float):
        if not self.enabled:
            return
        if delta_y != 0:
            # Positive delta_y = scroll up, negative = scroll down
            amount = int(-delta_y * 120)
            self.user32.mouse_event(self.MOUSEEVENTF_WHEEL, 0, 0, amount, 0)
        if delta_x != 0:
            amount = int(delta_x * 120)
            self.user32.mouse_event(self.MOUSEEVENTF_HWHEEL, 0, 0, amount, 0)

    def _resolve_vk(self, key_code: str, char: str) -> int:
        """Resolve JavaScript key/code to Windows Virtual Key code."""
        if key_code in self.VK_MAP:
            return self.VK_MAP[key_code]
        if char in self.VK_MAP:
            return self.VK_MAP[char]
            
        # Alphanumeric keys: 'KeyA' -> 'A', 'Digit1' -> '1'
        if key_code.startswith("Key") and len(key_code) == 4:
            return ord(key_code[3].upper())
        if key_code.startswith("Digit") and len(key_code) == 6:
            return ord(key_code[5])
            
        # Single characters
        if len(char) == 1:
            c = ord(char.upper())
            if (65 <= c <= 90) or (48 <= c <= 57):
                return c
            # VkKeyScan for symbols
            vk = self.user32.VkKeyScanW(ord(char))
            if vk != -1:
                return vk & 0xFF
                
        return 0

    def key_down(self, key_code: str, char: str = ""):
        if not self.enabled:
            return
        vk = self._resolve_vk(key_code, char)
        if vk:
            flags = 0
            if vk in (0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22):
                flags |= self.KEYEVENTF_EXTENDEDKEY
            self.user32.keybd_event(vk, 0, flags, 0)

    def key_up(self, key_code: str, char: str = ""):
        if not self.enabled:
            return
        vk = self._resolve_vk(key_code, char)
        if vk:
            flags = self.KEYEVENTF_KEYUP
            if vk in (0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22):
                flags |= self.KEYEVENTF_EXTENDEDKEY
            self.user32.keybd_event(vk, 0, flags, 0)

    def execute_shortcut(self, name: str):
        """Execute special system shortcut combinations."""
        if not self.enabled:
            return
        if name == "ctrl_alt_del":
            # Direct Ctrl+Alt+Del is blocked by Win32 security without service credentials,
            # but we can launch Task Manager directly or simulate Ctrl+Shift+Esc
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_ESCAPE = 0x1B
            self.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            self.user32.keybd_event(VK_SHIFT, 0, 0, 0)
            self.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            time.sleep(0.05)
            self.user32.keybd_event(VK_ESCAPE, 0, self.KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_SHIFT, 0, self.KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_CONTROL, 0, self.KEYEVENTF_KEYUP, 0)
        elif name == "win":
            VK_LWIN = 0x5B
            self.user32.keybd_event(VK_LWIN, 0, 0, 0)
            time.sleep(0.05)
            self.user32.keybd_event(VK_LWIN, 0, self.KEYEVENTF_KEYUP, 0)
        elif name == "alt_tab":
            VK_MENU = 0x12
            VK_TAB = 0x09
            self.user32.keybd_event(VK_MENU, 0, 0, 0)
            self.user32.keybd_event(VK_TAB, 0, 0, 0)
            time.sleep(0.05)
            self.user32.keybd_event(VK_TAB, 0, self.KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_MENU, 0, self.KEYEVENTF_KEYUP, 0)
