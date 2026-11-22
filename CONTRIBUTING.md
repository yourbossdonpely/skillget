# Contributing

Thanks for improving skillget.

## Development setup

```powershell
git clone <your-fork>
cd skillget
python -m pip install -r requirements-dev.txt
```

## Before opening a PR

1. Run a small crawl against a temp destination:
   ```powershell
   python tools/skillget.py catalog --max-pages 3
   python tools/skillget.py crawl --limit 10 --workers 2 --dest "$env:TEMP\skillget-test" --manifest "$env:TEMP\manifest-test.json"
   ```
2. Run `python tools/skillget.py verify --dest "$env:TEMP\skillget-test" --manifest "$env:TEMP\manifest-test.json"`.
3. Keep changes small and focused. Do not commit `data/` or `logs/`.
4. Update `README.md` / `CHANGELOG.md` when behavior changes.

## Design rules

- Never overwrite a folder that skillget did not create.
- Never write a skill folder without a non-empty `SKILL.md`.
- Keep the manifest write on the main thread.
- Prefer the site's JSON endpoints over HTML parsing.
- Treat downloaded skills as untrusted input.

## Reporting issues

Include the command, the slug, the manifest entry, and the relevant log excerpt from
`logs/`. Redact tokens and personal paths if needed.
