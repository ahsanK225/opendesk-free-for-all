# Native migration validation — archived engineering record

The current stable release is **2.8**. See [current validation](RELEASE_2_8_VALIDATION.md) and [continuous version history](VERSION_HISTORY.md). Original build identifiers below are retained as historical evidence.

The subsequent **3.0.0-alpha.2** input, voice, connection and approval changes are recorded in [ALPHA2_VALIDATION.md](ALPHA2_VALIDATION.md). Results below describe the original alpha.1 baseline.

OpenDesk 3.0.0-alpha.1 replaces the Python runtime/build implementation with a Rust engine, Qt/QML desktop and independent Rust delivery tools. This record describes local Windows checks; it is not a claim of physical two-device WAN/headset acceptance or production certification.

## Regressions addressed

| Earlier problem | Native change and evidence |
|---|---|
| Low FPS and accumulating video latency | BGRA capture buffers, direct SIMD TurboJPEG workers, dependency-preserving acknowledgements, adaptive profiles and GPU textures. Ordered full/delta reconstruction is tested. |
| Blank viewer on an idle desktop | A real GDI baseline is supplied until DXGI emits its first changed frame. The real host/client integration test caught this issue and passed after the fix. |
| Voice rate/pitch/jitter problems | Hardware rates are explicit, resampling preserves duration across chunks, microphone blocks are 20 ms and queues are bounded. WASAPI devices reopen after failure/default-device changes. Actual speech intelligibility remains a hardware acceptance item. |
| Installer stuck closing applications | Separate Rust helper: cooperative fixture closed in 0.46 s; an unresponsive fixture closed in 2.29 s. Whole locked legacy-to-native upgrade completed in 21.08 s, including extraction. |
| Python DLL startup failure | Installed and portable native runtimes contain no Python interpreter/PyInstaller extraction and exclude foreign OS CRT/API-set DLLs. Standalone and installed startup were exercised with only Windows system PATH entries. |
| Portable extraction too slow | Reduced per-file physical disk flushes while flushing executable code and the publication marker. First-launch test dropped from 44.22 s to 13.43 s; missing-DLL/explicit repair from about 49 s to about 13.8 s. |
| Unclear portable loader failures | Missing runtime files trigger transactional re-extraction. Overlong Windows plugin paths are rejected with an actionable shorter-cache instruction; `OPENDESK_RUNTIME_DIR` supports that override. A failing native child reports repair guidance. |
| Stalled network session | Host/client liveness deadlines release a peer after lost communication; unpaired registered sockets have a bounded lifetime. |
| UI overflow and scaling | Native window bounds follow available screen space, compact sidebar, stacked home panels and scrollable/elided session tabs. Home/Settings reviewed at 100% and 150%. |

## Local checks

- **31 Rust engine tests passed**, including real two-App loopback registration/identity verification, attended approval, captured-frame decoding, ordered binary file upload/download, final-hash failure cleanup, traversal/UNC/reparse restrictions, revocation, legacy DPAPI/password migration and browser punctuation/keypad mapping.
- Engine Clippy passed with warnings denied. Native helper tests passed (two process/path tests and update digest validation); helper and portable Clippy checks passed after cleanup.
- Browser protocol/password/audio regression checks passed with Node.
- Actual TurboJPEG encode/decode colour order and alpha, mismatched-dimension rejection and Qt GPU texture presentation passed using the Intel HD Graphics D3D11 backend. The visible renderer test passed at 150% scaling as well.
- Packaged Home/Settings startup passed at 100%/150%, with no unexpected Qt startup warnings. Hidden-window Qt grabWindow captures produced a fractional-DPI offscreen artifact; final 150% visual checks used visible windows and passed.
- Isolated locked-app installer test passed: unresponsive old process closed, recognized `_internal/python311.dll` runtime removed, existing configuration sentinel and nine-digit ID preserved, installed native GUI launched without SDK paths. The test installer used a separate AppId and no desktop integration; its test installation was uninstalled afterward.
- The actual user installation was upgraded from v2.0.2 in **26.59 s**, then launched visibly. Native version, preserved device ID, local host readiness, no Qt startup warnings and removal of the old Python runtime were verified. A normal native OpenDesk window was left running and the local release/installed folders were opened.
- Independent native portable update test passed: waited for the parent, verified/staged replacement, retained the previous executable and launched the replacement.
- Final portable checks passed: first launch **13.43 s**, cached launch **3.55 s**, missing-DLL repair **13.78 s**, explicit repair **13.76 s**, and overlong-path rejection. These timings include the native application's deliberate **2.5-second smoke-test display wait** and process teardown; they are not time-to-first-paint measurements. Device ID remained unchanged across repair.
- Replaced tracked Python runtime/build/test files were removed after native session and installed-package checks. v2.0.1/v2.0.2 Git tags, release assets and preserved source snapshots retain the previous implementation.

## Final media measurement

The [complete report](benchmark-native.json) was captured with compiler/packager activity stopped. The synthetic source is 2560×1440; each profile has 12 full-frame and 24 changed-region samples. Full encode includes resize, JPEG and packet preparation; decode includes reconstruction. Changed-region timing also includes source resize/dirty comparison.

| Profile | Output width cap | Mean full encode | Mean full decode | Mean changed-region encode |
|---|---:|---:|---:|---:|
| Performance | 1280 | 9.13 ms | 5.04 ms | 7.62 ms |
| Balanced | 1600 | 18.56 ms | 8.79 ms | 12.81 ms |
| Sharp | 2560 | 23.10 ms | 24.11 ms | 6.54 ms |

The earlier Qt JPEG/BGRA prototype on this machine measured approximately 20.97/10.28 ms encode/decode for Performance, 33.44/18.56 ms for Balanced, and 44.87/40.71 ms for Sharp. Sharp in the direct TurboJPEG path uses 4:4:4 chroma for text quality, so its output bytes differ. An earlier run concurrent with packaging had a first-sample cold outlier; the full final JSON includes mean, median, p95 and maximum rather than presenting a delivered-FPS estimate.

Capture in the final report contains **one initial GDI baseline** and **59 idle polls excluded**, at 1280×960. That sample does not establish steady DXGI capture throughput. Transport and GPU presentation are excluded from codec timings. **60 FPS is a Performance profile target, not a verified internet result.**

## Distribution and remaining acceptance

Release-mode Rust/MSVC and Qt 6.8.3, direct libjpeg-turbo 3.2.1, pinned cloudflared 2026.9.3 and the Visual C++ Desktop runtime are used. Qt is dynamically linked and replaceable; license texts, dependency copyright notices and Qt SPDX inventories are packaged. Publicly trusted Authenticode signing is not claimed. The GitHub workflow remains a template in `ci/windows.yml`, as authorized; it has not run as an installed workflow.

Before promoting this preview, exercise physical two-device WAN/native/browser sessions and real headset/microphone intelligibility, long-session jitter, device changes and wider GPU/DPI coverage. Independent security review is still open. Primary-monitor user-session control is implemented; pre-login service/UAC secure-desktop control, monitor selection, acoustic echo cancellation and end-to-end peer encryption are not implemented. Cloudflare terminates the tunnel.

Preview artifact URLs and expected SHA-256 values are in [native/version.json](../native/version.json). The root `version.json` keeps the prior stable update channel, so existing stable installations are not silently moved to a preview.
