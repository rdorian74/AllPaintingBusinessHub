@echo off
title Payroll - Port 5003

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    goto :run
)

echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat
echo Installing dependencies...
pip install flask pdfplumber anthropic pdf2image pytesseract pillow --quiet
echo Setup complete!

:run
echo.
echo ============================================================
echo    PAYROLL APP: http://localhost:5003
echo ============================================================
echo.

python app.py
pause
