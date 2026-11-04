# Lite edition and compatibility validation — 2026-11-04

Results from branch `feature/lite-and-compat-fixes`, not pushed or released. Built and run on one Windows 10 PC (8 GB RAM, under memory and disk pressure) from a copy of the tree on another drive.

## Builds

`build.ps1` passed for both editions, including engine tests, the packaged incoming, launcher, update and portable checks, and Inno Setup compilation. `native/test-installer.ps1` passed for both using isolated smoke installers with separate AppIds. The Full build ran before the Lite-only style removal was added to `native/build.ps1`; that branch does not run for Full.

| Check | Full | Lite |
| --- | --- | --- |
| Engine tests | 46 passed, 0 failed, 3 ignored | 45 passed, 0 failed, 3 ignored |
| Clippy `--lib -D warnings` | Passed | Passed |
| Isolated installer test | Passed | Passed |

Also passed: launcher tests, `tests/test_web.cjs`, `tests/test_release_versions.cjs`.

## Lite against Full

| Measure | Full | Lite | Difference |
| --- | --- | --- | --- |
| Installer | 37,362,157 bytes | 33,495,768 bytes | 10.3% smaller |
| Portable | 51,828,736 bytes | 44,810,240 bytes | 13.5% smaller |
| Runtime folder | 138.1 MB, 1,735 files | 121.2 MB, 598 files | 12.2% smaller |
| Idle working set | 81-82 MB | 82 MB | None |
| Idle private memory | 66-67 MB | 67 MB | None |
| Idle CPU over 5 s | 0 s | 0 s | None |
| Warm start to window, 4 runs | 0.58-0.73 s | 0.48-0.70 s | Within run-to-run variation |

Memory, CPU and start were measured on a copy of the Lite runtime with the same styles removed, on the home page with no session. Startup is not shown as an improvement. Memory and CPU in a session were NOT measured. Lite removes voice, file transfer and automatic updates; it does not lower idle use. `bin/cloudflared.exe` is 53 MB of each runtime, so internet hosting is the largest remaining size cost.

First launch of a freshly written bundle on this loaded machine took 11-45 s, against under 1 s when warm. The cause was not isolated.

## Compatibility

| Case | How tested | Result |
| --- | --- | --- |
| New viewer to v1.9 relay, no password | Relay code from the `v1.9` tag on loopback with a scripted host | Connects in compatibility mode after consent |
| New viewer to v1.9 relay with password | Same | Refused; the password is not sent |
| Saved device answering as protocol 1 | Scripted peer | Refused |
| Protocol downgrade after a verified identity | Scripted peer | Refused |
| Older viewer to new host | Scripted protocol 1 client | Reaches attended approval, without files |
| Same version, native to native | Loopback integration test | Stream, transfer and revoke pass (Full) |
| Real older desktop apps, including v2.8, in either direction | | NOT RUN |
| Two physical PCs, separate networks | | NOT RUN, one PC available |

## DNS (error 11002)

Windows error 11002 is `WSATRY_AGAIN`, a temporary resolver failure. `net.rs` retries through DNS over HTTPS, with TLS still verifying the original hostname. An ignored live test resolved a real name through that path and passed. An actual 11002 failure on a user network was not reproduced. `cloudflared` does its own resolving, so hosting through a tunnel still needs working system DNS.

## Interface

Smoke screenshots from built apps were captured without errors for home, settings, audio settings and saved devices in Dark and Light for both editions, plus files for Full. A sample covering both themes and both editions was inspected and looked correct. Lite hides voice, file transfer and update controls. Theme was set through configuration; changing the selector by hand in a running app, and the new session speaker and mic buttons in a live session, were NOT exercised.

## Test harness changes

These packaged checks had failed on this machine. No assertion was removed.

- `native/test-*.ps1` read `ExitCode` as empty under Windows PowerShell, which counted a clean exit as failure. They now cache the process handle.
- `tests/test_incoming.cjs` could read the evidence file before it was written, so it now waits for complete JSON.
- `native/test-incoming.ps1` does a warm-up launch and allows longer deadlines; the smoke evidence delay limit in `main.cpp` rose from 10 s to 30 s.
- `native/test-portable.ps1` allows 240 s per launch. Run alone, its four modes took 26.6, 3.7, 54.4 and 30.7 s; straight after compiling, first launch took about 124 s.
