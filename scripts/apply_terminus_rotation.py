"""Apply a small local differential-rotation patch to Terminus's accretion disk.

The Workshop item remains the source of all Terminus models/textures. This script edits
only the six 3DAccretionDiskConcave cloud-layer AngularVelocity values in the installed
Terminus.sbc, after validating the exact expected layer layout. Steam may restore the
Workshop file during an update/verification, so the Random Sector installer reapplies
this patch before building a campaign.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "reports" / "inventory.json"
BACKUPS = ROOT / "backups"
WORKSHOP_ID = "3481843850"
RELATIVE_DEFINITION = Path("Data") / "Terminus.sbc"
DISK_MODEL = "Models/Environment/Sky/3DAccretionDiskConcave.mwm"

# Space Engineers documents cloud-layer AngularVelocity as radians per roughly
# ten simulation ticks. These values target visually readable differential
# rotation: about 90 s at the inner disk to about 12 min at the outer disk.
TARGETS = {
    120.0: "0.0116",
    240.0: "0.0087",
    480.0: "0.0058",
    960.0: "0.0035",
    1920.0: "0.0022",
    2940.0: "0.0015",
}

CLOUD_RE = re.compile(r"<CloudLayer>.*?</CloudLayer>", re.I | re.S)
MODEL_RE = re.compile(r"<Model>\s*([^<]+?)\s*</Model>", re.I)
ALT_RE = re.compile(r"(<RelativeAltitude>\s*)([-+0-9.eE]+)(\s*</RelativeAltitude>)", re.I)
VELOCITY_RE = re.compile(r"(<AngularVelocity>\s*)([-+0-9.eE]+)(\s*</AngularVelocity>)", re.I)


def ensure_closed() -> None:
    if sys.platform != "win32":
        return
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq SpaceEngineers.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "SpaceEngineers.exe" in result.stdout:
        raise RuntimeError("Exit Space Engineers before patching Terminus.")


def terminus_definition() -> Path:
    if not INVENTORY.is_file():
        raise RuntimeError("reports/inventory.json is missing; run scripts\\audit.py first.")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    matches = [
        Path(mod["path"]) / RELATIVE_DEFINITION
        for mod in inventory.get("mods", [])
        if str(mod.get("id")) == WORKSHOP_ID
    ]
    matches = [path for path in matches if path.is_file()]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one installed Terminus {RELATIVE_DEFINITION}; found {len(matches)}."
        )
    return matches[0]


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:128]:
            return raw.decode("utf-16"), "utf-16"
        raise RuntimeError("Unsupported Terminus.sbc text encoding.")


def validate_layers(text: str) -> dict[float, str]:
    found: dict[float, str] = {}
    for match in CLOUD_RE.finditer(text):
        block = match.group(0)
        model = MODEL_RE.search(block)
        if not model or model.group(1).strip().replace("\\", "/") != DISK_MODEL:
            continue
        altitude = ALT_RE.search(block)
        velocity = VELOCITY_RE.search(block)
        if not altitude or not velocity:
            raise RuntimeError("A Terminus accretion-disk layer is missing altitude or velocity.")
        key = float(altitude.group(2))
        if key in found:
            raise RuntimeError(f"Duplicate Terminus disk RelativeAltitude: {key:g}")
        found[key] = velocity.group(2)

    expected = set(TARGETS)
    actual = set(found)
    if actual != expected:
        raise RuntimeError(
            "Unexpected Terminus accretion-disk layout. Expected altitudes "
            f"{sorted(expected)}, found {sorted(actual)}. Workshop content may have changed."
        )
    return found


def patch_text(text: str) -> str:
    def patch_layer(match: re.Match[str]) -> str:
        block = match.group(0)
        model = MODEL_RE.search(block)
        if not model or model.group(1).strip().replace("\\", "/") != DISK_MODEL:
            return block
        altitude = ALT_RE.search(block)
        if not altitude:
            raise RuntimeError("Terminus disk layer is missing RelativeAltitude.")
        key = float(altitude.group(2))
        target = TARGETS.get(key)
        if target is None:
            raise RuntimeError(f"Unexpected Terminus disk altitude during patch: {key:g}")
        if not VELOCITY_RE.search(block):
            raise RuntimeError("Terminus disk layer is missing AngularVelocity.")
        return VELOCITY_RE.sub(lambda m: m.group(1) + target + m.group(3), block, count=1)

    return CLOUD_RE.sub(patch_layer, text)


def main() -> None:
    ensure_closed()
    path = terminus_definition()
    raw = path.read_bytes()
    text, encoding = decode(raw)
    before = validate_layers(text)
    patched = patch_text(text)
    after = validate_layers(patched)

    expected_after = {alt: value for alt, value in TARGETS.items()}
    if after != expected_after:
        raise RuntimeError(f"Terminus rotation validation failed: {after}")

    ET.fromstring(patched)
    changed = patched != text
    backup = None

    if changed:
        BACKUPS.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUPS / f"Terminus-before-disk-rotation-{stamp}.sbc"
        backup.write_bytes(raw)

        payload = patched.encode(encoding)
        fd, temp_name = tempfile.mkstemp(prefix="Terminus.", suffix=".sbc.tmp", dir=str(path.parent))
        os.close(fd)
        temp = Path(temp_name)
        try:
            temp.write_bytes(payload)
            check_text, _ = decode(temp.read_bytes())
            validate_layers(check_text)
            ET.fromstring(check_text)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    print(json.dumps({
        "definition": str(path),
        "changed": changed,
        "backup": str(backup) if backup else None,
        "disk_model": DISK_MODEL,
        "layers": [
            {
                "relative_altitude": int(altitude),
                "angular_velocity": float(TARGETS[altitude]),
            }
            for altitude in sorted(TARGETS)
        ],
        "event_horizon_layers_modified": False,
    }, indent=2))


if __name__ == "__main__":
    main()
