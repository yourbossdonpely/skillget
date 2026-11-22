"""Benchmark concurrent detail endpoint latency / rate limits."""
import concurrent.futures as cf
import time
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}
BASE = "https://www.typingmind.com/_next/data/build-TfctsWXpff2fKS"
slugs = [
    "d4vinci-scrapling-official", "vercel-labs-agentcore", "mukul975-analyzing-ransomware-payment-wallets",
    "davila7-autogpt-agents", "donchitos-adopt", "kubesphere-frontend-forge-fe-operations",
    "prowler-cloud-framework-compliance-triage", "amir20-add-app-icon", "orchestra-research-langchain",
    "elie222-changelog", "bigbodycobain-shadowbroker", "agents365-ai-drawio-skill",
    "xerrors-chat-widgets", "trailofbits-ossfuzz", "modelengine-group-nexent-daily-test",
    "gosom-google-maps-scraper", "dammyjay93-interface-design", "jgraph-drawio",
    "epicenterhq-abstraction", "xingkongliang-manage-skills",
]


def one(slug):
    t = time.time()
    r = requests.get(f"{BASE}/skills/{slug}.json", headers=H, timeout=30)
    return slug, r.status_code, len(r.content), time.time() - t


t0 = time.time()
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    res = list(ex.map(one, slugs * 2))
print("total", round(time.time() - t0, 2), "n", len(res))
print("avg", round(sum(x[3] for x in res) / len(res), 3), "max", round(max(x[3] for x in res), 3))
from collections import Counter
print("status", Counter(x[1] for x in res))
print("slowest", sorted(res, key=lambda x: -x[3])[:5])
