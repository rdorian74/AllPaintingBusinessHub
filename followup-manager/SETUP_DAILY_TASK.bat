@echo off
REM ================================================
REM Setup Daily Auto-Scan Task
REM This will open PowerShell as Administrator
REM ================================================

echo Setting up daily auto-scan task...
echo.
echo A UAC prompt will appear - click Yes to continue.
echo.

powershell -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0SETUP_DAILY_TASK.ps1\"' -Verb RunAs"
