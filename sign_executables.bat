@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sign_executables.ps1" %*
exit /b %errorlevel%
