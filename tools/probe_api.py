"""Probe pagination and Next.js data endpoints."""
import json
import re
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}
BASE = "https://www.typingmind.com"


def next_data(t):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', t, re.S)
    return json.loads(m.group(1)) if m else None


def show(label, r):
    print(f"--- {label}: HTTP {r.status_code} bytes={len(r.content)} type={r.headers.get('content-type')}")
    try:
        d = json.loads(r.text)
        print("json top keys:", list(d.keys())[:15])
        pp = d.get("props", {}).get("pageProps", {}).get("json") or d.get("pageProps", {}).get("json")
        if pp:
            print("  page:", pp.get("initialPage"), "skills:", len(pp.get("skills", [])), "total:", pp.get("totalCount"))
            if pp.get("skills"):
                print("  first:", pp["skills"][0]["slug"])
        return d
    except Exception as e:
        print("not json:", e)
        return None


build = "build-TfctsWXpff2fKS"
urls = [
    ("html page2", f"{BASE}/skills?category=devops&page=2"),
    ("next data list", f"{BASE}/_next/data/{build}/skills.json?category=devops&page=2"),
    ("next data list no page", f"{BASE}/_next/data/{build}/skills.json?category=devops"),
    ("next data detail", f"{BASE}/_next/data/{build}/skills/d4vinci-scrapling-official.json"),
]
for label, u in urls:
    try:
        r = requests.get(u, headers=H, timeout=60)
        show(label, r)
    except Exception as e:
        print(label, "ERR", e)

# page 2 html parse
r = requests.get(f"{BASE}/skills?category=devops&page=2", headers=H, timeout=60)
d = next_data(r.text)
pp = d["props"]["pageProps"]["json"]
print("HTML page2 initialPage", pp["initialPage"], "count", len(pp["skills"]), "first", pp["skills"][0]["slug"])
