"""Install a TypingMind skill payload into ~/.agents/skills/<folder>/."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import github_fetch
import quiet as quiet_frontmatter

WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_manifest_lock = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_folder(name: str) -> str:
    name = (name or "skill").strip().lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-._")
    name = name[:100].rstrip(" .")
    if not name:
        name = "skill"
    if name.lower() in WINDOWS_RESERVED:
        name = f"skill-{name}"
    return name


def safe_skill_name(name: str, fallback: str) -> str:
    n = (name or fallback or "skill").strip().lower()
    n = re.sub(r"[^a-z0-9-]+", "-", n)
    n = re.sub(r"-{2,}", "-", n).strip("-")
    return (n or "skill")[:64]


def yaml_value(v: Any) -> str:
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(str(v), ensure_ascii=False)


def synthesize_skill_md(skill: dict[str, Any]) -> str:
    body = (skill.get("bodyMarkdown") or "").strip()
    if not body:
        body = f"# {skill.get('name') or skill.get('slug')}\n\n{skill.get('description') or ''}\n"
    name = safe_skill_name(skill.get("skillName") or "", skill.get("slug") or "skill")
    desc = (skill.get("description") or skill.get("shortDescription") or "").strip().replace("\n", " ")
    lines = ["---", f"name: {yaml_value(name)}", f"description: {yaml_value(desc)}"]
    if skill.get("license"):
        lines.append(f"license: {yaml_value(skill['license'])}")
    if skill.get("compatibility"):
        lines.append(f"compatibility: {yaml_value(skill['compatibility'])}")
    tools = skill.get("allowedTools") or []
    if tools:
        lines.append(f"allowed-tools: {yaml_value(tools)}")
    meta = skill.get("metadata") or {}
    if meta:
        lines.append(f"metadata: {yaml_value(meta)}")
    lines.extend(["---", "", body, ""])
    return "\n".join(lines)


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.data.setdefault("version", 1)
        self.data.setdefault("skills", {})
        self.data.setdefault("created_at", utcnow())

    def get(self, slug: str) -> dict[str, Any] | None:
        return self.data["skills"].get(slug)

    def mark(self, slug: str, **fields) -> dict[str, Any]:
        with _manifest_lock:
            entry = self.data["skills"].setdefault(slug, {})
            entry.update(fields)
            entry["updated_at"] = utcnow()
            return entry

    def save(self) -> None:
        self.data["updated_at"] = utcnow()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.data["skills"].values():
            status = entry.get("status", "unknown")
            out[status] = out.get(status, 0) + 1
        return out


def pick_folder(dest: Path, slug: str, manifest: Manifest, owned_folders: set[str]) -> str:
    """Choose a non-destructive folder name for a skill."""
    existing = manifest.get(slug)
    if existing and existing.get("folder"):
        return existing["folder"]
    base = safe_folder(slug)
    candidate = base
    n = 1
    while True:
        target = dest / candidate
        if not target.exists():
            return candidate
        if candidate in owned_folders or folder_belongs_to(target, slug):
            return candidate
        n += 1
        candidate = f"{base}-tm" if n == 2 else f"{base}-tm-{n - 1}"


def folder_belongs_to(path: Path, slug: str) -> bool:
    """True when a folder was installed by skillget for this slug (crash recovery)."""
    meta = path / ".skillget.json"
    if not meta.exists():
        return False
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("slug") == slug
    except (OSError, ValueError):
        return False


def install_skill(
    skill: dict[str, Any],
    dest: Path,
    *,
    folder: str,
    fetch_md: bool = True,
    fetch_files: bool = True,
    resource_workers: int = 4,
    quiet: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    slug = skill.get("slug") or ""
    name = skill.get("name") or slug
    src = github_fetch.parse_source(skill)
    source = skill.get("sourceURL") or (f"https://github.com/{src[0]}/{src[1]}" if src else "")
    result: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "folder": folder,
        "source": source,
        "license": skill.get("license") or "",
        "categories": skill.get("categories") or [],
        "resource_failures": [],
        "skill_md": "generated",
        "files": 0,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result

    dest.mkdir(parents=True, exist_ok=True)
    tmp_root = dest / ".skillget-tmp"
    tmp_root.mkdir(exist_ok=True)
    tmp = tmp_root / f"{folder}-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()

    try:
        md_text = None
        md_error = None
        if fetch_md:
            md_text, md_error = github_fetch.fetch_skill_md(skill)
        if md_text:
            result["skill_md"] = "raw"
        else:
            md_text = synthesize_skill_md(skill)
            result["skill_md"] = "generated"
            if md_error:
                result["skill_md_error"] = md_error
        if not md_text.strip():
            raise RuntimeError("empty SKILL.md")
        if quiet:
            md_text, quiet_status = quiet_frontmatter.ensure_quiet(
                md_text, name, skill.get("description") or ""
            )
            result["quiet"] = quiet_status not in {"already", "unparsed"}
        (tmp / "SKILL.md").write_text(md_text, encoding="utf-8")
        result["files"] += 1

        if fetch_files and skill.get("resources"):
            written, failures = github_fetch.fetch_resources(
                skill, tmp, workers=resource_workers
            )
            result["files"] += len(written)
            result["resource_failures"] = [{"path": p, "error": e} for p, e in failures]

        provenance = {
            "slug": slug,
            "name": name,
            "source": source,
            "github": skill.get("githubUrl") or "",
            "license": skill.get("license") or "",
            "categories": skill.get("categories") or [],
            "installed_at": utcnow(),
            "tool": "skillget",
            "tool_version": "1.0.0",
            "skill_md": result["skill_md"],
            "quiet": result.get("quiet", False),
            "resources_failed": result["resource_failures"],
        }
        (tmp / ".skillget.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        result["files"] += 1

        target = dest / folder
        if target.exists():
            if folder_belongs_to(target, slug):
                # Our own previous (possibly partial) install for this slug:
                # replace it in place. Windows cannot rename a directory over an
                # existing directory, so clear it first.
                shutil.rmtree(target, ignore_errors=True)
            else:
                # A folder we do not own appeared here (e.g. a user skill or a
                # concurrent writer). Never clobber it; pick a suffixed name.
                base = folder
                n = 1
                while target.exists():
                    n += 1
                    folder = f"{base}-tm" if n == 2 else f"{base}-tm-{n - 1}"
                    target = dest / folder
                result["folder"] = folder
        try:
            tmp.rename(target)
        except FileExistsError:
            # Directory appeared between the check and the rename. Fall back to a
            # fresh suffixed folder rather than failing the whole skill.
            base = folder
            n = 1
            while True:
                if not target.exists():
                    break
                n += 1
                folder = f"{base}-tm" if n == 2 else f"{base}-tm-{n - 1}"
                target = dest / folder
            result["folder"] = folder
            tmp.rename(target)

        result["status"] = "ok"
        result["path"] = str(target)
        return result
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
