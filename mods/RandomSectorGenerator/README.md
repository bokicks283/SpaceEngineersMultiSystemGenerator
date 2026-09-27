# Random Sector Generator — v0.2 audit/bootstrap

Experimental one-shot bootstrap mod for **Space Engineers + Real Solar Systems**.

This build generates a randomized multi-system sector without manually placing planets in TSE. It is intentionally guarded so it only runs in an offline-prepared disposable world.

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

RSG will not generate unless the checkpoint variable:

```text
RSG_DisposableBootstrap_v1 = armed
```

was written by the offline `scripts/world_checkpoint.py arm` command.

It also refuses generation when:
- a denylisted Workshop mod is active,
- loaded voxel materials exceed the conservative budget of 120,
- planet/star entities already exist,
- the required APIs are unavailable,
- no approved starter is loaded,
- the verified black-hole skin is unavailable,
- a previous bootstrap is pending/completed/interrupted.

## RSS handoff

Do **not** rely on mod load order to inject RSS configuration.

After RSG generates:

1. Save the disposable world.
2. Exit Space Engineers completely.
3. Run the repository's offline `world_checkpoint.py commit` command.
4. The tool verifies RSG state and saved entity IDs, archives the world, writes the pending protobuf config to RSS's normal checkpoint variable, and disarms RSG.
5. Reload the world.
6. RSS adopts/spawns the configured bodies.
7. RSG verifies all pre-spawned bodies are RSS-managed, moves the player to the starter proxy, and marks the bootstrap applied.

RSG should remain in the save until adoption has been verified. Removing it afterward is a later acceptance test, not an assumption.

## Chat commands

```text
/rsg help
/rsg status
/rsg skins
/rsg planets
/rsg generate [seed]
```

Manual `/rsg generate` is still subject to every safety gate above.

## Known acceptance risks

- In-game script whitelist/runtime validation is still required even after offline CLR compilation.
- Every custom terrestrial body must have exactly one valid RSS proxy before the disposable world is armed.
- MES planetary encounter precision around RSS's far-away physical voxel planets still requires an in-game acceptance test.
