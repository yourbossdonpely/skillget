import json
import pathlib
import requests

REPO = "anthropics/skills"
SKILL = "skills/skill-creator"
DEST = pathlib.Path.home() / ".agents" / "skills" / "anthropic-skill-creator"

FILES = [
    "LICENSE.txt",
    "SKILL.md",
    "agents/analyzer.md",
    "agents/comparator.md",
    "agents/grader.md",
    "assets/eval_review.html",
    "eval-viewer/generate_review.py",
    "eval-viewer/viewer.html",
    "references/schemas.md",
    "scripts/__init__.py",
    "scripts/aggregate_benchmark.py",
    "scripts/generate_report.py",
    "scripts/improve_description.py",
    "scripts/package_skill.py",
    "scripts/quick_validate.py",
    "scripts/run_eval.py",
    "scripts/run_loop.py",
    "scripts/utils.py",
]


def main() -> int:
    ok = 0
    for rel in FILES:
        url = f"https://raw.githubusercontent.com/{REPO}/main/{SKILL}/{rel}"
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            print("FAIL", r.status_code, rel)
            continue
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        ok += 1
    print(f"WROTE {ok}/{len(FILES)} files -> {DEST}")
    (DEST / ".skillget.json").write_text(json.dumps({
        "slug": "anthropic-skill-creator",
        "name": "skill-creator",
        "source": f"https://github.com/{REPO}/tree/main/{SKILL}",
        "status": "ok",
    }, indent=2), encoding="utf-8")
    md = DEST / "SKILL.md"
    print("SKILL.md:", md.exists(), md.stat().st_size if md.exists() else 0, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
