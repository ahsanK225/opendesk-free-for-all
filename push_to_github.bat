@echo off
title OpenDesk - Push to GitHub
cd /d "%~dp0"

echo ========================================================
echo   OpenDesk: Pushing code to GitHub
echo   Repository: https://github.com/ahsanK225/opendesk-free-for-all.git
echo ========================================================
echo.

git remote set-url origin https://github.com/ahsanK225/opendesk-free-for-all.git
git branch -M main

echo Uploading commits to GitHub...
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   SUCCESS! All code has been pushed to your GitHub repo.
    echo   Visit: https://github.com/ahsanK225/opendesk-free-for-all
    echo ========================================================
) else (
    echo.
    echo [Info] If your GitHub repo already has a README or files, trying pull rebase...
    git pull --rebase origin main
    git push -u origin main
)

echo.
pause
