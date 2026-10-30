# OpenDesk Project Structure

## 1. Project Overview
OpenDesk is an ultra-low-latency, zero-configuration remote desktop and bi-directional voice system inspired by AnyDesk. It provides high-performance desktop screen streaming using a custom DeskRT tile & delta codec, sub-millisecond Win32 mouse/keyboard input injection, 64-bit bidirectional clipboard synchronization, chunked file transfer, real-time voice communication, and global zero-configuration tunneling powered by Cloudflare Tunnel (`cloudflared`). It is packaged as both a standalone executable (`OpenDesk.exe`) and a professional Windows setup installer (`OpenDesk_Setup.exe`), featuring an authentic AnyDesk multi-tab window architecture and embedded in-tab session viewports.

## 2. Technology Stack & Framework Versions
- **Core Runtime**: Python 3.15.1 (Windows x86_64)
- **GUI Engine**: Tkinter / Tcl 8.6 with custom AnyDesk 8 dark-themed multi-tab strip, navigation sidebar, and embedded session canvas
- **Screen Capture**: `mss` 10.1.0 (Direct DXGI / GDI fast screen buffer capture)
- **Image Processing & Tile Codec**: Pillow (`PIL`) 11.1.0, NumPy 2.2.3
- **Audio Engine**: PortAudio with `sounddevice` 0.5.1, smart physical microphone auto-detection, 16kHz 16-bit mono PCM
- **Networking**: `aiohttp` 3.11.12, `websockets` 15.0.1, standard `asyncio`
- **Tunneling**: Cloudflare Tunnel (`cloudflared` binary) executed from external user directory to prevent temp folder file locking
- **Packaging Tools**: PyInstaller 6.22.3, Inno Setup 6.7.3 (ISCC)
- **Code Signing**: Windows Authenticode with PowerShell PKI (`Set-AuthenticodeSignature`, `certutil`) and DigiCert RFC 3161 Timestamping

## 3. Directory Tree
```
opendesk/
├── .gitignore                      # Git exclusion rules (ignores build/, dist/, .exe)
├── build_installer.bat             # 1-Click compiler for PyInstaller & Inno Setup
├── CHANGELOG.md                    # Auditable chronological change history
├── GEMINI_SYSTEM_PROMPT.md         # Active engineering rules & multi-agent system prompt
├── INCREMENTAL_UPDATE_GUIDE.md     # Differential auto-update & server deployment guide
├── OpenDesk.exe                    # Standalone single-file executable (Digitally Signed)
├── opendesk.ico                    # High-resolution application icon
├── opendesk.spec                   # PyInstaller bundle specification with all hidden imports
├── opendesk_app.py                 # AnyDesk 8 multi-tab GUI, sidebar, quick-connect & embedded session viewer
├── opendesk_installer.iss          # Inno Setup 6 wizard installation script (v1.1.7)
├── OpenDesk_Setup.exe              # Compiled Inno Setup installer wizard (Digitally Signed)
├── OpenDesk_Setup_v1.1.7_Installer.exe # Versioned installer wizard binary (v1.1.7)
├── OpenDesk_v1.1.7_Portable.exe    # Versioned standalone portable binary (v1.1.7)
├── PROJECT_STRUCTURE.md            # Detailed structural and module specification
├── push_to_github.bat              # 1-Click Git push synchronization script
├── README.md                       # Public documentation, quickstart, and downloads
├── requirements.txt                # Python package dependencies
├── run_host.py                     # Standalone host runner CLI
├── run_relay.py                    # Standalone relay server CLI
├── SYSTEM_DESIGN.md                # System design & architecture specification
├── TASKS.md                        # Persistent task tracking checklist
├── version.json                    # Remote software update manifest and release metadata
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
│   ├── viewer.py                   # In-tab EmbeddedSessionView & NativeSessionViewer: Aspect ratio modes (Fit/Stretch/1:1), Zoom (50%-300%), Pan, render debouncing, backward-compatible coordinate normalization
│   └── __init__.py
│
├── common/
│   ├── codec.py                    # DeskRT 64x64 grid tile & delta frame encoder
│   ├── config.py                   # Persistent host ID, recent sessions, favorites, unattended access
│   ├── incremental_updater.py      # Smart differential updater with SHA-256 verification & atomic rollback
│   ├── protocol.py                 # JSON message schema & message type definitions
│   ├── rendezvous.py               # Dual-Redundant Global Rendezvous (ntfy.sh Cloudflare Edge primary + KeyValue fallback)
│   ├── tunnel.py                   # Externalized cloudflared runner & process killer
│   ├── updater.py                  # In-app auto-update engine, progress downloader & self-restart
│   └── __init__.py
│
├── host/
│   ├── agent.py                    # Host orchestration engine, event loop & signaling
│   ├── audio.py                    # Bi-directional 16kHz PCM audio capture with 40ms blocks & zero-delay jitter purging
│   ├── capture.py                  # High-fps screen grabber using mss
│   ├── clipboard.py                # 64-bit safe Win32 clipboard monitor and setter
│   ├── file_manager.py             # Chunked file upload and download handler
│   ├── input_controller.py         # Direct Win32 SendInput API mouse/keyboard injection
│   └── __init__.py
│
├── relay/
│   ├── server.py                   # WebSocket broker routing host and clients
│   └── __init__.py
│
├── scripts/
│   ├── generate_cert.ps1           # Generates 2048-bit RSA Code Signing Certificate
│   ├── install_certificate.bat     # 1-Click root/publisher trust installer via certutil
│   ├── sign_executables.ps1        # Authenticode SHA256 & DigiCert RFC 3161 signing script
│   └── verify_signatures.ps1       # Digital signature audit & validation tool
│
├── tests/
│   ├── test_audio.py               # Unit tests for audio buffer, chunking, and PCM logic
│   ├── test_clipboard_audio.py     # Unit tests for 64-bit clipboard and mic selection
│   ├── test_codec.py               # Unit tests for tile delta encoding and compression
│   ├── test_file_manager.py        # Unit tests for file chunking and hash integrity
│   ├── test_incremental_updater.py # Unit tests for SHA-256 delta updates, rollback & multi-release tests
│   ├── test_integration.py         # End-to-end integration tests for relay and host
│   ├── test_native_viewer.py       # Unit tests for native desktop session viewer
│   ├── test_rendezvous.py          # Unit tests for 9-digit rendezvous publish, resolve, and heartbeat
│   ├── test_tabbed_gui.py          # Unit tests for AnyDesk tab lifecycle & recent session config
│   ├── test_updater.py             # Unit tests for auto-update version check & download
│   └── __init__.py
│
├── tools/
│   ├── manifest_generator.py       # Generates versioned manifest.json with file SHA-256 hashes
│   └── update_server.py            # HTTP update distribution server for delta delivery
│
└── web/
    ├── index.html                  # Responsive HTML5 client web app (browser fallback)
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
- **`opendesk_app.py`**: AnyDesk 8 multi-tab desktop application. Provides top tab strip (`[ 🏠 New Connection ]`, dynamic `[ 💻 <ID> ✕ ]` tabs, `+` button), left navigation sidebar, Home dashboard with This Desk card, quick connect search bar, unattended password setup, recent sessions & favorites discovery grid, and embedded in-tab session viewports.
- **`client/viewer.py`**: Contains `EmbeddedSessionView(tk.Frame)` and `NativeSessionViewer(tk.Toplevel)`. Renders real-time DeskRT video frames onto Tkinter canvas, scales coordinates, forwards mouse/keyboard input, synchronizes clipboard, handles 16kHz audio, and manages fullscreen and shortcuts.
- **`host/agent.py`**: Core host engine. Captures screens, encodes delta frames, streams audio, injects input, synchronizes clipboard, and coordinates file transfers.
- **`common/config.py`**: Persistent configuration store for 9-digit host ID, recent sessions history, aliases, favorite devices, unattended password access, and automatic update preferences.
- **`common/rendezvous.py`**: Global rendezvous directory client and heartbeat service. Maps 9-digit OpenDesk IDs to live Cloudflare Tunnel endpoints worldwide, enabling instant AnyDesk-style cross-network discovery.
- **`common/updater.py`**: In-app software updater. Queries remote `version.json` or GitHub releases, parses semantic versions, downloads update packages with progress monitoring, and handles seamless Windows batch self-replacement and relaunch.
