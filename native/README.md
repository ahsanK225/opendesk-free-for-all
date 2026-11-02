# Native migration — work in progress

The shipped desktop remains [v2.0.1](https://github.com/ahsanK225/opendesk-free-for-all/releases/tag/v2.0.1). This directory starts the Rust/Qt migration and is not an executable replacement yet. Python source stays available until native parity is verified.

## Stack and ownership

- Rust owns authorization, networking, capture/encoding, audio, input, clipboard, files, identity and process lifecycle.
- Qt 6 / QML owns presentation and native Windows integration. A small C++ bridge exposes typed commands/state; heavy work never runs on the GUI thread.
- Video uses immutable reference-counted pixel buffers across the bridge and Qt scene graph textures. Control events use a bounded channel; replaceable visual events keep only the latest value. Delta frames must be reconstructed in order before the presentation stage can replace old frames.
- Preserve protocol-v2 compatibility, explicit session permissions, request-bound approval, password challenge authentication and trusted-device key checks.

## Current implementation

The engine contains a strict zero-copy ODV2 envelope decoder, deny-by-default authorization state machine, and bounded acknowledgement/dependency accounting with tests. No native network, capture or audio backend is wired yet. No performance or feature-parity claim is made for this foundation.

```powershell
cargo test --manifest-path native/engine/Cargo.toml
cargo clippy --manifest-path native/engine/Cargo.toml --all-targets -- -D warnings
```

## Replacement gates

1. Build Rust static library and Qt/QML desktop with MSVC 2022 and a pinned Qt 6 SDK; include dependency notices and dynamic Qt deployment.
2. Port and exercise attended/unattended auth, key trust, cancellation, revocation, permission checks, reconnect and shutdown.
3. Implement DXGI capture/GDI fallback, dirty JPEG tiles, ordered reconstruction, adaptive stream pacing and GPU presentation. Measure capture, encode, network and render separately.
4. Wire bounded WASAPI voice with explicit format/rate conversion; preserve clipboard/input reset and home-scoped atomic file transfers.
5. Preserve settings/device identity and installer behavior; run packaged upgrade tests with running old and native processes.
6. Check dark/red UI at several DPI/scales, keyboard navigation and accessibility, and perform two-device WAN/headset acceptance.
7. Only then remove replaced Python runtime/build files, update the root build/docs, and publish the native release.

The existing Python release and preserved Git history provide the reference behavior. A source snapshot of v2.0.1 is also kept outside this repository in the task's release directory. The initial Rust foundation passes 17 unit tests and Clippy with warnings denied on Windows x64 (Rust 1.95.0); those checks do not establish native application feature parity.
