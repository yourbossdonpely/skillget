"""Dump full skill detail JSON."""
import json
import re
import sys
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"}


def next_data(html_text):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_text, re.S)
    return json.loads(m.group(1)) if m else None


url = sys.argv[1]
r = requests.get(url, headers=HEADERS, timeout=60)
d = next_data(r.text)
skill = d["props"]["pageProps"]["json"]["skill"]
print(json.dumps(skill, indent=2, ensure_ascii=False))
