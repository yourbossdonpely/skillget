# Tools

All scripts are plain Python 3.10+ and use only `requests`.

| File | Purpose |
| --- | --- |
| `skillget.py` | Main CLI: `catalog`, `crawl`, `status`, `verify`, `list`. |
| `tm_catalog.py` | TypingMind Next.js page-data client (catalog + detail). |
| `github_fetch.py` | Raw GitHub downloads, path safety, resource fan-out. |
| `installer.py` | Atomic skill folder writer, frontmatter synthesis, manifest. |
| `quiet.py` | Add `metadata.opencode/autoinvoke: false` without rewriting the rest of the YAML. |
| `merge.py` | Merge a staged library into `~/.agents/skills` safely. |
| `reconcile.py` | Repair an interrupted/concurrent crawl: recover orphaned temp installs, delete junk temp folders, rebuild the manifest from disk. |
| `index.py` | Build `skills-index.md` and `skills-index.json` for discovery. |
| `report.py` | Coverage/license/failure report. |
| `stage_existing.py` | Move skillget folders from the live root into staging. |
| `inspect_page.py` | Debug: print `__NEXT_DATA__` structure of a page. |
| `dump_detail.py` | Debug: dump the full detail JSON for one skill. |
| `probe_api.py` | Debug: check pagination and Next.js data endpoints. |
| `probe2.py` | Debug: check detail fields and raw GitHub access. |
| `bench.py` | Debug: measure detail-endpoint concurrency. |

## Repair after an interrupted crawl

```powershell
python tools/reconcile.py          # recover temp installs + rebuild manifest from disk
python tools/skillget.py verify    # confirm every OK entry still has SKILL.md
python tools/skillget.py crawl --quiet   # resume the remaining skills
```

## Invariants

- `skillget.py` is the only entry point that writes a manifest.
- Workers never touch the manifest; the main thread marks results and saves in batches.
- A skill folder is staged in `.skillget-tmp/` and renamed into place only after
  `SKILL.md` exists.
- `merge.py` refuses to overwrite a folder without a matching `.skillget.json` slug.
- `crawl` takes a lock (`data/.crawl.lock`). Never run two crawls against the same
  destination: they race on folder renames and corrupt the manifest. If a run was
  interrupted, run `python tools/reconcile.py` before resuming.
- A folder is replaced in place only when its `.skillget.json` slug matches the skill
  being installed; any other existing folder is given a `-tm` suffix, never deleted.

## Adding a category

```powershell
python tools/skillget.py catalog --category security --refresh-catalog
python tools/skillget.py crawl --category security --dest "$env:TEMP\opencode\security-skills" --manifest data\manifest-security.json
```

The catalog cache is keyed by category in `data/catalog.json`; use `--refresh-catalog`
when switching categories, or point `--category` at a fresh run.
