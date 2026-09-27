# Proxy workbench launch repair — 2026-09-27

Confirmed Space Engineers was closed. The initial worktree was clean on
`finish-rsg-bootstrap`; after fetching, HEAD and origin both pointed to
`dddbf2923c04d3624ed5644550ca88511c295ef8`. No reset or checkout was performed.

## Cause and evidence

`SpaceEngineers_20260927_033923799.log`, lines 494–550, records checkpoint
deserialization failing with `Namespace prefix 'xsd' is not defined`, followed
by the exact workbench `Sandbox.sbc` path and the world-load error.
The stack passes through `Read2458_EntryOfStringObject` and
`Read2460_MyObjectBuilder_ScriptManager`, before mod initialization.

The original Empty World declares `xmlns:xsd`. The workbench preparation script
used ElementTree's plain writer, which dropped that declaration while preserving
`xsi:type="xsd:string"` on copied script variables. Ordinary XML parsing accepts
this document, but the game's typed deserializer cannot resolve those values.

Both workbench mod lists agree: Planet Exporter (3350589349), Water Mod
(2200451495), Zenitaia (3695766186), Relicta (3489648084), and local
ProxyExportBootstrap. All installed directories exist; the helper's installed
source matches the repository byte for byte. The sector contains one character
and no planets, and matches the source sector byte for byte. World Storage is
absent. This launch failed before those mods could initialize; it does not
establish their runtime compatibility.

## Repair

Preparation now uses the existing `world_checkpoint.write_atomic` writer, which
preserves the xsd declaration. Added `repair` (closed-game check and archive
before writing) and read-only `validate` commands to `proxy_export_world.py`.
Validation checks scoped xsi:type prefixes as well as both mod lists, Creative
mode, sector XML, session name, and installed mod directories.

The live workbench's checkpoint and configuration were repaired in place.
No reset, planet respawn, mod source change, or Workshop edit was needed.

Backups relative to the repository:

- `backups/ProxyExportWorkbench-before-namespace-repair-20260927-131812.zip`
  contains the complete pre-repair workbench.
- `backups/Workbench-diagnostic-evidence-20260927-131811.zip` preserves prior
  reports, generated files, and the complete failed-launch log.

## Validation and next launch

- The new namespace validator rejects the original broken checkpoint.
- Repair and repeated serialization pass, preserving parsed XML content.
- `py scripts/proxy_export_world.py validate` passes on the repaired workbench.
- `scripts/Build-RSG.ps1` passes offline CLR compilation for both RSG and
  ProxyExportBootstrap. In-game whitelist and runtime checks remain pending.
- `reports/runtime-check.json` now captures the failed workbench launch; it is
  pre-repair evidence, not evidence of a successful post-repair launch.

Load **Proxy Export Workbench 2026-09-27**, wait for the two planets, and run
`/pex status`. If both are ready, save and exit. The next runtime log must confirm
successful loading and bootstrap execution before proceeding to export setup.
