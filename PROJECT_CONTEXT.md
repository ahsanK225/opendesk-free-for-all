# OpenDesk project context

Audit date: 2026-11-04. Audited at commit `473bd5d` on `main`, plus the uncommitted working-tree changes listed below. This file describes state at that date; check `git status` and `TASKS.md` for anything newer.

## Project overview

OpenDesk is a Windows 10/11 remote desktop application in the style of AnyDesk: share the primary screen, control an approved desktop, talk during a session and exchange files in a folder chosen by the host. The current public release is **2.8 stable**. It was originally a Python/Tk application and was rewritten in Rust and Qt; the Python code survives only in Git tags and old releases.

Remotes: `origin` is `ahsanK225/opendesk-free-for-all` (canonical, and the source of in-app updates). `portfolio` is `hamxa8769/opendesk-free-for-all` (fork).

## Architecture

| Part | Technology | Location |
| --- | --- | --- |
| Engine | Rust static library: capture, session authorization, network, audio, files, updates | `native/engine` |
| Desktop app | Qt 6.8.3/QML with a small C++ bridge over a C ABI | `native/desktop` |
| Installer/update helper | Standalone Rust executable, Inno Setup script | `native/launcher`, `native/installer.iss` |
| Browser viewer | Plain JavaScript, served by the engine | `web` |
| Tunnel | Hash-pinned `cloudflared` child process | `bin/cloudflared.exe`, `native/engine/src/directory.rs` |
| Device lookup | Signed, expiring records on `ntfy.sh` and `keyvalue.immanuel.co` | `native/engine/src/directory.rs` |
| Storage | No database. `config.json` in `%USERPROFILE%\.opendesk`, secrets protected by DPAPI | `native/engine/src/store.rs` |

There is no separate backend server: each desktop runs its own host. The transport is protocol-v2 WebSocket/WSS with JPEG tiles and mono PCM voice, not WebRTC. See `SYSTEM_DESIGN.md` for detail.

## Completed features

Present in the code. The core flow is covered by automated loopback tests; older packaged-app evidence is in `docs/`.

- DXGI screen capture with GDI fallback; Balanced, Performance and Sharp profiles with adaptive quality.
- Remote mouse and keyboard, cursor indicators, optional text clipboard.
- Per-connection approval with separate input, voice, clipboard and file permissions; immediate revocation.
- Device fingerprints, pinning and signed directory records; password-based unattended access using a challenge and proof.
- Two-way voice through WASAPI with mute, gain, volume and device retry.
- Folder-scoped file transfer with ordered chunks, SHA-256 checks and atomic replacement.
- Saved desktops, favorites, session tabs and a browser viewer.
- Installer, portable launcher with repair, SHA-256-verified updates.

### Uncommitted work (in the working tree only)

Committed on branch `feature/lite-and-compat-fixes`, not pushed or released, and the `OpenDesk.exe` in `native-build` predates it.

- Light theme, `Toggle.qml`, `LevelSlider.qml`, English-locale forcing and settings normalization.
- Protocol 1 compatibility with older desktops (`legacy.rs`).
- LAN address and listening on all interfaces (`network.rs`).
- DNS-over-HTTPS recovery and faster connection (`net.rs`), bounded directory responses.

## Verification on 2026-11-04

The table below is the original audit. Later results, including Full and Lite builds, packaged checks and installer tests, are in `docs/LITE_AND_COMPATIBILITY_VALIDATION.md`.

| Check | Result |
| --- | --- |
| Engine tests on a copy of the working tree | 39 passed, 0 failed |
| Engine Clippy with warnings denied | Passed |
| `tests/test_web.cjs` | Passed |
| `tests/test_release_versions.cjs` | Passed |
| v2.8 installer and portable SHA-256 against manifest | Match |
| Qt/C++ build of the uncommitted code | NOT RUN |
| Launcher tests and `native/test-*.ps1` | NOT RUN |
| Running the GUI | NOT RUN |
| Two physical devices, internet, headset | Never performed, according to project docs |

## Known bugs

Confirmed by reading the code; none was reproduced by running the application.

**In uncommitted code:**

1. **Fixed on the branch (T-004).** Originally: **High: protocol downgrade bypasses identity pinning.** A server that answers registration as protocol 1 enters legacy mode without any check of the saved key (`native/engine/src/client.rs:138`, `:228`). After the user continues past a warning, the password is sent in plaintext JSON (`client.rs:232`). Unverified legacy address hints from public directories make this reachable when no valid signed record is found (`directory.rs:142`, `:154`). A device that is already trusted should refuse legacy mode. Fix before committing.
2. **Medium: the host now listens on all interfaces.** `native/engine/src/network.rs:660` binds to `0.0.0.0`; the last commit bound to loopback. LAN traffic, including screen and input, is unencrypted, and the "Internet access" setting does not turn it off. Approval is still required.

**Minor UI:**

3. Fixed on the branch (T-007). The session quality selector always starts at "Balanced", whatever profile is active (`native/desktop/qml/Main.qml:210`).
4. Fixed on the branch (T-008). File sizes display only in B or KB, so large files read oddly (`Main.qml:163`).
5. Fixed on the branch (T-009). Reconnect opens a new tab and leaves the ended one open (`Main.qml:224`).

**Project hygiene:**

6. `RELEASE_NOTES.md` still describes 3.0.0-alpha.1. The README does not mention LAN or legacy mode. `../OPENDESK_AUDIT.md` and `../audit_checks.py` target old Python v1.2.2 and should not be used as current findings.
7. CI is not active: `.github/workflows` is empty. The template `ci/windows.yml` uses Inno Setup 6, while the README and local tools use 7.
8. Leftovers are present but ignored by Git: `client`, `common`, `host`, `relay`, `scripts` and `tools` contain only caches or nothing, along with `.build-deps` and `.build-spec` from the Python era.

## Pending tasks

See `TASKS.md`. In short: secure and commit the uncommitted work, then physical two-device and headset acceptance, measured FPS and latency, wider GPU and DPI coverage, independent security review and a signing decision. Future features: monitor selection, pre-login operation, compressed voice and echo cancellation, direct peer transport, end-to-end encryption and signed update metadata.

## Important file locations

| What | Where |
| --- | --- |
| Project instructions, subagents | `CLAUDE.md`, `.claude/agents/` |
| Session authorization rules | `native/engine/src/session.rs` |
| Host, relay, command handling | `native/engine/src/network.rs` |
| Viewer connection | `native/engine/src/client.rs` |
| Protocol 1 adapter | `native/engine/src/legacy.rs` |
| Capture and frame encode/decode | `capture.rs`, `media.rs`, `protocol.rs`, `stream.rs` in `native/engine/src` |
| Identity, passwords, config | `native/engine/src/store.rs` |
| Update logic | `native/engine/src/updater.rs`, `native/launcher/src/update.rs` |
| Main UI, theme | `native/desktop/qml/Main.qml`, `Theme.qml` |
| Build script | `build.ps1`, `native/build.ps1` |
| Release manifests | `version.json`, `native/version.json` |
| Validation evidence | `docs/` |
| Published binaries, build output (outside the repo) | `../Releases`, `../native-build` |

## Development instructions

Requirements: Windows x64, Rust 1.95.0 MSVC, Visual Studio 2022 Build Tools, CMake 3.24+, Qt 6.8.3 MSVC 2022 x64, libjpeg-turbo 3.2.1, Node.js and Inno Setup. See `CLAUDE.md` for test and build commands and `README.md` for the full build example.

Found on this computer during the audit: Rust 1.95.0, CMake 4.3.1, Node 25.3.0, Visual Studio Build Tools 2022, and Qt 6.8.3 under `%USERPROFILE%\.codex\visualizations\...`. That Qt location is an installation left by the previous agent, so consider moving it to a stable path. Inno Setup was not found in Program Files (`.release-tools` holds its installer).

## Recommended next steps

1. Decide whether to push `feature/lite-and-compat-fixes` (needs your approval).
2. Decide LAN exposure (known bug 2, T-005).
3. Check the built app on real hardware.
4. Do the two-device internet and headset acceptance run.
5. Update stale documents, then prepare 2.9.
