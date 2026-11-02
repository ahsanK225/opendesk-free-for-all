# OpenDesk 2.0.1 validation

Date: 2026-11-03. Windows 10 x64, Python 3.11.3.

- 104 Python tests passed, including UI dispatch coalescing/budget, native Windows caption controls, render-lock release, process-name scope, PID identity recheck, graceful shutdown and named-event single-instance activation.
- Frozen fixture tests used a separate IPC suffix and an exact workspace process directory. No unrelated running app was targeted.
- Duplicate launch returned as a secondary instance. Graceful helper shutdown completed in 2.01s. A deliberately unresponsive frozen process was force-closed in 3.29s, including its onefile bootloader.
- UI upload microbenchmark: 1280x720, new allocation 79.928ms/frame, reuse 11.674ms/frame. These are local upload-stage timings.
- GUI-only unit tests isolate network workers and explicitly collect destroyed Tk interpreters on the main thread; hardware audio streams remain mocked.

- Packaged application GUI smoke passed: version 2.0.1, one desktop tab, services disabled for isolation.
- Installer upgrade passed in 8.663 seconds with exit code 0. A deliberately unresponsive frozen process held the destination executable open; the helper closed that fixture and the installer replaced the executable. The installed SHA-256 matched the release application. The test used an isolated App ID, exact process-directory scope and separate IPC suffix. Uninstall returned exit code 0.
- Release SHA-256 digests accompany the downloadable artifacts in SHA256SUMS.txt; version.json carries the portable executable digest for update verification.

The release is unsigned. It is not a completed two-device WAN/headset soak test or independent security certification. Automatic CI remains a template because the publishing credential lacks workflow scope.
