@echo off
setlocal
echo ========================================================
echo   OpenDesk Professional Installer Compilation Script
echo ========================================================

echo.
echo [1/3] Compiling OpenDesk.exe using PyInstaller...
python -m PyInstaller opendesk.spec --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller compilation failed!
    exit /b 1
)
copy /y dist\OpenDesk.exe OpenDesk.exe >nul

echo.
echo [2/3] Locating Inno Setup Compiler...
set "ISCC=C:\Users\ahsan\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
    echo [ERROR] Inno Setup compiler ISCC.exe not found!
    exit /b 1
)

echo.
echo [3/3] Compiling OpenDesk_Setup.exe Wizard Installer...
"%ISCC%" opendesk_installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup packaging failed!
    exit /b 1
)
copy /y installer_output\OpenDesk_Setup_v1.1.0.exe OpenDesk_Setup.exe >nul

echo.
echo ========================================================
echo   BUILD COMPLETED SUCCESSFULLY!
echo   Installer Output: OpenDesk_Setup.exe
echo ========================================================
