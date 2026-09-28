# RSG readiness fix and Crew Enabled follow-up — 2026-09-27

## Scope

This pass changes only Random Sector Generator's post-adoption starter
readiness, teleport, and recovery path. It does not change the sector topology,
campaign mod list, economy state, encounter settings, or Crew Enabled.

## RSS readiness and teleport correction

The installed Real Solar Systems API exposes the current logical body position,
surface rotation, entity zone, zone bounds, and physical-to-proxy conversion.
RSG now binds `GetBodyProxyPosition`, `GetBodyProxyRotation`, and
`GetEntityZone` in addition to its existing `GetBodyZoneRange` and
`ConvertPlanetPosToProxy` bindings.

Adoption no longer completes from body resolution and `IsManagedBody` alone.
The starter must also:

- be resolved through the persisted `StorageName`;
- report finite proxy position, rotation, and zone bounds;
- be past the conservative tick-360 startup floor;
- not report the solar-system origin when its persisted RSS body is orbiting;
- remain valid with bounded motion for three consecutive one-second checks.

The bounded-motion tolerance is derived from RSS's current orbit-zone range and
allows normal orbital movement while rejecting discontinuous or reinitialized
state.

For teleport, RSG selects a physical surface point, converts it through RSS,
and derives logical up from the converted point relative to the current proxy
center. RSS converts physical offsets with the inverse of its published proxy
rotation, so RSG applies that same inverse to the player's forward basis. It
then teleports and clears linear and angular velocity.

On the following readiness check, RSG requires `GetEntityZone` to identify the
player as being in the exact starter planet's surface zone and requires the
player's current radius to remain within the reported surface-zone bound. A
failure leaves `PendingApply=true`, retries later, and never writes
`Applied=true`.

The host-only `/rsg recoverstarter` command runs the same readiness, transform,
teleport, and zone-validation path against an already adopted save. It does not
write adoption flags or regenerate the hierarchy and can be repeated.

## Crew Enabled and AiEnabled crash path

The current installed sources confirm the captured path:

1. `CrewEnabledGrid.OnSyncOutAreaExited` removes the last player from the
   grid's sync set and calls `DecrewGrid`.
2. `DecrewGrid` removes Crew Enabled listeners and seating-map entries, then
   calls `CrewEnabledSession.DeleteBot` for each crew character.
3. `DeleteBot` calls AiEnabled's public `RemoveBot` directly. It does not first
   call `TryRemoveBotFromSeat`, validate that the character is still the
   cockpit's pilot, or inspect the result of `RemoveBot`.
4. AiEnabled `LocalBotAPI.CloseBot` checks that its bot object exists and is not
   dead, then calls `BotBase.Close(true)`.
5. `BotBase.Close` runs cleanup, reads `Character.Parent as IMyCockpit`, and
   calls `seat?.RemovePilot()`. The engine then throws inside
   `MyCockpit.RemovePilot`, consistent with a cockpit reference whose internal
   pilot state has already become stale or partially cleared.

This is a concrete stale-seat cleanup race, but the existing evidence contains
one occurrence while the player was abnormally stranded at the root-star proxy
center. The trigger is specifically sync-area exit, so rapid or discontinuous
player/zone movement remains a plausible contributor. The evidence does not
yet prove a generic Crew Enabled failure or an RCSP-only failure.

Crew Enabled supports `BlacklistGrids` and `BlacklistFactions`. Both use exact,
case-insensitive equality. Grid matching is against `IMyCubeGrid.Name`, not
`DisplayName`; faction matching is against the owning faction tag. The RCSP
spawn definition identifies the relevant prefab as `(NPC-RCSP) Valkyrie`, but
the source prefab's serialized grid `Name` is a numeric entity name while its
display name is the Valkyrie label. A display-name blacklist entry is therefore
not proven to match the runtime grid. No blacklist is applied in this pass.

## Required classification

**A — keep Crew Enabled unchanged while retesting after the starter-position
fix.**

If the same stack reproduces under normal starter positioning and only the
Valkyrie family triggers it, the next classification becomes B after capturing
the runtime `CubeGrid.Name` or faction tag needed for a supported exact
blacklist. If it reproduces across unrelated crewed grids, the smallest robust
code repair is in AiEnabled's `BotBase.Close`/seat cleanup or Crew Enabled's
pre-removal sequence; that would require a separately justified compatibility
strategy rather than a speculative change here.

## Runtime acceptance still required

Offline compilation and static pack checks cannot prove live RSS zone timing or
the absence of the cockpit cleanup crash. The existing adopted world is the
first test target:

1. Load `Random Sector 2026-09-27 21-24`.
2. Run `/rsg adoption`.
3. Run `/rsg recoverstarter`.
4. Confirm visible Tellus terrain, stable gravity direction, and unchanged
   `Applied=true` state.
5. Remain in the world long enough for normal Crew Enabled/MES spawn and
   sync-out behavior.

Only after recovery succeeds should one fresh Random Sector be created for the
full generation, save/reload, adoption, and starter-position acceptance test.
