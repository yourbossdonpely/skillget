"""skillget CLI: harvest TypingMind skills into ~/.agents/skills."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import github_fetch  # noqa: E402
import installer  # noqa: E402
import tm_catalog  # noqa: E402

DATA = ROOT / "data"
LOGS = ROOT / "logs"
CATALOG_PATH = DATA / "catalog.json"
MANIFEST_PATH = DATA / "manifest.json"
DEFAULT_DEST = Path.home() / ".agents" / "skills"
_print_lock = threading.Lock()
_log_path: Path | None = None


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _print_lock:
        print(line, flush=True)
        if _log_path:
            with _log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def load_catalog(args) -> dict:
    if CATALOG_PATH.exists() and not args.refresh_catalog:
        data = tm_catalog.load_json(CATALOG_PATH, {})
        if data.get("category") == args.category and data.get("skills"):
            return data
    log(f"Fetching catalog for category={args.category} sort={args.sort} ...")
    build = tm_catalog.discover_build_id()
    log(f"buildId={build}")
    skills, total = tm_catalog.fetch_catalog(
        args.category,
        sort=args.sort,
        workers=args.catalog_workers,
        build=build,
        max_pages=args.max_pages,
        progress=lambda p, pages, n: log(f"catalog page {p}/{pages} ({n} rows)"),
    )
    if len(skills) < total - 2 and not args.max_pages:
        log(f"catalog has {len(skills)} unique of {total}; unioning with trending order")
        extra, _ = tm_catalog.fetch_catalog(
            args.category, sort="trending", workers=args.catalog_workers, build=build
        )
        seen = {s.slug for s in skills}
        skills.extend(s for s in extra if s.slug not in seen)
    data = {
        "category": args.category,
        "sort": args.sort,
        "build": build,
        "total": total,
        "fetched_at": installer.utcnow(),
        "skills": [s.__dict__ for s in skills],
    }
    tm_catalog.save_json(CATALOG_PATH, data)
    log(f"Catalog saved: {len(skills)} unique skills (site reports {total}) -> {CATALOG_PATH}")
    return data


def cmd_catalog(args) -> int:
    data = load_catalog(args)
    print(json.dumps({k: v for k, v in data.items() if k != "skills"}, indent=2))
    print(f"skills: {len(data['skills'])}")
    return 0


def process_one(skill: dict, folder: str, args) -> dict:
    slug = skill["slug"]
    try:
        detail = tm_catalog.fetch_detail(slug, args._build)
    except LookupError:
        return {"slug": slug, "name": skill.get("name", ""), "folder": folder, "status": "not_found",
                "error": "detail 404"}
    except Exception as e:
        return {"slug": slug, "name": skill.get("name", ""), "folder": folder, "status": "error",
                "error": f"detail: {type(e).__name__}: {e}"}
    if args.cache_details:
        tm_catalog.save_json(DATA / "details" / f"{slug}.json", detail)
    return installer.install_skill(
        detail,
        args._dest,
        folder=folder,
        fetch_md=not args.fast,
        fetch_files=not args.no_resources,
        resource_workers=args.resource_workers,
        quiet=args.quiet,
        dry_run=args.dry_run,
    )


def cmd_crawl(args) -> int:
    global _log_path
    LOGS.mkdir(parents=True, exist_ok=True)
    # A single crawl may own the destination. Concurrent crawls race on the same
    # folders and corrupt the manifest, so refuse to start a second one unless
    # the caller explicitly ignores the lock.
    lock_path = DATA / ".crawl.lock"
    if not args.ignore_lock:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            try:
                other = lock_path.read_text(encoding="utf-8").strip()
            except OSError:
                other = "?"
            print(f"another crawl holds {lock_path} (pid {other}); "
                  f"stop it or pass --ignore-lock", file=sys.stderr)
            return 2
    try:
        return _run_crawl(args)
    finally:
        if not args.ignore_lock:
            try:
                lock_path.unlink()
            except OSError:
                pass


def _run_crawl(args) -> int:
    global _log_path
    _log_path = LOGS / f"crawl-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    dest = Path(args.dest).expanduser().resolve()
    args._dest = dest
    data = load_catalog(args)
    args._build = args.build or data.get("build") or tm_catalog.discover_build_id()
    manifest = installer.Manifest(Path(args.manifest))

    catalog = data["skills"]
    by_slug = {s["slug"]: s for s in catalog}
    only = {x.strip() for x in (args.only or "").split(",") if x.strip()}
    if only:
        missing = only - set(by_slug)
        if missing:
            log(f"WARNING: unknown slugs: {', '.join(sorted(missing))}")
        todo = [by_slug[s] for s in only if s in by_slug]
    else:
        todo = catalog
    if args.retry_errors:
        todo = [s for s in todo if (manifest.get(s["slug"]) or {}).get("status") in ("error", "not_found", "partial")]
    elif not args.force:
        todo = [s for s in todo if (manifest.get(s["slug"]) or {}).get("status") not in ("ok", "dry_run")]
    if args.limit:
        todo = todo[: args.limit]

    owned = {e.get("folder") for e in manifest.data["skills"].values() if e.get("folder")}
    jobs: list[tuple[dict, str]] = []
    for s in todo:
        entry = manifest.get(s["slug"])
        if entry and entry.get("folder"):
            folder = entry["folder"]
        else:
            folder = installer.pick_folder(dest, s["slug"], manifest, owned)
        owned.add(folder)
        jobs.append((s, folder))

    log(f"destination: {dest}")
    log(f"catalog={len(catalog)} todo={len(jobs)} workers={args.workers} fast={args.fast} "
        f"resources={not args.no_resources} quiet={args.quiet} dry_run={args.dry_run}")
    if not jobs:
        log("nothing to do")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    done = 0
    counts: dict[str, int] = {}
    errors: list[tuple[str, str]] = []

    try:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_one, s, folder, args): s for s, folder in jobs}
            for fut in cf.as_completed(futures):
                try:
                    res = fut.result()
                except Exception as e:
                    s = futures[fut]
                    res = {"slug": s["slug"], "name": s.get("name", ""), "status": "error",
                           "error": f"worker: {type(e).__name__}: {e}"}
                done += 1
                status = res.get("status", "error")
                counts[status] = counts.get(status, 0) + 1
                payload = {k: v for k, v in res.items() if k != "slug"}
                manifest.mark(res["slug"], **payload)
                if status == "error":
                    errors.append((res["slug"], res.get("error", "")))
                if done % 20 == 0 or done == len(jobs):
                    manifest.save()
                    elapsed = time.monotonic() - started
                    rate = done / elapsed if elapsed else 0
                    eta = (len(jobs) - done) / rate if rate else 0
                    log(f"{done}/{len(jobs)} ({done / len(jobs) * 100:.1f}%) "
                        f"{rate:.2f}/s eta {eta / 60:.1f}m | {counts}")
                if args.dry_run and done >= 25:
                    log("dry-run sample complete; stopping")
                    break
    except KeyboardInterrupt:
        log("interrupted; saving manifest")
    finally:
        manifest.save()

    elapsed = time.monotonic() - started
    log(f"finished in {elapsed / 60:.1f}m | {counts}")
    if errors:
        log("last errors:")
        for slug, err in errors[-10:]:
            log(f"  {slug}: {err}")
    log(f"manifest: {args.manifest}")
    log(f"log: {_log_path}")
    return 0


def cmd_status(args) -> int:
    data = tm_catalog.load_json(CATALOG_PATH, {})
    manifest = installer.Manifest(Path(args.manifest))
    counts = manifest.counts()
    dest = Path(args.dest).expanduser().resolve()
    dirs = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith(".")] if dest.exists() else []
    print(f"catalog: {len(data.get('skills', []))} skills (site total {data.get('total')})")
    print(f"manifest: {sum(counts.values())} entries -> {counts}")
    print(f"destination: {dest} ({len(dirs)} folders)")
    if data.get("skills"):
        installed = {e.get("folder") for e in manifest.data["skills"].values() if e.get("status") == "ok"}
        print(f"installed folders tracked: {len(installed)}")
    errors = [(k, v.get("error")) for k, v in manifest.data["skills"].items() if v.get("status") == "error"]
    if errors:
        print(f"errors: {len(errors)} (last 10)")
        for k, e in errors[-10:]:
            print(f"  {k}: {e}")
    return 0


def cmd_verify(args) -> int:
    manifest = installer.Manifest(Path(args.manifest))
    dest = Path(args.dest).expanduser().resolve()
    bad = []
    ok = 0
    for slug, entry in manifest.data["skills"].items():
        if entry.get("status") not in ("ok",):
            continue
        folder = entry.get("folder")
        md = dest / folder / "SKILL.md" if folder else None
        if not md or not md.exists() or md.stat().st_size == 0:
            bad.append((slug, "missing SKILL.md"))
            if args.fix:
                manifest.mark(slug, status="error", error="verify: missing SKILL.md")
        else:
            ok += 1
    if args.fix and bad:
        manifest.save()
    print(f"verified ok: {ok}")
    print(f"bad: {len(bad)}")
    for slug, why in bad[:20]:
        print(f"  {slug}: {why}")
    return 1 if bad else 0


def cmd_list(args) -> int:
    manifest = installer.Manifest(Path(args.manifest))
    rows = []
    for slug, e in manifest.data["skills"].items():
        if args.status and e.get("status") != args.status:
            continue
        rows.append((slug, e.get("status", ""), e.get("folder", ""), e.get("source", "")))
    for row in rows[: args.limit or len(rows)]:
        print("\t".join(str(x) for x in row))
    print(f"# {len(rows)} rows")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillget", description="Harvest TypingMind skills into ~/.agents/skills")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--category", default="devops")
        sp.add_argument("--sort", default="stars")
        sp.add_argument("--dest", default=str(DEFAULT_DEST))
        sp.add_argument("--refresh-catalog", action="store_true")
        sp.add_argument("--max-pages", type=int, default=None)
        sp.add_argument("--catalog-workers", type=int, default=8)

    c = sub.add_parser("catalog", help="fetch and cache the category catalog")
    common(c)
    c.set_defaults(func=cmd_catalog)

    c = sub.add_parser("crawl", help="install every skill in the catalog")
    common(c)
    c.add_argument("--workers", type=int, default=12)
    c.add_argument("--resource-workers", type=int, default=3)
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--only", default="")
    c.add_argument("--force", action="store_true")
    c.add_argument("--retry-errors", action="store_true")
    c.add_argument("--fast", action="store_true", help="skip raw SKILL.md fetch; use bodyMarkdown")
    c.add_argument("--no-resources", action="store_true")
    c.add_argument("--quiet", action="store_true", help="hide from auto-injected skill list (still loadable by ID)")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--cache-details", action="store_true")
    c.add_argument("--build", default=None)
    c.add_argument("--manifest", default=str(MANIFEST_PATH))
    c.add_argument("--ignore-lock", action="store_true",
                   help="run even if another crawl is active (unsafe)")
    c.set_defaults(func=cmd_crawl)

    c = sub.add_parser("status", help="show progress")
    c.add_argument("--dest", default=str(DEFAULT_DEST))
    c.add_argument("--manifest", default=str(MANIFEST_PATH))
    c.set_defaults(func=cmd_status)

    c = sub.add_parser("verify", help="check installed SKILL.md files")
    c.add_argument("--dest", default=str(DEFAULT_DEST))
    c.add_argument("--manifest", default=str(MANIFEST_PATH))
    c.add_argument("--fix", action="store_true")
    c.set_defaults(func=cmd_verify)

    c = sub.add_parser("list", help="list manifest entries")
    c.add_argument("--manifest", default=str(MANIFEST_PATH))
    c.add_argument("--status", default=None)
    c.add_argument("--limit", type=int, default=None)
    c.set_defaults(func=cmd_list)
    return p


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
