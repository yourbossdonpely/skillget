"""GitHub raw download helpers for skill packages."""
from __future__ import annotations

import concurrent.futures as cf
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from tm_catalog import request

RAW = "https://raw.githubusercontent.com"

WINDOWS_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_part(name: str) -> str:
    """Make one path segment writable on Windows (and anywhere else)."""
    out = WINDOWS_ILLEGAL.sub("_", name.replace("\\", "_"))
    out = out.rstrip(" .") or "_"
    stem = out.split(".")[0].lower()
    if stem in WINDOWS_RESERVED:
        out = f"_{out}"
    # Windows caps a single segment at 255 chars; keep extensions readable.
    if len(out) > 120:
        base, dot, ext = out.rpartition(".")
        out = (base[: 120 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else out[:120]
    return out


def clean_relpath(p: str) -> Path | None:
    """Convert a repository-relative path to a safe local Path (no traversal)."""
    if not p:
        return None
    p = p.replace("\\", "/").strip()
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return None
    raw_parts = p.split("/")
    if any(part == ".." for part in raw_parts):
        return None
    parts = [x for x in raw_parts if x not in ("", ".")]
    if not parts:
        return None
    # Keep folder names valid on Windows too: upstream repos may ship files such
    # as `Sources/iPhone/<Name>App.swift`, which NTFS refuses to create.
    return Path(*(safe_part(x) for x in parts))


def parse_source(skill: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """Return (owner, repo, branch, path) from detail metadata."""
    owner = (skill.get("owner") or "").strip()
    repo = (skill.get("repo") or "").strip()
    branch = (skill.get("defaultBranch") or "").strip()
    path = (skill.get("path") or "").strip().strip("/")
    source = (skill.get("sourceURL") or "").strip()
    if source:
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/(?:tree|blob)/([^/]+)(?:/(.*))?)?", source)
        if m:
            owner = owner or m.group(1)
            repo = repo or m.group(2)
            branch = branch or (m.group(3) or "")
            path = path or (m.group(4) or "").strip("/")
    if not owner or not repo:
        return None
    return owner, repo, branch or "HEAD", path


def raw_url(owner: str, repo: str, branch: str, path: str) -> str:
    encoded = quote(path, safe="/")
    return f"{RAW}/{owner}/{repo}/{quote(branch, safe='')}/{encoded}"


def get_bytes(url: str, *, max_bytes: int = 50 * 1024 * 1024, timeout: int = 60):
    """Download bytes. Returns (status, content, content_type) or (status, None, None)."""
    r = request(url, tries=3, timeout=timeout, stream=True)
    if r is None:
        return 0, None, None
    if r.status_code != 200:
        return r.status_code, None, r.headers.get("content-type")
    cl = r.headers.get("content-length")
    if cl and int(cl) > max_bytes:
        return 413, None, r.headers.get("content-type")
    buf = bytearray()
    try:
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf) > max_bytes:
                return 413, None, r.headers.get("content-type")
    finally:
        r.close()
    return 200, bytes(buf), r.headers.get("content-type")


def fetch_skill_md(skill: dict[str, Any]) -> tuple[str | None, str | None]:
    """Fetch the canonical SKILL.md. Returns (text, error)."""
    src = parse_source(skill)
    if not src:
        return None, "no github source"
    owner, repo, branch, path = src
    candidates = []
    if path:
        candidates.append(f"{path}/SKILL.md")
        candidates.append(f"{path}/skill.md")
    candidates.append("SKILL.md")
    for rel in candidates:
        status, data, _ = get_bytes(raw_url(owner, repo, branch, rel), max_bytes=2 * 1024 * 1024)
        if status == 200 and data:
            return data.decode("utf-8", errors="replace"), None
    return None, "SKILL.md not found on raw.githubusercontent.com"


def fetch_resources(skill: dict[str, Any], dest: Path, *, workers: int = 4, max_bytes: int = 50 * 1024 * 1024):
    """Download all supporting files listed in the skill detail payload.

    Returns (written_paths, failures). Failures are (path, reason) tuples.
    """
    resources = skill.get("resources") or []
    src = parse_source(skill)
    if not resources or not src:
        return [], ([] if not resources else [("", "no github source")])
    owner, repo, branch, base = src
    written: list[str] = []
    failures: list[tuple[str, str]] = []
    lock = threading.Lock()

    def one(res: dict[str, Any]):
        rel_raw = str(res.get("path") or "")
        rel = clean_relpath(rel_raw)
        if rel is None:
            with lock:
                failures.append((rel_raw, "unsafe path"))
            return
        full = f"{base}/{rel.as_posix()}" if base else rel.as_posix()
        status, data, _ = get_bytes(raw_url(owner, repo, branch, full), max_bytes=max_bytes)
        if (status != 200 or data is None) and base:
            # Some payloads list paths relative to the repository root.
            status2, data2, _ = get_bytes(raw_url(owner, repo, branch, rel.as_posix()), max_bytes=max_bytes)
            if status2 == 200 and data2 is not None:
                status, data = status2, data2
        if status != 200 or data is None:
            with lock:
                failures.append((rel_raw, f"HTTP {status}"))
            return
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        with lock:
            written.append(rel.as_posix())

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, resources))
    return written, failures
