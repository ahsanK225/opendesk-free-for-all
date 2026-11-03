# OpenDesk native desktop

The native implementation uses a Rust engine, a Qt 6.8.3 / QML desktop, and libjpeg-turbo 3.2.1. It retains the dark/red OpenDesk design and the protocol-v2 browser viewer. The current stable release is 2.8. Public release numbers advance by 0.1; see ../docs/VERSION_HISTORY.md for the full ascending history.

## Implemented

- A built-in local relay, signed expiring device-directory records and a supervised, hash-pinned Cloudflare tunnel.
- Request-bound approvals, one-use password challenges, device-key trust, revocation, independent session permissions and persistent DPAPI-protected identity.
- Win32 DXGI capture with GDI fallback, an initial baseline even on idle desktops, cursor composition, BGRA buffers, ordered JPEG delta reconstruction, bounded acknowledgements and adaptive video profiles.
- Direct SIMD TurboJPEG encoding/decoding on media workers and Qt scene-graph textures for presentation. FPS counts actual texture presentations; an unchanged screen displays Idle.
- WASAPI voice through CPAL with explicit rates, continuous resampling, 20 ms mono packets, bounded queues, microphone mute and gain, speaker volume, default-device change detection and failed-device reopening.
- Keyboard/mouse input with held-input release, Unicode text clipboard, and folder-scoped file transfers with ordered chunks, SHA-256 verification, atomic replacement and partial-file cleanup.
- Native file/folder dialogs, saved devices/favorites, scrollable connection tabs, fingerprint verification, approval controls, software updates and an explicit host sharing indicator.
- A separate Rust maintenance helper for bounded shutdown, scoped process checks, portable replacement and installed updates. Portable runtime extraction is persistent and transactional rather than per-launch temporary Python extraction.

## Build on Windows x64

Use Rust 1.95.0 (MSVC), Visual Studio 2022 Build Tools with the Windows SDK, CMake 3.24+, Node for browser checks, Qt 6.8.3 MSVC 2022 x64, and the official libjpeg-turbo 3.2.1 Visual C++ x64 SDK. No Python interpreter or Python packages are required by the native application or its build.

```powershell
.\native\build.ps1 `
  -QtRoot C:\SDKs\Qt\6.8.3\msvc2022_64 `
  -TurboJpegRoot C:\SDKs\libjpeg-turbo-3.2.1 `
  -VcRuntimeDir 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\14.44.35112\x64\Microsoft.VC143.CRT' `
  -InnoCompiler 'C:\Program Files (x86)\Inno Setup 7\ISCC.exe'
```

The tunnel binary in `bin/cloudflared.exe` is pinned to official cloudflared 2026.9.3, SHA-256 `f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2`. Download it from the [official release](https://github.com/cloudflare/cloudflared/releases/tag/2026.9.3). The build rejects a different binary. The official JPEG SDK installer digest is `1f05bc3ed1585e6b12a8b0c24c8c5f07b1f6d90d01b4b709b331bedc9d6e5838`; use the [3.2.1 release](https://github.com/libjpeg-turbo/libjpeg-turbo/releases/tag/3.2.1).

Qt is dynamically linked. The installed runtime and portable cache contain ordinary replaceable Qt DLLs/plugins. The application-specific portable cache is under `%LOCALAPPDATA%\OpenDesk\runtimes`; `--repair` re-extracts its embedded runtime. Set `OPENDESK_RUNTIME_DIR` to a shorter absolute writable directory if a redirected profile exceeds the Windows Qt plugin loader path limit. User settings stay in `%USERPROFILE%\.opendesk`. License texts, upstream copyright notices, dependency inventory and Qt SPDX documents are in `licenses` in the distributable and [the source tree](licenses/README.md).

## Validation

```powershell
cargo test --release --locked --lib --manifest-path native/engine/Cargo.toml -- --test-threads=1
cargo clippy --release --locked --lib --manifest-path native/engine/Cargo.toml -- -D warnings
cargo test --release --locked --manifest-path native/launcher/Cargo.toml --features fixtures
node tests/test_web.cjs
```

The native executable supports isolated startup evidence:

```powershell
OpenDesk.exe --smoke-test --config-dir C:\Temp\OpenDeskSmoke --smoke-page settings --screenshot C:\Temp\settings.png --smoke-output C:\Temp\state.json
OpenDesk.exe --benchmark-output C:\Temp\native-benchmark.json
```

Benchmark JSON separates changed-screen capture, full/delta encode and decode. Codec timings exclude transport and GPU presentation and do not establish delivered internet FPS. [Process shutdown](test-launcher.ps1) and [executable replacement](test-update.ps1) scripts use isolated fixtures, so they do not need to close the user's real application.

## Test coverage and platform limits

Local native session/file/revocation tests, packaged locked-app upgrade, GPU pixel-format/render verification and 100%/150% DPI checks have passed. First/cached portable startup, automatic missing-DLL repair, explicit repair and actionable long-path rejection have also passed. Two-device WAN/headset acceptance remains open in the validation record. This is a primary-monitor, user-session Windows app: pre-login/service operation, the UAC secure desktop, multi-monitor selection and acoustic echo cancellation are not implemented. Headphones are recommended for two-way voice. Cloudflare terminates the HTTPS/WSS tunnel; this is not an end-to-end encrypted peer-to-peer transport.

The replaced Python runtime/build source has been removed from this native tree after native session and installed-package checks. Git tags v2.0.1 and v2.0.2, their release assets, and preserved source snapshots retain the previous implementation and rollback reference. No proprietary AnyDesk code, protocol or DeskRT codec is shipped.
