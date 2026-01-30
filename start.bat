@echo off
chcp 65001 >nul
cls
title Intact JSON Generator
color 0A

echo.
echo ============================================================
echo            Intact JSON Generator
echo ============================================================
echo.
echo This program extracts information from documents and generates JSON files
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python first.
    pause
    exit /b
)

REM Check config file
if not exist "config\config.json" (
    echo [ERROR] Config file not found!
    echo.
    echo Please:
    echo 1. Copy config\config.example.json to config\config.json
    echo 2. Fill in your API Key in config\config.json
    echo.
    pause
    exit /b
)

echo Please drag and drop your document paths into the input box below, or type the path directly
echo (At least one document is required)
echo.
echo ------------------------------------------------------------
echo.

set /p autoplus="[1] Autoplus document path (optional, press Enter to skip): "
set /p quote="[2] Quote document path (optional, press Enter to skip): "
set /p mvr="[3] MVR document path (optional, press Enter to skip): "
set /p appform="[4] Application Form document path (optional, press Enter to skip): "

echo.
echo ------------------------------------------------------------
echo.

REM Build arguments
set args=
if not "%autoplus%"=="" (
    set args=%args% --autoplus "%autoplus%"
)
if not "%quote%"=="" (
    set args=%args% --quote "%quote%"
)
if not "%mvr%"=="" (
    set args=%args% --mvr "%mvr%"
)
if not "%appform%"=="" (
    set args=%args% --application-form "%appform%"
)

REM Check if at least one argument is provided
if "%args%"=="" (
    echo [ERROR] At least one document path is required!
    echo.
    pause
    exit /b
)

echo Running program...
echo.

REM Run Python program
python main.py %args%

echo.
echo ============================================================
echo Process completed!
echo ============================================================
echo.
pause
