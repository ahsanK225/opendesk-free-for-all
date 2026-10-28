@echo off
echo [OpenDesk] Downloading latest cloudflared binary for Windows...
curl -Lo "%~dp0cloudflared.exe" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
if %ERRORLEVEL% EQU 0 (
    echo [OpenDesk] cloudflared.exe successfully downloaded to %~dp0
) else (
    echo [OpenDesk] Error downloading cloudflared.exe. Please check your internet connection.
)
