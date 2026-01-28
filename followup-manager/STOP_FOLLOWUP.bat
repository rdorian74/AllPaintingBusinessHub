@echo off
echo Stopping Follow Up Manager...

REM Find and kill Python processes running on port 1000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":1000"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Follow Up Manager stopped.
timeout /t 2
