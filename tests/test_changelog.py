import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


path = Path(__file__).resolve().parents[1] / "scripts/changelog.py"
spec = importlib.util.spec_from_file_location("changelog", path)
changelog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changelog)

CHANGELOG_TEXT = """# Changelog

Intro.

## Unreleased

### Added
- Arch Linux support.

### Fixed
- A stuck request.

## 1.3.0 - 2026-09-01

### Fixed
- Old fix.
"""


class ChangelogTests(unittest.TestCase):
    def test_highest_heading_decides_the_bump(self):
        self.assertEqual(changelog.next_version("1.3.2", "### Fixed\n- x"), "1.3.3")
        self.assertEqual(changelog.next_version("1.3.2", "### Fixed\n- x\n### Added\n- y"), "1.4.0")
        self.assertEqual(changelog.next_version("1.3.2", "### Security\n- x\n### Removed\n- y"), "2.0.0")
        self.assertEqual(changelog.next_version("1.3.2", "### Breaking\n- x"), "2.0.0")

    def test_empty_unreleased_means_no_release(self):
        self.assertIsNone(changelog.next_version("1.3.2", ""))

    def test_unknown_or_missing_heading_fails(self):
        with self.assertRaises(SystemExit):
            changelog.next_version("1.3.2", "### Feature\n- x")

        with self.assertRaises(SystemExit):
            changelog.next_version("1.3.2", "- a note without a heading")

    def test_cut_moves_unreleased_and_notes_reads_it_back(self):
        released_text = changelog.cut_changelog(CHANGELOG_TEXT, "1.4.0", "2026-09-28")

        self.assertIn("## Unreleased\n\n## 1.4.0 - 2026-09-28\n\n### Added", released_text)
        self.assertEqual(changelog.section_notes(released_text, r"## Unreleased"), "")
        self.assertEqual(changelog.section_notes(released_text, r"## 1\.4\.0 - .*"),
                         "### Added\n- Arch Linux support.\n\n### Fixed\n- A stuck request.")
        self.assertIn("## 1.3.0 - 2026-09-01", released_text)
        self.assertTrue(released_text.endswith("- Old fix.\n"))

    def test_set_file_version_keeps_formatting(self):
        with tempfile.TemporaryDirectory() as directory:
            version_file = os.path.join(directory, "package.json")
            Path(version_file).write_text('{\n  "name": "x",\n  "version": "1.3.0",\n  "dependencies": {"a": "1.0.0"}\n}\n')

            changelog.set_file_version(version_file, "1.4.0")

            self.assertEqual(json.loads(Path(version_file).read_text())["version"], "1.4.0")
            self.assertIn('"a": "1.0.0"', Path(version_file).read_text())
            self.assertTrue(Path(version_file).read_text().startswith('{\n  "name"'))


if __name__ == "__main__":
    unittest.main()
