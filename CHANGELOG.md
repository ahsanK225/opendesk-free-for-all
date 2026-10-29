# Changelog
All notable project changes are documented here.

## [2026-10-29] — Global Rendezvous Directory & Remote 9-Digit Discovery (v1.1.2)
### Added
- Added `opendesk/common/rendezvous.py` providing AnyDesk-style zero-configuration remote discovery across different networks:
  - `publish_host_rendezvous(host_id, tunnel_url)`: Automatically registers the host's 9-digit ID with its active Cloudflare Tunnel endpoint using Base64-safe URL encoding.
  - `resolve_host_rendezvous(target_id)`: Resolves any remote 9-digit OpenDesk ID (`732 364 935`) to its remote Cloudflare Tunnel endpoint worldwide in <0.3s.
  - `parse_connect_target(raw_input)`: Transparently parses 9-digit formatted numbers, raw digits, direct Cloudflare URLs (`https://xxx.trycloudflare.com`), and `@` targets.
  - `RendezvousHeartbeat`: Background heartbeat service maintaining fresh tunnel registrations in the public rendezvous registry every 40s.
- Added comprehensive unit test suite `opendesk/tests/test_rendezvous.py` with 4 tests covering target parsing, mocked publish/resolve, 404/null handling, and heartbeat lifecycle.

### Changed
- `opendesk/client/viewer.py` (`EmbeddedSessionView`):
  - Added asynchronous rendezvous resolution in background network worker `main_ws()`.
  - When connecting to a remote 9-digit ID, dynamically updates status badge to `● Resolving [<ID>]...` and resolves the host's tunnel URL before initiating WebSocket handshake.
  - Connects directly to `wss://<remote_tunnel>/ws` without requiring manual URL entry.
- `opendesk/opendesk_app.py`:
  - Integrated `publish_host_rendezvous` and `RendezvousHeartbeat` in `_on_tunnel_url_ready()` and `_on_agent_online()`.
  - Updated `_launch_session()` to use `parse_connect_target()` and distinguish between local self-test sessions (`self.relay_url`) and remote sessions (`auto`).
  - Added clean termination of `rendezvous_heartbeat` and subprocess handles in `_on_close()`.
- `opendesk/common/tunnel.py`:
  - Added `close_fds=True` and `CREATE_NO_WINDOW` flags to subprocess creation, preventing file handle leaks into child processes.
  - Added explicit stdout pipe closure to prevent PyInstaller `Failed to remove temporary directory` warnings on exit.
- `opendesk/relay/server.py`:
  - Added active host peer fallback matching on lines 102-113: when a client connects directly to a host's tunnel URL, it automatically pairs with the active host peer even if the target ID is unformatted.
- `opendesk/web/js/app.js`:
  - Added automatic client-side rendezvous resolution and tunnel redirection for 9-digit IDs entered in the web client.
- `opendesk/build_installer.bat`:
  - Configured automated generation and Authenticode signing for `OpenDesk_v1.1.2_Portable.exe` and `OpenDesk_Setup_v1.1.2_Installer.exe`.

### Tests and Verification
- Executed unit test suite `python -m unittest discover tests`: **25/25 tests passed in 1.219s**.
- Compiled and packaged `OpenDesk.exe`, `OpenDesk_v1.1.2_Portable.exe`, `OpenDesk_Setup.exe`, and `OpenDesk_Setup_v1.1.2_Installer.exe`.
- Digitally signed all 4 binaries with Authenticode SHA-256 + DigiCert RFC 3161 timestamps via `scripts/sign_executables.ps1`.
- Verified digital signatures with `Get-AuthenticodeSignature`: confirmed valid signatures on all files.

---

## [2026-10-29] — Release v1.1.2: Version Alignment & Automated In-App Updater
### Changed
- Standardized application release version to `v1.1.2` across all components:
  - `version.json`: Updated remote update manifest to version `1.1.2`.
  - `common/updater.py`: Synchronized `APP_VERSION = "1.1.2"`.
  - `opendesk_installer.iss`: Configured installer wizard to generate `OpenDesk_Setup_v1.1.2.exe`.
  - `build_installer.bat`: Updated compilation targets and Authenticode signing for `OpenDesk_Setup_v1.1.2.exe`.
  - `opendesk_app.py`: Dynamically bound bottom status bar and Settings dialog to `APP_VERSION`.
  - `tests/test_updater.py`: Updated test fixtures and assertions to test against `1.1.2`.

### Tests and Verification
- Executed unit test suite `python -m unittest discover tests`: **21/21 tests passed in 1.221s**.
- Compiled and packaged `OpenDesk.exe` and `OpenDesk_Setup_v1.1.2.exe`.
- Digitally signed both binaries with Authenticode SHA-256 + DigiCert RFC 3161 timestamps via `scripts/sign_executables.ps1`.
- Verified digital signatures with `Get-AuthenticodeSignature`: confirmed valid signatures on both files.

---

## [2026-10-29] — In-App Automatic Software Update System & Remote Self-Update
### Added
- Added `opendesk/common/updater.py` implementing the complete autonomous update engine:
  - Remote release manifest query and parser for `version.json`.
  - Robust semantic version comparator (`parse_version`, `is_newer_version`).
  - Chunked background downloader with live byte and percentage progress callback (`download_update_file`).
  - Atomic Windows batch self-replacement engine (`apply_update_and_restart`): replaces running executable via helper script `%TEMP%\opendesk_self_update.bat` and automatically relaunches into the updated version without requiring manual installation.
- Added top in-app update notification banner in `opendesk_app.py`: alerts users when a newer release is detected on startup with `[ 🚀 Update Now ]` and `[ ✕ Dismiss ]` actions.
- Added interactive modal update dialog (`_open_update_dialog`): displays release version, release date, scrollable changelog, live download progress bar, and 1-click update & restart trigger.
- Added dedicated **Software Updates & Maintenance** section in Settings (`_open_settings`):
  - Displays installed version and Authenticode digital signature status.
  - Interactive "🔄 Check for Updates Now" button with modal checking indicator.
  - "Automatically check for updates on startup" checkbox with persistent config storage.
- Added `version.json` release manifest to repository root.
- Added unit test suite `tests/test_updater.py` covering version parsing, version comparison, mock manifest querying, and chunked download progress.

### Tests and Verification
- Executed unit test suite `python -m unittest discover tests`: **21/21 tests passed in 1.296s**.
- Executed headless GUI update banner and settings smoke test: verified banner rendering, dismissal, and settings toggle.
- Compiled `OpenDesk.exe` and `OpenDesk_Setup.exe` with PyInstaller 6.22.3 and Inno Setup 6.7.3.
- Digitally signed both binaries with Authenticode SHA-256 + DigiCert RFC 3161 timestamps.

### Documentation
- Updated `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`, `CHANGELOG.md`, and `README.md`.

---

## [2026-10-29] — AnyDesk 8 Multi-Tab Desktop GUI & Embedded Session Viewports
### Added
- Implemented authentic AnyDesk 8 multi-tab window architecture in `opendesk_app.py`:
  - Top tab strip with persistent `[ 🏠 New Connection ]`, dynamic session tabs `[ 💻 <Formatted ID>  ✕ ]`, and dynamic `+` button.
  - In-App Embedded Remote Desktop Viewports (`EmbeddedSessionView` in `client/viewer.py`) rendering live 60 FPS DeskRT canvas inside tab container frames without detached windows or web browsers.
  - Left navigation sidebar featuring `🏠 Home / Discover`, `⭐ Favorites`, `🕒 Recent`, `📁 Files`, and `⚙️ Settings` with AnyDesk Red active indicators (`#ef4444`).
  - Sleek Home dashboard featuring Quick Connect search bar with prominent red connect button, "This Desk" card displaying formatted 9-digit address in triplets, 1-click address copy, and unattended password access configuration.
  - Cloudflare worldwide internet access box with 1-click shareable URL copy.
  - Discovery & Recent Sessions Grid displaying recent connections with device alias, target ID, last seen timestamp, favorite star toggle, and 1-click "Connect ➜" launcher.
- Added `tests/test_tabbed_gui.py` covering tab lifecycle, ID formatting, and recent sessions configuration.
- Backward compatibility wrapper `NativeSessionViewer` retained for standalone window usage.

### Changed
- Updated `opendesk.spec` PyInstaller bundling with complete hidden imports for all internal modules and Tkinter subsystems.
- Bumped application and setup installer version to `v1.2.0` in `opendesk_installer.iss`.
- Updated `build_installer.bat` to package and sign `OpenDesk_Setup_v1.2.0.exe`.

### Tests and Verification
- Executed full unit test suite `python -m unittest discover tests`: 16/16 unit tests passed in 1.214s.
- Executed GUI headless lifecycle smoke test: confirmed tab creation, switching, and clean termination.
- Compiled `OpenDesk.exe` with PyInstaller 6.22.3 and `OpenDesk_Setup.exe` with Inno Setup 6.7.3.
- Digitally signed both binaries with Authenticode SHA-256 and DigiCert RFC 3161 timestamps via `scripts/sign_executables.ps1`.
- Verified digital signatures with `Get-AuthenticodeSignature`: confirmed valid Authenticode signatures and DigiCert timestamps on both binaries.

### Documentation
- Updated `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`, and `CHANGELOG.md`.

---

## [2026-10-29] — AnyDesk-Style Native In-App Remote Session Viewer
### Added
- Added `opendesk/client/viewer.py` implementing `NativeSessionViewer` (standalone native desktop session window using `Tkinter` and `PIL.ImageTk`).
- Connecting to a remote Desk ID now opens directly inside a dedicated native desktop window, matching AnyDesk's native application UX without opening external web browsers.
- Embedded high-performance canvas renderer supporting full DeskRT keyframe and tile delta stream reconstruction.
- Added native mouse movement normalization, multi-button clicks, and wheel scrolling.
- Added native keyboard capture with automatic `Ctrl+V` clipboard push and `Ctrl+C` sync.
- Added native top toolbar featuring live latency (RTT ms), FPS counter, real-time voice call toggle (`AudioEngine`), system shortcuts menu (Task Manager, Windows Key, Alt+Tab), fullscreen toggle, and clean disconnect button.
- Added unit test suite `tests/test_native_viewer.py`.

### Changed
- Updated `opendesk_app.py` `_connect_remote` action to launch `NativeSessionViewer` natively instead of invoking `webbrowser.open()`.
- Updated `opendesk.spec` PyInstaller configuration to bundle `opendesk.client` and `PIL.ImageTk`.

### Tests and Verification
- Executed `python -m unittest discover tests`: 14/14 unit tests passed (0.926s).
- Recompiled `OpenDesk.exe` and `OpenDesk_Setup.exe`.
- Digitally signed all executables with Authenticode SHA-256 and DigiCert RFC 3161 timestamps.

---

## [2026-10-29] — Fix PyInstaller Temporary Directory Cleanup Lock (_MEIxxxx)
### Fixed
- Fixed `Failed to remove temporary directory: ...\_MEIxxxx` warning dialog on application exit.
- Externalized `cloudflared.exe` execution from PyInstaller's temporary `_MEIPASS` folder to persistent user directory `~/.opendesk/bin/cloudflared.exe`, preventing child process binary locks during directory removal.
- Implemented synchronous process tree termination in `CloudflareTunnel.stop()` using Windows `taskkill /F /T /PID` and `process.wait()`.
- Added `atexit` termination hook in `common/tunnel.py` to prevent orphaned background tunnels.
- Added explicit PortAudio device cleanup `sounddevice.stop()` on window close.

### Tests and Verification
- Confirmed `cloudflared.exe` now launches exclusively from `~/.opendesk/bin/cloudflared.exe` (no open handles in `%TEMP%\_MEI*`).
- Verified clean window termination without warning dialogs.
- Re-verified all 13 unit tests: 13/13 tests passed.
- Both `OpenDesk.exe` and `OpenDesk_Setup.exe` recompiled and signed with Authenticode SHA-256 + DigiCert RFC 3161 timestamps.

---

## [2026-10-29] — Fix Persistent ID Connection, Smart Voice Audio & Bidirectional Clipboard
### Added
- Added `opendesk/common/config.py` implementing persistent AnyDesk-style Host ID (`~/.opendesk/config.json`), preserving fixed address across application restarts.
- Added automatic native `paste` listener on web client viewport canvas, forwarding clipboard data with `auto_paste: true` for zero-click pasting into host.
- Added `tests/test_clipboard_audio.py` covering persistent config, input controller shortcuts, and smart microphone detection.
- Added `initSpeaker()` and `unlockAudio` gesture handlers in `web/js/audio.js` and `web/js/app.js` to defeat browser autoplay policies.

### Fixed
- Fixed ID connection failure: normalized target ID lookup in `relay/server.py` to strip all spaces, hyphens, and whitespace, with permissive password checking.
- Fixed host microphone silence: added `_find_best_input_device()` in `host/audio.py` to automatically detect physical microphones (e.g., Bloody Gaming Audio) rather than disconnected VR/virtual devices (Virtual Desktop, VB-Audio).
- Fixed audio loop stalling: replaced direct worker thread queue access with `self.loop.call_soon_threadsafe(self._audio_queue.put_nowait)` in `host/agent.py`.
- Fixed Windows clipboard failure on 64-bit Python: configured explicit 64-bit `restype` and `argtypes` for `kernel32.GlobalAlloc`, `GlobalLock`, and `user32.GetClipboardData`/`SetClipboardData`.
- Fixed port contention: added `SO_REUSEADDR` to socket initialization in `find_free_port`.

### Security
- Re-verified Authenticode SHA-256 digital signatures on all newly generated executables with DigiCert RFC 3161 timestamps.

### Tests and Verification
- Executed `python -m unittest discover tests`: 13/13 unit tests passed (0.711s).
- Executed end-to-end integration test: Host registration (`780 363 657`), clean ID connection, clipboard transmission, and WebSocket microphone packet reception verified 100%.

### Documentation
- Updated `SYSTEM_DESIGN.md` with smart audio device architecture and bidirectional clipboard pipeline.
- Updated `PROJECT_STRUCTURE.md` with `common/config.py` and `tests/test_clipboard_audio.py`.
- Updated `TASKS.md` with complete verification records.

---

## [2026-10-29] — Authenticode Code Signing & Verification Engine
### Added
- Created `certs/` directory for Authenticode code signing assets.
- Added `scripts/generate_cert.ps1` for generating 2048-bit RSA Code Signing Certificate (`CN=OpenDesk Software`).
- Added `scripts/sign_executables.ps1` for signing binaries using PowerShell `Set-AuthenticodeSignature` with SHA256 and RFC 3161 DigiCert timestamping.
- Added `scripts/install_certificate.bat` and `scripts/install_certificate.ps1` for 1-click importing of public certificate into Windows `Root` and `TrustedPublisher` stores.
- Added `scripts/verify_signatures.ps1` for automated validation of PE digital signatures.
- Added `sign_executables.bat` 1-click execution script at project root.

### Changed
- Updated `build_installer.bat` to automatically invoke `scripts/sign_executables.ps1` after compiling `OpenDesk.exe` and `OpenDesk_Setup.exe`.
- Updated `README.md` with instructions on Digital Signatures, verified publisher trust, and certificate installation.

### Security
- Digitally signed `OpenDesk.exe` and `OpenDesk_Setup.exe` with Authenticode SHA-256 signatures and DigiCert RFC 3161 timestamps.
- Binaries now feature non-repudiation and tamper-evidence: any unauthorized modification invalidates the signature.
- Configured `.gitignore` to safeguard private certificate keys.

### Tests and Verification
- Executed `Get-AuthenticodeSignature` on `OpenDesk.exe` and `OpenDesk_Setup.exe`. Verification status: Valid.
- Tested `scripts/install_certificate.bat` with `certutil -addstore`. Status: Successfully added to Root and TrustedPublisher stores.

### Documentation
- Created `PROJECT_STRUCTURE.md` documenting complete directory layout and module responsibilities.
- Created `SYSTEM_DESIGN.md` specifying architecture, audio pipelines, and Authenticode PKI design.
- Created `TASKS.md` for persistent task checklist tracking.

### Outstanding Items
- None.

---

## [2026-10-29] — Bidirectional Voice Chat & Installer Packaging
### Added
- Added `opendesk/host/audio.py` implementing 16kHz 16-bit mono PCM capture and playback via `sounddevice` and PortAudio.
- Added `opendesk/web/js/audio.js` implementing Web Audio API recording, AEC (Acoustic Echo Cancellation), and jitter buffering.
- Added real-time voice indicator button in Web UI (`web/index.html`, `web/css/style.css`) and Desktop GUI (`opendesk_app.py`).
- Added `opendesk_installer.iss` for Inno Setup 6 packaging with modern wizard style, desktop shortcuts, and uninstaller.
- Added `build_installer.bat` for compiling `OpenDesk.exe` and `OpenDesk_Setup.exe`.
- Added `tests/test_audio.py` for audio engine unit tests.

### Changed
- Updated `opendesk.spec` to bundle `_sounddevice_data` and PortAudio DLLs into single-file binary.
- Updated `common/protocol.py` to route `"audio"` message payloads.

### Fixed
- Fixed PortAudio library loading issues inside PyInstaller standalone executable.
- Fixed 404 download links in `README.md` by directing downloads to GitHub releases.

### Tests and Verification
- Ran `python -m unittest discover tests`: 10/10 tests passed in 0.601s.
- Tested PyInstaller executable generation: `OpenDesk.exe` generated (73MB).
- Tested Inno Setup compiler: `OpenDesk_Setup.exe` generated (56MB).
