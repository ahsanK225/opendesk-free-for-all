# Changelog

## 2.8 stable — 2026-11-03

- Adopted the approved continuous public version sequence from 1.0 through 2.8, with no missing release numbers.
- Aligned application, Windows file metadata, installer, portable launcher, live update manifests and GitHub Latest releases.
- Preserved original source tags, archived executable bytes and full original-to-new history in docs/VERSION_HISTORY.md.
- Synchronized current binaries and historical release pages across the original repository and portfolio fork.
- Added two-component version parsing and stable upgrade comparison coverage. All latest native input, voice and foreground approval fixes are included.

## Archived implementation notes

The entries below retain the original build names for engineering provenance. Public release numbering is listed in [VERSION_HISTORY.md](docs/VERSION_HISTORY.md).

## 3.0.0-alpha.2 — 2026-11-03

- Process authorized input independently of capture/encoding and coalesce viewer mouse movement; flush motion before clicks/scrolling and show separate controller cursor visuals on both desktops.
- Restore a minimized host for incoming approval, keep it topmost while unanswered, flash the taskbar when Windows restricts focus, and restore normal stacking after resolution. Reset permissions for every request.
- Give control, voice, files and video independent bounded outgoing lanes, preserving file-message order. A busy capture/file queue no longer ends an otherwise healthy session.
- Recover from decoder overload with a fresh keyframe without blocking voice/heartbeat reads; explicitly answer pings, count ping/pong traffic as liveness and allow a bounded 30-second network write deadline.
- Preserve session microphone intent when unrelated settings change, retry unavailable microphones, remove the fixed quiet-speech gate and expose device readiness/errors and sent/received audio packet counts.
- Add aligned version badges, a reconnect action requiring fresh authorization, and comprehensive installation, voice, architecture, update and troubleshooting documentation.
- Add priority/ordering regressions and a 30-second bidirectional PCM/video session test. Physical two-device WAN/headset acceptance remains open; no fixed internet FPS/latency is promised.

## 3.0.0-alpha.1 native preview — 2026-11-03

- Replaced Python runtime/build code with a Rust engine and Qt/QML desktop, retaining the dark/red identity and adopting the Portal O icon.
- Added DXGI/GDI capture, an idle-screen baseline, BGRA buffers, direct SIMD TurboJPEG workers and GPU texture presentation.
- Ported device-key trust/DPAPI identity, session authorization, WASAPI voice, input/clipboard, selected-folder atomic transfers and tunnel/directory supervision.
- Added standalone Rust installer/update helpers, transactional persistent-cache portable delivery, repair support and verified independent updates.
- Added responsive high-DPI layouts, microphone state/gain, native file dialogs, saved desktops, sharing controls and update UI.
- Preserved v2 releases/history and contributor attribution. Two-device WAN/headset acceptance remains open.

## 2.0.2 — 2026-11-03

- Excluded foreign OS CRT/API-set DLLs from Windows 10+ packages and restricted the build DLL search path.
- Switched the installed application to a persistent runtime bundle; retained the standalone onefile portable download.
- Cleared inherited frozen-process extraction state during independent update restarts.
- Installed bundles select the installer and its own SHA-256 instead of overwriting their launcher with a portable executable.
- Removed incorrect hard-coded Authenticode-signed claims from the UI.

## 2.0.1 — 2026-11-03

- Replaced Restart Manager closing-applications waits with a small bounded shutdown helper and verified PID force-close fallback.
- Added single-instance activation and early maintenance launch without GUI/media imports.
- Restored native Windows caption/resize controls, responsive cached cards and bounded visual callback dispatch.
- Reused Tk image storage, shortened image snapshot locks and moved audio lifecycle work off the GUI thread.
- Added launcher/installer regression coverage and isolated hung-process upgrade validation.


## 2.0.0 — 2026-11-03

Breaking protocol upgrade. Both host and viewer must run v2.

- Replaced permissive relay pairing with explicit request, approval, start and revocation states.
- Added host registration secret, challenge-based unattended authentication, rate limits, request expiry, busy-session rejection and host-side authorization.
- Added persistent device keys, native fingerprint pinning, signed expiring discovery records and DPAPI credential migration.
- Added DXGI capture with cursor composition/GDI fallback, binary video frames, dependency-safe flow control, worker-based capture/encoding and streaming profiles.
- Fixed browser/native voice sample rates, broken browser audio syntax, audio backlog and speech-gate clipping.
- Added native file manager; constrained host transfers and validated chunk ordering, size and optional digest.
- Fixed session/tab cleanup, modifier release, shutdown coordination, package imports and import-time annotation errors.
- Hardened full/incremental update paths and rollback; replaced worker-thread self-exit with main-process shutdown plus external update helper.
- Added reproducible dependencies, Windows version resources, build scripts, regression coverage and CI.
- Replaced unmeasured performance/security claims and hardcoded Online/60 FPS displays with documented capabilities and real state.

Earlier history remains available in Git tags/commits.
