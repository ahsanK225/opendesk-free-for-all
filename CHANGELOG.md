# Changelog
All notable project changes are documented here.

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
