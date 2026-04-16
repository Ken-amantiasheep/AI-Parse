@echo off
chcp 65001 >nul
setlocal

set "INSTALL_ROOT=%~dp0"
if exist "%INSTALL_ROOT%\bootstrap\client_launcher.py" (
    set "BOOTSTRAP=%INSTALL_ROOT%\bootstrap\client_launcher.py"
) else (
    set "INSTALL_ROOT=%~dp0.."
    set "BOOTSTRAP=%INSTALL_ROOT%\bootstrap\client_launcher.py"
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.
    pause
    exit /b 1
)

if not exist "%BOOTSTRAP%" (
    echo [ERROR] Bootstrap launcher not found: %BOOTSTRAP%
    pause
    exit /b 1
)

python "%BOOTSTRAP%" --install-root "%INSTALL_ROOT%"
exit /b %errorlevel%
