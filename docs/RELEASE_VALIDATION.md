# Release validation — 2.0.0

Validation dates: 2026-11-02–03. Windows 10 x64, Python 3.11.3.

- 97 Python tests passed using isolated configuration. Regression cases cover unauthorized pairing, password-proof replay, host ID collisions, busy sessions, disconnect revocation, permission denial, video backpressure, explicit voice rates, local-only loopback, unsafe transfer paths/chunks/digests, identity verification and update containment/rollback.
- Browser tests passed: strict binary envelope, WebCrypto/Python-compatible password proof, 48kHz block duration and voice teardown.
- Source GUI smoke passed with one initial Home tab and network services suppressed.
- Real local capture checked: GDI and DXGI, including cursor composition, x64 handles and explicit COM ownership cleanup.
- See benchmark-v2.json for measured timings. These exclude network RTT and viewer rendering and are not end-to-end FPS guarantees.
- Packaged GUI smoke passed outside the sandbox's temporary-extraction restriction. Bundled PortAudio loaded; DXGI captured a valid 1280×960 frame with network services disabled.
- Installer compiled with Inno Setup 7.1.1. An isolated smoke App ID installed into a test directory; the installed EXE SHA-256 matched the portable build. Installed GUI/PortAudio/DXGI smoke passed and the isolated uninstall completed.
- Upstream v1.2.3 commits 0398c29, 283fe9d and b824b67 were reviewed and merged without rewriting their history. The final code retains upstream's reusable codec buffers and zero-idle behavior, LAN/explicit-WebSocket normalization/tests, mouse coalescing and live RTT measurement within the v2 session protocol.
- The most recent capture benchmark rerun encountered an unavailable/locked desktop; the earlier successful capture measurements remain in benchmark-v2.json. Post-merge synthetic codec results are in benchmark-v2-codec.json.

## Operational boundaries

Unsigned artifacts; no trusted publisher private key was available. No two-machine WAN acceptance run, real microphone/speaker intelligibility assessment, soak test, full driver matrix, multi-monitor/service/UAC certification or independent penetration test was performed. Automated audio tests use synthetic PCM and mocked hardware streams. First-use native device trust requires comparing fingerprints through a trusted channel.

HTTP/WS is restricted to local/test deployments. Internet usage must use HTTPS/WSS. Device identity/discovery checks and TLS do not provide application-layer E2E encryption; the relay/tunnel operator is trusted. Full update hashes verify downloaded bytes against GitHub-hosted metadata; independent signed release metadata is not implemented.

The pinned DXcam 0.3.0 integration includes a scoped compatibility shim that leaves pointer Release ownership to comtypes, avoiding the double-release observed in the upstream release methods. GDI remains the fallback.


## Release artifact verification

The final artifact set contains the portable EXE, installer, digest-bearing version.json and SHA256SUMS.txt. Both artifacts are unsigned. A source/packaged GUI smoke check is repeated after the upstream merge. Capture and PortAudio dependency checks passed before the display became unavailable; physical WAN/voice acceptance remains outstanding.


Automatic CI is not enabled in this release: GitHub rejected workflow creation because the publishing OAuth token lacks the workflow scope. The complete Windows workflow is included as ci/windows.yml for later activation. Validation reported here is local, not a completed GitHub Actions run.

Final merged executable GUI smoke passed. Final artifact digests:

- `OpenDesk_v2.0.0_Portable.exe` — 58,040,567 bytes — SHA-256 `6ef1abbf7e45a1610dee41f1ce994fd6fa6a8bf90a432756deba582238065996`
- `OpenDesk_Setup_v2.0.0_Installer.exe` — 59,297,995 bytes — SHA-256 `faf1ba895dfb4c691b4a166ffc51a324d98f131e4078ec8bccc6fe96f39a9d40`
