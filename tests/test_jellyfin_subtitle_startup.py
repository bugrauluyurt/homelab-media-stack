import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


repo = Path(__file__).resolve().parents[1]
hook = repo / "apps/jellyfin/custom-cont-init.d/subtitle-downloads.sh"


class SubtitleStartupTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.web_root = Path(temporary_directory.name) / "web"
        self.web_root.mkdir()
        self.index = self.web_root / "index.html"

    def test_installs_once_and_preserves_other_customizations(self):
        self.index.write_text('<html><body><script src="ui/spotlight-loader.js"></script></body></html>')

        first_run = self._run_hook()
        first_index = self.index.read_bytes()
        second_run = self._run_hook()

        self.assertEqual(first_run.returncode, 0, first_run.stderr)
        self.assertEqual(second_run.returncode, 0, second_run.stderr)
        self.assertEqual(self.index.read_bytes(), first_index)
        self.assertEqual(self.index.read_text().count("data-subtitle-downloads"), 1)
        self.assertIn('src="ui/spotlight-loader.js"', self.index.read_text())
        self.assertEqual((self.web_root / "ui/subtitle-downloads.js").read_bytes(),
                         (hook.parent / "assets/subtitle-downloads.js").read_bytes())
        self.assertTrue(second_run.stdout.strip().startswith("="))

    def test_reapplies_after_web_files_are_replaced(self):
        self.index.write_text("<html><body>old image</body></html>")
        self.assertEqual(self._run_hook().returncode, 0)

        shutil.rmtree(self.web_root / "ui")
        self.index.write_text("<html><body>new image</body></html>")
        replacement_run = self._run_hook()

        self.assertEqual(replacement_run.returncode, 0, replacement_run.stderr)
        self.assertIn("new image", self.index.read_text())
        self.assertEqual(self.index.read_text().count("data-subtitle-downloads"), 1)
        self.assertTrue((self.web_root / "ui/subtitle-downloads.js").is_file())

    def test_replaces_old_loader_with_content_version(self):
        self.index.write_text('<body><script src="ui/subtitle-downloads.js?v=old" '
                              'type="module" data-subtitle-downloads></script></body>')

        hook_run = self._run_hook()
        script_hash = hashlib.sha256((hook.parent / "assets/subtitle-downloads.js").read_bytes()).hexdigest()

        self.assertEqual(hook_run.returncode, 0, hook_run.stderr)
        self.assertEqual(self.index.read_text().count("data-subtitle-downloads"), 1)
        self.assertIn(f"subtitle-downloads.js?v={script_hash}", self.index.read_text())
        self.assertNotIn("?v=old", self.index.read_text())

    def test_unsupported_index_is_unchanged_and_does_not_block_startup(self):
        unsupported_index = "<html><main>different Jellyfin layout</main></html>"
        self.index.write_text(unsupported_index)

        hook_run = self._run_hook()

        self.assertEqual(hook_run.returncode, 0, hook_run.stderr)
        self.assertEqual(self.index.read_text(), unsupported_index)
        self.assertFalse((self.web_root / "ui").exists())
        self.assertIn("!", hook_run.stdout)

    def test_missing_web_root_does_not_block_startup(self):
        shutil.rmtree(self.web_root)

        hook_run = self._run_hook()

        self.assertEqual(hook_run.returncode, 0, hook_run.stderr)
        self.assertIn("!", hook_run.stdout)

    def _run_hook(self):
        return subprocess.run(["bash", str(hook), str(self.web_root)],
                              capture_output=True, text=True, check=False)
