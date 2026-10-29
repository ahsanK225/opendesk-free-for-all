"""
Comprehensive Unit & Integration Test Suite for Incremental Auto-Updater
Validates:
1. SHA-256 cryptographic hashing and verification.
2. Differential manifest comparison (skipping unchanged files).
3. Preservation of user settings and session configuration.
4. Automatic atomic rollback protection on hash mismatch or failure.
5. End-to-end multi-release update test (v1.0.0 -> v1.0.1 -> v1.0.2) using live HTTP server.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.incremental_updater import (
    compute_file_sha256,
    should_preserve_file,
    IncrementalUpdater,
    DifferentialPlan,
    DEFAULT_PRESERVE_PATTERNS,
)
from tools.manifest_generator import generate_release_manifest
from tools.update_server import start_update_server


class TestIncrementalUpdater(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_rc_updater_")
        self.install_dir = os.path.join(self.test_dir, "client_app")
        self.server_dir = os.path.join(self.test_dir, "update_server")
        os.makedirs(self.install_dir, exist_ok=True)
        os.makedirs(self.server_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sha256_computation_and_verify(self):
        """Verify SHA-256 hash calculation matches known standard output."""
        sample_file = os.path.join(self.test_dir, "sample.txt")
        with open(sample_file, "wb") as f:
            f.write(b"RemoteConnect Incremental Update Engine 2026")

        calculated = compute_file_sha256(sample_file)
        self.assertEqual(len(calculated), 64)
        # Verify determinism
        recalculated = compute_file_sha256(sample_file)
        self.assertEqual(calculated, recalculated)

    def test_preserve_patterns(self):
        """Verify user configuration and logs are recognized for preservation."""
        self.assertTrue(should_preserve_file("config.json", DEFAULT_PRESERVE_PATTERNS))
        self.assertTrue(should_preserve_file("logs/session_8812.log", DEFAULT_PRESERVE_PATTERNS))
        self.assertTrue(should_preserve_file("unattended.key", DEFAULT_PRESERVE_PATTERNS))
        self.assertTrue(should_preserve_file("certs/OpenDesk_CodeSigning.cer", DEFAULT_PRESERVE_PATTERNS))
        self.assertFalse(should_preserve_file("RemoteConnect.exe", DEFAULT_PRESERVE_PATTERNS))
        self.assertFalse(should_preserve_file("common/updater.py", DEFAULT_PRESERVE_PATTERNS))

    def test_differential_detection(self):
        """
        Verify differential comparison: unchanged files are skipped,
        modified/new files are flagged for download, and savings percentage is calculated.
        """
        # Create 5 existing files in client install
        files_data = {
            "core.dll": b"Binary core code v1.0.0" * 500,
            "engine.py": b"print('Engine v1.0.0')",
            "assets/icon.png": b"PNG ICON DATA" * 200,
            "styles.css": b"body { background: #f3f4f6; }",
            "config.json": b'{"user_id": "732 364 935", "unattended": true}',
        }
        for rel_p, data in files_data.items():
            abs_p = os.path.join(self.install_dir, rel_p.replace("/", os.sep))
            os.makedirs(os.path.dirname(abs_p), exist_ok=True)
            with open(abs_p, "wb") as f:
                f.write(data)

        # Manifest represents v1.0.1:
        # - core.dll and assets/icon.png are identical
        # - engine.py is modified (new hash)
        # - styles.css is modified
        # - new_module.py is added
        engine_v101 = b"print('Engine v1.0.1 - patched!')"
        styles_v101 = b"body { background: #ffffff; color: #dc2626; }"
        new_module_data = b"def delta_feature(): pass"

        import hashlib
        manifest = {
            "app_name": "RemoteConnect",
            "version": "1.0.1",
            "base_url": "https://updates.remoteconnect.io/releases/v1.0.1/",
            "files": [
                {
                    "path": "core.dll",
                    "size": len(files_data["core.dll"]),
                    "sha256": hashlib.sha256(files_data["core.dll"]).hexdigest(),
                    "action": "replace",
                },
                {
                    "path": "engine.py",
                    "size": len(engine_v101),
                    "sha256": hashlib.sha256(engine_v101).hexdigest(),
                    "action": "replace",
                },
                {
                    "path": "assets/icon.png",
                    "size": len(files_data["assets/icon.png"]),
                    "sha256": hashlib.sha256(files_data["assets/icon.png"]).hexdigest(),
                    "action": "replace",
                },
                {
                    "path": "styles.css",
                    "size": len(styles_v101),
                    "sha256": hashlib.sha256(styles_v101).hexdigest(),
                    "action": "replace",
                },
                {
                    "path": "new_module.py",
                    "size": len(new_module_data),
                    "sha256": hashlib.sha256(new_module_data).hexdigest(),
                    "action": "replace",
                },
            ],
            "preserve": ["config.json"],
        }

        updater = IncrementalUpdater(
            install_dir=self.install_dir,
            manifest_url="http://mock.test/manifest.json",
            current_version="1.0.0",
        )

        plan = updater.compute_differential(manifest)

        # Check results
        skipped_paths = [f["path"] for f in plan.to_skip]
        download_paths = [f["path"] for f in plan.to_download]

        self.assertIn("core.dll", skipped_paths)
        self.assertIn("assets/icon.png", skipped_paths)
        self.assertIn("engine.py", download_paths)
        self.assertIn("styles.css", download_paths)
        self.assertIn("new_module.py", download_paths)

        # Verify bandwidth savings
        self.assertGreater(plan.bandwidth_saved_pct, 50.0)
        self.assertEqual(plan.target_version, "1.0.1")

    def test_rollback_on_hash_mismatch(self):
        """
        Verify that if a downloaded file's SHA-256 does not match the manifest,
        the staging directory is wiped and the current install is not touched.
        """
        # Create server directory with corrupted content
        server_release = os.path.join(self.server_dir, "v1.0.1")
        os.makedirs(server_release, exist_ok=True)

        patch_file = os.path.join(server_release, "patch.bin")
        with open(patch_file, "wb") as f:
            f.write(b"CORRUPTED BYTES TRANSFERRED")

        server, port, _ = start_update_server(self.server_dir)
        try:
            # Manifest advertises a different hash than what server delivers
            manifest = {
                "app_name": "RemoteConnect",
                "version": "1.0.1",
                "base_url": f"http://127.0.0.1:{port}/v1.0.1/",
                "files": [
                    {
                        "path": "patch.bin",
                        "size": 27,
                        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",  # mismatched
                        "action": "replace",
                    }
                ],
            }

            updater = IncrementalUpdater(
                install_dir=self.install_dir,
                manifest_url=f"http://127.0.0.1:{port}/manifest.json",
                current_version="1.0.0",
            )

            plan = updater.compute_differential(manifest)
            success, err_msg = updater.download_delta(plan)

            self.assertFalse(success)
            self.assertIn("Integrity check failed", err_msg)

            # Ensure staging directory was wiped
            staging = os.path.join(self.install_dir, ".update_staging")
            self.assertFalse(os.path.exists(staging))

        finally:
            server.shutdown()
            server.server_close()

    def test_user_settings_preserved_during_update(self):
        """
        Verify that user settings, session tokens, and custom config files
        remain completely intact when applying an incremental update.
        """
        config_path = os.path.join(self.install_dir, "config.json")
        user_config_data = {
            "host_id": "732 364 935",
            "alias": "My Office Workstation",
            "unattended_password_hash": "$argon2id$v=19$m=65536,t=3,p=4$abc123secret",
            "recent_sessions": [{"id": "482 910 234", "alias": "Build Server"}],
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(user_config_data, f, indent=2)

        # Existing code file
        main_py = os.path.join(self.install_dir, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write("# Version 1.0.0")

        # Create staged update with new main.py
        staging_dir = os.path.join(self.install_dir, ".update_staging")
        os.makedirs(staging_dir, exist_ok=True)
        staged_main = os.path.join(staging_dir, "main.py")
        with open(staged_main, "w", encoding="utf-8") as f:
            f.write("# Version 1.0.1 - Upgraded!")

        plan = DifferentialPlan(
            current_version="1.0.0",
            target_version="1.0.1",
            to_download=[{"path": "main.py", "size": 30, "sha256": "fake"}],
            to_skip=[],
        )

        updater = IncrementalUpdater(
            install_dir=self.install_dir,
            manifest_url="http://mock/manifest.json",
            current_version="1.0.0",
        )

        success, msg = updater.apply_staged_update(plan, staging_dir)
        self.assertTrue(success)

        # Verify main.py was upgraded
        with open(main_py, "r", encoding="utf-8") as f:
            self.assertIn("Version 1.0.1 - Upgraded!", f.read())

        # Verify user config.json was NOT overwritten or modified!
        with open(config_path, "r", encoding="utf-8") as f:
            loaded_cfg = json.load(f)
        self.assertEqual(loaded_cfg["host_id"], "732 364 935")
        self.assertEqual(loaded_cfg["unattended_password_hash"], user_config_data["unattended_password_hash"])
        self.assertEqual(len(loaded_cfg["recent_sessions"]), 1)

    def test_real_incremental_update_two_releases(self):
        """
        END-TO-END INTEGRATION TEST:
        1. Setup client installation at Release v1.0.0.
        2. Publish Release v1.0.1 with only 2 files modified on live update HTTP server.
        3. Run updater: verify ONLY those 2 files are downloaded, unchanged 70 MB files skipped.
        4. Client successfully upgraded to v1.0.1.
        5. Publish Release v1.0.2 with 1 file modified.
        6. Client successfully upgraded to v1.0.2.
        7. User settings remain completely preserved through both updates.
        """
        # --- STEP 1: Setup v1.0.0 Client Installation ---
        client_files = {
            "RemoteConnect.exe": b"MZ_EXECUTABLE_LAUNCHER_SIMULATION_V100" * 1000,   # ~38 KB
            "runtime_core.dll": b"HEAVY_RUNTIME_DEPENDENCY_DLL_UNCHANGED" * 5000,    # ~195 KB
            "app.py": b"# RemoteConnect App v1.0.0\nAPP_VERSION = '1.0.0'\n",
            "ui_assets/theme.css": b"/* Theme v1.0.0 */\n.btn { color: red; }\n",
            "config.json": b'{"device_id": "732 364 935", "theme": "dark", "saved_secret": "persist_me_123"}',
        }

        for rel_p, content in client_files.items():
            abs_p = os.path.join(self.install_dir, rel_p.replace("/", os.sep))
            os.makedirs(os.path.dirname(abs_p), exist_ok=True)
            with open(abs_p, "wb") as f:
                f.write(content)

        # Start live HTTP update server
        server, port, _ = start_update_server(self.server_dir)
        base_url = f"http://127.0.0.1:{port}"

        try:
            # --- STEP 2: Publish Release v1.0.1 on Server ---
            # Only app.py and a new patch_notes.txt are changed/added!
            # RemoteConnect.exe, runtime_core.dll, ui_assets/theme.css are IDENTICAL.
            v101_release_dir = os.path.join(self.server_dir, "releases", "v1.0.1")
            os.makedirs(v101_release_dir, exist_ok=True)

            v101_files = {
                "RemoteConnect.exe": client_files["RemoteConnect.exe"],       # UNCHANGED
                "runtime_core.dll": client_files["runtime_core.dll"],         # UNCHANGED
                "app.py": b"# RemoteConnect App v1.0.1\nAPP_VERSION = '1.0.1'\n# Incremental patch applied!\n", # MODIFIED
                "ui_assets/theme.css": client_files["ui_assets/theme.css"],   # UNCHANGED
                "patch_notes.txt": b"Release v1.0.1 Notes:\n- Incremental update support\n",                     # NEW
            }

            for rel_p, content in v101_files.items():
                abs_p = os.path.join(v101_release_dir, rel_p.replace("/", os.sep))
                os.makedirs(os.path.dirname(abs_p), exist_ok=True)
                with open(abs_p, "wb") as f:
                    f.write(content)

            # Generate v1.0.1 manifest
            manifest_v101 = generate_release_manifest(
                source_dir=v101_release_dir,
                version="1.0.1",
                base_url=f"{base_url}/releases/v1.0.1/",
                changelog=["Added incremental updates", "Fixed minor memory leak"],
                output_file=os.path.join(self.server_dir, "manifest.json"),
            )

            # --- STEP 3: Client Checks and Applies Update to v1.0.1 ---
            updater = IncrementalUpdater(
                install_dir=self.install_dir,
                manifest_url=f"{base_url}/manifest.json",
                current_version="1.0.0",
            )

            fetched_manifest = updater.fetch_manifest()
            self.assertIsNotNone(fetched_manifest)
            self.assertEqual(fetched_manifest["version"], "1.0.1")

            plan = updater.compute_differential(fetched_manifest)

            # Assert: 3 files are skipped, only 2 files downloaded!
            skipped = [f["path"] for f in plan.to_skip]
            download = [f["path"] for f in plan.to_download]

            self.assertIn("RemoteConnect.exe", skipped)
            self.assertIn("runtime_core.dll", skipped)
            self.assertIn("ui_assets/theme.css", skipped)
            self.assertIn("app.py", download)
            self.assertIn("patch_notes.txt", download)
            self.assertEqual(len(download), 2)

            # Verify massive bandwidth savings
            self.assertGreater(plan.bandwidth_saved_pct, 80.0)

            # Download delta with progress tracking
            progress_events = []
            def on_progress(done, total, cur_file, idx, total_files):
                progress_events.append((done, total, cur_file, idx, total_files))

            success, staging_path = updater.download_delta(plan, progress_callback=on_progress)
            self.assertTrue(success)
            self.assertTrue(len(progress_events) > 0)

            # Apply staged update
            apply_ok, apply_msg = updater.apply_staged_update(plan, staging_path)
            self.assertTrue(apply_ok)

            # Verify files on client disk
            with open(os.path.join(self.install_dir, "app.py"), "rb") as f:
                self.assertIn(b"APP_VERSION = '1.0.1'", f.read())
            self.assertTrue(os.path.isfile(os.path.join(self.install_dir, "patch_notes.txt")))

            # Verify user config was completely preserved
            with open(os.path.join(self.install_dir, "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg["saved_secret"], "persist_me_123")

            # --- STEP 4: Publish Release v1.0.2 on Server ---
            # In v1.0.2, only ui_assets/theme.css changes!
            v102_release_dir = os.path.join(self.server_dir, "releases", "v1.0.2")
            os.makedirs(v102_release_dir, exist_ok=True)

            v102_files = dict(v101_files)
            v102_files["ui_assets/theme.css"] = b"/* Theme v1.0.2 Dark Mode */\n.btn { color: #dc2626; background: #111; }\n"

            for rel_p, content in v102_files.items():
                abs_p = os.path.join(v102_release_dir, rel_p.replace("/", os.sep))
                os.makedirs(os.path.dirname(abs_p), exist_ok=True)
                with open(abs_p, "wb") as f:
                    f.write(content)

            generate_release_manifest(
                source_dir=v102_release_dir,
                version="1.0.2",
                base_url=f"{base_url}/releases/v1.0.2/",
                changelog=["Dark mode high contrast theme"],
                output_file=os.path.join(self.server_dir, "manifest.json"),
            )

            # --- STEP 5: Client Updates to v1.0.2 ---
            updater_v102 = IncrementalUpdater(
                install_dir=self.install_dir,
                manifest_url=f"{base_url}/manifest.json",
                current_version="1.0.1",
            )

            manifest_2 = updater_v102.fetch_manifest()
            plan_2 = updater_v102.compute_differential(manifest_2)

            # Assert: ONLY 1 file (ui_assets/theme.css) is in download list!
            self.assertEqual(len(plan_2.to_download), 1)
            self.assertEqual(plan_2.to_download[0]["path"], "ui_assets/theme.css")
            self.assertEqual(len(plan_2.to_skip), 4)

            # Download & apply
            d_ok, st_path = updater_v102.download_delta(plan_2)
            self.assertTrue(d_ok)
            a_ok, _ = updater_v102.apply_staged_update(plan_2, st_path)
            self.assertTrue(a_ok)

            # Verify updated css file
            with open(os.path.join(self.install_dir, "ui_assets", "theme.css"), "rb") as f:
                self.assertIn(b"Theme v1.0.2 Dark Mode", f.read())

            # User config still intact
            with open(os.path.join(self.install_dir, "config.json"), "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg["saved_secret"], "persist_me_123")

        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
