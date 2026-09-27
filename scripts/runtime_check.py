"""Summarize the most recent Space Engineers runtime log for RSG/RSS validation."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SE = Path(os.environ["APPDATA"]) / "SpaceEngineers"

KEYWORDS = [
    "[RSG]",
    "Random Sector Generator",
    "RandomSectorGenerator",
    "Real Solar Systems",
    "RealSolarSystems",
    "Real Stars",
    "RealStars",
    "Real Gas Giants",
    "RealGasGiants",
    "Relative Top Speed",
    "RelativeTopSpeed",
    "Aerodynamic Physics",
    "SEDrag",
    "Real Orbits",
    "RealisticGravity",
    "MOD_ERROR",
    "Compilation",
    "compile",
    "Exception",
    "Jormun",
    "Aulden",
    "Seren",
    "Kerbin",
    "Alien",
    "Titan",
    "Triton",
    "Pertam",
    "OrlundaSide",
    "Kor",
    "3618043241",
    "3362332228",
    "3576683005",
    "PlanetGeneratorDefinition",
    "DefinitionErrors",
    "Definition error",
    "ProxyExportBootstrap",
    "Proxy Export Bootstrap",
    "[PEX]",
    "PEX_",
    "Proxy Export Workbench",
    "Failed to load",
    "world load",
    "Error loading heightmap",
    "malformed texture",
    "Cannot build prunning tree",
    "max velocity",
]

ERROR_PATTERNS = [
    re.compile(r"\bMOD_ERROR\b", re.I),
    re.compile(r"\bcompile(?:r|d|ation)?\b.*\b(error|failed|failure)\b", re.I),
    re.compile(r"\bexception\b", re.I),
    re.compile(r"\berror\b.*RandomSectorGenerator", re.I),
    re.compile(r"RandomSectorGenerator.*\berror\b", re.I),
    re.compile(r"\b(definition|mod).*\b(error|failed|failure)\b", re.I),
    re.compile(r"ProxyExportBootstrap.*\b(error|failed|exception)\b", re.I),
    re.compile(r"\[PEX\].*\b(error|failed|exception)\b", re.I),
    re.compile(r"\b(load|loading).*\b(world|save).*\b(error|failed|exception)\b", re.I),
    re.compile(r"(?:RelativeTopSpeed|Relative Top Speed|SEDrag|Aerodynamic Physics|RealisticGravity|Real Orbits).*\b(error|failed|failure|exception)\b", re.I),
    re.compile(r"\b(error|failed|failure|exception)\b.*(?:RelativeTopSpeed|Relative Top Speed|SEDrag|Aerodynamic Physics|RealisticGravity|Real Orbits)", re.I),
]

CAMPAIGN_ISSUES = [
    ("planet_heightmap_fallback", "blocking", re.compile(r"Error loading heightmap", re.I)),
    ("water_texture_fallback", "warning", re.compile(r"WaterMod: Planet config .* malformed texture", re.I)),
    ("heightmap_pruning_optimization", "warning", re.compile(r"Cannot build prunning tree for heightmap face", re.I)),
    ("speed_definition_conflict", "blocking", re.compile(r"(?:max(?:imum)?\s+(?:grid\s+)?velocity|speed.definition).*(?:conflict|duplicate|failed|error)", re.I)),
]

def latest_log():
    logs = [p for p in SE.glob("SpaceEngineers*.log") if p.is_file()]
    if not logs:
        raise RuntimeError(f"No Space Engineers logs found under {SE}")
    return max(logs, key=lambda p: p.stat().st_mtime)

def main():
    REPORTS.mkdir(exist_ok=True)
    log = latest_log()
    lines = log.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    relevant = []
    errors = []
    campaign_issues = []
    for i, line in enumerate(lines):
        if any(k.lower() in line.lower() for k in KEYWORDS):
            relevant.append({"line": i + 1, "text": line})
        if any(p.search(line) for p in ERROR_PATTERNS):
            errors.append({"line": i + 1, "text": line})
        for issue, severity, pattern in CAMPAIGN_ISSUES:
            if pattern.search(line):
                campaign_issues.append({"line": i + 1, "issue": issue,
                                        "severity": severity, "text": line})

    # Add small context around any RSG-specific line so startup/handshake sequences are visible.
    context_indexes = set()
    for row in relevant:
        if "rsg" in row["text"].lower() or "randomsector" in row["text"].lower():
            idx = row["line"] - 1
            for j in range(max(0, idx - 3), min(len(lines), idx + 4)):
                context_indexes.add(j)
    context = [{"line": i + 1, "text": lines[i]} for i in sorted(context_indexes)]

    speed_orbit_indexes = set()
    integration_markers = (
        "relativetop", "relative top speed", "aerodynamic physics",
        "sedrag", "real orbits", "realisticgravity"
    )
    for row in relevant:
        if any(marker in row["text"].lower() for marker in integration_markers):
            idx = row["line"] - 1
            for j in range(max(0, idx - 3), min(len(lines), idx + 4)):
                speed_orbit_indexes.add(j)
    speed_orbit_context = [
        {"line": i + 1, "text": lines[i]} for i in sorted(speed_orbit_indexes)
    ]

    error_context_indexes = set()
    for row in errors:
        idx = row["line"] - 1
        for j in range(max(0, idx - 4), min(len(lines), idx + 8)):
            error_context_indexes.add(j)
    error_context = [{"line": i + 1, "text": lines[i]} for i in sorted(error_context_indexes)]

    result = {
        "log": str(log),
        "modified": log.stat().st_mtime,
        "relevant_count": len(relevant),
        "error_count": len(errors),
        "campaign_issue_count": len(campaign_issues),
        "campaign_issues": campaign_issues[-200:],
        "errors": errors[-200:],
        "error_context": error_context[-1200:],
        "relevant": relevant[-1000:],
        "rsg_context": context[-400:],
        "speed_orbit_context": speed_orbit_context[-400:],
    }
    out = REPORTS / "runtime-check.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")

    print(json.dumps({
        "log": str(log),
        "relevant_count": len(relevant),
        "error_count": len(errors),
        "campaign_issue_count": len(campaign_issues),
        "report": str(out),
        "last_relevant": relevant[-20:],
        "last_error_context": error_context[-80:],
    }, indent=2))

if __name__ == "__main__":
    main()
