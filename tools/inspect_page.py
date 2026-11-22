"""Inspect typingmind skills listing/detail page structure."""
import json
import re
import sys
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}


def next_data(html_text):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_text, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.typingmind.com/skills?category=devops"
    r = requests.get(url, headers=HEADERS, timeout=60)
    print("STATUS", r.status_code, "LEN", len(r.text), "FINAL", r.url)
    d = next_data(r.text)
    if not d:
        print("NO NEXT_DATA")
        return
    print("PAGE", d.get("page"), "QUERY", d.get("query"), "BUILD", d.get("buildId"))
    pp = d.get("props", {}).get("pageProps", {})
    print("PAGEPROPS KEYS", list(pp.keys()))
    for k, v in pp.items():
        if isinstance(v, list):
            print(k, "list len", len(v))
            if v:
                print(" sample:", json.dumps(v[0])[:500])
        elif isinstance(v, dict):
            print(k, "dict keys", list(v.keys())[:30])
            for kk, vv in v.items():
                if isinstance(vv, list):
                    print("   ", kk, "len", len(vv), "sample", json.dumps(vv[0])[:300] if vv else None)
                else:
                    print("   ", kk, "=", str(vv)[:200])
        else:
            print(k, "=", v)
    # also dump raw html length and look for github links
    gh = sorted(set(re.findall(r'https://github\.com/[^"\'\s<>]+', r.text)))
    print("GITHUB LINKS IN LIST PAGE:", len(gh))
    for g in gh[:10]:
        print("  ", g)


if __name__ == "__main__":
    main()
