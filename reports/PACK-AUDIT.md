# Selected pack audit

Static voxel total: **117** = 62 vanilla + 55 additions; **11** headroom against 128 and 3 below the conservative budget of 120. Runtime validation pending.

| Body | Selected | Active RSS proxies | Science |
|---|---|---:|---|
| Agni | yes | 1 | native |
| Cauldron | yes | 1 | local authored preset |
| Kor | yes | 1 | native |
| Tellus | yes | 1 | native |
| Teal-WaterMod | no | 0 | native |
| Teralis - City Planet | no | 0 | native |
| Jormun | yes | 1 | local authored preset |
| Zenitaia | yes | 0 | local authored preset |
| OrlundaSide | yes | 1 | native |
| Komorebi | no | 1 | native |
| Nivis | no | 0 | generic fallback |
| Relicta | yes | 0 | local authored preset |
| Sulfate | no | 0 | generic fallback |
| unavailable | no | 0 | unavailable |

## Workshop load-list membership

- 3791989881 — Yoink!
- 2200451495 — Water Mod
- 3222232482 — Visual Overrides API
- 758597413 — Text HUD API
- 3240629702 — Solar Blocks Override
- 2841920953 — Shower Light
- 3665099597 — Scientific Progress
- 1965654081 — Rich HUD Master
- 3746220940 — Resource Node Miner
- 3152436752 — Real Stars
- 3351055036 — Real Solar Systems
- 3232085677 — Real Gas Giants
- 3695766186 — Planet Zenitaia
- 3489648084 — Planet Relicta
- 3618043241 — Planet - Jormun (Water)
- 3741238881 — Pipes Junctions
- 3736894294 — Monorail Tracks
- 1521905890 — Modular Encounters Systems
- 3731921987 — Malware's Docking Aid
- 2839553181 — In Depth LCDs
- 3770315903 — Humanoid's Retractable Solar Panels
- 3767444521 — Handheld Hacker Grid Takeover (Version 1.6)
- 3576683005 — Cauldron System
- 2336089504 — Bot_spawner
- 3218645300 — Asteroid Filter API
- 2391318591 — Assertive Loot
- 3155707452 — Assertive Combat Systems Dependency
- 1902970975 — Assertive Combat Systems
- 3784633330 — AQD - LCD Color Profiles
- 3472275442 — AQD - Conveyored Pipes
- 2596208372 — AiEnabled v1.9
- 2310821218 — Abandoned Settlements [v2]
- 3362332228 — Orlunda (Sideways)
- 3690317665 — AquaExpansion
- 2899106264 — Terran Titans Naval Blocks
- 3361803398 — title unavailable locally

## Local mods

- RandomSectorGenerator: one-shot armed disposable-world bootstrap, pending RSS checkpoint handoff, spoiler manifest.
- CampaignScienceCompatibility: authored Cauldron, Jormun, Relicta, and Zenitaia biome presets.

## Water and encounters

The selected water worlds are Jormun and Zenitaia. AquaExpansion and Terran Titans Naval Blocks are selected alongside Water Mod. No global water entry is added to planets that were not designed for it.
MES, Assertive Combat Systems, Abandoned Settlements, and AiEnabled are retained. MES warns about NPC grid precision beyond 6,500 km from origin; RSS clamps its physical voxel spawn range to at least 10,000 km. No confirmed safe configuration-only repair was found. Planetary NPC spawning near RSS physical planets remains an acceptance risk.

## Limits

The selected cut prioritizes varied exploration while staying at or below the conservative 120-material budget: Cauldron System, Jormun, Zenitaia, Orlunda Sideways, and Relicta are retained. Teal, Teralis, Komorebi, Nivis, Sulfate, and Acribus are excluded for this campaign.
Cauldron bundles four exact RSS proxy definitions. Orlunda Sideways uses the Orlunda/Komorebi SD proxy pack and Jormun uses its dedicated SD proxy. Zenitaia and Relicta require locally exported proxies unless exact compatible Workshop proxies are discovered during a later audit. The prepared world remains disarmed until coverage is exact.
Voxel modifiers are excluded. No subtype duplicates were found in the selected local definitions. Unique subtype union is independent of override precedence. The old test save contained stale Workshop entries and was not edited; its static voxel estimate is a lower bound. The original was preserved in timestamped ZIPs.
The most recent pre-change game log loaded 189 unique voxel materials from the old pack. The new pack has passed static auditing and offline RSG compilation, but has not been launched, generated, reloaded, or checked for water/science/MES behavior in game.
