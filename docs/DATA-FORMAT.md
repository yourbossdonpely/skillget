# Data formats

All JSON is UTF-8, pretty-printed, and written atomically (`.tmp` + replace).

## `data/catalog.json`

```json
{
  "category": "devops",
  "sort": "stars",
  "build": "build-TfctsWXpff2fKS",
  "total": 9271,
  "fetched_at": "2026-11-22T04:18:50+00:00",
  "skills": [
    {
      "id": "21147",
      "slug": "d4vinci-scrapling-official",
      "name": "Scrapling Official",
      "description": "...",
      "owner": "D4Vinci",
      "stars": 84767,
      "resources_count": 23,
      "is_popular": true
    }
  ]
}
```

## `data/manifest*.json`

```json
{
  "version": 1,
  "created_at": "2026-11-22T04:19:15+00:00",
  "updated_at": "2026-11-22T04:20:00+00:00",
  "skills": {
    "d4vinci-scrapling-official": {
      "status": "ok",
      "name": "Scrapling Official",
      "folder": "d4vinci-scrapling-official",
      "source": "https://github.com/D4Vinci/Scrapling/tree/main/agent-skill/Scrapling-Skill",
      "license": "BSD-3-Clause",
      "categories": ["software-development", "devops", "ai-ml"],
      "skill_md": "raw",
      "files": 24,
      "resource_failures": [],
      "path": "C:\\Users\\<user>\\.agents\\skills\\d4vinci-scrapling-official",
      "updated_at": "2026-11-22T04:19:15+00:00"
    }
  }
}
```

Fields that may appear on failures: `error`, `skill_md_error`, `resource_failures`
(list of `{path, error}`), `status: "not_found"`.

## `<skill>/.skillget.json`

```json
{
  "slug": "d4vinci-scrapling-official",
  "name": "Scrapling Official",
  "source": "https://github.com/D4Vinci/Scrapling/tree/main/agent-skill/Scrapling-Skill",
  "github": "https://github.com/D4Vinci/Scrapling",
  "license": "BSD-3-Clause",
  "categories": ["software-development", "devops", "ai-ml"],
  "installed_at": "2026-11-22T04:19:15+00:00",
  "tool": "skillget",
  "tool_version": "1.0.0",
  "skill_md": "raw",
  "resources_failed": []
}
```

This file is the ownership marker used by collision handling and merge.

## Logs

`logs/crawl-YYYYMMDD-HHMMSS.log` contains one progress line per 20 skills and the final
summary. Per-skill errors are in the manifest, not the log, so the log stays small.
