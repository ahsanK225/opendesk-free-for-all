# Native release acceptance

Completed locally: native Rust/Qt implementation, strict protocol/auth tests, two native endpoints with captured frames and file transfer/revocation, GPU colour/alpha rendering checks, 100%/150% UI review, bounded cooperative/force shutdown, independent portable executable replacement, locked legacy-to-native installation preserving settings/ID, and packaged startup with no SDK PATH or Python runtime. See docs/NATIVE_VALIDATION.md for the final artifact evidence.

Before promoting the preview to a production release:

- Run two physical Windows devices on separate networks and verify both native and browser viewers, approvals/declines, busy state, reconnect and revocation.
- Measure delivered FPS, latency and bandwidth in Balanced, Performance and Sharp profiles across realistic RTT/bandwidth limits. Codec stage timings do not establish internet FPS.
- Check intelligibility with actual microphones/headsets, device unplug/replug, silence transitions and a long voice session.
- Extend GPU/driver, display-change, Windows 10/11 and DPI coverage.
- Obtain an independent security review and decide on trusted publisher signing before claiming those properties.

Future features: monitor selection, service/pre-login operation, negotiated compressed voice/AEC, direct peer transport, application-layer E2E encryption and separately signed update metadata. These are not advertised as implemented.

# Engineering task tracker

Started 2026-11-04. The acceptance list above is preserved as the release gate. Severity and evidence for bugs are in `PROJECT_CONTEXT.md`.

| ID | Task | Agent | Status | Acceptance / verification |
| --- | --- | --- | --- | --- |
| T-001 | Initialize engineering setup | documentation | Done | All nine agents listed in a new session started in this folder; application code unchanged by this step |
| T-002 | Project audit | project-analysis | Done | Tests in `CHANGELOG.md`; agent NOT RUN, done in the main session |
| T-003 | Protect uncommitted work on a branch | implementation | Done in 2.9 | All uncommitted paths are committed; nothing pushed without approval |
| T-004 | Refuse protocol 1 for a pinned device; stop plaintext password to unverified peers | security, implementation | Done in 2.9 | Regression tests failed before the fix and pass after; agents NOT RUN |
| T-005 | Decide LAN exposure and add a user control | architect, security | Done in 3.0 | Off by default, on only through the setting; encryption limit stated in Settings; real-address test passes |
| T-006 | Build and run Qt app from the uncommitted code | testing-qa | Partly done | `build.ps1` passes for Full and Lite; smoke at 100% in both themes; 150% only in Dark through the incoming check; agent NOT RUN |
| T-007 | Session quality selector shows the active profile | ui-ux, implementation | Done in 2.9 | Selector follows the active profile; not exercised in a live session |
| T-008 | Readable file sizes | implementation | Done in 2.9 | MB and GB formatting added; not exercised with a real transfer |
| T-009 | Reconnect reuses the ended session tab | implementation | Done in 2.9 | Reconnect closes the ended tab first; not exercised in a live session |
| T-010 | Refresh stale documents | documentation | Open | `RELEASE_NOTES.md` and README match the code being released |
| T-011 | Enable CI | testing-qa | Open, needs approval | Workflow enabled; Inno Setup version consistent with the README |
| T-012 | Physical two-device acceptance | release-audit | Open, needs hardware | The release gate list above is completed with recorded evidence |
| T-013 | OpenDesk Lite edition | implementation | Done for size only in 2.9 | Builds, installs and runs separately; 10-13% smaller; idle RAM, CPU and warm start unchanged (`docs/LITE_AND_COMPATIBILITY_VALIDATION.md`) |
| T-014 | Real old-to-new and new-to-old app testing | release-audit | Open, needs hardware | Real older apps, including v2.8, tested both ways between two PCs |
| T-015 | Lite and Full side by side | architect | Open | Lite installer shutdown helper also closes a running Full instance; both share one instance name and `%USERPROFILE%\.opendesk` |
| T-016 | Real microphone and two-PC voice check | release-audit | Open, needs hardware | The PC used for 3.0 has no connected microphone; voice heard on the other PC with a real mic |
| T-017 | Real update from 3.0 to a later release | release-audit | Open | The update window downloads, verifies and installs a real newer release |
| T-018 | ID connection between two PCs on separate networks | release-audit | Open, needs hardware | Tested through the real tunnel on one PC only; connect from a phone hotspot to a PC on another network |
| T-019 | Own directory and relay | architect, security | Open | Directories and the relay are public services without a guarantee; iroh advises against its public relays for production, so hosting `iroh-relay` is the next step for reliability |
| T-020 | Direct path, H.264 and Opus | architect | Done in 3.3 | Works through the real services on one PC; two networks are T-018 |
| T-021 | Hardware H.264 and separate voice stream | architect | Open | Software H.264 runs on the CPU; voice shares one QUIC stream with video, so loss on it delays both |
| T-022 | Windows service and sign-in screen control | architect, security | Open | OpenDesk must be open in a signed-in session, so a locked or restarted PC cannot be reached unattended |
| T-023 | Code signing | release-audit | Open, needs a certificate | Windows and browsers warn about unsigned files |
| T-024 | Multiple monitors | implementation | Open | Only the primary monitor is captured |
| T-025 | Full-screen remote view | ui-ux | Open | The session keeps the sidebar and toolbar on screen |
| T-026 | Send Ctrl+Alt+Del and other system keys | implementation, security | Open | Needs the Windows service in T-022 |
| T-027 | Tray icon and optional run in background | ui-ux | Open | Closing quits, so a PC must keep OpenDesk open to stay reachable |
| T-028 | Verified viewer identity | security | Open | The viewer name and ID in the session notice are reported, not proven |
| T-029 | Presence that cannot be replayed | security | Open | An old signed "online" state could be republished by someone else; it can only make a PC look online |
| T-030 | Screen blinking on an older Intel HD driver | ui-ux | Open, needs that PC | Turning off flip-model presentation made the window white instead, so 3.5 restored it; the cause is still unknown |
