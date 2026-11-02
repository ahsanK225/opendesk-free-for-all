"""Verified Cloudflare Quick Tunnel with bounded restart and shutdown."""
import atexit
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Optional, Callable

BINARY_SHA256 = 'f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2'


def _verified(path):
    try:
        with open(path,'rb') as stream:
            return hashlib.file_digest(stream,'sha256').hexdigest() == BINARY_SHA256
    except (OSError,TypeError): return False


class CloudflareTunnel:
    def __init__(self, local_port: int, on_url_ready: Optional[Callable[[Optional[str]],None]] = None):
        self.local_port, self.on_url_ready = local_port, on_url_ready
        self.public_url = self.process = self.thread = None
        self.running = False
        self._stop = threading.Event()
        atexit.register(self.stop)

    def _find_binary(self):
        permanent_dir = os.path.expanduser('~/.opendesk/bin')
        permanent = os.path.join(permanent_dir,'cloudflared.exe')
        if hasattr(sys,'_MEIPASS'):
            bundled = os.path.join(sys._MEIPASS,'bin','cloudflared.exe')
            if not _verified(bundled): return None
            if _verified(permanent): return permanent
            try:
                os.makedirs(permanent_dir,exist_ok=True)
                temporary = permanent+f'.{os.getpid()}.tmp'
                shutil.copy2(bundled,temporary)
                os.replace(temporary,permanent)
                return permanent
            except OSError:
                return bundled
        candidates = [permanent,os.path.join(os.path.dirname(os.path.dirname(__file__)),'bin','cloudflared.exe'),shutil.which('cloudflared')]
        return next((candidate for candidate in candidates if candidate and _verified(candidate)),None)

    def start(self):
        if self.running: return
        binary = self._find_binary()
        if not binary:
            print('[Tunnel] Verified cloudflared binary missing. Run python -m tools.fetch_cloudflared.')
            return
        self.running=True
        self._stop.clear()
        def supervise():
            retry=1
            while self.running:
                process=None
                try:
                    process=subprocess.Popen([binary,'tunnel','--url',f'http://127.0.0.1:{self.local_port}'],
                        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,encoding='utf-8',errors='replace',bufsize=1,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.process=process
                    for line in process.stdout:
                        if not self.running: break
                        match=re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',line)
                        if match and not self.public_url:
                            self.public_url=match.group(0)
                            retry=1
                            if self.on_url_ready: self.on_url_ready(self.public_url)
                    process.wait()
                except OSError as exc:
                    print(f'[Tunnel] {exc}')
                finally:
                    self.public_url=None
                    if self.on_url_ready and self.running: self.on_url_ready(None)
                    if process and process.stdout: process.stdout.close()
                    if self.process is process: self.process=None
                if self._stop.wait(retry): break
                retry=min(30,retry*2)
        self.thread=threading.Thread(target=supervise,name='tunnel',daemon=True)
        self.thread.start()

    def stop(self):
        self.running=False
        self._stop.set()
        process=self.process
        if process:
            try:
                # Kill before closing a pipe another thread is reading.
                process.terminate()
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            except OSError:
                pass
        self.public_url=None
