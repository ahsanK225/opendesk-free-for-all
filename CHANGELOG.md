# Changelog
All notable project changes are documented here.

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
