"""Repair an interrupted or concurrent crawl.

A crash (or two crawlers racing) can leave finished skills stranded inside
``<dest>/.skillget-tmp`` instead of the live skill root, and can leave the
manifest out of sync with what is actually on disk. This tool:

1. Recovers any temp folder that contains a complete ``SKILL.md`` +
   ``.skillget.json`` into ``<dest>/<folder>`` when that folder is missing.
2. Deletes the remaining (incomplete) temp folders.
3. Rebuilds the manifest from the folders that carry a ``.skillget.json``,
   marking each as ``ok`` and preserving any richer fields already recorded.

It never deletes a live skill folder and never overwrites an existing one.
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

DEFAULT_DEST = Path.home() / ".agents" / "skills"
DEFAULT_MANIFEST = ROOT / "data" / "manifest.json"


def read_provenance(path: Path) -> dict | None:
    meta = path / ".skillget.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def recover_temp(dest: Path) -> tuple[int, int]:
    """Move complete temp installs into place, delete the rest."""
    tmp_root = dest / ".skillget-tmp"
    if not tmp_root.is_dir():
        return 0, 0
    recovered = 0
    removed = 0
    # Prefer "old-" folders: those were complete installs moved aside during a
    # replace. Then plain staged folders.
    entries = sorted(tmp_root.iterdir(), key=lambda p: (not p.name.startswith("old-"), p.name))
    for entry in entries:
        if not entry.is_dir():
            try:
                entry.unlink()
            except OSError:
                pass
            continue
        prov = read_provenance(entry)
        has_md = (entry / "SKILL.md").exists()
        if prov and has_md and prov.get("slug"):
            folder = installer.safe_folder(prov.get("folder") or prov["slug"])
            target = dest / folder
            if not target.exists():
                try:
                    entry.rename(target)
                    recovered += 1
                    continue
                except OSError:
                    pass
        try:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        except OSError:
            pass
    return recovered, removed


def rebuild_manifest(dest: Path, manifest_path: Path) -> int:
    manifest = installer.Manifest(manifest_path)
    scanned = 0
    added = 0
    for folder in sorted(dest.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        if not (folder / "SKILL.md").exists():
            continue
        prov = read_provenance(folder)
        if not prov or not prov.get("slug"):
            continue
        slug = prov["slug"]
        scanned += 1
        existing = manifest.get(slug) or {}
        if not existing:
            added += 1
        manifest.mark(
            slug,
            name=existing.get("name") or prov.get("name", ""),
            folder=folder.name,
            source=existing.get("source") or prov.get("source", ""),
            license=existing.get("license") or prov.get("license", ""),
            categories=existing.get("categories") or prov.get("categories", []),
            resource_failures=existing.get("resource_failures")
            or prov.get("resources_failed", []),
            skill_md=existing.get("skill_md") or prov.get("skill_md", "raw"),
            files=existing.get("files", 2),
            status="ok",
            path=str(folder),
        )
    manifest.save()
    print(f"scanned folders with provenance: {scanned}")
    print(f"new manifest entries added: {added}")
    print(f"manifest total: {len(manifest.data['skills'])}")
    return scanned


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reconcile", description=__doc__)
    p.add_argument("--dest", default=str(DEFAULT_DEST))
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--skip-recover", action="store_true")
    p.add_argument("--skip-manifest", action="store_true")
    args = p.parse_args(argv)

    dest = Path(args.dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if not args.skip_recover:
        recovered, removed = recover_temp(dest)
        print(f"recovered from temp: {recovered}")
        print(f"discarded temp folders: {removed}")
    if not args.skip_manifest:
        rebuild_manifest(dest, Path(args.manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
