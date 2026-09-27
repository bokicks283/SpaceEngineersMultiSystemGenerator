# Random Sector Generator — v0.1.0-alpha

Experimental local bootstrap mod for **Space Engineers + Real Solar Systems**.

This build is intentionally an MVP for a new survival world. It creates a randomized multi-system RSS sector without manually placing planets in `/TSE`.

## What v0.1 does

- Discovers enabled `PlanetGeneratorDefinition`s from vanilla + loaded planet mods.
- Uses up to 24 usable planet definitions.
- Picks a survivable starter, preferring Tellus, Teal, Zenitaia, Teralis, then EarthLike.
- Generates roughly 4 logical root systems by default.
- Randomly distributes planets and moons among physical Real Stars.
- Creates up to two normal Real Gas Giants when skins are available.
- Creates a black-hole-centered cluster when a known black-hole Real Gas Giants skin is available (prefers `Trithorne`).
- Hides the generated map from normal chat output.
- Writes a spoiler/debug manifest into world storage for troubleshooting.
- Bootstraps RSS by serializing a wire-compatible RSS config, then lets RSS own the sector after reload.

## Required mods

- Real Solar Systems
- Real Stars
- Real Gas Giants
- Your selected planet mods / proxy packs

Other gameplay mods such as Water Mod, MES, Scientific Progress, etc. can remain enabled.

## IMPORTANT load order

In the **in-game Active Mods list**, put:

```text
Real Solar Systems
Random Sector Generator   <-- BELOW RSS
```

Space Engineers loads the in-game list bottom-to-top. RSG needs to run first on the bootstrap reload so it can inject the generated RSS configuration before RSS reads it.

Dependencies such as Real Stars / Real Gas Giants can remain where Space Engineers places them.

## First-world procedure

Use a **fresh RSS Empty World**. Do not generate into a world that already contains planets/stars.

1. Enable RSS, Real Stars, Real Gas Giants, RSG, and the planet mods you want in the pool.
2. Ensure **RSG is below RSS** in the in-game Active Mods list.
3. Load the empty world.
4. Wait several seconds, then run:

```text
/rsg status
```

You want Real Stars and Real Gas Giants to show `ready`.

5. Optional checks:

```text
/rsg skins
/rsg planets
```

`/rsg skins` should identify a black-hole candidate if your Real Gas Giants install provides one.

6. Generate a random sector:

```text
/rsg generate
```

Or use a reproducible seed:

```text
/rsg generate 123456
```

7. When RSG says generation succeeded, **save the world**.
8. Quit to the main menu.
9. Reload the same world.
10. Wait for:

```text
Random Sector Generator: RSS successfully adopted the generated sector. Bootstrap is complete.
```

Then play normally.

## Commands

```text
/rsg help
/rsg status
/rsg skins
/rsg planets
/rsg generate [seed]
```

## Important alpha limitations

- This has been source-audited against the user's installed RSS / SSG / System Manager code, but it has **not yet been compiled inside Space Engineers**. The first launch is an integration test.
- v0.1 is aimed at single-player / host-first bootstrap. Dedicated-server hardening comes later.
- Planet proxy quality depends on the RSS proxy definitions you have installed. Unsupported planets fall back to RSS's generic proxy rather than preventing generation.
- The generator currently considers all usable loaded planet definitions, including vanilla planets, up to the 24-body cap.
- Do not remove RSS, Real Stars, Real Gas Giants, or planet mods from the generated save casually.

## If bootstrap does not complete

Do not continue the survival campaign yet. Preserve the test save and collect `SpaceEngineers.log` plus the RSG world-storage state/manifest so the failure can be patched without revealing the sector layout to the player.
