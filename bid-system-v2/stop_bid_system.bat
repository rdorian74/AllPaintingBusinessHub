@echo off
REM ============================================================================
REM Stop Bid System - All Painting Ltd.
REM Stops all running Python services
REM ============================================================================

echo Stopping Bid System services...

REM Kill Python processes running on the bid system ports
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3030 :3031 :3032 :3033 :3034 :3035 :3036"') do (
    taskkill /F /PID %%a >nul 2>nul
)

REM Alternative: kill all python processes (uncomment if above doesn't work)
REM taskkill /F /IM python.exe >nul 2>nul

echo.
echo All Bid System services stopped.
pause
