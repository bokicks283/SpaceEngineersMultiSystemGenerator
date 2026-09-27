# Space Engineers survival campaign workspace

Status: **prepared for a disposable compile/load check; sector generation remains disarmed.** The selected pack has 118 static unique voxel material subtypes against a conservative budget of 120. The original save and installed RSG prototype have timestamped ZIP backups under `backups/`.

`reports/PACK-AUDIT.md` lists every selected Workshop ID, planet cut, proxy status, science status, and current risk. `reports/inventory.json` is the local inventory from the three Steam libraries; `reports/selected-voxel-audit.json`, `reports/coverage.json`, and `reports/planet-cut-options.json` hold the detailed machine-readable evidence.

The local source is `mods/RandomSectorGenerator`. `mods/CampaignScienceCompatibility` adds authored science definitions for Cauldron and Zenitaia (and an unused Relicta preset) without touching Workshop files. `Install-RandomSectorGenerator.ps1` backs up the installed RSG and installs these local mods. `scripts/Build-RSG.ps1` compiles RSG against the installed game assemblies. `scripts/verify_local.py` checks the pack, wire tags, saved mod list, original backup, and safety arm state.

The disposable world is `%APPDATA%\SpaceEngineers\Saves\76561198045624840\RSG Disposable Audit 2026-09-27`. It was cloned from the existing RSS Empty World, with stale Workshop entries and prior mod storage removed. Its checkpoint arm variable is `blocked-proxies`, so it cannot generate by accident. The original world was never changed.

## Required asset work

The selected Cauldron System already provides its four RSS proxies. Teal-WaterMod, Teralis - City Planet, and Zenitaia still have no active exact proxy. Steam subscriptions/downloads are the user's part of this work. The [Alkurah SD proxy pack](https://steamcommunity.com/sharedfiles/filedetails/?id=3357964376) may cover Teal and Teralis, subject to checking its actual installed definitions. The [RSS Planet Exporter](https://steamcommunity.com/sharedfiles/filedetails/?id=3350589349) is the upstream tool for producing Zenitaia proxy textures in game. Avoid the Alkurah HD duplicate. Do not arm this world until `reports/coverage.json` shows exactly one selected proxy for every selected body and the proxy textures load.

The exporter requires in-game rendering of the planet; its current instructions list `/ExportCM` and `/ExportNG` and BC7 DDS conversion. Once installed, the agent can prepare a separate local proxy mod definition, convert the exported files with the game's `texconv.exe`, and validate it. No protected Workshop planet assets should be copied.

## Runtime sequence after proxy coverage

The agent reruns `python scripts/audit.py` and `python scripts/prepare_pack.py`, updates the disposable mod list if needed, installs any local proxy mod, then runs `python scripts/world_checkpoint.py arm <disposable-world-path>`. The user loads the disposable world. RSG generates once automatically after its APIs are ready; `/rsg status` shows state. The user saves and **exits the game**. The agent runs `python scripts/world_checkpoint.py commit <disposable-world-path>`, which checks all generated entities, archives the world, and writes the pending RSS config to the checkpoint. On reload, RSS should adopt all saved bodies. RSG marks bootstrap complete only after its starter and all pre-spawned celestial bodies are managed and the player reaches the starter proxy.

Runtime acceptance still needs checks for script compilation, exact proxy rendering, three-to-five roots, a black-hole root, a breathable Tellus starter, Water Mod on the selected water worlds, Scientific Progress discoveries, MES/Assertive/Abandoned/AiEnabled encounter spawning, and a clean `SpaceEngineers.log`. The mod must remain in the save until RSS adoption is verified; removal afterward is not yet validated. The MES physical-voxel precision issue documented in the audit has no proven setting-only fix.
