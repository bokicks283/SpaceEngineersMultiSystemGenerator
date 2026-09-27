# Post-sector Campaign Activation

This phase begins only after the selected planet pool and proxies are complete,
RSG has generated the final sector, the offline RSS handoff has been committed,
and a reload has verified RSS adoption and the final body hierarchy. It must
finish before the world is presented as ready for normal survival play.

## Pre-activation state

During generation and RSS adoption, both `Sandbox.sbc` and
`Sandbox_config.sbc` must have Economy, Cargo Ships, Random Encounters, and
Planetary Encounters off and `GlobalEncounterCap` set to zero. The disposable
world checkpoint tooling now checks this before arming or committing.

The original `RSG Disposable Audit 2026-09-27` inherited 72 NPC economy station
records and an Economy component with `GenerateFactionsOnStart=false` from its
source Empty World save, even though `EnableEconomy=false` at the time of audit.
It is preserved but excluded from sector generation. The new
`RSG Disposable Clean 2026-09-27` was cloned from the installed stock Empty
World template before any game launch. It has zero station records and no
Economy component. Static validation passes; its first in-game load remains
to be tested.

| Saved setting | Earlier disposable (before this work) | Clean disposable |
|---|---:|---:|
| Economy | off | off |
| Cargo Ships | off | off |
| Random Encounters | off | off |
| Planetary Encounters | on | off |
| Global Encounter Cap | 1 | 0 |
| TradeFactionsCount | 10 | absent in stock template |
| StationsDistanceInnerRadius | 5,000,000 | absent in stock template |
| StationsDistanceOuterRadiusStart | 5,000,000 | absent in stock template |
| StationsDistanceOuterRadiusEnd | 10,000,000 | absent in stock template |

The clean template's absent fields require effective-default verification in
the installed game before any activation value is proposed.

## Required finalization workflow

1. Audit RSG completion, committed RSS handoff, adopted hierarchy, exact final
   bodies, stable topology, and the disabled pre-activation settings. Refuse
   activation if economy factions or stations were generated prematurely.
2. Inspect selected planet definitions for explicit or default values of
   `AllowSurfaceEconomyStations`, `AllowOrbitalEconomyStations`, and
   `AllowContractSpawns`. Report intentional hostile-world exceptions; place
   any necessary overrides in a local compatibility mod, never Workshop files.
3. Inspect the saved station distance radii, `TradeFactionsCount`, vanilla
   Planetary Encounter filters, MES/PvE settings, and respawn behavior. Treat
   the current values as evidence, not as recommended activation values.
4. Back up the entire adopted sector as `Pre-Economy-Final-Sector`, then make
   an `RSG Economy QA` clone. First enable Economy and any chosen vanilla
   encounter systems only in that QA copy. Save, reload, and inspect faction,
   station, contract, and encounter distribution across systems without
   revealing the generated map to the player.
5. After QA passes, back up the real campaign again and apply only the
   verified settings. Preserve the sector topology and never rerun RSG.

Reusable finalization tooling should expose explicit audit, QA preparation,
QA activation, QA inspection, and real activation commands. Every save write
must require Space Engineers to be closed, verify the save target, archive the
complete save, update both checkpoint/config settings, and validate XML before
replacement. Economy distance and trade faction values must be configurable
and reported as original versus planned. Planetary Encounters remain disabled
unless the installed game's name/material filters and spawn density pass QA.
MES's long-distance NPC precision concern remains open until tested in the
adopted RSS sector. Campaign readiness also requires water, science, PvE, and
respawn acceptance, followed by a final activation backup.

No finalization command has been run or applied to a campaign save yet.
