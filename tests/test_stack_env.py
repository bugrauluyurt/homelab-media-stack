import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


repo = Path(__file__).resolve().parents[1]


def load_stack_env(env_text):
    """A fresh stack_env reading env_text as its .env, from a throwaway copy of the repo layout."""
    temp_repo = Path(tempfile.mkdtemp())
    (temp_repo / "scripts").mkdir()
    shutil.copy(repo / "scripts/stack_env.py", temp_repo / "scripts/stack_env.py")
    (temp_repo / ".env").write_text(env_text)

    spec = importlib.util.spec_from_file_location("stack_env_under_test", temp_repo / "scripts/stack_env.py")
    stack_env = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack_env)

    return stack_env, temp_repo / ".env"


class EnvParsingTests(unittest.TestCase):
    def test_quoted_values_are_read_unquoted(self):
        stack_env, _ = load_stack_env("CONFIG_ROOT=/srv/config\nSINGLE='a$b'\nDOUBLE=\"c d\"\nPLAIN=e=f\n")

        self.assertEqual(stack_env.ENV["SINGLE"], "a$b")
        self.assertEqual(stack_env.ENV["DOUBLE"], "c d")
        self.assertEqual(stack_env.ENV["PLAIN"], "e=f")

    def test_comment_lines_are_skipped(self):
        stack_env, _ = load_stack_env("CONFIG_ROOT=/srv/config\n# COMMENTED=1\n  # INDENTED=2\n")

        self.assertNotIn("# COMMENTED", stack_env.ENV)
        self.assertNotIn("  # INDENTED", stack_env.ENV)

    def test_state_and_storage_derive_from_env(self):
        stack_env, _ = load_stack_env("CONFIG_ROOT=/srv/data/config\n")

        self.assertEqual(stack_env.STATE, Path("/srv/data/state"))
        self.assertEqual(stack_env.STORAGE, Path("/mnt/storage"))


class NtfyServerTests(unittest.TestCase):
    def test_unset_or_empty_falls_back_to_ntfy_sh(self):
        for env_text in ("CONFIG_ROOT=/c\n", "CONFIG_ROOT=/c\nNTFY_SERVER=\n"):
            with self.subTest(env_text=env_text):
                stack_env, _ = load_stack_env(env_text)

                self.assertEqual(stack_env.NTFY_SERVER, "https://ntfy.sh")

    def test_set_value_wins(self):
        stack_env, _ = load_stack_env("CONFIG_ROOT=/c\nNTFY_SERVER=https://ntfy.example\n")

        self.assertEqual(stack_env.NTFY_SERVER, "https://ntfy.example")


class SetEnvTests(unittest.TestCase):
    def test_replaces_an_existing_line_in_place(self):
        stack_env, env_path = load_stack_env("CONFIG_ROOT=/c\n# note\nAPI_KEY=old\nOTHER=1\n")

        stack_env.set_env("API_KEY", "new")

        self.assertEqual(env_path.read_text(), "CONFIG_ROOT=/c\n# note\nAPI_KEY=new\nOTHER=1\n")
        self.assertEqual(stack_env.ENV["API_KEY"], "new")

    def test_appends_a_missing_key_and_keeps_the_trailing_newline(self):
        stack_env, env_path = load_stack_env("CONFIG_ROOT=/c")

        stack_env.set_env("API_KEY", "value")

        self.assertEqual(env_path.read_text(), "CONFIG_ROOT=/c\nAPI_KEY=value\n")

    def test_a_key_prefix_is_not_mistaken_for_the_key(self):
        stack_env, env_path = load_stack_env("CONFIG_ROOT=/c\nAPI_KEY_OLD=keep\n")

        stack_env.set_env("API_KEY", "value")

        self.assertEqual(env_path.read_text(), "CONFIG_ROOT=/c\nAPI_KEY_OLD=keep\nAPI_KEY=value\n")


if __name__ == "__main__":
    unittest.main()
