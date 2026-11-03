# OpenDesk 3.0.0-alpha.2 validation — 2026-11-03

This update addresses input/media contention, voice state and foreground approval in the native preview. It does not certify physical two-device WAN or headset performance.

## Automated engine checks

- 33 release-mode Rust engine tests passed, with no failures (32.65 seconds of execution, excluding compilation).
- The real two-App loopback test verifies registration, device trust, attended approval, desktop-frame decoding, atomic file upload/download and permission revocation.
- The same test now keeps a session active for 30 seconds while requesting video keyframes and sending synthetic 48 kHz mono PCM in both directions. Each receiver must report at least 200 valid voice packets. Fixture microphones remain muted and speaker volume disabled; this is transport/playback-buffer validation, not a microphone recording or speech intelligibility test.
- New queue tests saturate video/file capacity and verify control/voice delivery remains available and prioritized. A second regression verifies file start/chunk/completion ordering across priority lanes.
- Browser protocol, password and audio regression checks passed with Node.

## Changes linked to the reported failures

| Failure | Change |
| --- | --- |
| Mouse latency and queue-triggered session loss | Authorized mouse/key input bypasses the capture queue. Viewer movement is coalesced and flushed before ordered actions. Capture queue saturation no longer tears down a session. |
| Voice stops under screen-sharing load | Voice has independent outgoing capacity, incoming host voice bypasses capture, and quiet microphone blocks are transmitted without a fixed noise gate. |
| Mic silently muted after settings changes | Applying gain/volume/other settings preserves session mute intent; only the microphone default setting explicitly reapplies it. |
| Device says enabled despite an error | Requested state and actual stream readiness/errors are separate; failed default devices are retried. |
| Socket reader blocked by video decode | Decoder overflow discards the dependent chain and requests a full frame without waiting for queue space. |
| Healthy but slow socket closed early | Bounded write deadline increased from 5 to 30 seconds; text, ping and pong traffic count as liveness. |
| Approval hidden behind other apps | Each request opens the dialog, restores a minimized host and temporarily makes the window topmost. Resolution restores the previous topmost state. |

## Packaged Windows checks

- Engine Clippy passed with warnings denied. Native Qt/C++/Rust release builds and Inno installer compilation completed.
- A real protocol-v2 request restored the minimized packaged host at 150% scaling: `foreground=true`, `minimized=false`, `topmost=true`. After a peer cancelled its request at 100% scaling: `minimized=false`, `topmost=false`. The permission dialog screenshot was visually reviewed; controls and Allow/Reject actions fit.
- The final probe cancels its first request, then submits a second request to the same running host. The second request also restores/presents correctly. Startup additionally inspects an already-received request after QML initialization so an early engine notification cannot be missed. The test discovers the fixture's process-owned listening port to avoid shutdown/rebind races between isolated runs.
- Packaged Home at 100% scaling was visually reviewed, including the aligned `v3.0.0-alpha.2` badge. The actual JPEG/D3D11 presentation self-test passed at 150% scaling.
- Portable first launch: **13.53 s**; cached launch: **4.63 s**; missing-DLL repair: **17.12 s**; explicit repair: **16.32 s**. These include a deliberate 2.5-second smoke display wait and teardown, not time to first paint. Identity stayed the same through all repairs; the invalid-cache-path diagnostic passed.
- The actual per-user installation upgraded from alpha.1 to alpha.2 in **18.13 s**, closing the running older application. Installed startup passed with Windows-only PATH, local relay readiness, unchanged device ID and saved desktops, and no old Python runtime. Its startup stderr was empty.
- After the startup-notification fix, the final rebuilt installer replaced a running alpha.2 instance in **12.90 s**. The installed executable's SHA-256 exactly matched the final staging executable. Final installed startup again passed with unchanged identity/saved desktops and empty stderr. The updated app was left visibly running and both release/installed folders were opened.
- Some isolated GUI starts emitted the exact transient Qt message `qt.qpa.mime: Retrying to obtain clipboard.`. This clipboard-contention diagnostic is retained in logs and excluded from unexpected-warning failures; other warnings still fail the scripts.

## Remaining hardware acceptance

Two physical Windows computers, separate internet connections, headset speech intelligibility, microphone hotplug/Windows privacy denial and driver coverage remain hardware acceptance tasks. A single WebSocket can still experience head-of-line delay during a slow write. No internet FPS or 1–2-second control guarantee is inferred from loopback tests. The transport is WebSocket/WSS, not WebRTC/ICE.
