# OpenDesk native architecture

The Qt GUI owns window state and presentation. It sends bounded JSON commands to Rust and polls revisioned state; video does not cross the bridge as JSON/base64. Capture, encoding, ordered decode, audio and file IO run on workers.

DXGI captures the primary monitor into a reusable D3D staging surface, with GDI fallback and an initial baseline for idle screens. BGRA pixels stay in Windows-native order. When both sides support it, `h264.rs` encodes with the H.264 codecs built into Windows; otherwise JPEG tiles are used. A bounded acknowledgement window preserves frame dependencies. `stream.rs` paces frames to the bytes that reached the viewer when delay grows, and lowers quality, then dimensions, only when frames are too large for the link. It never silently drops an arbitrary dependent delta. The receiver reconstructs in order. Immutable reference-counted frame buffers cross the C ABI with explicit releases and become Qt scene-graph textures.

The built-in relay listens on loopback. A verified owned cloudflared process provides a public HTTPS/WSS tunnel and publishes signed, short-lived device-directory records. Records go to free third-party directories: ntfy.sh, two public MQTT brokers (`mqtt.rs`) and, in a compact form, keyvalue.immanuel.co. A record is signed, stays fresh for 2 minutes for viewers up to 3.0, and stays usable for 12 hours for newer viewers, which check that its address answers. Native clients verify a nonce-bound Ed25519 identity and a saved/published key before requesting access. The first unpinned connection asks for fingerprint comparison. Host approval binds to an expiring request; password authentication uses a one-use challenge and PBKDF2/HMAC proof. Session permissions gate input, voice, clipboard and files. Ending a session revokes access and releases held input.

CPAL/WASAPI uses the hardware device rate, streaming resampling, 20 ms mono voice packets, bounded microphone/playback queues and explicit session mute. Default-device changes reopen streams. Echo cancellation is not implemented. File transfers stay inside a selected host root, reject traversal/reparse points and use ordered chunks, size limits, SHA-256 and atomic replacement. Partial files are removed on cancellation.

The Qt desktop has no Python runtime. The Rust maintenance helper can request a graceful shutdown and, after a bounded grace period, terminate only verified OpenDesk processes in the current Windows session. Installed updates run an installer after application exit. Portable updates wait for the app/launcher, verify the staged executable again, retain a rollback copy and atomically replace the launcher. Portable dependencies live in a persistent transactional cache and can be repaired.

Connections try three routes. `p2p.rs` dials the device key with iroh, over direct UDP or a relay that forwards encrypted QUIC packets, and carries the same WebSocket protocol in one QUIC stream. The Cloudflare tunnel is the fallback: HTTPS/WSS protects each tunnel leg, and Cloudflare terminates it, so that route is not end-to-end encrypted. The app controls the primary monitor in the logged-in user session; it does not implement a pre-login service, UAC secure-desktop control, multi-monitor selection or AnyDesk's proprietary DeskRT codec.

## Interfaces

The engine serves one local HTTP server:

| Route | Purpose |
| --- | --- |
| `GET /ws` | WebSocket for protocol messages; 16 connections at most, 2 MiB message limit |
| `GET /health` | App name and supported protocols |
| other paths | Static browser viewer from `web` |

Text messages are JSON of the form `{"type":...,"payload":...}`. Main types: `register`, `identify`, `identity`, `connect`, `auth_challenge`, `connect_resp`, `heartbeat`, `session_end`, input messages, `audio_chunk`, `clipboard_text`, `file_*`, `video_ack`, `video_refresh` and `video_config`. Video travels as binary ODV2 frames decoded strictly by `protocol.rs`. The desktop talks to the engine only through the C ABI in `ffi.rs`.

## Data storage

There is no database. `%USERPROFILE%\.opendesk\config.json` holds settings, saved desktops and trusted device keys, plus the device identity key and unattended password, both protected with DPAPI. Portable runtimes are cached in `%LOCALAPPDATA%\OpenDesk\runtimes` and staged updates in `%LOCALAPPDATA%\OpenDesk\updates`.

## UI design

`Main.qml` holds one window with a sidebar (Home, Saved devices, File transfer, Settings), session tabs and modal dialogs for approval, trust, passwords and legacy mode. `Theme.qml` is the color singleton. Below about 1080 px width the sidebar collapses to icons.

## Uncommitted changes to this design

Recorded on 2026-11-04 from the working tree. These are not committed or released, so the description above and earlier in this document may differ until they are:

- The host always listens on loopback, which the tunnel uses. A second listener opens on the private address of the default route only while the `lanAccess` setting is on (default off). Turning it off closes that listener and any open local network connection, and non-loopback requests are refused. LAN traffic is not encrypted, and the setting is separate from Internet access.
- Protocol 1 peers are supported through `legacy.rs`, without identity verification and without file transfer. A saved device answering as protocol 1 is refused, and passwords are never sent in this mode, so an older desktop with a password cannot be reached.
- The `full` Cargo feature is on by default. Lite builds without it, and `Permissions::for_edition` removes voice and file transfer in the engine, not only in the UI.
- Hosts with a password send protocol 1 peers to attended approval rather than password access.
- DNS failures are retried through DNS over HTTPS with TLS verification of the original hostname (`net.rs`).
- A light theme is available in Settings.
