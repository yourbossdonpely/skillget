import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import github_fetch

m = json.load(open(Path(__file__).resolve().parent.parent / "data" / "manifest-staging.json", encoding="utf-8"))
rows = [(k, v) for k, v in m["skills"].items() if v.get("resource_failures")]
print("skills with failures:", len(rows))
for slug, e in rows[:8]:
    print("\n===", slug, "|", e.get("source"))
    print("folder:", e.get("folder"), "skill_md:", e.get("skill_md"))
    for f in e["resource_failures"][:6]:
        print("  ", f)
