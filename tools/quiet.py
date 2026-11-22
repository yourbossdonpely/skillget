"""Mark installed skills as non-autoinvoked.

OpenCode injects every skill that has a `description` into the system prompt unless
its frontmatter sets `metadata.opencode/autoinvoke: false` (or
`disable-model-invocation: true`). With 9,271 skills that list is far larger than any
context window. This tool adds the flag in place, leaving the skill fully loadable
through the `skill` tool by ID.

The edit is line-based so the rest of the original YAML (quoting, ordering, comments)
is preserved byte-for-byte.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

FLAG = "opencode/autoinvoke"
DEFAULT_ROOT = Path.home() / "AppData" / "Local" / "Temp" / "opencode" / "skillget-staging"
FLAG_RE = re.compile(r"^\s*[\"']?" + re.escape(FLAG) + r"[\"']?\s*:\s*(.*)$")
META_RE = re.compile(r"^[\"']?metadata[\"']?\s*:\s*(.*)$")
DISABLE_RE = re.compile(r"^\s*[\"']?disable-model-invocation[\"']?\s*:\s*(.*)$")


def split_frontmatter(text: str) -> tuple[list[str], str, str] | None:
    """Return (frontmatter_lines, body, newline) or None when there is no frontmatter."""
    if text.startswith("\ufeff"):
        text = text[1:]
    nl = "\r\n" if "\r\n" in text[:200] else "\n"
    lines = text.split(nl)
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], nl.join(lines[i + 1 :]), nl
    return None


def truthy(value: str) -> bool:
    return value.strip().strip("\"'").lower() in {"true", "yes", "on", "1"}


def already_quiet(fm: list[str]) -> bool:
    for line in fm:
        m = DISABLE_RE.match(line)
        if m and truthy(m.group(1)):
            return True
        m = FLAG_RE.match(line)
        if m and not truthy(m.group(1)):
            return True
    return False


def mark(fm: list[str]) -> tuple[list[str], str]:
    """Insert or replace the autoinvoke flag. Returns (lines, status)."""
    if already_quiet(fm):
        return fm, "already"

    for idx, line in enumerate(fm):
        m = FLAG_RE.match(line)
        if m:
            indent = line[: len(line) - len(line.lstrip())]
            fm[idx] = f"{indent}{FLAG}: false"
            return fm, "updated"

    for idx, line in enumerate(fm):
        m = META_RE.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value in {"", "null", "~"}:
            fm[idx] = "metadata:"
            fm.insert(idx + 1, f"  {FLAG}: false")
            return fm, "added"
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            if inner:
                fm[idx] = f"metadata: {{ {FLAG}: false, {inner} }}"
            else:
                fm[idx] = f"metadata: {{ {FLAG}: false }}"
            return fm, "added"
        # Unusual metadata value (list, scalar). Fall back to a second key, which
        # YAML would reject as a duplicate, so leave it alone and report.
        return fm, "unparsed"

    # No metadata key: append a block at the end of the frontmatter.
    fm.append("metadata:")
    fm.append(f"  {FLAG}: false")
    return fm, "added"


def ensure_quiet(text: str, name: str = "skill", description: str = "") -> tuple[str, str]:
    """Return (possibly edited text, status).

    `prepended` means the file had no frontmatter, so a minimal valid one was added.
    """
    parsed = split_frontmatter(text)
    if parsed is None:
        lines = ["---", f"name: {json.dumps(name or 'skill', ensure_ascii=False)}"]
        if description:
            lines.append(f"description: {json.dumps(description, ensure_ascii=False)}")
        lines += ["metadata:", f"  {FLAG}: false", "---", ""]
        return "\n".join(lines) + text, "prepended"
    fm, body, nl = parsed
    new_fm, status = mark(fm)
    if status in {"already", "unparsed"}:
        return text, status
    return nl.join(["---", *new_fm, "---"]) + nl + body, status


def process(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    meta_path = path.parent / ".skillget.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    new_text, status = ensure_quiet(text, meta.get("name") or path.parent.name)
    if status in {"already", "unparsed"}:
        return status
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".skillget-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    meta["quiet"] = True
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description="Add metadata.opencode/autoinvoke: false to installed skills")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    for i, folder in enumerate(folders):
        if args.limit is not None and i >= args.limit:
            break
        skill = folder / "SKILL.md"
        if not skill.is_file():
            counts["missing-skill-md"] = counts.get("missing-skill-md", 0) + 1
            continue
        if args.dry_run:
            text = skill.read_text(encoding="utf-8", errors="replace")
            _, status = ensure_quiet(text, folder.name)
        else:
            status = process(skill)
        counts[status] = counts.get(status, 0) + 1
        examples.setdefault(status, [])
        if len(examples[status]) < 5:
            examples[status].append(folder.name)

    print(f"root: {root}")
    print(f"folders: {len(folders)}")
    for status in sorted(counts):
        print(f"  {status}: {counts[status]}  e.g. {', '.join(examples[status])}")
    return 1 if counts.get("unparsed") or counts.get("no-frontmatter") else 0


if __name__ == "__main__":
    raise SystemExit(main())
