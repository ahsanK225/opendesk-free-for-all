# OpenDesk: Ultra-Low-Latency Remote Desktop Suite

OpenDesk is a modern, open-source remote desktop solution inspired by AnyDesk's architecture. It features a custom **DeskRT-style Tile & Delta Video Codec**, Win32 desktop session capturing, bidirectional input injection, P2P/Relay fallback networking, chunked file transfer, and live clipboard synchronization.

---

## 🔍 AnyDesk Reverse Engineering & Architecture Analysis

From our static and binary inspection of `AnyDesk.exe` (using PE parsing and REA framework):

### 1. Packaging & Binary Architecture
* **Single-Executable Deployment**: AnyDesk ships as a self-contained 8.5MB binary without external runtime dependencies (no Qt, Electron, or .NET).
* **In-Memory Unpacker**: The physical `.text` section is a compact ~10KB bootstrap loader. The primary 31MB executable payload resides compressed within the `.data` section and is unpacked at runtime into the virtual `.itext` section before execution.
* **Direct Win32 & DirectX Core**: Custom lightweight GUI engine drawn directly on top of Direct2D/DirectX surfaces rather than standard OS widgets, ensuring immediate responsiveness and minimal footprint.

### 2. DeskRT Video Streaming Pipeline
* **GUI-Optimized Tile Encoding**: Standard video codecs (H.264/HEVC) are optimized for continuous photographic motion and introduce blur or high latency on sharp window edges and text. AnyDesk's proprietary **DeskRT** codec divides the screen into uniform tiles, calculates spatial/temporal delta hashes, and only transmits dirty rectangles.
* **Near-Zero Static Bandwidth**: When no user activity occurs, 0 bytes are transmitted. When typing in a text editor or moving a cursor, only that specific 128x128 block is compressed and sent.
* **Screen Capture Engine**: Attaches to `OpenInputDesktop`/`SetThreadDesktop` to capture interactive sessions directly via Desktop Duplication (DXGI) and GDI DIB sections.

### 3. Rendezvous & Networking Model
* **9-Digit AnyDesk ID**: Numerical routing ID registered with global AnyDesk rendezvous servers.
* **NAT Traversal (P2P vs Relay)**: Attempts direct peer-to-peer connection using STUN/ICE UDP hole punching. If firewall/symmetric NAT prevents direct UDP traversal, connections fall back seamlessly to relay proxies.

---

## 🚀 OpenDesk Architecture & Features

OpenDesk rebuilds this core architecture into a clean, modern Python + Web/Canvas stack:

```
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│          Host Machine           │                 │       Remote Client (Web)       │
│                                 │                 │                                 │
│  [WindowsScreenCapturer]        │                 │  [RemoteRenderer (HTML5 Canvas)]│
│            │                    │                 │                 ▲               │
│            ▼                    │                 │                 │               │
│     [DeskRTCodec]               │                 │  [InputHandler] │ [FileManager] │
│  (Dirty-Tile Delta Compression) │                 │                 │       │       │
│            │                    │                 │                 │       │       │
│            ▼                    │                 │                 ▼       ▼       │
│       [HostAgent] ◄─────────────┼─[WebSocket/P2P]─┼──────────► [OpenDesk Client]    │
│            │                    │      Tunnel     │                                 │
│            ▼                    │                 │                                 │
│ [WindowsInputController]        │                 │                                 │
│ [WindowsClipboard / FileManager]│                 │                                 │
└─────────────────────────────────┘                 └─────────────────────────────────┘
                                           ▲
                                           │
                           ┌───────────────────────────────┐
                           │   OpenDesk Relay & Web App    │
                           │     (Port 8080 - HTTP/WS)     │
                           └───────────────────────────────┘
```

### Key Modules:
1. **`common/codec.py` (`DeskRTCodec`)**:
   - Uniform 128x128 tile grid partitioning.
   - Fast tile checksum diffing (transmits only modified tiles).
   - Dynamic keyframe generation and fallback.
   - Achieves up to 95% bandwidth savings compared to raw full-frame streaming.
2. **`host/capture.py` (`WindowsScreenCapturer`)**:
   - Low-level Win32 GDI DIBSection capture with `OpenInputDesktop` attachment.
   - Benchmark: Full 1920x1080 capture in ~15-22 ms.
3. **`host/input_controller.py` (`WindowsInputController`)**:
   - Normalized coordinate mapping (0.0 to 1.0) to actual host monitor resolution.
   - Mouse move, left/right/middle click, wheel scroll, keyboard keyup/keydown, and system shortcuts (Ctrl+Shift+Esc, Windows Key, Alt+Tab).
4. **`host/clipboard.py` (`WindowsClipboard`)**:
   - Win32 clipboard monitoring via `GetClipboardSequenceNumber`.
   - Bidirectional text push and pull.
5. **`host/file_manager.py` (`FileManager`)**:
   - Remote directory traversal with parent navigation.
   - 64KB chunked upload and download with SHA-256 verification.
6. **`relay/server.py` (`RelayServer`)**:
   - AnyDesk-style 9-digit numeric ID generation and routing.
   - Fallback relay server with WebSocket tunneling for 100% NAT/firewall penetration.
   - Built-in HTTP server hosting the client web interface.
7. **`host/audio.py` (`AudioEngine`) & `web/js/audio.js` (`WebAudioVoiceChat`)**:
   - WhatsApp-style real-time bidirectional voice call.
   - 16kHz 16-bit PCM streaming with ultra-low latency (<50ms).
   - PortAudio capture & playback on Windows Desktop Host with GUI mute/unmute control.
   - HTML5 Web Audio API in client browser with hardware acoustic echo cancellation (AEC) and noise suppression.
8. **`web/` (Client Frontend)**:
   - Modern glassmorphic dark UI.
   - Low-latency HTML5 Canvas tile rendering with dirty rect update.
   - Real-time FPS, RTT latency, and connection status badges.
   - Live Voice Call button (`🎙️ Voice: ON / Muted / Off`).
   - Interactive File Manager modal and Clipboard sync panel.

---

## 🛠️ Quickstart & Setup Instructions

### 1. Install Dependencies
```bash
cd opendesk
pip install -r requirements.txt
```

### 2. Start the Relay & Web Server
```bash
python run_relay.py --port 8080
```
* Output will display:
  `Web Client: http://localhost:8080`
  `WebSocket:  ws://localhost:8080/ws`

### 3. Start the Host Agent (Machine to be Controlled)
In a separate terminal:
```bash
python run_host.py
```
* The host agent will connect to the relay and print its unique 9-digit ID:
  ```
  ==================================================
    OPENDESK HOST IS READY!
    Your OpenDesk ID: 524 819 301
    Relay Server: ws://localhost:8080/ws
    Client Web UI: http://localhost:8080
  ==================================================
  ```

### 4. Connect from Any Browser / Client
1. Open your browser at `http://localhost:8080` (or `http://<your-lan-ip>:8080` from another PC, phone, or laptop).
2. Enter the host's 9-digit OpenDesk ID (e.g. `524 819 301`).
3. Click **Connect Session**.
4. The remote desktop stream will immediately appear with interactive mouse and keyboard control, file transfer, and clipboard sync!

---

## 🔄 In-App Automatic Software Updates

OpenDesk includes an autonomous, 1-click in-app software updater designed for seamless client and friend distribution:
- **Automatic Startup Check**: Upon launch, OpenDesk silently checks GitHub for newer releases in the background without freezing the GUI.
- **Top Notification Banner**: When a newer version is detected, a sleek notification banner alerts you (`⚡ Update Available: OpenDesk vx.x.x is ready to install!`).
- **Interactive Update Modal**: Click `Update Now` to review the release notes, new features, and view real-time download progress.
- **Zero-Friction Self-Relaunch**: Once downloaded, OpenDesk automatically closes, replaces the executable in 1-2 seconds, and relaunches into the updated version without requiring any manual installation steps!
- **Settings Control**: Open `Settings (⚙️)` anytime to manually check for updates or toggle automatic background checks on startup.

---

## 📦 Standalone Distribution & Installer

### 1. Ready-To-Share Installer
* **Direct Download (Installer)**: [👉 Download Setup Wizard (`OpenDesk_Setup_v1.1.2.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.1.2/OpenDesk_Setup_v1.1.2.exe)
* **Direct Download (Portable)**: [👉 Download Portable Executable (`OpenDesk_v1.1.2.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.1.2/OpenDesk_v1.1.2.exe)
* **GitHub Releases**: [View All Releases & Assets](https://github.com/ahsanK225/opendesk-free-for-all/releases)
* **Local Build Path**: Generated locally in your project folder as `installer_output\OpenDesk_Setup_v1.1.2.exe` and `OpenDesk.exe`.

### 2. Features of the Installer:
* **Interactive Setup Wizard**: Guided welcome, destination directory, and confirmation screens.
* **Desktop & Start Menu Shortcuts**: Includes checkbox options for creating desktop and Start Menu shortcuts.
* **Clean Uninstaller**: Registered in Windows *Apps & Features* for clean removal anytime.
* **Silent Install Support**: Supports automated/silent installations using `/SILENT` or `/VERYSILENT`.

### 3. Recompiling the Installer & Automatic Signing (1-Click):
To recompile both the portable executable and the installer wizard with automated Authenticode signing:
```cmd
build_installer.bat
```

---

## 🛡️ Digital Signatures & Authenticode Code Signing

All OpenDesk binaries (`OpenDesk.exe` and `OpenDesk_Setup.exe`) are digitally signed using **Windows Authenticode** with SHA-256 digests and RFC 3161 timestamps provided by DigiCert.

### 1. Verifying Digital Signatures in Windows
1. Right-click `OpenDesk.exe` or `OpenDesk_Setup.exe` in Windows File Explorer.
2. Select **Properties**.
3. Click the **Digital Signatures** tab.
4. You will see:
   - **Name of Signer**: `OpenDesk Software`
   - **Digest Algorithm**: `sha256`
   - **Timestamp**: Signed with DigiCert RFC 3161 timestamp authority (valid until 2037).

### 2. Trusting the OpenDesk Publisher (1-Click)
To ensure Windows SmartScreen and UAC recognize OpenDesk as a trusted, verified publisher:
```cmd
scripts\install_certificate.bat
```
*(Double-click `install_certificate.bat` and click "Yes" when prompted by Windows).*

### 3. Manual Signing Script
To sign any custom build or binary:
```cmd
sign_executables.bat
```
or via PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\sign_executables.ps1
```
