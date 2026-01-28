@echo off
echo ============================================================
echo ALL PAINTING LTD - AI AGENT SERVICE
echo ============================================================
echo Starting AI Agent on port 5011...
echo Dashboard: http://localhost:5011
echo ============================================================

cd /d "%~dp0"
python app.py

pause
