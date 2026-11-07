# OpenDesk mobile plan

Status: **plan only, waiting for approval.** Nothing in this document is implemented. Written 2026-11-07 against OpenDesk 3.7.

## Goal

An OpenDesk app for Android and iOS that reaches any OpenDesk desktop by its ID and shows, controls, talks to and exchanges files with it, with the same approval, password and device-key checks as the Windows viewer.

Out of scope for the first releases:

- **Hosting from the phone.** iOS does not let one app control another, so an iPhone can never be controlled. Android screen sharing would need MediaProjection plus an Accessibility service and is a later, separate project.
- **Controlling a phone from a PC.**
- **Anything the Windows host cannot do today.** Sign-in screen, UAC prompts, Ctrl+Alt+Del and multiple monitors stay open as T-022, T-024 and T-026; the phone inherits those limits.

## What already exists and can be reused

| Part | Today | Reuse on mobile |
| --- | --- | --- |
| Protocol v2 | JSON messages plus binary ODV2 video frames over WebSocket or one iroh QUIC stream | Unchanged. The phone is one more viewer. |
| Engine C ABI (`ffi.rs`) | `od_create`, `od_command`, `od_poll`, `od_frame_acquire` / `od_frame_release` | The same JSON command/state contract can drive a Kotlin, Swift, Qt or Flutter UI. |
| Viewer logic | `client.rs`, `stream.rs`, `protocol.rs`, `directory.rs`, `p2p.rs`, `mqtt.rs`, `files.rs` (viewer half), `audio.rs` | Portable Rust, apart from the Windows calls listed below. |
| Codec negotiation | The viewer lists `codecs` in `video_config`; without `h264` the host sends JPEG tiles | A first phone build can ship JPEG tiles only and still work with every 3.x host. |
| Browser viewer (`web/`) | Served by the host at its share URL | Usable on a phone browser today, but only through the Cloudflare tunnel, which is not end-to-end encrypted, and with desktop-style input. |

Windows-only code that a mobile build must leave out or replace:

| Module | Windows dependency | Mobile replacement |
| --- | --- | --- |
| `capture.rs`, `platform.rs` input, `media.rs` host loop | DXGI, GDI, SendInput | Not needed: the phone does not host. |
| `h264.rs` | Media Foundation | Android `MediaCodec`, iOS `VideoToolbox` (phase 3) |
| `jpeg.rs` | libjpeg-turbo loaded by the desktop | libjpeg-turbo builds for both platforms, or `zune-jpeg` in pure Rust |
| `store.rs` | DPAPI protects the device key and password | Android Keystore, iOS Keychain |
| `files.rs` | `MoveFileExW`, WIC thumbnails (host half) | `std::fs::rename` in the app sandbox; the host half is not needed |
| `updater.rs`, launcher | Windows installer and portable updates | App stores update the app |
| `audio.rs` | CPAL with WASAPI | CPAL supports AAudio/Oboe and CoreAudio; Opus via `audiopus` builds for both |

## Architecture

```
 ┌──────────── Phone app ────────────┐
 │ UI (screens, gestures, keyboard)  │
 │        │ JSON commands / state    │
 │        ▼                          │
 │ opendesk-core (Rust, staticlib)   │──── iroh QUIC (direct or relay) ───┐
 │  client, stream, protocol,        │──── WSS through the tunnel ────────┤
 │  directory, presence, files,      │                                     ▼
 │  audio, identity                  │                         OpenDesk desktop host
 │        │ decoded RGBA frames      │
 │        ▼                          │
 │ GPU texture view                  │
 └───────────────────────────────────┘
```

1. **Split the engine.** Move the portable modules into a `native/core` crate with a `viewer` feature. The Windows engine depends on it and adds the host modules behind `cfg(windows)`. The desktop build and its tests must stay unchanged; that is the first acceptance check.
2. **One C ABI for every platform.** `ffi.rs` already exposes everything a viewer needs. Android calls it through a small JNI shim; iOS calls it directly from Swift as a C module. Frames stay zero-copy: the UI acquires a frame buffer, uploads it to a texture and releases it, as `FrameItem` does today.
3. **Identity.** Each phone gets its own ed25519 device key, stored in the Keystore or Keychain and never exported. Host keys are pinned on first use, exactly as on Windows, and the fingerprint dialog is shown.

### UI technology

| Option | For | Against |
| --- | --- | --- |
| **Qt Quick 6.8 for Android and iOS** (recommended for Android first) | Reuses `FrameItem`, the QML components, `Theme.qml` and the build knowledge; Android builds on this Windows PC | Phone screens need a new layout, not `Main.qml`; Qt on iOS links statically, which brings LGPL relinking duties or a commercial licence |
| Flutter with `flutter_rust_bridge` | One modern touch UI for both stores, permissive licence | New language and toolchain; frames go through a platform texture bridge |
| Kotlin (Compose) and SwiftUI | Best platform feel and store review experience | Two UIs to write and keep in step |

Recommendation: decide this at the end of phase 0 with a one-day prototype that shows a live remote screen at 30 FPS on a real Android phone. If Qt meets that bar, use Qt for Android and decide iOS separately once the licence question is answered.

## Phone experience

- **Home:** enter an ID or share link, the access password if one is set, and the saved and recent desktops with live online state from the presence service.
- **Session screen:** the remote screen fills the phone, landscape by default. A thin bar slides in from the top with keyboard, special keys, quality, voice, files and disconnect, and hides itself after 3 seconds.
- **Two control modes, switchable in the bar:**
  - **Touch mode:** a tap clicks where the finger is.
  - **Trackpad mode:** the screen is a touchpad that moves a visible cursor. It is precise for small targets.
- **Gestures:**

  | Gesture | Action |
  | --- | --- |
  | Tap | Left click |
  | Double tap | Double click |
  | Long press, or two-finger tap | Right click |
  | Long press, then drag | Drag and drop |
  | Two-finger drag | Scroll |
  | Pinch | Zoom the local view; the host is not touched |
  | Three-finger tap | Show or hide the bar |

- **Keyboard:** the system keyboard types text. A key row offers Esc, Tab, Ctrl, Alt, Shift and Win as sticky modifiers, plus arrows, F1–F12, Delete and common shortcuts such as Ctrl+C, Ctrl+V, Alt+Tab and Win+D. Ctrl+Alt+Del needs T-026.
- **Picture:** the phone asks for the width of its own screen in pixels (`video_profile` with `maxWidth`), which saves mobile data. A data saver switch picks the Performance profile on mobile networks.
- **Voice:** push-to-talk or open microphone, using the phone microphone and speaker. Bluetooth headsets follow the system route.
- **Files:** the file page from 3.7, with the system file picker for upload. Downloads land in the app's folder and can be shared to other apps. Picture thumbnails work unchanged.
- **Clipboard:** a **Send clipboard** and **Get clipboard** pair instead of silent sync, because iOS warns on every background paste.
- **Privacy:** the session screen is hidden from screenshots and the app switcher (`FLAG_SECURE` on Android, a blur on iOS). The host's session dot still appears on the PC.

## Platform limits to design around

- **Background:** iOS suspends an app within seconds of leaving the foreground, and Android can do the same. A session lives while the app is visible. Android can keep it briefly with a foreground service and a notification; iOS cannot. Reconnecting must be quick and keep the zoom and position.
- **Networks:** iroh direct UDP often fails on mobile carrier NAT, so the relay path matters more. Hosting our own `iroh-relay` (T-019) becomes important before a public phone release.
- **Battery and heat:** limit to 30 FPS by default and stop decoding when the screen is off.
- **Builds and stores:**
  - **Android:** builds on this Windows PC with the NDK. A signed APK can be sideloaded right away. The Play Store needs a developer account, a privacy policy and the data-safety form.
  - **iOS:** builds need a Mac with Xcode and an Apple Developer account. TestFlight comes before the App Store. App Review asks how remote control is approved, which the approval dialog on the host answers.

## Phases

| Phase | Work | Done when |
| --- | --- | --- |
| 0. Groundwork (1–2 weeks) | Split `native/core`; build it for `aarch64-linux-android` and `aarch64-apple-ios`; UI technology prototype | Windows tests and builds unchanged; core unit tests pass on an Android emulator; prototype shows a live screen |
| 1. Android viewer MVP (3–4 weeks) | Home, connect by ID and password, fingerprint trust, JPEG tiles, touch and trackpad modes, keyboard and key row, quality, disconnect | Controls a real PC on another network from a real phone, through both the direct path and the tunnel; approval and revocation behave as on Windows |
| 2. Daily use (2–3 weeks) | Saved devices and presence, voice, files, clipboard, reconnect, data saver, privacy screen | Each item checked on a real phone against a 3.7 host, with results recorded in `docs/` |
| 3. Smooth picture (2 weeks) | H.264 decoding through MediaCodec, advertised as the `h264` codec | Measured FPS, latency and data use recorded on Wi-Fi and 4G; no claims beyond the measurements |
| 4. iOS (3–4 weeks, needs a Mac) | Same core with a Keychain store, VideoToolbox, iOS UI and gestures, TestFlight | Same acceptance as phases 1 and 2 on a real iPhone |
| 5. Store release | Signing, store listings, privacy policy, security review of the phone side | Independent review findings closed; published only with your approval |

Estimates are for one developer and assume no changes to the desktop protocol. Phase 0 can change them.

## Tests

- Rust unit tests for the core on Windows and in the Android emulator in CI.
- Protocol tests: a phone viewer against the 3.7 host, and against the oldest supported 3.x host with JPEG tiles.
- A gesture table test: each gesture produces the expected input messages.
- Real-device checks for every phase, recorded with phone model, OS version, network type and measured numbers.

## Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Public iroh relays and directories have no guarantee | Phones on carrier NAT fail to connect | Host our own relay and directory (T-019) before the public release |
| Qt licence on iOS | Licence duties or cost | Decide before phase 4; SwiftUI over the same C ABI is the fallback |
| Phone keyboards send text, not key codes | Shortcuts and games behave differently | The host already accepts the `key` text with `vk`; add a text-input message if testing shows gaps |
| Store review of remote-control apps | Delay | Show that every session is approved on the host and visibly marked by the session dot |

## Approval needed

1. Go-ahead to start phase 0.
2. UI technology after the prototype.
3. Whether an iOS build is wanted, which needs a Mac and an Apple Developer account.
4. Publishing to the Play Store and App Store, which also needs the developer accounts.
