# OpenDesk 3 native preview

**Download v3.0.0-alpha.1:** [Windows installer](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v3.0.0-alpha.1/OpenDesk_Setup_v3.0.0-alpha.1_Installer.exe) · [Portable EXE](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v3.0.0-alpha.1/OpenDesk_v3.0.0-alpha.1_Portable.exe) · [Native release page](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v3.0.0-alpha.1)

The native version is listed as a **Pre-release** on the Releases page. GitHub's stable **Latest** link continues to show v2.0.2. The [portfolio fork's native release](https://github.com/hamxa8769/opendesk-free-for-all/releases/tag/v3.0.0-alpha.1) mirrors the same verified binaries.

OpenDesk now has a **Rust engine and Qt/QML desktop**, retaining the dark/red design with a new Portal O icon. The native Windows application, installer helper and portable launcher do not use Python or temporary PyInstaller extraction.

The native build is a preview pending two-device WAN/headset acceptance. [v2.0.2 remains the previous stable release](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.0.2). Optimized Release builds and local test results are not a guarantee of internet FPS or voice quality on every device.

## What changed

- Native DXGI capture with cursor composition, GDI fallback and an initial frame even when the desktop is idle.
- BGRA buffers, direct SIMD libjpeg-turbo 3.2.1, ordered JPEG tile reconstruction, bounded video acknowledgements and adaptive quality. Qt renders frames through its GPU scene graph; the toolbar reports actual frame presentations.
- Native WASAPI voice through CPAL, explicit sample rates, continuous resampling, 20 ms packets, bounded buffers, microphone mute/gain, speaker volume and default-device recovery.
- Device fingerprint verification, DPAPI-protected identity/passwords, one-use password challenges, request-bound approval, independent input/voice/clipboard/file permissions and immediate revocation.
- Saved desktops, favorites, multiple session tabs, native file/folder dialogs, a chosen shared folder, ordered hash-verified atomic transfers and an always-visible host sharing indicator.
- A responsive Qt desktop checked at 100% and 150% scaling. The sidebar compacts and home cards stack on smaller screens.
- A standalone Rust shutdown helper with a bounded cooperative grace period and verified-process force-close fallback. The installer upgrades running old versions and preserves configuration/device identity.
- A portable launcher with a persistent transactional runtime cache and repair support. Updates verify the official release URL and SHA-256, wait for the app to exit, retain a portable rollback copy and restart independently.

This project uses its own protocol-v2 JPEG tile transport. It does not implement AnyDesk's proprietary DeskRT codec or connect to AnyDesk devices.

## Build and verify

Windows 10/11 x64, Rust 1.95.0 MSVC, Visual Studio 2022 Build Tools/Windows SDK, CMake, Qt 6.8.3 MSVC 2022 x64 and libjpeg-turbo 3.2.1 Visual C++ x64 are required. Node runs the browser checks. Inno Setup builds the installer.

```powershell
.\native\fetch-cloudflared.ps1
.\build.ps1 -QtRoot C:\SDKs\Qt\6.8.3\msvc2022_64 `
  -TurboJpegRoot C:\SDKs\libjpeg-turbo-3.2.1 `
  -VcRuntimeDir 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\14.44.35112\x64\Microsoft.VC143.CRT' `
  -InnoCompiler 'C:\Program Files (x86)\Inno Setup 7\ISCC.exe'
```

See [native build/architecture instructions](native/README.md), [native validation](docs/NATIVE_VALIDATION.md), [dependency licenses](native/licenses/README.md) and the [four logo directions](assets/brand/README.md). The CI template lives in [ci/windows.yml](ci/windows.yml); it is not an active GitHub workflow.

## Running and sharing

Open the installed or portable executable. Enter a remote device's nine-digit ID or share URL. Verify its fingerprint on first connection, then request access. The host chooses permissions. A configured unattended password grants control, voice, clipboard and access to the selected shared folder without an approval prompt; new passwords require at least eight characters. Microphones start muted by default.

Settings and persistent identity live in `%USERPROFILE%\.opendesk`. Portable runtimes are cached in `%LOCALAPPDATA%\OpenDesk\runtimes`; `--repair` re-extracts the embedded runtime. `OPENDESK_RUNTIME_DIR` can select a shorter absolute cache directory for redirected Windows profiles. Existing Qt DLLs remain replaceable in the cache/installation.

Keep both devices on protocol-v2 releases. Cloudflare provides HTTPS/WSS access and signed, expiring directory records. Cloudflare terminates the tunnel; this is not an end-to-end encrypted peer-to-peer transport. Headphones reduce voice feedback. Primary-monitor control in the logged-in user session is supported; pre-login services, the UAC secure desktop, multi-monitor selection and acoustic echo cancellation are not implemented.

## Collaboration and portfolio

OpenDesk originates in [Ahsan's repository](https://github.com/ahsanK225/opendesk-free-for-all). Original authorship, MIT license and Git history are preserved. [Hamza Iqbal (@hamxa8769)](https://github.com/hamxa8769) contributes the v2 modernization and native migration, assisted by Codex.

The [portfolio fork](https://github.com/hamxa8769/opendesk-free-for-all), [public engineering project](https://github.com/users/hamxa8769/projects/3), [native pull request](https://github.com/ahsanK225/opendesk-free-for-all/pull/1) and [contribution record](docs/CONTRIBUTIONS.md) provide implementation and validation evidence. Earlier Python implementations remain available in tags/releases v2.0.1 and v2.0.2; replaced runtime/build files were removed from this native source tree after native session, installer and startup checks.

`version.json` describes the stable update channel. A native preview can be downloaded separately without silently enrolling existing stable users into preview updates. Release executables are not claimed to have a publicly trusted Authenticode signature.
