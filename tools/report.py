"""Summarize catalog + install manifest as JSON and text."""
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
import tm_catalog  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Report catalog and install coverage")
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    ap.add_argument("--catalog", default=None,
                    help="catalog file (default: data/catalog-<category>.json or data/catalog.json)")
    ap.add_argument("--category", default=None,
                    help="limit the report to one category, e.g. devops")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    catalog_path = args.catalog
    if catalog_path is None:
        scoped = ROOT / "data" / f"catalog-{args.category}.json" if args.category else None
        catalog_path = str(scoped if scoped and scoped.is_file() else ROOT / "data" / "catalog.json")
    catalog = tm_catalog.load_json(Path(catalog_path), {}) or {}
    manifest = installer.Manifest(Path(args.manifest))

    def in_category(entry: dict) -> bool:
        if not args.category:
            return True
        cats = entry.get("categories") or []
        return args.category in [str(c).strip().lower() for c in cats]

    entries = {k: v for k, v in manifest.data["skills"].items() if in_category(v)}
    catalog_skills = catalog.get("skills", [])
    # Catalog rows carry no per-skill categories; the catalog itself is scoped via
    # its top-level `category`. Only tag-filter when that is absent or different.
    cat_scope = str(catalog.get("category") or "").strip().lower()
    if args.category and cat_scope != args.category:
        filtered = [s for s in catalog_skills if in_category(s)]
        if filtered:
            catalog_skills = filtered
    counts = Counter(e.get("status", "unknown") for e in entries.values())
    total = len(catalog_skills)
    ok = counts.get("ok", 0)
    failures = Counter()
    licenses = Counter()
    skill_md = Counter()
    resource_skills = 0
    quiet = 0
    for entry in entries.values():
        if entry.get("resource_failures"):
            resource_skills += 1
        for f in entry.get("resource_failures", []) or []:
            failures[f.get("error", "?")] += 1
        if entry.get("license"):
            licenses[entry["license"]] += 1
        if entry.get("skill_md"):
            skill_md[entry["skill_md"]] += 1
        if entry.get("quiet"):
            quiet += 1
    report = {
        "category": args.category or "all",
        "catalog_file": str(catalog_path),
        "catalog_total": total,
        "manifest_entries": sum(counts.values()),
        "status": dict(counts),
        "coverage_pct": round(ok / total * 100, 2) if total else 0,
        "top_licenses": licenses.most_common(10),
        "resource_failures": failures.most_common(10),
        "skills_with_resource_failures": resource_skills,
        "skill_md_sources": dict(skill_md),
        "quiet": quiet,
        "missing": max(0, total - ok),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"category: {report['category']}")
        print(f"catalog: {total}")
        print(f"installed ok: {ok} ({report['coverage_pct']}%)")
        print(f"status: {dict(counts)}")
        print(f"missing: {report['missing']}")
        print(f"skill.md sources: {dict(skill_md)}")
        print(f"skills with resource failures: {resource_skills}")
        print(f"quiet: {quiet}")
        if failures:
            print(f"resource failure reasons: {failures.most_common(5)}")
        if licenses:
            print(f"top licenses: {licenses.most_common(5)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
