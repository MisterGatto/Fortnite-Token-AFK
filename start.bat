@echo off
setlocal
title Fortnite Auto OCR (ViGEm + RapidOCR)
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ was not found in PATH.
    echo Please install Python from https://www.python.org/downloads/ and check "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [SETUP] Installing dependencies from requirements.txt ...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    ".venv\Scripts\pip.exe" install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
) else (
    ".venv\Scripts\python.exe" -c "import rapidocr_onnxruntime, cv2, mss, numpy, colorama" >nul 2>&1
    if errorlevel 1 (
        echo [SETUP] Installing missing dependencies from requirements.txt ...
        ".venv\Scripts\pip.exe" install -r requirements.txt
        if errorlevel 1 (
            echo [ERROR] Failed to install Python dependencies.
            pause
            exit /b 1
        )
    )
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [HINT] If ViGEmBus failed to initialize, install the driver:
    echo        winget install ViGEm.ViGEmBus
)
pause
