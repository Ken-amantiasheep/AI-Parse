@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AI Parse - Update From GitHub

echo ========================================
echo AI Parse Updater
echo ========================================
echo.

powershell -ExecutionPolicy Bypass -File "scripts\update_from_github.ps1" -AppRoot "%~dp0"
if errorlevel 1 (
    echo.
    echo [ERROR] Update failed.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Update completed.
pause
