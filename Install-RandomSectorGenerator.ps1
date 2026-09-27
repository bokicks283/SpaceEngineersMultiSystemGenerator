#Requires -Version 7.0
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if (Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue) { throw 'Exit Space Engineers before replacing local mods.' }
$modRoot=Join-Path $env:APPDATA 'SpaceEngineers\Mods'
$backupRoot=Join-Path $PSScriptRoot 'backups'
New-Item -ItemType Directory -Force -Path $modRoot,$backupRoot | Out-Null
foreach ($name in @('RandomSectorGenerator','CampaignScienceCompatibility')) {
    $source=Join-Path $PSScriptRoot "mods\$name"
    $dest=Join-Path $modRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Missing source: $source" }
    if (Test-Path -LiteralPath $dest) {
        $zip=Join-Path $backupRoot "$name-before-install-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
        Compress-Archive -LiteralPath $dest -DestinationPath $zip -CompressionLevel Optimal
        Write-Host "Backed up $name to $zip"
    }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
        $relative=[IO.Path]::GetRelativePath($source,$file.FullName)
        $target=Join-Path $dest $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
            throw "Install verification failed: $target"
        }
    }
    Write-Host "Installed $name to $dest"
}
