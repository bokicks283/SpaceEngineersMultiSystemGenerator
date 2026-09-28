"""Build a local RSS proxy mod from Planet Exporter TGA output.

The only required in-game work is exporting CM/NG (and ADD when available) for the
selected planets. This script finds the newest exports, converts them to BC7 DDS
with mipmaps using texconv, writes RSS proxy definitions, and stages the complete
local mod under generated/CampaignPlanetProxies.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
GENERATED = ROOT / "generated" / "CampaignPlanetProxies"
BACKUPS = ROOT / "backups"
STORAGE = Path(os.environ["APPDATA"]) / "SpaceEngineers" / "Storage"

EXPORTED_PLANETS = {
    "Zenitaia": {
        "atmo_color": "(0.45,0.72,1.0,1.0)",
        "atmo_thickness": "1.0",
        "atmo_mult": "1.1",
        "icon": "(0.4,0.8,1.0,1.0)",
    },
    "Relicta": {
        "atmo_color": "(0.85,0.28,0.12,1.0)",
        "atmo_thickness": "0.98",
        "atmo_mult": "1.0",
        "icon": "(1.0,0.35,0.15,1.0)",
    },
    "Kerbin - Water Mod Ready": {
        "atmo_color": "(0.55,0.76,1.0,1.0)",
        "atmo_thickness": "1.0",
        "atmo_mult": "1.0",
        "icon": "(0.35,0.70,0.95,1.0)",
    },
    "Aulden": {
        "atmo_color": "(0.65,0.78,0.9,1.0)",
        "atmo_thickness": "1.0",
        "atmo_mult": "1.0",
        "icon": "(0.7,0.85,0.95,1.0)",
    },
    "Terminus (Black Hole)": {
        "atmo_color": None,
        "atmo_thickness": None,
        "atmo_mult": None,
        "icon": "(0.85,0.32,0.08,1.0)",
    },
    "Seren": {
        "atmo_color": "(0.55,0.35,0.8,1.0)",
        "atmo_thickness": "0.7",
        "atmo_mult": "1.0",
        "icon": "(0.55,0.55,0.9,1.0)",
    },
}
PACKAGED_PLANETS = {
    "Jormun": {
        "workshop_id": "3663505475",
        "atmo_color": "(0.62,0.80,1.0,1.0)",
        "atmo_thickness": "1.0",
        "atmo_mult": "1.0",
        "icon": "(0.45,0.75,1.0,1.0)",
    }
}
PLANETS = {**PACKAGED_PLANETS, **EXPORTED_PLANETS}
REQUIRED_SPECIAL_EXPORTS = ["Terminus (Black Hole)"]

XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("xsi", XSI)


def selected_targets() -> list[str]:
    coverage = json.loads((REPORTS / "coverage.json").read_text(encoding="utf-8"))
    plan = json.loads((REPORTS / "pack-plan.json").read_text(encoding="utf-8"))
    active_workshop = {m["id"] for m in plan["selected_workshop"]}
    # Local generated proxies are the output of this build, not a reason to
    # omit their source planets on the next build.
    exports = [c["planet"] for c in coverage if c["selected"] and
               not any(p["mod"] in active_workshop for p in c["proxy_candidates"]) and
               c["planet"] not in PACKAGED_PLANETS]
    unsupported = sorted(set(exports) - set(EXPORTED_PLANETS))
    if unsupported:
        raise RuntimeError("Selected proxy export has no visual profile: " + ", ".join(unsupported))
    return list(PACKAGED_PLANETS) + exports + [
        planet for planet in REQUIRED_SPECIAL_EXPORTS
        if planet not in PACKAGED_PLANETS and planet not in exports
    ]


def newest_export(planet: str, kind: str) -> Path | None:
    name = f"PlanetProxy_{planet}_{kind}.tga"
    matches = [p for p in STORAGE.rglob(name) if p.is_file()] if STORAGE.exists() else []
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def game_path() -> Path | None:
    inventory = REPORTS / "inventory.json"
    if not inventory.is_file():
        return None
    data = json.loads(inventory.read_text(encoding="utf-8"))
    games = data.get("games") or []
    return Path(games[0]["path"]) if games else None


def installed_mod_path(workshop_id: str) -> Path | None:
    inventory = REPORTS / "inventory.json"
    if not inventory.is_file():
        return None
    data = json.loads(inventory.read_text(encoding="utf-8"))
    for mod in data.get("mods") or []:
        if str(mod.get("id")) == str(workshop_id):
            path = Path(mod["path"])
            if path.is_dir():
                return path
    return None


def packaged_proxy_assets(planet: str) -> dict[str, Path | None]:
    info = PACKAGED_PLANETS[planet]
    root = installed_mod_path(info["workshop_id"])
    if root is None:
        return {"cm": None, "ng": None, "add": None}
    texture_root = root / "Textures" / "Planets"
    return {
        kind: next(iter(sorted(texture_root.glob(f"PlanetProxy_{planet}_{kind}.dds"))), None)
        for kind in ("cm", "ng", "add")
    }


def find_texconv(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("TEXCONV")
    if env:
        candidates.append(Path(env))
    on_path = shutil.which("texconv.exe") or shutil.which("texconv")
    if on_path:
        candidates.append(Path(on_path))

    game = game_path()
    if game and game.exists():
        candidates.extend([
            game / "texconv.exe",
            game / "Bin64" / "texconv.exe",
            game / "Tools" / "texconv.exe",
            game / "Tools" / "TextureConverter" / "texconv.exe",
        ])
        # Fallback search only inside the installed game, not the whole drive.
        candidates.extend(game.rglob("texconv.exe"))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "texconv.exe was not found. Set TEXCONV or pass --texconv with its full path."
    )


def convert(texconv: Path, source: Path, output: Path, srgb: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fmt = "BC7_UNORM_SRGB" if srgb else "BC7_UNORM"
    with tempfile.TemporaryDirectory(prefix="rsg-texconv-") as td:
        td_path = Path(td)
        cmd = [
            str(texconv), "-y", "-nologo", "-m", "0", "-f", fmt,
            "-o", str(td_path), str(source),
        ]
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(
                f"texconv failed for {source.name}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        produced = [p for p in td_path.iterdir() if p.suffix.lower() == ".dds"]
        if len(produced) != 1:
            raise RuntimeError(f"Expected one DDS from texconv for {source.name}; found {len(produced)}")
        shutil.copy2(produced[0], output)


def archive_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUPS / f"CampaignPlanetProxies-before-build-{stamp}.zip"
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for file in path.rglob("*"):
            if file.is_file():
                z.write(file, file.relative_to(path))
    return target


def build_definition(available_add: set[str], planets: list[str]) -> ET.ElementTree:
    root = ET.Element("Definitions")
    components = ET.SubElement(root, "EntityComponents")
    for planet in planets:
        visual = PLANETS[planet]
        component = ET.SubElement(
            components,
            "EntityComponent",
            {f"{{{XSI}}}type": "MyObjectBuilder_InventoryComponentDefinition"},
        )
        ident = ET.SubElement(component, "Id")
        ET.SubElement(ident, "TypeId").text = "Inventory"
        ET.SubElement(ident, "SubtypeId").text = "PlanetProxyType_" + planet
        lines = [
            f"PlanetTexture_cm: Textures\\Planets\\PlanetProxy_{planet}_cm.dds",
            f"PlanetTexture_ng: Textures\\Planets\\PlanetProxy_{planet}_ng.dds",
        ]
        if planet in available_add:
            lines.append(f"PlanetTexture_add: Textures\\Planets\\PlanetProxy_{planet}_add.dds")
        if visual["atmo_color"] is not None:
            lines += [
                f"AtmoColor: {visual['atmo_color']}",
                f"AtmoThickness: {visual['atmo_thickness']}",
                f"AtmoColorMult: {visual['atmo_mult']}",
                "AtmoInZoneMult: 1",
            ]
        lines += [
            "Scale: 0.99",
            "ScaleFadeMin: 0.7",
            f"EditorIconColor: {visual['icon']}",
        ]
        ET.SubElement(component, "Description").text = "\n\t\t\t" + "\n\t\t\t".join(lines) + "\n\t  "
    ET.indent(root)
    return ET.ElementTree(root)


def status(planets: list[str]) -> int:
    rows = []
    missing = False
    for planet in planets:
        row = {"planet": planet, "source": "workshop" if planet in PACKAGED_PLANETS else "exporter"}
        assets = packaged_proxy_assets(planet) if planet in PACKAGED_PLANETS else {
            kind: newest_export(planet, kind) for kind in ("cm", "ng", "add")
        }
        for kind, found in assets.items():
            row[kind] = str(found) if found else None
        if not row["cm"] or not row["ng"]:
            missing = True
        rows.append(row)
    print(json.dumps({"storage": str(STORAGE), "assets": rows}, indent=2))
    return 1 if missing else 0


def build(args) -> None:
    requested = args.planets
    unknown = [p for p in requested if p not in PLANETS]
    if unknown:
        raise RuntimeError("Unsupported proxy target(s): " + ", ".join(unknown))

    assets: dict[str, dict[str, Path | None]] = {}
    ready: list[str] = []
    missing: list[str] = []
    for planet in requested:
        if planet in PACKAGED_PLANETS:
            assets[planet] = packaged_proxy_assets(planet)
        else:
            assets[planet] = {kind: newest_export(planet, kind) for kind in ("cm", "ng", "add")}
        if assets[planet]["cm"] and assets[planet]["ng"]:
            ready.append(planet)
        else:
            missing.append(planet)

    if "Jormun" in requested and "Jormun" not in ready:
        raise RuntimeError(
            "The Jormun proxy Workshop item 3663505475 is missing its CM/NG DDS files locally."
        )
    if missing:
        raise RuntimeError("Incomplete proxy export batch: " + ", ".join(missing))

    needs_texconv = any(p in EXPORTED_PLANETS for p in ready)
    texconv = find_texconv(args.texconv) if needs_texconv else None
    parent = GENERATED.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / ".CampaignPlanetProxies.staging"
    if staging.exists():
        shutil.rmtree(staging)
    textures = staging / "Textures" / "Planets"
    data = staging / "Data"
    textures.mkdir(parents=True)
    data.mkdir(parents=True)

    available_add: set[str] = set()
    for planet in ready:
        if planet in PACKAGED_PLANETS:
            shutil.copy2(assets[planet]["cm"], textures / f"PlanetProxy_{planet}_cm.dds")
            shutil.copy2(assets[planet]["ng"], textures / f"PlanetProxy_{planet}_ng.dds")
            if assets[planet]["add"]:
                shutil.copy2(assets[planet]["add"], textures / f"PlanetProxy_{planet}_add.dds")
                available_add.add(planet)
        else:
            convert(texconv, assets[planet]["cm"], textures / f"PlanetProxy_{planet}_cm.dds", True)
            convert(texconv, assets[planet]["ng"], textures / f"PlanetProxy_{planet}_ng.dds", False)
            if assets[planet]["add"]:
                convert(texconv, assets[planet]["add"], textures / f"PlanetProxy_{planet}_add.dds", True)
                available_add.add(planet)

    definition = build_definition(available_add, ready)
    definition.write(data / "PlanetProxyDefaults.sbc", encoding="utf-8", xml_declaration=True)

    # Validate every texture referenced by the generated SBC before replacing the prior build.
    parsed = ET.parse(data / "PlanetProxyDefaults.sbc")
    for desc in parsed.findall(".//Description"):
        for line in (desc.text or "").splitlines():
            if line.strip().startswith("PlanetTexture_"):
                relative = line.split(":", 1)[1].strip().replace("\\", "/")
                if not (staging / relative).is_file():
                    raise RuntimeError("Generated proxy definition references a missing texture: " + relative)

    backup = archive_existing(GENERATED)
    if GENERATED.exists():
        shutil.rmtree(GENERATED)
    staging.replace(GENERATED)

    print(json.dumps({
        "built": str(GENERATED),
        "backup": str(backup) if backup else None,
        "texconv": str(texconv) if texconv else None,
        "planets": ready,
        "waiting_for_exports": missing,
        "additive_textures": sorted(available_add),
        "next": [
            "py scripts\\prepare_pack.py",
            "pwsh .\\Install-RandomSectorGenerator.ps1",
            "py scripts\\world_checkpoint.py sync <disposable-world>",
            "py scripts\\verify_local.py",
        ],
    }, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status")
    s.add_argument("--planets", nargs="+", choices=sorted(PLANETS), default=None)
    b = sub.add_parser("build")
    b.add_argument("--planets", nargs="+", choices=sorted(PLANETS), default=None)
    b.add_argument("--texconv")
    args = parser.parse_args()
    if args.planets is None:
        args.planets = selected_targets()
    if args.command == "status":
        raise SystemExit(status(args.planets))
    build(args)


if __name__ == "__main__":
    main()
