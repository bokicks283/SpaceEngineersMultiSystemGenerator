#Requires -Version 7.0
[CmdletBinding()]
param(
    [switch]$UseCachedCollection
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$backupRoot = Join-Path $repoRoot 'backups'
$spaceEngineersRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$localModRoot = Join-Path $spaceEngineersRoot 'Mods'
$globalStorageRoot = Join-Path $spaceEngineersRoot 'Storage'

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host "[$Label]"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
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

function Find-SpaceEngineers {
    $matches = foreach ($root in Get-SteamRoots) {
        $candidate = Join-Path $root 'steamapps\common\SpaceEngineers'
        if (Test-Path -LiteralPath (Join-Path $candidate 'Bin64\SpaceEngineers.exe') -PathType Leaf) {
            (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $matches = @($matches | Sort-Object -Unique)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one Space Engineers installation; found $($matches.Count): $($matches -join ', ')"
    }
    return $matches[0]
}

function Get-TreeManifest([string]$Root) {
    $resolved = (Resolve-Path -LiteralPath $Root).Path
    return @(Get-ChildItem -LiteralPath $resolved -Recurse -File | Sort-Object FullName | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($resolved, $_.FullName).Replace('\', '/')
        "$relative|$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
    })
}

function Test-TreesEqual([string]$Left, [string]$Right) {
    if (-not (Test-Path -LiteralPath $Left -PathType Container) -or
        -not (Test-Path -LiteralPath $Right -PathType Container)) { return $false }
    return -not (Compare-Object (Get-TreeManifest $Left) (Get-TreeManifest $Right))
}

function Install-Directory([string]$Name, [string]$Source, [string]$Destination, [string]$StageRoot, [string]$AllowedRoot) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Missing source: $Source" }
    $allowed = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $target = [IO.Path]::GetFullPath($Destination)
    if (-not $target.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace a directory outside $AllowedRoot`: $Destination"
    }
    if ((Test-Path -LiteralPath $Destination) -and (Test-TreesEqual $Source $Destination)) {
        Write-Host "Unchanged: $Destination"
        return
    }
    if (Test-Path -LiteralPath $Destination) {
        $zip = Join-Path $backupRoot "$Name-before-phase-a-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
        Compress-Archive -LiteralPath $Destination -DestinationPath $zip -CompressionLevel Optimal
        Write-Host "Backed up $Name to $zip"
    }
    $staged = Join-Path $StageRoot $Name
    Copy-Item -LiteralPath $Source -Destination $staged -Recurse
    if (-not (Test-TreesEqual $Source $staged)) { throw "Staging verification failed: $Name" }
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    Move-Item -LiteralPath $staged -Destination $Destination
    if (-not (Test-TreesEqual $Source $Destination)) { throw "Install verification failed: $Name" }
    Write-Host "Installed $Name to $Destination"
}

if (Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue) {
    throw 'Exit Space Engineers before installing Random Sector.'
}

$gameRoot = Find-SpaceEngineers
$customWorldRoot = Join-Path $gameRoot 'Content\CustomWorlds'
$randomSectorDest = Join-Path $customWorldRoot 'Random Sector'
New-Item -ItemType Directory -Force -Path $backupRoot, $localModRoot, $globalStorageRoot | Out-Null

Invoke-Checked 'Audit installed content' { py scripts\audit.py }
$policy = Get-Content (Join-Path $repoRoot 'phase-a-pack-policy.json') -Raw | ConvertFrom-Json
$collectionArgs = @('scripts\steam_collection.py', '--collection-id', $policy.collection_id)
if ($UseCachedCollection) { $collectionArgs += '--use-cache' }
Invoke-Checked 'Resolve Steam collection' { py @collectionArgs }
Invoke-Checked 'Prepare selected pack' { py scripts\prepare_pack.py }

$plan = Get-Content (Join-Path $repoRoot 'reports\pack-plan.json') -Raw | ConvertFrom-Json
$voxel = Get-Content (Join-Path $repoRoot 'reports\selected-voxel-audit.json') -Raw | ConvertFrom-Json
$coverage = Get-Content (Join-Path $repoRoot 'reports\coverage.json') -Raw | ConvertFrom-Json
$collection = Get-Content (Join-Path $repoRoot 'reports\steam-collection.json') -Raw | ConvertFrom-Json
if ([int]$voxel.total -gt [int]$voxel.budget) {
    throw "Voxel material count $($voxel.total) exceeds Phase A budget $($voxel.budget)"
}
if ([int]$voxel.total -ge [int]$policy.engine_voxel_limit) {
    throw "Voxel material count $($voxel.total) reaches/exceeds engine limit $($policy.engine_voxel_limit)"
}
$selectedCoverage = @($coverage | Where-Object selected)
if ($selectedCoverage.Count -ne 18) { throw "Expected 18 selected planets; found $($selectedCoverage.Count)" }
$badCoverage = @($selectedCoverage | Where-Object { [int]$_.active_proxy_count -ne 1 })
if ($badCoverage.Count) { throw "Proxy coverage is not exactly one for: $($badCoverage.planet -join ', ')" }

$generatedProxyDefinition = Join-Path $repoRoot 'generated\CampaignPlanetProxies\Data\PlanetProxyDefaults.sbc'
$terminusProxyId = '<SubtypeId>PlanetProxyType_Terminus (Black Hole)</SubtypeId>'
if (-not (Test-Path -LiteralPath $generatedProxyDefinition -PathType Leaf) -or
    -not (Get-Content -LiteralPath $generatedProxyDefinition -Raw).Contains($terminusProxyId)) {
    throw 'Generated CampaignPlanetProxies is missing the Terminus (Black Hole) RSS proxy. Complete the proxy export/build workflow before installing Random Sector.'
}

foreach ($mod in $plan.selected_workshop) {
    if (-not (Test-Path -LiteralPath $mod.path -PathType Container)) {
        throw "Required Workshop mod is not installed: $($mod.id) $($mod.title)"
    }
}

Invoke-Checked 'Patch Terminus accretion-disk rotation' { py scripts\apply_terminus_rotation.py }
Invoke-Checked 'Sync pending RSG save mod lists' { py scripts\sync_pending_world_mods.py }

Write-Host ''
Write-Host "Steam collection: $($plan.collection_id)"
Write-Host "Collection items: $($collection.items.Count)"
foreach ($item in $collection.items) {
    $label = if ($item.active) { 'INCLUDED' } elseif ($item.classification -in @('phase_a_planet_deferred', 'collection_non_world_content')) { 'EXCLUDED' } else { 'BLOCKED' }
    $reason = if ($item.active) { $item.classification } else { $item.exclusion_reason }
    Write-Host ("{0}: {1} - {2} ({3})" -f $label, $item.id, $item.title, $reason)
}
$normalActive = @($collection.items | Where-Object { $_.active -and $_.classification -eq 'normal_collection_mod' }).Count
$planetActive = @($collection.items | Where-Object { $_.active -and $_.classification -eq 'phase_a_planet' }).Count
$planetDeferred = @($collection.items | Where-Object classification -eq 'phase_a_planet_deferred').Count
Write-Host ''
Write-Host "Normal collection mods active: $normalActive"
Write-Host "Phase A planet mods active: $planetActive"
Write-Host "Planet catalog items deferred: $planetDeferred"
Write-Host "Dependencies added: $($plan.dependency_additions.Count)"
Write-Host "Local RSG mods: $($plan.local.Count)"
Write-Host "Voxel materials: $($voxel.total) / $($voxel.budget) Phase A budget"

Invoke-Checked 'Offline compile' { pwsh -NoProfile -File scripts\Build-RSG.ps1 }

$stageRoot = Join-Path $env:TEMP ("RandomSectorInstaller-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stageRoot | Out-Null
try {
    $localSources = [ordered]@{
        RandomSectorGenerator = Join-Path $repoRoot 'mods\RandomSectorGenerator'
        CampaignScienceCompatibility = Join-Path $repoRoot 'mods\CampaignScienceCompatibility'
        CampaignPlanetProxies = Join-Path $repoRoot 'generated\CampaignPlanetProxies'
    }
    foreach ($entry in $localSources.GetEnumerator()) {
        Install-Directory $entry.Key $entry.Value (Join-Path $localModRoot $entry.Key) $stageRoot $localModRoot
    }

    $rtsSource = Join-Path $repoRoot 'profiles\RelativeTopSpeed.cfg'
    [xml]$rts = Get-Content -LiteralPath $rtsSource -Raw
    if ($rts.Settings.SpeedLimit -ne '5000' -or $rts.Settings.RemoteControlSpeedLimit -ne '1000') {
        throw 'Locked RTS profile is not 5000/1000'
    }
    $rtsDestDir = Join-Path $globalStorageRoot '1359618037.sbm_RelativeTopSpeed'
    $rtsDest = Join-Path $rtsDestDir 'RelativeTopSpeed.cfg'
    New-Item -ItemType Directory -Force -Path $rtsDestDir | Out-Null
    if ((Test-Path -LiteralPath $rtsDest) -and
        ((Get-FileHash $rtsDest).Hash -ne (Get-FileHash $rtsSource).Hash)) {
        Copy-Item -LiteralPath $rtsDest -Destination (Join-Path $backupRoot "RelativeTopSpeed-before-phase-a-$(Get-Date -Format yyyyMMdd-HHmmss).cfg")
    }
    Copy-Item -LiteralPath $rtsSource -Destination $rtsDest -Force
    if ((Get-FileHash $rtsDest).Hash -ne (Get-FileHash $rtsSource).Hash) { throw 'RTS profile install verification failed' }

    $templateStage = Join-Path $stageRoot 'Random Sector'
    Invoke-Checked 'Build Random Sector CustomWorld' {
        py scripts\random_sector_custom_world.py build --game-root $gameRoot --output $templateStage
    }
    Install-Directory 'Random-Sector-CustomWorld' $templateStage $randomSectorDest $stageRoot $customWorldRoot
    Invoke-Checked 'Validate installed Random Sector' {
        py scripts\random_sector_custom_world.py validate $randomSectorDest
    }

    # Exercise two independent copies and prove the reusable source is unchanged.
    $sourceManifestBefore = Get-TreeManifest $randomSectorDest
    $copyOne = Join-Path $stageRoot 'FreshWorldOne'
    $copyTwo = Join-Path $stageRoot 'FreshWorldTwo'
    Copy-Item -LiteralPath $randomSectorDest -Destination $copyOne -Recurse
    Copy-Item -LiteralPath $randomSectorDest -Destination $copyTwo -Recurse
    if (-not (Test-TreesEqual $copyOne $copyTwo)) { throw 'Fresh template copy comparison failed' }
    Invoke-Checked 'Validate first fresh copy' { py scripts\random_sector_custom_world.py validate $copyOne }
    Invoke-Checked 'Validate second fresh copy' { py scripts\random_sector_custom_world.py validate $copyTwo }
    if (Compare-Object $sourceManifestBefore (Get-TreeManifest $randomSectorDest)) {
        throw 'Installed Random Sector changed while testing fresh copies'
    }
}
finally {
    $resolvedTemp = (Resolve-Path -LiteralPath $env:TEMP).Path
    $resolvedStage = (Resolve-Path -LiteralPath $stageRoot -ErrorAction SilentlyContinue).Path
    if ($resolvedStage -and $resolvedStage.StartsWith($resolvedTemp + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}

Write-Host ''
Write-Host 'Random Sector Phase A is installed.' -ForegroundColor Green
Write-Host 'Next:'
Write-Host '1. Launch Space Engineers and create a fresh Random Sector world.'
Write-Host '2. Wait for static generation to complete; the setup character remains at the original safe spawn.'
Write-Host '3. Save, exit to menu, and reload that same save.'
Write-Host '4. Run /AddStrayPlanets. Do not use planetary respawn entries during bootstrap.'
Write-Host '5. Verify adopted bodies in /TSE without manually assigning hierarchy, then save and exit Space Engineers.'
Write-Host '6. Run Collect-RSG-TestDiagnostics.ps1 so RSS config + RandomSectorStaticPlan can be inspected for automated hierarchy setup.'
Write-Host '7. Only after RSS hierarchy is verified: /SetupRealOrbits, Economy, final starter/crash scenario.'
Write-Host 'Economy remains OFF during bootstrap.'
