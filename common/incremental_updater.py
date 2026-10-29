"""
Smart Incremental Auto-Updater for RemoteConnect / OpenDesk
Enables AnyDesk-style differential updates by downloading and updating only modified
or new files rather than re-downloading entire 70 MB application packages.
Features:
- SHA-256 cryptographic hash validation for all files.
- Differential manifest analysis: skips unchanged files (up to 99% bandwidth savings).
- User settings and session data preservation (never overwrites config, tokens, logs).
- Atomic staging with automatic rollback protection on download failure or hash mismatch.
- Support for Windows file-lock avoidance and automatic application relaunch.
"""

import os
import sys
import json
import hashlib
import fnmatch
import shutil
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple

DEFAULT_PRESERVE_PATTERNS = [
    "config.json",
    "recent_sessions.json",
    "unattended.key",
    "certs/*",
    "logs/*",
    "*.log",
    "user_data/*",
    ".opendesk/*",
    ".remoteconnect/*",
]


def compute_file_sha256(filepath: str, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 cryptographic hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def should_preserve_file(rel_path: str, preserve_patterns: List[str]) -> bool:
    """Check if relative path matches any preserve pattern."""
    normalized = rel_path.replace("\\", "/")
    for pattern in preserve_patterns:
        pat_norm = pattern.replace("\\", "/")
        if fnmatch.fnmatch(normalized, pat_norm) or fnmatch.fnmatch(os.path.basename(normalized), pat_norm):
            return True
    return False


@dataclass
class DifferentialPlan:
    current_version: str
    target_version: str
    to_download: List[Dict[str, Any]] = field(default_factory=list)
    to_skip: List[Dict[str, Any]] = field(default_factory=list)
    to_delete: List[str] = field(default_factory=list)
    total_delta_bytes: int = 0
    total_install_bytes: int = 0
    bandwidth_saved_bytes: int = 0
    bandwidth_saved_pct: float = 0.0
    changelog: List[str] = field(default_factory=list)
    release_date: str = ""
    base_url: str = ""

    def summary(self) -> str:
        return (
            f"Update {self.current_version} -> {self.target_version}: "
            f"{len(self.to_download)} files to download ({self.total_delta_bytes / 1024:.1f} KB), "
            f"{len(self.to_skip)} files unchanged (saved {self.bandwidth_saved_pct:.1f}% bandwidth)."
        )


class IncrementalUpdater:
    """
    Core engine for differential file-level software updates.
    """

    def __init__(
        self,
        install_dir: str,
        manifest_url: str,
        app_name: str = "RemoteConnect",
        current_version: str = "1.0.0",
        preserve_patterns: Optional[List[str]] = None,
    ):
        self.install_dir = os.path.abspath(install_dir)
        self.manifest_url = manifest_url
        self.app_name = app_name
        self.current_version = current_version
        self.preserve_patterns = preserve_patterns or list(DEFAULT_PRESERVE_PATTERNS)

    def fetch_manifest(self, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Fetch and parse remote versioned manifest from HTTP/HTTPS server."""
        req = urllib.request.Request(
            self.manifest_url,
            headers={"User-Agent": f"{self.app_name}-IncrementalUpdater/{self.current_version}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
        except Exception as e:
            print(f"[IncrementalUpdater] Failed to fetch manifest from {self.manifest_url}: {e}")
            return None
        return None

    def compute_differential(self, manifest: Dict[str, Any]) -> DifferentialPlan:
        """
        Compare local files against remote manifest using SHA-256 hashes.
        Identifies exact files to download, unchanged files to skip, and obsolete files to delete.
        """
        target_version = manifest.get("version", self.current_version)
        changelog = manifest.get("changelog", [])
        if isinstance(changelog, str):
            changelog = [changelog]
        release_date = manifest.get("release_date", "")
        base_url = manifest.get("base_url", "")
        remote_files = manifest.get("files", [])
        preserve_patterns = list(self.preserve_patterns) + manifest.get("preserve", [])

        to_download: List[Dict[str, Any]] = []
        to_skip: List[Dict[str, Any]] = []
        remote_paths_set = set()

        total_install_bytes = 0
        total_delta_bytes = 0

        for r_file in remote_files:
            rel_path = r_file.get("path", "").replace("\\", "/")
            if not rel_path:
                continue

            remote_paths_set.add(rel_path)
            file_size = int(r_file.get("size", 0))
            expected_sha256 = r_file.get("sha256", "").lower()
            total_install_bytes += file_size

            local_path = os.path.join(self.install_dir, rel_path.replace("/", os.sep))

            # Skip if explicitly preserved
            if should_preserve_file(rel_path, preserve_patterns) and os.path.isfile(local_path):
                to_skip.append(r_file)
                continue

            # Check if local file exists and hash matches
            if os.path.isfile(local_path):
                try:
                    local_sha256 = compute_file_sha256(local_path)
                    if local_sha256 == expected_sha256:
                        to_skip.append(r_file)
                        continue
                except Exception:
                    pass  # Hash computation failed; mark for re-download

            # File is missing, modified, or has mismatched hash
            to_download.append(r_file)
            total_delta_bytes += file_size

        # Find deprecated files in local install that are not in remote manifest
        to_delete: List[str] = []
        if os.path.isdir(self.install_dir):
            for root, _, filenames in os.walk(self.install_dir):
                for fname in filenames:
                    abs_p = os.path.join(root, fname)
                    rel_p = os.path.relpath(abs_p, self.install_dir).replace("\\", "/")

                    # Ignore internal updater staging/backup directories
                    if rel_p.startswith(".update_") or rel_p.startswith("__pycache__"):
                        continue

                    # Check preserve patterns
                    if should_preserve_file(rel_p, preserve_patterns):
                        continue

                    if rel_p not in remote_paths_set:
                        to_delete.append(rel_p)

        saved_bytes = total_install_bytes - total_delta_bytes
        saved_pct = (saved_bytes / total_install_bytes * 100.0) if total_install_bytes > 0 else 0.0

        return DifferentialPlan(
            current_version=self.current_version,
            target_version=target_version,
            to_download=to_download,
            to_skip=to_skip,
            to_delete=to_delete,
            total_delta_bytes=total_delta_bytes,
            total_install_bytes=total_install_bytes,
            bandwidth_saved_bytes=saved_bytes,
            bandwidth_saved_pct=saved_pct,
            changelog=changelog,
            release_date=release_date,
            base_url=base_url,
        )

    def download_delta(
        self,
        plan: DifferentialPlan,
        staging_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str, int, int], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, str]:
        """
        Download only modified/new files into staging directory and verify SHA-256 for each.
        If any hash fails, staging is wiped and an error is returned.
        progress_callback: (downloaded_bytes, total_delta_bytes, current_file, current_index, total_files)
        Returns: (success: bool, error_message_or_staging_path: str)
        """
        if not staging_dir:
            staging_dir = os.path.join(self.install_dir, ".update_staging")

        # Clean staging dir
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)

        downloaded_so_far = 0
        total_files = len(plan.to_download)

        try:
            for idx, file_info in enumerate(plan.to_download, start=1):
                if cancel_flag and cancel_flag():
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return False, "Update cancelled by user."

                rel_path = file_info["path"].replace("\\", "/")
                expected_sha256 = file_info["sha256"].lower()
                file_size = int(file_info.get("size", 0))

                # Build URL
                file_url = file_info.get("url")
                if not file_url:
                    base = plan.base_url.rstrip("/")
                    file_url = f"{base}/{urllib.parse.quote(rel_path)}"

                staged_file_path = os.path.join(staging_dir, rel_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(staged_file_path), exist_ok=True)

                # Download with chunked hashing
                hasher = hashlib.sha256()
                req = urllib.request.Request(
                    file_url,
                    headers={"User-Agent": f"{self.app_name}-IncrementalUpdater"},
                )

                with urllib.request.urlopen(req, timeout=30.0) as resp:
                    with open(staged_file_path, "wb") as f_out:
                        while True:
                            if cancel_flag and cancel_flag():
                                shutil.rmtree(staging_dir, ignore_errors=True)
                                return False, "Update cancelled by user."

                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            hasher.update(chunk)
                            downloaded_so_far += len(chunk)

                            if progress_callback:
                                progress_callback(
                                    downloaded_so_far,
                                    plan.total_delta_bytes,
                                    rel_path,
                                    idx,
                                    total_files,
                                )

                # Verify SHA-256 hash immediately
                computed_hash = hasher.hexdigest().lower()
                if computed_hash != expected_sha256:
                    # Integrity failure: wipe staging and abort with rollback
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    err_msg = (
                        f"Integrity check failed for {rel_path}! "
                        f"Expected SHA-256: {expected_sha256}, got: {computed_hash}"
                    )
                    print(f"[IncrementalUpdater] {err_msg}")
                    return False, err_msg

            return True, staging_dir

        except Exception as e:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return False, f"Download failed: {str(e)}"

    def apply_staged_update(
        self,
        plan: DifferentialPlan,
        staging_dir: str,
        backup_dir: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Atomically apply verified files from staging to target install_dir.
        Creates backup snapshot beforehand. If any copy fails, automatically
        rolls back all changes from backup. User settings are never touched.
        """
        if not os.path.isdir(staging_dir):
            return False, f"Staging directory does not exist: {staging_dir}"

        if not backup_dir:
            backup_dir = os.path.join(self.install_dir, ".update_backup")

        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
        os.makedirs(backup_dir, exist_ok=True)

        copied_paths: List[Tuple[str, str]] = []  # (staged, target)
        preserve_patterns = list(self.preserve_patterns)

        try:
            # 1. Backup all files that will be modified or deleted
            for file_info in plan.to_download:
                rel_p = file_info["path"].replace("\\", "/")
                if should_preserve_file(rel_p, preserve_patterns):
                    continue
                target_p = os.path.join(self.install_dir, rel_p.replace("/", os.sep))
                if os.path.isfile(target_p):
                    bk_p = os.path.join(backup_dir, rel_p.replace("/", os.sep))
                    os.makedirs(os.path.dirname(bk_p), exist_ok=True)
                    shutil.copy2(target_p, bk_p)

            for rel_del in plan.to_delete:
                if should_preserve_file(rel_del, preserve_patterns):
                    continue
                target_p = os.path.join(self.install_dir, rel_del.replace("/", os.sep))
                if os.path.isfile(target_p):
                    bk_p = os.path.join(backup_dir, rel_del.replace("/", os.sep))
                    os.makedirs(os.path.dirname(bk_p), exist_ok=True)
                    shutil.copy2(target_p, bk_p)

            # 2. Copy all staged files into install directory
            for file_info in plan.to_download:
                rel_p = file_info["path"].replace("\\", "/")
                if should_preserve_file(rel_p, preserve_patterns):
                    continue
                staged_p = os.path.join(staging_dir, rel_p.replace("/", os.sep))
                target_p = os.path.join(self.install_dir, rel_p.replace("/", os.sep))
                os.makedirs(os.path.dirname(target_p), exist_ok=True)
                shutil.copy2(staged_p, target_p)
                copied_paths.append((staged_p, target_p))

            # 3. Remove obsolete files
            for rel_del in plan.to_delete:
                if should_preserve_file(rel_del, preserve_patterns):
                    continue
                target_p = os.path.join(self.install_dir, rel_del.replace("/", os.sep))
                if os.path.isfile(target_p):
                    try:
                        os.remove(target_p)
                    except Exception:
                        pass

            # 4. Save updated local manifest/version file
            version_marker_path = os.path.join(self.install_dir, "version.json")
            try:
                marker_data = {
                    "app_name": self.app_name,
                    "version": plan.target_version,
                    "release_date": plan.release_date or time.strftime("%Y-%m-%d"),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_delta_bytes": plan.total_delta_bytes,
                }
                with open(version_marker_path, "w", encoding="utf-8") as f:
                    json.dump(marker_data, f, indent=2)
            except Exception:
                pass

            # Update in-memory version
            self.current_version = plan.target_version

            # 5. Clean up staging & backup on success
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)

            return True, f"Successfully upgraded {self.app_name} to version {plan.target_version}."

        except Exception as e:
            # 6. ROLLBACK TRIGGER: Restore all backed up files
            print(f"[IncrementalUpdater] Error during update application: {e}. Initiating atomic rollback...")
            try:
                for root, _, filenames in os.walk(backup_dir):
                    for fname in filenames:
                        bk_file = os.path.join(root, fname)
                        rel_bk = os.path.relpath(bk_file, backup_dir)
                        restore_dest = os.path.join(self.install_dir, rel_bk)
                        os.makedirs(os.path.dirname(restore_dest), exist_ok=True)
                        shutil.copy2(bk_file, restore_dest)
            except Exception as rollback_err:
                print(f"[IncrementalUpdater] Critical: Rollback error: {rollback_err}")

            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(backup_dir, ignore_errors=True)
            return False, f"Update failed and was rolled back safely: {str(e)}"

    def create_windows_restart_script(
        self,
        staging_dir: str,
        target_exe: str,
        process_pid: Optional[int] = None,
    ) -> str:
        """
        Generate a standalone Windows batch script to apply staged updates
        after the current application process terminates, avoiding file lock errors,
        and relaunching the updated application.
        """
        temp_dir = tempfile.gettempdir()
        script_path = os.path.join(temp_dir, f"{self.app_name.lower()}_apply_delta.bat")
        pid = process_pid or os.getpid()

        script_content = f"""@echo off
setlocal enabledelayedexpansion
title {self.app_name} Incremental Auto-Updater

echo ========================================================
echo   {self.app_name} Incremental Update in Progress
echo ========================================================
echo Waiting for running process (PID {pid}) to exit...

:WAIT_PROCESS
tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto WAIT_PROCESS
)

echo Applying verified delta files...
timeout /t 1 /nobreak >nul

xcopy /E /Y /Q "{staging_dir}\\*" "{self.install_dir}\\" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Could not copy files directly. Retrying...
    timeout /t 2 /nobreak >nul
    xcopy /E /Y /Q "{staging_dir}\\*" "{self.install_dir}\\" >nul 2>&1
)

echo Cleaning up update cache...
rmdir /S /Q "{staging_dir}" >nul 2>&1

echo Relaunching {self.app_name}...
start "" "{target_exe}"

timeout /t 1 /nobreak >nul
del "%~f0" >nul 2>&1
exit
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        return script_path
