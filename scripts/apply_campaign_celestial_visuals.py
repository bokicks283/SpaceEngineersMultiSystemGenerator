"""Apply the campaign's final celestial-visual scale pass to an existing RSS save.

This is intentionally a visual-scale patch:
- doubles the four Real Stars physical radii/damage shells once
- enlarges the Real Gas Giants black-hole root to 450 km radius
- gives the black hole Real Gas Giants' built-in DefaultBlackHole ring as an
  accretion disk
- widens the black-hole RSS orbit zone so the reference-frame handoff happens
  outside the visible disk
- writes a versioned marker so star radii are never multiplied twice

The local RSG mod supplies distant point-star rendering and the distant-only
S-star cluster; this script only changes persisted celestial definitions.
"""
from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from apply_campaign_speed_profile import read_mod_text, replace_tag, write_atomic as write_mod_atomic
from world_checkpoint import archive, ensure_closed

PATCH_VERSION = "celestial-visuals-v1"
BLACK_HOLE_RADIUS_KM = 450.0
BLACK_HOLE_ORBIT_ZONE_M = 5_000_000.0
STAR_RADIUS_MULT = 2.0


def scoped(world: Path, hint: str, name: str) -> Path:
    matches = [p for p in (world / "Storage").rglob(name) if hint in str(p.parent)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {hint}/{name}; found {len(matches)}")
    return matches[0]


def parse_mod_xml(path: Path) -> tuple[ET.Element, str]:
    text, encoding = read_mod_text(path)
    normalized = re.sub(
        r'encoding=["\'](?:utf-16|utf-8)["\']',
        'encoding="utf-8"',
        text,
        count=1,
        flags=re.I,
    )
    return ET.fromstring(normalized), encoding


def write_tree(path: Path, root: ET.Element, encoding: str) -> None:
    ET.indent(root)
    xml = ET.tostring(root, encoding="unicode")
    payload = '<?xml version="1.0" encoding="utf-8"?>\n' + xml
    write_mod_atomic(path, payload, encoding)


def direct(node: ET.Element, tag: str) -> ET.Element:
    child = node.find(tag)
    if child is None:
        child = ET.SubElement(node, tag)
    return child


def marker_path(world: Path) -> Path:
    return world / "Storage" / "RandomSectorGenerator_RandomSectorGenerator" / "CampaignCelestialVisuals.State.xml"


def marker_applied(world: Path) -> bool:
    path = marker_path(world)
    if not path.is_file():
        return False
    try:
        root = ET.parse(path).getroot()
        return root.findtext("Version") == PATCH_VERSION and root.findtext("Applied") == "true"
    except ET.ParseError:
        return False


def write_marker(world: Path) -> None:
    path = marker_path(world)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("CampaignCelestialVisualsState")
    ET.SubElement(root, "Version").text = PATCH_VERSION
    ET.SubElement(root, "Applied").text = "true"
    ET.SubElement(root, "StarRadiusMultiplier").text = str(STAR_RADIUS_MULT)
    ET.SubElement(root, "BlackHoleRadiusKm").text = str(BLACK_HOLE_RADIUS_KM)
    ET.SubElement(root, "BlackHoleOrbitZoneM").text = str(BLACK_HOLE_ORBIT_ZONE_M)
    ET.indent(root)
    temp = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(root).write(temp, encoding="utf-8", xml_declaration=True)
    os.replace(temp, path)


def tune_real_stars(world: Path, scale_stars: bool) -> list[dict]:
    path = scoped(world, "3152436752", "Config.xml")
    root, encoding = parse_mod_xml(path)
    direct(root, "OverrideFromConfig").text = "true"

    rows = []
    stars = root.findall(".//StarInfo")
    if len(stars) != 4:
        raise RuntimeError(f"Expected four Real Stars; found {len(stars)}")

    for star in stars:
        name = star.findtext("StarCustomName") or star.get("StarName") or "<unnamed>"
        radius = float(star.findtext("Radius") or "0")
        damage = float(star.findtext("DamageRadius") or "0")
        if radius <= 0:
            raise RuntimeError(f"Invalid Real Stars radius for {name}: {radius}")
        before = radius
        if scale_stars:
            radius *= STAR_RADIUS_MULT
            damage *= STAR_RADIUS_MULT
            direct(star, "Radius").text = f"{radius:.6f}".rstrip("0").rstrip(".")
            direct(star, "DamageRadius").text = f"{damage:.6f}".rstrip("0").rstrip(".")
        rows.append({"name": name, "before_km": before, "after_km": radius})

    # Keep native near-star flares strong. The custom client renderer handles
    # distances beyond Real Stars' hard 200,000 km glare limit.
    direct(root, "LensFlareOpacityMult").text = "2"
    direct(root, "LensFlareSizeMult").text = "2"
    write_tree(path, root, encoding)
    return rows


def ring_child(parent: ET.Element, tag: str, text: str) -> None:
    direct(parent, tag).text = text


def configure_black_hole_ring(rings: ET.Element) -> None:
    existing = rings.findall("RingConfigInfo")
    ring = next((x for x in existing if x.findtext("RingSkin") == "DefaultBlackHole"), None)
    if ring is None:
        ring = ET.SubElement(rings, "RingConfigInfo")

    ring_child(ring, "HasRing", "true")
    ring_child(ring, "RingSkin", "DefaultBlackHole")

    normal = direct(ring, "RingNormal")
    ring_child(normal, "X", "0")
    ring_child(normal, "Y", "10")
    ring_child(normal, "Z", "1")

    color = direct(ring, "RingColor")
    ring_child(color, "X", "255")
    ring_child(color, "Y", "165")
    ring_child(color, "Z", "72")

    ring_child(ring, "RingLightMult", "2.5")
    ring_child(ring, "RingShadowMult", "0.15")
    ring_child(ring, "RingInnerScale", "1.15")
    ring_child(ring, "RingOuterScale", "8")
    ring_child(ring, "RingLayerSpacingScale", "0.75")
    ring_child(ring, "RingRotationPeriodSeconds", "900")
    ring_child(ring, "ConstrainNearbyAsteroidsToRing", "false")
    ring_child(ring, "ShadowOnRingEnabled", "false")
    ring_child(ring, "CollectRingResources", "false")
    ring_child(ring, "CollectResourceRingSubtypeId", "Ice")
    ring_child(ring, "CollectResourceRingAmount", "0")
    ring_child(ring, "EnabledDraw", "true")
    ring_child(ring, "EnabledParticle", "true")

    # Do not accumulate stale/duplicate black-hole rings on reapplication.
    seen = False
    for item in list(rings.findall("RingConfigInfo")):
        if item.findtext("RingSkin") != "DefaultBlackHole":
            continue
        if not seen:
            seen = True
        else:
            rings.remove(item)


def tune_black_hole(world: Path) -> dict:
    path = scoped(world, "3232085677", "Config.xml")
    root, encoding = parse_mod_xml(path)
    direct(root, "OverrideFromConfig").text = "true"

    candidates = [
        node
        for node in root.findall(".//GasGiantConfigInfo")
        if node.findtext("PlanetSkin") == "DefaultBlackHole"
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one DefaultBlackHole gas giant; found {len(candidates)}")

    hole = candidates[0]
    direct(hole, "Radius").text = str(BLACK_HOLE_RADIUS_KM)
    rings = direct(hole, "RingsInfo")
    configure_black_hole_ring(rings)
    write_tree(path, root, encoding)

    return {
        "name": hole.findtext("PlanetCustomName") or hole.get("PlanetName") or "<black hole>",
        "radius_km": BLACK_HOLE_RADIUS_KM,
        "disk_outer_radius_km": BLACK_HOLE_RADIUS_KM * 8.0,
    }


def tune_rss_black_hole_zone(world: Path) -> None:
    path = scoped(world, "3351055036", "Config.xml")
    root, encoding = parse_mod_xml(path)
    direct(root, "OverrideFromConfig").text = "true"
    root_body = root.find(".//RootBody")
    if root_body is None or root_body.findtext("PlanetTypeId") != "RealGasGiant":
        raise RuntimeError("RSS root is not the expected RealGasGiant black hole")
    direct(root_body, "PlanetOrbitZoneRadius").text = str(int(BLACK_HOLE_ORBIT_ZONE_M))
    write_tree(path, root, encoding)


def validate(world: Path, scaled_now: bool) -> None:
    star_path = scoped(world, "3152436752", "Config.xml")
    stars, _ = parse_mod_xml(star_path)
    if stars.findtext("OverrideFromConfig") != "true":
        raise RuntimeError("Real Stars override readback failed")
    if len(stars.findall(".//StarInfo")) != 4:
        raise RuntimeError("Real Stars count changed")

    giant_path = scoped(world, "3232085677", "Config.xml")
    giants, _ = parse_mod_xml(giant_path)
    holes = [x for x in giants.findall(".//GasGiantConfigInfo") if x.findtext("PlanetSkin") == "DefaultBlackHole"]
    if len(holes) != 1:
        raise RuntimeError("Black-hole readback failed")
    hole = holes[0]
    if abs(float(hole.findtext("Radius") or "0") - BLACK_HOLE_RADIUS_KM) > 0.01:
        raise RuntimeError("Black-hole radius readback failed")
    rings = [x for x in hole.findall("./RingsInfo/RingConfigInfo") if x.findtext("RingSkin") == "DefaultBlackHole"]
    if len(rings) != 1 or rings[0].findtext("HasRing") != "true":
        raise RuntimeError("Black-hole accretion disk readback failed")

    rss_path = scoped(world, "3351055036", "Config.xml")
    rss, _ = parse_mod_xml(rss_path)
    if abs(float(rss.findtext(".//RootBody/PlanetOrbitZoneRadius") or "0") - BLACK_HOLE_ORBIT_ZONE_M) > 1:
        raise RuntimeError("RSS black-hole orbit zone readback failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_closed()
    world = args.save.expanduser().resolve()
    if not world.is_dir() or not (world / "Sandbox.sbc").is_file():
        raise SystemExit("ERROR: incomplete Space Engineers save: " + str(world))

    already = marker_applied(world)
    if args.dry_run:
        print("Save:", world)
        print("Already applied:", already)
        print("Target black hole radius:", BLACK_HOLE_RADIUS_KM, "km")
        print("Target accretion disk outer radius:", BLACK_HOLE_RADIUS_KM * 8.0, "km")
        print("Target black-hole RSS orbit zone:", BLACK_HOLE_ORBIT_ZONE_M / 1000.0, "km")
        print("Star radius multiplier:", "already applied" if already else STAR_RADIUS_MULT)
        print("DRY RUN: no files changed.")
        return

    backup = archive(world, "World-before-campaign-celestial-visuals")
    star_rows = tune_real_stars(world, scale_stars=not already)
    black_hole = tune_black_hole(world)
    tune_rss_black_hole_zone(world)
    write_marker(world)
    validate(world, scaled_now=not already)

    print("Backup:", backup)
    for row in star_rows:
        print(
            f"Star: {row['name']}: {row['before_km']:.1f} km -> "
            f"{row['after_km']:.1f} km"
        )
    print(
        "Black hole:",
        black_hole["name"],
        f"radius={black_hole['radius_km']:.0f} km",
        f"disk outer radius~{black_hole['disk_outer_radius_km']:.0f} km",
    )
    print("Celestial visual scale pass applied.")


if __name__ == "__main__":
    main()
