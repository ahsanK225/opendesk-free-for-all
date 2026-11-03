# OpenDesk 2.8 stable release validation

Date: 2026-11-03. Public versions advance by 0.1, from 1.0 through 2.8; the next release is 2.9. Rust uses the equivalent package version 2.8.0 and Windows uses numeric file version 2.8.0.0.

## Version and update checks

- 34 release-mode native engine tests passed with no failures, including numeric comparison of two- and three-component versions, update URL restrictions and downgrade rejection. Execution took 33.56 seconds, excluding compilation.
- The real local host/viewer regression includes 30 seconds of video refresh and bidirectional synthetic PCM reception, file transfer and permission revocation.
- Warnings-denied Rust Clippy passed.
- Browser protocol/password/audio regressions passed.
- The release metadata check verifies all 19 consecutive version entries, unique tags, unchanged original source commits, matching root/native manifests, Cargo normalization, stable URLs and current documentation.
- CMake generates application and Windows version resources from the release manifest. Generated strings are 2.8, numeric resources are 2.8.0.0 and FILEFLAGS is zero (no prerelease flag).
- The original 2.0.2 Python updater was inspected: its numeric parser pads missing patch components, so 2.8 compares greater than 2.0.2. Already-installed 3.0.0-alpha clients require the 2.8 installer once because their existing comparator rejects the lower new sequence number.

## Packaged Windows checks

- The final foreground probe passed twice: each cycle cancels a first request, receives a second fresh request, restores the minimized host and verifies topmost state; cancellation clears topmost. Native restoration is rechecked while a request is pending, including delayed Windows minimize/restore events.
- Portable first launch **15.56 s**, cached launch **3.64 s**, missing-DLL repair **14.92 s**, explicit repair **17.14 s**. Timings include a deliberate 2.5-second smoke display wait and teardown. Identity stayed unchanged; long-cache-path rejection passed.
- The actual installed 3.0.0-alpha.2 application migrated to **2.8** in **20.06 s**. Installer exit was zero; installed EXE hash matched the final runtime. ProductVersion and FileVersion were both 2.8, and IsPreRelease was false.
- Actual installed startup passed with Windows-only PATH, local host readiness, unchanged identity/saved devices and empty stderr. The 150% DPI JPEG/GPU presentation self-test passed.

## Archived release integrity

The [ascending history](VERSION_HISTORY.md) and [source mapping](RELEASE_MAPPING.json) record every original tag and source commit. Existing historical assets retain their IDs, sizes and digests in the original repository when their release-associated tags are changed. The fork's historical pages link directly to those preserved binaries; its existing native archived assets remain attached. New stable installer/portable assets are uploaded to both repositories.

The two previously source-only tags receive source-history entries, without invented executable downloads. Original Git tags are retained alongside the new consecutive release tags.

## Scope

This release aligns stable delivery and numbering while retaining the latest native input, voice, cursor and foreground approval changes. Physical two-device WAN/headset coverage and known platform limits remain documented in [the preceding media validation](ALPHA2_VALIDATION.md) and the README. Stable publication does not add unmeasured FPS or latency guarantees.
