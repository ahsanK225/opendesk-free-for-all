# Native release acceptance

Completed locally: native Rust/Qt implementation, strict protocol/auth tests, two native endpoints with captured frames and file transfer/revocation, GPU colour/alpha rendering checks, 100%/150% UI review, bounded cooperative/force shutdown, independent portable executable replacement, locked legacy-to-native installation preserving settings/ID, and packaged startup with no SDK PATH or Python runtime. See docs/NATIVE_VALIDATION.md for the final artifact evidence.

Before promoting the preview to a production release:

- Run two physical Windows devices on separate networks and verify both native and browser viewers, approvals/declines, busy state, reconnect and revocation.
- Measure delivered FPS, latency and bandwidth in Balanced, Performance and Sharp profiles across realistic RTT/bandwidth limits. Codec stage timings do not establish internet FPS.
- Check intelligibility with actual microphones/headsets, device unplug/replug, silence transitions and a long voice session.
- Extend GPU/driver, display-change, Windows 10/11 and DPI coverage.
- Obtain an independent security review and decide on trusted publisher signing before claiming those properties.

Future features: monitor selection, service/pre-login operation, negotiated compressed voice/AEC, direct peer transport, application-layer E2E encryption and separately signed update metadata. These are not advertised as implemented.
