# OpenDesk collaboration and contribution record

OpenDesk began in [ahsanK225/opendesk-free-for-all](https://github.com/ahsanK225/opendesk-free-for-all). Ahsan and earlier contributors retain their original authorship. The MIT license and Git history remain intact.

## Hamza Iqbal — @hamxa8769

- **v3.0.0-alpha.2:** capture-independent remote input, controller cursor visuals, foreground attended approval, prioritized transport lanes, decode/liveness recovery, voice state/device diagnostics, expanded documentation and 30-second bidirectional PCM/video regression coverage. See [validation](ALPHA2_VALIDATION.md).

Role: contributor responsible for the v2 modernization work, including performance, session security, media reliability, and Windows delivery. Implementation was assisted by Codex; engineering claims below refer to the committed implementation and recorded checks.

- **v2.0.0:** DXGI capture integration and GDI fallback, binary JPEG tile transport, bounded video acknowledgements, adaptive quality, explicit voice sample-rate handling and bounded playback; request-bound approvals, host registration secrets, password challenges, device-key verification and session permission checks; constrained atomic file transfer and release integrity checks.
- **v2.0.1:** bounded installer shutdown with verified-process force-close fallback, a separate maintenance helper, Windows named-event single-instance activation, native caption controls, responsive saved sessions, budgeted/coalesced UI dispatch, reusable image uploads and asynchronous audio teardown.
- **v2.0.2:** corrected Windows runtime dependency collection, persistent installed runtime layout, clean frozen-process update/restart environment and packaged self-update regression checks, following a reported installed-startup DLL failure.
- **Native preview:** Rust remote engine, Qt/QML desktop, SIMD JPEG/GPU media path, WASAPI voice, permission-bound native sessions, native file dialogs/transfers, persistent-cache portable launcher and independent Rust installer/update helpers. The previous Python runtime/build files were replaced after local session, startup and installer checks. Two-device WAN/headset acceptance remains open; see [native validation](NATIVE_VALIDATION.md).

Evidence: [v2.0.0 commit](https://github.com/ahsanK225/opendesk-free-for-all/commit/0ad0fb456abdee3c9c6b2714353fd32a60628c38), [v2.0.0 validation](RELEASE_VALIDATION.md), [v2.0.1 validation](RELEASE_VALIDATION_2.0.1.md), and the repository's commit history and regression tests.

## Portfolio links

- [Hamza's linked fork](https://github.com/hamxa8769/opendesk-free-for-all)
- [Public engineering project and roadmap](https://github.com/users/hamxa8769/projects/3)
- [Upstream releases](https://github.com/ahsanK225/opendesk-free-for-all/releases)

Local benchmark numbers are stage timings, not guaranteed internet FPS. Two-device WAN/headset testing, driver coverage, and independent security review remain open validation work. This is a collaborative contribution record, not a claim of sole original authorship or production certification.
