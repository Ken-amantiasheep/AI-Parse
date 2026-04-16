@echo off
chcp 65001 >nul
setlocal

set "SHARE_ROOT=%~dp0"
set "SOURCE_DIR=%SHARE_ROOT%release\AI_parse"
set "DEFAULT_INSTALL_DIR=%LOCALAPPDATA%\AI-parse"

echo ============================================
echo          AI-parse First Install
echo ============================================
echo Shared source:
echo   %SOURCE_DIR%
echo.

if not exist "%SOURCE_DIR%" (
    echo [ERROR] Release source not found. Please contact admin.
    pause
    exit /b 1
)

set /p INSTALL_DIR=Choose install folder (Enter for default): 
if "%INSTALL_DIR%"=="" set "INSTALL_DIR=%DEFAULT_INSTALL_DIR%"

echo.
echo Install to:
echo   %INSTALL_DIR%
set /p CREATE_SHORTCUT=Create desktop shortcut? (Y/n): 
if /I "%CREATE_SHORTCUT%"=="n" (
    set "DO_SHORTCUT=0"
) else (
    set "DO_SHORTCUT=1"
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" >nul 2>nul
robocopy "%SOURCE_DIR%" "%INSTALL_DIR%" /MIR /R:2 /W:1 /XD logs output __pycache__ .git >nul
if errorlevel 8 (
    echo [ERROR] File copy failed.
    pause
    exit /b 1
)

if "%DO_SHORTCUT%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AI-parse.lnk'); $S.TargetPath='%INSTALL_DIR%\start_gui.bat'; $S.WorkingDirectory='%INSTALL_DIR%'; $S.Save()"
)

echo.
echo [OK] Install completed.
echo Launcher:
echo   %INSTALL_DIR%\start_gui.bat
echo.
choice /C YN /N /M "Start now? (Y/N): "
if errorlevel 2 goto end
start "" "%INSTALL_DIR%\start_gui.bat"

:end
pause
