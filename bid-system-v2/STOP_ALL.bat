@echo off
echo Stopping All Bid System Services...
echo.

:: Use WMIC to find and kill cmd.exe processes with our window titles
:: This properly closes the cmd windows

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Center"') do (
    taskkill /PID %%~i /F /T 2>nul
)

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Email Scanner"') do (
    taskkill /PID %%~i /F /T 2>nul
)

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Pipedrive Sync"') do (
    taskkill /PID %%~i /F /T 2>nul
)

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Calendar"') do (
    taskkill /PID %%~i /F /T 2>nul
)

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Notifications"') do (
    taskkill /PID %%~i /F /T 2>nul
)

for /f "tokens=2" %%i in ('tasklist /v /fo csv ^| findstr /i "Bid Quote Sent Mover"') do (
    taskkill /PID %%~i /F /T 2>nul
)

:: Also kill any remaining processes on our ports
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3030 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3031 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3032 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3033 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3034 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3035 " ^| findstr "LISTENING"') do taskkill /PID %%a /F 2>nul

echo.
echo All services stopped.
timeout /t 2 >nul
exit
