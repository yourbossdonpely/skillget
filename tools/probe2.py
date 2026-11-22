"""Validate detail payload, GitHub raw access, and sort options."""
import json
import re
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}
BASE = "https://www.typingmind.com"
BUILD = "build-TfctsWXpff2fKS"


def get(u):
    r = requests.get(u, headers=H, timeout=60)
    print("GET", u, "->", r.status_code, len(r.content))
    return r


# sort options
for sort in ["trending", "stars", "newest", "name", "downloads"]:
    r = get(f"{BASE}/_next/data/{BUILD}/skills.json?category=devops&page=1&sort={sort}")
    if r.status_code == 200:
        pp = r.json()["pageProps"]["json"]
        print("  sort", sort, "->", pp["initialSort"], "first", pp["skills"][0]["slug"])

# detail
r = get(f"{BASE}/_next/data/{BUILD}/skills/d4vinci-scrapling-official.json")
pp = r.json()["pageProps"]["json"]
s = pp["skill"]
print("detail keys:", list(s.keys()))
print("sourceURL:", s.get("sourceURL"))
print("owner/repo/path:", s.get("owner"), s.get("repo"), s.get("path"))
print("resources:", len(s.get("resources") or []))
print("body starts:", repr((s.get("bodyMarkdown") or "")[:120]))

# raw HEAD ref test
raw = f"https://raw.githubusercontent.com/{s['owner']}/{s['repo']}/HEAD/{s['path']}/SKILL.md"
r2 = requests.get(raw, headers=H, timeout=60)
print("RAW SKILL.md:", r2.status_code, len(r2.content), repr(r2.text[:120]))

# raw resource test
if s.get("resources"):
    rp = s["resources"][0]["path"]
    raw2 = f"https://raw.githubusercontent.com/{s['owner']}/{s['repo']}/HEAD/{s['path']}/{rp}"
    r3 = requests.get(raw2, headers=H, timeout=60)
    print("RAW resource:", rp, r3.status_code, len(r3.content))

# how many details lack sourceURL? sample 60
missing = 0
nores = 0
for sk in pp.get("relatedSkills", []):
    pass
print("sample detail body length:", len(s.get("bodyMarkdown") or ""))
