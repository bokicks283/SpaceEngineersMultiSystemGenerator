#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Downloads = Join-Path $HOME 'Downloads'
$Root = Join-Path $env:TEMP "Terminus-ProxyAudit-$Stamp"
$Out = Join-Path $Root 'Collected'
$Zip = Join-Path $Downloads "Terminus-ProxyAudit-$Stamp.zip"
$Report = Join-Path $Root 'REPORT.txt'
$RepoRoot = $PSScriptRoot

New-Item -ItemType Directory -Force -Path $Out, $Downloads | Out-Null

function Add-Report([string]$Text = '') {
    $Text | Add-Content -LiteralPath $Report -Encoding utf8
}

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

function Copy-TextFiles([string]$Source, [string]$Destination) {
    Get-ChildItem -LiteralPath $Source -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -in @('.sbc','.xml','.cs','.cfg','.ini','.txt','.md','.json','.sbmi') -and
            $_.Length -lt 8MB
        } |
        ForEach-Object {
            $relative = [IO.Path]::GetRelativePath($Source, $_.FullName)
            $target = Join-Path $Destination $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
}

"Terminus / RSS proxy audit" | Set-Content -LiteralPath $Report -Encoding utf8
Add-Report "Generated: $(Get-Date -Format o)"
Add-Report

$mods = [ordered]@{
    '3481843850' = 'Terminus - Black Hole'
    '3350589349' = 'RSS Planet Exporter'
    '3351055036' = 'Real Solar Systems'
    '3152436752' = 'Real Stars'
}

foreach ($entry in $mods.GetEnumerator()) {
    $matches = @(Find-WorkshopMod $entry.Key)
    if ($matches.Count -ne 1) {
        Add-Report "MISSING/AMBIGUOUS: $($entry.Key) $($entry.Value) count=$($matches.Count)"
        if ($entry.Key -eq '3481843850') {
            throw 'Terminus is not installed exactly once. Subscribe to Workshop 3481843850 and let Steam finish downloading it.'
        }
        continue
    }

    $source = $matches[0]
    Add-Report "WORKSHOP: $($entry.Key) $($entry.Value) -> $source"
    $dest = Join-Path $Out ("Workshop\" + $entry.Key)
    Copy-TextFiles -Source $source -Destination $dest

    $treeFile = Join-Path $dest 'FILE-TREE.txt'
    Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction SilentlyContinue |
        Sort-Object FullName |
        ForEach-Object {
            $relative = [IO.Path]::GetRelativePath($source, $_.FullName)
            "$relative | $($_.Length)" | Add-Content -LiteralPath $treeFile -Encoding utf8
        }
}

$repoFiles = @(
    'phase-a-pack-policy.json',
    'campaign-planets.json',
    'scripts\prepare_pack.py',
    'scripts\proxy_export_world.py',
    'scripts\build_exported_proxies.py',
    'mods\ProxyExportBootstrap\Data\Scripts\ProxyExportBootstrap\ProxyExportBootstrapSession.cs',
    'mods\ProxyExportBootstrap\Data\Scripts\ProxyExportBootstrap\ProxyExportTargets.cs',
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\StaticSectorBootstrapSession.cs',
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\CampaignCelestialVisualsSession.cs'
)
foreach ($relative in $repoFiles) {
    $source = Join-Path $RepoRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
    $target = Join-Path (Join-Path $Out 'Repo') $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
Compress-Archive -Path (Join-Path $Root '*') -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ''
Write-Host 'Created Terminus proxy audit:' -ForegroundColor Green
Write-Host "  $Zip" -ForegroundColor Cyan
Write-Host ''
Write-Host 'Upload that ZIP here.'
