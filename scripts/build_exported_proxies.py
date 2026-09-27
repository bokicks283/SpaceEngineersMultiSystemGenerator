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

PLANETS = {
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
}

XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("xsi", XSI)


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


def build_definition(available_add: set[str]) -> ET.ElementTree:
    root = ET.Element("Definitions")
    components = ET.SubElement(root, "EntityComponents")
    for planet, visual in PLANETS.items():
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
        lines += [
            f"AtmoColor: {visual['atmo_color']}",
            f"AtmoThickness: {visual['atmo_thickness']}",
            f"AtmoColorMult: {visual['atmo_mult']}",
            "AtmoInZoneMult: 1",
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
        row = {"planet": planet}
        for kind in ("cm", "ng", "add"):
            found = newest_export(planet, kind)
            row[kind] = str(found) if found else None
        if not row["cm"] or not row["ng"]:
            missing = True
        rows.append(row)
    print(json.dumps({"storage": str(STORAGE), "exports": rows}, indent=2))
    return 1 if missing else 0


def build(args) -> None:
    requested = args.planets
    unknown = [p for p in requested if p not in PLANETS]
    if unknown:
        raise RuntimeError("Unsupported proxy target(s): " + ", ".join(unknown))

    exports: dict[str, dict[str, Path | None]] = {}
    for planet in requested:
        exports[planet] = {kind: newest_export(planet, kind) for kind in ("cm", "ng", "add")}
        if not exports[planet]["cm"] or not exports[planet]["ng"]:
            raise RuntimeError(
                f"Missing Planet Exporter CM/NG output for {planet}. "
                f"Run /ExportCM and /ExportNG while {planet} is targeted."
            )

    texconv = find_texconv(args.texconv)
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
    for planet in requested:
        convert(texconv, exports[planet]["cm"], textures / f"PlanetProxy_{planet}_cm.dds", True)
        convert(texconv, exports[planet]["ng"], textures / f"PlanetProxy_{planet}_ng.dds", False)
        if exports[planet]["add"]:
            convert(texconv, exports[planet]["add"], textures / f"PlanetProxy_{planet}_add.dds", True)
            available_add.add(planet)

    # The campaign currently expects both definitions in one local proxy mod.
    missing_targets = set(PLANETS) - set(requested)
    if missing_targets:
        raise RuntimeError(
            "Build both campaign proxies together so the generated local mod is complete. Missing: "
            + ", ".join(sorted(missing_targets))
        )

    definition = build_definition(available_add)
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
        "texconv": str(texconv),
        "planets": requested,
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
    s.add_argument("--planets", nargs="+", choices=sorted(PLANETS), default=sorted(PLANETS))
    b = sub.add_parser("build")
    b.add_argument("--planets", nargs="+", choices=sorted(PLANETS), default=sorted(PLANETS))
    b.add_argument("--texconv")
    args = parser.parse_args()
    if args.command == "status":
        raise SystemExit(status(args.planets))
    build(args)


if __name__ == "__main__":
    main()
