@echo off
title All Painting - Estimate Automation
echo ============================================================
echo ALL PAINTING LTD - ESTIMATE AUTOMATION SYSTEM
echo ============================================================
echo.
echo Starting automation system...
echo Dashboard will be available at: http://localhost:5002
echo.
echo Press Ctrl+C to stop
echo ============================================================
echo.

cd /d "%~dp0"
python main.py

pause
