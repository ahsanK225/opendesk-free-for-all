# OpenDesk 3.1 validation — 2026-11-05

Built and run on one Windows 10 PC with no connected microphone. Host and viewer ran on the same PC, and traffic went out through the real Cloudflare tunnel and back. This is not a test between two networks.

## Causes found

| Report | Cause | Change |
| --- | --- | --- |
| "Not reachable" when connecting by ID | The backup directory never accepted a signed record: the record was too long (372 characters) and the request lacked `Content-Length`, so it answered 411. The primary directory allows 250 messages a day per address, used up in about two hours at one every 30 seconds. A record was only valid for 2 minutes. | Compact signed record (about 170 characters), publishing inside the daily limit, records usable for 12 hours with a check that the address answers, new tunnel after 3 minutes without an answer |
| Video delay | The in-flight window grew with delay, a late ACK forced a full frame, and sessions opened with several full frames | Pacing to delivered bytes, a window based on the fastest recent trip, no extra full frames |
| Voice delay | 48 kHz PCM needs about 128 KB/s after encoding, and it shares a TCP connection with video | 16 kHz, about 43 KB/s; shorter queues; video no longer fills the connection |

The ID in the reported error had published a record for about 12 minutes, then stopped 16 minutes before the check. Why it stopped could not be seen from this PC. If the PC was asleep, closed or offline, 3.1 reports that and cannot connect either.

## Results

| Check | Full | Lite |
| --- | --- | --- |
| Engine tests, before the automatic update change | 65 passed, 6 ignored | 64 passed, 5 ignored |
| Clippy, before the automatic update change | Passed | Passed |

The published files were built with `-SkipTests` at the owner's request, who tests them directly. The automatic update change compiled, and its behaviour was not run.

### Connecting by ID through the real services

A separate test host on this PC, reached from a second app by ID alone: found in 1.3 to 6.3 s once the tunnel was up (one earlier run took 18.9 s), first frame 0.3 to 1.6 s later. The tunnel took 9 to 31 s to come up. The backup directory held a usable record. After the host closed, the viewer reported when it was last online.

### Round trip through the tunnel

Heartbeat round trip during a session, with the video code as the only difference. Moving picture: a synthetic 1080p screen with most of it changing every frame, a heavy case. Runs alternated, so both versions met similar network conditions. Each run has 45 samples.

| Round | 3.1 median | 3.1 worst | 3.0 median | 3.0 worst |
| --- | --- | --- | --- | --- |
| 1 | 127 ms | 2403 ms | 928 ms | 3264 ms |
| 2 | 1124 ms | 9709 ms | 5441 ms | 10208 ms |
| 3 | 119 ms | 2319 ms | 854 ms | 7362 ms |

Spikes of seconds remain in this heavy case, and round 2 shows how much the network itself can vary. On the normal desktop of this PC, without motion, 3.1 measured a median of 53 to 55 ms and a worst of 62 to 192 ms over 30 to 45 samples. 3.0 was not measured on a normal desktop.

### Frame delay on a modelled link

The real encoder with a modelled link of 80 ms round trip. This compares policies only; it is not a measurement of a real network.

| Link | Before | Now |
| --- | --- | --- |
| 2 Mbps | p50 4648 ms, p95 8156 ms, 7.6 fps | p50 484 ms, p95 660 ms, 7.1 fps |
| 5 Mbps | p50 528 ms, p95 530 ms, 18.9 fps | p50 210 ms, p95 284 ms, 13.7 fps |
| 20 Mbps | p50 114 ms, p95 406 ms, 27.7 fps | p50 198 ms, p95 198 ms, 15.3 fps |

Under full-screen motion the frame rate is lower than before, and at 20 Mbps the median delay is higher. Lower delay has a cost here, and a fast link with heavy motion gets the worse side of it.

## Limits

- The other PC must be on, awake and online, with OpenDesk open and Internet access on. OpenDesk does not run as a service.
- All traffic is TCP through a Cloudflare quick tunnel, which has no uptime guarantee. Delay depends on the upload speed of the host and on the route.
- Both directories are free third-party services. If both fail, only a share link works.
- Voice is uncompressed. Echo cancellation is not implemented.
- Viewers up to 3.0 may not find a 3.1 host by ID after its first 30 minutes on one tunnel address.

## NOT RUN

- Two physical PCs on separate networks, including a phone hotspot or another country (T-018).
- A real microphone, and voice heard between two PCs, so voice delay was not measured (T-016).
- A real update to 3.1 from an installed 3.0, through the update window, and the automatic install from 3.1 on (T-017).
- The packaged incoming, update, portable and installer checks for this build.
- The dead-tunnel replacement after real sleep or a network change. Its code ran only as part of the session loop.
- A real older viewer against a 3.1 host. Its acceptance rule has a unit test.
- Specialist agents (code-review, security, release-audit).
