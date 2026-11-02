# Source layout

- `opendesk_app.py`: Tk desktop application and GUI smoke-test entry point.
- `host/agent.py`: authorization, media lifecycle, capture worker and file/input dispatch.
- `host/capture.py`, `host/dxgi.py`: DXGI/GDI capture, cursor composition and COM ownership adapter.
- `host/audio.py`: explicit-rate PCM capture/playback, VAD, gain and loopback.
- `host/input_controller.py`, `host/clipboard.py`, `host/file_manager.py`: native interaction and scoped transfers.
- `relay/server.py`: local registration, authentication challenges, approval state, forwarding and revocation.
- `common/protocol.py`, `common/codec.py`: binary video envelope and JPEG tile encoding.
- `common/security.py`, `common/credentials.py`, `common/identity.py`: password proofs, DPAPI and device trust.
- `common/rendezvous.py`, `common/tunnel.py`: expiring signed discovery and supervised public tunnels.
- `common/config.py`, `common/updater.py`, `common/incremental_updater.py`: configuration and update maintenance.
- `client/viewer.py`, `client/files.py`: native session rendering and streamed file UI.
- `web/`: browser viewer, ordered rendering and AudioWorklet voice.
- `tests/`: Python authorization/media/file/update regressions and Node browser checks.
- `tools/`: pinned tunnel fetch and local benchmarking.
- `build.ps1`, `opendesk.spec`, `opendesk_installer.iss`: Windows build/installer tooling.
- `ci/windows.yml`: Windows test/build CI template.
- `docs/`, `RELEASE_NOTES.md`: measured validation and release boundaries.
