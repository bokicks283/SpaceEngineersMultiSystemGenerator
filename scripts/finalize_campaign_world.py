"""One-pass finalizer for the validated RSS campaign save."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from apply_campaign_speed_profile import (
    PROFILE,
    REMOTE_LIMIT,
    SPEED_LIMIT,
    read_mod_text,
    replace_tag,
    update_grid,
    write_atomic as write_mod_atomic,
)
from world_checkpoint import archive, ensure_closed, write_atomic as write_checkpoint

FSD_ID = "2640137506"
FINAL_WORKSHOP = [
    ("2667547195", "Bigger Explosions"),
    ("2649159807", "Kinetic Devastation"),
    ("2760086069", "HyperDrive"),
    ("2802482180", "Damaged Spawnships"),
    ("1608841667", "Daily Needs Survival Kit"),
    ("2747715235", "Populated Worlds Creatures"),
]
SURFACE_ZONE_RADIUS_MULT = 0.20


def scoped(world: Path, hint: str, name: str) -> Path:
    matches = [p for p in (world / "Storage").rglob(name) if hint in str(p.parent)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {hint}/{name}; found {len(matches)}")
    return matches[0]


def set_setting(root: ET.Element, name: str, value: str) -> None:
    settings = root.find("Settings")
    if settings is None:
        raise RuntimeError("World has no Settings section")
    node = settings.find(name)
    if node is None:
        node = ET.SubElement(settings, name)
    node.text = value


def finalize_mod_list(root: ET.Element) -> None:
    mods = root.find("Mods")
    if mods is None:
        raise RuntimeError("World has no Mods section")
    for item in list(mods.findall("ModItem")):
        if item.findtext("PublishedFileId") == FSD_ID:
            mods.remove(item)
    existing = {
        item.findtext("PublishedFileId")
        for item in mods.findall("ModItem")
        if item.find("PublishedFileId") is not None
    }
    children = list(mods)
    index = next((i for i, x in enumerate(children) if x.find("PublishedFileId") is None), len(children))
    for workshop_id, title in FINAL_WORKSHOP:
        if workshop_id in existing:
            continue
        item = ET.Element("ModItem", {"FriendlyName": title})
        ET.SubElement(item, "Name").text = workshop_id + ".sbm"
        ET.SubElement(item, "PublishedFileId").text = workshop_id
        ET.SubElement(item, "PublishedServiceName").text = "Steam"
        mods.insert(index, item)
        index += 1


def finalize_world_files(world: Path) -> None:
    for filename in ("Sandbox.sbc", "Sandbox_config.sbc"):
        path = world / filename
        tree = ET.parse(path)
        root = tree.getroot()
        finalize_mod_list(root)
        set_setting(root, "EnableEconomy", "true")
        set_setting(root, "FoodConsumptionRate", "0")
        # MES owns encounter traffic for this campaign.
        set_setting(root, "CargoShipsEnabled", "false")
        set_setting(root, "EnableEncounters", "false")
        set_setting(root, "EnablePlanetaryEncounters", "false")
        set_setting(root, "GlobalEncounterCap", "0")
        write_checkpoint(tree, path)


def tune_rts(world: Path) -> None:
    path = scoped(world, "1359618037", "RelativeTopSpeed.cfg")
    text, encoding = read_mod_text(path)
    text = replace_tag(text, "SpeedLimit", SPEED_LIMIT)
    text = replace_tag(text, "RemoteControlSpeedLimit", REMOTE_LIMIT)
    text = update_grid(text, "LargeGrid", PROFILE["LargeGrid"])
    text = update_grid(text, "SmallGrid", PROFILE["SmallGrid"])
    write_mod_atomic(path, text, encoding)


def tune_real_orbits(world: Path) -> None:
    path = scoped(world, "2609118808", "Config.xml")
    text, encoding = read_mod_text(path)
    text = replace_tag(text, "CharacterGravityMultiplier", 1)
    # /SetupRealOrbits has already written inverse-square (2.0) values to the
    # campaign bodies. Stop Real Orbits from flattening our deliberate star and
    # Terminus exceptions back to 2.0 on every load.
    text = replace_tag(text, "OverridePlanetGravityFalloff", "false")
    write_mod_atomic(path, text, encoding)


def tune_real_stars(world: Path) -> None:
    path = scoped(world, "3152436752", "Config.xml")
    text, encoding = read_mod_text(path)
    # Real Stars normally restores its binary checkpoint payload over Config.xml.
    # One-shot OverrideFromConfig imports these final values into that payload.
    text = replace_tag(text, "OverrideFromConfig", "true")
    text = replace_tag(text, "LensFlareOpacityMult", 2)
    text = replace_tag(text, "LensFlareSizeMult", 2)

    # Real Stars defaults these campaign stars to falloff 7. Lower them by one
    # for a somewhat longer stellar gravity reach without making them remotely
    # as broad as inverse-square planetary gravity.
    pattern = re.compile(
        r"(<StarInfo\b[^>]*>.*?<GravityFalloff>)([^<]+)(</GravityFalloff>.*?</StarInfo>)",
        re.I | re.S,
    )
    text, count = pattern.subn(r"\g<1>6\g<3>", text)
    if count != 7:
        raise RuntimeError(f"Expected 7 Real Stars entries; found {count}")
    write_mod_atomic(path, text, encoding)


def tune_real_gas_giants(world: Path) -> None:
    path = scoped(world, "3232085677", "Config.xml")
    text, encoding = read_mod_text(path)
    text = replace_tag(text, "OverrideFromConfig", "true")

    desired = {
        "Koreus Giant": "DefaultJupiter",
        "Saion Giant": "DefaultSaturn",
    }
    pattern = re.compile(r"(<GasGiantConfigInfo\b[^>]*>)(.*?)(</GasGiantConfigInfo>)", re.I | re.S)
    seen = set()

    def edit(match: re.Match) -> str:
        block = match.group(2)
        name_match = re.search(r"<PlanetCustomName>([^<]+)</PlanetCustomName>", block, re.I)
        if not name_match:
            return match.group(0)
        name = name_match.group(1)
        skin = desired.get(name)
        if skin is None:
            return match.group(0)

        skin_match = re.search(r"(<PlanetSkin>)([^<]+)(</PlanetSkin>)", block, re.I)
        if not skin_match:
            raise RuntimeError(f"{name} lacks PlanetSkin")
        block = block[:skin_match.start(2)] + skin + block[skin_match.end(2):]
        seen.add(name)
        return match.group(1) + block + match.group(3)

    text = pattern.sub(edit, text)
    missing = set(desired) - seen
    if missing:
        raise RuntimeError("Missing expected campaign gas giants: " + ", ".join(sorted(missing)))
    write_mod_atomic(path, text, encoding)


def tune_rss(world: Path) -> int:
    path = scoped(world, "3351055036", "Config.xml")
    text, encoding = read_mod_text(path)
    text = replace_tag(text, "OverrideFromConfig", "true")

    # RSS stores Terminus as a terrestrial-style body too, so the campaign has
    # 19 TerrestrialPlanetInfo records total: 18 normal worlds + Wyaris Abyss.
    # Protect the root record while applying ordinary planet surface-zone tuning.
    root_info_pattern = re.compile(
        r'(<RootBody\b[^>]*>.*?<Name>Wyaris Abyss</Name>.*?)(<TerrestrialPlanetInfo>.*?</TerrestrialPlanetInfo>)',
        re.I | re.S,
    )
    root_match = root_info_pattern.search(text)
    if root_match is None:
        raise RuntimeError("Could not locate Wyaris Abyss terrestrial info in RSS config")

    root_info = root_match.group(2)
    root_falloff = re.search(r"(<GravityFalloff>)([^<]+)(</GravityFalloff>)", root_info, re.I)
    if root_falloff is None:
        raise RuntimeError("Wyaris Abyss lacks GravityFalloff")
    root_info = (
        root_info[:root_falloff.start(2)] +
        "3.8" +
        root_info[root_falloff.end(2):]
    )

    root_token = "__RSG_TERMINUS_ROOT_INFO__"
    if root_token in text:
        raise RuntimeError("Unexpected Terminus placeholder collision")
    text = text[:root_match.start(2)] + root_token + text[root_match.end(2):]

    pattern = re.compile(r"(<TerrestrialPlanetInfo>)(.*?)(</TerrestrialPlanetInfo>)", re.I | re.S)
    count = 0

    def edit(match: re.Match) -> str:
        nonlocal count
        block = match.group(2)
        radius = re.search(r"<RadiusKm>([^<]+)</RadiusKm>", block, re.I)
        surface = re.search(r"(<PlanetSurfaceZoneRadius>)([^<]+)(</PlanetSurfaceZoneRadius>)", block, re.I)
        fade = re.search(r"(<PlanetProxyFadeoutHeightMult>)([^<]+)(</PlanetProxyFadeoutHeightMult>)", block, re.I)
        if not radius or not surface or not fade:
            raise RuntimeError("RSS terrestrial body lacks radius/surface/fade values")
        altitude = max(1000, int(round(float(radius.group(1)) * 1000 * SURFACE_ZONE_RADIUS_MULT)))
        block = block[:surface.start(2)] + str(altitude) + block[surface.end(2):]
        fade = re.search(r"(<PlanetProxyFadeoutHeightMult>)([^<]+)(</PlanetProxyFadeoutHeightMult>)", block, re.I)
        block = block[:fade.start(2)] + "0" + block[fade.end(2):]
        count += 1
        return match.group(1) + block + match.group(3)

    text = pattern.sub(edit, text)
    if count != 18:
        raise RuntimeError(f"Expected 18 normal terrestrial bodies plus Terminus; found {count} normal bodies")

    text = text.replace(root_token, root_info, 1)
    if text.count(root_token):
        raise RuntimeError("Terminus placeholder restoration failed")

    write_mod_atomic(path, text, encoding)
    return count


def damage_effect(parent, probability, minimum, maximum, type_id, prefab=None, subtype=None):
    node = ET.SubElement(parent, "DamageEffect")
    if prefab:
        ET.SubElement(node, "Prefab").text = prefab
    ET.SubElement(node, "Probability").text = str(probability)
    ET.SubElement(node, "MinimumDamage").text = str(minimum)
    ET.SubElement(node, "MaximumDamage").text = str(maximum)
    ET.SubElement(node, "TypeId").text = type_id
    if subtype:
        ET.SubElement(node, "SubtypeId").text = subtype


def damaged_defaults() -> ET.ElementTree:
    root = ET.Element("Configuration")
    ET.SubElement(root, "Version").text = "1.0.8.56"
    ET.SubElement(root, "Logging").text = "false"
    ET.SubElement(root, "ProtectAdminSpawnships").text = "false"
    ET.SubElement(root, "ProtectedPrefabs")
    protected = ET.SubElement(root, "ProtectedBlocks")
    for type_id in ("Parachute", "SurvivalKit", "Cockpit", "Beacon", "BatteryBlock"):
        block = ET.SubElement(protected, "Block")
        ET.SubElement(block, "TypeId").text = type_id
    ET.SubElement(root, "WipeProgrammableBlocks").text = "true"
    effects = ET.SubElement(root, "DamageDefinitions")
    damage_effect(effects, 1, .6, .9, "OxygenGenerator", "RespawnPlanetPod")
    damage_effect(effects, .45, .5, 1.25, "CubeBlock")
    damage_effect(effects, .5, .6, .9, "Thrust")
    damage_effect(effects, 1, .75, .98, "JumpDrive")
    for type_id in ("GravityGenerator", "GravityGeneratorSphere", "SpaceBall", "VirtualMass", "Refinery", "Assembler", "UpgradeModule"):
        damage_effect(effects, 1, .85, 1, type_id)
    damage_effect(effects, 1, .85, 1, "Gyro", subtype="LargeBlockGyro")
    ET.indent(root)
    return ET.ElementTree(root)


def tune_damaged_spawnships(world: Path) -> Path:
    path = world / "Storage" / "2802482180.sbm_DamagedSpawnships" / "DamagedSpawnshipsConfig.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = None
    if path.is_file():
        try:
            text, _ = read_mod_text(path)
            text = re.sub(r'encoding=["\']utf-16["\']', 'encoding="utf-8"', text, count=1, flags=re.I)
            root = ET.fromstring(text)
            if root.findtext("Version") == "1.0.8.56":
                node = root.find("ProtectAdminSpawnships")
                if node is None:
                    node = ET.SubElement(root, "ProtectAdminSpawnships")
                node.text = "false"
                protected = root.find("ProtectedBlocks")
                if protected is None:
                    protected = ET.SubElement(root, "ProtectedBlocks")
                if "BatteryBlock" not in {b.findtext("TypeId") for b in protected.findall("Block")}:
                    block = ET.SubElement(protected, "Block")
                    ET.SubElement(block, "TypeId").text = "BatteryBlock"
                tree = ET.ElementTree(root)
        except Exception:
            tree = None
    if tree is None:
        tree = damaged_defaults()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, path)
    return path


def create_travel_config(world: Path) -> Path:
    path = world / "Storage" / "RandomSectorGenerator_RandomSectorGenerator" / "CampaignTravelTuning.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    root = ET.Element("CampaignTravelTuningConfig")
    values = {
        "NormalJumpMaxDistanceM": "50000000",
        "NormalJumpMaxMassKg": "1250000",
        "NormalJumpRequiredPowerMW": "64",
        "NormalJumpStoredEnergyMWh": "1.2",
        "HyperDriveMaxDistanceM": "2500000000",
        "HyperDriveMaxMassKg": "25600000",
        "HyperDriveRequiredPowerMW": "250",
        "HyperDriveStoredEnergyMWh": "10",
    }
    for key, value in values.items():
        ET.SubElement(root, key).text = value
    ET.indent(root)
    tmp = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(root).write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, path)
    return path


def remove_fsd_storage(world: Path) -> None:
    for path in (world / "Storage").glob(FSD_ID + "*"):
        if path.is_dir():
            shutil.rmtree(path)


def validate(world: Path) -> None:
    for filename in ("Sandbox.sbc", "Sandbox_config.sbc"):
        root = ET.parse(world / filename).getroot()
        ids = [x.findtext("PublishedFileId") for x in root.findall("./Mods/ModItem") if x.find("PublishedFileId") is not None]
        if FSD_ID in ids:
            raise RuntimeError(f"{filename}: FSD is still active")
        for workshop_id, _ in FINAL_WORKSHOP:
            if ids.count(workshop_id) != 1:
                raise RuntimeError(f"{filename}: mod {workshop_id} count is {ids.count(workshop_id)}")
        if root.findtext("Settings/EnableEconomy") != "true" or root.findtext("Settings/FoodConsumptionRate") != "0":
            raise RuntimeError(f"{filename}: final world settings did not stick")
    rss, _ = read_mod_text(scoped(world, "3351055036", "Config.xml"))
    if rss.count("<TerrestrialPlanetInfo>") != 19 or "<OverrideFromConfig>true</OverrideFromConfig>" not in rss:
        raise RuntimeError("RSS finalization readback failed")
    if "<Name>Wyaris Abyss</Name>" not in rss or "<GravityFalloff>3.8</GravityFalloff>" not in rss:
        raise RuntimeError("Terminus gravity profile did not stick")

    stars, _ = read_mod_text(scoped(world, "3152436752", "Config.xml"))
    if len(re.findall(r"<StarInfo\b", stars, re.I)) != 7 or len(re.findall(r"<GravityFalloff>6</GravityFalloff>", stars, re.I)) != 7:
        raise RuntimeError("Real Stars gravity profile did not stick")

    orbits, _ = read_mod_text(scoped(world, "2609118808", "Config.xml"))
    if "<OverridePlanetGravityFalloff>false</OverridePlanetGravityFalloff>" not in orbits:
        raise RuntimeError("Real Orbits gravity override did not stick")

    giants, _ = read_mod_text(scoped(world, "3232085677", "Config.xml"))
    if "<OverrideFromConfig>true</OverrideFromConfig>" not in giants:
        raise RuntimeError("Real Gas Giants import override did not stick")
    for name, skin in (("Koreus Giant", "DefaultJupiter"), ("Saion Giant", "DefaultSaturn")):
        pattern = re.compile(
            r"<GasGiantConfigInfo\b[^>]*>.*?<PlanetCustomName>" + re.escape(name) +
            r"</PlanetCustomName>.*?<PlanetSkin>" + re.escape(skin) + r"</PlanetSkin>.*?</GasGiantConfigInfo>",
            re.I | re.S,
        )
        if not pattern.search(giants):
            raise RuntimeError(f"{name} gas giant skin did not stick")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ensure_closed()
    world = args.save.expanduser().resolve()
    if not world.is_dir() or not (world / "Sandbox.sbc").is_file():
        raise SystemExit("ERROR: incomplete Space Engineers save: " + str(world))
    rss, _ = read_mod_text(scoped(world, "3351055036", "Config.xml"))
    if rss.count("<TerrestrialPlanetInfo>") != 19:
        raise RuntimeError("This is not the validated campaign save (expected 18 normal worlds + Terminus)")
    if args.dry_run:
        # Structural preflight only; no files are changed.
        if "<Name>Wyaris Abyss</Name>" not in rss:
            raise RuntimeError("Wyaris Abyss root is missing from RSS config")
        stars, _ = read_mod_text(scoped(world, "3152436752", "Config.xml"))
        if len(re.findall(r"<StarInfo\\b", stars, re.I)) != 7:
            raise RuntimeError("Expected 7 campaign stars")
        giants, _ = read_mod_text(scoped(world, "3232085677", "Config.xml"))
        for name in ("Koreus Giant", "Saion Giant"):
            if name not in giants:
                raise RuntimeError(f"Expected campaign gas giant is missing: {name}")
        print("DRY RUN OK:", world)
        print("RSS terrestrial records: 19 (18 normal worlds + Terminus)")
        print("Campaign stars: 7")
        print("Campaign gas giants: Koreus Giant, Saion Giant")
        return

    backup = archive(world, "World-before-campaign-finalization")
    finalize_world_files(world)
    tune_rts(world)
    tune_real_orbits(world)
    tune_real_stars(world)
    tune_real_gas_giants(world)
    body_count = tune_rss(world)
    damaged = tune_damaged_spawnships(world)
    travel = create_travel_config(world)
    remove_fsd_storage(world)
    validate(world)
    print("Backup:", backup)
    print("RSS bodies tuned:", body_count)
    print("Damaged Spawnships config:", damaged.relative_to(world))
    print("Travel config:", travel.relative_to(world))
    print("Campaign finalization complete.")


if __name__ == "__main__":
    main()
