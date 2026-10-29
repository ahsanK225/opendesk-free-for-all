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
                                           v
+-----------------------------------------------------------------------------------+
|                            REMOTE CLIENT (WEB BROWSER)                            |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |  HTML5 Web Application (web/index.html & web/js/)                           |  |
|  |  - HTML5 Canvas Tile Redraw (renderer.js)     - Input Scaling (input.js)    |  |
|  |  - Web Audio API AEC Voice (audio.js)         - File Assembly (file_tran...) | |
|  |  - Connection Manager (app.js)                                              |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

## 3. Code Signing & Authenticode Architecture
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
- **Packet Size**: 100 ms chunks (1,600 samples / 3,200 bytes per frame).
- **Transport**: JSON WebSocket frames with base64 encoded audio payloads (`{"type": "audio", "data": "<base64>"}`).
- **Browser Playback**: Decoded via `AudioContext` and scheduled smoothly into Web Audio buffer sources to prevent popping and underruns.
- **Echo Cancellation**: Configured in Web Audio API with `echoCancellation: true`, `noiseSuppression: true`, `autoGainControl: true`.

## 5. Security & Threat Model
1. **Session Access**: Protected by random 9-digit alphanumeric session tokens.
2. **Data in Transit**: Tunneled across Cloudflare's TLS 1.3 encrypted infrastructure.
3. **PE Binary Integrity**: Authenticode digital signature ensures that the binary cannot be tampered with or infected by malware post-compilation without invalidating the cryptographic checksum.
4. **Input Control**: Input injection is bound strictly to the active session and host window constraints.
