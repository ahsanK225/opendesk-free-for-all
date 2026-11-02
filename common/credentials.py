"""Windows user-bound credential protection. Never store unattended secrets in plaintext."""
import base64
import ctypes
import sys
from ctypes import wintypes


def _crypt(raw, decrypt=False):
    if sys.platform != 'win32':
        raise RuntimeError('Unattended credential storage requires Windows DPAPI')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = getattr(ctypes.windll.crypt32, 'CryptUnprotectData' if decrypt else 'CryptProtectData')
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('Windows could not protect/unprotect the unattended credential')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree.restype = ctypes.c_void_p
        ctypes.windll.kernel32.LocalFree(output.data)


def protect(password):
    return 'dpapi:' + base64.b64encode(_crypt(password.encode('utf-8'))).decode('ascii')


def unprotect(value):
    if not value:
        return ''
    if not value.startswith('dpapi:'):
        raise ValueError('Unprotected credential')
    return _crypt(base64.b64decode(value[6:]), decrypt=True).decode('utf-8')
