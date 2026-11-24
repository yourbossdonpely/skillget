## skillget 0.4.0 — Windows desktop app

The `skillget` engine now ships as a Windows desktop app: browse the TypingMind
catalog, search it, read a skill, install it into `~/.agents/skills`.

### Downloads

| Asset | What it is |
| --- | --- |
| `skillget_0.4.0_x64-setup.exe` | NSIS installer, per-user, no admin prompt |
| `skillget-0.4.0-windows-portable.zip` | unzip and run `skillget.exe` |
| `SHA256SUMS.txt` | checksums for both |

The binaries are unsigned, so SmartScreen may warn; *More info → Run anyway*.

### What's new

- **Tauri 2 shell** that bundles the Node engine (with `node.exe`) and starts it on a free
  loopback port; the window opens only after `/api/health` answers, and the engine is
  killed on exit.
- **Browse** — all 16 categories with live counts, 51 per page, sort by stars/newest.
- **Search** — TypingMind site-wide search, paginated.
- **Detail** — source link, license, resource list, `SKILL.md` preview.
- **Installed** — tracked installs with folder, `SKILL.md` origin, quiet state and disk health.
- **Quiet installs by default** — `metadata.opencode/autoinvoke: false` is added when the
  frontmatter can still be parsed; the original text is left alone otherwise.
- **Never overwrites** an unowned folder (`-tm` suffix), and replaces its own install in
  place instead of duplicating it.
- Per-app install state in `%LOCALAPPDATA%\com.yourbossdonpely.skillget\state`, separate
  from the CLI's `data/manifest.json`.

### Verified

- `vite build` and `tauri build` (release + NSIS) pass.
- The packaged app launches, answers `/api/health`, installs a real skill through its own
  engine, and lists it under Installed.
- CLI unit tests (`python -m unittest discover -s tests`) and `skillget verify` still pass;
  `data/manifest.json` is untouched by the desktop app.

### Known limitations

- Windows x64 build only; unsigned.
- Search covers the TypingMind catalog only.
- WebView2 runtime is required (preinstalled on current Windows).
