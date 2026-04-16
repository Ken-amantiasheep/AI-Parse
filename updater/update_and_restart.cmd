@echo off
setlocal EnableDelayedExpansion

if "%~4"=="" (
  echo Usage: update_and_restart.cmd PID SOURCE_DIR TARGET_DIR LAUNCHER_BAT
  exit /b 1
)

set "APP_PID=%~1"
set "SRC_DIR=%~2"
set "DST_DIR=%~3"
set "LAUNCHER=%~4"

if not exist "%DST_DIR%\logs" mkdir "%DST_DIR%\logs" >NUL 2>NUL
echo [%DATE% %TIME%] updater started>>"%DST_DIR%\logs\updater.log"

:waitLoop
tasklist /FI "PID eq %APP_PID%" 2>NUL | find /I "%APP_PID%" >NUL
if not errorlevel 1 (
  timeout /T 1 /NOBREAK >NUL
  goto waitLoop
)

echo [%DATE% %TIME%] process exited, syncing files>>"%DST_DIR%\logs\updater.log"
robocopy "%SRC_DIR%" "%DST_DIR%" /MIR /R:2 /W:1 /XD logs output __pycache__ .git>>"%DST_DIR%\logs\updater.log" 2>&1

echo [%DATE% %TIME%] relaunching app>>"%DST_DIR%\logs\updater.log"
start "" "%DST_DIR%\%LAUNCHER%"
exit /b 0
