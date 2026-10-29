@echo off
setlocal
echo ========================================================
echo   OpenDesk 1-Click Trust Certificate Installer
echo ========================================================
echo.
echo Installing OpenDesk Root & Code Signing Certificate into
echo Windows Trusted Certificate Authorities and Trusted Publishers...
echo.

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set "CER_FILE=%ROOT_DIR%\certs\OpenDesk_CodeSigning.cer"

if not exist "%CER_FILE%" (
    echo [ERROR] Certificate file not found at:
    echo   %CER_FILE%
    echo Generating certificate first...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%generate_cert.ps1"
)

if not exist "%CER_FILE%" (
    echo [ERROR] Could not find or generate %CER_FILE%!
    pause
    exit /b 1
)

echo Adding to CurrentUser Root Store...
certutil -addstore -user -f "Root" "%CER_FILE%"

echo Adding to CurrentUser TrustedPublisher Store...
certutil -addstore -user -f "TrustedPublisher" "%CER_FILE%"

echo.
echo ========================================================
echo   CERTIFICATE SUCCESSFULLY INSTALLED AND TRUSTED!
echo   OpenDesk executables will now show 'Verified Publisher'
echo ========================================================
pause
