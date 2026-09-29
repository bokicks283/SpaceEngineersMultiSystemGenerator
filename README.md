# Space Engineers Multi-System Generator

Status: **Phase A installs a reusable `Random Sector` Custom Game; its first in-game generation/adoption test is next.**

## Phase A player install

Close Space Engineers, open PowerShell in this repository, and run:

```powershell
pwsh .\Install-RandomSector.ps1
```

The installer resolves the current children of Steam collection
**3808835800** through Steam's public Web API, verifies every collection item
is installed, applies the explicit Phase A planet/compatibility policy, and
writes the decision record to `reports/steam-collection.json`. It then audits
the fixed 18-body pack, compiles and installs the local mods, installs the
locked RTS profile, and creates `Content\CustomWorlds\Random Sector` from the
root files of the stock Empty World. It deliberately excludes the stock
template's `Storage` and `Backup` directories. The installed template starts
in Survival with Economy, Cargo Ships, Random Encounters, Planetary Encounters,
and the global encounter cap disabled.

Steam resolution fails closed. If Steam is temporarily unavailable and the
last successful snapshot is intentionally accepted, rerun with:

```powershell
pwsh .\Install-RandomSector.ps1 -UseCachedCollection
```

The normal player workflow is:

1. Launch Space Engineers and choose **New Game > Custom Game > Random Sector**.
2. Start the world and wait for RSG to report that generation finished.
3. Save and exit to the menu once, then reload the same world.
4. Run `/rsg adoption`, then `/rsg status`. When status reports
   `pending=False` and `applied=True`, run
   `/SetupRealOrbits` once and save.

RSG writes RSS's normal persisted configuration variable directly. The normal
workflow does not use `world_checkpoint.py prepare`, `sync`, `arm`, or `commit`.
Those commands remain developer/recovery tools. Economy remains disabled for
Phase A.

Collection entries tagged as IngameScript, Blueprint, Scenario, or other
non-Mod Workshop content remain visible in the collection report but are not
inserted into the world's `Mods` list.

This repository owns the local compatibility/configuration work for a heavily modded Space Engineers survival campaign built around Real Solar Systems (RSS), Real Stars, Real Gas Giants, Scientific Progress, Water Mod, MES, and a one-shot Random Sector Generator (RSG).

## Selected planet pack

The current campaign cut favors variety while prioritizing a Water Mod-capable starter:

- **Cauldron System** — Cauldron, Tellus, Agni, Kor
- **Jormun** — water/river world
- **Zenitaia** — tropical/deep-ocean world; preferred campaign starter
- **Orlunda (Sideways)** — RSS-friendly tidally locked world
- **Relicta** — hostile volcanic/radiation world
- All eight vanilla planets (EarthLike, Moon, Mars, Europa, Alien, Titan, Triton,
  Pertam) are eligible without adding Workshop voxel materials.
- Phase 2A also selects the zero-material Kerbin water variant and Aulden.

Additional planet catalog items may remain in the Steam collection for future
campaigns. Phase A reports them as inactive with a reason and keeps the fixed
18-body pool at about **117 unique voxel-material subtypes** after
AquaExpansion. `scripts/audit.py`, `scripts/steam_collection.py`, and
`scripts/prepare_pack.py` are authoritative and rerun on the actual machine.

## Proxy requirements

- Cauldron System bundles exact proxies for its four bodies.
- Orlunda Sideways: Workshop proxy pack **3361803398**.
- Jormun: local proxy built from Workshop texture source **3663505475**.
- Zenitaia, Relicta, Kerbin - Water Mod Ready, and Aulden use the
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

## RSS handoff internals

RSG no longer relies on session-component load order.

After generation validates, RSG writes its durable pending state and the
wire-compatible RSS payload to `RealSolarSystemsSettings_Config_xml`, then
permanently disarms generation. On the next load, RSS reads its normal
persisted variable and adopts the bodies. RSG marks bootstrap complete only
after every generated body is RSS-managed and the player can be moved to the
starter proxy.

While adoption is pending, RSG reasserts that payload during save so RSS's
pre-adoption runtime configuration cannot overwrite the handoff. The installer
also repairs an older pending save from its durable RSG state before reload.

This avoids modifying/forking RSS.

### Recovering the generated hierarchy after manual RSS adoption

If `/AddStrayPlanets` has already captured the generated bodies and the world
has subsequently been saved, `scripts/apply_static_sector_plan.py` can restore
the RSG plan's hierarchy and generated names offline. It does not create or
move voxel bodies, change `StorageName`/`PlanetGenerator` identity, or touch
Workshop content.

Space Engineers must be closed. Validate the exact adopted save first:

```powershell
py scripts\apply_static_sector_plan.py `
  "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Static Sector v2 - Pre RSS" `
  --plan "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-28 02-10\Storage\RandomSectorGenerator_RandomSectorGenerator\RandomSectorStaticPlan.tsv" `
  --dry-run
```

Remove `--dry-run` only after reviewing every reported identity mapping. The
write path creates a complete ZIP backup in the saves directory's sibling
`CodexBackups` folder, validates all staged XML, and replaces only the target
save's RSS, Real Stars, Real Gas Giants, and sector XML files. It sets each
mod's one-shot `OverrideFromConfig` flag so the edited files win on the next
load.

On that first load, inspect `/TSE` for the `Wyaris Abyss` root and the planned
parent/child tree. Then run `/SetupRealOrbits` once, save, fully exit, reload,
and recheck the hierarchy and names. Stock respawn-screen labels remain a
runtime acceptance item; RSS source proves the underlying planet entity name
changes, but not how every stock UI surface chooses its label.

The source-backed lifecycle and exact preservation rules are documented in
[RSS Static Sector Lifecycle](reports/RSS-STATIC-SECTOR-LIFECYCLE-2026-09-28.md).

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

- In-game proxy visual validation.
- Space Engineers in-game script whitelist/runtime compilation.
- RSS adoption after the offline checkpoint handoff.
- Water Mod behavior on Jormun/Zenitaia.
- Scientific Progress discovery behavior on all selected bodies.
- MES/Assertive/Abandoned/AiEnabled planetary spawning around RSS physical voxel planets. RSS places physical voxel planets far enough from origin that MES precision remains a known acceptance risk; no untested range tweak is presented here as a fix.


## First disarmed speed/orbit runtime gate

Before arming RSG, load `RSG Disposable Clean 2026-09-27` once with the final
pack. Run:

```text
/rsg status
/rsg planets
/rsg skins
/rts config
```

Do **not** run `/rsg generate` or `/SetupRealOrbits` during this validation.
Save, fully exit Space Engineers, then run:

```powershell
py scripts\runtime_check.py
py scripts\speed_orbit_runtime.py
```

`runtime_check.py` captures RSG/RSS plus RTS, Aerodynamic Physics, and Real
Orbits startup/error context. `speed_orbit_runtime.py` is read-only and
reports the actual per-world configuration files that the first load created.
