<#
.SYNOPSIS
  Build a clean release zip for Agent Bus.

.DESCRIPTION
  Bundle the agent-bus project into a zip, excluding dev/runtime artifacts:
  - cache: __pycache__/, *.pyc, *.pyo, .pytest_cache/, .coverage*, htmlcov/
  - virtualenv: .venv/, venv/, env/, .env
  - log/runtime: *.log, *.jsonl, _log/, _sandbox/, _dbg_out.txt
  - local config: config.json, config/bot.json (keeps config.example.json)

  Does NOT modify source — copies filtered files to temp, then zips.

.PARAMETER Tag
  Optional release tag. Default "REV_E".

.PARAMETER OutDir
  Output folder for the zip. Default = project root.

.EXAMPLE
  cd scripts
  .\build_release.ps1
  # → C:\Projects\agent-bus\release_REV_E_2026-05-11_1234.zip

.NOTES
  Sync with .gitignore: config.json, bot.json, _sandbox, _log, *.log, *.jsonl.
#>

[CmdletBinding()]
param(
    [string]$Tag = "REV_E",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if ([string]::IsNullOrEmpty($OutDir)) {
    $OutDir = $ProjectRoot
}

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$ZipName   = "release_${Tag}_${Timestamp}.zip"
$ZipPath   = Join-Path $OutDir $ZipName

Write-Host "=== Build release zip ===" -ForegroundColor Cyan
Write-Host "Source : $ProjectRoot"
Write-Host "Output : $ZipPath"
Write-Host ""

$ExcludePatterns = @(
    "*\__pycache__\*",
    "*\__pycache__",
    "*.pyc",
    "*.pyo",
    "*\.pytest_cache\*",
    "*\.pytest_cache",
    "*\.coverage",
    "*\.coverage.*",
    "*\htmlcov\*",
    "*\.venv\*",
    "*\venv\*",
    "*\env\*",
    "*\.env",
    "*.log",
    "*.jsonl",
    "*\_log\*",
    "*\_log",
    "*\_sandbox\*",
    "*\_sandbox",
    "*\_dbg_out.txt",
    "*\_scan_out.txt",
    "*\config.json",
    "*\config\bot.json"
)

$Stage = Join-Path $env:TEMP "release_stage_$(Get-Random)"
New-Item -ItemType Directory -Path $Stage | Out-Null
Write-Host "Stage  : $Stage" -ForegroundColor DarkGray
Write-Host ""

$total = 0
$skipped = 0
$copied = 0

Write-Host "[1/3] Filtering files..." -ForegroundColor Yellow
Get-ChildItem -Path $ProjectRoot -Recurse -File -Force | ForEach-Object {
    $total++
    $rel = $_.FullName.Substring($ProjectRoot.Length).TrimStart('\', '/')
    $exclude = $false
    foreach ($pat in $ExcludePatterns) {
        if ($_.FullName -like $pat) {
            $exclude = $true
            break
        }
    }
    if ($exclude) {
        $skipped++
        return
    }
    $destPath = Join-Path $Stage $rel
    $destDir  = Split-Path -Parent $destPath
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -Path $_.FullName -Destination $destPath -Force
    $copied++
}

Write-Host "  Total scanned : $total"
Write-Host "  Copied        : $copied" -ForegroundColor Green
Write-Host "  Skipped       : $skipped" -ForegroundColor DarkYellow
Write-Host ""

Write-Host "[2/3] Compressing..." -ForegroundColor Yellow
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipSizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host "  Done. Size: $ZipSizeMb MB" -ForegroundColor Green
Write-Host ""

Write-Host "[3/3] Cleanup stage..." -ForegroundColor Yellow
Remove-Item $Stage -Recurse -Force
Write-Host "  Done." -ForegroundColor Green
Write-Host ""

Write-Host "=== Release ready ===" -ForegroundColor Cyan
Write-Host "  $ZipPath" -ForegroundColor Cyan
