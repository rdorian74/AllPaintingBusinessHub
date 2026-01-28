@echo off
echo ========================================
echo Starting Bid System v2.0
echo All Painting Ltd.
echo ========================================
echo.

echo Starting Email Scanner (Port 3031)...
start "Bid Email Scanner" cmd /k "cd /d %~dp0bid-email-scanner && python app.py"
timeout /t 2 /nobreak >nul

echo Starting Pipedrive Sync (Port 3032)...
start "Bid Pipedrive Sync" cmd /k "cd /d %~dp0bid-pipedrive-sync && python app.py"
timeout /t 2 /nobreak >nul

echo Starting Calendar (Port 3033)...
start "Bid Calendar" cmd /k "cd /d %~dp0bid-calendar && python app.py"
timeout /t 2 /nobreak >nul

echo Starting Notifications (Port 3034)...
start "Bid Notifications" cmd /k "cd /d %~dp0bid-notifications && python app.py"
timeout /t 2 /nobreak >nul

echo Starting Quote Sent Mover (Port 3035)...
start "Bid Quote Sent Mover" cmd /k "cd /d %~dp0bid-quote-sent-mover && python app.py"
timeout /t 2 /nobreak >nul

echo Starting Bid Center Dashboard (Port 3030)...
start "Bid Center" cmd /k "cd /d %~dp0bid-center && python app.py"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo All services started!
echo Dashboard: http://localhost:3030
echo ========================================
echo.
echo Press any key to open the dashboard...
pause >nul
start http://localhost:3030
