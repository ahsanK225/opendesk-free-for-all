# OpenDesk 3.0 validation — 2026-11-04

Built and run on one Windows 10 PC with no connected microphone. Results are filled in from real runs; anything not run is listed under NOT RUN.

## Causes found

| Report | Cause | Change |
| --- | --- | --- |
| Update showed no progress | Only a text line existed, and the whole download had a 5 minute limit | Update window with progress and cancel; a limit on stalled reads replaces the total limit |
| Local mouse could not move | Every remote move called `SetCursorPos` on the only Windows cursor | While the local user moves, remote hover stays an overlay |
| No sound from the microphone | On this PC every capture device is unplugged or not present. Separately, voice was unticked by default and the session did not say why the button was disabled | Clear message, microphone test, level meters, voice ticked by default, own microphone still off by default |
| Slow file transfer without progress | One 64 KiB chunk at a time, waiting for each reply | Up to 24 chunks in flight with peers that state a window; progress bar, speed, time left, Cancel |
| Shared folder unclear | The folder appeared only as a line in Settings, and the Files page did not load the list on its own | Files page shows the folder, its state and Open folder; the list loads when the page opens |

## Limits

Windows has one cursor. Remote hover effects do not reach the host while the local user is moving their mouse, and a remote click briefly takes the cursor before handing it back. Two people cannot click at the same moment.

The update window asks before installing, because installing closes open sessions.

## Results

Run on F: from the same sources as the published files, with `OPENDESK_DEV_NO_TUNNEL=1`.

| Check | Full | Lite |
| --- | --- | --- |
| Build, including the incoming, update and portable checks | Passed | Passed |
| Engine tests | 48 passed, 4 ignored | 47 passed, 3 ignored |
| Clippy with `-D warnings` | Passed | Passed |
| Isolated installer over a running older build | Passed, 16.5 s | Passed, 9.4 s |
| Screens for update, transfer, files, settings, audio, home, both themes | Captured with no errors | Captured with no errors |
| Portable size | 51.9 MB | 44.8 MB |
| Installer size | 37.4 MB | 33.5 MB |

Launcher tests and the web checks passed. The real-device test failed as expected on this PC: the speaker opened, and there is no default microphone.

The update window and transfer card screens use sample values. They show the layout, not a live download.

### File transfer speed

A 13.1 MB file over loopback on this one PC, three runs. No network is involved, and no earlier build was timed the same way, so these numbers are not a speed-up figure or a prediction for a real connection.

| Direction | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| Upload | 892 ms | 596 ms | 587 ms |
| Download | 593 ms | 410 ms | 564 ms |

## NOT RUN

- A real microphone, and voice heard between two PCs (T-016). Voice transport is covered only with synthetic audio.
- A real update through the new window (T-017). The window ships in 3.0, so 2.9 and older still use their old update text, and the first real use is the update after 3.0.
- A live session with both mice moving. The cursor rule has a unit test only.
- Two physical PCs, including local network access beyond this PC's own private address.
- File transfer with a real older peer. Older peers state no window and stay at one chunk at a time.
