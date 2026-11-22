# Publishing checklist

These are the steps used to publish this repository. Run them from
`C:\dev\appbuilddev\skillget`.

## 1. Local git

```powershell
git init -b main
git add .
git commit -m "feat: initial skillget crawler"
git tag -a v0.1.0 -m "skillget 0.1.0"
```

Verify the ignored files:

```powershell
git status --short
# data/ and logs/ must not appear
```

## 2. Create the public repository

With GitHub CLI:

```powershell
gh auth status
gh repo create skillget --public --source . --remote origin --push
git push origin v0.1.0
```

Without `gh`, create the repo in the browser, then:

```powershell
git remote add origin https://github.com/<owner>/skillget.git
git push -u origin main
git push origin v0.1.0
```

## 3. Release

```powershell
gh release create v0.1.0 --title "skillget v0.1.0" --notes-file CHANGELOG.md
```

Or create a release from the tag in the GitHub UI and paste the `0.1.0` section of
`CHANGELOG.md`.

## 4. Repository settings

- Description: `Harvest TypingMind open-source agent skills into ~/.agents/skills`
- Topics: `ai`, `agents`, `skills`, `crawler`, `typingmind`, `devops`, `python`
- Enable Issues and Discussions.
- Add the MIT license (already in `LICENSE`).
- Pin the release.

## 5. Post-publish

- Confirm CI is green on `main`.
- Verify the README badge/links if added.
- Keep `data/` and `logs/` out of the repository; they contain local paths and
  third-party content.
