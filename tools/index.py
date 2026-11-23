"""Build a discovery index for an installed skill library.

With thousands of skills, injecting every description into a prompt is impossible.
The index gives an agent (or a human) one greppable file plus a machine-readable
JSON catalogue, while the skills themselves stay loadable by ID.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import installer  # noqa: E402
import tm_catalog  # noqa: E402


def frontmatter(path: Path, max_lines: int = 600) -> dict[str, str]:
    """Read simple top-level scalar keys from a SKILL.md YAML (or JSON) frontmatter block.

    Reads line by line until the closing `---` so large frontmatter blocks (some skills
    carry multi-kilobyte metadata) are parsed in full without reading the whole file.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            if fh.readline().lstrip("\ufeff").strip() != "---":
                return {}
            lines: list[str] = []
            for _ in range(max_lines):
                line = fh.readline()
                if not line:
                    break
                if line.rstrip("\r\n").strip() == "---":
                    break
                lines.append(line)
    except OSError:
        return {}
    block = "\n".join(lines).strip()
    if block.startswith("{"):
        try:
            data, _ = json.JSONDecoder().raw_decode(block)
        except ValueError:
            data = {}
        if isinstance(data, dict):
            return {
                str(k): " ".join(str(v).split())
                for k, v in data.items()
                if isinstance(v, (str, int, float))
            }
    out: dict[str, str] = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line[:1].isspace() and key:
            out[key] = f"{out[key]} {line.strip()}".strip()
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().strip('"').strip("'")
            value = value.strip()
            if value in {"|", "|-", "|+", ">", ">-", ">+"}:
                value = ""
            out[key] = value.strip('"').strip("'")
    return out


def one_line(value: object, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text.replace("|", "\\|")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build skills-index.md and skills-index.json")
    ap.add_argument("--dest", default=str(Path.home() / ".agents" / "skills"))
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    ap.add_argument("--catalog", default=str(ROOT / "data" / "catalog.json"))
    ap.add_argument("--out-dir", default=str(Path.home() / ".agents"))
    ap.add_argument("--limit", type=int, default=None, help="only index the first N folders")
    args = ap.parse_args()

    dest = Path(args.dest).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    catalog = tm_catalog.load_json(Path(args.catalog), {}) or {}
    manifest = installer.Manifest(Path(args.manifest))
    by_slug = {s.get("slug"): s for s in catalog.get("skills", [])}

    rows: list[dict] = []
    seen: set[str] = set()
    for slug, entry in manifest.data["skills"].items():
        if entry.get("status") != "ok" or not entry.get("folder"):
            continue
        folder = entry["folder"]
        if folder in seen:
            continue
        skill_file = dest / folder / "SKILL.md"
        if not skill_file.is_file():
            continue
        seen.add(folder)
        cat = by_slug.get(slug, {})
        fm = frontmatter(skill_file)
        rows.append(
            {
                "id": folder,
                "slug": slug,
                "name": entry.get("name") or cat.get("name") or fm.get("name") or folder,
                "description": cat.get("description") or fm.get("description") or "",
                "source": entry.get("source") or cat.get("sourceURL") or "",
                "license": entry.get("license") or fm.get("license") or "",
                "stars": cat.get("stars") or 0,
                "categories": entry.get("categories") or cat.get("categories") or [],
            }
        )
        if args.limit is not None and len(rows) >= args.limit:
            break

    rows.sort(key=lambda r: (-int(r["stars"] or 0), r["name"].lower()))
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "skills-index.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_by": "skillget",
                "count": len(rows),
                "dest": str(dest),
                "skills": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / "skills-index.md"
    lines = [
        "# Installed skills index",
        "",
        f"{len(rows):,} skills installed under `{dest}`.",
        "",
        "Every skill is installed with `metadata.opencode/autoinvoke: false`, so the list is",
        "not injected into every prompt. Load one by ID with the `skill` tool, or search this",
        "file:",
        "",
        "```powershell",
        "Select-String -Path \"$env:USERPROFILE\\.agents\\skills-index.md\" -Pattern \"kubernetes\"",
        "```",
        "",
        "The same data is available as JSON in `skills-index.json`.",
        "",
        "| Skill | ID | Description | License | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        source = str(r["source"]).replace("|", "%7C")
        source_cell = f"[repo](<{source}>)" if source else ""
        lines.append(
            f"| {one_line(r['name'], 80)} | `{r['id']}` | {one_line(r['description'])} | "
            f"{one_line(r['license'], 40)} | {source_cell} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"indexed: {len(rows)}")
    print(f"markdown: {md_path} ({md_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"json: {json_path} ({json_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
