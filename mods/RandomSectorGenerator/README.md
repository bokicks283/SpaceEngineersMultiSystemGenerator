# Random Sector Generator 0.2 audit build

This is an experimental local bootstrap for an offline-prepared, disposable Space Engineers world. It has passed an offline compile against the installed game assemblies but **has not passed in-game generation, reload, RSS adoption, MES, Water Mod, or science acceptance**.

The game selects the seed randomly by default. `/rsg generate <signed 32-bit seed>` gives a repeatable system layout. An armed disposable world also generates automatically when RSS, Real Stars, and Real Gas Giants APIs are ready. `/rsg status`, `/rsg skins`, and `/rsg planets` show setup without revealing the sector map.

The current definition allowlist is Tellus, Agni, Cauldron, Kor, Teal-WaterMod, Teralis - City Planet, Zenitaia, EarthLike, Moon, Mars, and Europa. Denylisted Workshop IDs and more than 120 loaded voxel material subtypes stop generation. Tellus, then EarthLike, are the only starters. The verified `DefaultBlackHole` skin must be present. The generator selects three to five root systems, places a black-hole cluster with multiple stars, and records a private manifest in world storage.

Generated entities are guarded by a world state file. A crash or interrupted generation locks that disposable save; restore its baseline before retrying. After generation, **save and exit the game**. The local `scripts/world_checkpoint.py commit` tool validates the saved entities, archives the whole disposable world, and commits the pending RSS protobuf configuration to its checkpoint variable. Reload only after that step. RSS then loads the hierarchy from its ordinary persisted configuration. The RSG mod remains installed until adoption is confirmed; removing it after adoption has not yet been validated.

The baseline is prepared by `scripts/world_checkpoint.py prepare`; it starts with `RSG_DisposableBootstrap_v1=blocked-proxies` while the required proxy art is missing. Arming is a separate local step after proxy coverage is verified.
