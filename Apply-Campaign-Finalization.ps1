#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$SaveName = 'RSG Static Sector v2 - Post RSS'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = $PSScriptRoot
$SeRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$LocalModRoot = Join-Path $SeRoot 'Mods'
$BackupRoot = Join-Path $RepoRoot 'backups'
New-Item -ItemType Directory -Force -Path $BackupRoot, $LocalModRoot | Out-Null

function Get-SteamRoots {
    $roots = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Steam'),
        (Join-Path $env:ProgramFiles 'Steam')
    )
    foreach ($key in @('HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
        try {
            $item = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
            if ($item.SteamPath) { $candidates += $item.SteamPath }
            if ($item.InstallPath) { $candidates += $item.InstallPath }
        } catch { }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Container)) {
            [void]$roots.Add((Resolve-Path -LiteralPath $candidate).Path)
        }
    }
    foreach ($steam in @($roots)) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (-not (Test-Path -LiteralPath $vdf -PathType Leaf)) { continue }
        $text = Get-Content -LiteralPath $vdf -Raw
        foreach ($match in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
            $path = $match.Groups[1].Value -replace '\\\\', '\'
            if (Test-Path -LiteralPath $path -PathType Container) {
                [void]$roots.Add((Resolve-Path -LiteralPath $path).Path)
            }
        }
    }
    return @($roots)
}

function Find-WorkshopMod([string]$Id) {
    $matches = foreach ($root in Get-SteamRoots) {
        $candidate = Join-Path $root "steamapps\workshop\content\244850\$Id"
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return @($matches | Sort-Object -Unique)
}

if (Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue) {
    throw 'Fully exit Space Engineers before finalizing the campaign.'
}

$requiredWorkshop = [ordered]@{
    '2667547195' = 'Bigger Explosions'
    '2649159807' = 'Kinetic Devastation'
    '2760086069' = 'HyperDrive'
    '2802482180' = 'Damaged Spawnships'
    '1608841667' = 'Daily Needs Survival Kit'
    '2747715235' = 'Populated Worlds Creatures'
}
foreach ($entry in $requiredWorkshop.GetEnumerator()) {
    $found = @(Find-WorkshopMod $entry.Key)
    if ($found.Count -ne 1) {
        throw "Required Workshop mod is not installed exactly once: $($entry.Key) $($entry.Value). Found $($found.Count)."
    }
    Write-Host "Found $($entry.Value): $($found[0])"
}

$saveMatches = @(
    Get-ChildItem -LiteralPath (Join-Path $SeRoot 'Saves') -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq $SaveName -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'Sandbox.sbc') -PathType Leaf)
        }
)
if ($saveMatches.Count -ne 1) {
    throw "Expected exactly one save named '$SaveName'; found $($saveMatches.Count)."
}
$SavePath = $saveMatches[0].FullName

Write-Host ''
Write-Host '[1/3] Compile local RandomSectorGenerator changes' -ForegroundColor Cyan
pwsh -NoProfile -File (Join-Path $RepoRoot 'scripts\Build-RSG.ps1')
if ($LASTEXITCODE -ne 0) { throw "Build-RSG.ps1 failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host '[2/3] Install updated local RandomSectorGenerator' -ForegroundColor Cyan
$sourceMod = Join-Path $RepoRoot 'mods\RandomSectorGenerator'
$destMod = Join-Path $LocalModRoot 'RandomSectorGenerator'
if (-not (Test-Path -LiteralPath $sourceMod -PathType Container)) {
    throw "Missing repo mod source: $sourceMod"
}
if (Test-Path -LiteralPath $destMod -PathType Container) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $zip = Join-Path $BackupRoot "RandomSectorGenerator-before-finalization-$stamp.zip"
    Compress-Archive -LiteralPath $destMod -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Backed up installed RSG: $zip"
    Remove-Item -LiteralPath $destMod -Recurse -Force
}
Copy-Item -LiteralPath $sourceMod -Destination $destMod -Recurse

Write-Host ''
Write-Host '[3/3] Finalize the existing campaign save' -ForegroundColor Cyan
py (Join-Path $RepoRoot 'scripts\finalize_campaign_world.py') $SavePath
if ($LASTEXITCODE -ne 0) { throw "Campaign finalizer failed with exit code $LASTEXITCODE" }

Write-Host ''
Write-Host 'Campaign is finalized for the launch smoke test.' -ForegroundColor Green
Write-Host "Save: $SavePath"
Write-Host ''
Write-Host 'Next:'
Write-Host '  1. Launch this save.'
Write-Host '  2. When ready to begin, choose Crash Start - Lorek (normal) or Crash Start - Talek (hard).'
Write-Host '  3. If the pod is damaged but usable, DNSK appears, and the world remains stable after one save/reload: play.'
Write-Host '  4. Do not do another broad test pass unless an actual blocker appears.'
