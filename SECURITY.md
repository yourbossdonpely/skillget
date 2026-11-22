# Security

skillget downloads third-party `SKILL.md` files and supporting resources from public
GitHub repositories. Those files are **untrusted content**. Installing a skill does not
sandbox it, and many skills instruct an agent to run commands.

## Recommendations

- Review `SKILL.md` and scripts before enabling a downloaded skill.
- Prefer skills from repositories you trust.
- Run crawls in a dedicated directory when testing.
- Keep `.skillget.json` with each skill so provenance is auditable.
- Do not run the crawler with elevated privileges.

## Tool-specific protections

- Path traversal is rejected for resource paths.
- Files larger than 50 MB are skipped.
- Existing non-skillget folders are never overwritten.
- Downloads use HTTPS and a bounded worker pool.

## Reporting a vulnerability in the tool

Open a private security advisory on the repository (or contact the maintainer) with a
reproduction. Do not include secrets in the report.
