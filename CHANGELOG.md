# Changelog

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
