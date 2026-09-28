"""Prepare and configure an isolated Planet Exporter workbench world.

This keeps proxy creation separate from the campaign save. The workbench loads
Planet Exporter plus the selected export targets, including Terminus, and the local
ProxyExportBootstrap.
"""
import argparse
import datetime
import json
import os
import re
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
WORKSHOP_IDS = ["3350589349", "2200451495", "3695766186", "3489648084", "3481843850"] + list(
    json.loads((ROOT / "campaign-planets.json").read_text(encoding="utf-8"))["additional_workshop"]
)
LOCAL_MOD = "ProxyExportBootstrap"
SPECIAL_EXPORT_TARGETS = ["Terminus (Black Hole)"]


def export_targets():
    coverage = json.loads((REPORTS / "coverage.json").read_text(encoding="utf-8"))
    targets = [row["planet"] for row in coverage
               if row["selected"] and row["active_proxy_count"] == 0]
    for name in SPECIAL_EXPORT_TARGETS:
        if name not in targets:
            targets.append(name)
    return targets

# Base colors approximate the installed CM textures sampled at 64x64. Glow is
# authored for hot/lava materials because the exporter uses a single scalar per
# voxel subtype; it cannot derive a spatial emissive map from the source DDS.
VOXELS = {
    "Zenit_Grass": ((0.23, 0.36, 0.26), 0.05, 0.00),
    "Zenit_OCSand": ((0.70, 0.44, 0.20), 0.03, 0.00),
    "ZenitLavaGravel": ((0.12, 0.12, 0.13), 0.05, 0.08),
    "ZenitHotRock": ((0.07, 0.06, 0.06), 0.08, 0.18),
    "ZenitLavaRockOC": ((0.10, 0.09, 0.09), 0.10, 0.65),
    "ZenitLavaRockSurface": ((0.18, 0.09, 0.05), 0.10, 0.85),
    "RelBasalt": ((0.15, 0.15, 0.15), 0.06, 0.00),
    "RelBedrock": ((0.16, 0.16, 0.16), 0.04, 0.00),
    "RelMagma": ((0.75, 0.21, 0.06), 0.12, 1.00),
    "RelRock": ((0.15, 0.15, 0.15), 0.05, 0.00),
    "Terminus": ((0.003, 0.003, 0.003), 0.00, 0.00),
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


def save_profile_root() -> Path:
    """Choose the active Space Engineers save-profile directory from audited saves."""
    worlds = inventory()["worlds"]
    parents = {}
    for world in worlds:
        parent = Path(world["file"]).parent.parent.resolve()
        if SAVE_ROOT.resolve() not in parent.parents and parent != SAVE_ROOT.resolve():
            continue
        checkpoint = Path(world["file"])
        try:
            modified = checkpoint.stat().st_mtime
        except OSError:
            modified = 0
        count, newest = parents.get(parent, (0, 0))
        parents[parent] = (count + 1, max(newest, modified))

    if parents:
        return max(parents, key=lambda p: (parents[p][0], parents[p][1]))

    candidates = [p.resolve() for p in SAVE_ROOT.iterdir() if p.is_dir()] if SAVE_ROOT.is_dir() else []
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(
        "Could not determine the active Space Engineers save profile. "
        "Create or save any world once, rerun scripts\\audit.py, and retry."
    )


def source_world() -> Path:
    """Use an audited Empty World save when present, otherwise the stock game template."""
    worlds = inventory()["worlds"]
    candidates = [
        Path(w["file"]).parent
        for w in worlds
        if w["name"].startswith("Empty World")
    ]
    if candidates:
        return candidates[0]

    games = inventory().get("games") or []
    for game in games:
        candidate = Path(game["path"]) / "Content" / "CustomWorlds" / "Empty World"
        if (candidate / "Sandbox.sbc").is_file() and (candidate / "Sandbox_config.sbc").is_file():
            return candidate

    raise RuntimeError("Could not find the installed stock Empty World template.")


def existing_workbench() -> Path:
    """Locate the existing proxy workbench directly by its saved SessionName."""
    candidates = []
    if SAVE_ROOT.is_dir():
        for checkpoint in SAVE_ROOT.rglob("Sandbox.sbc"):
            if "Backup" in checkpoint.parts:
                continue
            try:
                if ET.parse(checkpoint).findtext("SessionName") == WORLD_NAME:
                    candidates.append(checkpoint.parent.resolve())
            except (ET.ParseError, OSError):
                continue

    unique = sorted(set(candidates), key=lambda p: str(p).lower())
    if not unique:
        raise RuntimeError(
            f"Existing proxy workbench {WORLD_NAME!r} was not found under {SAVE_ROOT}. "
            "If it was deleted, recreate it with the prepare command."
        )
    if len(unique) != 1:
        raise RuntimeError(
            "Multiple proxy workbenches have the same SessionName:\n  " +
            "\n  ".join(str(path) for path in unique)
        )

    world = unique[0]
    if SAVE_ROOT.resolve() not in world.parents:
        raise RuntimeError("Proxy workbench resolved outside the Space Engineers save root.")
    return world


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
    # After a successful launch Space Engineers adds this installed dependency
    # and writes PublishedServiceName=Steam on the local helper entry.
    loaded_dependency = ("758597413.sbm", "758597413", "Steam")
    for file in save_files(world):
        validate_xml_types(file)
        root = ET.parse(file).getroot()
        actual = [(m.findtext("Name"), m.findtext("PublishedFileId"),
                   m.findtext("PublishedServiceName", "")) for m in root.findall("./Mods/ModItem")]
        tail = actual[len(expected):]
        helpers = [entry for entry in tail if entry[0:2] == (LOCAL_MOD, None)
                   and entry[2] in ("", "Steam")]
        dependencies = [entry for entry in tail if entry == loaded_dependency]
        if (actual[:len(expected)] != expected or len(helpers) != 1 or
                len(dependencies) not in (0, 1) or len(tail) != len(helpers) + len(dependencies)):
            raise RuntimeError(f"{file.name}: unexpected workbench mod list: {actual}")
        if root.findtext("./Settings/GameMode") != "Creative":
            raise RuntimeError(f"{file.name}: workbench must be Creative")
    if ET.parse(world / "Sandbox.sbc").findtext("SessionName") != WORLD_NAME:
        raise RuntimeError("Unexpected workbench session name")
    sectors = list(world.glob("SANDBOX_*.sbs"))
    if len(sectors) != 1:
        raise RuntimeError("Expected exactly one workbench sector")
    validate_xml_types(sectors[0])
    for wid in WORKSHOP_IDS + ["758597413"]:
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
    world = existing_workbench()
    if SAVE_ROOT.resolve() not in world.parents or not world.is_dir():
        raise RuntimeError("Workbench save is missing or outside the save root")
    backup = archive(world, "ProxyExportWorkbench-before-namespace-repair")
    for file in save_files(world):
        write_atomic(ET.parse(file), file)
    result = validate_world(world)
    result["backup"] = str(backup)
    print(json.dumps(result, indent=2))


def sync():
    """Expand an existing workbench, or create it when it does not exist yet."""
    ensure_closed()
    try:
        world = existing_workbench()
    except RuntimeError as exc:
        if "was not found" not in str(exc):
            raise
        prepare(False)
        return
    if SAVE_ROOT.resolve() not in world.parents or not world.is_dir():
        raise RuntimeError("Expected an existing isolated proxy workbench")
    for f in save_files(world):
        validate_xml_types(f)
    mods = workshop_map()
    missing = [wid for wid in WORKSHOP_IDS if wid not in mods or not Path(mods[wid]["path"]).is_dir()]
    if missing:
        raise RuntimeError("Missing workbench Workshop mod(s): " + ", ".join(missing))
    backup = archive(world, "ProxyExportWorkbench-before-pool-sync")
    install_bootstrap()
    for file in save_files(world):
        tree = ET.parse(file)
        node = tree.getroot().find("Mods")
        if node is None:
            raise RuntimeError(f"{file.name}: missing Mods node")
        node.clear()
        for wid in WORKSHOP_IDS + ["758597413"]:
            item = ET.SubElement(node, "ModItem")
            title = mods[wid].get("title")
            if title:
                item.set("FriendlyName", title)
            ET.SubElement(item, "Name").text = wid + ".sbm"
            ET.SubElement(item, "PublishedFileId").text = wid
            ET.SubElement(item, "PublishedServiceName").text = "Steam"
        item = ET.SubElement(node, "ModItem")
        ET.SubElement(item, "Name").text = LOCAL_MOD
        write_atomic(tree, file)
    print(json.dumps({"workbench": str(world), "backup": str(backup),
                      "helper": str(MOD_ROOT / LOCAL_MOD), "mods": WORKSHOP_IDS,
                      "export_targets": export_targets()}, indent=2))


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

    if SAVE_ROOT.resolve() in src.parents:
        dest = src.parent / WORLD_NAME
    else:
        dest = save_profile_root() / WORLD_NAME
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
        "next": "Load this world once, wait for all export targets to spawn, SAVE, then EXIT.",
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


def parse_exporter_config(config: Path) -> ET.ElementTree:
    """Handle exporter files whose UTF-16 declaration disagrees with UTF-8 bytes."""
    raw = config.read_bytes()
    try:
        return ET.ElementTree(ET.fromstring(raw))
    except ET.ParseError as original_error:
        # Only recover an ASCII-compatible XML stream that falsely claims UTF-16/32.
        # Real UTF-16 (with or without a BOM) is handled by the normal parser.
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:128]:
            raise
        ascii_bytes = raw.removeprefix(b"\xef\xbb\xbf")
        declaration = re.match(br"<\?xml\s+[^?]*\?>", ascii_bytes)
        if not declaration or not re.search(br"encoding\s*=\s*['\"]utf-(?:16|32)['\"]", declaration.group(), re.I):
            raise
        try:
            ascii_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise original_error
        corrected = re.sub(br"(encoding\s*=\s*['\"])utf-(?:16|32)(['\"])",
                           br"\g<1>utf-8\2", declaration.group(), flags=re.I)
        return ET.ElementTree(ET.fromstring(corrected + ascii_bytes[declaration.end():]))


def require_exporter_schema(root):
    if root.tag != "PlanetUnwrapperSettingsConfig":
        raise RuntimeError("Unexpected Planet Exporter config root: " + root.tag)
    for name in ("SamplingWidth", "SamplingHeight", "ScaleReductionTexCM",
                 "ScaleReductionTexNG", "ScaleReductionTexADD", "ModdedVoxelInfoList"):
        if len(root.findall(name)) != 1:
            raise RuntimeError("Expected exactly one Planet Exporter field: " + name)
    voxel_list = root.find("ModdedVoxelInfoList")
    if any(entry.tag != "VoxelInfo" or entry.find("VoxelName") is None or
           entry.find("VoxelColor") is None or entry.find("VoxelGloss") is None or
           entry.find("VoxelAdditive") is None for entry in voxel_list):
        raise RuntimeError("Unexpected Planet Exporter VoxelInfo schema")
    return voxel_list


def configure_file(config: Path):
    raw = config.read_bytes()
    tree = parse_exporter_config(config)
    root = tree.getroot()
    voxel_list = require_exporter_schema(root)

    # SD settings recommended by the exporter author.
    set_existing(root, ["SamplingWidth"], 4096)
    set_existing(root, ["SamplingHeight"], 2048)
    set_existing(root, ["ScaleReductionTexCM"], 1)
    set_existing(root, ["ScaleReductionTexNG"], 2)
    set_existing(root, ["ScaleReductionTexADD"], 2)

    existing = {child.findtext("VoxelName"): child for child in voxel_list}
    if len(existing) != len(voxel_list):
        raise RuntimeError("Duplicate names in Planet Exporter ModdedVoxelInfoList")
    for name, (rgb, gloss, additive) in VOXELS.items():
        entry = existing.get(name)
        if entry is None:
            entry = ET.SubElement(voxel_list, "VoxelInfo")
            ET.SubElement(entry, "VoxelName").text = name
            ET.SubElement(entry, "VoxelColor")
            ET.SubElement(entry, "VoxelGloss")
            ET.SubElement(entry, "VoxelAdditive")
        entry.find("VoxelColor").attrib.update({
            "X": f"{rgb[0]:.4f}", "Y": f"{rgb[1]:.4f}", "Z": f"{rgb[2]:.4f}",
        })
        entry.find("VoxelGloss").text = f"{gloss:.4f}"
        entry.find("VoxelAdditive").text = f"{additive:.4f}"

    # The exporter normally includes these namespace declarations on its root.
    # ElementTree otherwise drops declarations used only in attribute values.
    for prefix in ("xsd", "xsi"):
        match = re.search(rb"\bxmlns:" + prefix.encode() + rb"\s*=\s*(['\"])(.*?)\1", raw[:512])
        if match:
            uri = match.group(2).decode("ascii")
            if not any("{" + uri + "}" in e.tag or any("{" + uri + "}" in k for k in e.attrib)
                       for e in root.iter()):
                root.set("xmlns:" + prefix, uri)
    ET.indent(tree)
    temp = config.with_suffix(".xml.rsg-tmp")
    try:
        tree.write(temp, encoding="utf-8", xml_declaration=True)
        reparsed = ET.parse(temp)
        require_exporter_schema(reparsed.getroot())
        if not temp.read_bytes().startswith(b"<?xml version='1.0' encoding='utf-8'?>"):
            raise RuntimeError("Rewritten exporter config has a mismatched encoding declaration")
        os.replace(temp, config)
    finally:
        temp.unlink(missing_ok=True)


def configure():
    ensure_closed()
    world = existing_workbench()
    if not world.is_dir():
        raise RuntimeError("Proxy export workbench does not exist. Run prepare first.")

    config = exporter_config(world)
    backup = archive(config.parent, "PlanetExporter-config-before-campaign-patch")
    configure_file(config)

    print(json.dumps({
        "config": str(config),
        "backup": str(backup),
        "sampling": "4096x2048 SD",
        "configured_voxels": sorted(VOXELS),
        "next": [f"Reload {WORLD_NAME}", "/ReloadConfig", "/pex status"] + [
            command for name in export_targets()
            for command in ("/pex " + name, "/ExportCM", "/ExportNG", "/ExportADD")
        ] + ["SAVE and EXIT", "py scripts\\build_exported_proxies.py build"],
    }, indent=2))


def status():
    try:
        world = existing_workbench()
    except RuntimeError as exc:
        print(json.dumps({
            "world_exists": False,
            "world": None,
            "bootstrap_installed": (MOD_ROOT / LOCAL_MOD).is_dir(),
            "export_targets": export_targets(),
            "world_status": str(exc),
        }, indent=2))
        return

    result = {
        "world_exists": True,
        "world": str(world),
        "bootstrap_installed": (MOD_ROOT / LOCAL_MOD).is_dir(),
        "export_targets": export_targets(),
    }
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
    sub.add_parser("sync")
    args = p.parse_args()

    if args.command == "prepare":
        prepare(False)
    elif args.command == "reset":
        prepare(True)
    elif args.command == "configure":
        configure()
    elif args.command == "repair":
        repair()
    elif args.command == "sync":
        sync()
    elif args.command == "validate":
        print(json.dumps(validate_world(existing_workbench()), indent=2))
    else:
        status()


if __name__ == "__main__":
    main()
