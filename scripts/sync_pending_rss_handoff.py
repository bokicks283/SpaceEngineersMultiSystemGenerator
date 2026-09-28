"""Restore pending RSG payloads to the checkpoint variable consumed by RSS."""
import base64
import json
import re
import xml.etree.ElementTree as ET

from sync_pending_world_mods import STATE_NAME, pending_worlds
from world_checkpoint import RSG_KEY, RSS_KEY, archive, ensure_closed, get_variable, put_variable, write_atomic


def read_pending_payload(world):
    matches = list((world / "Storage").rglob(STATE_NAME))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one RSG state file in {world}; found {len(matches)}")
    raw = matches[0].read_bytes().decode("utf-8-sig")
    raw = re.sub(r'encoding=["\']utf-16["\']', 'encoding="utf-8"', raw, count=1, flags=re.I)
    root = ET.fromstring(raw)
    payload = root.findtext("RssConfigBase64")
    if not payload or len(base64.b64decode(payload, validate=True)) < 100:
        raise RuntimeError(f"Pending RSG state has no RSS payload: {matches[0]}")
    return payload


def main():
    ensure_closed()
    results = []
    for world in pending_worlds():
        checkpoint = world / "Sandbox.sbc"
        if not checkpoint.is_file():
            raise RuntimeError(f"Pending RSG save has no checkpoint: {world}")
        payload = read_pending_payload(world)
        tree = ET.parse(checkpoint)
        current = get_variable(tree, RSS_KEY)
        if current == payload:
            results.append({"world": str(world), "changed": False, "payload_matches": True})
            continue

        world_key = "-".join(world.parts[-2:])
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", world_key).strip("-")
        backup = archive(world, f"World-before-pending-RSS-handoff-repair-{safe_name}")
        put_variable(tree, RSS_KEY, payload)
        if get_variable(tree, RSG_KEY) != "handoff-committed":
            put_variable(tree, RSG_KEY, "handoff-committed")
        write_atomic(tree, checkpoint)

        check = ET.parse(checkpoint)
        if get_variable(check, RSS_KEY) != payload:
            raise RuntimeError(f"RSS handoff readback mismatch: {world}")
        results.append({
            "world": str(world),
            "changed": True,
            "payload_matches": True,
            "backup": str(backup),
        })

    print(json.dumps({
        "pending_worlds": len(results),
        "changed": sum(row["changed"] for row in results),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
