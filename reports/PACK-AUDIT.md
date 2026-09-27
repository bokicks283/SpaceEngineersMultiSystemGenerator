# Selected pack audit

Static voxel total: **118** = 62 vanilla + 56 additions; **10** headroom against 128 and 2 below the conservative budget of 120. Runtime validation pending.

| Body | Selected | Active RSS proxies | Science |
|---|---|---:|---|
| Agni | yes | 1 | native |
| Cauldron | yes | 1 | local authored preset |
| Kor | yes | 1 | native |
| Tellus | yes | 1 | native |
| Teal-WaterMod | yes | 0 | native |
| Teralis - City Planet | yes | 0 | native |
| Jormun | no | 0 | generic fallback |
| Zenitaia | yes | 0 | local authored preset |
| OrlundaSide | no | 0 | native |
| Komorebi | no | 0 | native |
| Nivis | no | 0 | generic fallback |
| Relicta | no | 0 | local authored preset |
| Sulfate | no | 0 | generic fallback |
| unavailable | no | 0 | unavailable |

## Workshop load-list membership

- 3791989881 — Yoink!
- 2200451495 — Water Mod
- 3222232482 — Visual Overrides API
- 758597413 — Text HUD API
- 2195637331 — Teralis - City Planet
- 2644430625 — Teal - Water Mod
- 3240629702 — Solar Blocks Override
- 2841920953 — Shower Light
- 3665099597 — Scientific Progress
- 1965654081 — Rich HUD Master
- 3746220940 — Resource Node Miner
- 3152436752 — Real Stars
- 3351055036 — Real Solar Systems
- 3232085677 — Real Gas Giants
- 3695766186 — Planet Zenitaia
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
- 3690317665 — AquaExpansion
- 2899106264 — Terran Titans Naval Blocks

## Local mods

- RandomSectorGenerator: one-shot armed disposable-world bootstrap, pending RSS checkpoint handoff, spoiler manifest.
- CampaignScienceCompatibility: authored Cauldron and Zenitaia biomes; Relicta is prepared but excluded from this pack.

## Water and encounters

The local Teal-WaterMod, Teralis - City Planet, and Zenitaia packages each define their own WaterConfig planet entry. AquaExpansion and Terran Titans Naval Blocks are selected alongside Water Mod. No global water entry was added.
MES, Assertive Combat Systems, Abandoned Settlements, and AiEnabled are retained. MES warns about NPC grid precision beyond 6,500 km from origin; RSS clamps its physical voxel spawn range to at least 10,000 km. No confirmed safe configuration-only repair was found. Planetary NPC spawning near RSS physical planets remains an acceptance risk.

## Limits

The selected cut is the only six-mod cut under 120 materials that retains Cauldron plus Water Teal, Teralis, and Zenitaia among the locally available requested planets. Excluded: Komorebi, Orlunda Sideways, Relicta, Sulfate, Jormun, and Nivis. Acribus is not installed.
Cauldron bundles four exact RSS proxy definitions. Teal-WaterMod, Teralis - City Planet, and Zenitaia still lack active exact proxies. Alkurah SD proxy pack and RSS Planet Exporter were identified as candidates but their Workshop downloads and runtime coverage remain unverified. The prepared world is disarmed until coverage is exact.
Voxel modifiers are excluded. No subtype duplicates were found in the selected local definitions. Unique subtype union is independent of override precedence. The old test save contained stale Workshop entries and was not edited; its static voxel estimate is a lower bound. The original was preserved in timestamped ZIPs.
The most recent pre-change game log loaded 189 unique voxel materials from the old pack. The new pack has passed static auditing and offline RSG compilation, but has not been launched, generated, reloaded, or checked for water/science/MES behavior in game.
