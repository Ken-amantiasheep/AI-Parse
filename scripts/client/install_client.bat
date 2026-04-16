@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_client.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] 安装失败，请检查上面的错误信息。
    pause
    exit /b 1
)

echo.
echo [OK] 安装成功。
pause
