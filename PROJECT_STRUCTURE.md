# OpenDesk structure

- `native/engine`: Rust authorization, signed device lookup/tunnel supervision, DXGI capture, JPEG delta transport/reconstruction, WASAPI audio, Win32 input/clipboard, atomic file transfer, settings and verified update downloads.
- `native/desktop`: Qt/QML native desktop, small C++ command/state bridge, immutable frame views, GPU textures and TurboJPEG worker callbacks.
- `native/launcher`: independent Rust installer/shutdown helper, post-exit updater and persistent-cache portable bootstrap.
- `native/licenses`: pinned dependency inventory, license/copyright files and Qt SPDX documents.
- `web`: compatible protocol-v2 browser viewer.
- `tests/test_web.cjs`: browser protocol/auth/audio checks.
- `native/test-*.ps1`: isolated process, executable replacement, installer and portable repair checks.
- `assets/brand`: four SVG logo directions, comparison board and native ICO/PNG assets.
- `docs`: contribution record and dated release-validation evidence.
- `build.ps1`: native build entry point. `ci/windows.yml` is a publishable CI template, not an installed workflow.

The previous Python implementation is retained in Git tags/releases v2.0.1 and v2.0.2 and source snapshots. It is no longer part of this native source tree.
