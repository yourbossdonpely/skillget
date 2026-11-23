import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import installer  # noqa: E402

DATA = ROOT / "data"
DEST = Path.home() / ".agents" / "skills"
MANIFEST = DATA / "manifest.json"


def main() -> int:
    manifest = installer.Manifest(MANIFEST)
    before = len(manifest.data["skills"])
    for e in manifest.data["skills"].values():
        e["_had_entry"] = True

    rows = {}
    all_slugs = set()
    missing = []
    for p in sorted(DATA.glob("catalog-media-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("skills"):
            continue
        q = d.get("q") or p.stem
        ok = died = 0
        for s in d["skills"]:
            slug = s["slug"]
            e = manifest.get(slug)
            if not e or e.get("status") != "ok":
                continue
            folder = DEST / e.get("folder", "")
            if (folder / "SKILL.md").exists():
                ok += 1
                all_slugs.add(slug)
            else:
                died += 1
                missing.append((slug, e.get("folder")))
        rows[q] = (ok, died, len(d["skills"]))

    print(f"{'query':26s} {'installed':>9s} {'missing':>8s} {'hits':>6s}")
    for q, (ok, died, hits) in rows.items():
        print(f"{q:26s} {ok:9d} {died:8d} {hits:6d}")
    print(f"\nunique slugs installed from these searches: {len(all_slugs)}")

    # register the authoring skill
    slug = "anthropic-skill-creator"
    if not manifest.get(slug):
        manifest.mark(
            slug,
            name="skill-creator",
            folder="anthropic-skill-creator",
            status="ok",
            source="https://github.com/anthropics/skills/tree/main/skills/skill-creator",
        )
        manifest.save()
        print(f"registered {slug} in manifest")
    else:
        print(f"{slug} already in manifest -> {manifest.get(slug).get('status')}")

    print(f"manifest entries: {before} -> {len(manifest.data['skills'])}")
    if missing:
        print("MISSING SKILL.md:", missing[:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
