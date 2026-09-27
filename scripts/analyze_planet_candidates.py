"""Score locally installed planet mods against the selected material union."""
import argparse
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from audit import ROOT, OUT

DEFAULT_IDS = ["2941085186", "2961923776", "2961924256"]
KNOWN_TITLES = {"2941085186": "Kerbin", "2961923776": "Aulden", "2961924256": "Seren"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", default=DEFAULT_IDS)
    args = parser.parse_args()
    inventory = json.loads((OUT / "inventory.json").read_text(encoding="utf-8"))
    mods = {m["id"]: m for m in inventory["mods"]}
    baseline = set(json.loads((OUT / "selected-voxel-audit.json").read_text(encoding="utf-8"))["subtypes"])
    vanilla = {d["subtype"] for g in inventory["games"] for d in g["definitions"]["voxels"]}
    plan = json.loads((OUT / "pack-plan.json").read_text(encoding="utf-8"))
    active_ids = {m["id"] for m in plan["selected_workshop"]}
    native = set()
    science = Path(mods["3665099597"]["path"]) / "Data"
    for f in science.glob("*.sbc"):
        for e in ET.parse(f).iter("EntityComponent"):
            subtype = e.findtext("Id/SubtypeId", "")
            if subtype.startswith("PlanetBiomePresetType_"):
                native.add(subtype.removeprefix("PlanetBiomePresetType_"))
    local_science = set()
    local_file = ROOT / "mods/CampaignScienceCompatibility/Data/CampaignBiomes.sbc"
    if local_file.is_file():
        for name in re.findall(r"PlanetBiomePresetType_([^<]+)", local_file.read_text(encoding="utf-8")):
            local_science.add(name)
    proxy = {}
    for m in inventory["mods"]:
        for p in m["proxies"]:
            targets = re.findall(r"PlanetDefaults:\s*([^\r\n]+)", p.get("description") or "")
            if not targets and p["subtype"].startswith("PlanetProxyType_"):
                targets = [p["subtype"].removeprefix("PlanetProxyType_")]
            for target in (x.strip() for group in targets for x in group.split(",")):
                proxy.setdefault(target, []).append({"mod": m["id"], "subtype": p["subtype"],
                                                      "active": m["id"] in active_ids})
    rows = []
    for wid in args.ids:
        m = mods.get(wid)
        if m is None:
            rows.append({"id": wid, "installed": False})
            continue
        names = {v["subtype"] for v in m["voxels"]}
        used = set()
        for planet in m["planets"]:
            root = ET.parse(planet["file"]).getroot()
            used.update(e.get("Material") for e in root.iter() if e.get("Material"))
            used.update(e.get("Type") for e in root.iter("Ore") if e.get("Type"))
        used.discard(None)
        used.difference_update({"true", "false"})
        cost = len(names - baseline)
        water_variant = {p["subtype"]: ("Water Mod Ready" in p["subtype"])
                         for p in m["planets"]}
        rows.append({
            "id": wid, "title": m["title"] or KNOWN_TITLES.get(wid), "path": m["path"], "installed": True,
            "planet_subtypes": [p["subtype"] for p in m["planets"]],
            "defined_custom_voxels": sorted(names - vanilla),
            "incremental_voxels": sorted(names - baseline), "incremental_cost": cost,
            "referenced_voxel_materials": sorted(used),
            "existing_material_overlap": sorted(used & baseline),
            "unresolved_material_references": sorted(used - baseline - names),
            "cost_class": "FREE" if cost == 0 else "CHEAP" if cost <= 2 else "MODERATE" if cost == 3 else "EXPENSIVE",
            "dependencies_in_metadata": m["dependencies"],
            "water_mod_terrain_variant": water_variant,
            "science": {p["subtype"]: "native" if p["subtype"] in native else
                        "local" if p["subtype"] in local_science else "missing"
                        for p in m["planets"]},
            "proxies": {p["subtype"]: proxy.get(p["subtype"], []) for p in m["planets"]},
            "proxy_count": {p["subtype"]: sum(x["active"] for x in proxy.get(p["subtype"], []))
                            for p in m["planets"]},
            "export_required": {p["subtype"]: not any(x["active"] for x in proxy.get(p["subtype"], []))
                                for p in m["planets"]},
            "scan_errors": m["errors"],
        })
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
