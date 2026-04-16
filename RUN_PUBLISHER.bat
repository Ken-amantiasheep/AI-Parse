@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python first.
    pause
    exit /b 1
)

python "%~dp0publisher_gui.py"
