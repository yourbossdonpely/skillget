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

try:  # optional: only the --repair verification needs it
    import yaml
except Exception:  # pragma: no cover - PyYAML is in requirements.txt
    yaml = None

FLAG = "opencode/autoinvoke"
DEFAULT_ROOT = Path.home() / "AppData" / "Local" / "Temp" / "opencode" / "skillget-staging"
FLAG_RE = re.compile(r"^\s*[\"']?" + re.escape(FLAG) + r"[\"']?\s*:\s*(.*)$")
META_RE = re.compile(r"^[\"']?metadata[\"']?\s*:\s*(.*)$")
DISABLE_RE = re.compile(r"^\s*[\"']?disable-model-invocation[\"']?\s*:\s*(.*)$")
# The flag wherever it sits, including inside an inline `metadata: { ... }` map.
FLAG_ANY_RE = re.compile(
    r"opencode/autoinvoke\s*:\s*[\"']?(true|false|yes|no|on|off|1|0)", re.I
)


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
        m = FLAG_ANY_RE.search(line)
        if m and not truthy(m.group(1)):
            return True
    return False


def dedupe_flags(fm: list[str]) -> tuple[list[str], int]:
    """Collapse repeated `opencode/autoinvoke: false` keys to one. Returns (lines, removed)."""
    out: list[str] = []
    seen = False
    removed = 0
    for line in fm:
        hits = list(FLAG_ANY_RE.finditer(line))
        if not hits:
            out.append(line)
            continue
        if seen:
            stripped = FLAG_ANY_RE.sub("", line).strip().lstrip(",").strip()
            if stripped in {"", ","}:
                removed += 1
                continue
        # Drop every occurrence after the first (with its separating comma).
        for match in reversed(hits[1:]):
            end = match.end()
            if line[end:end + 1] == ",":
                end += 1
            line = line[: match.start()] + line[end:]
            removed += 1
        line = re.sub(r",\s*,", ",", line).rstrip()
        if false_in(line):
            seen = True
        out.append(line)
    return out, removed


def false_in(line: str) -> bool:
    match = FLAG_ANY_RE.search(line)
    return bool(match) and not truthy(match.group(1))


def block_child_indent(fm: list[str], idx: int) -> str:
    """Indentation for a new child of the block at `idx`, matching its existing children."""
    parent = len(fm[idx]) - len(fm[idx].lstrip())
    for line in fm[idx + 1:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        return " " * (indent if indent > parent else parent + 2)
    return " " * (parent + 2)


def mark_flow(fm: list[str], child: int) -> tuple[list[str], str]:
    """Add the flag inside a flow mapping that opens on line `child`."""
    line = fm[child]
    stripped = line.lstrip()
    body = stripped[1:].lstrip()  # text after the opening brace
    lead = line[: len(line) - len(stripped)]
    if body == "}":
        fm[child] = f"{lead}{{{FLAG}: false}}"
    else:
        fm[child] = f"{lead}{{{FLAG}: false, {body}"
    return fm, "added"


def mark(fm: list[str]) -> tuple[list[str], str]:
    """Insert or replace the autoinvoke flag. Returns (lines, status)."""
    if already_quiet(fm):
        return fm, "already"

    for idx, line in enumerate(fm):
        m = FLAG_RE.match(line)
        if m:
            indent = line[: len(line) - len(line.lstrip())]
            key = line.split(":", 1)[0].strip()  # keep JSON-style quotes if present
            trailing = "," if line.rstrip().endswith(",") else ""
            new = f"{indent}{key}: false{trailing}"
            if new == line:
                return fm, "already"
            fm[idx] = new
            return fm, "updated"

    for idx, line in enumerate(fm):
        m = META_RE.match(line)
        if not m:
            continue
        if FLAG_ANY_RE.search(line):
            # Inline map that already names the flag: flip it instead of adding a key.
            new = FLAG_ANY_RE.sub(f"{FLAG}: false", line, count=1)
            if new == line:
                return fm, "already"
            fm[idx] = new
            return fm, "updated"
        value = m.group(1).strip()
        if value in {"", "null", "~"}:
            child = next((k for k in range(idx + 1, len(fm)) if fm[k].strip()), None)
            if child is not None and fm[child].lstrip().startswith("{"):
                # `metadata:` followed by a flow mapping on later lines: a block key
                # cannot precede it, so the flag has to go inside the braces.
                return mark_flow(fm, child)
            fm[idx] = "metadata:"
            fm.insert(idx + 1, f"{block_child_indent(fm, idx)}{FLAG}: false")
            return fm, "added"
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            if inner:
                fm[idx] = f"metadata: {{ {FLAG}: false, {inner} }}"
            else:
                fm[idx] = f"metadata: {{ {FLAG}: false }}"
            return fm, "added"
        if value.startswith("{"):
            # Flow mapping opened on the `metadata:` line and continued below.
            line = fm[idx]
            brace = line.index("{")
            rest = line[brace + 1:].strip()
            fm[idx] = f"{line[:brace + 1]} {FLAG}: false," + (f" {rest}" if rest else "")
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


def write_skill(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".skillget-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


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
    parsed = split_frontmatter(new_text)
    if yaml is not None and parsed and not yaml_ok(parsed[0]):
        # Never write frontmatter we cannot parse; report it instead.
        return "unverified"
    write_skill(path, new_text)
    meta["quiet"] = True
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def yaml_ok(fm: list[str]) -> bool:
    if yaml is None:
        return False
    try:
        data = yaml.safe_load("\n".join(fm))
    except Exception:
        return False
    return isinstance(data, dict)


def repair_json_frontmatter(path: Path, fm: list[str], body: str, nl: str, dry_run: bool) -> str:
    """Deal with a JSON frontmatter object that a YAML `metadata:` tail was appended to."""
    tail = list(fm)
    while tail and not tail[-1].strip():
        tail.pop()
    if len(tail) < 2 or not META_RE.match(tail[-2]) or not FLAG_RE.match(tail[-1]):
        return "unrepairable"
    new_fm = tail[:-2]
    for idx, line in enumerate(new_fm):
        if re.match(r'^\s*"metadata"\s*:\s*\{', line):
            indent = line[: len(line) - len(line.lstrip())] + "  "
            new_fm.insert(idx + 1, f'{indent}"opencode/autoinvoke": false,')
            break
    else:
        return "unrepairable"
    try:
        data = json.loads(nl.join(new_fm))
    except ValueError:
        return "unrepairable"
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
        return "unrepairable"
    if data["metadata"].get("opencode/autoinvoke") is not False:
        return "unrepairable"
    if not dry_run:
        write_skill(path, nl.join(["---", *new_fm, "---"]) + nl + body)
    return "would-repair" if dry_run else "repaired"


def repair(path: Path, dry_run: bool = False) -> str:
    """Undo a flag line that mis-indented frontmatter into invalid YAML.

    Drops the flag inserted right after `metadata:`, re-adds it with that block's own
    child indentation (or inside a flow mapping), and writes only when the result
    parses as a mapping. Files that were already invalid are reported, not rewritten.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    parsed = split_frontmatter(text)
    if parsed is None:
        return "no-frontmatter"
    if yaml is None:
        return "no-yaml-validator"
    fm, body, nl = parsed
    new_fm, removed = dedupe_flags(fm)
    if removed:
        if not yaml_ok(new_fm):
            return "unrepairable"
        if not dry_run:
            write_skill(path, nl.join(["---", *new_fm, "---"]) + nl + body)
        return "would-dedupe" if dry_run else "deduped"
    if yaml_ok(fm):
        return "ok"
    if fm and fm[0].lstrip().startswith("{"):
        return repair_json_frontmatter(path, fm, body, nl, dry_run)
    for idx, line in enumerate(fm):
        meta = META_RE.match(line)
        if not meta or meta.group(1).strip():
            continue
        child = next((k for k in range(idx + 1, len(fm)) if fm[k].strip()), None)
        if child is None or not FLAG_RE.match(fm[child]):
            continue
        original = list(fm)
        del fm[child]
        new_fm, status = mark(fm)
        if status in {"already", "unparsed"} or not yaml_ok(new_fm):
            fm[:] = original
            return "unrepairable"
        if not dry_run:
            write_skill(path, nl.join(["---", *new_fm, "---"]) + nl + body)
        return "would-repair" if dry_run else "repaired"
    return "unrepairable"


def main() -> int:
    ap = argparse.ArgumentParser(description="Add metadata.opencode/autoinvoke: false to installed skills")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--manifest", default=None,
                    help="only touch folders recorded as ok in this manifest (leaves other managers' skills alone)")
    ap.add_argument("--repair", action="store_true",
                    help="fix frontmatter broken by a mis-indented flag; only writes when it parses")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    if args.manifest:
        try:
            data = json.loads(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"could not read manifest {args.manifest}: {exc}", file=sys.stderr)
            return 2
        entries = data.get("skills", {}) if isinstance(data, dict) else {}
        wanted = {
            str(entry.get("folder"))
            for entry in entries.values()
            if isinstance(entry, dict) and entry.get("status") == "ok" and entry.get("folder")
        }
        folders = [root / name for name in sorted(wanted) if (root / name).is_dir()]
        counts["folder-missing"] = len(wanted) - len(folders)
        print(f"manifest: {args.manifest} ({len(wanted):,} ok folders)")
    else:
        folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    for i, folder in enumerate(folders):
        if args.limit is not None and i >= args.limit:
            break
        skill = folder / "SKILL.md"
        if not skill.is_file():
            counts["missing-skill-md"] = counts.get("missing-skill-md", 0) + 1
            continue
        if args.repair:
            status = repair(skill, args.dry_run)
        elif args.dry_run:
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
        print(f"  {status}: {counts[status]}  e.g. {', '.join(examples.get(status, []))}")
    failing = ("unparsed", "no-frontmatter", "unrepairable", "no-yaml-validator")
    return 1 if any(counts.get(key) for key in failing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
