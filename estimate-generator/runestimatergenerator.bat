@echo off
echo ==========================================
echo ALL PAINTING LTD - Estimate Generator
echo ==========================================
echo.
echo Starting server...
echo.

cd C:\Scripts\estimate-generator

REM Start Python app in background
start /B python app.py

REM Wait 3 seconds for server to start
timeout /t 3 /nobreak >nul

REM Open Chrome
echo Opening Chrome...
start chrome http://localhost:5000

echo.
echo ==========================================
echo Server is running!
echo Close this window to stop the server.
echo ==========================================
echo.
pause