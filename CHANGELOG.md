# Changelog

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
