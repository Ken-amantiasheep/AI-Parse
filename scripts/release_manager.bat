@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

python "%~dp0release_manager_gui.py"
