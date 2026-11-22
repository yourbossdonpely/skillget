"""Unit tests for pure helpers (no network)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import audit  # noqa: E402
import github_fetch  # noqa: E402
import index  # noqa: E402
import installer  # noqa: E402
import quiet  # noqa: E402


class FolderTests(unittest.TestCase):
    def test_safe_folder(self):
        self.assertEqual(installer.safe_folder("My Skill!"), "my-skill")
        self.assertEqual(installer.safe_folder("a//b"), "a-b")
        self.assertEqual(installer.safe_folder(""), "skill")

    def test_reserved(self):
        self.assertTrue(installer.safe_folder("CON").startswith("skill-"))

    def test_skill_name(self):
        self.assertEqual(installer.safe_skill_name("My Skill", "x"), "my-skill")
        self.assertEqual(installer.safe_skill_name("", "fallback"), "fallback")


class FrontmatterTests(unittest.TestCase):
    def test_generated_frontmatter(self):
        skill = {
            "slug": "demo-skill",
            "skillName": "Demo Skill",
            "description": "Does a thing.",
            "bodyMarkdown": "# Demo\n\nHello",
            "license": "MIT",
            "allowedTools": ["Bash(ls:*)"],
            "metadata": {"homepage": "https://example.com"},
        }
        md = installer.synthesize_skill_md(skill)
        self.assertTrue(md.startswith("---\n"))
        self.assertIn('name: "demo-skill"', md)
        self.assertIn('description: "Does a thing."', md)
        self.assertIn("# Demo", md)
        self.assertIn("allowed-tools", md)

    def test_empty_body_gets_heading(self):
        md = installer.synthesize_skill_md({"slug": "x", "name": "X", "description": "d"})
        self.assertIn("# X", md)


class PathTests(unittest.TestCase):
    def test_clean_relpath(self):
        self.assertEqual(github_fetch.clean_relpath("a/b/c.md").as_posix(), "a/b/c.md")
        self.assertIsNone(github_fetch.clean_relpath("../secret"))
        self.assertIsNone(github_fetch.clean_relpath("/etc/passwd"))
        self.assertIsNone(github_fetch.clean_relpath("C:\\Windows\\x"))
        self.assertIsNone(github_fetch.clean_relpath(""))

    def test_parse_source(self):
        skill = {
            "owner": "o",
            "repo": "r",
            "defaultBranch": "main",
            "path": "skills/x",
            "sourceURL": "https://github.com/o/r/tree/main/skills/x",
        }
        self.assertEqual(github_fetch.parse_source(skill), ("o", "r", "main", "skills/x"))

    def test_parse_source_from_url(self):
        skill = {"sourceURL": "https://github.com/o/r/tree/dev/skills/x"}
        self.assertEqual(github_fetch.parse_source(skill), ("o", "r", "dev", "skills/x"))

    def test_parse_source_missing(self):
        self.assertIsNone(github_fetch.parse_source({}))


class ManifestTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            m = installer.Manifest(path)
            m.mark("a", status="ok", folder="a")
            m.mark("b", status="error", error="boom")
            m.save()
            again = installer.Manifest(path)
            self.assertEqual(again.get("a")["status"], "ok")
            self.assertEqual(again.get("b")["error"], "boom")
            self.assertEqual(again.counts(), {"ok": 1, "error": 1})
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], 1)


class QuietTests(unittest.TestCase):
    def test_no_frontmatter(self):
        self.assertIsNone(quiet.split_frontmatter("# just a body\n"))

    def test_adds_metadata(self):
        fm, body, nl = quiet.split_frontmatter("---\nname: demo\ndescription: x\n---\nBody\n")
        self.assertEqual(body, "Body\n")
        new, status = quiet.mark(fm)
        self.assertEqual(status, "added")
        self.assertEqual(new[-2:], ["metadata:", "  opencode/autoinvoke: false"])

    def test_inserts_under_existing_metadata(self):
        fm = ["name: demo", "metadata:", "  version: 1.0.0"]
        new, status = quiet.mark(fm)
        self.assertEqual(status, "added")
        self.assertEqual(new[2], "  opencode/autoinvoke: false")
        self.assertEqual(new[3], "  version: 1.0.0")

    def test_inline_metadata(self):
        fm = ["name: demo", "metadata: {}"]
        new, status = quiet.mark(fm)
        self.assertEqual(status, "added")
        self.assertEqual(new[1], "metadata: { opencode/autoinvoke: false }")

    def test_idempotent(self):
        fm = ["name: demo", "metadata:", "  opencode/autoinvoke: false"]
        new, status = quiet.mark(fm)
        self.assertEqual(status, "already")
        self.assertEqual(new, fm)

    def test_respects_disable_model_invocation(self):
        fm = ["name: demo", "disable-model-invocation: true"]
        new, status = quiet.mark(fm)
        self.assertEqual(status, "already")
        self.assertEqual(new, fm)

    def test_no_frontmatter_prepends(self):
        text, status = quiet.ensure_quiet("# Body\n", "demo")
        self.assertEqual(status, "prepended")
        self.assertTrue(text.startswith('---\nname: "demo"'))
        self.assertIn("opencode/autoinvoke: false", text)
        self.assertTrue(text.endswith("# Body\n"))

    def test_roundtrip_preserves_body(self):
        text = "---\r\nname: demo\r\ndescription: x\r\n---\r\n# Title\r\n\r\nBody\r\n"
        fm, body, nl = quiet.split_frontmatter(text)
        new, _ = quiet.mark(fm)
        rebuilt = nl.join(["---", *new, "---"]) + nl + body
        self.assertIn("opencode/autoinvoke: false", rebuilt)
        self.assertTrue(rebuilt.endswith("# Title\r\n\r\nBody\r\n"))


class AuditTests(unittest.TestCase):
    def test_no_frontmatter(self):
        status, _ = audit.check_frontmatter("# Body\n", False)
        self.assertEqual(status, "no-frontmatter")

    @unittest.skipIf(audit.yaml is None, "pyyaml not installed")
    def test_quiet_ok(self):
        text = (
            "---\nname: demo\ndescription: x\nmetadata:\n  opencode/autoinvoke: false\n---\nBody\n"
        )
        status, _ = audit.check_frontmatter(text, True)
        self.assertEqual(status, "ok")

    @unittest.skipIf(audit.yaml is None, "pyyaml not installed")
    def test_not_quiet(self):
        text = "---\nname: demo\ndescription: x\n---\nBody\n"
        status, _ = audit.check_frontmatter(text, True)
        self.assertEqual(status, "not-quiet")

    @unittest.skipIf(audit.yaml is None, "pyyaml not installed")
    def test_disable_model_invocation_counts_as_quiet(self):
        text = "---\nname: demo\ndescription: x\ndisable-model-invocation: true\n---\nBody\n"
        status, _ = audit.check_frontmatter(text, True)
        self.assertEqual(status, "ok")


class IndexTests(unittest.TestCase):
    def test_one_line(self):
        self.assertEqual(index.one_line("a | b\n c"), "a \\| b c")

    def test_truncates(self):
        self.assertTrue(index.one_line("x" * 300, limit=20).endswith("…"))


if __name__ == "__main__":
    unittest.main()
