# OpenDesk 2.0.1 — Reliable installation and smoother native UI

This maintenance release fixes the installer stopping at "closing applications".

- A small standalone helper requests graceful shutdown, then force-closes verified OpenDesk processes in the current Windows session after a bounded grace period. It handles older versions without the new shutdown protocol and onefile parent/child processes.
- Windows Restart Manager's automatic close/restart wait is disabled. The helper returns an actionable error if an elevated process cannot be closed; setup does not delete user settings or device identity.
- Single-instance launch activates the current window. App shutdown starts an independent watchdog before driver cleanup; audio open/close does not block the GUI.
- Native Windows caption/resize/snap controls replace the custom titlebar controls. Recent cards reflow on resize and skip unchanged rebuilds.
- Main-thread work is budgeted; stale VU/frame updates are coalesced. Image resizing/Tcl uploads run after releasing the shared frame lock; stable-size Tk images are reused.

104 Python tests passed. The frozen launcher rejected a duplicate instance, exited gracefully in 2.01 seconds, and force-closed a deliberately unresponsive test process in 3.29 seconds. Installer upgrade and final artifact checks are recorded in docs/RELEASE_VALIDATION_2.0.1.md.

A local 1280x720 Tk upload microbenchmark measured 79.928ms/frame for new image allocation versus 11.674ms for reuse. This is a local upload-stage measurement, not guaranteed end-to-end internet FPS.

Both computers should use protocol-v2 builds; 2.0.0 and 2.0.1 share that protocol. Artifacts are unsigned. Real WAN/headset acceptance and an independent security assessment remain outstanding. This hotfix retains Python/Tk; a native Rust/C++ engine or Qt migration is separate work.
