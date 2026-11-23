import json
from pathlib import Path

DATA = Path(r"C:\dev\appbuilddev\skillget\data")
DEST = Path.home() / ".agents" / "skills"


def desc(md: Path) -> str:
    txt = md.read_text(encoding="utf-8", errors="replace")
    out, grab = [], False
    for line in txt.splitlines():
        if line.strip() == "---":
            if grab:
                break
            grab = True
            continue
        if grab:
            out.append(line.strip())
    d = " ".join(out)
    d = d.split("description:", 1)[-1].strip()
    return " ".join(d.split())[:110]


def main() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["skills"]
    for q in ("blender", "capcut", "blender render"):
        cat = json.loads((DATA / f"catalog-media-{q.replace(' ', '-')}.json").read_text(encoding="utf-8"))
        print(f"\n### {q} ({len(cat['skills'])} hits)")
        for s in cat["skills"]:
            e = manifest.get(s["slug"]) or {}
            folder = DEST / (e.get("folder") or "")
            md = folder / "SKILL.md"
            files = sum(1 for _ in folder.rglob("*") if _.is_file()) if folder.exists() else 0
            kb = md.stat().st_size // 1024 if md.exists() else 0
            mark = "ok " if md.exists() else "MISS"
            print(f"  {mark} {s['slug'][:42]:42s} {kb:4d}KB {files:3d}f  {desc(md) if md.exists() else ''}")


if __name__ == "__main__":
    main()
