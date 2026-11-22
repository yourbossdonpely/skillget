"""Merge a staged skill library into the live ~/.agents/skills root.

Safe by default: never overwrites a folder that was not installed by skillget.
Colliding third-party folders get a `-tm` suffix instead.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import installer  # noqa: E402


def load_manifest(path: Path) -> installer.Manifest:
    return installer.Manifest(path)


def read_provenance(folder: Path) -> dict:
    meta = folder / ".skillget.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pick_target(dest: Path, base: str, slug: str) -> str:
    candidate = base
    n = 1
    while True:
        target = dest / candidate
        if not target.exists():
            return candidate
        meta = read_provenance(target)
        if meta.get("slug") == slug:
            return candidate
        n += 1
        candidate = f"{base}-tm" if n == 2 else f"{base}-tm-{n - 1}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge staged skills into the live skill root")
    ap.add_argument("--source", default=str(Path.home() / "AppData" / "Local" / "Temp" / "opencode" / "skillget-staging"))
    ap.add_argument("--dest", default=str(Path.home() / ".agents" / "skills"))
    ap.add_argument("--source-manifest", default=str(ROOT / "data" / "manifest-staging.json"))
    ap.add_argument("--dest-manifest", default=str(ROOT / "data" / "manifest.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()
    src_manifest = load_manifest(Path(args.source_manifest))
    dst_manifest = load_manifest(Path(args.dest_manifest))
    dest.mkdir(parents=True, exist_ok=True)

    entries = {k: v for k, v in src_manifest.data["skills"].items() if v.get("status") == "ok"}
    moved = 0
    renamed = 0
    skipped = 0
    already = 0
    failed = 0
    for slug, entry in entries.items():
        folder = entry.get("folder")
        src = source / folder if folder else None
        if not folder or not src or not src.is_dir() or not (src / "SKILL.md").exists():
            # A rerun after a partial merge: the folder may already be in place.
            current = dst_manifest.get(slug) or {}
            target = dest / current["folder"] if current.get("folder") else None
            if target and target.is_dir() and (target / "SKILL.md").exists():
                already += 1
            else:
                skipped += 1
            continue
        target_name = pick_target(dest, folder, slug)
        if target_name != folder:
            renamed += 1
        target = dest / target_name
        if args.dry_run:
            print(f"would move {folder} -> {target_name}")
            moved += 1
            continue
        try:
            if target.exists():
                meta = read_provenance(target)
                if meta.get("slug") == slug:
                    shutil.rmtree(target)
                else:
                    raise RuntimeError(f"refusing to overwrite {target}")
            shutil.move(str(src), str(target))
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            failed += 1
            entry["merge_error"] = f"{type(e).__name__}: {e}"
            print(f"FAILED {slug}: {entry['merge_error']}")
            continue
        entry["folder"] = target_name
        entry["path"] = str(target)
        entry["merged_at"] = installer.utcnow()
        entry.pop("merge_error", None)
        dst_manifest.mark(slug, **{k: v for k, v in entry.items() if k != "slug"})
        moved += 1
        if moved % 250 == 0:
            dst_manifest.save()
            print(f"merged {moved} ...")

    if not args.dry_run:
        dst_manifest.save()
    print(f"merged={moved} renamed={renamed} already={already} skipped={skipped} failed={failed}")
    print(f"dest: {dest}")
    print(f"dest manifest: {args.dest_manifest}")
    return 0 if skipped == 0 and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
