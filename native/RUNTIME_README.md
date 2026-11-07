# OpenDesk native Windows desktop

OpenDesk connects Windows desktops using an address or share URL. Open the app on both devices, compare the fingerprint on the first connection, request access and approve the permissions on the host. The host can end sharing at any time.

Microphones start muted by default. Permit two-way voice for the session, then use Mic on/off. Settings provides microphone level and speaker volume. Headphones reduce feedback.

Choose a shared folder in Settings before granting file access. Changing the folder ends an existing incoming sharing session. Existing device identity, saved desktops and settings are preserved in `%USERPROFILE%\.opendesk`.

The installer closes an existing OpenDesk instance before replacing application files. Portable runtimes are stored persistently under `%LOCALAPPDATA%\OpenDesk\runtimes`. Missing runtime files are repaired on the next launch; `--repair` forces a fresh extraction. If a redirected profile path is too long for Windows Qt plugins, set `OPENDESK_RUNTIME_DIR` to a shorter absolute writable directory. Runtime Qt libraries can be replaced in the cache or installation.

This is the stable 3.7 native Windows release. Local engine, GPU, DPI, installer and hardware acceptance coverage are recorded in the repository. Internet performance depends on devices and the connection. The app controls the primary monitor of the logged-in user session and does not control the UAC secure desktop. Cloudflare terminates the HTTPS/WSS tunnel; this is not an end-to-end encrypted peer-to-peer transport.

Source, build instructions, validation and releases:
https://github.com/ahsanK225/opendesk-free-for-all

Copyright/license notices are in the adjacent licenses directory. No proprietary AnyDesk codec or assets are shipped. The executable is not claimed to have a publicly trusted Authenticode signature.
