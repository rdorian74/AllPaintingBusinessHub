@echo off
REM ================================================
REM Follow Up Manager - Daily Auto Scan
REM Runs at beginning of day, checks last 24 hours
REM ================================================

echo [%date% %time%] Running daily auto scan...

REM Call the auto-scan endpoint
curl -s -X GET "http://localhost:1000/api/scan/auto"

echo.
echo [%date% %time%] Auto scan complete.
