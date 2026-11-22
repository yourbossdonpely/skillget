# Changelog

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
