"""Initialize native coordinate space before Tk or capture creates windows."""
import sys
import ctypes


def enable_dpi_awareness():
    if sys.platform == 'win32':
        try:
            function = ctypes.windll.user32.SetProcessDpiAwarenessContext
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_bool
            function(ctypes.c_void_p(-4))  # per-monitor v2
        except (AttributeError,OSError):
            ctypes.windll.user32.SetProcessDPIAware()
