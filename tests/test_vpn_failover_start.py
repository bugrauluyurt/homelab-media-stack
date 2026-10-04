import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VpnFailoverStartTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.fixture_directory = Path(temporary_directory.name)
        self.server_directory = self.fixture_directory / 'verified-servers'
        self.server_directory.mkdir()

        self.entrypoint_path = self.fixture_directory / 'gluetun-entrypoint'
        self.entrypoint_path.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 37\n')
        self.entrypoint_path.chmod(0o700)

        wrapper_source = (ROOT / 'apps/gluetun/start-failover.sh').read_text()
        wrapper_source = wrapper_source.replace('/gluetun/verified-servers/', str(self.server_directory) + '/')
        wrapper_source = wrapper_source.replace('/gluetun-entrypoint', str(self.entrypoint_path))
        self.wrapper_path = self.fixture_directory / 'start-failover.sh'
        self.wrapper_path.write_text(wrapper_source)

        for server_file_name in ['manifest.json', 'protonvpn.json']:
            (self.server_directory / server_file_name).write_text('{}')

    def test_valid_files_exec_gluetun_and_preserve_arguments_and_exit_code(self):
        wrapper_result = self.run_wrapper(['healthcheck', 'argument with spaces'])

        self.assertEqual(wrapper_result.returncode, 37)
        self.assertEqual(wrapper_result.stdout, 'healthcheck\nargument with spaces\n')
        self.assertEqual(wrapper_result.stderr, '')

    def test_missing_empty_and_directory_inputs_stop_before_gluetun(self):
        for server_file_name in ['manifest.json', 'protonvpn.json']:
            for input_state in ['missing', 'empty', 'directory']:
                with self.subTest(server_file_name=server_file_name, input_state=input_state):
                    server_file = self.server_directory / server_file_name
                    server_file.unlink()

                    if input_state == 'empty':
                        server_file.touch()
                    elif input_state == 'directory':
                        server_file.mkdir()

                    wrapper_result = self.run_wrapper(['must-not-run'])

                    self.assertEqual(wrapper_result.returncode, 1)
                    self.assertEqual(wrapper_result.stdout, '')
                    self.assertIn(server_file_name, wrapper_result.stderr)

                    if server_file.is_dir():
                        server_file.rmdir()

                    server_file.write_text('{}')

    @unittest.skipIf(os.getuid() == 0, 'root bypasses Unix file read permissions')
    def test_unreadable_server_file_stops_before_gluetun(self):
        server_file = self.server_directory / 'protonvpn.json'
        server_file.chmod(0o000)

        wrapper_result = self.run_wrapper(['must-not-run'])

        self.assertEqual(wrapper_result.returncode, 1)
        self.assertEqual(wrapper_result.stdout, '')
        self.assertIn('protonvpn.json', wrapper_result.stderr)

    def run_wrapper(self, arguments):
        return subprocess.run(
            ['/bin/sh', str(self.wrapper_path), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
