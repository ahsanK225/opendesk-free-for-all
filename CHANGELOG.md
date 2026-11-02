# Changelog

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
