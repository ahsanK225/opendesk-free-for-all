# OpenDesk 2.0.2 runtime validation

Environment: Windows 10 22H2 x64 (build 19045), Python 3.11.3, PyInstaller 6.20.0. Date: 2026-11-03.

The reported dialog was `Failed to load Python DLL ... _MEI.../python311.dll`, `LoadLibrary: The specified module could not be found`. A dialog alone does not identify the missing transitive dependency.

The v2.0.1 build inventory revealed `ucrtbase.dll` and API-set stubs collected from an unrelated libheif SDK on the builder PATH. That CRT has file version **10.0.26100.4654**; the actual Windows 10 system CRT has version **10.0.19041.3636**. v2.0.2 excludes those OS runtime files, retains Python's VC runtime redistributables, and restricts build PATH. The installed app uses a persistent runtime directory and updater restarts discard stale extraction state.

- 107 Python regressions passed and browser protocol/audio checks passed. After the final updater edits, all 8 updater/packaging tests passed again.
- The corrected onefile application and maintenance helper started with only Windows system directories on PATH. GUI smoke, PortAudio loading and valid 1280x960 DXGI capture passed.
- A real frozen self-update fixture replaced its own executable after both old onefile processes exited, then reported a different, existing extraction directory. This test also found and fixed Windows PowerShell lookup/module-path inheritance issues. It passed with PowerShell absent from PATH and an inherited PowerShell Core module configuration removed before launch.
- Release dependency audits require a bundled Python DLL and reject bundled OS CRT/API-set DLLs for both portable and installed formats. Build scripts now enforce this audit before packaging.

- Final portable GUI/DXGI/PortAudio smoke passed after all updater changes. The full 107-test regression suite also passed again.
- Isolated installer upgrade replaced a deliberately unresponsive, file-locking fixture in **13.790 seconds**, exit 0. The installed launcher hash matched the packaged launcher and `_internal/python311.dll` was present. Installed GUI, PortAudio and valid 1280x960 DXGI capture passed with clean Windows PATH. Fixture uninstall passed.
- The user's existing installation was upgraded in place, exit 0, and the installed file version is 2.0.2. Normal startup remained alive with its local HTTP/WebSocket listener ready. Protocol-v2 client registration and an Ed25519 nonce signature verification passed against that running packaged application. No remote-control session was requested.
- The existing desktop shortcut targets the corrected installed launcher and its installation working directory. Launching it again left the same single main process running. The existing device ID was preserved.

The corrected local installation is left running for the user. Release hashes are recorded in the downloadable manifest and SHA256SUMS.txt. These checks do not replace a second-machine WAN/headset acceptance run.
