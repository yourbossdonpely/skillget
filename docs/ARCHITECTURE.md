# Architecture

## Data flow

```
TypingMind catalog page
  └─ /_next/data/<buildId>/skills.json?category=devops&page=N&sort=stars
        └─ 182 pages × 51 rows → dedupe by slug → data/catalog.json (9,271)

For each slug:
  └─ /_next/data/<buildId>/skills/<slug>.json
        ├─ bodyMarkdown, description, license, compatibility, allowedTools
        ├─ sourceURL, owner, repo, path, defaultBranch
        └─ resources[] {path, size}
              ├─ SKILL.md  ← raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>/SKILL.md
              └─ resources ← raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>/<resource>
                    └─ atomic install → ~/.agents/skills/<slug>/
```

## Why the Next.js data endpoints

The directory is server-rendered. The HTML contains a `__NEXT_DATA__` blob, but the
`/_next/data/...` endpoints return the same JSON without the 500 KB page shell. The
detail endpoint is ~30 KB versus ~270 KB of HTML, which matters at 9,271 skills.

The `buildId` changes when the site deploys. `discover_build_id()` reads it from the
listing HTML; `catalog --refresh-catalog` re-discovers it. The fallback constant keeps
the tool usable if the regex changes.

## Pagination stability

`sort=trending` can reorder between page requests, causing duplicates and gaps.
`sort=stars` is stable for the duration of a crawl. The catalog command checks the
unique count against the site-reported `totalCount`; if it is short, it unions the
`trending` ordering as a safety net.

## Concurrency model

- Catalog: 8 workers, 182 requests.
- Crawl: 12 skill workers (configurable). Each worker fetches one detail payload,
  then one `SKILL.md`, then its resources with an inner pool of 3.
- Manifest updates happen only on the main thread, in batches of 20.
- Each worker uses a thread-local `requests.Session`.

Typical observed throughput: 5–7 skills/second on the DevOps category, dominated by
the detail request and GitHub raw latency.

## Install transaction

1. Choose a folder (slug, or `-tm` suffix on collision).
2. Create `.skillget-tmp/<folder>-<random>/`.
3. Fetch `SKILL.md`; fall back to synthesized frontmatter + `bodyMarkdown`.
4. Fetch resources into the temp tree.
5. Write `.skillget.json` provenance.
6. Rename the temp tree to the final folder. If the folder is an older skillget
   install, rename it aside, swap, then delete the old copy.

A crash leaves either the old folder or the new folder, never a half-written
`SKILL.md`.

## Manifest state machine

| State | Meaning | Retried by default? |
| --- | --- | --- |
| `ok` | `SKILL.md` written, install complete | No |
| `partial` | Installed, some resources failed | No (use `--retry-errors`) |
| `error` | Detail/GitHub/write failure | No (use `--retry-errors`) |
| `not_found` | Detail endpoint 404 | No (use `--retry-errors`) |
| `dry_run` | Planned only | No |

`verify --fix` converts a missing `SKILL.md` back to `error`.

## Staging

The live skill root (`~/.agents/skills`) may be scanned by an agent at session start.
A 9,271-skill install can exceed the model's context budget. The staging workflow
writes to a temp directory outside the scanned roots, then `merge.py` moves the
finished library into place once. The merge is idempotent and collision-safe.

## Quiet mode

The skill plugin injects every parsed skill that has a `description` into the system
prompt. `SkillFile.parse` in OpenCode reads `metadata.opencode/autoinvoke` (and the
Claude Code-compatible `disable-model-invocation`). Setting it to `false` removes the
skill from the injected list but leaves it in the `Skill` service, so the `skill` tool
can still load it by ID.

`tools/quiet.py` inserts the key with a line-based edit:

- existing `metadata:` block → insert `opencode/autoinvoke: false` as the first child;
- `metadata: {}` → `metadata: { opencode/autoinvoke: false }`;
- no `metadata:` → append a block at the end of the frontmatter;
- no frontmatter → prepend a minimal `name` / `metadata` block, because the loader
  skips files without frontmatter;
- `disable-model-invocation: true` or an existing false flag → leave untouched.

The flag is idempotent and the rest of the YAML is preserved byte-for-byte. The crawl
applies the same transform when `--quiet` is passed.

## Discovery index

`tools/index.py` reads the catalog and destination manifest and writes
`~/.agents/skills-index.md` and `~/.agents/skills-index.json`. Both live beside the
skill root, not inside it, so the scanner does not treat them as skills. The Markdown
file is sorted by stars and is intended for `Select-String` / `grep`; the JSON file is
for tooling.

## Audit

`tools/audit.py` cross-checks the catalog, manifest, folders, `SKILL.md`, provenance,
and (when PyYAML is installed) frontmatter syntax and the quiet flag. It exits non-zero
when a skill is missing or malformed, which makes it suitable as a release gate.

## Failure handling

- 429/5xx: bounded exponential backoff (up to 4 attempts).
- Unexpected JSON: retried; a stale `buildId` is the usual cause.
- Missing `SKILL.md`: generated fallback, flagged in `.skillget.json`.
- Resource 404: recorded per path; `SKILL.md` still installs.
- Unsafe path / >50 MB: skipped and recorded.
- Windows path length: recorded as a resource failure rather than aborting.
