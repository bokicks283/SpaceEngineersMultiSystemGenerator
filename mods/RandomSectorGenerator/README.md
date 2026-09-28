# Random Sector Generator — v0.2 audit/bootstrap

Experimental one-shot bootstrap mod for **Space Engineers + Real Solar Systems**.

This build generates a randomized multi-system sector without manually placing planets in TSE. The normal entry point is the repository-installed `Random Sector` Custom Game; disposable worlds remain supported for developer recovery.

## Current campaign pool

Custom definitions:
- Cauldron
- Tellus
- Agni
- Kor
- Jormun
- Zenitaia
- OrlundaSide
- Relicta
- Kerbin - Water Mod Ready
- Aulden

Vanilla definitions:
- EarthLike
- Moon
- Mars
- Europa
- Alien
- Titan
- Triton
- Pertam

The runtime allowlist is deliberate. Loaded planet mods outside this list are not silently included.

## Generation behavior

- Deterministic optional seed; random seed for automatic bootstrap.
- 3–5 root systems.
- Real Stars physical stars.
- Real Gas Giants gas giants.
- Requires the locally verified `DefaultBlackHole` skin and creates a black-hole-centered hierarchy.
- Random planet/moon distribution with orbital-envelope validation.
- Starter must be Tellus or EarthLike.
- Full generated hierarchy is written only to a spoiler/debug world-storage manifest.
- Partial generation rolls back spawned entities and permanently locks that disposable bootstrap attempt.

## Safety gate

RSG will not generate unless the checkpoint variable contains either the
reusable-template marker:

```text
RSG_DisposableBootstrap_v1 = random-sector-template-v1
```

or the legacy developer/recovery value `armed`. The template marker is written
by `Install-RandomSector.ps1`; players do not run an arm command.

It also refuses generation when:
- a denylisted Workshop mod is active,
- loaded voxel materials exceed the conservative budget of 120,
- planet/star entities already exist,
- the required APIs are unavailable,
- no approved starter is loaded,
- the verified black-hole skin is unavailable,
- a previous bootstrap is pending/completed/interrupted.

## RSS handoff

After RSG generates:

1. RSG writes the pending protobuf config to RSS's own checkpoint variable and
   changes its arm value to `handoff-pending`.
2. Save and exit to the menu.
3. Reload the world.
4. RSS adopts/spawns the configured bodies.
5. RSG verifies all pre-spawned bodies are RSS-managed and waits for a finite,
   valid starter proxy state that remains stable across consecutive checks.
6. RSG converts a physical surface point and player orientation into the RSS
   proxy frame, moves the player, and verifies RSS assigned the player to the
   starter surface zone.
7. Only after that validation does RSG mark the bootstrap applied and change
   the arm value to `complete`.

RSG should remain in the save until adoption has been verified. Removing it afterward is a later acceptance test, not an assumption.

## Chat commands

```text
/rsg help
/rsg status
/rsg adoption
/rsg recoverstarter
/rsg skins
/rsg planets
/rsg generate [seed]
```

Manual `/rsg generate` is still subject to every safety gate above.

`/rsg recoverstarter` is a host-only recovery for an already adopted save. It
waits for the same proxy-readiness checks, repeats the corrected starter
teleport, and validates the RSS surface zone without changing the generated
hierarchy or the adoption flags.

## Known acceptance risks

- In-game script whitelist/runtime validation is still required even after offline CLR compilation.
- Every custom terrestrial body must have exactly one valid RSS proxy before the disposable world is armed.
- MES planetary encounter precision around RSS's far-away physical voxel planets still requires an in-game acceptance test.
