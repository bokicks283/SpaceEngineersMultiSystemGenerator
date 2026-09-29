#Requires -Version 7.0
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRoot = Join-Path $env:TEMP "SE-GasGiant-HUD-Diagnostics-$timestamp"
$zipPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) "Downloads\SE-GasGiant-HUD-Diagnostics-$timestamp.zip"

$save = Join-Path $env:APPDATA 'SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-28 20-48'
$seRoot = Join-Path $env:APPDATA 'SpaceEngineers'
$localRsg = Join-Path $seRoot 'Mods\RandomSectorGenerator'
$workshopRoot = 'S:\SteamLibrary\steamapps\workshop\content\244850'

function Add-FilePreserve {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Base,
        [Parameter(Mandatory)][string]$Bucket
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }

    $relative = [IO.Path]::GetRelativePath($Base, $Path)
    $dest = Join-Path $outRoot (Join-Path $Bucket $relative)
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item -LiteralPath $Path -Destination $dest -Force
}

function Add-TreeFiles {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Bucket,
        [string[]]$Extensions = @('.cs', '.xml', '.sbc')
    )

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return }

    Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object {
        $Extensions -contains $_.Extension.ToLowerInvariant()
    } | ForEach-Object {
        Add-FilePreserve -Path $_.FullName -Base $Root -Bucket $Bucket
    }
}

New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

$summary = [System.Collections.Generic.List[string]]::new()
$summary.Add("Generated: $(Get-Date -Format o)")
$summary.Add("Repo root: $PWD")
$summary.Add("Save: $save")
$summary.Add("")

# Git state
try {
    $head = git rev-parse HEAD 2>&1
    $branch = git branch --show-current 2>&1
    $status = git status --short 2>&1
    $summary.Add("Git branch: $branch")
    $summary.Add("Git HEAD: $head")
    $summary.Add("Git status:")
    if ($status) { $summary.AddRange([string[]]$status) } else { $summary.Add("  <clean>") }
} catch {
    $summary.Add("Git state unavailable: $($_.Exception.Message)")
}
$summary.Add("")

if (-not (Test-Path -LiteralPath $save -PathType Container)) {
    throw "Expected campaign save not found: $save"
}

# Save configs relevant to RSS / Real Stars / Real Gas Giants.
$saveFiles = @(
    'Sandbox.sbc',
    'Storage\3232085677.sbm_RealGasGiants\Config.xml',
    'Storage\3351055036.sbm_RealSolarSystems\Config.xml',
    'Storage\3152436752.sbm_RealSun\Config.xml',
    'Storage\RandomSectorGenerator_RandomSectorGenerator\RandomSectorStaticPlan.tsv',
    'Storage\RandomSectorGenerator_RandomSectorGenerator\RandomSectorStaticBootstrap.State.xml'
)

foreach ($rel in $saveFiles) {
    Add-FilePreserve -Path (Join-Path $save $rel) -Base $save -Bucket 'save'
}

# Extract concise giant/RSS evidence for easy review.
$giantsConfig = Join-Path $save 'Storage\3232085677.sbm_RealGasGiants\Config.xml'
if (Test-Path -LiteralPath $giantsConfig) {
    $summary.Add("=== Real Gas Giants config matches ===")
    Select-String -LiteralPath $giantsConfig -Pattern 'Saion|Koreus|DefaultBlackHole|DefaultJupiter|DefaultSaturn|Default1|Default2|Cauldron|Skin|PlanetName|PlanetCustomName' |
        ForEach-Object { $summary.Add(("[{0}] {1}" -f $_.LineNumber, $_.Line.Trim())) }
    $summary.Add("")
}

$rssConfig = Join-Path $save 'Storage\3351055036.sbm_RealSolarSystems\Config.xml'
if (Test-Path -LiteralPath $rssConfig) {
    $summary.Add("=== RSS matches for giants / Wyaris root ===")
    Select-String -LiteralPath $rssConfig -Pattern 'Saion Giant|Koreus Giant|Wyaris Abyss|RealGasGiant|PlanetOrbitZoneRadius|FunctionalZoneInfoConfig|SurfaceZone|OrbitZone' |
        ForEach-Object { $summary.Add(("[{0}] {1}" -f $_.LineNumber, $_.Line.Trim())) }
    $summary.Add("")
}

# Compare repository RSG source to installed local mod to catch stale installs.
$repoFiles = @(
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\StaticSectorBootstrapSession.cs',
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\CampaignCelestialVisualsSession.cs',
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\RealGasGiantsClient.cs',
    'mods\RandomSectorGenerator\Data\Scripts\RandomSectorGenerator\RealSolarSystemsClient.cs'
)

$summary.Add("=== Repo vs installed RSG hashes ===")
foreach ($repoRel in $repoFiles) {
    $repoPath = Join-Path $PWD $repoRel
    $installedRel = $repoRel -replace '^mods\\RandomSectorGenerator\\', ''
    $installedPath = Join-Path $localRsg $installedRel

    if (Test-Path -LiteralPath $repoPath) {
        Add-FilePreserve -Path $repoPath -Base $PWD -Bucket 'repo'
    }
    if (Test-Path -LiteralPath $installedPath) {
        Add-FilePreserve -Path $installedPath -Base $localRsg -Bucket 'installed-RandomSectorGenerator'
    }

    if ((Test-Path -LiteralPath $repoPath) -and (Test-Path -LiteralPath $installedPath)) {
        $repoHash = (Get-FileHash -LiteralPath $repoPath -Algorithm SHA256).Hash
        $installedHash = (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        $summary.Add("$installedRel")
        $summary.Add("  repo:      $repoHash")
        $summary.Add("  installed: $installedHash")
        $summary.Add("  match:     $($repoHash -eq $installedHash)")
    } else {
        $summary.Add("$installedRel")
        $summary.Add("  missing repo or installed copy")
    }
}
$summary.Add("")

# Latest runtime log, plus filtered evidence.
$latestLog = Get-ChildItem -LiteralPath $seRoot -Filter 'SpaceEngineers_*.log' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($latestLog) {
    Add-FilePreserve -Path $latestLog.FullName -Base $seRoot -Bucket 'logs'

    $summary.Add("Latest log: $($latestLog.FullName)")
    $summary.Add("=== Filtered latest-log evidence ===")
    Select-String -LiteralPath $latestLog.FullName -Pattern 'RSG|RealGas|Gas Giant|DefaultBlackHole|Saion|Koreus|RealSolar|RSS|Real Orbits|System Manager|horizon|distance|planet' |
        Select-Object -Last 600 |
        ForEach-Object { $summary.Add(("[{0}] {1}" -f $_.LineNumber, $_.Line.Trim())) }
    $summary.Add("")
}

# Workshop source for the systems most likely involved.
$mods = [ordered]@{
    '3232085677-RealGasGiants' = '3232085677'
    '3351055036-RealSolarSystems' = '3351055036'
    '2609118808-RealOrbits' = '2609118808'
    '3780085631-SystemManager' = '3780085631'
}

foreach ($entry in $mods.GetEnumerator()) {
    $root = Join-Path $workshopRoot $entry.Value
    if (Test-Path -LiteralPath $root) {
        $scriptRoot = Join-Path $root 'Data\Scripts'
        Add-TreeFiles -Root $scriptRoot -Bucket ("workshop\" + $entry.Key) -Extensions @('.cs')

        if ($entry.Value -eq '3232085677') {
            # Include Real Gas Giants data definitions too, where skins/defaults are usually declared.
            $dataRoot = Join-Path $root 'Data'
            if (Test-Path -LiteralPath $dataRoot) {
                Get-ChildItem -LiteralPath $dataRoot -Recurse -File | Where-Object {
                    $_.Extension.ToLowerInvariant() -in @('.xml', '.sbc')
                } | ForEach-Object {
                    Add-FilePreserve -Path $_.FullName -Base $root -Bucket ("workshop\" + $entry.Key)
                }
            }
        }
    } else {
        $summary.Add("Workshop mod folder missing: $root")
    }
}

$summaryPath = Join-Path $outRoot 'diagnostic-summary.txt'
$summary | Set-Content -LiteralPath $summaryPath -Encoding UTF8

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $outRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ''
Write-Host "Diagnostic ZIP created:"
Write-Host $zipPath
Write-Host ''
Write-Host 'Upload that ZIP here.'
