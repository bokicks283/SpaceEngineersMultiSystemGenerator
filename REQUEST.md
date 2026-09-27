You are taking ownership of ALL LOCAL TECHNICAL WORK for my heavily modded Space Engineers survival campaign.

Do not ask me to manually edit configuration files, Workshop copies, XML files, save files, load-order files, proxy definitions, or local mod source unless there is genuinely no safe automated alternative.

I will handle Steam Workshop subscribing/unsubscribing when you identify a Workshop item that must change. You handle everything local.

## Objective

Prepare a stable Space Engineers survival world built around:

- multiple randomly generated stellar systems
- Real Solar Systems
- Real Stars
- Real Gas Giants
- at least one black-hole-centered system/cluster
- custom planets and moons
- Water Mod gameplay
- Scientific Progress
- Modular Encounters Systems
- AiEnabled
- NPC/PvE encounters
- our local Random Sector Generator
- long-term interplanetary and interstellar survival progression

I do NOT want to manually place planets or configure systems.

The Random Sector Generator should bootstrap the sector automatically and then allow RSS to own/runtime-manage the resulting hierarchy.

## Important local paths

Automatically discover Steam libraries through:

`steamapps/libraryfolders.vdf`

Space Engineers app ID:

`244850`

Workshop mods are typically under:

`steamapps/workshop/content/244850/<WorkshopId>`

Space Engineers user data is under:

`%APPDATA%\SpaceEngineers`

Local mods are under:

`%APPDATA%\SpaceEngineers\Mods`

Saves are under:

`%APPDATA%\SpaceEngineers\Saves`

Do not assume Space Engineers is installed on C:. Discover all Steam libraries.

## Local Random Sector Generator

A prototype local mod was created earlier in this project.

Look for:

`%APPDATA%\SpaceEngineers\Mods\RandomSectorGenerator`

If present, treat that as the current source and move/copy it into an appropriate Git working repository if necessary so all changes are version controlled.

Do NOT edit Workshop copies of Real Solar Systems, Real Stars, Real Gas Giants, MES, Scientific Progress, Water Mod, or planet mods.

If compatibility work is needed, create separate local compatibility mods.

## Desired planet allowlist

The random sector should use these custom planet mods/bodies:

- 3576683005 — Cauldron System
  - Cauldron
  - Tellus
  - Agni
  - Kor
- 2644430625 — Teal - Water Mod
- 2195637331 — Teralis - City Planet
- 3618043241 — Jormun
- 3695766186 — Planet Zenitaia
- 3362332228 — Orlunda (Sideways)
- 3309805284 — Komorebi
- 3684013414 — Planet Nivis
- 3489648084 — Planet Relicta
- 3515518898 — Moon Sulfate
- 3486181518 — Planet Acribus

Vanilla planets/moons may also be eligible because they do not add additional Workshop voxel definitions and Scientific Progress already understands them.

However, custom planets above should remain the main exploration content.

## Explicit denylist

The generator must NOT use these planet definitions/mods if they are still installed locally:

- 2873186053 — normal Orlunda
- 2266665708 — Satreus
- 2636128625 — Trelan
- 2296726670 — Tohil
- 2459246911 — Kimi & Qun
- 3617008256 — Glacies
- 3617040986 — Tibur
- 3618093811 — Vermilion
- 3617496051 — Miasma
- 3561998389 — Torr
- 2603627657 — normal/non-Water Teal
- 2789619117 — Star System Generator

Do not silently delete Workshop files. Report if one is still subscribed/installed so I can unsubscribe through Steam.

The local Random Sector Generator replaces Star System Generator.

## Step 1 — Authoritative local mod audit

Inspect Steam Workshop manifests and installed Workshop directories.

Build a machine-readable inventory containing:

- Workshop ID
- title
- installed path
- metadata
- dependencies where detectable
- whether it belongs to the desired pack
- whether it is obsolete/redundant/denylisted
- whether multiple versions of the same planet/proxy are installed

Use local files as the authoritative source rather than relying on the Steam website.

Also inspect the current Space Engineers save/world mod list if a test world exists.

Produce a concise report before making destructive changes.

## Step 2 — Exact voxel-material audit

This is critical.

Space Engineers has a hard limit around 128 voxel material definitions.

Parse:

- vanilla Space Engineers voxel material definitions from the installed game
- every intended planet mod
- any other active mod that defines voxel materials

Count unique effective `VoxelMaterialDefinition`/subtype definitions as the game will see them.

Report:

- vanilla count
- per-mod additions
- duplicate/overridden definitions
- total effective count
- remaining headroom

If the desired pack exceeds the limit, do NOT randomly delete definitions.

Instead identify the smallest reasonable planet cut necessary and report it.

The goal is to stay safely below the cap, not merely equal 128.

## Step 3 — RSS proxy audit

Inspect Real Solar Systems and every installed RSS proxy pack.

For each desired custom planet determine:

- proxy exists
- proxy subtype/name matches the planet definition
- SD/HD duplicates exist
- proxy is current/usable
- proxy is missing

Do not keep multiple competing proxy definitions for the same planet.

Prefer a single appropriate proxy.

Cauldron System reportedly contains its own RSS proxies, so verify those rather than adding duplicates.

Orlunda must use the Sideways definition/proxy, not normal Orlunda.

If a proxy is missing, build a separate local compatibility/proxy mod where legally and technically possible.

Respect Workshop mod licenses. A compatibility mod should reference the original as a dependency and must not copy protected source assets when the license disallows that.

If the RSS Planet Exporter must be run inside Space Engineers to generate an asset that cannot be created offline, automate everything possible and then give me only the exact minimum in-game action required.

## Step 4 — Scientific Progress compatibility

Audit Scientific Progress against every desired planet.

Identify planets with:

- native dedicated presets
- generic fallback only
- incorrectly matched definitions because of renamed variants such as Orlunda Sideways

Create one local compatibility mod for missing/variant Scientific Progress definitions where feasible.

Do not modify Scientific Progress's Workshop directory.

The goal is that every selected custom world has useful exploration/science behavior.

## Step 5 — Random Sector Generator

Take ownership of the local RSG source.

The generator must have an explicit allowlist/denylist and MUST NOT simply include every loaded `PlanetGeneratorDefinition`.

Requirements:

- deterministic optional seed
- random seed by default
- approximately 3–5 stellar systems
- randomized system locations
- randomized planet distribution
- planets may become moons where sensible
- gas giants supported
- binary/multiple-star systems supported where RSS/Real Stars permit
- GUARANTEE at least one black-hole-centered hierarchy if an appropriate Real Gas Giants/RSS black-hole skin is available
- choose a survivable starting body
- never start the player on a late-game lethal planet
- do not reveal the full generated map/GPS positions
- record a private/debug manifest for troubleshooting
- avoid placing worlds so close that orbital/proxy zones overlap incorrectly
- inter-system spacing should make interstellar propulsion meaningful
- generation should happen once, then RSS should own the resulting system
- recovery must be safe if generation fails halfway
- never corrupt an existing established survival save

Prefer:
`generate -> save -> reload -> RSS adopts -> bootstrap complete`

Do not require the RSG mod to remain active afterward unless technically necessary.

## Step 6 — RSS persistence/config

Earlier inspection found that RSS stores its hierarchy/config in its save storage/world variables and can load hierarchy configuration on world startup.

Inspect the installed current RSS source yourself; do not rely only on this summary.

Determine the cleanest stable handoff mechanism.

Avoid modifying/forking RSS unless absolutely necessary.

Priority:

1. RSS-supported public/API mechanism
2. compatible persisted config/world-variable handoff
3. tiny compatibility bridge
4. RSS fork only as last resort

If a compatibility bridge is required, isolate it in its own local mod and document exactly why.

## Step 7 — RSS/MES compatibility

MES is essential to the campaign.

RSS has known spawn-position/voxel-location interactions because physical voxel planets can exist far from their logical/proxy positions.

Inspect current RSS and MES configuration/source.

Apply safe configuration fixes for voxel planet spawn range/center if appropriate.

Do not guess values.

Create a compatibility shim only if configuration cannot solve the actual observed problem.

We care particularly about:

- planetary installations
- Assertive Combat Systems
- Abandoned Settlements
- AiEnabled ground NPCs
- cargo/space encounters

## Step 8 — Water stack

Verify local compatibility for:

- Water Mod
- Teal - Water Mod
- Teralis water
- Jormun
- Zenitaia
- AquaExpansion
- Terran Titans Naval Blocks

Ensure required dependencies exist.

Do not globally add water to planets that were not designed for it merely because Water Mod is installed.

Water should be part of the sector's variety, not present everywhere.

## Step 9 — World configuration

Once the mods and generator are ready, own all local world configuration.

Use an RSS-compatible empty/test world.

Configure:

- correct active mod list
- correct load order
- RSS settings
- Real Stars
- Real Gas Giants
- Scientific Progress
- MES
- RSG bootstrap
- Water Mod settings when needed

Back up any save before editing.

Never edit the only copy of a survival save.

Preserve an original backup in a timestamped ZIP.

## Step 10 — Testing

Before calling this ready:

- launch/build-check local mod scripts where possible
- inspect `SpaceEngineers.log`
- verify no RSG compile errors
- verify desired planet definitions load
- verify voxel-material total is safe
- verify no duplicate RSS proxy definitions
- generate a disposable sector
- reload it
- verify RSS adopts the generated hierarchy
- verify a black hole exists
- verify multiple systems exist
- verify starter planet is reachable/playable
- verify Water Mod activates on intended worlds
- verify Scientific Progress recognizes selected worlds
- verify MES can spawn encounters near an RSS planet
- verify no obvious planet texture fallback to stone

If GUI/in-game interaction is required, give me the smallest possible acceptance test with exact commands/actions. Everything else should be automated locally.

## Deliverables

Maintain the work in Git.

At the end give me:

1. A short status summary.
2. Exact files changed/created.
3. Any local compatibility mods created.
4. Final active Workshop/local mod list.
5. Voxel-material audit results.
6. RSS proxy coverage table.
7. Scientific Progress coverage table.
8. RSG generation settings.
9. Any remaining known risks.
10. A very short in-game acceptance test.

Do not ask me to manually edit configuration/XML/source files. Make the changes yourself and back them up.