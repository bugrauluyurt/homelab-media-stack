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

## 1.3.0 - 2026-09-01

### Fixed
- Old fix.
"""


def write_entries(directory, entries):
    for name, text in entries.items():
        Path(directory, name).write_text(text)


class ChangelogTests(unittest.TestCase):
    def test_highest_heading_decides_the_bump(self):
        self.assertEqual(changelog.next_version("1.3.2", ["fixed"]), "1.3.3")
        self.assertEqual(changelog.next_version("1.3.2", ["fixed", "added"]), "1.4.0")
        self.assertEqual(changelog.next_version("1.3.2", ["security", "removed"]), "2.0.0")
        self.assertEqual(changelog.next_version("1.3.2", ["breaking"]), "2.0.0")

    def test_no_entries_means_no_release(self):
        self.assertIsNone(changelog.next_version("1.3.2", []))

    def test_entries_come_from_file_names_sorted_and_skip_the_readme(self):
        with tempfile.TemporaryDirectory() as directory:
            write_entries(directory, {
                "zz-stuck-request.fixed.md": "- A stuck request.\n",
                "arch-support.added.md": "- Arch Linux support.\n  On x86 too.\n",
                "README.md": "How to write an entry.\n",
            })

            entries = changelog.changelog_entries(Path(directory))

        self.assertEqual([(entry_path.name, heading, entry) for entry_path, heading, entry in entries], [
            ("arch-support.added.md", "added", "- Arch Linux support.\n  On x86 too."),
            ("zz-stuck-request.fixed.md", "fixed", "- A stuck request."),
        ])

    def test_badly_named_or_written_entry_fails(self):
        for name, text in [("thing.feature.md", "- x"), ("added.md", "- x"), ("thing.added.md", "no bullet")]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                write_entries(directory, {name: text})

                with self.assertRaises(SystemExit):
                    changelog.changelog_entries(Path(directory))

    def test_cut_writes_the_release_above_the_last_one_and_notes_reads_it_back(self):
        entries = [
            (Path("b.fixed.md"), "fixed", "- A stuck request."),
            (Path("a.added.md"), "added", "- Arch Linux support."),
            (Path("c.breaking.md"), "breaking", "- A new mount."),
        ]

        section = changelog.release_section("2.0.0", "2026-09-28", entries)
        released_text = changelog.cut_changelog(CHANGELOG_TEXT, section)

        self.assertIn("Intro.\n\n## 2.0.0 - 2026-09-28\n\n### Breaking", released_text)
        self.assertEqual(changelog.section_notes(released_text, r"## 2\.0\.0 - .*"),
                         "### Breaking\n- A new mount.\n\n### Added\n- Arch Linux support.\n\n### Fixed\n- A stuck request.")
        self.assertIn("## 1.3.0 - 2026-09-01", released_text)
        self.assertTrue(released_text.endswith("- Old fix.\n"))

    def test_leftover_unreleased_section_is_refused(self):
        with self.assertRaises(SystemExit):
            changelog.refuse_unreleased("# Changelog\n\n## Unreleased\n\n### Fixed\n- x\n")

        changelog.refuse_unreleased(CHANGELOG_TEXT)

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
