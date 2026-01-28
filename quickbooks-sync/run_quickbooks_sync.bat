@echo off
title QuickBooks Sync - All Painting Ltd
cd /d "%~dp0"

echo ============================================================
echo   QuickBooks Sync Service
echo   All Painting Ltd
echo ============================================================
echo.

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
)

echo.
echo Starting QuickBooks Sync Service...
echo Dashboard: http://localhost:5010
echo.
python app.py

pause
