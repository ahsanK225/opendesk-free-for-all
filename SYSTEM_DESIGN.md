# OpenDesk System Design & Architecture Specification

## 1. System Goals and Scope
OpenDesk is designed to offer a lightweight, zero-configuration, ultra-fast remote desktop and voice solution. Its scope encompasses:
1. Low-latency desktop screen mirroring with minimal bandwidth usage.
2. Low-latency, full-duplex voice communication between Host and Web Client.
3. Natural Win32 hardware input emulation (keyboard and mouse).
4. Bi-directional clipboard text synchronization and chunked binary file transfers.
5. Worldwide connectivity without port-forwarding via Cloudflare Quick Tunnels.
6. Single-file portable execution and seamless installation wizard.
7. Enterprise-compliant Windows Authenticode Code Signing with RFC 3161 timestamps.

## 2. Architecture Overview
```
+-----------------------------------------------------------------------------------+
|                                HOST MACHINE (WINDOWS)                             |
|                                                                                   |
|  +-----------------------+     +--------------------+     +--------------------+  |
|  |   Tkinter GUI App     |     |   Screen Capture   |     |    Audio Engine    |  |
|  |  (opendesk_app.py)    |     |    (host/capture)  |     |   (host/audio.py)  |  |
|  +-----------+-----------+     +---------+----------+     +---------+----------+  |
|              |                           |                          |             |
|              v                           v                          v             |
|  +-----------------------------------------------------------------------------+  |
|  |                      Host Agent Engine (host/agent.py)                      |  |
|  |  - DeskRT 64x64 Tile Delta Codec               - Win32 SendInput Controller |  |
|  |  - 16kHz PCM Audio Streamer                    - Clipboard Synchronizer     |  |
|  |  - Chunked File Transfer Engine                - WebSocket Client           |  |
|  +---------------------------------------+-------------------------------------+  |
|                                          |                                        |
|                                          v (Local WS: ws://127.0.0.1:8765)        |
|  +-----------------------------------------------------------------------------+  |
|  |                     Relay Server (relay/server.py)                          |  |
|  |  - Session Router (9-Digit Room ID)           - Static Web Server (aiohttp) |  |
|  +---------------------------------------+-------------------------------------+  |
|                                          |                                        |
|                                          v (Exposes port 8765)                    |
|  +-----------------------------------------------------------------------------+  |
|  |                     Cloudflare Tunnel (common/tunnel.py)                    |  |
|  |  - cloudflared.exe subprocess                 - HTTPS / WSS Worldwide Edge  |  |
|  +---------------------------------------+-------------------------------------+  |
+------------------------------------------|----------------------------------------+
                                           |
                              Secure Edge / Internet (WSS)
                                           |
                    +----------------------+----------------------+
                    |                                             |
                    v                                             v
+-----------------------------------------+   +-----------------------------------------+
|     NATIVE ANYDESK CLIENT (WINDOWS)     |   |      REMOTE CLIENT (WEB BROWSER)        |
|                                         |   |                                         |
| +-------------------------------------+ |   | +-------------------------------------+ |
| | NativeSessionViewer (client/viewer) | |   | | HTML5 Web App (web/index.html & js) | |
| | - Tkinter Canvas + PIL ImageTk      | |   | | - HTML5 Canvas Tile Redraw          | |
| | - Win32 Mouse & Keyboard Injection  | |   | | - Web Audio API AEC Voice           | |
| | - Integrated Native AudioEngine     | |   | | - Browser Clipboard Sync            | |
| | - Direct Windows Clipboard Sync     | |   | | - Zero-Install Remote Control       | |
| +-------------------------------------+ |   | +-------------------------------------+ |
+-----------------------------------------+   +-----------------------------------------+
```

## 3. Global Rendezvous & Cross-Network Discovery Architecture
OpenDesk implements an AnyDesk-style zero-configuration discovery system enabling two users on completely different LANs, cellular networks, or firewalls to establish a remote desktop session using only a 9-digit numerical ID (e.g., `732 364 935`).

### 3.1 Architecture Overview
```
[Host PC (ID: 732 364 935)]
        │
        ├── 1. Initializes Local Relay & Cloudflare Tunnel
        │      Tunnel URL generated: https://alpha-beta.trycloudflare.com
        │
        ├── 2. Publishes to Dual-Redundant Global Rendezvous (common/rendezvous.py)
        │      Primary: HTTP POST -> ntfy.sh/opendesk_node_732364935 (Cloudflare Edge, <100ms)
        │      Secondary: HTTP POST -> keyvalue.immanuel.co/api/KeyVal/UpdateValue/s460x9wm/732364935/<Base64 URL>
        │
        └── 3. Runs Background RendezvousHeartbeat every 40s
               Maintains fresh endpoint registration across both channels

                                     ▲
                                     │ (Lookup: <100ms on Cloudflare Edge)
                                     ▼

[Client PC (Any Network)]
        │
        ├── 1. User enters 9-digit ID: "732 364 935"
        │
        ├── 2. EmbeddedSessionView Worker Queries Dual-Redundant Rendezvous
        │      Primary: HTTP GET -> ntfy.sh/opendesk_node_732364935/raw?poll=1
        │      Secondary Fallback: HTTP GET -> keyvalue.immanuel.co/api/KeyVal/GetValue/s460x9wm/732364935
        │      Decodes URL -> https://alpha-beta.trycloudflare.com
        │
        └── 3. Connects directly: wss://alpha-beta.trycloudflare.com/ws
               Host relay accepts client and connects session!
```

### 3.2 Dynamic Fallback Routing
If a client connects directly to a host's tunnel URL (e.g. from an invite link or browser bookmark), `relay/server.py` performs active peer fallback matching: if the specified target ID is not directly indexed, the relay automatically routes the session to the currently registered host peer on that instance.

## 4. Code Signing & Authenticode Architecture
Windows enforces digital signatures on Executable (`.exe`) and Dynamic Link Library (`.dll`) binaries through Microsoft Authenticode.
Unsigned binaries trigger Windows SmartScreen warnings ("Windows protected your PC / Unknown Publisher") and strict enterprise anti-malware inspection.

### 3.1 Digital Signature Pipeline
```
[Unsigned Binary] (OpenDesk.exe / OpenDesk_Setup.exe)
        │
        ▼
[PowerShell PKI Engine] (Set-AuthenticodeSignature)
        ├── Signing Key: RSA 2048-bit Private Key (.pfx)
        ├── Digest Algorithm: SHA-256 (Secure Hash Standard)
        └── RFC 3161 Timestamp Server: http://timestamp.digicert.com
        │
        ▼
[PE Header Embedded Signature] (WIN_CERTIFICATE Table in PE Header)
        │
        ▼
[Client Verification] (Get-AuthenticodeSignature / Windows Explorer)
        ├── Status: Valid
        ├── Signer: "CN=OpenDesk Software, O=OpenDesk Project"
        └── Valid Even After Certificate Expiration (Preserved by Timestamp Authority)
```

### 3.2 Certificate Strategy
1. **Subject**: `CN=OpenDesk Software, O=OpenDesk Project, OU=Development, C=US`
2. **Key Specifications**: RSA 2048-bit key length, SHA-256 signature algorithm.
3. **Enhanced Key Usage (EKU)**: Code Signing (`1.3.6.1.5.5.7.3.3`).
4. **Validity**: 10 Years (2026 - 2036).
5. **Timestamping**: RFC 3161 compliant DigiCert timestamp server ensures that even if the certificate reaches its expiration date in 2036, the signed executables remain cryptographically valid because they were timestamped when the certificate was active.
6. **Trust Provisioning**: For client workstations and lab environments, a 1-click batch script (`scripts/install_certificate.bat`) registers the public certificate (`certs/OpenDesk_CodeSigning.cer`) into the machine's `Root` and `TrustedPublisher` certificate stores using Windows native `certutil.exe`.

## 4. Audio Streaming Architecture
- **Format**: Uncompressed Linear PCM, 16,000 Hz, 16-bit signed integer, 1 channel (mono).
- **Packet Size**: 40 ms chunks (640 samples / 1,280 bytes per frame), down from 100 ms to achieve sub-millisecond audio transmission latency.
- **Adaptive Jitter Buffer Purge**: The speaker playback queue automatically drops stale frames if the queue length exceeds 2 packets (>80ms), preventing cumulative audio drift and delay accumulation during bursty network activity.
- **Transport**: JSON WebSocket frames with base64 encoded audio payloads (`{"type": "audio", "data": "<base64>"}`).
- **Smart Device Selection**: Automatically scans PortAudio input devices and selects physical microphones (e.g., Gaming Audio Headset, Realtek) over disconnected virtual devices (Virtual Desktop, VB-Audio, Steam Streaming).
- **Thread-Safe Queueing**: Dispatches PortAudio background thread callbacks into asyncio event loop via `call_soon_threadsafe`.
- **Browser Playback**: Decoded via `AudioContext` and scheduled smoothly into Web Audio buffer sources clamped to <0.15s window to prevent popping, underruns, and playhead lag.
- **Echo Cancellation**: Configured in Web Audio API with `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`.

## 5. Viewport Rendering & Event Loop Debouncing
- **Canvas Debouncing**: `client/viewer.py` uses `_trigger_render` with an atomic `_render_pending` flag and `self.after_idle(self._render_frame)` to batch incoming `VIDEO_DELTA` tile bursts.
- **Starvation Prevention**: Prevents saturation of Tkinter's single-threaded event loop, keeping the Windows OS message dispatch queue (`WM_PAINT`, `WM_TIMER`, mouse motion) active and eliminating application hangs / "Not Responding" states under high framerate.

## 6. Bidirectional Clipboard Synchronization Architecture
- **Host-to-Client**: `WindowsClipboard` monitors OS sequence numbers (`GetClipboardSequenceNumber`) with 64-bit safe ctypes pointers (`GlobalAlloc`, `GlobalLock`). Detected changes are relayed to the client and written automatically via `navigator.clipboard.writeText`.
- **Client-to-Host**: Native browser `paste` events intercept `Ctrl+V` on the viewport canvas, transmitting the plain text payload to the host with `auto_paste: true`. The host commits the text to the Windows clipboard and injects `Ctrl+V` via `user32.keybd_event`.

## 6. Security & Threat Model
1. **Session Access**: Protected by random 9-digit alphanumeric session tokens.
2. **Data in Transit**: Tunneled across Cloudflare's TLS 1.3 encrypted infrastructure.
3. **PE Binary Integrity**: Authenticode digital signature ensures that the binary cannot be tampered with or infected by malware post-compilation without invalidating the cryptographic checksum.
4. **Input Control**: Input injection is bound strictly to the active session and host window constraints.

## 7. AnyDesk 8 Multi-Tab GUI & Session Viewport Architecture

### 7.1 Multi-Tab Workflow & Viewport Switching
OpenDesk adheres to the signature AnyDesk 8 desktop experience:
- **Top Window Tab Bar**: A horizontal tab strip featuring persistent `[ 🏠 New Connection ]`, active remote session tabs `[ 💻 <Formatted ID>  ✕ ]`, and a dynamic `+` button.
- **In-App Embedded Session Viewport (`EmbeddedSessionView`)**: Remote desktop sessions are hosted directly within the tab container frame inside the main window, rendering 60 FPS DeskRT delta frames onto an interactive Tkinter `Canvas` with normalized Win32 input, voice audio, and bidirectional clipboard sync.
- **Tab Lifecycle**:
  1. User enters a 9-digit address in the Quick Connect bar or clicks a Recent Session card.
  2. The tab manager verifies if a tab for that target ID already exists. If yes, it brings that tab to focus.
  3. If not, it instantiates an `EmbeddedSessionView` inside a dedicated `tk.Frame`, registers the tab in `self.tabs`, and displays the tab button with close `✕`.
  4. The user can switch freely between `New Connection` (Home) and active remote sessions without disconnecting the underlying WebSocket streams.
  5. Clicking `✕` or "Disconnect" terminates the session, stops the `AudioEngine`, cancels the network tasks, destroys the tab frame, and returns focus to the Home dashboard.

### 7.2 Left Navigation Sidebar & Dashboard
- **Sidebar Strip**: Sleek vertical strip (`#12151e`) containing navigation items for `🏠 Home`, `⭐ Favorites`, `🕒 Recent`, `📁 Files`, and `⚙️ Settings` with an active AnyDesk red indicator bar (`#ef4444`).
- **Quick Connect Search Bar**: Prominent address bar with monospace font, optional unattended password entry, and a primary AnyDesk Red action button (`#ef4444`).
- **This Desk Card**: Displays persistent 9-digit address in bold triplets (`780 363 657`), 1-click address copy, unattended password management, and Cloudflare worldwide tunnel status with 1-click shareable link.
- **Recent Sessions & Favorites Discovery Grid**: Responsive grid rendering recent target workstations with computer icon, device alias, 9-digit ID, last seen timestamp, favorite star toggle, and 1-click "Connect ➜" launcher.

### 7.3 Design Tokens & Styling
- **Backgrounds**: Main `#0c0e14`, Sidebar `#12151e`, Header/TabBar `#141822`, Cards `#161924`, Input/Address Box `#202534`.
- **Accents**: Primary Brand Red `#ef4444` (hover `#dc2626`), Electric Blue `#3b82f6`, Success Green `#22c55e`, Warning Amber `#e0af68`.
- **Borders & Dividers**: Subtle borders `#282e3f`, active tab highlight `#ef4444`.
- **Typography**: Interface font `Segoe UI` (8pt to 12pt bold), Monospace address font `Consolas` (9pt to 20pt bold).

## 8. In-App Automatic Software Update Architecture

### 8.1 Remote Release Manifest & Version Handshake
OpenDesk employs a lightweight, decoupled update manifest stored at the root of the repository (`version.json`):
- **Version Endpoint**: `https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/version.json`
- **Payload Schema**:
  ```json
  {
    "version": "1.1.2",
    "release_date": "2026-10-29",
    "download_url": "https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/OpenDesk.exe",
    "installer_url": "https://raw.githubusercontent.com/ahsanK225/opendesk-free-for-all/main/OpenDesk_Setup.exe",
    "changelog": ["Feature A", "Feature B"]
  }
  ```
- **Semantic Versioning**: Evaluated via numeric tuple comparison (`parse_version`), distinguishing releases strictly newer than the active build (`APP_VERSION`).

### 8.2 Client Lifecycle & Update UX
1. **Background Discovery**: When enabled via config (`auto_update: true`), a non-blocking background daemon thread performs an update check 2.5 seconds after GUI initialization.
2. **Notification Banner**: If a newer version exists, an AnyDesk-style notification banner animates beneath the top tab bar alerting the user with `[ 🚀 Update Now ]`.
3. **Interactive Modal**: The user can review the formatted changelog, inspect the release version, and initiate a monitored chunked download (with live progress bar reporting download speed and percentage).
4. **Windows Binary Self-Replacement**:
   - Because Windows locks active running executables, OpenDesk writes an atomic batch updater helper script (`%TEMP%\opendesk_self_update.bat`).
   - The batch script waits for the old OpenDesk process to cleanly exit (`timeout /t 2`), overwrites the target binary (`copy /y`), relaunches the new binary (`start "" "%TARGET_EXE%"`), and self-deletes (`del "%~f0"`).
   - This ensures zero-friction, 1-click self-updates for all clients and remote workstations without requiring manual zip extraction or reinstallation.

### 8.3 Smart Incremental Differential Auto-Update System
- **Differential Manifest Comparison (`common/incremental_updater.py`)**:
  - Instead of downloading the full 70 MB application package on minor releases, the client inspects file hashes against the remote `manifest.json`.
  - Unchanged files (such as runtime DLLs, system libraries, and static assets) are marked `to_skip` (0 bytes downloaded).
  - Only modified or new files are downloaded into a temporary `.update_staging/` sandbox (typically 15 KB to 200 KB, saving >98% bandwidth).
- **Per-File SHA-256 Integrity Verification**:
  - Every downloaded chunk is verified against the manifest's SHA-256 cryptographic hash.
  - If a hash mismatch or corrupt payload is detected, the staging directory is wiped immediately, and the update aborts with a clear error.
- **Atomic Rollback & User Data Preservation**:
  - A pre-update snapshot of target files is created in `.update_backup/`.
  - If any error occurs during the file copy process, the backup is restored automatically, leaving the running installation completely uncorrupted.
  - Glob rules (`config.json`, `recent_sessions.json`, `unattended.key`, `logs/*`, `certs/*`) prevent user tokens, settings, and session histories from ever being overwritten during updates.
- **Manifest Generation & Release Server Tools**:
  - `tools/manifest_generator.py`: Recursively scans release folders and generates versioned `manifest.json` files with SHA-256 hashes.
  - `tools/update_server.py`: Lightweight HTTP server supporting byte-range streaming, CORS headers, and delta delivery for local testing and CDN deployment.
