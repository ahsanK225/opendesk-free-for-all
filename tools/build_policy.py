"""Windows 10+ packages must use the OS API sets and Universal CRT.

Developer PATH entries can otherwise make PyInstaller collect a newer Windows
runtime from an unrelated SDK. VCRUNTIME redistributables remain bundled.
"""
import os
import sys
from pathlib import PureWindowsPath


def application_binaries(entries):
    result = []
    for entry in entries:
        name = PureWindowsPath(entry[0]).name.lower()
        if name == 'ucrtbase.dll' or name.startswith(('api-ms-win-', 'ext-ms-win-')):
            continue
        result.append(entry)
    return result


def clean_build_path():
    windows = os.environ.get('SystemRoot', r'C:\Windows')
    return os.pathsep.join([os.path.dirname(sys.executable),
                           os.path.join(os.path.dirname(sys.executable), 'Scripts'),
                           os.path.join(windows, 'System32'), windows])
