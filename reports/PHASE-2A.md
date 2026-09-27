# Phase 2A planet expansion — 2026-09-27

The selected pool has **19 / 24** RSG planet definitions: 8 vanilla and 11
custom. The static voxel material union remains **117 / 128** (62 vanilla,
55 additions, 11 spare). The runtime safety budget remains 120. No new voxel
materials are contributed by the three selected Workshop candidates.

| Candidate | Workshop ID | Actual generator subtype | Increment | Science | Active proxy |
|---|---:|---|---:|---|---:|
| Kerbin | 2941085186 | Kerbin - Water Mod Ready | 0 | local preset | 0 |
| Aulden | 2961923776 | Aulden | 0 | local preset | 0 |
| Seren | 2961924256 | Seren | 0 | local preset | 0 |

All three are installed locally, with no dependencies declared in local
`metadata.mod` files. Their SBCs define no voxel materials; every material
they reference is in the current selected union. Kerbin's package also loads
`Kerbin - Vanilla Version`, which RSG deliberately excludes. The selected
water-ready variant changes seabed layers, but actual Water Mod behavior must
be checked in game. Aulden has 0.82 surface gravity; Seren has 2.80, an
extreme-hot temperature setting, and an ice surface. They add distinct terrain
and hazard profiles without spending material slots. No locally installed
distinctive +1/+2 material candidate was found, so five of the 24 definition
slots remain free.

`campaign-planets.json` now owns the selected vanilla, required custom, and
optional custom subtype lists. `prepare_pack.py` generates the RSG pool source
and the workbench export-target source from that manifest and proxy coverage.
`analyze_planet_candidates.py` accepts arbitrary installed Workshop IDs for
future cost, science, water-terrain, and proxy checks.

The added vanilla generator subtypes are Alien, Titan, Triton, and Pertam.
RSS itself supplies one active proxy for each of the eight vanilla planets.
The installed vanilla HD proxy pack **3381681547** supplies eight more, so it
remains inactive to prevent duplicate definitions. It is **not** a required
subscription. All four newly added vanilla worlds have native Scientific
Progress presets.

Active proxy coverage is **14 / 19**: 13 from active Workshop mods and one
Jormun proxy in the local generated mod. Five selected worlds need export in
one batch: **Zenitaia, Relicta, Kerbin - Water Mod Ready, Aulden, Seren**.
There are no duplicate active proxies. The source Workshop proxy for Jormun
remains intact. Science coverage is **12 native** and **7 local authored**.
No new Workshop subscriptions are required.

The existing proxy workbench was archived to
`backups/ProxyExportWorkbench-before-pool-sync-20260927-160436.zip` and
expanded in place. Its previously spawned Zenitaia/Relicta planets, saved
sector, and Planet Exporter config remain present. The installed helper was
replaced with the generated five-target version. The disarmed disposable
audit world was archived to
`backups/World-before-disposable-sync-20260927-160828.zip` and synced to the
39-mod selected list. Its checkpoint remains `blocked-proxies`; no sector was
generated or armed. Planet Exporter is only in the isolated workbench.

Offline RSG and helper compilation, `verify_local.py`, workbench validation,
material union, science presence, and proxy uniqueness pass. The expanded
planet pool and the three new export targets have not yet been tested in game.
The CM/NG/ADD TGA files for the five missing proxies do not exist yet.
