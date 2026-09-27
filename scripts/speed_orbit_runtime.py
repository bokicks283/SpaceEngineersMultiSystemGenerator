"""Inspect RTS/Aero/Real Orbits runtime config for the clean disposable world.

This script is intentionally read-only. It tolerates the false UTF-16/UTF-32
XML declarations emitted by some Space Engineers mod serializers when the
actual file bytes are UTF-8.
"""
import json
import os
import re
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

FALSE_WIDE_DECL = re.compile(
    r'(<\?xml[^>]*\bencoding=["\'])utf-(?:16|32)(["\'])',
    re.IGNORECASE,
)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_xml_compat(path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw), None
    except Exception as first:
        # Several SE mods serialize XML to a .NET string (which declares
        # UTF-16) and then write that string as UTF-8. The game accepts the
        # text because its storage API deserializes strings, but a byte-aware
        # XML parser correctly rejects the mismatched declaration.
        try:
            text = raw.decode("utf-8-sig")
            repaired = FALSE_WIDE_DECL.sub(r"\1utf-8\2", text, count=1)
            if repaired == text:
                raise first
            return ET.fromstring(repaired), None
        except Exception:
            return None, str(first)


def relevant_xml_values(path):
    root, error = parse_xml_compat(path)
    if root is None:
        return {"parse_error": error, "values": {}}

    values = {}

    def walk(element, parent=""):
        name = local_name(element.tag)
        current = f"{parent}/{name}" if parent else name

        if name == "Point":
            mass = element.get("Mass")
            speed = element.get("Speed")
            if mass is not None or speed is not None:
                values[f"{current}[Mass={mass}]"] = {
                    "Mass": mass,
                    "Speed": speed,
                }

        if not list(element):
            value = (element.text or "").strip()
            if value and any(token in name.lower() for token in INTERESTING):
                values[current] = value

        for child in element:
            walk(child, current)

    walk(root)
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
    configs_parse = [
        row for group in ("rts", "real_orbits")
        for row in found[group]
    ]
    result = {
        "world": str(WORLD),
        "mods_present": {name: wid in mods for name, wid in MOD_IDS.items()},
        "configs": found,
        "expectations": {
            "rts_config_after_first_load": "expected",
            "aero_config_after_first_load": "optional on listen host",
            "real_orbits_config_after_first_load": "expected",
        },
        "ready_for_tuning_review": bool(
            found["rts"] and found["real_orbits"] and
            all(row["parse_error"] is None for row in configs_parse)
        ),
        "writes_performed": False,
    }
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "speed-orbit-runtime.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({**result, "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
