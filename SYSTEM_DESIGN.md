# OpenDesk 2 architecture

## Session state

A local relay binds to loopback. Only a host presenting its per-process registration secret may register as a host. Client identifiers are server-assigned and cannot overwrite hosts. Protocol version 2 is mandatory.

An interactive connection creates a random, 60-second request bound to one host/client pair. Only that host can accept/reject the exact request ID. A successful transition issues a random session ID and normalized permissions, then notifies both peers. The host starts only for its own approved request or a configured unattended authentication flow. Both host and relay enforce operation permissions. Session end/socket loss removes both mappings, clears transfers/media and releases input.

Unattended access uses PBKDF2-HMAC-SHA256 with a random salt and a one-use HMAC challenge. Password text is not sent to the relay. Local storage uses user-bound Windows DPAPI. The relay holds the derived password key and is trusted. Device identity uses Ed25519, signed expiring directory records, directory/endpoint key matching and native fingerprint pinning. Initial trust must be verified out of band. This is not an application-layer E2E encryption protocol.

## Video

One dedicated executor owns capture and codec state. DXGI BGRA frames are copied into a reusable GDI DIB for hardware cursor composition; unsupported drivers/sessions fall back to BitBlt. Explicit x64 Win32 signatures avoid handle truncation. A version-scoped DXcam ownership shim prevents duplicate COM releases.

The JPEG codec uses vectorized dirty-block reductions. Binary ODV2 envelopes carry a length-prefixed JSON header and JPEG byte ranges. No base64 image encoding is needed. Full frames establish state; subsequent deltas preserve capture order. A small acknowledgement window (three frames by default, up to ten based on measured RTT) bounds in-flight frames, so dependent updates are never discarded to reduce latency. The browser paints in order and acknowledges after presentation; the native viewer acknowledges after decode and coalesces UI rendering. Video refresh requests force a new full frame.

Profiles set target FPS, maximum width and JPEG quality. Capture cost and queue delay beyond baseline RTT reduce width/quality/FPS, with gradual recovery; actual frame rate depends on hardware and RTT. Quality 80+ uses JPEG 4:4:4 for text. Idle video sends no unchanged frames instead of claiming a synthetic 60 FPS.

## Voice and input

Mono PCM uses explicit sample_rate/channels/format metadata. Native capture uses 20ms 48kHz blocks; browser capture uses AudioWorklet at its actual context rate. Resampling uses metadata, not packet length. Queues/buffers are bounded; VAD has a speech hangover. Browser AEC is native browser processing; native AEC is not implemented. Microphone test audio is local only. VU UI updates are dispatched to Tk's main thread.

Input is allowed only during an authorized session. The host tracks pressed keys/buttons and releases them on focus reset/session end. Capture scaling preserves normalized input mapping to the original screen dimensions. Per-monitor DPI awareness is initialized before Tk.

## Files, updates and lifecycle

Transfers are contained to the host home directory. The file manager resolves paths, rejects traversal/unsafe filenames, validates chunk indices/lengths, supports optional final SHA-256 comparison and replaces completed files atomically. Session cleanup removes partial files. Native/browser clients stream chunks rather than sending a complete file in one message.

The desktop updater requires an official HTTPS release URL plus SHA-256. It stages an external helper, requests main-process shutdown, then replaces/relaunches with bounded waiting. Source checkouts update through Git. The separately tested incremental library validates paths, limits deletion to previously owned files and removes new files during rollback; it is not used to patch a running monolithic EXE.

Tab closure explicitly closes sockets and cancels tasks. App shutdown hides UI, performs bounded cleanup and then exits. The tunnel uses a pinned official binary, retries failed processes with bounded backoff, and kills before closing its reader pipe. Root certificates are not automatically trusted during builds.

## Current boundaries

Primary monitor only; no service/pre-login mode, UAC secure desktop guarantee, WebRTC/UDP transport, native AEC or independent signed update metadata. Tests/build checks are documented in docs/RELEASE_VALIDATION.md. Independent security review and two-machine WAN/voice acceptance remain required for production certification.
