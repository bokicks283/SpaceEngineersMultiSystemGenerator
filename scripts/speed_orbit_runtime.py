"""Inspect RTS/Aero/Real Orbits runtime config after the clean world's first load.

This script is intentionally read-only. It does not tune or create config files.
"""
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
WORLD = (Path(os.environ["APPDATA"]) / "SpaceEngineers" / "Saves" /
         "76561198045624840" / "RSG Disposable Clean 2026-09-27")

MOD_IDS = {
    "rts": "1359618037",
    "aero": "571920453",
    "real_orbits": "2609118808",
    "rss": "3351055036",
}

INTERESTING = (
    "speed", "remote", "boost", "resistance", "cruise",
    "drag", "heat", "reentry", "multiplier", "gravity",
    "falloff", "orbit",
)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def relevant_xml_values(path):
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return {"parse_error": str(exc), "values": {}}
    values = {}
    for element in root.iter():
        if list(element):
            continue
        name = local_name(element.tag)
        value = (element.text or "").strip()
        if value and any(token in name.lower() for token in INTERESTING):
            values[name] = value
    return {"parse_error": None, "values": values}


def checkpoint_mods():
    checkpoint = ET.parse(WORLD / "Sandbox.sbc").getroot()
    return {
        item.findtext("PublishedFileId")
        for item in checkpoint.findall("./Mods/ModItem")
        if item.findtext("PublishedFileId")
    }


def candidates():
    storage = WORLD / "Storage"
    result = {"rts": [], "aero": [], "real_orbits": []}
    if not storage.is_dir():
        return result

    for path in storage.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        rel = str(path.relative_to(WORLD))
        if name == "relativetopspeed.cfg":
            parsed = relevant_xml_values(path)
            result["rts"].append({"path": rel, **parsed})
            continue
        if name == "dragsettings.xml":
            parsed = relevant_xml_values(path)
            result["aero"].append({"path": rel, **parsed})
            continue
        if name == "config.xml":
            try:
                raw = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            hint = (str(path.parent).lower() + "\n" + raw.lower())
            if ("realisticgravity" in hint or
                    "overrideplanetgravityfalloff" in hint or
                    "largegridmaxspeedmultiplier" in hint or
                    "smallgridmaxspeedmultiplier" in hint):
                parsed = relevant_xml_values(path)
                result["real_orbits"].append({"path": rel, **parsed})
    return result


def main():
    if not WORLD.is_dir():
        raise RuntimeError("Clean disposable world does not exist: " + str(WORLD))

    mods = checkpoint_mods()
    found = candidates()
    result = {
        "world": str(WORLD),
        "mods_present": {name: wid in mods for name, wid in MOD_IDS.items()},
        "configs": found,
        "expectations": {
            "rts_config_after_first_load": "expected",
            "aero_config_after_first_load": "optional on listen host",
            "real_orbits_config_after_first_load": "expected",
        },
        "ready_for_tuning_review": bool(found["rts"] and found["real_orbits"]),
        "writes_performed": False,
    }
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "speed-orbit-runtime.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({**result, "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
