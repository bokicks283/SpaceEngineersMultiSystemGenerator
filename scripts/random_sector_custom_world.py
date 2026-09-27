"""Build and validate the reusable Random Sector CustomWorld."""
import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from audit import ROOT, OUT
from world_checkpoint import (
    PRE_ACTIVATION_SETTINGS,
    RSG_KEY,
    RSS_KEY,
    check_no_economy_history,
    get_variable,
    put_variable,
    remove_variable,
    set_pre_activation_settings,
    write_atomic,
)

TEMPLATE_NAME = "Random Sector"
TEMPLATE_ARM_VALUE = "random-sector-template-v1"
ROOT_FILES = (
    "Sandbox.sbc",
    "Sandbox_config.sbc",
    "SANDBOX_0_0_0_.sbs",
    "SANDBOX_0_0_0_.sbsB5",
    "thumb.jpg",
)
LOCAL_MODS = (
    "RandomSectorGenerator",
    "CampaignScienceCompatibility",
    "CampaignPlanetProxies",
)
REQUIRED_SPEED_MODS = {"1359618037", "571920453", "2609118808", "3351055036"}
DENIED_SPEED_MODS = {"570767699", "570766507"}
DRAG_KEY = "DragSettings"
DRAG_ENVIRONMENT_KEY = "DragEnviroment"
ORBIT_KEY = "OrbitSettings_Config_xml"


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def set_text(root, name, value):
    node = root.find(name)
    if node is None:
        node = ET.SubElement(root, name)
    node.text = value


def set_mods(tree, workshop, local_mods):
    root = tree.getroot()
    mods = root.find("Mods")
    if mods is None:
        mods = ET.SubElement(root, "Mods")
    mods.clear()
    for item in workshop:
        node = ET.SubElement(mods, "ModItem")
        if item.get("title"):
            node.set("FriendlyName", item["title"])
        ET.SubElement(node, "Name").text = item["id"] + ".sbm"
        ET.SubElement(node, "PublishedFileId").text = item["id"]
        ET.SubElement(node, "PublishedServiceName").text = "Steam"
    for name in local_mods:
        node = ET.SubElement(mods, "ModItem")
        ET.SubElement(node, "Name").text = name


def validate_source(empty_world):
    missing = [name for name in ROOT_FILES if not (empty_world / name).is_file()]
    if missing:
        raise RuntimeError("Stock Empty World is missing root files: " + ", ".join(missing))
    checkpoint = ET.parse(empty_world / "Sandbox.sbc").getroot()
    check_no_economy_history(checkpoint)
    sector = ET.parse(empty_world / "SANDBOX_0_0_0_.sbs").getroot()
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    planets = [node for node in sector.findall(".//SectorObjects/*")
               if "Planet" in (node.get("{%s}type" % xsi) or "")]
    if planets:
        raise RuntimeError("Stock Empty World contains planet entities")


def load_inputs():
    plan = json.loads((OUT / "pack-plan.json").read_text(encoding="utf-8"))
    voxel = json.loads((OUT / "selected-voxel-audit.json").read_text(encoding="utf-8"))
    coverage = json.loads((OUT / "coverage.json").read_text(encoding="utf-8"))
    workshop = plan["selected_workshop"]
    ids = [item["id"] for item in workshop]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Selected Workshop list contains duplicates")
    if not REQUIRED_SPEED_MODS.issubset(ids):
        raise RuntimeError("Selected Workshop list is missing a required speed/orbit mod")
    if DENIED_SPEED_MODS.intersection(ids):
        raise RuntimeError("A Midspace fixed-speed mod is selected")
    if voxel["total"] > 120:
        raise RuntimeError("Voxel material count exceeds Phase A budget: %s" % voxel["total"])
    selected = [entry for entry in coverage if entry["selected"]]
    bad_proxy = [entry["planet"] for entry in selected if entry["active_proxy_count"] != 1]
    if bad_proxy:
        raise RuntimeError("Selected planets without exactly one active proxy: " + ", ".join(bad_proxy))
    if len(selected) != 18:
        raise RuntimeError("Expected 18 selected planets; found %s" % len(selected))
    return workshop, voxel["total"], len(selected)


def build(game_root, output):
    game_root = game_root.resolve()
    empty_world = game_root / "Content" / "CustomWorlds" / "Empty World"
    validate_source(empty_world)
    workshop, voxel_total, selected_count = load_inputs()
    if output.exists():
        raise RuntimeError("Output already exists: " + str(output))
    output.mkdir(parents=True)
    before = tree_hash(empty_world)
    for name in ROOT_FILES:
        shutil.copy2(empty_world / name, output / name)

    drag_xml = (ROOT / "profiles" / "AerodynamicPhysics.dragsettings.xml").read_text(encoding="utf-8")
    drag = ET.fromstring(drag_xml)
    expected_drag = {
        "SmallShipMaxSpeed": "1500",
        "LargeShipMaxSpeed": "1500",
        "SimulationMaxSpeed": "400",
    }
    for name, expected in expected_drag.items():
        if drag.findtext(name) != expected:
            raise RuntimeError("Locked Aero profile mismatch: %s" % name)

    for name in ("Sandbox.sbc", "Sandbox_config.sbc"):
        path = output / name
        tree = ET.parse(path)
        root = tree.getroot()
        set_text(root, "SessionName", TEMPLATE_NAME)
        set_text(root, "Description", "One-shot generated Random Sector campaign")
        settings = root.find("Settings")
        if settings is None:
            raise RuntimeError("Template has no Settings: " + name)
        set_text(settings, "GameMode", "Survival")
        set_text(settings, "OnlineMode", "OFFLINE")
        set_text(settings, "ScenarioEditMode", "false")
        set_pre_activation_settings(tree)
        set_mods(tree, workshop, LOCAL_MODS)
        if name == "Sandbox.sbc":
            dictionary = root.find("./ScriptManagerData/variables/dictionary")
            if dictionary is None:
                raise RuntimeError("Template checkpoint has no variable dictionary")
            dictionary.clear()
            put_variable(tree, RSG_KEY, TEMPLATE_ARM_VALUE)
            put_variable(tree, DRAG_KEY, drag_xml)
        write_atomic(tree, path)

    after = tree_hash(empty_world)
    if before != after:
        raise RuntimeError("Stock Empty World changed while building Random Sector")
    result = validate(output)
    result.update({
        "source": str(empty_world),
        "source_hash": before,
        "selected_planets": selected_count,
        "voxel_materials": voxel_total,
    })
    return result


def validate(template):
    template = template.resolve()
    missing = [name for name in ROOT_FILES if not (template / name).is_file()]
    if missing:
        raise RuntimeError("Random Sector is missing files: " + ", ".join(missing))
    if (template / "Storage").exists() or (template / "Backup").exists():
        raise RuntimeError("Reusable Random Sector must not contain Storage or Backup")
    workshop, voxel_total, selected_count = load_inputs()
    expected_ids = [item["id"] for item in workshop]
    for name in ("Sandbox.sbc", "Sandbox_config.sbc"):
        tree = ET.parse(template / name)
        root = tree.getroot()
        if root.findtext("SessionName") != TEMPLATE_NAME:
            raise RuntimeError("Wrong SessionName in " + name)
        settings = root.find("Settings")
        for key, value in PRE_ACTIVATION_SETTINGS.items():
            if settings.findtext(key) != value:
                raise RuntimeError("Unsafe %s in %s" % (key, name))
        if settings.findtext("GameMode") != "Survival":
            raise RuntimeError("Random Sector is not configured for Survival")
        actual_ids = [node.findtext("PublishedFileId") for node in root.findall("./Mods/ModItem")
                      if node.find("PublishedFileId") is not None]
        if actual_ids != expected_ids:
            raise RuntimeError("Workshop mod list mismatch in " + name)
        actual_local = [node.findtext("Name") for node in root.findall("./Mods/ModItem")
                        if node.find("PublishedFileId") is None]
        if actual_local != list(LOCAL_MODS):
            raise RuntimeError("Local mod list mismatch in " + name)
    checkpoint = ET.parse(template / "Sandbox.sbc")
    check_no_economy_history(checkpoint.getroot())
    if get_variable(checkpoint, RSG_KEY) != TEMPLATE_ARM_VALUE:
        raise RuntimeError("Random Sector does not contain the template bootstrap marker")
    if get_variable(checkpoint, RSS_KEY) is not None:
        raise RuntimeError("Random Sector contains an RSS campaign payload")
    drag_xml = get_variable(checkpoint, DRAG_KEY)
    drag = ET.fromstring(drag_xml or "")
    if (drag.findtext("SmallShipMaxSpeed"), drag.findtext("LargeShipMaxSpeed"),
            drag.findtext("SimulationMaxSpeed")) != ("1500", "1500", "400"):
        raise RuntimeError("Random Sector Aero profile is not locked to 1500/1500/400")
    sector = ET.parse(template / "SANDBOX_0_0_0_.sbs").getroot()
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    if any("Planet" in (node.get("{%s}type" % xsi) or "")
           for node in sector.findall(".//SectorObjects/*")):
        raise RuntimeError("Random Sector source contains generated planets")
    if list(template.rglob("RandomSectorGenerator.State.xml")):
        raise RuntimeError("Random Sector source contains RSG state")
    return {
        "template": str(template),
        "template_hash": tree_hash(template),
        "workshop_mods": len(expected_ids),
        "local_mods": list(LOCAL_MODS),
        "selected_planets": selected_count,
        "voxel_materials": voxel_total,
        "proxy_coverage": "%s/%s" % (selected_count, selected_count),
        "economy": "off",
        "armed": True,
        "rss_payload": False,
        "storage": False,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--game-root", required=True, type=Path)
    b.add_argument("--output", required=True, type=Path)
    v = sub.add_parser("validate")
    v.add_argument("template", type=Path)
    args = parser.parse_args()
    result = build(args.game_root, args.output) if args.command == "build" else validate(args.template)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
