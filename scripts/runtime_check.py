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
    "MOD_ERROR",
    "Compilation",
    "compile",
    "Exception",
]

ERROR_PATTERNS = [
    re.compile(r"\bMOD_ERROR\b", re.I),
    re.compile(r"\bcompile(?:r|d|ation)?\b.*\b(error|failed|failure)\b", re.I),
    re.compile(r"\bexception\b", re.I),
    re.compile(r"\berror\b.*RandomSectorGenerator", re.I),
    re.compile(r"RandomSectorGenerator.*\berror\b", re.I),
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
    for i, line in enumerate(lines):
        if any(k.lower() in line.lower() for k in KEYWORDS):
            relevant.append({"line": i + 1, "text": line})
        if any(p.search(line) for p in ERROR_PATTERNS):
            errors.append({"line": i + 1, "text": line})

    # Add small context around any RSG-specific line so startup/handshake sequences are visible.
    context_indexes = set()
    for row in relevant:
        if "rsg" in row["text"].lower() or "randomsector" in row["text"].lower():
            idx = row["line"] - 1
            for j in range(max(0, idx - 3), min(len(lines), idx + 4)):
                context_indexes.add(j)
    context = [{"line": i + 1, "text": lines[i]} for i in sorted(context_indexes)]

    result = {
        "log": str(log),
        "modified": log.stat().st_mtime,
        "relevant_count": len(relevant),
        "error_count": len(errors),
        "errors": errors[-200:],
        "relevant": relevant[-1000:],
        "rsg_context": context[-400:],
    }
    out = REPORTS / "runtime-check.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "log": str(log),
        "relevant_count": len(relevant),
        "error_count": len(errors),
        "report": str(out),
        "last_relevant": relevant[-20:],
    }, indent=2))

if __name__ == "__main__":
    main()
