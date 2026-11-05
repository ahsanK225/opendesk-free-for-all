# OpenDesk 3.3 validation — 2026-11-05

Built and run on one Windows 10 PC with no connected microphone. Host and viewer ran on the same PC and used the real public services. This is not a test between two networks, so the delay numbers below say nothing about a real distance.

## How a connection is made now

1. The host keeps a signed record on ntfy.sh, two MQTT brokers and keyvalue.immanuel.co. It names the device key and, when there is one, a tunnel address.
2. The viewer asks them all and takes the newest record.
3. The viewer dials the device key. The connection starts through a relay and moves to direct UDP when hole punching succeeds.
4. If that fails within 8 seconds, the viewer uses the Cloudflare tunnel.
5. Approval, identity and permissions are the same on every route.

## Results

| Check | Full | Lite |
| --- | --- | --- |
| Engine tests in the final build | 73 passed, 6 ignored | 71 passed, 5 ignored |
| Clippy with `-D warnings` | Passed | Passed |
| Launcher tests | Passed | Passed |
| Installer test: locked upgrade keeps ID and settings | Passed in 18.2 s | Passed in 8.8 s |

The web regression checks passed. The update helper replaced a real test install in a folder whose name has a space, and reopened the app.

### One live run through the real services

On the final source: found by ID in 2.8 s, starting on the relay and moving to direct. Both brokers held a record. The first frame came 0.8 s after approval. The 1 ms round trip reflects host and viewer sharing one PC.

### Moving picture, synthetic 1080p screen, one live run each

| Video | Sent per second | Frames per second |
| --- | --- | --- |
| JPEG tiles at width 1280 | about 4400 KB | about 40 |
| H.264 at width 1280 | about 275 KB | about 55 |

The Windows codecs took 7 ms to encode and 11 ms to decode a 1600 x 900 frame on this PC, on a synthetic picture. Real screens will differ.

### Voice

Opus used under 6000 bytes for one second of a test tone, against 32 000 bytes as 16-bit samples. No real voice was measured.

## Limits

- The other PC must be on, awake and online, with OpenDesk open and signed in. OpenDesk is not a Windows service, so it cannot be reached after a restart until someone signs in and opens it.
- iroh's public relays are free and rate limited, and iroh advises against relying on them in production. When direct UDP fails, the relay can slow down, and the Cloudflare tunnel only takes over if the first connection fails.
- The directories and brokers are public services without a guarantee, and anyone can write to a topic. Viewers only accept signed records, but someone could hide a record by overwriting it on a broker until the next publish.
- H.264 runs on the CPU, and voice shares one stream with video.
- Windows Firewall may ask about OpenDesk on first use. Without UDP the relay or tunnel is used.
- The files are not code-signed.

## NOT RUN

- Two PCs on separate networks, a real hole punch across the internet, and a phone hotspot (T-018).
- A real microphone and real voice (T-016).
- An update from 3.2 to 3.3 from inside the app. The helper passed a test with a real installer.
- A real older peer against 3.3, in either direction.
- Specialist agents (code-review, security, release-audit).
