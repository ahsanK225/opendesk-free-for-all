# Changelog
All notable project changes are documented here.

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
