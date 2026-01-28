@echo off
title Invoice Generator - Port 5001

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install flask anthropic python-docx reportlab pdfplumber --quiet
)

echo.
echo ============================================================
echo    INVOICE GENERATOR: http://localhost:5001
echo ============================================================
echo.

python app.py
pause
