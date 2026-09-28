#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Downloads = Join-Path $HOME 'Downloads'
$Root = Join-Path $env:TEMP "RSG-TestDiagnostics-$Stamp"
$Out = Join-Path $Root 'Collected'
$Zip = Join-Path $Downloads "RSG-TestDiagnostics-$Stamp.zip"

New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Copy-WithRelativePath {
    param(
        [Parameter(Mandatory)] [string]$File,
        [Parameter(Mandatory)] [string]$Base,
        [Parameter(Mandatory)] [string]$Destination
    )
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { return }
    $relative = [IO.Path]::GetRelativePath($Base, $File)
    $target = Join-Path $Destination $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $File -Destination $target -Force
}

$seRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$report = Join-Path $Root 'REPORT.txt'
"Random Sector Generator test diagnostics" | Set-Content $report
"Generated: $(Get-Date -Format o)" | Add-Content $report
"" | Add-Content $report

# Current Space Engineers builds use timestamped log names. Collect the
# newest few so the exact failed run is preserved even if another launch occurs.
$logCandidates = @(
    Get-ChildItem -LiteralPath $seRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'SpaceEngineers*.log' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 5
)
foreach ($entry in $logCandidates) {
    Copy-WithRelativePath -File $entry.FullName -Base $seRoot -Destination (Join-Path $Out 'AppData-SpaceEngineers')
    "LOG: $($entry.FullName)" | Add-Content $report
}

Get-ChildItem -LiteralPath $seRoot -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match 'crash|exception|minidump' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 10 |
    ForEach-Object {
        Copy-WithRelativePath -File $_.FullName -Base $seRoot -Destination (Join-Path $Out 'AppData-SpaceEngineers')
    }

# Exact installed local mod source.
$localMod = Join-Path $seRoot 'Mods\RandomSectorGenerator'
if (Test-Path -LiteralPath $localMod) {
    Copy-Item -LiteralPath $localMod -Destination (Join-Path $Out 'LocalMod') -Recurse -Force
    "LOCAL MOD: $localMod" | Add-Content $report
} else {
    "LOCAL MOD MISSING: $localMod" | Add-Content $report
}

# Find RSG state/manifest in saves. These identify the bootstrap save without
# requiring the user to know which generated Storage subfolder SE chose.
$saveRoot = Join-Path $seRoot 'Saves'
$matchingFiles = @()
if (Test-Path -LiteralPath $saveRoot) {
    $matchingFiles += Get-ChildItem -LiteralPath $saveRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @(
                'RandomSectorGenerator.State.xml',
                'RandomSectorGenerator.Manifest.txt'
            )
        }
}

$worldDirs = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

foreach ($file in $matchingFiles) {
    Copy-WithRelativePath -File $file.FullName -Base $saveRoot -Destination (Join-Path $Out 'Saves')
    "RSG WORLD FILE: $($file.FullName)" | Add-Content $report

    # Walk upward until we reach the directory directly below the SteamID folder.
    # We then independently search parent candidates for Sandbox.sbc.
    $dir = $file.Directory
    while ($null -ne $dir -and $dir.FullName.StartsWith($saveRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath (Join-Path $dir.FullName 'Sandbox.sbc')) {
            [void]$worldDirs.Add($dir.FullName)
            break
        }
        $dir = $dir.Parent
    }
}

# If RSG never got far enough to write state, also consider the most recently
# modified saves so compile/startup failures still have useful world config.
if ($worldDirs.Count -eq 0 -and (Test-Path -LiteralPath $saveRoot)) {
    Get-ChildItem -LiteralPath $saveRoot -Directory -Recurse -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'Sandbox.sbc') } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 3 |
        ForEach-Object { [void]$worldDirs.Add($_.FullName) }
}

foreach ($world in $worldDirs) {
    "WORLD: $world" | Add-Content $report

    foreach ($name in @('Sandbox.sbc', 'Sandbox_config.sbc')) {
        $file = Join-Path $world $name
        if (Test-Path -LiteralPath $file) {
            Copy-WithRelativePath -File $file -Base $saveRoot -Destination (Join-Path $Out 'Saves')
        }
    }

    # RSS and related configs/state files are small; collect matching Storage text/XML.
    $storage = Join-Path $world 'Storage'
    if (Test-Path -LiteralPath $storage) {
        Get-ChildItem -LiteralPath $storage -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Extension -in @('.xml', '.txt') -and (
                    $_.FullName -match 'RealSolar|3351055036|RandomSector|RealStars|RealGas'
                )
            } |
            ForEach-Object {
                Copy-WithRelativePath -File $_.FullName -Base $saveRoot -Destination (Join-Path $Out 'Saves')
            }
    }
}

# Relevant log excerpts are convenient for a fast first read, while the full log
# remains included above.
$mainLog = $logCandidates | Select-Object -First 1
if ($null -ne $mainLog) {
    $patterns = 'Random Sector Generator|\[RSG\]|MOD_ERROR|Compilation|compile|Exception|RealSolarSystems|Real Solar Systems|RealGasGiants|Real Stars|starter|proxy|zone|gravity|teleport|recover'
    Select-String -LiteralPath $mainLog.FullName -Pattern $patterns -CaseSensitive:$false -ErrorAction SilentlyContinue |
        Select-Object -Last 2500 |
        ForEach-Object { $_.Line } |
        Set-Content -LiteralPath (Join-Path $Root 'RelevantLogExcerpt.txt') -Encoding utf8
}

New-Item -ItemType Directory -Force -Path $Downloads | Out-Null
if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
Compress-Archive -Path (Join-Path $Root '*') -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ""
Write-Host "Created diagnostics:" -ForegroundColor Green
Write-Host "  $Zip" -ForegroundColor Cyan
Write-Host ""
Write-Host "Upload that ZIP to the Random Sector Generator thread."
