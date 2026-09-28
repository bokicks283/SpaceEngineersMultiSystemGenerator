#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$SaveName = 'RSG Static Sector v2 - Post RSS'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$SeRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$SaveRoot = Join-Path $SeRoot 'Saves'
$LocalModRoot = Join-Path $SeRoot 'Mods'
$BackupRoot = Join-Path $RepoRoot 'backups'
New-Item -ItemType Directory -Force -Path $BackupRoot, $LocalModRoot | Out-Null

if (Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue) {
    throw 'Fully exit Space Engineers before applying celestial visual changes.'
}

$matches = @(
    Get-ChildItem -LiteralPath $SaveRoot -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq $SaveName -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'Sandbox.sbc') -PathType Leaf)
        }
)
if ($matches.Count -ne 1) {
    throw "Expected exactly one save named '$SaveName'; found $($matches.Count)."
}
$SavePath = $matches[0].FullName

Write-Host ''
Write-Host '[1/3] Compile celestial visual changes' -ForegroundColor Cyan
pwsh -NoProfile -File (Join-Path $RepoRoot 'scripts\Build-RSG.ps1')
if ($LASTEXITCODE -ne 0) { throw "Build-RSG.ps1 failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host '[2/3] Install updated RandomSectorGenerator' -ForegroundColor Cyan
$sourceMod = Join-Path $RepoRoot 'mods\RandomSectorGenerator'
$destMod = Join-Path $LocalModRoot 'RandomSectorGenerator'
if (Test-Path -LiteralPath $destMod -PathType Container) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $zip = Join-Path $BackupRoot "RandomSectorGenerator-before-celestial-visuals-$stamp.zip"
    Compress-Archive -LiteralPath $destMod -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Backed up installed RSG: $zip"
    Remove-Item -LiteralPath $destMod -Recurse -Force
}
Copy-Item -LiteralPath $sourceMod -Destination $destMod -Recurse

Write-Host ''
Write-Host '[3/3] Patch current campaign celestial scale' -ForegroundColor Cyan
py (Join-Path $RepoRoot 'scripts\apply_campaign_celestial_visuals.py') $SavePath
if ($LASTEXITCODE -ne 0) { throw "Celestial visual patch failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host 'Celestial visual pass complete.' -ForegroundColor Green
Write-Host "Save: $SavePath"
Write-Host ''
Write-Host 'Next: launch the save and look from open space toward the other systems and Wyaris Abyss.'
Write-Host 'Remote stars should now remain visible as small points beyond Real Stars native 200,000 km glare range.'
Write-Host 'Wyaris Abyss is enlarged and has a built-in Real Gas Giants black-hole accretion disk.'
Write-Host 'The distant S-star cluster around the black hole is visual-only and fades out on approach.'
