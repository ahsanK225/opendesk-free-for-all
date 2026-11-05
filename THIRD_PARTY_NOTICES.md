# Third-party native components

OpenDesk's own source is MIT-licensed. Native builds use Rust dependencies recorded in `native/licenses/rust/dependencies.json`, dynamically linked Qt 6.8.3, libjpeg-turbo 3.2.1, cloudflared 2026.9.3 and Microsoft's Visual C++ Desktop redistributable runtime. Inno Setup is the installer build tool. The compatible browser viewer is JavaScript.

Exact upstream license/copyright files and Qt SPDX software bills of materials are in `native/licenses` and are copied into native distributions. See `native/licenses/README.md` for corresponding-source links and Qt library replacement details. Python/Tk, PyInstaller, Pillow, NumPy and PortAudio are dependencies of the archived v2 implementation, not of the native application.

No proprietary AnyDesk binary, DeskRT codec or assets are bundled. Release executables are not claimed to carry a publicly trusted Authenticode signature.

## Added in 3.3

- iroh, MIT or Apache-2.0: peer connections. It uses public relays run by number 0 by default.
- audiopus and libopus, ISC and BSD-3-Clause: voice coding.
- H.264 uses the codecs included with Windows, and OpenDesk bundles no H.264 code.
