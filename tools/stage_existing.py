"""Move skillget-installed folders out of the live skill root into staging.

The harness auto-loads every SKILL.md under ~/.agents/skills, which makes a
9,271-skill bulk install impractical in one session. Staging keeps the crawl
fast; `skillget merge` moves the finished library back at the end.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import installer  # noqa: E402

LIVE = Path.home() / ".agents" / "skills"
STAGING = Path.home() / "AppData" / "Local" / "Temp" / "opencode" / "skillget-staging"
SRC_MANIFEST = ROOT / "data" / "manifest.json"
DST_MANIFEST = ROOT / "data" / "manifest-staging.json"


def main() -> int:
    manifest = installer.Manifest(SRC_MANIFEST)
    STAGING.mkdir(parents=True, exist_ok=True)
    moved = 0
    for slug, entry in manifest.data["skills"].items():
        if entry.get("status") != "ok" or not entry.get("folder"):
            continue
        src = LIVE / entry["folder"]
        dst = STAGING / entry["folder"]
        if dst.exists():
            entry["path"] = str(dst)
            moved += 1
            continue
        if not src.exists():
            continue
        shutil.move(str(src), str(dst))
        entry["path"] = str(dst)
        moved += 1
    tmp = LIVE / ".skillget-tmp"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    DST_MANIFEST.write_text(json.dumps(manifest.data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"staged {moved} skills -> {STAGING}")
    print(f"manifest -> {DST_MANIFEST}")
    print(f"live folders left: {sum(1 for p in LIVE.iterdir() if p.is_dir())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
