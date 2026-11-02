# OpenDesk 2.0.0 — Performance and security upgrade

Upgrade both computers to v2. The protocol rejects v1 clients and hosts.

## Sharing and responsiveness

- DXGI Desktop Duplication replaces the default GDI capture path, retaining a GDI fallback for unsupported drivers/sessions.
- Dedicated capture/encode worker keeps video processing off the network/audio event loop.
- Binary JPEG packets remove base64 image expansion. A bounded RTT-aware acknowledgement window preserves delta dependencies and limits backlog.
- Balanced, Performance and Sharp profiles; Performance targets 60 FPS at a lower resolution/quality. Displayed FPS reflects actual rendered frames and idle state.
- Local capture measurement on the validation machine: GDI mean 33.26ms, adaptive DXGI mean 6.56ms. A synthetic keyframe used 25.0% fewer wire bytes. These are local measurements, not guaranteed internet frame rates.

## Voice

- Explicit sample-rate/channel/format metadata fixes the previous browser/native playback-speed mismatch.
- Browser AudioWorklet produces 20ms blocks; native PCM uses 48kHz/20ms blocks.
- Bounded audio queues and buffers, speech-gate hangover, native resampling, thread-safe VU updates and local-only microphone testing.
- Browser echo cancellation uses the browser implementation. Native acoustic echo cancellation is not implemented; use headphones for speaker feedback.

## Session and file safety

- Host registration secret, request-bound approval, host busy checks, expiring requests and immediate disconnect revocation.
- Salted password challenge/proof, attempt limits, centralized host authorization and relay role/permission filtering.
- Ed25519 device identity, native fingerprint pinning, signed expiring discovery records and Windows DPAPI credential migration.
- Native file manager and browser transfers scoped to the host home folder, ordered/length-checked chunks, atomic replacement and optional upload SHA-256 verification.
- Tab/socket cleanup, input release on disconnect/focus loss, graceful tunnel termination/restart and removal of misleading Online/signed/standby-FPS claims.

## Build and maintenance

- Fixed source imports and annotation startup crashes; pinned tested dependencies and supplied Windows version resources.
- Verified full-binary updates, external restart helper, contained incremental paths, ownership-aware deletion and improved rollback.
- Build script, Windows CI template, regression coverage, benchmark tooling and distribution checksums.

## Validation and deployment status

97 Python regression tests and browser protocol/password/audio checks passed locally. Source GUI launch and Windows capture were checked. See docs/RELEASE_VALIDATION.md for packaged build checks.

No trusted publisher certificate was supplied: artifacts are unsigned. Two-device WAN sessions, long-duration real microphone/speaker calls, target GPU coverage and independent security review remain rollout acceptance work. Current capabilities cover the primary monitor; there is no service/pre-login mode, guaranteed UAC secure-desktop control, WebRTC P2P transport or application-layer end-to-end encryption. The tunnel/relay operator remains part of the trust boundary.


Upstream v1.2.3 was merged during final integration. Its buffer reuse/idle codec behavior, LAN parsing tests, mouse coalescing and real RTT probe are retained within the v2 protocol.
