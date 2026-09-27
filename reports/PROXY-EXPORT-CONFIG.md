# Planet Exporter config repair — 2026-09-27

The workbench successfully loaded and created
`Storage/3350589349.sbm_PlanetUnwrapper/Config.xml`. Its first bytes are ASCII
`<?xml version="1.0" encoding="utf-16"?>` followed by ordinary single-byte XML;
there is no BOM or UTF-16 NUL pattern. UTF-8 decodes the complete file. The
declaration contradicts the bytes, so Python's XML parser rejected it before
`configure` could change any settings.

`scripts/proxy_export_world.py` now parses normal XML directly. For the specific
case of an ASCII-compatible UTF-8 document that falsely declares UTF-16/32, it
corrects the declaration in memory and parses it. It writes UTF-8 with a matching
declaration, preserving the exporter's namespace declarations. It checks the
actual installed schema before editing: `SamplingWidth`, `SamplingHeight`, the
three `ScaleReductionTex*` fields, and `ModdedVoxelInfoList` entries with
`VoxelName`, `VoxelColor` attributes X/Y/Z, `VoxelGloss`, and `VoxelAdditive`.
Existing entries are updated in place; unrelated entries and settings stay intact.

The ten custom voxel names were checked against the installed Zenitaia and
Relicta `VoxelMaterials.sbc` files. CM textures were downsampled to 64x64 for
representative base colors where the source files exist. Zenitaia's sand uses a
vanilla sand texture, so its color follows the exporter's vanilla sand preset.
Lava and hot materials receive authored additive values because this exporter
accepts one glow scalar per subtype. Final visual appearance needs an in-game
inspection after export.

The exact failing config was tested in a temporary copy: parse, rewrite, parse
again, and repeat rewrite all passed. Correct UTF-16, correct UTF-8, and UTF-8
with a BOM plus a wrong UTF-16 declaration were also exercised. The live
workbench config has been updated. Its complete original is archived at
`backups/PlanetExporter-config-before-campaign-patch-20260927-152936.zip`.
The rewritten file parses, declares UTF-8, preserves all unrelated top-level
settings and all 62 vanilla voxel entries, and contains exactly one configured
entry for each selected custom material.

The installed Planet Exporter source accepts `/ReloadConfig` and `/ReloadColors`.
The workbench's source and save remain isolated from the campaign save.
The successful game load added installed Text HUD API (`758597413`) to both
workbench mod lists and set the local helper's service name to `Steam`; static
validation now accepts that observed game serialization.

No Zenitaia or Relicta TGA exports exist yet. After the user exports CM, NG,
and ADD for each world, run `py scripts/build_exported_proxies.py build` and
`py scripts/prepare_pack.py`, then inspect all generated DDS files, RSS texture
references, coverage, and voxel totals before arming any campaign world.
