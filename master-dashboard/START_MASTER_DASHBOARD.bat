@echo off
title All Painting Ltd - Master Dashboard
color 0A

echo ============================================================
echo    ALL PAINTING LTD - MASTER DASHBOARD
echo    http://localhost:5099
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if Flask is installed
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing Flask...
    pip install flask --quiet
)

echo Starting Master Dashboard...
echo.

REM Start the dashboard and open Chrome
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" "http://localhost:5099"
python app.py

pause
