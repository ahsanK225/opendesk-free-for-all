@echo off
setlocal
echo ========================================================
echo   OpenDesk 1-Click Authenticode Digital Signing
echo ========================================================
echo.

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\sign_executables.ps1"

if errorlevel 1 (
    echo.
    echo [ERROR] Code signing encountered issues.
    pause
    exit /b 1
)

echo.
echo All binaries successfully signed and verified!
pause
