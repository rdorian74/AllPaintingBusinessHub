@echo off
echo ============================================================
echo INSTALLING AI AGENT DEPENDENCIES
echo ============================================================

pip install -r requirements.txt

echo.
echo ============================================================
echo IMPORTANT: Set your Anthropic API Key
echo ============================================================
echo.
echo Option 1 - Set environment variable (recommended):
echo    setx ANTHROPIC_API_KEY "your-api-key-here"
echo.
echo Option 2 - Edit config.py directly (not recommended):
echo    Open config.py and set ANTHROPIC_API_KEY
echo.
echo After setting the API key, run: run_agent.bat
echo ============================================================

pause
