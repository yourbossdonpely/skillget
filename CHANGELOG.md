# Changelog

## 0.3.0 — 2026-11-23

- **Search harvests.** `--q` / `--query` crawls only the hits for a site search instead
  of a whole category, and accepts a pasted `?q=` URL (the query is read from the URL
  alongside the category). Each query gets its own catalog file
  (`data/catalog-<category>-<slugified-query>.json`) so searches never clobber
  `data/catalog.json`; `tm_catalog.fetch_query()` pages the search endpoint to
  `totalCount`.
- **Authoring skill.** `tools/fetch_authoring_skill.py` installs Anthropic's
  `skill-creator` (18 files: `SKILL.md`, `scripts/`, `agents/`, `references/`,
  `eval-viewer/`) into `~/.agents/skills/anthropic-skill-creator` with a
  `.skillget.json` record and the manifest slug `anthropic-skill-creator`.
- **Search-batch tooling.** `tools/report_media.py` reports per-query
  installed/missing/hit counts and verifies each folder's `SKILL.md`;
  `tools/spotcheck_media.py` prints size, file count and description per hit.
- **`index.py`** falls back to the `SKILL.md` frontmatter (including JSON-style blocks)
  for `name`, `description` and `license` when the catalog lacks them, so hand-installed
  skills — such as the authoring skill — are described instead of blank.
- **`report.py --category`** scopes the coverage report to one category and resolves
  the matching `catalog-<category>.json`.
- Harvested 619 skills across 23 animation/video/Blender/CapCut queries with 0
  failures, bringing the manifest to 45,775 entries (45,774 `ok`).

## 0.2.0 — 2026-11-22

- Enumerate categories larger than the 200-page list cap by partitioning on the
  category-scoped `author` filter (`--split-by auto|author|none`). Reaches the full
  `software-development` catalog (34,491) that paging alone truncates at ~10,200.
- `--category` accepts a full TypingMind skills URL.
- Recover orphaned temp installs and rebuild the manifest from disk (`tools/reconcile.py`).
- `crawl` holds a lock so two runs cannot corrupt the destination/manifest.
- Resource paths are sanitised to Windows-legal names (`< > : " | ? *`, control
  characters, reserved device names, trailing dots), so packages that ship files
  like `Sources/iPhone/<Name>App.swift` install instead of failing.
- Full harvest of the `software-development` category: 34,491 skills, joined with
  DevOps into 41,515 installed skills and 0 errors.

## 0.1.0 — 2026-11-22

- Initial release.
- Discovers TypingMind skill categories through the Next.js page-data API.
- Harvests the DevOps category: 9,271 unique skills across 182 pages.
- Preserves canonical `SKILL.md` frontmatter from GitHub raw content.
- Downloads supporting resources with traversal protection and size caps.
- Atomic installs with `.skillget.json` provenance.
- Resumable manifest with `ok` / `partial` / `error` / `not_found` states.
- Non-destructive collision handling (`-tm` suffix).
- Staging + merge workflow for very large installs.
- `--quiet` install mode (`metadata.opencode/autoinvoke: false`) keeps thousands of
  skills loadable by ID without injecting every description into the prompt.
- `skills-index.md` / `skills-index.json` discovery index.
- Frontmatter + provenance audit (`tools/audit.py`).
- Coverage, license, and failure reporting.
