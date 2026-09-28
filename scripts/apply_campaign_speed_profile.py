"""Apply the current campaign high-speed profile to an existing save.

The campaign uses Relative Top Speed as the single grid-speed owner:
- 5,000 m/s physical hard ceiling
- existing mass-based cruise curves
- 5,000 m/s boost ceiling
- 1,000 m/s remote/autopilot ceiling during the first safety pass

Aerodynamic Physics is aligned to the same ship ceiling while preserving the
400 m/s SimulationMaxSpeed used by the campaign's atmospheric/reentry tuning.
Real Orbits speed multipliers must remain disabled.
"""
from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from world_checkpoint import archive, ensure_closed

SPEED_LIMIT = 5000
REMOTE_LIMIT = 1000
AERO_SIMULATION_MAX_SPEED = 400

PROFILE = {
    "LargeGrid": {
        "CruiseCurve": [(200000, 1200), (5000000, 850), (8000000, 650)],
        "MaxBoostSpeed": 5000,
        "ResistanceMultiplier": 1.5,
    },
    "SmallGrid": {
        "CruiseCurve": [(10000, 1200), (300000, 1000), (400000, 950)],
        "MaxBoostSpeed": 5000,
        "ResistanceMultiplier": 1.0,
    },
}


def read_mod_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:256]:
        return raw.decode("utf-16"), "utf-16"
    return raw.decode("utf-8-sig"), "utf-8"


def write_atomic(path: Path, text: str, encoding: str) -> None:
    temp = path.with_name(path.name + ".campaign-speed-tmp")
    temp.write_text(text, encoding=encoding, newline="")
    os.replace(temp, path)


def read_tag(text: str, tag: str) -> str | None:
    match = re.search(
        rf"<{re.escape(tag)}>([^<]+)</{re.escape(tag)}>",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def replace_tag(text: str, tag: str, value) -> str:
    pattern = re.compile(
        rf"(<{re.escape(tag)}>)([^<]*)(</{re.escape(tag)}>)",
        re.IGNORECASE,
    )
    updated, count = pattern.subn(
        lambda match: match.group(1) + str(value) + match.group(3),
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Expected exactly one <{tag}>; found {count}")
    return updated


def update_grid(text: str, grid_name: str, settings: dict) -> str:
    pattern = re.compile(
        rf"(<{re.escape(grid_name)}>)(.*?)(</{re.escape(grid_name)}>)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"RTS config has no {grid_name} section")

    block = match.group(2)
    for mass, speed in settings["CruiseCurve"]:
        point = re.compile(
            rf'(<Point\b(?=[^>]*\bMass="{mass}")(?=[^>]*\bSpeed=")[^>]*\bSpeed=")([^"]+)("[^>]*/>)',
            re.IGNORECASE,
        )
        block, count = point.subn(
            lambda found: found.group(1) + str(speed) + found.group(3),
            block,
            count=1,
        )
        if count != 1:
            raise RuntimeError(
                f"Expected one {grid_name} cruise point for mass {mass}; found {count}"
            )

    block = replace_tag(block, "MaxBoostSpeed", settings["MaxBoostSpeed"])

    resistance = read_tag(block, "ResistanceMultiplier")
    if resistance is None:
        raise RuntimeError(f"{grid_name} has no ResistanceMultiplier")
    if float(resistance) != float(settings["ResistanceMultiplier"]):
        raise RuntimeError(
            f"{grid_name} ResistanceMultiplier={resistance} differs from expected "
            f"{settings['ResistanceMultiplier']}; refusing to overwrite it"
        )

    return text[: match.start(2)] + block + text[match.end(2) :]


def find_one(root: Path, name: str) -> Path:
    matches = list((root / "Storage").rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {name}; found {len(matches)}")
    return matches[0]


def verify_real_orbits(world: Path) -> dict:
    candidates = []
    for path in (world / "Storage").rglob("Config.xml"):
        text, _ = read_mod_text(path)
        hint = str(path.parent).lower() + "\n" + text.lower()
        if (
            "realisticgravity" in hint
            or "globalmaxspeedmultiplier_largegrid" in hint
            or "globalmaxspeedmultiplier_smallgrid" in hint
        ):
            candidates.append((path, text))

    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected exactly one Real Orbits Config.xml; found {len(candidates)}"
        )

    path, text = candidates[0]
    values = {}
    for tag in (
        "GlobalMaxSpeedMultiplier_LargeGrid",
        "GlobalMaxSpeedMultiplier_SmallGrid",
    ):
        raw = read_tag(text, tag)
        if raw is None:
            raise RuntimeError(f"Real Orbits config is missing {tag}")
        value = float(raw)
        if value > 0:
            raise RuntimeError(
                f"Real Orbits {tag}={value} would compete with RTS; expected <= 0"
            )
        values[tag] = value

    return {"path": str(path.relative_to(world)), "values": values}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path, help="Existing Space Engineers save directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_closed()

    world = args.save.expanduser().resolve()
    if not world.is_dir() or not (world / "Sandbox.sbc").is_file():
        raise SystemExit("ERROR: not a complete Space Engineers save: " + str(world))

    rts = find_one(world, "RelativeTopSpeed.cfg")
    ro = verify_real_orbits(world)

    rts_text, rts_encoding = read_mod_text(rts)
    previous = {
        "SpeedLimit": read_tag(rts_text, "SpeedLimit"),
        "RemoteControlSpeedLimit": read_tag(rts_text, "RemoteControlSpeedLimit"),
    }

    rts_text = replace_tag(rts_text, "SpeedLimit", SPEED_LIMIT)
    rts_text = replace_tag(rts_text, "RemoteControlSpeedLimit", REMOTE_LIMIT)
    rts_text = update_grid(rts_text, "LargeGrid", PROFILE["LargeGrid"])
    rts_text = update_grid(rts_text, "SmallGrid", PROFILE["SmallGrid"])

    aero_matches = list((world / "Storage").rglob("dragsettings.xml"))
    if len(aero_matches) > 1:
        raise SystemExit(
            f"ERROR: expected at most one Aerodynamic Physics dragsettings.xml; "
            f"found {len(aero_matches)}"
        )

    aero = aero_matches[0] if aero_matches else None
    aero_text = None
    aero_encoding = None
    aero_previous = None

    if aero is not None:
        aero_text, aero_encoding = read_mod_text(aero)
        aero_previous = {
            "SmallShipMaxSpeed": read_tag(aero_text, "SmallShipMaxSpeed"),
            "LargeShipMaxSpeed": read_tag(aero_text, "LargeShipMaxSpeed"),
            "SimulationMaxSpeed": read_tag(aero_text, "SimulationMaxSpeed"),
        }
        aero_text = replace_tag(aero_text, "SmallShipMaxSpeed", SPEED_LIMIT)
        aero_text = replace_tag(aero_text, "LargeShipMaxSpeed", SPEED_LIMIT)
        aero_text = replace_tag(
            aero_text, "SimulationMaxSpeed", AERO_SIMULATION_MAX_SPEED
        )

    print("Save:", world)
    print("RTS:", rts.relative_to(world))
    print("RTS previous:", previous)
    print(
        f"RTS target: SpeedLimit={SPEED_LIMIT}, "
        f"RemoteControlSpeedLimit={REMOTE_LIMIT}, MaxBoostSpeed={SPEED_LIMIT}"
    )
    print("Real Orbits speed multipliers:", ro["values"])
    if aero is None:
        print("Aero: no dragsettings.xml found; no Aero file will be changed")
    else:
        print("Aero:", aero.relative_to(world))
        print("Aero previous:", aero_previous)
        print(
            f"Aero target: Small/Large={SPEED_LIMIT}, "
            f"SimulationMaxSpeed={AERO_SIMULATION_MAX_SPEED}"
        )

    if args.dry_run:
        print("DRY RUN: no files changed.")
        return

    backup = archive(world, "World-before-5kms-campaign-speed")
    write_atomic(rts, rts_text, rts_encoding)
    if aero is not None:
        write_atomic(aero, aero_text, aero_encoding)

    verify_rts, _ = read_mod_text(rts)
    if int(float(read_tag(verify_rts, "SpeedLimit"))) != SPEED_LIMIT:
        raise RuntimeError("RTS SpeedLimit readback mismatch")
    if int(float(read_tag(verify_rts, "RemoteControlSpeedLimit"))) != REMOTE_LIMIT:
        raise RuntimeError("RTS RemoteControlSpeedLimit readback mismatch")

    if aero is not None:
        verify_aero, _ = read_mod_text(aero)
        if int(float(read_tag(verify_aero, "SmallShipMaxSpeed"))) != SPEED_LIMIT:
            raise RuntimeError("Aero SmallShipMaxSpeed readback mismatch")
        if int(float(read_tag(verify_aero, "LargeShipMaxSpeed"))) != SPEED_LIMIT:
            raise RuntimeError("Aero LargeShipMaxSpeed readback mismatch")

    print("Backup:", backup)
    print("Applied campaign 5 km/s physical-flight profile.")
    print("Next load: run /rts load, then /rts config and verify SpeedLimit=5000.")


if __name__ == "__main__":
    main()
