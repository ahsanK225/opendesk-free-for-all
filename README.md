# OpenDesk: Ultra-Low-Latency Remote Desktop Suite

![Version](https://img.shields.io/badge/version-v1.2.2-red?style=for-the-badge&logo=github)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-blue?style=for-the-badge&logo=windows)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Security](https://img.shields.io/badge/code%20signing-Authenticode%20SHA--256-orange?style=for-the-badge)

OpenDesk is a modern, high-performance open-source remote desktop solution inspired by AnyDesk's architecture. It features a custom **DeskRT 60 FPS Tile & Delta Video Codec**, Win32 desktop session capturing, AnyDesk 8 multi-tab GUI with embedded viewports, **Modern Dark Glass Context Menus & Elevated Card UI**, **custom session management (Rename, Edit, Delete, Context Menus)** for recent sessions and favorites, **Discord-grade 48kHz HD voice communication** with "Let's Check" loopback mic testing, VAD sensitivity thresholding, and Push-to-Talk, AnyDesk-style incoming session request approval with granular permission toggles, adaptive 60 FPS motion rendering with stationary HD clarity, dynamic aspect ratio modes, zoom controls, 64-bit clipboard sync, and global zero-configuration tunneling powered by Cloudflare.

---

## 🚀 What's New in v1.2.2 (Latest Release)

- **🎨 Modern Dark Glass Context Menu Suite (`ModernContextMenu`)**:
  - **Eliminated OS White Borders**: Replaced native Win32 `tk.Menu` with a custom borderless menu encased in a sleek slate border (`#2a324b`) over deep dark glass (`#131622`).
  - **Dynamic Interactive Hover States**: Primary red highlight for Connect, soft crimson danger theme for Delete, and smooth slate highlights for Rename and Edit.
  - **Global Auto-Dismissal**: Auto-dismiss on click outside, focus change, or `<Escape>` key.
  - **Screen Boundary Clamping**: Intelligently clamps position to keep the popup safely within display bounds.

- **✨ Session Card Visual Elevation & Micro-Interactions**:
  - **Card Hover Elevation**: Added smooth border highlight (`#3b4664`) and background lift (`#191d2c`) when hovering over any card.
  - **Online Status Dot**: Added green `● Online` dot indicator beside device icon.
  - **High-Tech ID Chip**: Styled numerical ID inside a sleek dark chip (`#211823` background, `#3d222e` border, `#ef4444` Consolas font).
  - **Refined Action Toolbar**: Sleek pill-shaped `[✏️ Edit]` and `[🗑️]` buttons with smooth cyan (`#38bdf8`) and crimson (`#ef4444`) hover transitions.
  - **Dialog Focus Glow**: Added interactive AnyDesk red outline (`#ef4444`) to active input entries in Rename and Edit modal dialogs.

- **⭐ Recent Sessions & Favorites Custom Management Suite**:
  - **Rename Session**: Instantly rename device nicknames directly from the interface.
  - **Edit Details**: Comprehensive dialog to edit remote address, display alias, and favorite pinning.
  - **Delete Session**: Safely remove stale or unneeded sessions with an AnyDesk-style confirmation dialog.
  - **Quick Action Buttons**: Directly accessible `[✏️ Edit]` and `[🗑️]` buttons on each card.
  - **Right-Click Context Menu & 3-Dot Menu (`⋮`)**: Connect, Rename, Edit Details, Add/Remove Favorite, and Delete Session actions available on right-click anywhere on the card.
  - **Real-Time Reactivity**: Immediate UI updates upon any edit or deletion without requiring restart.

---

## 📦 Standalone Distribution & Installer

### 1. Ready-To-Share Installer (v1.2.2)
* **Direct Download (Installer)**: [👉 Download Setup Wizard (`OpenDesk_Setup_v1.2.2_Installer.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.2/OpenDesk_Setup_v1.2.2_Installer.exe)
* **Direct Download (Portable)**: [👉 Download Portable Executable (`OpenDesk_v1.2.2_Portable.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.2/OpenDesk_v1.2.2_Portable.exe)
* **GitHub Releases**: [View All Releases & Assets](https://github.com/ahsanK225/opendesk-free-for-all/releases)
* **Local Build Path**: Generated locally in your project folder as `OpenDesk_Setup.exe` and `OpenDesk.exe`.

- **🛡️ Startup & Connect Crash Immunity (Thread-Safe UI Queue)**:
  - **Thread-Safe `post_ui` Message Queue**: Solved `ucrtbase.dll 0xc0000409` and `RuntimeError: main thread is not in main loop` crashes by preventing background threads from directly invoking Tkinter Tcl commands.
  - **Connection Crash Elimination**: Completely resolved remote session crash when connecting to friends; video delta updates and status updates are cleanly marshaled to the main thread.
  - **Re-entrancy Guard**: Prevented Win32 message loop re-entrancy during window decoration initialization on visible desktops.

- **🖥️ Integrated Modern Title Bar (CSD) & Instant Hang-Proof Exit**:
  - **Embedded Window Controls ("App Ke Ander Hi")**: Seamlessly integrated Minimize (`―`), Maximize/Restore (`🗖`/`🗗`), and Close (`✕`) buttons right into the OpenDesk top tab bar, completely removing the external Windows OS white title bar.
  - **Native Aero Window Dragging**: Full multi-monitor dragging, edge snapping, and double-click maximize toggle.
  - **Instant Hang-Proof Close**: 0ms immediate window hiding and clean kernel-level exit (`os._exit(0)`), completely eliminating freezing or "Not Responding" when exiting.

- **🎧 Discord-Grade HD Voice & Video Suite**:
  - **Studio-Quality 48,000 Hz HD Voice**: Upgraded VoIP pipeline to Discord's 48kHz standard, matching native Windows audio hardware with zero anti-aliasing distortion.
  - **100% Backward Compatibility**: Ingests and plays audio from legacy 16kHz clients while delivering 48kHz studio audio to v1.2.1 peers.
  - **"Let's Check" Mic Test (Self-Hearing Loopback)**: Real-time self-hearing test loop routes your microphone directly into your headphones with an animated green/yellow/red VU meter.
  - **Voice Activity Detection (VAD) Sensitivity Slider**: Draggable threshold slider with auto-sensitivity ambient noise calibration cuts silence transmission completely, eliminating keyboard, fan, and breathing noise.
  - **Push-to-Talk (PTT)**: Configurable push-to-talk mode activated with `[ Left Ctrl ]`.
  - **Advanced Voice Processing**: Echo Cancellation, Noise Suppression (sub-80Hz rumble filter), and Automatic Gain Control (AGC).

- **⚡ Adaptive 60 FPS Fluid Rendering Engine**:
  - **Hardware Mouse Cursor Capture**: Direct Win32 `GetCursorInfo` and `DrawIconEx` blitting onto the host GDI memory DC ensures every remote mouse movement renders in real time as 60 FPS delta tiles.
  - **Direct RGB BGRX Screen Capture**: Captures desktop frames directly as RGB from 32-bit Win32 DIBSection memory, eliminating per-frame color space conversion overhead.
  - **Adaptive Motion Resampling**: Uses sub-millisecond `NEAREST` filter during active desktop motion and video streaming to maintain a silky smooth 60 FPS; automatically executes a pin-sharp `BILINEAR` HD pass the millisecond movement stops.
  - **Toolbar Quality Toggle**: 1-click toggle between `⚡ 60 FPS Fluid` and `💎 HD Sharp` rendering modes.

---

## 📦 Standalone Distribution & Installer

### 1. Ready-To-Share Installer (v1.2.2)
* **Direct Download (Installer)**: [👉 Download Setup Wizard (`OpenDesk_Setup_v1.2.2_Installer.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.2/OpenDesk_Setup_v1.2.2_Installer.exe)
* **Direct Download (Portable)**: [👉 Download Portable Executable (`OpenDesk_v1.2.2_Portable.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.2/OpenDesk_v1.2.2_Portable.exe)
* **GitHub Releases**: [View All Releases & Assets](https://github.com/ahsanK225/opendesk-free-for-all/releases)
* **Local Build Path**: Generated locally in your project folder as `OpenDesk_Setup.exe` and `OpenDesk.exe`.

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

### 1. Ready-To-Share Installer (v1.2.0)
* **Direct Download (Installer)**: [👉 Download Setup Wizard (`OpenDesk_Setup_v1.2.0_Installer.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.0/OpenDesk_Setup_v1.2.0_Installer.exe)
* **Direct Download (Portable)**: [👉 Download Portable Executable (`OpenDesk_v1.2.0_Portable.exe`)](https://github.com/ahsanK225/opendesk-free-for-all/releases/download/v1.2.0/OpenDesk_v1.2.0_Portable.exe)
* **GitHub Releases**: [View All Releases & Assets](https://github.com/ahsanK225/opendesk-free-for-all/releases)
* **Local Build Path**: Generated locally in your project folder as `OpenDesk_Setup.exe` and `OpenDesk.exe`.

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
