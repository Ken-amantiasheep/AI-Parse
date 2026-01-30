@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Intact JSON Generator - GUI

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

REM Run GUI application
python gui_app_simple.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start GUI application
    echo.
    echo Make sure all dependencies are installed:
    echo   pip install -r requirements.txt
    echo.
    pause
)
