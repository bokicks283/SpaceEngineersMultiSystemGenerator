param([string]$GameBin)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$GameBin) {
    $inventory = Get-Content (Join-Path $root 'reports/inventory.json') -Raw | ConvertFrom-Json
    $GameBin = Join-Path $inventory.games[0].path 'Bin64'
}
$out = Join-Path $root 'build'
New-Item -ItemType Directory -Force $out | Out-Null
$report=Join-Path $root 'reports/build-rsg.txt'
'' | Set-Content -LiteralPath $report
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$refs = @('Sandbox.Common','Sandbox.Game','SpaceEngineers.Game','VRage','VRage.Game','VRage.Library','VRage.Math','VRage.Render','VRage.Scripting','VRage.Input','VRage.Render11','ProtoBuf.Net','ProtoBuf.Net.Core','System.Collections.Immutable')
$argsList = @('/nologo','/target:library',('/out:' + (Join-Path $out 'RandomSectorGenerator.dll')))
$argsList += '/reference:C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework\v4.8.1\Facades\netstandard.dll'
foreach ($ref in $refs) { $argsList += '/reference:' + (Join-Path $GameBin ($ref + '.dll')) }
$argsList += Get-ChildItem (Join-Path $root 'mods/RandomSectorGenerator/Data/Scripts') -Recurse -Filter *.cs | ForEach-Object FullName
& $compiler @argsList 2>&1 | Tee-Object -Append $report
if ($LASTEXITCODE -ne 0) { throw 'RSG compile check failed' }
'Offline CLR compilation passed. In-game script whitelist and runtime validation are still required.' | Tee-Object -Append $report
