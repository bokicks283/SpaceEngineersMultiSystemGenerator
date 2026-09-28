"""Apply the campaign speed profile to the clean disposable world.

Relative Top Speed owns the 5,000 m/s physical grid ceiling. If Aerodynamic Physics has
already generated dragsettings.xml, its SimulationMaxSpeed is set to 400 m/s
for the campaign's atmospheric/reentry scaling. Real Orbits and RSS keep their
speed overrides disabled.
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from world_checkpoint import (
    RSG_KEY,
    archive,
    check_pre_activation,
    ensure_closed,
    get_variable,
)

WORLD = (Path(os.environ["APPDATA"]) / "SpaceEngineers" / "Saves" /
         "76561198045624840" / "RSG Disposable")

AERO_SIMULATION_MAX_SPEED = 400

PROFILE = {
    "SpeedLimit": 5000,
    "RemoteControlSpeedLimit": 1000,
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


def read_mod_text(path):
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    return raw.decode("utf-8-sig"), "utf-8"


def write_atomic(path, text, encoding):
    temp = path.with_name(path.name + ".new")
    if encoding == "utf-16":
        temp.write_text(text, encoding="utf-16", newline="")
    else:
        # Keep the serializer's existing declaration untouched. RTS itself
        # already produced UTF-8 bytes with a UTF-16 declaration and reads the
        # file through the SE world-storage string API.
        temp.write_text(text, encoding="utf-8", newline="")
    os.replace(temp, path)


def replace_tag(text, tag, value):
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
        raise RuntimeError(f"Expected exactly one <{tag}> in config; found {count}")
    return updated


def update_grid(text, grid_name, settings):
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
    # Preserve the installed mod's resistance behavior, but fail if it no
    # longer matches the profile we audited instead of silently changing it.
    resistance = re.search(
        r"<ResistanceMultiplier>([^<]+)</ResistanceMultiplier>",
        block,
        re.IGNORECASE,
    )
    if not resistance:
        raise RuntimeError(f"{grid_name} has no ResistanceMultiplier")
    actual = float(resistance.group(1))
    expected = float(settings["ResistanceMultiplier"])
    if actual != expected:
        raise RuntimeError(
            f"{grid_name} ResistanceMultiplier changed from audited default "
            f"{expected} to {actual}; refusing to overwrite it"
        )

    return text[:match.start(2)] + block + text[match.end(2):]


def find_one(root, name):
    matches = list((root / "Storage").rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {name}; found {len(matches)}")
    return matches[0]


def read_tag(text, tag):
    match = re.search(
        rf"<{re.escape(tag)}>([^<]+)</{re.escape(tag)}>",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def verify_real_orbits(world):
    candidates = []
    for path in (world / "Storage").rglob("Config.xml"):
        text, _ = read_mod_text(path)
        hint = str(path.parent).lower() + "\n" + text.lower()
        if ("realisticgravity" in hint or
                "overridecreatedplanetgravityfalloff" in hint or
                "globalmaxspeedmultiplier_largegrid" in hint or
                "globalmaxspeedmultiplier_smallgrid" in hint):
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
                f"Real Orbits {tag}={value} would compete with RTS; expected disabled <= 0"
            )
        values[tag] = value
    return str(path.relative_to(world)), values


def main():
    ensure_closed()
    if not WORLD.is_dir():
        raise RuntimeError("Clean disposable world does not exist: " + str(WORLD))

    check_pre_activation(WORLD)
    checkpoint = ET.parse(WORLD / "Sandbox.sbc")
    if get_variable(checkpoint, RSG_KEY) != "blocked-proxies":
        raise RuntimeError("Clean disposable world is not in the expected disarmed state")

    rts = find_one(WORLD, "RelativeTopSpeed.cfg")
    ro_path, ro_values = verify_real_orbits(WORLD)

    aero_matches = list((WORLD / "Storage").rglob("dragsettings.xml"))
    if len(aero_matches) > 1:
        raise RuntimeError(
            f"Expected at most one Aerodynamic Physics dragsettings.xml; found {len(aero_matches)}"
        )
    aero = aero_matches[0] if aero_matches else None

    text, encoding = read_mod_text(rts)

    original = {
        "SpeedLimit": read_tag(text, "SpeedLimit"),
        "RemoteControlSpeedLimit": read_tag(text, "RemoteControlSpeedLimit"),
    }
    text = replace_tag(text, "SpeedLimit", PROFILE["SpeedLimit"])
    text = replace_tag(
        text, "RemoteControlSpeedLimit", PROFILE["RemoteControlSpeedLimit"]
    )
    text = update_grid(text, "LargeGrid", PROFILE["LargeGrid"])
    text = update_grid(text, "SmallGrid", PROFILE["SmallGrid"])

    aero_previous = None
    aero_text = None
    aero_encoding = None
    if aero is not None:
        aero_text, aero_encoding = read_mod_text(aero)
        aero_previous = read_tag(aero_text, "SimulationMaxSpeed")
        if aero_previous is None:
            raise RuntimeError("Aerodynamic Physics config is missing SimulationMaxSpeed")
        aero_text = replace_tag(
            aero_text, "SimulationMaxSpeed", AERO_SIMULATION_MAX_SPEED
        )

    backup = archive(WORLD, "World-before-speed-orbit-profile")
    write_atomic(rts, text, encoding)
    if aero is not None:
        write_atomic(aero, aero_text, aero_encoding)

    reread, _ = read_mod_text(rts)
    if int(read_tag(reread, "SpeedLimit")) != PROFILE["SpeedLimit"]:
        raise RuntimeError("RTS SpeedLimit readback mismatch")
    if int(read_tag(reread, "RemoteControlSpeedLimit")) != PROFILE["RemoteControlSpeedLimit"]:
        raise RuntimeError("RTS RemoteControlSpeedLimit readback mismatch")

    aero_result = {
        "config": None,
        "previous_simulation_max_speed": None,
        "simulation_max_speed": None,
        "state": "not generated yet; rerun after Aero creates dragsettings.xml",
    }
    if aero is not None:
        aero_reread, _ = read_mod_text(aero)
        actual_aero_speed = float(read_tag(aero_reread, "SimulationMaxSpeed"))
        if actual_aero_speed != float(AERO_SIMULATION_MAX_SPEED):
            raise RuntimeError("Aero SimulationMaxSpeed readback mismatch")
        aero_result = {
            "config": str(aero.relative_to(WORLD)),
            "previous_simulation_max_speed": aero_previous,
            "simulation_max_speed": AERO_SIMULATION_MAX_SPEED,
            "state": "configured",
        }

    print(json.dumps({
        "world": str(WORLD),
        "backup": str(backup),
        "rts_config": str(rts.relative_to(WORLD)),
        "previous": original,
        "profile": PROFILE,
        "real_orbits_config": ro_path,
        "real_orbits_speed_multipliers": ro_values,
        "aero": aero_result,
        "next": [
            "Load the clean disposable world once; do not arm or generate.",
            "Run /rts config and confirm SpeedLimit 5000 and RemoteControlSpeedLimit 1000.",
            "Confirm Aero SimulationMaxSpeed remains 400 after save/exit.",
            "Save and fully exit Space Engineers.",
            r"py scripts\speed_orbit_runtime.py",
            r"py scripts\runtime_check.py",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
