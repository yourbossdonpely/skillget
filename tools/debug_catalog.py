import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm_catalog as t

b = t.discover_build_id()
print("build", b)
r = t.request(f"{t.BASE}/_next/data/{b}/skills.json", params={"category": "devops", "page": 1, "sort": "stars"})
print("status", r.status_code, "ctype", r.headers.get("content-type"), "len", len(r.content))
print(r.text[:1000])
