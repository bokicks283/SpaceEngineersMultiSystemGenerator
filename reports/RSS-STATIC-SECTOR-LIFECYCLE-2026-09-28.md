# RSS Static Sector Adoption, Hierarchy, and Naming Lifecycle

Date: 2026-09-28

## Outcome

The generated 25-body sector can be repaired offline without recreating or
moving its voxel planets. The safe target is an already-adopted world that was
saved after `/AddStrayPlanets`. The repair reconstructs RSS's XML hierarchy
from `RandomSectorStaticPlan.tsv`, applies the generated names consistently,
and arms the existing one-shot config-import flags for RSS, Real Stars, and
Real Gas Giants.

No Workshop file needs modification. The campaign save was inspected and
dry-run only; it was not changed by this work.

## Evidence inspected

Installed Workshop source was read directly from:

- RSS: `S:\SteamLibrary\steamapps\workshop\content\244850\3351055036`
- Real Stars: `S:\SteamLibrary\steamapps\workshop\content\244850\3152436752`
- Real Gas Giants: `S:\SteamLibrary\steamapps\workshop\content\244850\3232085677`
- System Manager: `S:\SteamLibrary\steamapps\workshop\content\244850\3780085631`

The newest plan-bearing source save was:

`%APPDATA%\SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-28 02-10`

Its RSS config contains no systems, which is expected before saved adoption.
The saved post-adoption target was:

`%APPDATA%\SpaceEngineers\Saves\76561198045624840\RSG Static Sector v2 - Pre RSS`

That target contains 25 RSS root systems and 25 saved `MyPlanet` entities.
The static plan also contains 25 bodies. All plan identities matched the
adopted RSS and sector bodies exactly by `StorageName` during the dry run.

## What `/AddStrayPlanets` actually does

RSS's chat command enumerates live `MyPlanet` voxel maps, excludes bodies that
RSS already manages, and calls `SolarSystemManager.CapturePlanet` for every
remaining body. `CapturePlanet` creates a `CelestialBody`, records the live
planet's `StorageName` as `BodyInstanceName`, populates its body-specific RSS
configuration, and initializes it as an independent root at its current world
position.

The command therefore changes RSS's in-memory graph immediately. It does not
directly write `Config.xml` or the checkpoint variable. Persistence occurs on
a later world save, when RSS serializes its current systems into both its
config file and `RealSolarSystemsSettings_Config_xml`. Closing TSE merely
closes its UI; it is not a save operation.

TSE has no separate stray-body database. It displays the same RSS
`solarSystems`/body graph. After capture, 25 generated bodies appear as 25
roots until their parent/child relationships are changed.

## Hierarchy and orbit state

TSE's set-root and set-child operations modify RSS's in-memory parent,
children, root-system, and `OrbitInfo` state. Its orbit controls update the
same per-body configuration. RSS persists that graph as nested
`SolarSystemConfig > RootBody > Children > CelestialBodyConfig` XML.

On load, RSS reads the saved XML, resolves each `BodyInstanceName` back to the
corresponding live `MyPlanet`, and recreates the graph. There is no additional
RSS hierarchy store that an offline repair must synchronize.

RSS's public mod-message API is query-only for this purpose: it exposes
coordinate, zone, and gravity information, but no supported hierarchy, orbit,
or rename mutation calls. Direct live automation is therefore less reliable
than rebuilding the already-persisted graph while the game is closed.

## Config precedence

Normally RSS can replace `Config.xml` with the checkpoint's serialized config
during load. With `OverrideFromConfig=true`, it instead accepts the file for
that load, clears the in-memory flag, and writes the imported configuration
back to the checkpoint variable. Real Stars and Real Gas Giants implement the
same one-shot pattern.

The repair consequently sets all three config override flags. The first load
imports the edited files; the next world save makes the result durable in the
checkpoint.

## Naming layers

Several names coexist and are not interchangeable:

| Layer | Field | Effect |
| --- | --- | --- |
| RSS | `CelestialBodyConfig.Name` | TSE label and RSS GPS/display name |
| Saved planet entity | `MyObjectBuilder_Planet/Name` | Canonical live planet entity name after load/save |
| Real Stars | `StarInfo.StarCustomName` | Real Stars label for generated stars |
| Real Stars | `PlanetInfo.PlanetCustomName` | Real Stars terrestrial/day-cycle record label |
| Real Gas Giants | `GasGiantConfigInfo.PlanetCustomName` | Gas-giant mod label |
| System Manager | alias/map metadata | Independent layout alias; not RSS identity or hierarchy |

TSE's name setter changes the RSS config name, refreshes RSS UI/GPS, forwards
custom names to Real Stars or Real Gas Giants when applicable, and changes the
underlying `MyPlanet.Name`. The repair mirrors those durable fields.

System Manager explicitly treats its rename as an alias; it does not modify
the planet entity or RSS identity. Its parent relation is likewise map/layout
metadata, not RSS orbital hierarchy, so it is intentionally not edited.

RSS source proves that the canonical planet entity name is updated. It does
not prove which name the stock respawn screen presents in every case. Respawn
labels must therefore be verified in-game rather than reported as fixed.

## Offline tool safety contract

`scripts/apply_static_sector_plan.py` fails closed unless all of these hold:

- Space Engineers is not running.
- The TSV has the exact expected schema, one root, unique names and identities,
  valid parents, no cycles, and numeric orbit values.
- The target already contains RSS config, Real Stars config, Real Gas Giants
  config, and `SANDBOX_0_0_0_.sbs`.
- RSS and the saved sector contain exactly the planned body count, with no
  unplanned bodies.
- Each plan body resolves first by exact `StorageName`; a numeric-suffix match
  is accepted only when it is unique.
- Each resolved RSS and sector body has the expected planet/generator type.

The tool preserves body-specific RSS nodes, including zones, atmosphere,
particle, functional-zone, and special configuration. It changes only the RSS
tree placement, generated name, plan orbit data, one-shot override flags, the
saved planet entity name, and corresponding Real Stars/Real Gas Giants custom
name fields. It never changes `StorageName`, `PlanetGenerator`, voxel storage,
physical position, or Workshop content.

Before any write it creates a ZIP of the entire target save under
`...\Saves\CodexBackups`. It stages and parses every XML result before atomic
replacement, then parses the files again from disk.

## Operator procedure

With Space Engineers fully closed, run the validation first:

```powershell
py scripts\apply_static_sector_plan.py `
  "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Static Sector v2 - Pre RSS" `
  --plan "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-28 02-10\Storage\RandomSectorGenerator_RandomSectorGenerator\RandomSectorStaticPlan.tsv" `
  --dry-run
```

Review all 25 mappings. If they remain exact, apply by running the same command
without `--dry-run`:

```powershell
py scripts\apply_static_sector_plan.py `
  "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\RSG Static Sector v2 - Pre RSS" `
  --plan "$env:APPDATA\SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-28 02-10\Storage\RandomSectorGenerator_RandomSectorGenerator\RandomSectorStaticPlan.tsv"
```

Then:

1. Start Space Engineers and load `RSG Static Sector v2 - Pre RSS`.
2. Open `/TSE`; confirm the `Wyaris Abyss` root and the planned hierarchy/names.
3. Run `/SetupRealOrbits` once.
4. Save and fully exit Space Engineers.
5. Reload and verify TSE hierarchy, names, GPS labels, orbit behavior, and the
   respawn UI.

Do not use the pre-adoption `Random Sector 2026-09-28 02-10` world as the
repair target. Its empty RSS systems list has no captured bodies to rearrange.
