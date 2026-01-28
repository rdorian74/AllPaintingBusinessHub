@echo off
echo ==================================
echo All Painting Ltd
echo Estimate Generator
echo ==================================
echo.

if "%ANTHROPIC_API_KEY%"=="" (
    echo ERROR: ANTHROPIC_API_KEY not set
    echo.
    echo Please set your API key:
    echo   set ANTHROPIC_API_KEY=your-api-key-here
    echo.
    echo Get your API key at: https://console.anthropic.com/
    pause
    exit /b 1
)

echo API key found
echo Starting server...
echo.

python app.py
pause
