"""
OpenDesk Automatic Update Engine
Provides in-app update checks, background download with progress monitoring,
and automatic Windows binary self-replacement and relaunch.
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import subprocess
import tempfile
from typing import Optional, Dict, Any, Callable, Tuple

APP_VERSION = "1.1.3"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/version.json"


def parse_version(v_str: str) -> Tuple[int, ...]:
    """Parse a version string (e.g., '1.2.0', 'v1.2.1', '1.3') into a numeric tuple."""
    clean = re.sub(r'^[^\d]*', '', v_str.strip())
    parts = []
    for p in clean.split('.'):
        digits = re.match(r'\d+', p)
        if digits:
            parts.append(int(digits.group(0)))
        else:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(remote_version: str, local_version: str) -> bool:
    """Return True if remote_version is strictly newer than local_version."""
    try:
        return parse_version(remote_version) > parse_version(local_version)
    except Exception:
        return False


def check_for_updates(current_version: str = APP_VERSION,
                       manifest_url: str = UPDATE_MANIFEST_URL,
                       timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    """
    Query the remote manifest and determine if a newer version is available.
    Returns a dict with update details, or None if network check fails.
    """
    req = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": f"OpenDesk/{current_version} (Windows NT 10.0; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                remote_ver = data.get("version", "")
                available = is_newer_version(remote_ver, current_version)
                
                changelog_raw = data.get("changelog", [])
                if isinstance(changelog_raw, list):
                    changelog_text = "\n".join(f"• {item}" for item in changelog_raw)
                else:
                    changelog_text = str(changelog_raw)

                return {
                    "available": available,
                    "version": remote_ver,
                    "current_version": current_version,
                    "release_date": data.get("release_date", "Recent"),
                    "download_url": data.get("download_url", ""),
                    "installer_url": data.get("installer_url", ""),
                    "changelog": changelog_text
                }
    except Exception as e:
        print(f"[Updater] Update check failed or offline: {e}")
        return None
    return None


def download_update_file(url: str,
                         dest_path: str,
                         progress_callback: Optional[Callable[[int, int], None]] = None,
                         cancel_flag: Optional[Callable[[], bool]] = None) -> bool:
    """
    Download update executable in chunks with progress reporting.
    progress_callback(bytes_downloaded, total_bytes)
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenDesk-AutoUpdater"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 64 * 1024  # 64 KB

            with open(dest_path, "wb") as f:
                while True:
                    if cancel_flag and cancel_flag():
                        return False
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)
        return True
    except Exception as e:
        print(f"[Updater] Download error: {e}")
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        return False


def apply_update_and_restart(new_file_path: str, is_installer: bool = False):
    """
    Replace the currently running executable or run the installer,
    then terminate the current instance to complete the update.
    """
    if not os.path.isfile(new_file_path):
        raise FileNotFoundError(f"Update file not found: {new_file_path}")

    # Case 1: An installer was downloaded (.exe setup)
    if is_installer or "setup" in os.path.basename(new_file_path).lower():
        subprocess.Popen([new_file_path, "/SILENT"], shell=True)
        time.sleep(0.5)
        sys.exit(0)

    # Case 2: Portable standalone executable replacement
    target_exe = sys.executable
    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen:
        # Running from Python source; replace OpenDesk.exe in repo directory if present
        repo_exe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "OpenDesk.exe")
        if os.path.exists(repo_exe):
            target_exe = repo_exe
        else:
            # Nothing to overwrite directly, just inform caller
            return

    # Generate a lightweight updater batch helper
    temp_dir = tempfile.gettempdir()
    bat_path = os.path.join(temp_dir, "opendesk_self_update.bat")

    bat_content = f"""@echo off
setlocal
echo ========================================================
echo   OpenDesk In-App Self-Update in Progress...
echo ========================================================
echo Waiting for existing OpenDesk process to shut down...
timeout /t 2 /nobreak >nul

:RETRY_COPY
copy /y "{new_file_path}" "{target_exe}" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto RETRY_COPY
)

echo Update successfully applied!
echo Relaunching OpenDesk...
start "" "{target_exe}"

timeout /t 1 /nobreak >nul
del /f /q "{new_file_path}" >nul 2>&1
del "%~f0" >nul 2>&1
exit
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Launch batch updater in separate process
    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(0.2)
    sys.exit(0)
