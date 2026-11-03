# OpenDesk 3.0.0-alpha.1 native preview

This release replaces the Python/Tk desktop and PyInstaller packaging with a Rust engine, Qt/QML desktop, direct SIMD TurboJPEG media workers and standalone Rust delivery tools. It retains protocol-v2 interoperability and the dark/red visual identity with the Portal O icon.

Native session authorization, captured-frame reconstruction, file integrity/revocation, actual GPU pixel-format/presentation, 100%/150% DPI, post-exit portable replacement, locked-app installer upgrade and standalone startup have been exercised locally. The native installed package contains no Python interpreter or foreign Windows CRT/API-set DLLs. Settings and device identity are preserved.

Use the installer for an existing installed OpenDesk. The helper requests a graceful shutdown and then performs a bounded force-close of verified OpenDesk processes if needed. The portable EXE extracts into a persistent cache and supports runtime repair. Software updates verify official release URLs and SHA-256 before independent replacement/restart.

This is a preview, not a production/WAN acceptance claim. Real two-device WAN/headset tests remain required. Headphones reduce feedback; acoustic echo cancellation, pre-login/UAC secure-desktop control, monitor selection and end-to-end peer encryption are not implemented. Cloudflare terminates the HTTPS/WSS tunnel. Publicly trusted Authenticode signing is not claimed.

The v2.0.2 stable release and its source tag remain available for rollback. The root version.json continues to describe the stable update channel; preview downloads do not silently opt existing users into preview updates. Validation, measured stage timings and remaining gates are recorded in docs/NATIVE_VALIDATION.md.
