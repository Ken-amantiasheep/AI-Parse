@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Check if arguments are provided
if "%~1"=="" (
    echo ========================================
    echo Intact JSON Generator
    echo ========================================
    echo.
    echo Usage:
    echo   run.bat --autoplus "path\to\autoplus.pdf" --quote "path\to\quote.pdf" --mvr "path\to\mvr.pdf" --application-form "path\to\form.pdf"
    echo.
    echo Example:
    echo   run.bat --autoplus "documents\autoplus\file.pdf" --quote "documents\quote\file.pdf"
    echo.
    echo Or use start.bat for interactive mode
    echo.
    pause
    exit /b
)

REM Run Python program
python main.py %*

if errorlevel 1 (
    echo.
    echo Press any key to exit...
    pause >nul
)
