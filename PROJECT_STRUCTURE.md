# OpenDesk Project Structure

## 1. Project Overview
OpenDesk is an ultra-low-latency, zero-configuration remote desktop and bi-directional voice system inspired by AnyDesk. It provides high-performance desktop screen streaming using a custom DeskRT tile & delta codec, sub-millisecond Win32 mouse/keyboard input injection, clipboard synchronization, chunked file transfer, real-time voice communication, and global zero-configuration tunneling powered by Cloudflare Tunnel (`cloudflared`). It is packaged as both a standalone executable (`OpenDesk.exe`) and a professional Windows setup installer (`OpenDesk_Setup.exe`).

## 2. Technology Stack & Framework Versions
- **Core Runtime**: Python 3.15.1 (Windows x86_64)
- **GUI Engine**: Tkinter / Tcl 8.6 with modern dark-themed aesthetics and thread-safe queues
- **Screen Capture**: `mss` 10.1.0 (Direct DXGI / GDI fast screen buffer capture)
- **Image Processing & Tile Codec**: Pillow (`PIL`) 11.1.0, NumPy 2.2.3
- **Audio Engine**: PortAudio with `sounddevice` 0.5.1, 16kHz 16-bit mono PCM
- **Networking**: `aiohttp` 3.11.12, `websockets` 15.0.1, standard `asyncio`
- **Tunneling**: Cloudflare Tunnel (`cloudflared` binary)
- **Packaging Tools**: PyInstaller 6.12.0, Inno Setup 6.4.1 (ISCC)
- **Code Signing**: Windows Authenticode with PowerShell PKI (`Set-AuthenticodeSignature`, `certutil`) and RFC 3161 Timestamping

## 3. Directory Tree
```
opendesk/
├── .gitignore                      # Git exclusion rules (ignores heavy build/, dist/, .exe)
├── build_installer.bat             # 1-Click compiler for PyInstaller & Inno Setup
├── CHANGELOG.md                    # Auditable chronological change history
├── GEMINI_SYSTEM_PROMPT.md         # Active engineering rules & multi-agent system prompt
├── OpenDesk.exe                    # Standalone single-file executable
├── opendesk.ico                    # High-resolution application icon
├── opendesk.spec                   # PyInstaller bundle specification
├── opendesk_app.py                 # Integrated Tkinter UI launcher (Agent + Relay + GUI)
├── opendesk_installer.iss          # Inno Setup 6 wizard installation script
├── OpenDesk_Setup.exe              # Compiled Inno Setup installer wizard
├── PROJECT_STRUCTURE.md            # Detailed structural and module specification
├── push_to_github.bat              # 1-Click Git push synchronization script
├── README.md                       # Public documentation, quickstart, and downloads
├── requirements.txt                # Python package dependencies
├── run_host.py                     # Standalone host runner CLI
├── run_relay.py                    # Standalone relay server CLI
├── SYSTEM_DESIGN.md                # System design & architecture specification
├── TASKS.md                        # Persistent task tracking checklist
├── __init__.py                     # Package marker
│
├── bin/
│   ├── .gitkeep                    # Tracks bin folder in git
│   ├── cloudflared.exe             # Cloudflare Tunnel zero-config binary
│   └── download_cloudflared.bat    # Automated fetch script for cloudflared
│
├── certs/                          # Authenticode Code Signing Certificates
│   ├── OpenDesk_CodeSigning.cer    # Public X.509 certificate for client trust
│   └── OpenDesk_CodeSigning.pfx    # PKCS#12 certificate and private key bundle
│
├── client/
│   ├── viewer.py                   # AnyDesk-style Native Desktop Remote Session Viewer (Tkinter + PIL)
│   └── __init__.py
│
├── common/
│   ├── codec.py                    # DeskRT 64x64 grid tile & delta frame encoder
│   ├── config.py                   # Persistent host ID and user settings manager
│   ├── protocol.py                 # JSON message schema & message type definitions
│   ├── tunnel.py                   # Async process wrapper & regex parser for cloudflared
│   └── __init__.py
│
├── host/
│   ├── agent.py                    # Host orchestration engine, event loop & signaling
│   ├── audio.py                    # Bi-directional 16kHz PCM audio capture & playback queue
│   ├── capture.py                  # High-fps screen grabber using mss
│   ├── clipboard.py                # Win32 clipboard monitor and setter
│   ├── file_manager.py             # Chunked file upload and download handler
│   ├── input_controller.py         # Direct Win32 SendInput API mouse/keyboard injection
│   └── __init__.py
│
├── relay/
│   ├── server.py                   # WebSocket broker routing host and web clients
│   └── __init__.py
│
├── scripts/
│   ├── generate_cert.ps1           # Generates 2048-bit RSA Code Signing Certificate
│   ├── install_certificate.bat     # 1-Click root/publisher trust installer via certutil
│   ├── sign_executables.ps1        # Authenticode SHA256 & RFC 3161 signing script
│   └── verify_signatures.ps1       # Digital signature audit & validation tool
│
├── tests/
│   ├── test_audio.py               # Unit tests for audio buffer, chunking, and PCM logic
│   ├── test_codec.py               # Unit tests for tile delta encoding and compression
│   ├── test_file_manager.py        # Unit tests for file chunking and hash integrity
│   ├── test_integration.py         # End-to-end integration tests for relay and host
│   └── __init__.py
│
└── web/
    ├── index.html                  # Responsive HTML5 client web app
    ├── css/
    │   └── style.css               # Modern dark styling, pulsating indicators, responsive grid
    └── js/
        ├── app.js                  # Client coordinator, WebSocket lifecycle & UI events
        ├── audio.js                # Web Audio API 16kHz PCM streaming & echo cancellation
        ├── file_transfer.js        # File drag-and-drop & download assembly
        ├── input.js                # Mouse coordinates scaling and keyboard event listener
        └── renderer.js             # Canvas tile renderer and partial redraw engine
```

## 4. Component Responsibilities
- **`opendesk_app.py`**: Main application GUI. Launches the background host agent and relay server, monitors Cloudflare tunnel connection, displays 9-digit session code, and provides visual audio controls.
- **`host/agent.py`**: Core host engine. Captures screens, encodes delta frames, streams audio, injects input, synchronizes clipboard, and coordinates file transfers.
- **`host/audio.py`**: Captures local microphone input via `sounddevice.InputStream` and streams 16kHz PCM chunks; plays incoming remote audio chunks smoothly via a jitter-buffer queue.
- **`host/input_controller.py`**: Interacts with Windows OS via `ctypes.windll.user32.SendInput` to accurately emulate native hardware mouse movement, clicks, scrolls, and keystrokes.
- **`common/codec.py`**: Divides screen into 64x64 tiles, computes pixel hashes, compresses dirty tiles using JPEG/PNG, and serializes delta frames.
- **`common/tunnel.py`**: Spawns `cloudflared.exe`, monitors stderr for public tunnel URL creation, and exposes the local port securely worldwide without firewall configuration.
- **`web/`**: Zero-install web client connecting via WebSockets to receive display frames and audio, capture mouse/keyboard inputs, and enable file exchange.
- **`scripts/`**: Enterprise-grade signing and certificate deployment utilities.
