# OpenDesk native architecture

The Qt GUI owns window state and presentation. It sends bounded JSON commands to Rust and polls revisioned state; video does not cross the bridge as JSON/base64. Capture, encoding, ordered decode, audio and file IO run on workers.

DXGI captures the primary monitor into a reusable D3D staging surface, with GDI fallback and an initial baseline for idle screens. BGRA pixels stay in Windows-native order. A bounded acknowledgement window preserves JPEG delta dependencies; congestion reduces dimensions/quality and never silently drops an arbitrary dependent delta. The receiver reconstructs in order. Immutable reference-counted frame buffers cross the C ABI with explicit releases and become Qt scene-graph textures.

The built-in relay listens on loopback. A verified owned cloudflared process provides a public HTTPS/WSS tunnel and publishes signed, short-lived device-directory records. Native clients verify a nonce-bound Ed25519 identity and a saved/published key before requesting access. The first unpinned connection asks for fingerprint comparison. Host approval binds to an expiring request; password authentication uses a one-use challenge and PBKDF2/HMAC proof. Session permissions gate input, voice, clipboard and files. Ending a session revokes access and releases held input.

CPAL/WASAPI uses the hardware device rate, streaming resampling, 20 ms mono voice packets, bounded microphone/playback queues and explicit session mute. Default-device changes reopen streams. Echo cancellation is not implemented. File transfers stay inside a selected host root, reject traversal/reparse points and use ordered chunks, size limits, SHA-256 and atomic replacement. Partial files are removed on cancellation.

The Qt desktop has no Python runtime. The Rust maintenance helper can request a graceful shutdown and, after a bounded grace period, terminate only verified OpenDesk processes in the current Windows session. Installed updates run an installer after application exit. Portable updates wait for the app/launcher, verify the staged executable again, retain a rollback copy and atomically replace the launcher. Portable dependencies live in a persistent transactional cache and can be repaired.

HTTPS/WSS protects each tunnel leg; Cloudflare terminates the tunnel. This is not an end-to-end encrypted peer-to-peer transport. The app controls the primary monitor in the logged-in user session; it does not implement a pre-login service, UAC secure-desktop control, multi-monitor selection or AnyDesk's proprietary DeskRT codec.
