"""TypingMind skills catalog + detail API client.

The site is a Next.js app. Its page-data endpoints expose the same JSON that the
UI renders, which lets us enumerate the catalog without browser automation.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import random
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

BASE = "https://www.typingmind.com"
FALLBACK_BUILD = "build-TfctsWXpff2fKS"
PAGE_SIZE = 51
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"})
        _local.session = s
    return s


def request(url: str, *, tries: int = 4, timeout: int = 45, **kwargs) -> requests.Response | None:
    """GET with bounded exponential backoff. Returns the last response or None."""
    last: requests.Response | None = None
    for attempt in range(tries):
        try:
            r = session().get(url, timeout=timeout, **kwargs)
            last = r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep((2**attempt) + random.random())
                continue
            return r
        except requests.RequestException:
            time.sleep((2**attempt) + random.random())
    return last


def discover_build_id() -> str:
    r = request(f"{BASE}/skills?category=devops")
    if r is not None and r.status_code == 200:
        m = re.search(r'"buildId":"([^"]+)"', r.text)
        if m:
            return m.group(1)
    return FALLBACK_BUILD


@dataclass
class CatalogSkill:
    id: str
    slug: str
    name: str
    description: str
    owner: str
    stars: int
    resources_count: int
    is_popular: bool = False

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "CatalogSkill":
        return cls(
            id=str(d.get("id", "")),
            slug=d.get("slug", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            owner=d.get("owner", ""),
            stars=int(d.get("stars") or 0),
            resources_count=int(d.get("resourcesCount") or 0),
            is_popular=bool(d.get("isPopular")),
        )


def fetch_catalog_page(category: str, page: int, sort: str, build: str) -> tuple[int, list[dict], int]:
    url = f"{BASE}/_next/data/{build}/skills.json"
    last_err = "unknown"
    for attempt in range(4):
        r = request(url, params={"category": category, "page": page, "sort": sort})
        if r is None:
            last_err = "no response"
        elif r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
        else:
            try:
                data = r.json()
                pp = (data.get("props") or data)["pageProps"]["json"]
                return int(pp.get("initialPage") or page), list(pp.get("skills") or []), int(pp.get("totalCount") or 0)
            except (ValueError, KeyError, TypeError):
                last_err = f"unexpected payload: {r.text[:160]!r}"
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"catalog page {page} failed: {last_err}")


def fetch_catalog(
    category: str,
    *,
    sort: str = "stars",
    workers: int = 8,
    build: str | None = None,
    max_pages: int | None = None,
    progress=None,
) -> tuple[list[CatalogSkill], int]:
    """Fetch every catalog page and return (deduped skills, reported total)."""
    build = build or discover_build_id()
    _, first, total = fetch_catalog_page(category, 1, sort, build)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if max_pages:
        pages = min(pages, max_pages)

    def one(p: int):
        for attempt in range(3):
            try:
                return fetch_catalog_page(category, p, sort, build)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    rows: list[dict] = list(first)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(one, p): p for p in range(2, pages + 1)}
        for i, fut in enumerate(cf.as_completed(futures), 2):
            _, items, _ = fut.result()
            rows.extend(items)
            if progress:
                progress(i, pages, len(rows))

    seen: set[str] = set()
    out: list[CatalogSkill] = []
    for row in rows:
        slug = row.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(CatalogSkill.from_json(row))
    return out, total


def fetch_page_props(
    category: str,
    *,
    page: int = 1,
    sort: str = "stars",
    build: str,
    **extra: Any,
) -> dict[str, Any]:
    """Return the full ``pageProps.json`` for one list page (includes filters)."""
    url = f"{BASE}/_next/data/{build}/skills.json"
    params = {"category": category, "page": page, "sort": sort, **extra}
    r = request(url, params=params)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"page props failed: {r.status_code if r is not None else 'no response'}")
    data = r.json()
    return (data.get("props") or data)["pageProps"]["json"]


def fetch_catalog_by_author(
    category: str,
    *,
    sort: str = "stars",
    workers: int = 10,
    build: str | None = None,
    progress=None,
) -> tuple[list[CatalogSkill], int]:
    """Enumerate a category the site will not page past 200 for.

    The list endpoint clamps every ordering at page 200 (~10.2k rows), so a large
    category is unreachable by ``page`` alone. The ``author`` filter is
    category-scoped and each author has few skills, so iterating authors covers
    the full category.
    """
    build = build or discover_build_id()
    first = fetch_page_props(category, sort=sort, build=build)
    total = int(first.get("totalCount") or 0)
    authors = [a["id"] for a in (first.get("authorOptions") or []) if a.get("id")]

    def author_rows(author: str) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while True:
            pp = fetch_page_props(category, page=page, sort=sort, build=build, author=author)
            items = pp.get("skills") or []
            rows.extend(items)
            count = int(pp.get("totalCount") or 0)
            pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
            if page >= pages or not items:
                break
            page += 1
        return rows

    seen: set[str] = set()
    out: list[CatalogSkill] = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(author_rows, a): a for a in authors}
        for fut in cf.as_completed(futures):
            done += 1
            try:
                rows = fut.result()
            except Exception:
                rows = []
            for row in rows:
                slug = row.get("slug")
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                out.append(CatalogSkill.from_json(row))
            if progress and done % 200 == 0:
                progress(done, len(authors), len(out))
    return out, total


def fetch_detail(slug: str, build: str) -> dict[str, Any]:
    url = f"{BASE}/_next/data/{build}/skills/{slug}.json"
    last_err = "unknown"
    for attempt in range(3):
        r = request(url, tries=3)
        if r is None:
            last_err = "no response"
        elif r.status_code == 404:
            raise LookupError("detail 404")
        elif r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
        else:
            try:
                data = r.json()
                return (data.get("props") or data)["pageProps"]["json"]["skill"]
            except (ValueError, KeyError, TypeError):
                last_err = f"unexpected payload: {r.text[:160]!r}"
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last_err)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
