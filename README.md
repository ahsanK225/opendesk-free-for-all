# OpenDesk 2.0.0

Windows remote desktop with native and browser viewers, approval-based sessions, voice, clipboard and file transfer. Inspired by remote assistance tools such as AnyDesk. This project implements its own JPEG tile/delta protocol; it is not an implementation of AnyDesk's proprietary DeskRT codec and does not connect to AnyDesk devices.

**Upgrade both devices to v2.** The authorization and media protocol deliberately reject v1 clients/hosts.

## What changed

- DXGI Desktop Duplication capture through DXcam, with cursor composition and GDI fallback.
- Binary JPEG full/delta frames remove base64 expansion; a bounded acknowledgement window preserves delta dependencies and limits backlog. Capture/encoding run on a dedicated worker rather than blocking network/audio events.
- Balanced (30 FPS / up to 1600px), Performance (60 FPS target / up to 1280px), and Sharp (30 FPS / up to 2560px) profiles. Real render FPS is shown; an idle screen is reported as Idle.
- Native and browser voice use explicit PCM sample-rate metadata. Native 20ms blocks, browser AudioWorklet capture, bounded playback buffers, and VAD hangover prevent the previous speed/pitch mismatch and clipped word endings.
- Request-bound approval, host-registration secrets, password challenges, role/permission enforcement, busy checks, request expiry, rate limits and immediate disconnect revocation.
- Ed25519 device identity with native trust-on-first-use. Compare the first fingerprint against the host Settings; a changed saved key is blocked. Windows DPAPI protects stored unattended passwords and device private keys.
- Native file manager and browser transfers scoped to the host's home directory. Ordered chunks, declared lengths, atomic replacement and optional final SHA-256 verification. Closing a session clears partial transfers and releases pressed input.
- Full updates require an official HTTPS release URL and an expected SHA-256 digest. Source checkouts update through Git. Frozen builds use a separate bounded updater after main-process shutdown.

## Run from source

Windows 10/11 x64, Python 3.11 or 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m tools.fetch_cloudflared
python opendesk_app.py
```

Share the host's HTTPS tunnel URL, or enter its nine-digit address in the native client. Public directory records are signed and expire after 120 seconds; the native device-key check remains the identity trust boundary. The browser uses the explicitly opened HTTPS origin and does not redirect to public directory results. Microphone access and browser password authentication require HTTPS or localhost.

To use the standalone local relay/host launchers, set the same random `OPENDESK_HOST_TOKEN` in both terminals and run `python run_relay.py`, then `python run_host.py`. A headless host never auto-approves interactive requests: configure `--password` for unattended use. Never expose an HTTP/WS relay directly to the public internet; use the HTTPS tunnel or a TLS reverse proxy.

## Tests and diagnostics

```powershell
python -m unittest discover -s tests -t .
node tests/test_web.cjs
python opendesk_app.py --smoke-test --smoke-output smoke.json
python -m tools.benchmark --capture --output benchmark.json
```

Tests isolate user configuration and mock microphone/speaker streams. See [local benchmark results](docs/benchmark-v2.json) and [release validation](docs/RELEASE_VALIDATION.md). Synthetic codec timings are not end-to-end internet FPS promises.

## Build

```powershell
python -m pip install -r requirements-build.txt
$env:ISCC_PATH = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
.\build.ps1
```

`build.ps1 -OutputDir C:\OpenDeskBuild` redirects large output when the source drive has little space. The script runs tests, verifies a pinned official Cloudflare executable, builds the portable application and optionally an Inno Setup installer, then produces a digest-bearing update manifest and `SHA256SUMS.txt`.

Authenticode signing is optional and requires your own trusted certificate via `OPENDESK_SIGN_PFX`, `OPENDESK_SIGN_PASSWORD` and `signtool.exe`. This repository does not create/install a self-signed root as part of release builds. Unsigned builds are labelled as such. A timestamp service is not a publisher certificate.

## Deployment boundaries

This release has automated regression tests and local Windows build/capture checks. Two-machine WAN testing, long-duration voice testing, target-driver coverage and an independent security assessment remain required before an organization treats it as a production-certified remote access service. Actual performance depends on display driver, CPU, resolution, bandwidth and RTT.

Current limits: primary monitor, no Windows service/pre-login control, no secure-attention-sequence or elevated UAC desktop guarantee, and no WebRTC/UDP P2P implementation. Transport uses HTTPS/WSS through Cloudflare, not application-layer end-to-end encryption. The relay/tunnel operator is part of the trust boundary. Native voice has no implemented acoustic echo canceller; headphones are recommended for speaker feedback. Browser AEC is provided by the browser.

The incremental updater library has path/rollback protections, but the monolithic desktop release uses full-binary updates. An unsigned manifest and matching SHA-256 do not protect against compromise of the GitHub release account itself.

## License

[MIT](LICENSE). Bundled dependencies retain their respective licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).


The Windows CI definition is supplied as `ci/windows.yml`. To enable it, copy it to `.github/workflows/windows.yml` using a GitHub credential with `workflow` scope. The publishing credential used for this release could push source/releases but GitHub rejected workflow creation, so automatic CI was not enabled.
