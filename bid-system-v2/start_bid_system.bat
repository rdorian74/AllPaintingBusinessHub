@echo off
REM ============================================================================
REM Bid System Launcher - All Painting Ltd.
REM Opens all services in Windows Terminal with split panes
REM ============================================================================

where wt >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Windows Terminal not found. Please install it from Microsoft Store.
    pause
    exit /b 1
)

set BASE_DIR=%~dp0

REM Launch with tabTitle for each pane - shows in tab and can use Ctrl+Shift+P to see pane titles
wt -M ^
    --tabColor "#1e40af" --title "Bid Center 3030" -d "%BASE_DIR%bid-center" cmd /k "title Bid Center [3030] && color 1F && echo. && echo ========================================== && echo    BID CENTER - Port 3030 && echo ========================================== && echo. && python app.py" ^
    ; split-pane -H --title "Quote Mover 3035" -d "%BASE_DIR%bid-quote-sent-mover" cmd /k "title Quote Mover [3035] && color 2F && echo. && echo ========================================== && echo    QUOTE SENT MOVER - Port 3035 && echo ========================================== && echo. && python app.py" ^
    ; move-focus left ^
    ; split-pane -V --title "Email Scanner 3031" -d "%BASE_DIR%bid-email-scanner" cmd /k "title Email Scanner [3031] && color 5F && echo. && echo ========================================== && echo    EMAIL SCANNER - Port 3031 && echo ========================================== && echo. && python app.py" ^
    ; move-focus right ^
    ; split-pane -V --title "Pipedrive Sync 3032" -d "%BASE_DIR%bid-pipedrive-sync" cmd /k "title Pipedrive Sync [3032] && color 6F && echo. && echo ========================================== && echo    PIPEDRIVE SYNC - Port 3032 && echo ========================================== && echo. && python app.py" ^
    ; move-focus down ^
    ; move-focus left ^
    ; split-pane -V --title "Calendar 3033" -d "%BASE_DIR%bid-calendar" cmd /k "title Calendar [3033] && color 3F && echo. && echo ========================================== && echo    CALENDAR - Port 3033 && echo ========================================== && echo. && python app.py" ^
    ; move-focus right ^
    ; split-pane -V --title "Notifications 3034" -d "%BASE_DIR%bid-notifications" cmd /k "title Notifications [3034] && color 4F && echo. && echo ========================================== && echo    NOTIFICATIONS - Port 3034 && echo ========================================== && echo. && python app.py" ^
    ; split-pane -H --title "Follow-Up 3036" -d "%BASE_DIR%bid-followup-creator" cmd /k "title Follow-Up Creator [3036] && color 5E && echo. && echo ========================================== && echo    FOLLOW-UP CREATOR - Port 3036 && echo ========================================== && echo. && python app.py"
