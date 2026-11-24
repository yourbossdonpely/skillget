"""Build a discovery index for an installed skill library.

With thousands of skills, injecting every description into a prompt is impossible.
The index gives an agent (or a human) one greppable file plus a machine-readable
JSON catalogue, while the skills themselves stay loadable by ID.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
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


def body_summary(path: Path, max_lines: int = 40) -> tuple[str, str]:
    """For SKILL.md files with no frontmatter: first heading, first prose line."""
    heading, summary = "", ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                max_lines -= 1
                if max_lines <= 0:
                    break
                text = line.strip().lstrip("\ufeff")
                if not text or text in {"---", "***"}:
                    continue
                if text.startswith("#"):
                    if not heading:
                        heading = text.lstrip("#").strip()
                    elif heading and summary:
                        break
                    continue
                if heading or not summary:
                    summary = text
                    if heading:
                        break
    except OSError:
        pass
    return heading, summary


def one_line(value: object, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text.replace("|", "\\|")


GITHUB_RE = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", re.I)
CARD_LICENSE_RE = re.compile(r"^#*\s*License/Terms of Use:\s*$", re.I | re.M)
LICENSE_HINT_RE = re.compile(
    r"\b(MIT-0|MIT|Apache(?: License)?(?:[- ]?2\.0)?|AGPL-3\.0|GPL-[23]\.0|LGPL-[23]\.0|"
    r"BSD-[23]-Clause|ISC|CC0-1\.0|CC-BY(?:-SA|-NC)?-?\d?\.?\d?|MPL-2\.0|Unlicense|0BSD|"
    r"EPL-2\.0|Proprietary)\b",
    re.I,
)
PLACEHOLDER_LICENSES = {"", "unknown", "n/a", "none", "-", "unspecified", "no license"}


def repo_key(*urls: object) -> str:
    """`owner/name` for the first GitHub URL, so repo-level facts can be shared."""
    for url in urls:
        match = GITHUB_RE.search(str(url or ""))
        if match:
            name = match.group(2).removesuffix(".git")
            return f"{match.group(1)}/{name}".lower()
    return ""


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def catalog_licenses(data_dir: Path) -> dict[str, str]:
    """slug -> license from every cached catalog (list payloads usually omit it)."""
    out: dict[str, str] = {}
    for path in sorted(data_dir.glob("catalog*.json")):
        for entry in read_json(path).get("skills", []):
            slug = entry.get("slug")
            value = str(entry.get("license") or "").strip()
            if slug and value:
                out.setdefault(slug, value)
    return out


def hub_metadata(dest: Path) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Hub install lock sources, and its cached catalogue entries keyed by skill name."""
    hub = dest / ".hub"
    sources: dict[str, str] = {}
    installed = read_json(hub / "lock.json").get("installed", {})
    if isinstance(installed, dict):
        for name, record in installed.items():
            if not isinstance(record, dict):
                continue
            meta = record.get("metadata") or {}
            scan = record.get("scan_provenance") or {}
            url = str(meta.get("source_url") or scan.get("source_url") or "").strip()
            if url:
                sources[name] = url
                sources[str(record.get("install_path") or name)] = url

    catalog: dict[str, list[dict]] = {}
    cache = hub / "index-cache"
    for path in sorted(cache.glob("*.json")) if cache.is_dir() else []:
        entries = read_json(path).get("skills")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name"):
                catalog.setdefault(str(entry["name"]).strip().lower(), []).append(entry)
    return sources, catalog


def usable_license(value: object) -> str:
    """A real license name; `Unknown`/`n/a` rows count as unknown, not as data."""
    text = str(value or "").strip()
    return "" if text.lower() in PLACEHOLDER_LICENSES else text


def desc_head(text: object, words: int = 16) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower()).split()[:words])


def hub_catalog_source(row: dict, catalog: dict[str, list[dict]]) -> str:
    """Repo URL from the hub catalogue, but only when name + folder identify one entry."""
    folder = str(row.get("id") or "").split("/")[-1].lower()
    cands = [
        entry
        for entry in catalog.get(str(row.get("name") or "").strip().lower(), [])
        if str(entry.get("identifier") or "").split("/")[-1].lower() == folder
        or str(entry.get("path") or "").split("/")[-1].lower() == folder
    ]
    if len(cands) > 1:
        head = desc_head(row.get("description"))
        cands = [entry for entry in cands if head and desc_head(entry.get("description")) == head]
    if len(cands) != 1:
        return ""
    repo = str(cands[0].get("repo") or "").strip().rstrip("/")
    return f"https://github.com/{repo}" if repo else ""


def skill_card_license(folder: Path) -> str:
    """Hub skills ship a `skill-card.md` with a `License/Terms of Use:` section."""
    try:
        text = (folder / "skill-card.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    match = CARD_LICENSE_RE.search(text)
    if not match:
        return ""
    for line in text[match.end():].splitlines():
        value = line.strip().lstrip("*`- ").strip()
        if not value or value.startswith("#"):
            continue
        # An empty card section runs straight into the next heading; only take a
        # line that actually names a license.
        if len(value) <= 40 and LICENSE_HINT_RE.search(value):
            return value
        return ""
    return ""


def backfill(rows: list[dict], dest: Path, data_dir: Path) -> Counter:
    """Fill missing license/source from provenance, catalog caches and hub metadata.

    Nothing is guessed per skill: a value comes from that skill's own record, or, for a
    license, from a unanimous license shared by every listed skill in its repo.
    """
    filled: Counter = Counter()
    licenses = catalog_licenses(data_dir)
    needs_hub = any(row["origin"] == "local" for row in rows)
    hub_sources, hub_catalog = hub_metadata(dest) if needs_hub else ({}, {})

    for row in rows:
        folder = dest / row["id"]
        provenance = read_json(folder / ".skillget.json")

        if str(row.get("license") or "").strip().lower() in PLACEHOLDER_LICENSES:
            if row.get("license"):
                filled["placeholder license cleared"] += 1
            row["license"] = ""


        if not row.get("license"):
            value = usable_license(provenance.get("license")) or usable_license(
                licenses.get(row.get("slug") or "", "")
            )
            if not value and row["origin"] == "local":
                value = usable_license(skill_card_license(folder))
            if value:
                row["license"] = value
                filled[f"{row['origin']} license"] += 1

        if not row.get("source"):
            folder_name = str(row["id"]).split("/")[-1]
            value = hub_sources.get(str(row["id"]) or "") or hub_sources.get(folder_name) or ""
            if not value and row["origin"] == "local":
                value = hub_catalog_source(row, hub_catalog)
            if not value:
                value = str(provenance.get("source") or provenance.get("github") or "").strip()
            if value:
                row["source"] = value
                filled[f"{row['origin']} source"] += 1

    # A repo licenses all of its skills the same way; only trust a unanimous value.
    by_repo: dict[str, set[str]] = {}
    for row in rows:
        key = repo_key(row.get("source"))
        if key and row.get("license"):
            by_repo.setdefault(key, set()).add(str(row["license"]))
    for row in rows:
        if row.get("license"):
            continue
        shared = by_repo.get(repo_key(row.get("source")))
        if shared and len(shared) == 1:
            row["license"] = next(iter(shared))
            filled[f"{row['origin']} license from repo"] += 1
    return filled


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

    # Skills installed by other managers (hub/bundled, hand-placed, category trees)
    # live under the same root but never appear in the skillget manifest.
    for skill_file in sorted(dest.rglob("SKILL.md")):
        rel = skill_file.parent.relative_to(dest).as_posix()
        parts = skill_file.parent.relative_to(dest).parts
        if any(p.startswith(".") or p == "node_modules" for p in parts):
            continue
        if rel in seen or not skill_file.is_file() or skill_file.stat().st_size == 0:
            continue
        seen.add(rel)
        fm = frontmatter(skill_file)
        heading, prose = ("", "") if fm else body_summary(skill_file)
        folders = skill_file.parent.parent.name if len(parts) > 1 else ""
        rows.append(
            {
                "id": rel,
                "slug": skill_file.parent.name,
                "name": fm.get("name") or heading or skill_file.parent.name,
                "description": fm.get("description") or prose or "",
                "source": fm.get("source") or fm.get("repository") or fm.get("homepage") or "",
                "license": fm.get("license") or "",
                "stars": 0,
                "categories": [folders] if folders else [],
                "origin": "local",
            }
        )
        if args.limit is not None and len(rows) >= args.limit:
            break

    for r in rows:
        r.setdefault("origin", "skillget")

    filled = backfill(rows, dest, ROOT / "data")

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
        f"{len(rows):,} skills installed under `{dest}` "
        f"({sum(1 for r in rows if r['origin'] == 'skillget'):,} `skillget`, "
        f"{sum(1 for r in rows if r['origin'] == 'local'):,} local).",
        "",
        "`skillget` writes `metadata.opencode/autoinvoke: false` into skills it installs in",
        "quiet mode (`crawl --quiet`), so those are not injected into every prompt; installs",
        "from older, non-quiet crawls keep their original frontmatter. The local, hub-managed",
        "skills are installed and configured by other tooling and may carry their own",
        "`autoinvoke` settings. Load any skill by ID with the `skill` tool, or search this",
        "file:",
        "",
        "```powershell",
        "Select-String -Path \"$env:USERPROFILE\\.agents\\skills-index.md\" -Pattern \"kubernetes\"",
        "```",
        "",
        "The same data is available as JSON in `skills-index.json`.",
        "",
        "| Skill | ID | Origin | Description | License | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        source = str(r["source"]).replace("|", "%7C")
        source_cell = f"[repo](<{source}>)" if source else ""
        lines.append(
            f"| {one_line(r['name'], 80)} | `{r['id']}` | {r['origin']} | {one_line(r['description'])} | "
            f"{one_line(r['license'], 40)} | {source_cell} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"indexed: {len(rows)}")
    if filled:
        print("backfilled: " + ", ".join(f"{k}={v:,}" for k, v in sorted(filled.items())))
    print(f"markdown: {md_path} ({md_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"json: {json_path} ({json_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
