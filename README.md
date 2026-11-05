# OpenDesk

A Windows remote desktop application with a **Rust engine, Qt 6/QML interface and C++ rendering bridge**. Share the primary display, control an approved desktop, talk during a session and exchange files in a folder selected by the host.

**Stable Windows release v3.4:** [Windows installer](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v3.4/OpenDesk_Setup_v3.4_Installer.exe) · [Portable executable](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v3.4/OpenDesk_v3.4_Portable.exe) · [Release notes/checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.4) · [OpenDesk Lite installer](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v3.4/OpenDeskLite_Setup_v3.4_Installer.exe)

OpenDesk 3.4 is the current stable release. Both repositories publish it as **Latest**, and the live update manifest points to the same build. The [portfolio fork](https://github.com/hamxa8769/opendesk-free-for-all/releases/tag/v3.4) mirrors the current installer and portable executable. [Complete ascending version history: 1.0 through 3.4](docs/VERSION_HISTORY.md).

Local network access is off by default, and its traffic is not encrypted. When you turn on **Settings → Local network access**, use it only on networks you trust. OpenDesk does not send a password to an older desktop that cannot prove its identity, so an older desktop with a password must be updated, or its password turned off, before you can connect to it.

## Features

- DXGI display capture with GDI fallback, initial idle-desktop frames and cursor composition. SIMD libjpeg-turbo JPEG tiles feed Qt's GPU scene graph.
- Balanced, Performance and Sharp profiles, bounded frame acknowledgements and adaptive resolution/quality. FPS counts actual viewer frame presentations; a static screen can show **Idle**.
- Remote mouse, buttons, scrolling and keyboard. Input bypasses capture/encoding work; the viewer coalesces mouse movement to avoid stale queues. A cyan **You** cursor provides immediate viewer feedback; **Remote** identifies the controller on the host.
- Native WASAPI voice through CPAL: explicit sample rates, continuous resampling, 20 ms mono PCM packets, independent outgoing audio capacity and bounded playback buffering. Session mute/gain/volume, default-device retry and device readiness/errors are available.
- Incoming approval restores a minimized window and remains above other apps until acceptance, rejection or expiry. Input, voice, clipboard and files have separate permissions.
- Verified/pinned device fingerprints, DPAPI-protected local identity/passwords, one-use password challenges and immediate access revocation with held-input release.
- Saved desktops, favorites, session tabs, native file dialogs and folder-scoped transfers with ordered chunks, SHA-256 verification and atomic replacement.
- Native installer shutdown helper, verified-process force-close fallback, persistent portable cache, repair and verified updates. No Python or PyInstaller runtime.

## System requirements

| Component | Requirement |
| --- | --- |
| OS | Windows 10/11 x64, signed-in interactive desktop |
| Graphics | Direct3D 11 rendering; DXGI capture with GDI fallback |
| Network | Local TCP for LAN; outbound HTTPS/WSS and Cloudflare access for internet links/directory lookup |
| Voice | Windows default microphone and speaker/headset; desktop microphone permission |
| Storage | Writable per-user application/profile directories and space for the extracted runtime |
| Compatibility | Protocol-v2 OpenDesk on both ends; AnyDesk devices are incompatible |

Multi-monitor selection, pre-login hosting, UAC secure-desktop control and native acoustic echo cancellation are not implemented. Use headphones for two-way voice.

## Installation and setup

1. Download the complete native installer or portable executable above. Verify its SHA-256 against the release's `SHA256SUMS.txt` when checking download integrity.
2. Run the installer. The per-user default destination is `%LOCALAPPDATA%\Programs\OpenDesk`. Upgrading attempts cooperative shutdown, then a verified-process force-close fallback. Configuration and identity are preserved.
3. Open **OpenDesk** from its shortcut. Portable users open the downloaded executable; first launch extracts a persistent runtime and later launches reuse it.
4. Wait for the desktop address/local host to become ready. For internet use, wait for the share link.

Settings, trust and identity live in `%USERPROFILE%\.opendesk`. Portable files are cached in `%LOCALAPPDATA%\OpenDesk\runtimes`. Keep installed/cache DLLs with their executable. `OPENDESK_RUNTIME_DIR` can select a shorter absolute writable cache directory for redirected Windows profiles.

## Remote connection and screen sharing

1. **Host:** share the nine-digit address or internet share link. With **Settings → Local network access** on, the home screen also shows a LAN address.
2. **Viewer:** enter the address, host URL or share link and select **Connect**. On first connection, compare the fingerprint with the host's **Settings** before trusting it.
3. **Host:** the incoming dialog appears above other applications. Choose permissions and accept. Keyboard/mouse starts selected; voice, clipboard and files require selection. Requests expire after 60 seconds.
4. **Viewer:** change quality, toggle voice, browse allowed files or disconnect using the session toolbar. Performance targets up to 60 FPS at a smaller frame width; delivered FPS depends on screen changes, CPU, capture and network.
5. **Host:** the sharing bar identifies the connected peer. **End sharing** revokes the session immediately.

The cyan cursor visualizes the controller's pointer. Windows still has one system pointer; this does not create a second independent OS mouse. Movement maps to the displayed image including letterboxing. Clicks flush pending motion; scrolling positions the pointer before the wheel event.

After a network interruption, select **Reconnect**. Trust is checked again and attended access requires fresh approval. Permissions are not silently restored. Investigate changed fingerprints before reconnecting.

### Unattended access

Set an access password of at least eight characters in Settings if unattended access is intended. A valid password grants input, voice, clipboard and selected shared-folder access without a prompt. Microphones still follow local mute/default settings. Remove the password to return to attended approval.

### Browser viewer and files

The built-in local server serves a protocol-v2 browser viewer at the host's share URL. Browser microphone capture needs HTTPS or localhost, browser permission and a user gesture to resume playback. Native voice follows Windows privacy settings instead.

Choose the host's **Shared folder** before granting file access. Transfers operate inside that folder and verify order, size and hash before replacing a destination. Changing the folder ends sharing so a new session can explicitly authorize the new location.

## Voice communication setup

1. Select working default recording/playback devices under **Windows Settings → System → Sound**. Native OpenDesk follows the Windows defaults.
2. Enable microphone access and **Let desktop apps access your microphone** in Windows privacy settings. Labels differ slightly between Windows 10 and 11.
3. The host must grant **Two-way voice**. A disabled microphone button means voice permission was not granted; reconnect with that permission.
4. Enable **Mic on** on each side that should transmit. Microphones start muted by default. Settings provides gain and speaker volume.
5. Hover over the viewer microphone button for packet counts/device errors. **Mic retrying** means transmission was requested but the device has not opened. The app retries the default device; the session status exposes errors.

Changing volume, gain or quality preserves the session mute choice. Audio has a separate outgoing lane from video/files. Continuous packets avoid a fixed noise gate cutting quiet speech. Use headphones to prevent feedback: native echo cancellation is unavailable. Packet delivery tests alone do not establish physical microphone/speaker intelligibility.

## Connection stability and architecture

OpenDesk uses its own **protocol-v2 WebSocket/WSS transport**, JPEG tiles and mono PCM voice. It does **not** use WebRTC, ICE, STUN/TURN or AnyDesk's proprietary DeskRT codec. There are no ICE states or WebRTC tracks to configure.

A supervised hash-pinned Cloudflare tunnel and signed, expiring directory records provide internet reachability. Cloudflare terminates HTTPS/WSS; media is not end-to-end encrypted peer to peer.

Independent bounded lanes prioritize control and voice over file/video backlog. Decoder overload requests a full frame without blocking the socket reader. Client heartbeats run every second; valid text/ping/pong traffic updates host liveness. A 45-second receive inactivity limit and 30-second write deadline still terminate unresponsive connections. Capture/file queue overload no longer deliberately ends the whole session. A single socket can still experience network head-of-line blocking during a write.

## Build and development

Use Windows x64, Rust **1.95.0 MSVC**, Visual Studio 2022 Build Tools/Windows SDK, CMake 3.24+, Qt **6.8.3 MSVC 2022 x64**, libjpeg-turbo **3.2.1 Visual C++ x64**, Node.js for browser checks and Inno Setup for the installer. No Python packages/interpreter are required.

```powershell
git clone https://github.com/ahsanK225/opendesk-free-for-all.git
cd opendesk-free-for-all
.\native\fetch-cloudflared.ps1
.\build.ps1 -QtRoot C:\SDKs\Qt\6.8.3\msvc2022_64 `
  -TurboJpegRoot C:\SDKs\libjpeg-turbo-3.2.1 `
  -VcRuntimeDir 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\14.44.35112\x64\Microsoft.VC143.CRT' `
  -InnoCompiler 'C:\Program Files (x86)\Inno Setup 7\ISCC.exe'
```

Add `-Edition Lite` to build OpenDesk Lite in `dist/native-lite`: remote screen, keyboard, mouse, clipboard and connection, without voice, file transfer or automatic updates. SDK paths are examples. The build verifies the pinned Cloudflare binary and produces a runtime, portable executable, installer, manifest and checksums in `dist/native`. Qt DLLs/plugins remain replaceable; notices and SPDX information ship in `licenses`.

```powershell
cargo test --release --locked --lib --manifest-path native/engine/Cargo.toml -- --test-threads=1
cargo clippy --release --locked --lib --manifest-path native/engine/Cargo.toml -- -D warnings
cargo test --release --locked --manifest-path native/launcher/Cargo.toml --features fixtures
node tests/test_web.cjs
```

See [native architecture/build details](native/README.md), [current release validation](docs/RELEASE_2_8_VALIDATION.md), [dependency licenses](native/licenses/README.md) and [logo directions](assets/brand/README.md). [ci/windows.yml](ci/windows.yml) is a template, **not an enabled GitHub Actions workflow**.

## Updates and recovery

**Settings → Software updates → Check for updates** checks the configured channel manifest. Updates verify an official release URL and SHA-256, then the independent helper replaces/restarts the app. Portable updates retain a rollback copy. Root `version.json` and `native/version.json` describe the same current stable release and verified download hashes.

Install the current stable release through its installer or replace the portable executable. Existing 3.0.0-alpha installations need this installer once to migrate to the consistent numbering. Portable `--repair` rebuilds a damaged extracted runtime. Preserve `%USERPROFILE%\.opendesk` to retain identity and saved devices. Release executables are not claimed to carry a publicly trusted Authenticode signature.

## Troubleshooting

| Symptom | Checks and recovery |
| --- | --- |
| `Failed to load Python DLL` on 2.0.1 | Install a complete native 3.x package. Native builds contain no Python DLL; avoid mixing files from old installations. |
| Installer waits while closing | Allow the bounded shutdown attempt to finish. Close an instance with different privileges or use matching installer privileges. The helper reports failure rather than waiting forever. |
| Missing Qt/plugin/VC DLL | Reinstall the complete package or use portable `--repair`. Do not copy only the inner executable. A shorter `OPENDESK_RUNTIME_DIR` can help redirected profiles. |
| Missing share link/ID lookup | Check internet, Cloudflare reachability and Internet access in Settings. On the same network, turn on Settings → Local network access and try the LAN address. Share URLs can change after a tunnel restart. |
| Incoming request unseen | Keep the host running. A new request restores the minimized window and remains topmost. Windows foreground restrictions can flash the taskbar; secure-desktop prompts remain outside app control. |
| Low FPS or delayed input | Update both sides, choose Performance and check CPU/network load. FPS measures presentation; static screens need fewer updates. |
| Voice enabled but silent | Check voice permission, both microphone toggles, Windows privacy/default devices and speaker volume. Inspect packet counters/device errors. Browser users also need permission and resumed playback. |
| Feedback/distortion | Use headphones and lower gain/volume. Native acoustic echo cancellation is unavailable. |
| Intermittent disconnect | Update both sides, check tunnel/network changes and reconnect with fresh approval. Report both versions, the visible error and LAN versus internet connection. |
| Changed fingerprint | Compare with the host. Do not dismiss this merely to connect. Deleting `.opendesk` creates a new identity. |
| File access denied | Confirm permission and chosen shared folder. Paths outside it, traversal and UNC access are rejected. |

## Version history and changelog

Release numbers advance without gaps: **1.0, 1.1, …, 1.9, 2.0, …, 3.4**. The next release is **3.5**.

| Version | Release notes and downloads |
| --- | --- |
| **1.0** | [Historical source archive](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.0) |
| **1.1** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.1) |
| **1.2** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.2) |
| **1.3** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.3) |
| **1.4** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.4) |
| **1.5** | [Historical source archive](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.5) |
| **1.6** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.6) |
| **1.7** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.7) |
| **1.8** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.8) |
| **1.9** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v1.9) |
| **2.0** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.0) |
| **2.1** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.1) |
| **2.2** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.2) |
| **2.3** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.3) |
| **2.4** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.4) |
| **2.5** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.5) |
| **2.6** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.6) |
| **2.7** | [Desktop release and downloads](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.7) |
| **2.8** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.8) |
| **2.9** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.9) |
| **3.0** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.0) |
| **3.1** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.1) |
| **3.2** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.2) |
| **3.3** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.3) |
| **3.4 — current stable** | [Windows installer, portable, manifest and checksums](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.4) |

Original source tags and historical binaries are preserved. See [complete history and original build mapping](docs/VERSION_HISTORY.md) and [CHANGELOG.md](CHANGELOG.md).

## Collaboration and license

OpenDesk originates in [Ahsan's repository](https://github.com/ahsanK225/opendesk-free-for-all). Original authorship, MIT license and Git history are preserved. [Hamza Iqbal (@hamxa8769)](https://github.com/hamxa8769) contributes modernization/native migration, assisted by Codex.

The [portfolio fork](https://github.com/hamxa8769/opendesk-free-for-all), [public engineering project](https://github.com/users/hamxa8769/projects/3), [migration PR](https://github.com/ahsanK225/opendesk-free-for-all/pull/1) and [contribution record](docs/CONTRIBUTIONS.md) document the work. This independent application does not implement or interoperate with AnyDesk's proprietary protocol.
