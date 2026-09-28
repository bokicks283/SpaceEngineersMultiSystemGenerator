#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$SaveName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Downloads = Join-Path $HOME 'Downloads'
$Root = Join-Path $env:TEMP "RSG-Finalization-$Stamp"
$Out = Join-Path $Root 'Collected'
$Zip = Join-Path $Downloads "RSG-Finalization-$Stamp.zip"
$SeRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$SaveRoot = Join-Path $SeRoot 'Saves'
$Report = Join-Path $Root 'REPORT.txt'

New-Item -ItemType Directory -Force -Path $Out, $Downloads | Out-Null

function Add-Report([string]$Text = '') {
    $Text | Add-Content -LiteralPath $Report -Encoding utf8
}

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

function Get-CampaignWorlds {
    if (-not (Test-Path -LiteralPath $SaveRoot -PathType Container)) { return @() }

    $all = @(
        Get-ChildItem -LiteralPath $SaveRoot -Directory -Recurse -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'Sandbox.sbc') }
    )

    if ($SaveName) {
        $named = @($all | Where-Object { $_.Name -eq $SaveName })
        if ($named.Count -ne 1) {
            throw "Expected exactly one save named '$SaveName'; found $($named.Count)"
        }
        return $named
    }

    $campaign = @(
        $all | Where-Object {
            $storage = Join-Path $_.FullName 'Storage'
            if (-not (Test-Path -LiteralPath $storage -PathType Container)) { return $false }
            @(Get-ChildItem -LiteralPath $storage -Recurse -File -Filter 'RandomSectorStaticPlan.tsv' -ErrorAction SilentlyContinue).Count -gt 0
        } | Sort-Object LastWriteTime -Descending
    )

    if ($campaign.Count -eq 0) {
        return @($all | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
    }

    return @($campaign | Select-Object -First 2)
}

"RSG finalization collection" | Set-Content -LiteralPath $Report -Encoding utf8
Add-Report "Generated: $(Get-Date -Format o)"
Add-Report "Space Engineers root: $SeRoot"
Add-Report

if (Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue) {
    Add-Report 'WARNING: Space Engineers was running while this collector executed.'
}

$logs = @(
    Get-ChildItem -LiteralPath $SeRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'SpaceEngineers*.log' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 3
)
foreach ($log in $logs) {
    Copy-WithRelativePath -File $log.FullName -Base $SeRoot -Destination (Join-Path $Out 'AppData-SpaceEngineers')
    Add-Report "LOG: $($log.FullName)"
}

$mainLog = $logs | Select-Object -First 1
if ($null -ne $mainLog) {
    $patterns = @(
        'MOD_ERROR','Exception','RelativeTopSpeed','Real Orbits','RealisticGravity',
        'RealSolar','Real Solar Systems','RealStars','Real Stars','RealGas',
        'MES','Modular Encounters','AiEnabled','Crew Enabled','Assertive',
        'RCSP','Daily Needs','Damaged Spawn','Kinetic','Bigger Explosions',
        'HyperDrive','JumpDrive','Creature','Populated Worlds'
    )
    Select-String -LiteralPath $mainLog.FullName -Pattern ($patterns -join '|') -CaseSensitive:$false -ErrorAction SilentlyContinue |
        Select-Object -Last 5000 |
        ForEach-Object { $_.Line } |
        Set-Content -LiteralPath (Join-Path $Root 'RelevantLogExcerpt.txt') -Encoding utf8
}

$worlds = @(Get-CampaignWorlds)
foreach ($world in $worlds) {
    Add-Report
    Add-Report "WORLD: $($world.FullName)"

    foreach ($name in @('Sandbox.sbc','Sandbox_config.sbc','SANDBOX_0_0_0_.sbs')) {
        $file = Join-Path $world.FullName $name
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            Copy-WithRelativePath -File $file -Base $SaveRoot -Destination (Join-Path $Out 'Saves')
        }
    }

    $storage = Join-Path $world.FullName 'Storage'
    if (Test-Path -LiteralPath $storage -PathType Container) {
        Get-ChildItem -LiteralPath $storage -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Extension -in @('.xml','.cfg','.txt','.tsv','.json') -and
                $_.Length -lt 10MB
            } |
            ForEach-Object {
                Copy-WithRelativePath -File $_.FullName -Base $SaveRoot -Destination (Join-Path $Out 'Saves')
            }
    }
}

foreach ($base in @(
    (Join-Path $SeRoot 'Storage'),
    (Join-Path $SeRoot 'Mods')
)) {
    if (-not (Test-Path -LiteralPath $base -PathType Container)) { continue }
    Get-ChildItem -LiteralPath $base -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @(
                'RelativeTopSpeed.cfg','dragsettings.xml','FSDriveConfig.cfg',
                'Config.xml','Settings.xml','settings.cfg'
            ) -and $_.Length -lt 5MB
        } |
        ForEach-Object {
            Copy-WithRelativePath -File $_.FullName -Base $SeRoot -Destination (Join-Path $Out 'AppData-SpaceEngineers')
        }
}

$mods = [ordered]@{
    '1359618037' = 'Relative Top Speed'
    '571920453'  = 'Aerodynamic Physics'
    '2609118808' = 'Real Orbits'
    '3152436752' = 'Real Stars'
    '3232085677' = 'Real Gas Giants'
    '3351055036' = 'Real Solar Systems'
    '2760086069' = 'HyperDrive'
    '2649159807' = 'Kinetic Devastation'
    '2667547195' = 'Bigger Explosions'
    '2802482180' = 'Damaged Spawnships'
    '1608841667' = 'Daily Needs Survival Kit'
    '2747715235' = 'Populated Worlds Creatures'
    '1521905890' = 'Modular Encounters Systems'
    '2596208372' = 'AiEnabled'
    '2803081060' = 'Crew Enabled'
    '1902970975' = 'Assertive Combat Systems'
    '3719498498' = 'RCSP Ground Assault'
    '3672452327' = 'RCSP Encounters'
}

foreach ($entry in $mods.GetEnumerator()) {
    $matches = @(Find-WorkshopMod $entry.Key)
    if ($matches.Count -eq 0) {
        Add-Report "WORKSHOP MISSING: $($entry.Key) $($entry.Value)"
        continue
    }

    foreach ($modRoot in $matches) {
        Add-Report "WORKSHOP: $($entry.Key) $($entry.Value) -> $modRoot"
        $dest = Join-Path $Out ("Workshop\" + $entry.Key)

        Get-ChildItem -LiteralPath $modRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Extension -in @('.cs','.sbc','.xml','.cfg','.ini','.txt','.md','.json') -and
                $_.Length -lt 5MB
            } |
            ForEach-Object {
                Copy-WithRelativePath -File $_.FullName -Base $modRoot -Destination $dest
            }

        foreach ($meta in @('metadata.mod','modinfo.sbmi')) {
            $file = Join-Path $modRoot $meta
            if (Test-Path -LiteralPath $file -PathType Leaf) {
                Copy-WithRelativePath -File $file -Base $modRoot -Destination $dest
            }
        }
    }
}

$localMods = Join-Path $SeRoot 'Mods'
if (Test-Path -LiteralPath $localMods -PathType Container) {
    foreach ($name in @('RandomSectorGenerator','CampaignScienceCompatibility','CampaignPlanetProxies')) {
        $dir = Join-Path $localMods $name
        if (Test-Path -LiteralPath $dir -PathType Container) {
            Copy-Item -LiteralPath $dir -Destination (Join-Path $Out "LocalMods\$name") -Recurse -Force
            Add-Report "LOCAL MOD: $dir"
        }
    }
}

if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip -Force }
Compress-Archive -Path (Join-Path $Root '*') -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ''
Write-Host 'Created finalization bundle:' -ForegroundColor Green
Write-Host "  $Zip" -ForegroundColor Cyan
Write-Host ''
Write-Host 'Upload that ZIP here. It contains text/config/source only; large Workshop assets are omitted.'
