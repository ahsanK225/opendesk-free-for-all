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

## 4. Audio Streaming & In-App VoIP Architecture
- **Format**: Uncompressed Linear PCM, 16,000 Hz VoIP standard transmission, 16-bit signed integer, 1 channel (mono).
- **Native Hardware Sample-Rate Handling (48kHz/44.1kHz WASAPI)**:
  - Captures and renders at physical hardware native rates via low-latency Windows WASAPI (`<3ms` hardware buffer latency).
  - Fast vectorized NumPy linear interpolation cleanly downsamples 48kHz/44.1kHz capture to 16kHz VoIP and upsamples 16kHz network audio to 48kHz/44.1kHz speaker playback without PortAudio MME distortion.
- **Continuous Sample Ring Buffer**:
  - Replaces discrete packet queues with a thread-safe, continuous sample ring buffer (`self.play_samples`) in `AudioEngine`.
  - PortAudio's `_speaker_callback` pulls the exact number of frames required by the audio driver, zero-padding only on buffer underrun.
  - Eliminates the previous buffer slicing bug where 25-50% of incoming audio samples were discarded, completely removing robotic buzzing, missing syllables, and stutter.
- **Digital Automatic Gain Control (AGC) & Noise Gate**:
  - Built-in `+6dB` (1.25x) digital gain multiplier with soft clipping guard (`np.clip(samples, -32767, 32767)`).
  - Noise gate silences background ambient fan noise and static during pauses.
- **In-App VoIP Hardware Controls ("App Ke Ander Hi")**:
  - Dedicated Audio Settings panel in `opendesk_app.py` with device dropdowns, volume scales, and real-time interactive "Test Mic" animated VU level meter.
  - Embedded session toolbar controls in `client/viewer.py`: Mic Mute/Unmute, live green pulsing voice activity VU bar, and speaker volume slider.
- **Conversational Latency Guard**: Buffer capped at 70ms with auto-purging to maintain conversational real-time delay `<50ms`.

## 5. Viewport Rendering & DeskRT 60 FPS Codec
- **Hardware Mouse Cursor Capture**: Embedded direct Win32 `GetCursorInfo` and `DrawIconEx` blitting onto the host GDI memory DC. Moving the mouse cursor immediately alters the screen buffer, ensuring small 32x32 delta tiles are broadcast at 60 FPS instead of remaining in an idle 2 FPS state when no window animations are playing.
- **Zero-Copy NumPy Vectorized Diff**: `WindowsScreenCapturer.grab_frame()` provides a direct 2D uint32 NumPy view (`1080x1920`) over Win32 GDI DIBSection memory in `<15 microseconds`, allowing screen-wide difference detection in `<1.5ms`.
- **Clustered Bounding Box Merging**: Adjacent dirty blocks (e.g. typing, scrolling, notifications) are merged into clean rectangular bounding boxes. This reduces JPEG compression calls from 30+ separate tile encodes down to 1-2 merged blocks, cutting CPU usage and WebSocket base64/JSON payload size by over 70%.
- **Decoupled Capture & Asynchronous WebSocket Sender**: Screen capture runs at 60 FPS decoupled from network latency; drops older stale frames under network congestion so the user always views the freshest screen state.
- **High-Performance Canvas Blitting**: Replaced canvas `delete("all")` item recreation with persistent canvas image item updates (`itemconfig`), avoiding Tkinter canvas garbage collection pauses.
- **Non-Starving Render Scheduling**: Replaced `after_idle` with `self.after(1, self._safe_render_frame)` to prevent mouse movement events from starving canvas redraws, achieving smooth 30-60 FPS remote desktop viewing.

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
- **Integrated Client-Side Decoration (CSD) Title & Tab Bar**: Replaces the standard Windows OS white title bar via Win32 `WS_CAPTION` stripping and `DWMWA_USE_IMMERSIVE_DARK_MODE`. The top bar hosts brand identity, tabs, and integrated Minimize (`―`), Maximize/Restore (`🗖`/`🗗`), and Close (`✕`) buttons with native hover feedback. Supports native Win32 `SC_MOVE` + `HTCAPTION` dragging and double-click maximize toggle.
- **Instant Hang-Proof Teardown**: Eliminates thread deadlock and UI freezing on close via immediate 0ms window hiding (`withdraw()`), background daemon cleanup worker, and clean kernel-level exit (`os._exit(0)`).
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

## 9. Dynamic Display Modes, Multi-Level Zooming & Backward Compatibility

### 9.1 Display Modes Architecture
In remote desktop sessions, display dimensions and aspect ratios frequently differ between client and host workstations (e.g. 16:9 1080p client connecting to 16:10 or 21:9 host, or client viewing in a windowed frame). OpenDesk provides three display modes selectable via the session toolbar `[ 📐 Mode: Fit ▾ ]`:
1. **Best Fit (`fit`)**:
   - Preserves host screen aspect ratio: `canvas_scale = min(cw / rw, ch / rh) * zoom_level`.
   - Centers image within canvas with letterboxing/pillarboxing.
   - Out-of-bounds canvas clicks inside black bars are dropped (`None, None`).
2. **Stretch to Fill (`stretch`)**:
   - Stretches remote desktop frame across entire canvas width and height: `dw = cw * zoom_level`, `dh = ch * zoom_level`.
   - Eliminates black bars completely, maximizing visible screen area on compact laptops and windowed layouts.
3. **1:1 Original Resolution (`original`)**:
   - Renders remote desktop at exact native pixel dimensions: `dw = rw * zoom_level`, `dh = rh * zoom_level`.
   - Provides zero interpolation blur and pixel-to-pixel fidelity for fine typography and IDE code editing.

### 9.2 Zoom and Pan Navigation
- **Zoom Range**: 0.5x (50%) to 3.0x (300%) with continuous 25% increments via `[ 🔍 - ]`, `[ 100% ]` (reset), and `[ 🔍 + ]`.
- **Cursor-Centered Zoom (`Ctrl + MouseWheel`)**: Dynamically computes normalized anchor under mouse cursor before scaling, adjusting pan offsets so the point directly beneath the cursor remains anchored in place.
- **Interactive Panning**:
  - **Middle-Click Drag (`<Button-2>`, `<B2-Motion>`)**: Smoothly pans viewport when remote dimensions exceed client canvas bounds.
  - Quick middle-clicks (<4px drag) pass through as native middle-click events to the remote desktop.
  - **Shift + Left-Click Drag (`<Shift-Button-1>`, `<Shift-B1-Motion>`)**: Dedicated pan alternative for trackpad and laptop users without physical middle buttons.
  - **Pan Bounds Clamping (`_clamp_pan`)**: Restricts pan offsets to `±(dw - cw) / 2 + 60px`, preventing the remote display from drifting off-screen.

### 9.3 100% Backward Compatibility Principle
All scaling, aspect ratio conversion, zoom transformation, and panning occur strictly in the client viewport canvas (`client/viewer.py`).
When transmitting mouse coordinates to the remote host:
$$\text{local\_x} = \text{event\_x} - (\text{offset\_x} + \text{pan\_x})$$
$$\text{local\_y} = \text{event\_y} - (\text{offset\_y} + \text{pan\_y})$$
$$\text{norm\_x} = \frac{\text{local\_x}}{\text{display\_width}}, \quad \text{norm\_y} = \frac{\text{local\_y}}{\text{display\_height}}$$

The resulting `norm_x, norm_y` are clamped to $[0.0, 1.0]$ and transmitted over standard WebSocket packets (`MessageType.INPUT_MOUSE_MOVE` / `INPUT_MOUSE_DOWN`).
Older host versions (v1.0.0, v1.1.0, v1.1.2, v1.1.5) consume these standard normalized coordinates without any modification:
$$\text{host\_x} = \text{int}(\text{norm\_x} \times \text{host\_width}), \quad \text{host\_y} = \text{int}(\text{norm\_y} \times \text{host\_height})$$
Thus, older hosts hit the exact target pixel regardless of whether the connecting client is zoomed in 200%, stretched, or in native 1:1 mode. Older clients connecting to newer hosts also remain 100% functional, preserving complete bidirectional backward compatibility.

## 10. Interactive Session Handshake & Granular Permissions Security Model

### 10.1 Handshake Sequence
In interactive (non-unattended) scenarios, OpenDesk protects host users from unauthorized control by introducing an AnyDesk-style approval gateway:
```
[Client]                         [Relay Server]                        [Host Agent / GUI]
   │                                    │                                      │
   ├─── 1. connect {target_id} ────────>│                                      │
   │                                    ├─── 2. session_request {client_id} ──>│
   │<── 3. connect_resp (waiting) ──────┤                                      │
   │    (Status: Waiting Approval)      │                                      ├─── 4. Play alert chime (MessageBeep)
   │                                    │                                      │    Display Topmost Modal Dialog
   │                                    │                                      │    Host selects permissions:
   │                                    │                                      │    [☑] Mouse/Keyboard, [☑] Audio,
   │                                    │                                      │    [☑] Clipboard, [☑] File Transfer
   │                                    │                                      │
   │                                    │<── 5. session_accept {permissions} ──┤ (or session_reject)
   │<── 6. connect_resp (ok/rejected) ──┤                                      │
   │    (Starts stream / Shows alert)   │                                      ├─── 6b. Apply permissions & start stream
```

### 10.2 Permission Enforcement
1. **Remote Input**: If `allow_input` is False, `WindowsInputController.enabled = False` discards all incoming mouse moves, button clicks, wheel scrolls, and keystrokes.
2. **Audio Transmission**: If `allow_audio` is False, `AudioEngine` is not activated for that session, and incoming/outgoing audio packets are discarded.
3. **Clipboard Sync**: If `allow_clipboard` is False, clipboard synchronization routines drop incoming packets and cease outbound broadcasts.
4. **File Transfer**: If `allow_file_transfer` is False, chunked read/write requests return `FILE_ERROR`.

## 11. Discord-Grade HD Voice & Video Architecture

### 11.1 48,000 Hz Studio Standard & Backward Compatibility
- **Native 48kHz Processing**: Standardizes audio sampling at 48,000 Hz mono 16-bit PCM with 20ms frame blocks (`CHUNK_MS = 20`, 960 samples/packet). This matches native Windows WASAPI hardware rates without downsampling, eliminating anti-aliasing artifacts and robotic distortion.
- **Dynamic Ingestion Adapter**: Detects incoming sample count in `play_chunk()`. Packets with `<600` samples (legacy 16kHz from older v1.1.8 clients) are smoothly upsampled to 48kHz via linear interpolation, providing 100% backward compatibility while delivering full studio fidelity to modern peers.

### 11.2 Discord Voice Suite Components
1. **"Let's Check" (Mic Test) Loopback**:
   - Loops incoming microphone audio directly into local speakers/headphones in real-time.
   - Allows users to audibly check voice clarity, room echo, and volume levels before or during an active session.
   - Accompanied by a live decibel-scaled VU meter bar (green normal, amber optimal, red clipping).
2. **Voice Activity Detection (VAD) & Ambient Noise Calibration**:
   - Continuously computes frame RMS: $RMS = \sqrt{\frac{1}{N} \sum x_i^2} / 32768$.
   - Auto-sensitivity mode dynamically computes the ambient noise floor:
     $$\text{noise\_floor} = 0.95 \times \text{noise\_floor} + 0.05 \times RMS \quad (\text{when } RMS < 0.05)$$
     $$\text{threshold} = \max(0.007, \text{noise\_floor} \times 2.5)$$
   - When speech is absent, transmission is completely gated (0 bytes sent), eliminating background fan noise, AC hum, and breathing sounds.
3. **Push-to-Talk (PTT)**:
   - Voice packets only transmit when the configured key (default `[ Left Ctrl ]`) is held down on the active session canvas.
4. **Advanced Voice Processing**:
   - **Echo Cancellation**: Prevents feedback oscillations when output speakers bleed into sensitive microphones.
   - **Noise Suppression**: High-pass difference filter removing sub-80Hz environmental rumble.
   - **Automatic Gain Control (AGC)**: Normalizes soft and loud speakers to an optimal conversational level (around -18 dBFS).

## 12. Adaptive 60 FPS Engine & Thread-Safe Concurrency

### 12.1 Concurrency Access Violation Fix (0xC0000005)
- **Problem**: When `client/viewer.py` received `VIDEO_DELTA` packets on the background WebSocket network thread, it called `self.remote_image.paste()` directly on the shared PIL image buffer while the main Tkinter thread was resizing that exact buffer (`self.remote_image.resize()`), resulting in a C-level access violation without a Python traceback.
- **Solution**: Thread-safe double-buffering guarded by `self.image_lock = threading.Lock()`. Incoming delta tiles are decoded outside the lock, and only pasted into the remote image buffer under lock. Resizing and frame rendering also hold `self.image_lock`.

### 12.2 Adaptive Motion Resampling
- **During Active Motion (<200ms from last frame)**: Canvas frame resizing uses ultra-fast `Image.Resampling.NEAREST` (<1ms per frame), keeping total per-frame render overhead far below the 16.6ms 60 FPS budget.
- **Stationary Pass (>180ms idle)**: When motion ceases, the viewport automatically triggers a high-quality `Image.Resampling.BILINEAR` pass, restoring pixel-perfect sharpness for stationary text, code, and UI elements.

## 13. Client-Side Titlebar Integration (CSD) & Thread-Safe UI Dispatch Queue

### 13.1 Thread-Safe UI Dispatch Queue (`post_ui`)
- **Problem**: In Python 3.12+, Tkinter strictly enforces that `widget.after()` or command callbacks cannot be registered from background worker threads. When background services (`run_agent`, Cloudflare reader, update check, or WebSocket receiver) called `root.after()`, concurrent access to Tcl's internal command hash table raised `RuntimeError: main thread is not in main loop` or corrupted the C runtime, causing `ucrtbase.dll 0xc0000409` fast-fail crashes after 2–5 seconds on startup or during remote connection with friends.
- **Solution**: Implemented a thread-safe message queue (`self._ui_queue = queue.Queue()`) in both `OpenDeskGUI` and `EmbeddedSessionView`. Background threads enqueue UI callbacks via `self.post_ui(fn, *args, **kwargs)`, and a single recurring timer (`_process_ui_queue`) drains and executes the callbacks safely on the main GUI thread every 16ms.

### 13.2 Seamless Client-Side Decoration (CSD) Titlebar & Re-entrancy Protection
- **Problem**: Standard Windows applications display an external OS title bar with white/gray window controls above the application body. Additionally, naive attempts to re-apply window styles on Win32 `<Map>` events lead to recursive message loop re-entrancy and `ucrtbase.dll 0xc0000409` buffer overrun termination.
- **Solution**: Seamless modern CSD integration with zero re-entrancy recursion:
  - Dynamically retrieves the true OS top-level window frame handle: `hwnd = int(self.root.wm_frame(), 16)`.
  - Enables Windows 10/11 Immersive Dark Mode via DWM attribute (`DWMWA_USE_IMMERSIVE_DARK_MODE = 20`).
  - Pre-initializes window styling via `withdraw()` -> `update_idletasks()` -> style application -> `deiconify()` so the native OS title bar is never rendered on screen.
  - Strips `WS_CAPTION` (`0x00C00000`) while preserving `WS_THICKFRAME`, `WS_MINIMIZEBOX`, `WS_MAXIMIZEBOX`, and `WS_SYSMENU`.
  - Implements strict re-entrancy protection: `if not (style & WS_CAPTION): return` and `_frameless_applying` lock, ensuring `SetWindowPos(SWP_FRAMECHANGED)` is never called recursively.
  - Seamlessly integrates Minimize (`―`), Maximize/Restore (`🗖`/`🗗`), and Close (`✕`) buttons directly inside the dark top tab bar ("App Ke Ander Hi").
  - Implements native Win32 `SC_MOVE` + `HTCAPTION` dragging and double-click maximize toggle.

### 13.3 Instant Hang-Proof App Close
- **Problem**: Synchronous shutdown of background network threads, PortAudio streams, and Cloudflare subprocesses during `_on_close` previously blocked the GUI event loop, causing Windows "Not Responding" hang dialogs.
- **Solution**: Multi-stage instantaneous exit:
  1. Hides the application window immediately via `self.root.withdraw()` (0ms perceived lag).
  2. Spawns a detached background daemon worker to cleanly terminate sub-processes and close sockets.
  3. Destroys Tkinter root widgets.
  4. Calls `os._exit(0)` for clean, immediate kernel-level termination without thread-join deadlocks.

### 13.4 Silent Testing Suite & Audio Hardware Isolation
- **Problem**: Automated test runs executing `tests/test_audio.py` and `tests/test_tabbed_gui.py` previously engaged real physical sound hardware via `sounddevice.OutputStream` and `winsound.MessageBeep`, creating jarring audio sounds and dings through the host machine during development.
- **Solution**: Complete isolation of the audio hardware during tests:
  - Mocks `sounddevice.OutputStream` and `sounddevice.InputStream` with synthetic buffer queues in `test_audio.py`.
  - Sets `os.environ["OPENDESK_SILENT_TEST"] = "1"` in `test_tabbed_gui.py` to silence system chimes.
  - Verifies all 52 unit and integration tests execute with 100% pass rate in complete silence.
