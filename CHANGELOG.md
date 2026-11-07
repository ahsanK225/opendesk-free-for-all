# Changelog

## 3.7 stable — 2026-11-07

- **Screen drawing setting against blinking.** On the PC with Intel HD Graphics and a 2015 driver, the screen blinked while OpenDesk was in front and the mouse moved. OpenDesk draws with Direct3D 11 flip-model presentation, which display drivers made for Windows 8.1 and older (WDDM 1.x) handle badly; most other apps draw differently. **Settings → Appearance → Screen drawing** now offers Automatic, Direct3D, OpenGL and Software, taking effect at the next start. Automatic picks OpenGL when the main display adapter has such a driver and OpenGL works, and Direct3D otherwise. On that PC OpenGL loads Intel's own OpenGL driver and draws the window correctly. Whether the blinking stops was not observed, because a blink does not show in screen captures.
- **Notices close by themselves.** Error and status notices at the bottom of the window stayed until clicked. Errors now leave after 8 seconds and other notices after 4, later while the pointer rests on them; a click still closes them at once.
- **Full screen.** The new button in the session toolbar makes the running session fill the whole screen, without the sidebar, tabs or toolbar. **Esc** leaves full screen; while in full screen, Esc is not sent to the remote desktop. Moving the mouse to the top edge shows a bar with **Exit full screen** and **Disconnect**.
- **Always allow a device.** The approval window can remember a device: **Always allow this device without asking, with these permissions**. That device then connects without approval and gets exactly those permissions; other devices are still asked. The device must prove its key: with its identity answer the host now sends a one-time challenge, and the viewer signs it together with the host key, so a proof is worthless for a later connection or another host. The option only appears for viewers from 3.7 on that sent a valid proof. **Settings → Connection & privacy → Devices allowed without asking** lists these devices with their key fingerprint and permissions, and **Remove** makes a device ask again. The ID and name shown are still what the viewer reports; the key is what is checked.

- **Update button in the sidebar.** When a new version is ready, the sidebar shows an **Update to** button with the new version above the status card, so an update stays one click away after the update window is closed with Later. With no session open it downloads and installs straight away; with a session open it opens the update window first, which says that installing closes sessions. While an update downloads, the button shows its progress.
- **Zoom no longer changes by itself.** Zoom counted remote pixels of the current picture, and the host lowers and raises the picture width as the connection changes. A zoomed picture therefore grew and shrank on its own. Zoom now counts pixels of the widest picture the session has sent, so the size on screen holds when the host changes resolution.
- **Run as administrator no longer ends the session.** A UAC prompt moves Windows to the secure desktop, which no ordinary program can capture. The capture error ended the host session. The host now keeps the session and the last picture, and resumes as soon as the normal desktop returns, retrying every second instead of every five. Windows still blocks a non-elevated OpenDesk from typing into or clicking an elevated window, and the viewer cannot answer the UAC prompt itself; both need OpenDesk to run with administrator rights, which is not implemented.
- **A session dot instead of the edge glow.** While a session is approved, a small red dot like a camera light sits at the top centre of the main screen. Drag it anywhere; double-click it to bring OpenDesk forward. It stays on top without taking focus and is left out of screen capture, so the viewer does not see it. **Settings → Connection & privacy → Session dot** turns it off.
- **File transfer upgrade.** **Send files** picks several files at once, **Send folder** sends a whole folder with its subfolders, and files and folders can be dropped from Explorer onto the page. Click to select, Ctrl+click to add to the selection, **Select all**, and **Download** saves one file where you choose or several items, including folders, into a folder you pick, without replacing existing files. Double-click opens a folder or downloads a file. The page lists the shared folder as soon as it opens, shows a list with dates and sizes or a thumbnail grid, and shows previews of pictures. The host makes previews with the Windows imaging codecs, at most 160 pixels and only for pictures up to 48 MB inside the shared folder. Every file is still checked with SHA-256, and a batch shows which file of how many is moving. Sending folders and previews need the remote desktop to run 3.7; downloading folders works with older hosts.

## 3.6 stable — 2026-11-06

- **Screen edge glow instead of the session panel.** The panel at the right edge of the screen got in the way. While a session is approved, a soft green glow now runs along the edges of the main screen. It is made of a few plain windows in bands that fade inwards, never redraws, lets clicks through and is left out of screen capture, so the viewer does not see it. **Settings → Connection & privacy → Screen edge glow** turns it off. The bar at the bottom of the OpenDesk window still names the viewer, shows how long they have been connected and ends the session.
- **Screen size works.** The size list only changed the width of the picture the other PC sends. With the picture fitted to the window, or a remote screen narrower than the chosen width, nothing visible changed. The list now chooses **Fit to window** or **Original size**, and shows the zoom level otherwise. A fitted picture is requested at the width of the window, which sharpens it on large windows and saves bandwidth on small ones. A zoomed or original-size picture is requested at full resolution. The zoom and size tools moved from over the picture into the session toolbar, so they no longer cover the remote screen, and the separate Fit and 1:1 buttons are gone because the list does the same.

## 3.5 stable — 2026-11-06

- **White window fixed.** The 3.4 change against screen blinking turned off flip-model presentation, and on an Intel HD Graphics PC with an older driver the window then stayed white while the app ran. 3.5 restores flip-model presentation. The screen blinking reported on that PC is not fixed.
- **Zoom and size.** Each session has Fit, zoom in and out, and actual size, with Ctrl + mouse wheel zooming around the pointer. Scroll bars and the mouse wheel move a zoomed picture when you are only viewing. The size list sets the width of the picture the other PC sends, through a setting every version already understands.
- **Session notice.** While a session is approved, a small panel stays on top at the right edge of the screen. It says whether the other side is viewing or controlling, names the viewer, lists what was allowed and has an End session button. It can be dragged and does not animate.
- **Who is connecting.** Viewers from 3.5 on send their PC name and ID, shown in the approval window and the notice. This is what the viewer reports, not proof of identity. Older viewers are shown as "An OpenDesk viewer".
- **Online status.** Saved desktops show Online, Offline or when they were last seen, and online ones are listed first. A 3.5 host keeps a signed, retained state on two public MQTT brokers over a link that stays open, with a will message: the broker marks the host offline as soon as the app closes, and within about 45 seconds when the PC or its network drops. Hosts from 3.3 and 3.4 show "Seen N min ago" from their 5-minute directory record, and older hosts show no status. A PC with Internet access off shows as offline.

## 3.4 stable — 2026-11-05

- **Closing the app ends everything.** The remote pointer window kept the app alive after the main window closed, so a session continued in the background. Closing now quits, ends the session, and stops the tunnel helper through a Windows job, even if the app is killed.
- **Unattended access is its own option, off by default.** With it off, every incoming connection needs approval, even with the right password. **A PC that relied on its password must have the option turned on in Settings after updating.**
- **Saved desktops.** Add, rename, change the ID, delete with a confirmation, search and copy the ID. Favorites stay when the list is full.
- **Screen blinking.** The app no longer uses flip-model presentation, the likely cause of the whole screen blinking on older display drivers. Set `QT_D3D_NO_FLIP=0` to restore it. This was not reproduced here, because a blink cannot be seen from a screen capture.

## 3.3 stable — 2026-11-05

Tested on one PC, with traffic going out through the real services. Two PCs on separate networks were not tested. Results are in [VALIDATION_3_3.md](docs/VALIDATION_3_3.md).

- **Direct connections.** Viewers dial the device key with iroh: UDP with hole punching, a public relay when that fails, and the Cloudflare tunnel after that. Hosts up to 3.2 are still reached by their tunnel, and viewers up to 3.2 still use the tunnel of a 3.3 host.
- **H.264 video** through the codecs built into Windows, used when both sides have it. JPEG tiles remain for older peers, the browser viewer and any codec failure.
- **Opus voice** at 24 kbit/s when both sides have it. Uncompressed 16 kHz voice remains for older peers.
- **More ID directories.** Records also go to two public MQTT brokers as retained messages, which have no daily limit like the first directory. A record works without a tunnel address, so a PC whose tunnel is down can still be found.
- **Interface.** A black and red theme with sharper corners, and each session shows its route: Direct, Relay, Cloudflare or Local network.

## 3.2 stable — 2026-11-05

Fix for a failure seen between two real PCs: a friend could not reach a laptop by ID during a session the other way round.

- A record from a PC whose clock was more than 3 minutes ahead was thrown away, so the viewer only saw old records and said the desktop was last online hours ago. Records are signed and the address still has to prove its key, so clocks up to a day apart are now accepted.
- Updating from inside the app failed on every installed copy: the helper passed the install folder in the `\\?\C:\...` form, and the installer refused it. The folder is now passed in its plain form. The helper runs from the version being replaced, so 3.0 and 3.1 cannot update themselves, and 3.2 has to be installed by hand once.
- After a failed update OpenDesk opens again and shows what went wrong, in place of a separate error box. Leftover update files are removed.
- Directory reads wait up to 15 seconds, because the second directory can take over 10 seconds to answer.
- PCs behind one internet address still share the first directory's limit of 250 messages a day, so it can fill up. That is why the second directory matters here, and a better design is planned.

Built without the packaged test run. Directory unit tests passed. A real connection with this fix was not run.

## 3.1 stable — 2026-11-05

Tested through the real tunnel on one PC. Two physical PCs on separate networks and a real microphone were not tested. Results are in [VALIDATION_3_1.md](docs/VALIDATION_3_1.md).

- Updates install by themselves from 3.1 on. OpenDesk checks every half hour, downloads with a progress window you can cancel, and installs when no session is open. Going from 3.0 to 3.1 still takes one click, because that is the code 3.0 has. Lite is still updated by hand.
- The second directory now works. Every signed record was too long for it, and its write request lacked a required header, so ID lookup depended on one service. A compact signed record fits.
- A host stays inside the primary directory's limit of 250 messages a day per address. It used to publish every 30 seconds, which used that up in about two hours. It now publishes every 30 seconds for the first 30 minutes of a tunnel address, then every 10 minutes.
- Viewers keep a record for 12 hours, ask the address whether it answers, and use the newest one that does.
- A dead tunnel is replaced after 3 minutes without an answer, for example after sleep or a network change.
- New messages say whether the desktop was last online some minutes ago, was not seen for 12 hours, or the directory could not be reached.
- Video is paced to what actually reached the viewer. The in-flight window used to grow when delay grew, which made the queue longer. A slow link no longer forces extra full frames, and the frames that open a session are no longer repeated.
- Voice is sent at 16 kHz instead of 48 kHz, about a third of the data, with shorter send queues and a small refill buffer. Every earlier peer already accepts this rate.
- Viewers up to 3.0 only see a host's record while it is fresh, so after 30 minutes they may fail to find a 3.1 host by ID. Update both PCs, or use a share link.

## 3.0 stable — 2026-11-04

Two physical PCs and a real microphone were not tested. Results are in [VALIDATION_3_0.md](docs/VALIDATION_3_0.md).

- In-app update window with changelog, download progress, cancel and automatic install. OpenDesk checks 8 seconds after start and every six hours, and asks before installing. A slow download no longer fails at 5 minutes.
- While the person at the host moves their mouse, the remote pointer shows as an overlay and does not move the Windows cursor. Remote clicks, drags and scrolling still use the one Windows cursor, then hand it back.
- File transfer sends up to 24 chunks at once with peers that support it and stays one at a time with older ones. Added a progress bar, speed, time left and Cancel. The list refreshes after sending.
- The Files page shows your shared folder, whether it is shared now, what was last received, and Open folder. The approval dialog names the folder, and the sharing banner shows it.
- Added a microphone test and level meters. The session says when voice was not allowed and when the microphone is silent. Two-way voice is now ticked by default in the approval dialog; your own microphone stays off until you turn it on.
- Added Settings → Local network access, off by default. The host listens only on loopback unless it is on, and then only on the private address of the default route. Turning it off closes open local network connections.
- The host skips a port that another app holds on all interfaces, so the local network address does not collide with it.

## 2.9 stable — 2026-11-04

Physical two-device use and real older apps were not tested for this release.

- Added project engineering setup: `CLAUDE.md`, nine subagents in `.claude/agents`, `PROJECT_CONTEXT.md`, and expanded `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md` and `TASKS.md`. No application code changed in this step.
- Uncommitted application work from before this setup, unreviewed for release: light theme, protocol 1 compatibility, LAN address and all-interface listening, DNS recovery, bounded directory responses, settings normalization.
- Test results on a copy of that working tree: engine tests 39 passed, 0 failed; engine Clippy with warnings denied passed; `tests/test_web.cjs` and `tests/test_release_versions.cjs` passed.
- NOT RUN: Qt/C++ build of this code, launcher tests, `native/test-*.ps1`, GUI, physical two-device or headset checks.
- Open defects are listed in `TASKS.md`.
- Fixed the legacy-mode identity bypass: a saved device answering as protocol 1 is refused, and no password is sent in compatibility mode. Older desktops with a password can no longer be reached until they are updated or the password is turned off.
- Added OpenDesk Lite (`build.ps1 -Edition Lite`): no voice, file transfer or automatic updates, installed separately. Measured 10-13% smaller than Full, with no measured difference in idle memory, idle CPU or warm start.
- Session quality selector follows the active profile, file sizes show MB and GB, Reconnect replaces the ended tab, the session bar has a speaker button and the mic icon shows its state. Settings has a separate Appearance section.
- Made packaged test scripts reliable under Windows PowerShell and on loaded machines; no assertion removed.
- Results and NOT RUN items are in [LITE_AND_COMPATIBILITY_VALIDATION.md](docs/LITE_AND_COMPATIBILITY_VALIDATION.md). Two physical PCs and real older apps were not tested.

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
