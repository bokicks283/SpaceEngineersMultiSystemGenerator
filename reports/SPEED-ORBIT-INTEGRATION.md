# Speed and orbit integration

This note records the installed-source behavior verified before the first full runtime load of `RSG Disposable Clean 2026-09-27`. It does not prescribe final tuning.

## Ownership and defaults

- Relative Top Speed (`1359618037`) writes the global SmallGrid and LargeGrid limits, applies mass-based per-grid cruise and boost resistance, and sets remote-control speed limits. Its defaults are a 140 m/s world ceiling and 100 m/s remote-control ceiling. Boosting is enabled. Small-grid cruise points are 10,000 kg at 110 m/s, 300,000 kg at 95 m/s, and 400,000 kg at 90 m/s, with 140 m/s maximum boost and resistance multiplier 1. Large-grid points are 200,000 kg at 110 m/s, 5,000,000 kg at 80 m/s, and 8,000,000 kg at 60 m/s, with 140 m/s maximum boost and resistance multiplier 1.5.
- Aerodynamic Physics (`571920453`) defaults SmallShipMaxSpeed and LargeShipMaxSpeed to 150 m/s, SimulationMaxSpeed to 1000 m/s, drag and heat-radiation multipliers to 100, heat enabled, and DisableReEntry false. It raises an engine limit only when that limit is below its configured minimum, then adopts and saves a higher existing engine limit. It therefore does not lower a higher RTS ceiling. It also clamps remote-control settings, so that interaction requires runtime validation.
- Real Orbits (`2609118808`) can set global SmallGrid and LargeGrid limits to 100 times its respective multipliers. Both multipliers default to `-1`, and the writes occur only for values above zero. Leave these defaults unchanged so RTS remains authoritative.
- Real Solar Systems (`3351055036`) writes the global speed limit only when GlobalSpeedLimit is above zero. Its global speed, orbit-zone speed, surface-zone speed, and per-body orbit/surface limits default to `-1`. RSG emits `-1` for all of them, so RSS imposes no speed cap.

## Configuration lifecycle

- RTS reads `RelativeTopSpeed.cfg` from world storage scoped to `RelativeTopSpeed.Settings`, falls back to the same scoped local-storage file, or creates defaults. A successful first server load writes both the world file and, if absent, the local fallback. `/rts config` displays the active XML. After a later edit, `/rts load` applies it live for an owner/admin; a game restart is not required.
- Aero reads `dragsettings.xml` from world storage scoped to `SEDrag.DragSettings`, then the `DragSettings` session variable, then defaults. Dedicated servers write it during initialization. An offline/listen host writes it when an admin setting changes or when Aero adopts a higher engine limit; its explicit Save menu items are disabled in this installed version. A normal save/reload alone is therefore not guaranteed to create the file. The mod has no chat status command.
- Real Orbits creates `Config.xml` in world storage scoped to `RealisticGravity.OrbitSettingsConfig` on the server's first load. It has no chat status command.

The exact on-disk type-scope folder names are created by Space Engineers. Confirm those generated paths after the first runtime load rather than pre-creating files.

## RSS and Real Orbits gravity

Real Orbits requires inverse-square planet gravity and, with its default OverridePlanetGravityFalloff enabled, changes loaded spherical planet gravity falloff to `2`. RSS detects Workshop `2609118808`; when an adopted terrestrial body's payload falloff is unset (`-1`), RSS substitutes `2`. RSG intentionally continues to emit `-1` so RSS and Real Orbits use their supported integration behavior.

RSS owns `/SetupRealOrbits`. The command changes all bodies already adopted by RSS: terrestrial planets get falloff `2` plus `UpdateTerrestrialGravity`; gas giants and stars get falloff `2`, push their API data, and reinitialize proxy gravity. Run it only after RSS adoption is complete, then save. Do not run it in the clean pre-generation world.

## Runtime acceptance checks

No installed-source launch blocker was found. Validate these interactions later in game:

- RSS frame and zone transitions at high RTS velocity.
- Real Orbits behavior around RSS-managed planets, gas giants, and stars.
- Aero forces, heating, and reentry at high speed.
- RTS remote-control/autopilot behavior, including Aero's remote-control clamp.
- MES and NPC behavior at campaign speeds.
- Economy orbital contacts and stations under Real Orbits.
- Collision and tunneling behavior at extreme speed.

The source-overlap classifications are:

- RTS plus Aero global limits: compatible by default/config. Aero only raises a lower environment limit and adopts a higher one; startup ordering still needs runtime confirmation.
- RTS plus Real Orbits global limits: compatible by default/config because both Real Orbits multipliers are disabled at `-1`.
- RSS speed limits: compatible by default/config because every emitted global and per-body speed override is `-1`.
- RSS plus Real Orbits: compatible by explicit API integration, with orbital behavior and velocity transforms requiring later runtime validation.
- Aero plus RSS frame transitions: no direct integration or definite conflict was found; requires later runtime validation.
