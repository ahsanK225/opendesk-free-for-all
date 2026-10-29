"""
Automatic Cloudflare Quick Tunnel Manager for OpenDesk
Provides zero-configuration, instant worldwide public internet access
without opening ports, signups, or manual router configuration.
"""

import os
import sys
import re
import shutil
import atexit
import subprocess
import threading
from typing import Optional, Callable

class CloudflareTunnel:
    def __init__(self, local_port: int, on_url_ready: Optional[Callable[[str], None]] = None):
        self.local_port = local_port
        self.on_url_ready = on_url_ready
        self.public_url: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        atexit.register(self.stop)

    def _find_binary(self) -> Optional[str]:
        # 1. External permanent directory outside PyInstaller _MEIPASS
        # Running child executables from inside _MEIPASS prevents Windows from deleting temp files on exit.
        permanent_dir = os.path.expanduser("~/.opendesk/bin")
        permanent_bin = os.path.join(permanent_dir, "cloudflared.exe")

        if hasattr(sys, "_MEIPASS"):
            bundled = os.path.join(sys._MEIPASS, "bin", "cloudflared.exe")
            if os.path.isfile(bundled):
                try:
                    os.makedirs(permanent_dir, exist_ok=True)
                    # Copy out of _MEIPASS if not exists or size differs
                    if not os.path.isfile(permanent_bin) or os.path.getsize(permanent_bin) != os.path.getsize(bundled):
                        shutil.copy2(bundled, permanent_bin)
                    return permanent_bin
                except Exception as e:
                    print(f"[Tunnel] Note copying binary to permanent cache: {e}")
                    return bundled

        if os.path.isfile(permanent_bin):
            return permanent_bin

        # 2. Local bin directory
        cand = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "cloudflared.exe"))
        if os.path.isfile(cand):
            return cand

        # 3. C:\tools\cloudflared.exe
        cand = r"C:\tools\cloudflared.exe"
        if os.path.isfile(cand):
            return cand

        # 4. In PATH
        return shutil.which("cloudflared")

    def start(self):
        binary = self._find_binary()
        if not binary:
            print("[Tunnel] cloudflared binary not found. Skipping auto-tunnel.")
            return

        self.running = True

        def run_proc():
            cmd = [binary, "tunnel", "--url", f"http://127.0.0.1:{self.local_port}"]
            # Hide console window on Windows
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    startupinfo=startupinfo
                )

                pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
                for line in iter(self.process.stdout.readline, ''):
                    if not self.running:
                        break
                    match = pattern.search(line)
                    if match and not self.public_url:
                        self.public_url = match.group(0)
                        print(f"[Tunnel] Public Internet URL: {self.public_url}")
                        if self.on_url_ready:
                            self.on_url_ready(self.public_url)

                self.process.wait()
            except Exception as e:
                print(f"[Tunnel] Exception: {e}")

        self.thread = threading.Thread(target=run_proc, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.process:
            try:
                pid = self.process.pid
                # On Windows, taskkill /F /T terminates process and all child processes synchronously
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                else:
                    self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
                except Exception:
                    pass
            self.process = None
