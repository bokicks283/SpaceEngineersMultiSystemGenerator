#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$PackagePath = (Join-Path $PSScriptRoot 'RandomSectorGenerator-v0.1.0-alpha.zip'),
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ModName = 'RandomSectorGenerator'
$Destination = Join-Path $env:APPDATA "SpaceEngineers\Mods\$ModName"
$Downloads = Join-Path $HOME 'Downloads'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Backup-ExistingMod {
    if (-not (Test-Path -LiteralPath $Destination)) {
        return
    }

    New-Item -ItemType Directory -Force -Path $Downloads | Out-Null
    $backup = Join-Path $Downloads "$ModName-Backup-$Stamp.zip"
    Compress-Archive -LiteralPath $Destination -DestinationPath $backup -CompressionLevel Optimal
    Write-Host "Backed up existing local mod to:" -ForegroundColor Yellow
    Write-Host "  $backup"
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $Destination) {
        Backup-ExistingMod
        Remove-Item -LiteralPath $Destination -Recurse -Force
        Write-Host "Removed local mod:" -ForegroundColor Green
        Write-Host "  $Destination"
    }
    else {
        Write-Host "Random Sector Generator is not installed locally."
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $PackagePath)) {
    throw @"
Package not found:
  $PackagePath

Put this installer beside RandomSectorGenerator-v0.1.0-alpha.zip,
or run:
  pwsh .\Install-RandomSectorGenerator.ps1 -PackagePath 'C:\path\to\RandomSectorGenerator-v0.1.0-alpha.zip'
"@
}

Backup-ExistingMod

$temp = Join-Path $env:TEMP "$ModName-Install-$Stamp"
try {
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $temp -Force

    $source = Join-Path $temp $ModName
    $mainScript = Join-Path $source 'Data\Scripts\RandomSectorGenerator\RandomSectorGeneratorSession.cs'
    if (-not (Test-Path -LiteralPath $mainScript)) {
        throw "Package is missing the expected mod structure: $mainScript"
    }

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $Destination -Recurse -Force

    Get-ChildItem -LiteralPath $Destination -Recurse -File -ErrorAction SilentlyContinue |
        Unblock-File -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "Random Sector Generator v0.1.0-alpha installed." -ForegroundColor Green
    Write-Host "  $Destination" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "IMPORTANT IN-GAME LOAD ORDER:" -ForegroundColor Yellow
    Write-Host "  Real Solar Systems"
    Write-Host "  Random Sector Generator   <-- place BELOW RSS in Active Mods"
    Write-Host ""
    Write-Host "Space Engineers' in-game Active Mods list loads bottom-to-top,"
    Write-Host "so RSG must be below RSS for the bootstrap reload."
    Write-Host ""
    Write-Host "Use a fresh RSS Empty World. After loading:"
    Write-Host "  /rsg status"
    Write-Host "  /rsg skins"
    Write-Host "  /rsg planets"
    Write-Host "  /rsg generate"
    Write-Host ""
    Write-Host "When generation succeeds: SAVE -> quit to main menu -> reload."
}
finally {
    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
