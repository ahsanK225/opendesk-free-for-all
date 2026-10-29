@echo off
setlocal
echo ========================================================
echo   OpenDesk Professional Installer Compilation Script
echo ========================================================

echo.
echo [1/4] Compiling OpenDesk.exe using PyInstaller...
python -m PyInstaller opendesk.spec --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller compilation failed!
    exit /b 1
)
copy /y dist\OpenDesk.exe OpenDesk.exe >nul

echo.
echo [2/4] Signing OpenDesk.exe with Authenticode Signature...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\sign_executables.ps1" -Files "dist\OpenDesk.exe" "OpenDesk.exe"

echo.
echo [3/4] Locating Inno Setup Compiler...
set "ISCC=C:\Users\ahsan\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
    echo [ERROR] Inno Setup compiler ISCC.exe not found!
    exit /b 1
)

echo.
echo Compiling OpenDesk_Setup.exe Wizard Installer...
"%ISCC%" opendesk_installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup packaging failed!
    exit /b 1
)
copy /y installer_output\OpenDesk_Setup_v1.1.0.exe OpenDesk_Setup.exe >nul

echo.
echo [4/4] Signing OpenDesk_Setup.exe with Authenticode Signature...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\sign_executables.ps1" -Files "installer_output\OpenDesk_Setup_v1.1.0.exe" "OpenDesk_Setup.exe"

echo.
echo ========================================================
echo   BUILD AND SIGNING COMPLETED SUCCESSFULLY!
echo   Signed Portable:  OpenDesk.exe
echo   Signed Installer: OpenDesk_Setup.exe
echo ========================================================
