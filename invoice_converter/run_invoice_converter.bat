@echo off
title Invoice Converter - Port 5005

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install flask anthropic pdfplumber python-docx --quiet
)

echo.
echo ============================================================
echo    INVOICE CONVERTER: http://localhost:5005
echo ============================================================
echo.

python app.py
pause
