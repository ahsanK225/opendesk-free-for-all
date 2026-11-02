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
from typing import Optional, Dict, Any, Callable, Tuple, List

from common.incremental_updater import (
    IncrementalUpdater,
    DifferentialPlan,
    compute_file_sha256,
)

APP_VERSION = "2.0.0"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/version.json"


def get_install_dir() -> str:
    """Return the base installation directory of the running application."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

                plan = None
                is_incremental = False
                return {
                    "available": available,
                    "version": remote_ver,
                    "current_version": current_version,
                    "release_date": data.get("release_date", "Recent"),
                    "download_url": data.get("download_url", ""),
                    "sha256": data.get("sha256", ""),
                    "installer_url": data.get("installer_url", ""),
                    "changelog": changelog_text,
                    "manifest_data": data,
                    "is_incremental": is_incremental,
                    "differential_plan": plan,
                }
    except Exception as e:
        print(f"[Updater] Update check failed or offline: {e}")
        return None
    return None


def download_update_file(url: str,
                         dest_path: str,
                         progress_callback: Optional[Callable[[int, int], None]] = None,
                         cancel_flag: Optional[Callable[[], bool]] = None,
                         error_holder: Optional[List[str]] = None,
                         expected_sha256: Optional[str] = None) -> bool:
    """
    Download update executable in chunks with progress reporting.
    progress_callback(bytes_downloaded, total_bytes)
    """
    if not expected_sha256 or not re.fullmatch(r'[a-fA-F0-9]{64}',expected_sha256):
        if error_holder is not None: error_holder.append('Update manifest is missing a valid SHA-256 digest.')
        return False
    from urllib.parse import urlsplit
    target = urlsplit(url)
    if target.scheme != 'https' or target.hostname != 'github.com' or not target.path.startswith('/ahsanK225/opendesk-free-for-all/releases/download/'):
        if error_holder is not None: error_holder.append('Update URL is not an official HTTPS release asset.')
        return False
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
        if compute_file_sha256(dest_path) != expected_sha256.lower():
            raise ValueError('Downloaded update SHA-256 mismatch')
        return True
    except urllib.error.HTTPError as he:
        err_msg = f"HTTP {he.code}: {he.reason} (File may not be uploaded to GitHub release yet)"
        print(f"[Updater] Download HTTP error: {err_msg}")
        if error_holder is not None:
            error_holder.append(err_msg)
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        return False
    except Exception as e:
        err_msg = str(e)
        print(f"[Updater] Download error: {err_msg}")
        if error_holder is not None:
            error_holder.append(err_msg)
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        return False


def apply_update_and_restart(new_file_path: str, is_installer: bool = False, expected_sha256: str = ''):
    """Stage an external, bounded Windows helper; caller must close the main application."""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Source checkout: update with Git. Executable replacement is available in packaged builds.')
    if not expected_sha256 or compute_file_sha256(new_file_path) != expected_sha256.lower():
        raise ValueError('Refusing to apply an unverified update')
    target = os.path.abspath(sys.executable)
    source = os.path.abspath(new_file_path)
    if os.path.normcase(target) == os.path.normcase(source):
        raise ValueError('Update source must differ from the running executable')
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    pid = os.getpid()
    if is_installer:
        install = f"Start-Process -FilePath {quote(source)} -ArgumentList '/SILENT' -WindowStyle Hidden"
    else:
        install = f"""$backup = {quote(target+'.previous')}
Copy-Item -LiteralPath {quote(target)} -Destination $backup -Force
try {{
    Copy-Item -LiteralPath {quote(source)} -Destination {quote(target)} -Force
    Start-Process -FilePath {quote(target)} -WorkingDirectory {quote(os.path.dirname(target))}
}} catch {{
    Copy-Item -LiteralPath $backup -Destination {quote(target)} -Force
    throw
}}"""
    script = f"""$ErrorActionPreference = 'Stop'
Wait-Process -Id {pid} -Timeout 30 -ErrorAction SilentlyContinue
if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ throw 'OpenDesk did not exit within 30 seconds' }}
if ((Get-FileHash -LiteralPath {quote(source)} -Algorithm SHA256).Hash.ToLower() -ne {quote(expected_sha256.lower())}) {{ throw 'Update hash changed after staging' }}
{install}
"""
    fd, helper = tempfile.mkstemp(prefix='opendesk_update_',suffix='.ps1')
    with os.fdopen(fd,'w',encoding='utf-8-sig') as stream: stream.write(script)
    subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',helper],
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return True
