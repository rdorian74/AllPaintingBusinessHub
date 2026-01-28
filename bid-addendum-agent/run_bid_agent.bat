@echo off
echo Starting Bid/Addendum Agent...
echo.
echo Make sure you have set the environment variables:
echo   AZURE_CLIENT_SECRET - Your Azure app secret
echo   ANTHROPIC_API_KEY - Your Anthropic API key
echo.
python main.py
pause
