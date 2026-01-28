@echo off
set ROOT=%~dp0..
set PYTHON=%ROOT%\subhub-dashboard\venv\Scripts\python.exe
if exist "%PYTHON%" (
  "%PYTHON%" "%ROOT%\subhub-dashboard\app.py"
) else (
  python "%ROOT%\subhub-dashboard\app.py"
)
