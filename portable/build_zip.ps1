Param()

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$Dist = Join-Path $RepoRoot "dist"
$ZipPath = Join-Path $Dist "AllPaintingBusinessHub-portable.zip"

New-Item -ItemType Directory -Path $Dist -Force | Out-Null

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Write-Host "Building portable zip..." -ForegroundColor Cyan
Compress-Archive -Path "$RepoRoot\*" -DestinationPath $ZipPath -Force
Write-Host "✅ Zip created at $ZipPath" -ForegroundColor Green
