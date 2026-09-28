"""Resolve a public Steam Workshop collection and cache its current children."""
import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from audit import OUT

COLLECTION_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/"
)
DETAILS_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
)
CACHE = OUT / "steam-collection.json"


def classify_content(tags, local):
    normalized = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
    if "ingamescript" in normalized:
        return "IngameScript"
    if "blueprint" in normalized:
        return "Blueprint"
    if "scenario" in normalized:
        return "Scenario"
    if "mod" in normalized:
        return "Mod"

    path = Path(local.get("path", "")) if local else Path()
    if path.is_dir():
        if (path / "Script.cs").is_file():
            return "IngameScript"
        if (path / "bp.sbc").is_file():
            return "Blueprint"
        if (path / "Sandbox.sbc").is_file():
            return "Scenario"
        if (path / "Data").is_dir():
            return "Mod"
    return "Other"


def post_json(url, fields):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("ascii"),
        headers={"User-Agent": "SpaceEngineersMultiSystemGenerator/phase-a"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def fetch(collection_id):
    payload = post_json(COLLECTION_URL, {
        "collectioncount": "1",
        "publishedfileids[0]": collection_id,
    })
    response = payload.get("response", {})
    details = response.get("collectiondetails", [])
    if response.get("result") != 1 or len(details) != 1:
        raise RuntimeError("Steam returned an invalid collection response")
    collection = details[0]
    if collection.get("result") != 1:
        raise RuntimeError(
            "Steam could not resolve collection %s (result %s)" %
            (collection_id, collection.get("result"))
        )
    children = collection.get("children", [])
    child_ids = [str(item["publishedfileid"]) for item in children]
    if not child_ids:
        raise RuntimeError("Steam collection %s has no children" % collection_id)

    if len(child_ids) != len(set(child_ids)):
        raise RuntimeError("Steam collection contains duplicate children")
    published = []
    for offset in range(0, len(child_ids), 100):
        batch = child_ids[offset:offset + 100]
        fields = {"itemcount": str(len(batch))}
        for index, published_id in enumerate(batch):
            fields["publishedfileids[%s]" % index] = published_id
        item_response = post_json(DETAILS_URL, fields).get("response", {})
        published.extend(item_response.get("publishedfiledetails", []))
    if len(published) != len(child_ids):
        raise RuntimeError(
            "Steam returned %s item details for %s collection children" %
            (len(published), len(child_ids))
        )
    by_id = {str(item.get("publishedfileid")): item for item in published}
    missing_details = [item for item in child_ids if item not in by_id]
    if missing_details:
        raise RuntimeError("Steam omitted item details for: " + ", ".join(missing_details))
    return children, by_id


def resolve(collection_id, inventory, use_cache=False):
    installed = {item["id"]: item for item in inventory["mods"]}
    if use_cache:
        if not CACHE.is_file():
            raise RuntimeError("No cached Steam collection exists at " + str(CACHE))
        report = json.loads(CACHE.read_text(encoding="utf-8"))
        if report.get("collection_id") != collection_id:
            raise RuntimeError("Cached Steam collection ID does not match " + collection_id)
        report["cache_used"] = True
        refreshed = []
        for item in report["items"]:
            local = installed.get(item["id"], {})
            tags = item.get("tags", [])
            refreshed.append(dict(item, installed=item["id"] in installed,
                                  path=local.get("path"), tags=tags,
                                  workshop_content_type=classify_content(tags, local)))
        report["items"] = refreshed
    else:
        try:
            children, details = fetch(collection_id)
        except (OSError, urllib.error.URLError, ValueError, RuntimeError) as error:
            raise RuntimeError(
                "Steam collection resolution failed; rerun with --use-cache only "
                "if the last successful collection snapshot is intentionally accepted: %s" % error
            ) from error
        items = []
        for child in children:
            published_id = str(child["publishedfileid"])
            detail = details[published_id]
            local = installed.get(published_id, {})
            title = detail.get("title") or local.get("title")
            tags = [entry.get("tag") for entry in detail.get("tags", []) if entry.get("tag")]
            items.append({
                "id": published_id,
                "sort_order": int(child.get("sortorder", 0)),
                "title": title,
                "steam_result": int(detail.get("result", 0)),
                "consumer_app_id": int(detail.get("consumer_app_id", 0) or 0),
                "creator_app_id": int(detail.get("creator_app_id", 0) or 0),
                "time_updated": int(detail.get("time_updated", 0) or 0),
                "file_size": int(detail.get("file_size", 0) or 0),
                "visibility": int(detail.get("visibility", 0) or 0),
                "tags": tags,
                "workshop_content_type": classify_content(tags, local),
                "installed": published_id in installed,
                "path": local.get("path"),
                "active": None,
                "classification": "pending Phase A policy",
                "exclusion_reason": None,
            })
        report = {
            "collection_id": collection_id,
            "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cache_used": False,
            "child_workshop_ids": [item["id"] for item in items],
            "items": items,
        }
    missing = [item["id"] for item in report["items"] if not item["installed"]]
    report["missing_collection_items"] = missing
    CACHE.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                     encoding="utf-8", newline="\r\n")
    if missing:
        raise RuntimeError(
            "Collection items are not installed locally: " + ", ".join(missing)
        )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--inventory", type=Path, default=OUT / "inventory.json")
    parser.add_argument("--use-cache", action="store_true")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    report = resolve(args.collection_id, inventory, args.use_cache)
    print("Steam collection: %s" % report["collection_id"])
    print("Collection items: %s" % len(report["items"]))
    print("Collection source: %s" % ("explicit cached snapshot" if report["cache_used"] else "live Steam API"))
    print("Missing collection items: %s" % len(report["missing_collection_items"]))


if __name__ == "__main__":
    main()
