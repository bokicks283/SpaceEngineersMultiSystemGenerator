# RSG post-adoption runtime diagnostic — 2026-09-27

## Scope

This is a read-only diagnosis of the first successful RSS adoption load of
`Random Sector 2026-09-27 21-24`. No source, mod configuration, installed mod,
or save data was changed. The player reported that no planets were visible and
that natural gravity reversed direction by about 180 degrees every few seconds.
The player later clarified that the jetpack was off.

Repository state examined:

- Branch: `feat/random-sector-phase-a`
- Starting commit: `7253aac954e26a4f72e500011b40c313a5d4093a`
- Game process: `SpaceEngineers.exe`, PID 26668, started 2026-09-27 22:17:09 local
- Runtime log: `%APPDATA%\SpaceEngineers\SpaceEngineers_20260927_221709733.log`
- Save snapshot: `%APPDATA%\SpaceEngineers\Saves\76561198045624840\Random Sector 2026-09-27 21-24`
- Sector snapshot timestamp: 2026-09-27 22:22:41 local

## Finding

The generated RSS hierarchy was adopted, but the player was left at the root
system origin instead of the starter planet proxy. The saved character position
is approximately `(0.106, 3.085, 0.090)`. The root system and its star proxy are
centered at `(0, 0, 0)`, while the starter planet `Caion` (`Tellus`) has a
53,000,000 m semimajor axis and a 52,500 m surface radius. The player therefore
was not near the starter surface when the save was captured.

The invisible 0.10 g source in the screenshot is consistent with the root star
proxy's gravity at its center. `Kaune Star` stores Real Stars gravity metadata
`10,7,79342.33`: strength 10 g, falloff 7, and minimum height 79,342.33 m. RSS's
`ProxyGravityProvider` clamps the center multiplier to 0.01, producing
`10 g * 0.01 = 0.10 g`, exactly matching the HUD. Its gravity direction is
`normalize(center - playerPosition)`. With the astronaut only a few metres from
the center and the jetpack off, crossing the center reverses the direction of
natural gravity and causes the observed repeated 180-degree reorientation.

This makes the missing planets and flipping gravity two effects of the same bad
post-adoption player location. Jetpack-off explains why the astronaut continued
to cross the center; it does not explain why the bootstrap placed or retained
the astronaut there.

The game subsequently crashed at 22:26:57. That crash has a concrete and
separate stack trace in Crew Enabled/AiEnabled bot cleanup. It is documented
below and should not be attributed to RSG, RSS, or gravity without an isolated
reproduction.

## Evidence

### Adoption itself completed

The current RSG state says:

- `PendingApply=false`
- `Applied=true`
- seed `-1936850583`
- 3 systems
- 18 selected planet definitions
- starter display name `Caion`
- starter subtype `Tellus`
- starter storage name `Tellus-1886068815d105000`

The runtime log records all eight persisted physical bodies and then initializes
the complete logical hierarchy: 18 terrestrial planets, four stars, and three
gas giants. At log line 16231, RSG reports eight expected persisted bodies,
eight resolved by storage name, eight RSS-managed, and zero blockers. The later
in-game `/rsg adoption` output reports `Pending: False`, `Applied: True`, and the
same 8/8 result.

No RSG, RSS, Real Stars, or Real Gas Giants runtime exception appears after
hierarchy initialization. The Aulden pruning warnings and Cauldron heightmap
fallback are real content issues, but neither explains why a Tellus starter was
left at the root system origin.

### Subsequent crash

Space Engineers exited at 22:26:58 and wrote
`%APPDATA%\SpaceEngineers\Minidump.dmp` (10,469,861 bytes). The runtime log
classifies the crash as managed, not out-of-memory, GPU, native, task, or hang.
Memory immediately before the exception was not exhausted: the crash footer
reports 8,385 MB hardware memory available.

The fatal exception begins at log line 16403:

```text
System.NullReferenceException
  at Sandbox.Game.Entities.MyCockpit.RemovePilot()
  at AiEnabled.Bots.BotBase.Close(Boolean cleanConfig, Boolean removeBot)
  at AiEnabled.Bots.EnemyBotBase.Close(Boolean cleanConfig, Boolean removeBot)
  at AiEnabled.API.LocalBotAPI.CloseBot(Int64 botEntityId)
  at CrewEnabled.RemoteBotAPI.RemoveBot(Int64 botEntityId)
  at CrewEnabled.CrewEnabledSession.DeleteBot(IMyCharacter bot)
  at CrewEnabled.CrewEnabledGrid.DecrewGrid()
  at CrewEnabled.CrewEnabledGrid.OnSyncOutAreaExited(String triggerName, Int64 playerId)
```

Seventeen seconds before the exception, the log initializes the large NPC grid
`(NPC-RCSP) Valkyrie`. Several unnamed bot characters then spawn. Crew Enabled's
`OnSyncOutAreaExited` handler calls `DecrewGrid` after the last synchronized
player leaves a grid's outer area trigger. During that cleanup, Crew Enabled
asks AiEnabled to remove a bot; AiEnabled reaches the engine's
`MyCockpit.RemovePilot` with invalid state and throws.

This establishes the immediate crash owner/path as the Crew Enabled and
AiEnabled cleanup interaction around an NPC cockpit. The trigger may have fired
because the player or grid crossed a sync boundary, but the current evidence
does not connect that crossing specifically to RSS zone movement. The crash is
therefore recorded as a second blocker rather than merged into the starter
teleport diagnosis.

### Saved player position is the star-proxy center

`SANDBOX_0_0_0_.sbs` lines 1464-1472 contain the player character and record:

```xml
<Position x="0.10647207693021743"
          y="3.085497713064342"
          z="0.090154649086308547" />
```

RSS `Config.xml` defines the home solar system position as `(0, 0, 0)` and its
root as `RealStar-1488165795d19000`, named `Kaune Star`. The same config places
`Tellus-1886068815d105000` (`Caion`) in a 53,000,000 m orbit with a 52,500 m
surface-zone radius. A valid starter surface position therefore cannot be within
roughly 3 m of the system origin.

The physical Tellus voxel is present and healthy enough to be adopted. In the
sector file it is named `Caion`, has storage name
`Tellus-1886068815d105000`, and is parked in RSS true space at approximately
`(46,934,034, 1,011,563,404, -468,414,601)`. The empty view is not evidence that
the voxel failed to spawn; RSS intentionally separates that true-space voxel
from its logical proxy location.

### The 0.10 g reading identifies the source

The `Kaune Star` entity's mod storage contains:

```text
f6649d92-33f9-4cb4-b38b-69bf19dd3001 = 10,7,79342.33
```

Real Orbits recognizes that GUID as `STAR_GRAVITY_DATA`. RSS creates a
`ProxyGravityProvider` for each star at the star's logical `bodyPosition`.
Inside the minimum radius, that provider computes `distance / minRadius` and
clamps the result to 0.01. With the stored star strength of 10, the minimum
field is 0.10 g. The screenshot shows `P-Gravity: 0.10g`.

The provider points gravity toward the proxy center. At a distance of only a few
metres, falling through the center changes the normalized direction to its
opposite. This is a direct explanation for the reported repeated inversion.

### High-confidence initialization race in the handoff

RSG considers adoption ready beginning at its tick 120. Once all persisted
bodies resolve and RSS reports them managed, it calls
`TeleportCharacterToRssStarter`, marks the handoff applied, and stops checking.

RSS deliberately delays runtime activation for 300 update ticks. Until that
counter expires, `RealSolarSystemsCore.UpdateBeforeSimulation` returns before
calling `ZoneManager.Update`, `PlanetProxyManager.Update`, and
`SolarSystemManager.Update`. `CelestialBody.bodyPosition` defaults to zero and
is assigned its orbit-derived value by `CelestialBody.Update`, which is reached
through `SolarSystemManager.Update` only after RSS's delayed initialization.

RSG's adoption predicate verifies body identity and RSS ownership, but it does
not verify that RSS has completed this delayed initialization or that the
starter's logical proxy center is nonzero/current. RSG can therefore call
RSS `ConvertPlanetPosToProxy` and declare success while the starter body's
`bodyPosition` and zone state are still in their pre-update state. This timing
matches the observed result and is the leading cause.

There is a second correctness issue in the same teleport routine: RSG converts
the surface position through RSS but builds the character orientation using the
untransformed true-space `Vector3D.Up`. RSS rotates surface offsets by the
body's `surfaceRotInv`. This can produce an initially wrong character basis,
although it does not explain the saved position at the system origin by itself.

## Real Orbits assessment

Workshop mod `2609118808` (`Real Orbits`, script namespace
`RealisticGravity`) is active. Its world config has:

- `CharacterGravityMultiplier=2`
- `OverridePlanetGravityFalloff=true`
- `EnforceSingleGravityWell=true`
- `EnforceStableOrbits=true`

Real Orbits explicitly integrates with RSS and RSS detects its presence. Real
Orbits tracks the physical `MyPlanet` entities and changes their falloff, while
RSS supplies the logical proxy gravity provider responsible for the exact
0.10 g center field. Nothing in the log proves Real Orbits caused this event.
It should remain a controlled compatibility variable in a later runtime test,
but removing or reconfiguring it is not supported by this diagnostic evidence.

## Confidence and remaining unknowns

High confidence:

1. RSS adopted the generated hierarchy.
2. The saved astronaut is at the logical root star center, not the starter.
3. The 0.10 g field and flips are explained by the 10 g root star proxy's
   0.01 center clamp plus the jetpack being off.
4. RSG can complete its check at tick 120 before RSS's tick-300 activation and
   first body-position update.
5. The later process crash is a null dereference in Crew Enabled -> AiEnabled ->
   `MyCockpit.RemovePilot`, not an RSG/RSS exception and not resource exhaustion.

Not yet proven from existing telemetry:

1. The exact intermediate coordinate returned by `ConvertPlanetPosToProxy` on
   the failing tick.
2. Whether the first RSS zone update moved an early teleport result to the
   origin, or the conversion itself returned an origin-relative stale result.
3. The exact starter proxy position and surface rotation on the first frame
   after RSS activation; neither is logged.
4. Whether RSS movement contributed to the Crew Enabled sync-out event. The
   available stack proves the cleanup failure but not its relationship to RSS.

## Recommended next diagnostic/implementation plan

The next work thread should plan a narrow handoff fix around RSS readiness,
without changing sector generation or campaign tuning:

1. Add temporary RSG diagnostics for the adoption tick, RSS zone result,
   physical starter center/surface, returned proxy position, RSS proxy center,
   proxy rotation, player position before/after teleport, and gravity vector.
2. Do not complete adoption until RSS has produced a stable, finite starter
   proxy center at the configured orbital distance across consecutive ticks.
   The RSS public API exposes `GetBodyProxyPosition`, `GetBodyProxyRotation`,
   `GetEntityZone`, and `GetEntityZone_ProxyPosRot`; the current RSG client binds
   only `GetBodyZoneRange` and `ConvertPlanetPosToProxy`.
3. Transform the character orientation with RSS's proxy/surface rotation rather
   than reusing true-space world up.
4. Confirm the post-teleport player is within the starter surface zone before
   setting `PendingApply=false` and `Applied=true`; retry or retain pending state
   if validation fails.
5. Reproduce in a disposable generated world with jetpack on for observation,
   then off after confirming the player is on visible terrain. Run one control
   with the existing full campaign stack before treating Real Orbits as causal.
6. Track the Crew Enabled/AiEnabled cockpit cleanup crash independently. A
   focused control should reproduce NPC crew spawn/despawn around a moving
   `Valkyrie` grid and verify whether it also crashes without RSG/RSS teleport
   activity.

No fix, save edit, configuration change, mod-list change, or campaign activation
was performed during this diagnostic pass.
