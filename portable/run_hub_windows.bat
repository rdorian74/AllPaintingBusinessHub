@echo off
set ROOT=%~dp0..
set PYTHON=%ROOT%\master-dashboard\venv\Scripts\python.exe
if exist "%PYTHON%" (
  "%PYTHON%" "%ROOT%\master-dashboard\app.py"
) else (
  python "%ROOT%\master-dashboard\app.py"
)
