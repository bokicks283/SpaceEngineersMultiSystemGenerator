"""Remove collection entries that are not world mods from pending RSG saves."""
import json
import re
import xml.etree.ElementTree as ET

from world_checkpoint import ROOT, SAVE_ROOT, archive, ensure_closed, write_atomic


STATE_NAME = "RandomSectorGenerator.State.xml"


def pending_state(path):
    raw = path.read_bytes().decode("utf-8-sig")
    raw = re.sub(r'encoding=["\']utf-16["\']', 'encoding="utf-8"', raw, count=1, flags=re.I)
    root = ET.fromstring(raw)
    return root.findtext("PendingApply") == "true" and root.findtext("Applied") != "true"


def pending_worlds():
    root = SAVE_ROOT.resolve()
    worlds = set()
    if not root.is_dir():
        return []
    for state in root.rglob(STATE_NAME):
        relative = state.resolve().relative_to(root)
        if "Backup" in relative.parts:
            continue
        storage = next((parent for parent in state.parents if parent.name == "Storage"), None)
        if storage is None or root not in storage.resolve().parents:
            continue
        world = storage.parent.resolve()
        if pending_state(state):
            worlds.add(world)
    return sorted(worlds, key=lambda path: str(path).casefold())


def excluded_ids():
    plan = json.loads((ROOT / "reports" / "pack-plan.json").read_text(encoding="utf-8"))
    return {str(item["id"]) for item in plan.get("collection_non_world_content", [])}


def mod_ids(path):
    return [
        item.findtext("PublishedFileId")
        for item in ET.parse(path).findall("./Mods/ModItem")
        if item.find("PublishedFileId") is not None
    ]


def remove_ids(path, targets):
    tree = ET.parse(path)
    mods = tree.getroot().find("Mods")
    if mods is None:
        raise RuntimeError(f"World is missing mod list: {path}")
    removed = []
    for item in list(mods.findall("ModItem")):
        published_id = item.findtext("PublishedFileId")
        if published_id in targets:
            mods.remove(item)
            removed.append(published_id)
    if removed:
        write_atomic(tree, path)
    return removed


def main():
    ensure_closed()
    targets = excluded_ids()
    if not targets:
        print(json.dumps({"pending_worlds": 0, "changed": 0, "reason": "No non-world collection entries"}, indent=2))
        return

    results = []
    for world in pending_worlds():
        files = [world / "Sandbox.sbc", world / "Sandbox_config.sbc"]
        if any(not path.is_file() for path in files):
            raise RuntimeError(f"Pending RSG save is incomplete: {world}")
        present = sorted({item for path in files for item in mod_ids(path)} & targets)
        if not present:
            results.append({"world": str(world), "changed": False, "removed": []})
            continue

        world_key = "-".join(world.relative_to(SAVE_ROOT.resolve()).parts)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", world_key).strip("-")
        backup = archive(world, f"World-before-non-world-mod-cleanup-{safe_name}")
        removed = sorted({item for path in files for item in remove_ids(path, targets)})
        remaining = {item for path in files for item in mod_ids(path)} & targets
        if remaining:
            raise RuntimeError(f"Non-world collection entries remain in {world}: {sorted(remaining)}")
        results.append({"world": str(world), "changed": True, "removed": removed, "backup": str(backup)})

    print(json.dumps({"pending_worlds": len(results), "changed": sum(row["changed"] for row in results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
