Param()

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$PythonVersion = "3.11.9"
$PythonZip = Join-Path $RuntimeDir "python-embed.zip"
$PythonDir = Join-Path $RuntimeDir "python"
$PythonExe = Join-Path $PythonDir "python.exe"

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

if (-not (Test-Path $PythonExe)) {
    Write-Host "Downloading Python $PythonVersion (embedded)..." -ForegroundColor Cyan
    $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip
    Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force
    Remove-Item $PythonZip -Force

    $PthFile = Join-Path $PythonDir "python311._pth"
    if (Test-Path $PthFile) {
        $pthContent = Get-Content $PthFile | ForEach-Object {
            if ($_ -match "^#import site") { "import site" } else { $_ }
        }
        $pthContent | Set-Content $PthFile
    }

    Write-Host "Installing pip..." -ForegroundColor Cyan
    $GetPip = Join-Path $RuntimeDir "get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
    & $PythonExe $GetPip
    Remove-Item $GetPip -Force
}

$Services = @(
    @{ Name = "AI Agent"; Path = "ai-agent" },
    @{ Name = "Bid Addendum Agent"; Path = "bid-addendum-agent" },
    @{ Name = "Bid Center"; Path = "bid-system-v2\bid-center" },
    @{ Name = "Bid Email Scanner"; Path = "bid-system-v2\bid-email-scanner" },
    @{ Name = "Bid Pipedrive Sync"; Path = "bid-system-v2\bid-pipedrive-sync" },
    @{ Name = "Bid Calendar"; Path = "bid-system-v2\bid-calendar" },
    @{ Name = "Bid Notifications"; Path = "bid-system-v2\bid-notifications" },
    @{ Name = "Bid Quote Sent Mover"; Path = "bid-system-v2\bid-quote-sent-mover" },
    @{ Name = "Bid Followup Creator"; Path = "bid-system-v2\bid-followup-creator" },
    @{ Name = "Estimate Generator"; Path = "estimate-generator" },
    @{ Name = "Invoice Generator"; Path = "invoice-generator" },
    @{ Name = "Invoice Converter"; Path = "invoice_converter" },
    @{ Name = "Followup Manager"; Path = "followup-manager" },
    @{ Name = "Payroll App"; Path = "payroll_app" },
    @{ Name = "QuickBooks Sync"; Path = "quickbooks-sync" },
    @{ Name = "Business Hub"; Path = "master-dashboard" },
    @{ Name = "Business Subhub"; Path = "subhub-dashboard" }
)

foreach ($service in $Services) {
    $servicePath = Join-Path $RepoRoot $service.Path
    $requirements = Join-Path $servicePath "requirements.txt"
    $venvPath = Join-Path $servicePath "venv"
    if (-not (Test-Path $venvPath)) {
        Write-Host "Creating venv for $($service.Name)..." -ForegroundColor Yellow
        & $PythonExe -m venv $venvPath
    }
    $pipExe = Join-Path $venvPath "Scripts\pip.exe"
    if (Test-Path $requirements) {
        Write-Host "Installing requirements for $($service.Name)..." -ForegroundColor Green
        & $pipExe install --upgrade pip
        & $pipExe install -r $requirements
    }
}

Write-Host "✅ Windows portable setup complete." -ForegroundColor Green
