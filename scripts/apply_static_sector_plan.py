"""Apply an RSG static-sector TSV to an RSS-adopted Space Engineers save.

The tool intentionally operates only on bodies RSS has already captured and
saved.  It never creates bodies, changes StorageName/PlanetGenerator identity,
or edits Workshop content.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


RSS_STORAGE = "3351055036.sbm_RealSolarSystems"
STARS_STORAGE = "3152436752.sbm_RealSun"
GIANTS_STORAGE = "3232085677.sbm_RealGasGiants"
PLAN_RELATIVE = Path("Storage/RandomSectorGenerator_RandomSectorGenerator/RandomSectorStaticPlan.tsv")
NUMERIC_SUFFIX = re.compile(r"\.\d+$")
XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)


@dataclass(frozen=True)
class PlanRow:
    role: str
    name: str
    planet_type: str
    storage_name: str
    parent: str
    semimajor_axis: str
    eccentricity: str
    pitch: str
    roll: str
    yaw: str
    orbital_period: str
    orbital_offset: str


def ensure_game_closed() -> None:
    if sys.platform != "win32":
        return
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SpaceEngineers.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "SpaceEngineers.exe" in result.stdout:
        raise RuntimeError("Space Engineers is running; exit it before inspecting or changing a save.")


def read_se_xml(path: Path) -> tuple[ET.Element, str]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:256]:
        text, encoding = raw.decode("utf-16"), "utf-16"
    else:
        text, encoding = raw.decode("utf-8-sig"), "utf-8"
    return ET.fromstring(XML_DECL_RE.sub("", text, count=1)), encoding


def xml_bytes(root: ET.Element, encoding: str) -> bytes:
    body = ET.tostring(root, encoding="unicode")
    declaration = '<?xml version="1.0" encoding="%s"?>\r\n' % encoding
    text = declaration + body.replace("\n", "\r\n")
    return text.encode("utf-16" if encoding == "utf-16" else "utf-8")


def parse_written_xml(payload: bytes) -> None:
    # ElementTree validates both the declaration and the actual encoded bytes.
    ET.fromstring(payload)


def load_plan(path: Path) -> list[PlanRow]:
    required = [
        "Role", "Name", "PlanetType", "StorageName", "Parent", "SemimajorAxisM",
        "Eccentricity", "Pitch", "Roll", "Yaw", "OrbitalPeriodS", "OrbitalPeriodOffset",
    ]
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != required:
            raise RuntimeError("Unexpected static-plan columns: " + repr(reader.fieldnames))
        rows = [PlanRow(*(row[name].strip() for name in required)) for row in reader]
    if not rows:
        raise RuntimeError("Static plan is empty.")
    names = [row.name for row in rows]
    identities = [row.storage_name for row in rows]
    if len(set(names)) != len(names):
        raise RuntimeError("Static plan contains duplicate generated names.")
    if len(set(identities)) != len(identities):
        raise RuntimeError("Static plan contains duplicate StorageName values.")
    roots = [row for row in rows if not row.parent]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one plan root; found {len(roots)}.")
    name_set = set(names)
    for row in rows:
        if row.parent and row.parent not in name_set:
            raise RuntimeError(f"Unknown parent {row.parent!r} for {row.name!r}.")
        if row.parent == row.name:
            raise RuntimeError(f"Body {row.name!r} cannot parent itself.")
        if row.parent:
            for value_name, value in (
                ("SemimajorAxisM", row.semimajor_axis), ("Eccentricity", row.eccentricity),
                ("Pitch", row.pitch), ("Roll", row.roll), ("Yaw", row.yaw),
                ("OrbitalPeriodS", row.orbital_period), ("OrbitalPeriodOffset", row.orbital_offset),
            ):
                try:
                    float(value)
                except ValueError as exc:
                    raise RuntimeError(f"Invalid {value_name} for {row.name}: {value!r}") from exc
    # Detect disconnected cycles before touching XML.
    by_name = {row.name: row for row in rows}
    root_name = roots[0].name
    for row in rows:
        seen = set()
        cursor = row
        while cursor.parent:
            if cursor.name in seen:
                raise RuntimeError(f"Plan hierarchy contains a cycle at {cursor.name!r}.")
            seen.add(cursor.name)
            cursor = by_name[cursor.parent]
        if cursor.name != root_name:
            raise RuntimeError(f"Body {row.name!r} does not lead to the sole root.")
    return rows


def unique_identity_match(expected: str, candidates: list[str], label: str) -> str:
    exact = [value for value in candidates if value == expected]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise RuntimeError(f"Ambiguous exact {label} match for {expected!r}.")
    suffixed = [
        value for value in candidates
        if value.startswith(expected) and NUMERIC_SUFFIX.fullmatch(value[len(expected):])
    ]
    if len(suffixed) != 1:
        raise RuntimeError(
            f"Expected one {label} match for {expected!r}; found {len(suffixed)} numeric-suffix matches."
        )
    return suffixed[0]


def direct_text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    return None if child is None else child.text


def rss_bodies(root: ET.Element) -> list[ET.Element]:
    solar_systems = root.find("SolarSystems")
    if solar_systems is None:
        raise RuntimeError("RSS Config.xml has no SolarSystems element.")
    bodies: list[ET.Element] = []

    def visit(body: ET.Element) -> None:
        bodies.append(body)
        sibling = body.find("./Sibling/CelestialBodyConfig")
        if sibling is not None:
            visit(sibling)
        for child in body.findall("./Children/CelestialBodyConfig"):
            visit(child)

    for system in solar_systems.findall("SolarSystemConfig"):
        body = system.find("./RootBody")
        if body is None:
            raise RuntimeError("RSS solar system has no RootBody.")
        visit(body)
    return bodies


def sector_bodies(root: ET.Element) -> list[ET.Element]:
    return [node for node in root.iter() if node.find("StorageName") is not None and node.find("PlanetGenerator") is not None]


def set_direct_text(node: ET.Element, tag: str, value: str) -> None:
    child = node.find(tag)
    if child is None:
        child = ET.SubElement(node, tag)
    child.text = value


def remove_direct(node: ET.Element, tag: str) -> None:
    child = node.find(tag)
    if child is not None:
        node.remove(child)


def insert_before(node: ET.Element, child: ET.Element, before_tags: tuple[str, ...]) -> None:
    children = list(node)
    index = next((i for i, item in enumerate(children) if item.tag in before_tags), len(children))
    node.insert(index, child)


def apply_orbit(body: ET.Element, row: PlanRow) -> None:
    remove_direct(body, "OrbitInfo")
    orbit = ET.Element("OrbitInfo")
    for tag, value in (
        ("SemimajorAxis", row.semimajor_axis), ("Eccentricity", row.eccentricity),
        ("Pitch", row.pitch), ("Roll", row.roll), ("Yaw", row.yaw),
        ("OrbitalPeriod", row.orbital_period), ("OrbitalPeriodOffset", row.orbital_offset),
    ):
        ET.SubElement(orbit, tag).text = value
    insert_before(body, orbit, ("ParticleInfoConfig", "FunctionalZoneInfoConfig", "SpecialInfoConfig", "SiblingWeight", "Sibling", "Children"))


def required_root_orbit_zone(rows: list[PlanRow]) -> float:
    """Return a root ORBIT-zone radius large enough to contain the whole planned sector.

    RSS uses nested orbit zones as coordinate frames. Keeping the fixed Terminus
    root's zone around every descendant means normal campaign space remains in
    Terminus's real-body frame instead of proxy space, while child bodies can
    still transition into their own nested zones.
    """
    by_parent: dict[str, list[PlanRow]] = {}
    root = next(row for row in rows if not row.parent)
    for row in rows:
        if row.parent:
            by_parent.setdefault(row.parent, []).append(row)

    def descendant_extent(name: str) -> float:
        maximum = 0.0
        for child in by_parent.get(name, []):
            semimajor = abs(float(child.semimajor_axis))
            eccentricity = max(0.0, float(child.eccentricity))
            child_extent = descendant_extent(child.name)
            maximum = max(maximum, semimajor * (1.0 + eccentricity) + child_extent)
        return maximum

    planned_extent = descendant_extent(root.name)
    # Ten percent provides room for body zones, terrain, and numerical drift.
    return max(5_000_000.0, planned_extent * 1.10)


def index_by_plan_identity(rows: list[PlanRow], nodes: list[ET.Element], identity_getter, label: str):
    identities = [identity_getter(node) for node in nodes]
    if any(not value for value in identities):
        raise RuntimeError(f"A {label} body is missing StorageName identity.")
    result = {}
    used = set()
    for row in rows:
        actual = unique_identity_match(row.storage_name, identities, label)
        matches = [node for node in nodes if identity_getter(node) == actual]
        if len(matches) != 1 or id(matches[0]) in used:
            raise RuntimeError(f"Ambiguous {label} node for {row.storage_name!r}.")
        result[row.storage_name] = (actual, matches[0])
        used.add(id(matches[0]))
    if len(used) != len(nodes):
        raise RuntimeError(f"{label} contains {len(nodes) - len(used)} unplanned celestial bodies; refusing to guess.")
    return result


def update_rss(root: ET.Element, rows: list[PlanRow]):
    bodies = rss_bodies(root)
    if len(bodies) != len(rows):
        raise RuntimeError(f"RSS saved {len(bodies)} bodies, but the plan contains {len(rows)}. Save after /AddStrayPlanets first.")
    indexed = index_by_plan_identity(rows, bodies, lambda n: n.get("BodyInstanceName"), "RSS")
    by_name = {row.name: row for row in rows}

    for row in rows:
        actual, body = indexed[row.storage_name]
        if direct_text(body, "PlanetTypeId") != row.planet_type:
            raise RuntimeError(
                f"PlanetType mismatch for {row.storage_name}: RSS={direct_text(body, 'PlanetTypeId')!r}, plan={row.planet_type!r}."
            )
        body.set("BodyInstanceName", actual)
        body.tag = "CelestialBodyConfig"
        set_direct_text(body, "Name", row.name)
        remove_direct(body, "Sibling")
        remove_direct(body, "Children")
        remove_direct(body, "OrbitInfo")

    for row in rows:
        _, body = indexed[row.storage_name]
        children = ET.Element("Children")
        child_rows = [candidate for candidate in rows if candidate.parent == row.name]
        for child_row in child_rows:
            _, child = indexed[child_row.storage_name]
            apply_orbit(child, child_row)
            children.append(child)
        insert_before(body, children, tuple())

    root_row = next(row for row in rows if not row.parent)
    _, root_body = indexed[root_row.storage_name]

    # Terminus is a fixed campaign root. Envelop the entire hierarchy in its
    # ORBIT zone so RSS keeps players in the real Terminus coordinate frame.
    # This avoids showing the parked real black hole beside a tiny proxy while
    # retaining normal nested RSS zones for every moving child body.
    root_orbit_zone = required_root_orbit_zone(rows)
    set_direct_text(root_body, "PlanetOrbitZoneRadius",
                    format(root_orbit_zone, ".9g"))

    solar_systems = root.find("SolarSystems")
    assert solar_systems is not None
    solar_systems.clear()
    system = ET.SubElement(solar_systems, "SolarSystemConfig")
    position = ET.SubElement(system, "Position")
    for axis in "XYZ":
        ET.SubElement(position, axis).text = "0"
    root_body.tag = "RootBody"
    system.append(root_body)
    set_direct_text(root, "OverrideFromConfig", "true")
    return indexed, by_name, root_orbit_zone


def update_sector(root: ET.Element, rows: list[PlanRow]):
    bodies = sector_bodies(root)
    if len(bodies) != len(rows):
        raise RuntimeError(f"Saved sector has {len(bodies)} planet entities, but the plan contains {len(rows)}.")
    indexed = index_by_plan_identity(rows, bodies, lambda n: direct_text(n, "StorageName"), "sector")
    for row in rows:
        actual, body = indexed[row.storage_name]
        generator = direct_text(body, "PlanetGenerator")
        if generator != row.planet_type:
            raise RuntimeError(
                f"PlanetGenerator mismatch for {row.storage_name}: sector={generator!r}, plan={row.planet_type!r}."
            )
        if direct_text(body, "StorageName") != actual:
            raise AssertionError("StorageName changed during matching")
        set_direct_text(body, "Name", row.name)
    return indexed


def update_named_config(root: ET.Element, rows: list[PlanRow], item_tag: str, identity_attr: str, name_tag: str, expected_types: set[str], label: str):
    selected = [row for row in rows if row.planet_type in expected_types]
    nodes = list(root.iter(item_tag))
    identities = [node.get(identity_attr) for node in nodes]
    for row in selected:
        actual = unique_identity_match(row.storage_name, identities, label)
        matches = [node for node in nodes if node.get(identity_attr) == actual]
        if len(matches) != 1:
            raise RuntimeError(f"Ambiguous {label} config for {row.storage_name!r}.")
        set_direct_text(matches[0], name_tag, row.name)
    set_direct_text(root, "OverrideFromConfig", "true")


def resolve_paths(save: Path, plan_arg: Path | None):
    save = save.expanduser().resolve()
    if not save.is_dir() or not (save / "Sandbox.sbc").is_file():
        raise RuntimeError("Not a complete Space Engineers save: " + str(save))
    plan = (plan_arg.expanduser().resolve() if plan_arg else save / PLAN_RELATIVE)
    if not plan.is_file():
        raise RuntimeError("Static plan not found; pass --plan explicitly: " + str(plan))
    sectors = list(save.glob("SANDBOX_*.sbs"))
    if len(sectors) != 1:
        raise RuntimeError(f"Expected one sector file; found {len(sectors)}.")
    paths = {
        "rss": save / "Storage" / RSS_STORAGE / "Config.xml",
        "stars": save / "Storage" / STARS_STORAGE / "Config.xml",
        "giants": save / "Storage" / GIANTS_STORAGE / "Config.xml",
        "sector": sectors[0],
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Required adopted-save files are missing: " + ", ".join(missing))
    return save, plan, paths


def archive_save(save: Path) -> Path:
    backup_dir = save.parent / "CodexBackups"
    backup_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{save.name}-before-static-sector-plan-{stamp}.zip"
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in save.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(save))
    return target


def atomic_replace_many(payloads: dict[Path, bytes]) -> None:
    staged: dict[Path, Path] = {}
    try:
        for path, payload in payloads.items():
            parse_written_xml(payload)
            fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".static-plan-tmp", dir=path.parent)
            os.close(fd)
            temp = Path(temp_name)
            temp.write_bytes(payload)
            parse_written_xml(temp.read_bytes())
            staged[path] = temp
        for path, temp in staged.items():
            os.replace(temp, path)
    finally:
        for temp in staged.values():
            if temp.exists():
                temp.unlink()


def execute(save_arg: Path, plan_arg: Path | None, dry_run: bool) -> dict:
    ensure_game_closed()
    save, plan_path, paths = resolve_paths(save_arg, plan_arg)
    rows = load_plan(plan_path)
    parsed = {key: read_se_xml(path) for key, path in paths.items()}
    rss_index, _, root_orbit_zone = update_rss(parsed["rss"][0], rows)
    sector_index = update_sector(parsed["sector"][0], rows)
    update_named_config(parsed["stars"][0], rows, "StarInfo", "StarName", "StarCustomName", {"RealStar"}, "Real Stars")
    # Real Stars also owns terrestrial day-cycle records.
    update_named_config(parsed["stars"][0], rows, "PlanetInfo", "PlanetName", "PlanetCustomName", {row.planet_type for row in rows if row.planet_type not in {"RealStar", "RealGasGiant"}}, "Real Stars planet")
    update_named_config(parsed["giants"][0], rows, "GasGiantConfigInfo", "PlanetName", "PlanetCustomName", {"RealGasGiant"}, "Real Gas Giants")

    report_rows = []
    for row in rows:
        rss_actual = rss_index[row.storage_name][0]
        sector_actual = sector_index[row.storage_name][0]
        if rss_actual != sector_actual:
            raise RuntimeError(f"RSS/sector identity mismatch for {row.storage_name}: {rss_actual!r} vs {sector_actual!r}.")
        report_rows.append({
            "storage_name": rss_actual,
            "generated_name": row.name,
            "parent": row.parent or "<ROOT>",
            "role": row.role,
        })

    payloads = {path: xml_bytes(parsed[key][0], parsed[key][1]) for key, path in paths.items()}
    backup = None
    if not dry_run:
        backup = archive_save(save)
        atomic_replace_many(payloads)
        # Full readback validation after replacement.
        verify = {key: read_se_xml(path)[0] for key, path in paths.items()}
        if direct_text(verify["rss"], "OverrideFromConfig") != "true":
            raise RuntimeError("RSS override readback failed; restore the complete save backup.")
        if len(rss_bodies(verify["rss"])) != len(rows) or len(sector_bodies(verify["sector"])) != len(rows):
            raise RuntimeError("Celestial body count changed during write; restore the complete save backup.")

    return {
        "save": str(save),
        "plan": str(plan_path),
        "dry_run": dry_run,
        "body_count": len(rows),
        "root_position": [0, 0, 0],
        "root_orbit_zone_m": root_orbit_zone,
        "backup": None if backup is None else str(backup),
        "mappings": report_rows,
        "next": "Load once, verify /TSE, save/exit, then run /SetupRealOrbits and save." if not dry_run else "No files changed.",
    }


def print_report(report: dict) -> None:
    print("Save:", report["save"])
    print("Plan:", report["plan"])
    print("Mode:", "DRY RUN" if report["dry_run"] else "APPLIED")
    print("Root logical position: 0,0,0")
    print("Root ORBIT zone: %.0f km" % (report["root_orbit_zone_m"] / 1000.0))
    print("StorageName -> generated name -> parent")
    for row in report["mappings"]:
        print(f"  {row['storage_name']} -> {row['generated_name']} -> {row['parent']}")
    if report["backup"]:
        print("Complete save backup:", report["backup"])
    print(report["next"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path, help="Already-adopted, saved Space Engineers world")
    parser.add_argument("--plan", type=Path, help="RandomSectorStaticPlan.tsv (defaults to the target save)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing")
    args = parser.parse_args()
    try:
        print_report(execute(args.save, args.plan, args.dry_run))
    except (OSError, RuntimeError, ValueError, ET.ParseError) as exc:
        raise SystemExit("ERROR: " + str(exc))


if __name__ == "__main__":
    main()
