@echo off
title Follow Up Manager - All Painting Ltd.
echo ================================================
echo   Follow Up Manager - All Painting Ltd.
echo   Starting on http://localhost:1000
echo ================================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Install dependencies if needed
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo Starting Follow Up Manager...
echo Press Ctrl+C to stop
echo.

python app.py

pause
