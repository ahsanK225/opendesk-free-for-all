# Release acceptance work

Completed in v2: source startup fixes, request-bound authorization, permission enforcement, disconnect revocation, DXGI capture, binary dependency-safe video, explicit voice rates, native file transfers, scoped paths, identity pinning/discovery signatures, DPAPI storage, updater verification, lifecycle cleanup, tests and Windows packaging.

Before production certification:

- Run two physical devices on separate networks; verify approval/decline, host busy, disconnect/reconnect and both viewer types.
- Measure end-to-end FPS/latency/bandwidth across the three profiles and multiple RTT/bandwidth scenarios.
- Assess real headset/microphone intelligibility, device changes, PTT, silence transitions and long-session jitter.
- Exercise target GPUs, display changes, locked desktops and Windows 10/11 DPI combinations.
- Perform an independent security review of authentication, discovery, transport trust and update distribution.
- Supply a trusted publisher signing certificate for signed release artifacts.

Future features: monitor selection, service/pre-login support, a negotiated compressed voice codec with native AEC, direct peer transport, application-layer E2E encryption and independently signed release metadata.
