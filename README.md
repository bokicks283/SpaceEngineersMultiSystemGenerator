# Space Engineers Multi-System Generator

Status: **all selected RSS proxies are built and installed; disposable-world runtime validation is next. Generation remains disarmed.**

This repository owns the local compatibility/configuration work for a heavily modded Space Engineers survival campaign built around Real Solar Systems (RSS), Real Stars, Real Gas Giants, Scientific Progress, Water Mod, MES, and a one-shot Random Sector Generator (RSG).

## Selected planet pack

The current campaign cut intentionally favors variety rather than maximizing water worlds:

- **Cauldron System** — Cauldron, Tellus, Agni, Kor
- **Jormun** — water/river world
- **Zenitaia** — tropical/deep-ocean world
- **Orlunda (Sideways)** — RSS-friendly tidally locked world
- **Relicta** — hostile volcanic/radiation world
- All eight vanilla planets (EarthLike, Moon, Mars, Europa, Alien, Titan, Triton,
  Pertam) are eligible without adding Workshop voxel materials.
- Phase 2A also selects the zero-material Kerbin water variant, Aulden, and Seren.

Teal, Teralis, Komorebi, Nivis, Sulfate, and Acribus are intentionally excluded from this campaign cut. The expected static budget is about **117 unique voxel-material subtypes** after AquaExpansion, but `scripts/audit.py` and `scripts/prepare_pack.py` are authoritative and must be rerun on the actual machine.

## Proxy requirements

- Cauldron System bundles exact proxies for its four bodies.
- Orlunda Sideways: Workshop proxy pack **3361803398**.
- Jormun: local proxy built from Workshop texture source **3663505475**.
- Zenitaia, Relicta, Kerbin - Water Mod Ready, Aulden, and Seren use the
  generated local RSS proxy mod. `reports/coverage.json` is authoritative.
- RSS itself includes one proxy for each vanilla planet. The installed vanilla
  HD pack 3381681547 stays inactive because it would duplicate those proxies.
- RSS Planet Exporter: **3350589349**.

Do not arm a disposable world until `reports/coverage.json` reports exactly one active proxy for every selected custom body and every referenced proxy texture exists.

### Building the missing local proxies

The isolated workbench and generated helper take their export targets from
selected bodies without Workshop proxies. After exporting each planet at 120 km, run:

```powershell
py scripts\build_exported_proxies.py status
py scripts\build_exported_proxies.py build
py scripts\prepare_pack.py
pwsh .\Install-RandomSectorGenerator.ps1
```

The builder finds the newest `PlanetProxy_<Planet>_cm/ng/add.tga` files under `%APPDATA%\SpaceEngineers\Storage`, locates `texconv.exe`, converts CM/ADD as BC7 sRGB and NG as BC7 Linear with mipmaps, and stages one generated local mod at `generated/CampaignPlanetProxies`. The normal installer then installs it as `%APPDATA%\SpaceEngineers\Mods\CampaignPlanetProxies`.

`/ExportADD` is optional at the file level; if the exporter produces an additive map, the builder includes it automatically.

## Local mods

- `mods/RandomSectorGenerator`
  - explicit planet allowlist/Workshop denylist
  - 3–5 randomized root systems
  - guaranteed `DefaultBlackHole` hierarchy when the verified Real Gas Giants skin is available
  - random stars, gas giants, planets, and moons
  - safe Tellus/EarthLike starter selection
  - spoiler/debug manifest only; sector layout is not revealed in normal play
  - one-shot bootstrap with rollback and durable state
- `mods/CampaignScienceCompatibility`
  - authored Scientific Progress presets for Cauldron, Jormun, Relicta, and Zenitaia

## RSS handoff

RSG no longer relies on session-component load order.

The supported bootstrap flow is:

1. Prepare a clean disposable RSS Empty World while **disarmed**, with Economy,
   Cargo Ships, Random Encounters, and Planetary Encounters off and the global
   encounter cap at zero. Do not use a save that already has economy stations.
2. After proxy coverage is complete, arm it offline.
3. Load the world. RSG generates once after the RSS/Real Stars/Real Gas Giants APIs are ready.
4. Save and **exit Space Engineers**.
5. Run the offline checkpoint `commit` command. It validates the pending RSG state and saved entity IDs, archives the world, writes the RSS protobuf payload into `RealSolarSystemsSettings_Config_xml`, and permanently disarms RSG.
6. Reload. RSS reads its normal persisted configuration and adopts the generated bodies.
7. RSG marks bootstrap complete only after all pre-spawned bodies are RSS-managed and the player can be moved to the starter proxy.

This avoids modifying/forking RSS.

After adoption and final-body verification, a separate
[Campaign Activation](reports/CAMPAIGN-ACTIVATION.md) phase must test Economy,
encounters, MES/PvE, and respawn behavior in a QA clone before enabling them
in the real campaign. The generated sector alone is not campaign-ready.

## Disposable-world commands

The earlier disposable world inherited generated NPC economy stations from its
source save and must not be used for sector generation. A clean disposable
world is prepared from the installed stock Empty World template with the
audited mod list and pre-activation settings. To recreate it under a new name:

```powershell
py scripts\world_checkpoint.py prepare-stock "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Disposable Audit 2026-09-27" --name "RSG Disposable Clean 2026-09-27"
```

When proxy coverage is complete:

```powershell
py scripts\world_checkpoint.py arm "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Disposable Clean 2026-09-27"
```

After generation, saving, and fully exiting the game:

```powershell
py scripts\world_checkpoint.py commit "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Disposable Clean 2026-09-27"
```

Every write operation checks that Space Engineers is closed and archives the disposable world before changing it.

## Local validation

From the repository root:

```powershell
py scripts\audit.py
py scripts\prepare_pack.py
pwsh .\Install-RandomSectorGenerator.ps1
pwsh .\scripts\Build-RSG.ps1
py scripts\world_checkpoint.py sync "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Disposable Clean 2026-09-27"
py scripts\verify_local.py
```

The generated files under `reports/` are machine-specific evidence. Re-run the audit after subscribing/unsubscribing planet or proxy mods instead of trusting stale committed report values.

## Remaining acceptance risks

- Zenitaia/Relicta proxy export and visual validation.
- Space Engineers in-game script whitelist/runtime compilation.
- RSS adoption after the offline checkpoint handoff.
- Water Mod behavior on Jormun/Zenitaia.
- Scientific Progress discovery behavior on all selected bodies.
- MES/Assertive/Abandoned/AiEnabled planetary spawning around RSS physical voxel planets. RSS places physical voxel planets far enough from origin that MES precision remains a known acceptance risk; no untested range tweak is presented here as a fix.
