"""Prepare and configure an isolated Planet Exporter workbench world.

This keeps proxy creation separate from the campaign save. The workbench loads only
Planet Exporter, Water Mod, Zenitaia, Relicta, and the local ProxyExportBootstrap.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from world_checkpoint import write_atomic

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SAVE_ROOT = Path(os.environ["APPDATA"]) / "SpaceEngineers" / "Saves"
MOD_ROOT = Path(os.environ["APPDATA"]) / "SpaceEngineers" / "Mods"
BACKUPS = ROOT / "backups"

WORLD_NAME = "Proxy Export Workbench 2026-09-27"
WORKSHOP_IDS = ["3350589349", "2200451495", "3695766186", "3489648084"]
LOCAL_MOD = "ProxyExportBootstrap"

VOXELS = {
    "Zenit_Grass": ((0.22, 0.48, 0.18), 0.05, 0.00),
    "Zenit_OCSand": ((0.68, 0.58, 0.42), 0.03, 0.00),
    "ZenitLavaGravel": ((0.24, 0.16, 0.12), 0.05, 0.05),
    "ZenitHotRock": ((0.15, 0.09, 0.07), 0.08, 0.18),
    "ZenitLavaRockOC": ((0.38, 0.12, 0.04), 0.10, 0.65),
    "ZenitLavaRockSurface": ((0.48, 0.16, 0.05), 0.10, 0.85),
    "RelBasalt": ((0.12, 0.13, 0.14), 0.06, 0.00),
    "RelBedrock": ((0.24, 0.22, 0.20), 0.04, 0.00),
    "RelMagma": ((0.95, 0.24, 0.03), 0.12, 1.00),
    "RelRock": ((0.19, 0.17, 0.16), 0.05, 0.00),
}

XSI = "http://www.w3.org/2001/XMLSchema-instance"


def ensure_closed():
    result = subprocess.check_output([
        "powershell.exe", "-NoProfile", "-Command",
        "(Get-Process -Name SpaceEngineers -ErrorAction SilentlyContinue | Measure-Object).Count",
    ], text=True).strip()
    if result != "0":
        raise RuntimeError("Exit Space Engineers before changing the proxy export workbench.")


def inventory():
    return json.loads((REPORTS / "inventory.json").read_text(encoding="utf-8"))


def workshop_map():
    return {m["id"]: m for m in inventory()["mods"]}


def source_world() -> Path:
    worlds = inventory()["worlds"]
    candidates = [
        Path(w["file"]).parent
        for w in worlds
        if w["name"].startswith("Empty World")
    ]
    if not candidates:
        raise RuntimeError("No audited Empty World source save was found.")
    return candidates[0]


def archive(path: Path, label: str) -> Path:
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUPS / f"{label}-{stamp}.zip"
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for file in path.rglob("*"):
            if file.is_file():
                z.write(file, file.relative_to(path))
    return target


def install_bootstrap():
    source = ROOT / "mods" / LOCAL_MOD
    if not source.is_dir():
        raise RuntimeError("ProxyExportBootstrap source is missing from the repository.")
    dest = MOD_ROOT / LOCAL_MOD
    MOD_ROOT.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        archive(dest, LOCAL_MOD + "-before-install")
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    return dest


def save_files(world: Path):
    return [world / "Sandbox.sbc", world / "Sandbox_config.sbc"]


def validate_xml_types(path: Path):
    """Check QName values too: a normal XML parse misses undeclared xsi:type prefixes."""
    scopes = [{}]
    pending = {}
    for event, value in ET.iterparse(path, events=("start-ns", "start", "end")):
        if event == "start-ns":
            prefix, uri = value
            pending[prefix] = uri
        elif event == "start":
            scope = dict(scopes[-1])
            scope.update(pending)
            pending.clear()
            scopes.append(scope)
            type_name = value.get(f"{{{XSI}}}type", "")
            if ":" in type_name:
                prefix = type_name.split(":", 1)[0]
                if prefix not in scope:
                    raise RuntimeError(f"{path.name}: undeclared xsi:type prefix: {type_name}")
                if prefix == "xsd" and scope[prefix] != "http://www.w3.org/2001/XMLSchema":
                    raise RuntimeError(f"{path.name}: incorrect xsd namespace")
        else:
            scopes.pop()


def validate_world(world: Path):
    expected = [(wid + ".sbm", wid, "Steam") for wid in WORKSHOP_IDS]
    expected.append((LOCAL_MOD, "0", ""))
    for file in save_files(world):
        validate_xml_types(file)
        root = ET.parse(file).getroot()
        actual = [(m.findtext("Name"), m.findtext("PublishedFileId", "0"),
                   m.findtext("PublishedServiceName", "")) for m in root.findall("./Mods/ModItem")]
        if actual != expected:
            raise RuntimeError(f"{file.name}: unexpected workbench mod list: {actual}")
        if root.findtext("./Settings/GameMode") != "Creative":
            raise RuntimeError(f"{file.name}: workbench must be Creative")
    if ET.parse(world / "Sandbox.sbc").findtext("SessionName") != WORLD_NAME:
        raise RuntimeError("Unexpected workbench session name")
    sectors = list(world.glob("SANDBOX_*.sbs"))
    if len(sectors) != 1:
        raise RuntimeError("Expected exactly one workbench sector")
    validate_xml_types(sectors[0])
    for wid in WORKSHOP_IDS:
        if not Path(workshop_map()[wid]["path"]).is_dir():
            raise RuntimeError("Missing Workshop mod: " + wid)
    if not list((MOD_ROOT / LOCAL_MOD / "Data" / "Scripts").rglob("*.cs")):
        raise RuntimeError("Installed ProxyExportBootstrap scripts are missing")
    return {"world": str(world), "static_validation": "passed",
            "checked": ["checkpoint/config XML and xsi:type namespaces", "sector XML",
                        "exact mod lists", "Creative mode", "installed mod paths"],
            "runtime_validation": "requires an in-game launch"}


def repair():
    """Repair saves written before the namespace-preserving writer was used."""
    ensure_closed()
    world = (source_world().parent / WORLD_NAME).resolve()
    if SAVE_ROOT.resolve() not in world.parents or not world.is_dir():
        raise RuntimeError("Workbench save is missing or outside the save root")
    backup = archive(world, "ProxyExportWorkbench-before-namespace-repair")
    for file in save_files(world):
        write_atomic(ET.parse(file), file)
    result = validate_world(world)
    result["backup"] = str(backup)
    print(json.dumps(result, indent=2))


def has_planet_entities(world: Path) -> bool:
    sectors = list(world.glob("SANDBOX_*.sbs"))
    if len(sectors) != 1:
        raise RuntimeError("Expected exactly one sector file in source world.")
    tree = ET.parse(sectors[0])
    return any(
        "Planet" in (e.get(f"{{{XSI}}}type") or "")
        for e in tree.findall(".//SectorObjects/*")
    )


def prepare(reset: bool):
    ensure_closed()
    mods = workshop_map()
    missing = [i for i in WORKSHOP_IDS if i not in mods or not Path(mods[i]["path"]).is_dir()]
    if missing:
        raise RuntimeError("Missing required Workshop item(s): " + ", ".join(missing))

    src = source_world().resolve()
    if has_planet_entities(src):
        raise RuntimeError("Audited Empty World source unexpectedly contains planets.")

    dest = src.parent / WORLD_NAME
    if dest.exists():
        if not reset:
            raise RuntimeError(
                f"{dest} already exists. Use 'reset' to archive and recreate it."
            )
        backup = archive(dest, "ProxyExportWorkbench-before-reset")
        shutil.rmtree(dest)
    else:
        backup = None

    install_bootstrap()
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("Backup", "Storage"))

    for file in save_files(dest):
        tree = ET.parse(file)
        root = tree.getroot()
        session = root.find("SessionName")
        if session is not None:
            session.text = WORLD_NAME

        mods_node = root.find("Mods")
        if mods_node is None:
            raise RuntimeError(f"{file.name} is missing its Mods node.")
        mods_node.clear()

        for wid in WORKSHOP_IDS:
            item = ET.SubElement(mods_node, "ModItem")
            title = mods[wid].get("title")
            if title:
                item.set("FriendlyName", title)
            ET.SubElement(item, "Name").text = wid + ".sbm"
            ET.SubElement(item, "PublishedFileId").text = wid
            ET.SubElement(item, "PublishedServiceName").text = "Steam"

        local = ET.SubElement(mods_node, "ModItem")
        ET.SubElement(local, "Name").text = LOCAL_MOD

        # Ensure this isolated helper world is creative where the checkpoint exposes the setting.
        for game_mode in root.findall(".//GameMode"):
            game_mode.text = "Creative"

        # xsi:type="xsd:string" values need an explicit xmlns:xsd declaration.
        # ElementTree drops it unless the namespace-preserving writer restores it.
        write_atomic(tree, file)

    validate_world(dest)

    print(json.dumps({
        "world": str(dest),
        "source": str(src),
        "previous_backup": str(backup) if backup else None,
        "bootstrap": str(MOD_ROOT / LOCAL_MOD),
        "workshop_mods": WORKSHOP_IDS,
        "next": "Load this world once, wait for both planets to spawn, SAVE, then EXIT.",
    }, indent=2))


def exporter_config(world: Path) -> Path:
    matches = list((world / "Storage").rglob("Config.xml")) if (world / "Storage").exists() else []
    exact = [p for p in matches if "3350589349.sbm_PlanetUnwrapper" in str(p.parent)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise RuntimeError("Multiple Planet Exporter Config.xml files found.")
    raise RuntimeError(
        "Planet Exporter Config.xml not found. Load the workbench once, let the planets spawn, SAVE, and EXIT."
    )


def find_first(root, names):
    for name in names:
        node = root.find(".//" + name)
        if node is not None:
            return node
    return None


def set_existing(root, names, value):
    node = find_first(root, names)
    if node is None:
        raise RuntimeError("Exporter config is missing expected setting: " + "/".join(names))
    node.text = str(value)


def configure():
    ensure_closed()
    world = source_world().parent / WORLD_NAME
    if not world.is_dir():
        raise RuntimeError("Proxy export workbench does not exist. Run prepare first.")

    config = exporter_config(world)
    backup = archive(config.parent, "PlanetExporter-config-before-campaign-patch")
    tree = ET.parse(config)
    root = tree.getroot()

    # SD settings recommended by the exporter author.
    set_existing(root, ["SamplingWidth", "ExportWidth"], 4096)
    set_existing(root, ["SamplingHeight", "ExportHeight"], 2048)
    set_existing(root, ["ScaleReductionTexCM"], 1)
    set_existing(root, ["ScaleReductionTexNG"], 2)
    set_existing(root, ["ScaleReductionTexADD"], 2)

    voxel_list = root.find(".//ModdedVoxelInfoList")
    if voxel_list is None:
        raise RuntimeError("Exporter config has no ModdedVoxelInfoList.")

    for child in list(voxel_list):
        name = child.findtext("VoxelName")
        if name in VOXELS:
            voxel_list.remove(child)

    for name, (rgb, gloss, additive) in VOXELS.items():
        entry = ET.SubElement(voxel_list, "VoxelInfo")
        ET.SubElement(entry, "VoxelName").text = name
        ET.SubElement(entry, "VoxelColor", {
            "X": f"{rgb[0]:.4f}",
            "Y": f"{rgb[1]:.4f}",
            "Z": f"{rgb[2]:.4f}",
        })
        ET.SubElement(entry, "VoxelGloss").text = f"{gloss:.4f}"
        ET.SubElement(entry, "VoxelAdditive").text = f"{additive:.4f}"

    ET.indent(tree)
    temp = config.with_suffix(".xml.rsg-tmp")
    tree.write(temp, encoding="utf-8", xml_declaration=True)
    ET.parse(temp)
    os.replace(temp, config)

    print(json.dumps({
        "config": str(config),
        "backup": str(backup),
        "sampling": "4096x2048 SD",
        "configured_voxels": sorted(VOXELS),
        "next": [
            f"Reload {WORLD_NAME}",
            "/ReloadConfig",
            "/pex zenitaia",
            "/ExportCM",
            "/ExportNG",
            "/ExportADD",
            "/pex relicta",
            "/ExportCM",
            "/ExportNG",
            "/ExportADD",
            "SAVE and EXIT",
            "py scripts\\build_exported_proxies.py build",
        ],
    }, indent=2))


def status():
    world = source_world().parent / WORLD_NAME
    result = {
        "world_exists": world.is_dir(),
        "world": str(world),
        "bootstrap_installed": (MOD_ROOT / LOCAL_MOD).is_dir(),
    }
    if world.is_dir():
        try:
            cfg = exporter_config(world)
            result["exporter_config"] = str(cfg)
        except Exception as e:
            result["exporter_config"] = None
            result["config_status"] = str(e)
    print(json.dumps(result, indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("reset")
    sub.add_parser("configure")
    sub.add_parser("status")
    sub.add_parser("validate")
    sub.add_parser("repair")
    args = p.parse_args()

    if args.command == "prepare":
        prepare(False)
    elif args.command == "reset":
        prepare(True)
    elif args.command == "configure":
        configure()
    elif args.command == "repair":
        repair()
    elif args.command == "validate":
        print(json.dumps(validate_world(source_world().parent / WORLD_NAME), indent=2))
    else:
        status()


if __name__ == "__main__":
    main()
