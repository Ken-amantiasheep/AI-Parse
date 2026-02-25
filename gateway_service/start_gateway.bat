@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

REM Load variables from gateway_service\env if present
if exist "gateway_service\env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("gateway_service\env") do (
        if not "%%~A"=="" (
            if /i not "%%~A:~0,1%%"=="#" (
                set "%%~A=%%~B"
            )
        )
    )
)

if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY is not set.
    echo Please set it in gateway_service\env or current environment.
    exit /b 1
)

set GATEWAY_HOST=%GATEWAY_HOST%
if "%GATEWAY_HOST%"=="" set GATEWAY_HOST=0.0.0.0
set GATEWAY_PORT=%GATEWAY_PORT%
if "%GATEWAY_PORT%"=="" set GATEWAY_PORT=8080

python -m uvicorn gateway_service.app:app --host %GATEWAY_HOST% --port %GATEWAY_PORT%
