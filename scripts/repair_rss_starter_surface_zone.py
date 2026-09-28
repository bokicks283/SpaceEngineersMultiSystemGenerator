"""Temporarily repair an adopted RSS world's starter surface-zone radius.

This is a targeted Phase A diagnostic/recovery tool for worlds generated before
RSG sized RSS surface zones from the voxel planet terrain envelope.

It edits only RSS Config.xml, after making a timestamped backup, and sets
OverrideFromConfig=true so RSS imports the corrected value on the next load.
"""
import argparse
import datetime as dt
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RSS_STORAGE = "3351055036.sbm_RealSolarSystems"
RSG_STORAGE = "RandomSectorGenerator_RandomSectorGenerator"


def ensure_game_closed():
    if sys.platform != "win32":
        return
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SpaceEngineers.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "SpaceEngineers.exe" in result.stdout:
        raise RuntimeError("Exit Space Engineers before repairing RSS Config.xml.")


def child_text(node, name):
    child = node.find(name)
    return None if child is None else child.text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("save", type=Path, help="Path to the Space Engineers save directory")
    parser.add_argument(
        "--multiplier",
        type=float,
        default=1.15,
        help="Minimum starter surface-zone radius as a multiple of nominal radius (default: 1.15)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.multiplier <= 1.0:
        raise SystemExit("--multiplier must be greater than 1.0")

    ensure_game_closed()

    save = args.save.expanduser().resolve()
    config_path = save / "Storage" / RSS_STORAGE / "Config.xml"
    state_path = save / "Storage" / RSG_STORAGE / "RandomSectorGenerator.State.xml"
    if not config_path.is_file():
        raise SystemExit("RSS Config.xml not found: " + str(config_path))
    if not state_path.is_file():
        raise SystemExit("RSG state not found: " + str(state_path))

    state_root = ET.parse(state_path).getroot()
    starter_name = child_text(state_root, "StartPlanetDisplayName")
    starter_subtype = child_text(state_root, "StartPlanetSubtype")
    if not starter_name or not starter_subtype:
        raise SystemExit("RSG state does not identify the starter planet.")

    tree = ET.parse(config_path)
    root = tree.getroot()

    matches = []
    for body in root.iter("CelestialBodyConfig"):
        if child_text(body, "Name") != starter_name:
            continue
        if child_text(body, "PlanetTypeId") != starter_subtype:
            continue
        terrestrial = body.find("TerrestrialPlanetInfo")
        if terrestrial is not None:
            matches.append((body, terrestrial))

    if len(matches) != 1:
        raise SystemExit(
            "Expected exactly one terrestrial starter body for %s [%s]; found %d"
            % (starter_name, starter_subtype, len(matches))
        )

    body, terrestrial = matches[0]
    radius_node = terrestrial.find("RadiusKm")
    zone_node = terrestrial.find("PlanetSurfaceZoneRadius")
    if radius_node is None or zone_node is None:
        raise SystemExit("Starter terrestrial config is missing radius/surface-zone values.")

    nominal_radius = float(radius_node.text) * 1000.0
    old_zone = float(zone_node.text)
    new_zone = max(old_zone, nominal_radius * args.multiplier)

    print("Save:", save)
    print("Starter:", starter_name, "[%s]" % starter_subtype)
    print("BodyInstanceName:", body.attrib.get("BodyInstanceName", "<missing>"))
    print("Nominal radius: %.3f m" % nominal_radius)
    print("Surface zone: %.3f m -> %.3f m" % (old_zone, new_zone))

    if args.dry_run:
        print("Dry run only; no files changed.")
        return

    override = root.find("OverrideFromConfig")
    if override is None:
        raise SystemExit("RSS Config.xml is missing OverrideFromConfig.")
    override.text = "true"
    zone_node.text = ("%.6f" % new_zone).rstrip("0").rstrip(".")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_path.with_name("Config.pre-surface-zone-repair-%s.xml" % stamp)
    shutil.copy2(config_path, backup)

    tree.write(config_path, encoding="utf-16", xml_declaration=True)

    # Verify the written XML is still readable and the requested values persisted.
    verify = ET.parse(config_path).getroot()
    if child_text(verify, "OverrideFromConfig") != "true":
        raise RuntimeError("RSS override flag verification failed.")

    print("Backup:", backup)
    print("Updated:", config_path)
    print("Next load will import Config.xml once; RSS should reset OverrideFromConfig on save.")


if __name__ == "__main__":
    main()
