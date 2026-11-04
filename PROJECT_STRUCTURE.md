# OpenDesk structure

- `native/engine`: Rust authorization, signed device lookup/tunnel supervision, DXGI capture, JPEG delta transport/reconstruction, WASAPI audio, Win32 input/clipboard, atomic file transfer, settings and verified update downloads.
- `native/desktop`: Qt/QML native desktop, small C++ command/state bridge, immutable frame views, GPU textures and TurboJPEG worker callbacks.
- `native/launcher`: independent Rust installer/shutdown helper, post-exit updater and persistent-cache portable bootstrap.
- `native/licenses`: pinned dependency inventory, license/copyright files and Qt SPDX documents.
- `web`: compatible protocol-v2 browser viewer.
- `tests/test_web.cjs`: browser protocol/auth/audio checks.
- `native/test-*.ps1`: isolated process, executable replacement, installer and portable repair checks.
- `assets/brand`: four SVG logo directions, comparison board and native ICO/PNG assets.
- `docs`: contribution record and dated release-validation evidence.
- `build.ps1`: native build entry point. `ci/windows.yml` is a publishable CI template, not an installed workflow.

The previous Python implementation is retained in Git tags/releases v2.0.1 and v2.0.2 and source snapshots. It is no longer part of this native source tree.

## Directory tree

```text
opendesk-free-for-all/
  CLAUDE.md, PROJECT_CONTEXT.md    project instructions and current status
  .claude/agents/                  nine project subagents
  build.ps1                        build entry point (calls native/build.ps1)
  version.json                     live stable update manifest
  web/                             browser viewer (index.html, css, js)
  tests/                           Node checks: browser, release versions, incoming probe
  docs/                            release validation evidence and version history
  assets/brand/                    logo directions and icons
  ci/windows.yml                   CI template, not an enabled workflow
  bin/                             cloudflared binary (git-ignored, fetched by script)
  native/
    build.ps1, installer.iss       packaging, Full and Lite editions
    fetch-cloudflared.ps1          fetches the pinned tunnel binary
    test-*.ps1                     packaged process, install, update and repair checks
    version.json                   copy of the live manifest
    engine/src/                    Rust engine
    desktop/                       C++ bridge and qml/
    launcher/src/                  installer, update and portable helper
    licenses/                      third-party notices
```

Next to the repository, not tracked by it: `../Releases` (published binaries) and `../native-build` (default build output). The folders `client`, `common`, `host`, `relay`, `scripts`, `tools`, `.build-deps` and `.build-spec` are ignored Python-era leftovers and are not part of the build.

## Engine modules

| Module | Responsibility |
| --- | --- |
| `app.rs` | Application handle, shared view state, settings normalization |
| `ffi.rs` | C ABI used by the Qt bridge |
| `network.rs` | Local HTTP/WebSocket host, peer handling, UI commands |
| `session.rs` | Host authorization state machine and permission checks |
| `client.rs` | Viewer connection, trust and password flow |
| `directory.rs` | Tunnel supervision, signed device records, address resolution |
| `net.rs` | DNS recovery and socket connection (uncommitted) |
| `legacy.rs` | Protocol 1 adapter (uncommitted) |
| `transport.rs` | Prioritized bounded outgoing lanes |
| `capture.rs`, `media.rs`, `jpeg.rs` | Screen capture, host and decode workers, JPEG |
| `protocol.rs`, `stream.rs` | Binary video envelope, acknowledgement window |
| `audio.rs` | WASAPI voice through CPAL |
| `files.rs` | Folder-scoped transfers |
| `platform.rs` | Win32 input, clipboard and window helpers |
| `store.rs` | Config, device identity, DPAPI secrets, password proof |
| `updater.rs` | Verified update download and handoff |
| `diagnostics.rs` | Startup and capture diagnostics |

## Main dependencies

Rust: tokio, axum, tokio-tungstenite, reqwest (rustls), serde, ed25519-dalek, pbkdf2, sha2, cpal, windows, jpeg-encoder, fast_image_resize. Desktop: Qt 6.8.3, libjpeg-turbo 3.2.1. Packaging: Inno Setup, cloudflared 2026.9.3 (hash-pinned).

## Execution flow

1. `native/desktop/main.cpp` enforces a single instance, creates the engine with `od_create` and loads `Main.qml`.
2. The engine thread starts the local host (`network::run`) on the first free port from 8080 to 8099 and, unless disabled, the tunnel (`directory::tunnel`).
3. QML sends JSON commands through `od_command` and receives state through `od_poll`; frames arrive through `od_frame_acquire`.
4. Connecting runs `client::run`: resolve, connect, register, verify identity, request access.
5. On approval the host starts `HostWorker`, and the viewer starts `DecodeWorker` and optionally `Voice`.
6. Ending a session revokes access and stops the workers.
