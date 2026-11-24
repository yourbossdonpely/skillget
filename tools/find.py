"""Search skills-index.json with ranked term matching.

The index is tens of megabytes of JSON; loading it into an agent prompt is not an
option. This reads the file once, scores every record against the query terms and
prints only the best matches, so a 46k-skill library stays searchable from a shell.

    python tools/find.py stick figure
    python tools/find.py --origin local --prefix apple
    python tools/find.py elevenlabs --limit 5 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_INDEX = Path.home() / ".agents" / "skills-index.json"

# Field weights for a single term hit. Name matches say the most about a skill.
WEIGHTS = {"name": 6, "id": 4, "categories": 2, "description": 2}
PHRASE_BONUS = {"name": 10, "description": 5}
# Dropped when the query has other words, so "text to speech" ranks on text/speech.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "my", "of", "on", "or", "that", "the", "this", "to", "with", "you",
}


def terms_of(query: str) -> list[str]:
    words = [t for t in re.split(r"\s+", query.lower().strip()) if t]
    return [t for t in words if t not in STOPWORDS] or words


def term_patterns(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Terms match at a word start (so `voice` finds `voices`) but not inside a
    longer word (`figure` must not match `configure`)."""
    return [(t, re.compile(r"(?<![a-z0-9])" + re.escape(t))) for t in terms]


def normalise(text: object) -> str:
    """Lowercase and treat `-`/`_` as spaces, so `stick-figure` matches `stick figure`."""
    return str(text or "").lower().replace("-", " ").replace("_", " ")


def haystack(row: dict) -> dict[str, str]:
    return {
        "name": normalise(row.get("name")),
        "id": normalise(row.get("id")),
        "description": normalise(row.get("description")),
        "categories": normalise(" ".join(row.get("categories") or [])),
    }


def score(
    row: dict, patterns: list[tuple[str, re.Pattern[str]]], phrase: str
) -> tuple[int, int] | None:
    """(matched terms, score) or None when the row matches no term."""
    fields = haystack(row)
    matched = 0
    total = 0
    for term, pattern in patterns:
        best = 0
        for field, weight in WEIGHTS.items():
            if pattern.search(fields[field]):
                best = max(best, weight)
        if best:
            matched += 1
            total += best
    if not matched:
        return None
    if phrase:
        # Also credit the run-together form so `stick figure` finds `stickfigure`.
        variants = {phrase, phrase.replace(" ", "")}
        for field, bonus in PHRASE_BONUS.items():
            if any(v in fields[field] for v in variants):
                total += bonus
    return matched, total


def snippet(text: str, terms: list[str], width: int = 180) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= width:
        return text
    low = text.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=-1)
    if pos < 0:
        return text[: width - 1].rstrip() + "…"
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    return ("…" if start else "") + text[start:end].rstrip() + ("…" if end < len(text) else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ranked search over skills-index.json")
    ap.add_argument("query", nargs="*", help="terms; all are scored, any one may match")
    ap.add_argument("--origin", choices=["skillget", "local"], help="only this origin")
    ap.add_argument("--prefix", default="", help="only IDs starting with this prefix")
    ap.add_argument("--limit", type=int, default=20, help="results to show (0 = all)")
    ap.add_argument("--json", action="store_true", help="print matching records as JSON")
    ap.add_argument("--index", default=str(DEFAULT_INDEX), help="path to skills-index.json")
    args = ap.parse_args()

    index_path = Path(args.index).expanduser()
    if not index_path.is_file():
        print(f"no index at {index_path} — build one with: python tools/index.py", file=sys.stderr)
        return 2
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"could not read {index_path}: {exc}", file=sys.stderr)
        return 2

    rows = data.get("skills", []) if isinstance(data, dict) else data
    phrase = " ".join(normalise(q) for q in args.query).strip()
    terms = terms_of(phrase)
    patterns = term_patterns(terms)
    prefix = args.prefix.lower()

    hits: list[tuple[int, int, dict]] = []
    for row in rows:
        if args.origin and row.get("origin") != args.origin:
            continue
        if prefix and not str(row.get("id") or "").lower().startswith(prefix):
            continue
        if patterns:
            scored = score(row, patterns, phrase)
            if scored is None:
                continue
            matched, total = scored
        else:
            matched, total = 0, 0
        hits.append((matched, total, row))

    hits.sort(key=lambda h: (-h[1], -h[0], -int(h[2].get("stars") or 0), str(h[2].get("name") or "").lower()))
    total_matches = len(hits)
    if args.limit:
        hits = hits[: args.limit]

    if args.json:
        out = [dict(row, score=total, matched_terms=matched) for matched, total, row in hits]
        print(json.dumps({"query": phrase, "origin": args.origin, "prefix": args.prefix,
                          "matches": total_matches, "shown": len(out), "skills": out},
                         indent=2, ensure_ascii=False))
        return 0 if total_matches else 1

    if not hits:
        print("no matches")
        return 1

    for matched, total, row in hits:
        print(f"[{total:>3}] {row.get('id')}  ({row.get('origin')})")
        print(f"      {row.get('name')}")
        if terms:
            print(f"      {snippet(row.get('description'), terms)}")
        else:
            print(f"      {snippet(row.get('description'), [], 140)}")
        source = str(row.get("source") or "")
        if source:
            print(f"      {source}")
        print()

    shown = f"{len(hits)} of {total_matches:,}" if len(hits) < total_matches else f"{total_matches:,}"
    print(f"{shown} match{'es' if total_matches != 1 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
