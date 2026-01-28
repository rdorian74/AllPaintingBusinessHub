# ================================================
# Follow Up Manager - Setup Daily Scheduled Task
# Run this script as Administrator to create the task
# ================================================

$TaskName = "FollowUpManager_DailyScan"
$Description = "Runs Follow Up Manager daily scan at 7:00 AM"
$ScriptPath = Join-Path $PSScriptRoot "DAILY_SCAN.bat"

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Please run this script as Administrator!" -ForegroundColor Red
    pause
    exit
}

# Remove existing task if exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the trigger - Daily at 7:00 AM
$Trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM

# Create the action
$Action = New-ScheduledTaskAction -Execute $ScriptPath -WorkingDirectory $PSScriptRoot

# Create settings
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries

# Register the task
Register-ScheduledTask -TaskName $TaskName -Description $Description -Trigger $Trigger -Action $Action -Settings $Settings -RunLevel Highest

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Task Created Successfully!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Task Name: $TaskName"
Write-Host "Schedule:  Daily at 7:00 AM"
Write-Host "Action:    $ScriptPath"
Write-Host ""
Write-Host "NOTE: Make sure Follow Up Manager is running"
Write-Host "      (START_FOLLOWUP.bat) for the scan to work."
Write-Host ""
Write-Host "To change the time, open Task Scheduler and edit the task."
Write-Host ""
pause
