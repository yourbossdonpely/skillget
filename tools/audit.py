"""Audit an installed skill library against the catalog and manifest.

Checks that every `ok` manifest entry has a folder, a non-empty `SKILL.md`, valid
frontmatter, and (optionally) the quiet flag. Also reports catalog entries that are
missing from the manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import installer  # noqa: E402
import quiet  # noqa: E402
import tm_catalog  # noqa: E402

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional validation dependency
    yaml = None


def check_frontmatter(text: str, require_quiet: bool) -> tuple[str, str]:
    parsed = quiet.split_frontmatter(text)
    if parsed is None:
        return "no-frontmatter", ""
    fm, _, _ = parsed
    if yaml is not None:
        try:
            data = yaml.safe_load("\n".join(fm)) or {}
        except Exception as e:  # noqa: BLE001 - report the parser message
            return "bad-yaml", f"{type(e).__name__}: {e}"
        if not isinstance(data, dict):
            return "bad-yaml", "frontmatter is not a mapping"
        if require_quiet:
            meta = data.get("metadata")
            flag = meta.get(quiet.FLAG) if isinstance(meta, dict) else None
            disable = data.get("disable-model-invocation")
            disable_true = disable is True or (
                isinstance(disable, str) and disable.strip().lower() in {"true", "yes", "on", "1"}
            )
            if flag is not False and not disable_true:
                return "not-quiet", ""
    return "ok", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit installed skills")
    ap.add_argument("--dest", default=str(Path.home() / ".agents" / "skills"))
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    ap.add_argument("--catalog", default=str(ROOT / "data" / "catalog.json"))
    ap.add_argument("--require-quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    dest = Path(args.dest).expanduser().resolve()
    catalog = tm_catalog.load_json(Path(args.catalog), {}) or {}
    manifest = installer.Manifest(Path(args.manifest))
    catalog_slugs = {s.get("slug") for s in catalog.get("skills", [])}

    counts: Counter[str] = Counter()
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    entries = [(s, e) for s, e in manifest.data["skills"].items() if e.get("status") == "ok"]
    if args.limit:
        entries = entries[: args.limit]
    for slug, entry in entries:
        folder = entry.get("folder")
        if not folder:
            counts["no-folder"] += 1
            issues.append({"slug": slug, "issue": "no-folder"})
            continue
        if folder in seen:
            counts["duplicate-folder"] += 1
            issues.append({"slug": slug, "issue": "duplicate-folder", "folder": folder})
            continue
        seen.add(folder)
        skill = dest / folder / "SKILL.md"
        if not skill.is_file():
            counts["missing-skill-md"] += 1
            issues.append({"slug": slug, "issue": "missing-skill-md", "folder": folder})
            continue
        try:
            text = skill.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            counts["read-error"] += 1
            issues.append({"slug": slug, "issue": f"read-error: {e}", "folder": folder})
            continue
        if not text.strip():
            counts["empty-skill-md"] += 1
            issues.append({"slug": slug, "issue": "empty-skill-md", "folder": folder})
            continue
        status, detail = check_frontmatter(text, args.require_quiet)
        counts[status] += 1
        if status != "ok":
            issues.append({"slug": slug, "issue": status, "detail": detail, "folder": folder})
        if not (dest / folder / ".skillget.json").is_file():
            counts["no-provenance"] += 1
            issues.append({"slug": slug, "issue": "no-provenance", "folder": folder})

    missing = sorted(s for s in catalog_slugs if s and s not in manifest.data["skills"])
    report = {
        "dest": str(dest),
        "catalog": len(catalog_slugs),
        "manifest_ok": len(entries),
        "checked": sum(counts.values()) - counts.get("no-provenance", 0),
        "status": dict(counts),
        "missing_from_manifest": len(missing),
        "missing_sample": missing[:20],
        "issues_sample": issues[:50],
        "yaml_validator": "pyyaml" if yaml is not None else "none",
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"dest: {dest}")
        print(f"catalog: {report['catalog']}")
        print(f"manifest ok: {report['manifest_ok']}")
        print(f"status: {dict(counts)}")
        print(f"missing from manifest: {report['missing_from_manifest']}")
        if missing:
            print(f"  sample: {', '.join(missing[:10])}")
        if issues:
            print("issues (first 20):")
            for issue in issues[:20]:
                print(f"  {issue}")
        if yaml is None:
            print("note: install pyyaml for frontmatter validation")
    bad = sum(v for k, v in counts.items() if k != "ok")
    return 0 if bad == 0 and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
