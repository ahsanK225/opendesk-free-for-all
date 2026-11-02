"""Small, stdlib-only launcher and installer shutdown helper for Windows."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

APP_NAME = re.compile(r'^opendesk(?:_v\d+\.\d+\.\d+_portable)?\.exe$', re.I)


def _kernel():
    dll = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, args, result in [
        ('CreateMutexW', [ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR], wintypes.HANDLE),
        ('CreateEventW', [ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR], wintypes.HANDLE),
        ('OpenEventW', [wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR], wintypes.HANDLE),
        ('SetEvent', [wintypes.HANDLE], wintypes.BOOL),
        ('WaitForSingleObject', [wintypes.HANDLE,wintypes.DWORD], wintypes.DWORD),
        ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ('ProcessIdToSessionId', [wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ('OpenProcess', [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD], wintypes.HANDLE),
        ('QueryFullProcessImageNameW', [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ('CreateToolhelp32Snapshot', [wintypes.DWORD,wintypes.DWORD], wintypes.HANDLE),
    ]:
        fn = getattr(dll,name)
        fn.argtypes, fn.restype = args,result
    return dll


def instance_name(suffix=''):
    user = os.path.normcase(os.path.expanduser('~'))
    digest = hashlib.sha256((user+suffix).encode()).hexdigest()[:24]
    return 'Local\\OpenDesk.'+digest


class SingleInstance:
    def __init__(self, suffix=''):
        self.kernel = _kernel()
        self.name = instance_name(suffix)
        ctypes.set_last_error(0)
        self.mutex = self.kernel.CreateMutexW(None,False,self.name)
        if not self.mutex: raise ctypes.WinError(ctypes.get_last_error())
        self.primary = ctypes.get_last_error() != 183
        self.shutdown = self.kernel.CreateEventW(None,False,False,self.name+'.shutdown')
        self.activate = self.kernel.CreateEventW(None,False,False,self.name+'.activate')
        if not self.shutdown or not self.activate:
            self.close()
            raise OSError('Unable to initialize launcher events')
        if not self.primary: self.kernel.SetEvent(self.activate)

    def poll(self):
        if self.kernel.WaitForSingleObject(self.shutdown,0)==0: return 'shutdown'
        if self.kernel.WaitForSingleObject(self.activate,0)==0: return 'activate'
        return None

    def close(self):
        for attr in ('shutdown','activate','mutex'):
            handle = getattr(self,attr,None)
            if handle: self.kernel.CloseHandle(handle)
            setattr(self,attr,None)


def signal_shutdown(suffix=''):
    kernel = _kernel()
    event = kernel.OpenEventW(0x0002,False,instance_name(suffix)+'.shutdown')
    if not event: return False
    try: return bool(kernel.SetEvent(event))
    finally: kernel.CloseHandle(event)


def process_path(pid):
    kernel = _kernel()
    handle = kernel.OpenProcess(0x1000,False,pid)
    if not handle: return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        return buffer.value if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)) else None
    finally: kernel.CloseHandle(handle)


def matching_processes(install_dir=None):
    class Entry(ctypes.Structure):
        _fields_ = [('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                   ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                   ('parent',wintypes.DWORD),('priority',ctypes.c_long),('flags',wintypes.DWORD),
                   ('exe',wintypes.WCHAR*260)]
    kernel = _kernel()
    for name in ('Process32FirstW','Process32NextW'):
        fn = getattr(kernel,name)
        fn.argtypes,fn.restype = [wintypes.HANDLE,ctypes.POINTER(Entry)],wintypes.BOOL
    excluded = {os.getpid()}
    if getattr(sys,'frozen',False): excluded.add(os.getppid()) # own onefile bootloader
    scope = os.path.normcase(os.path.realpath(install_dir)) if install_dir else None
    snapshot = kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    result = []
    current_session=wintypes.DWORD()
    kernel.ProcessIdToSessionId(os.getpid(),ctypes.byref(current_session))
    try:
        item = Entry(); item.size = ctypes.sizeof(Entry)
        found = kernel.Process32FirstW(snapshot,ctypes.byref(item))
        while found:
            session=wintypes.DWORD()
            same_session=kernel.ProcessIdToSessionId(item.pid,ctypes.byref(session)) and session.value==current_session.value
            if same_session and item.pid not in excluded and APP_NAME.fullmatch(item.exe):
                path = process_path(item.pid)
                if path and (not scope or os.path.normcase(os.path.dirname(os.path.realpath(path)))==scope):
                    result.append((item.pid,path))
                elif not path and not scope:
                    result.append((item.pid,'')) # report inaccessible elevated instances; never kill blindly
            found = kernel.Process32NextW(snapshot,ctypes.byref(item))
    finally: kernel.CloseHandle(snapshot)
    return result


def shutdown_running(force=False, timeout=8, install_dir=None, suffix=''):
    signal_shutdown(suffix)
    deadline = time.monotonic()+max(2,min(20,timeout))
    grace = min(deadline,time.monotonic()+1.5)
    while time.monotonic()<grace:
        if not matching_processes(install_dir): return []
        time.sleep(.1)
    if force:
        for pid,path in matching_processes(install_dir):
            if time.monotonic()>=deadline: break
            # Recheck immediately before terminating to avoid PID reuse targeting another app.
            if process_path(pid) != path: continue
            try:
                subprocess.run(['taskkill.exe','/PID',str(pid),'/T','/F'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                               timeout=max(.2,deadline-time.monotonic()))
            except (OSError,subprocess.TimeoutExpired): pass
    while time.monotonic()<deadline:
        remaining = matching_processes(install_dir)
        if not remaining: return []
        time.sleep(.1)
    return matching_processes(install_dir)


def shutdown_main():
    parser = argparse.ArgumentParser(description='Close OpenDesk for installation or maintenance')
    parser.add_argument('--shutdown',action='store_true')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--timeout',type=float,default=8)
    parser.add_argument('--install-dir')
    parser.add_argument('--instance-suffix',default='')
    parser.add_argument('--result-file')
    args = parser.parse_args()
    if not args.shutdown: parser.error('This maintenance helper requires --shutdown')
    remaining = shutdown_running(args.force,args.timeout,args.install_dir,args.instance_suffix)
    if args.result_file:
        Path(args.result_file).write_text(json.dumps({'closed':not remaining,'remaining_pids':[p[0] for p in remaining]}))
    return 1 if remaining else 0
