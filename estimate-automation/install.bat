@echo off
title Estimate Automation - Installation
echo ============================================================
echo ALL PAINTING LTD - ESTIMATE AUTOMATION INSTALLER
echo ============================================================
echo.

cd /d "%~dp0"

echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo ============================================================
echo Installation complete!
echo ============================================================
echo.
echo IMPORTANT: Before running, you need to set up your Azure secret.
echo.
echo Option 1 - Environment Variable (Recommended):
echo   Set the AZURE_CLIENT_SECRET environment variable:
echo   1. Search for "Environment Variables" in Windows
echo   2. Add new User Variable: AZURE_CLIENT_SECRET = your_secret_value
echo.
echo Option 2 - Edit config.py:
echo   Open config.py and replace YOUR_SECRET_HERE with your secret
echo   (Less secure, but simpler)
echo.
echo Once configured, run: run_automation.bat
echo.
pause
