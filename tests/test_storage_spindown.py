import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StorageSpindownTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

        (self.root / 'scripts').mkdir()
        for script_name in ['stack-env.sh', 'storage-spindown']:
            shutil.copy(ROOT / 'scripts' / script_name, self.root / 'scripts' / script_name)

        self.backup = self.root / 'backup'
        self.smartctl_log = self.root / 'smartctl.log'
        (self.root / '.env').write_text(f'CONFIG_ROOT={self.root}/config\nBACKUP_MOUNT={self.backup}\nBACKUP_UUID=backup-uuid\n')

        self.stub_directory = self.root / 'bin'
        self.stub_directory.mkdir()
        self.write_stub('mountpoint', '[ "$1" = -q ] && shift\ncase " $MOUNTED " in *" $1 "*) exit 0 ;; esac\nexit 1')
        self.write_stub('findmnt', 'echo /dev/sdb1')
        self.write_stub('lsblk', 'case "$*" in *PKNAME*) echo sdb ;; *TRAN*) echo usb ;; esac')
        self.write_stub('smartctl', 'echo "$*" >> "$SMARTCTL_LOG"')

    def test_sets_a_ten_minute_idle_timer_on_the_backup_disk(self):
        spindown_result = self.run_spindown(MOUNTED=str(self.backup))

        self.assertEqual(spindown_result.returncode, 0, spindown_result.stderr)
        self.assertEqual(self.smartctl_log.read_text().splitlines(), ['-s standby,120 -d sat /dev/sdb'])

    def test_refuses_when_the_backup_drive_is_not_mounted(self):
        spindown_result = self.run_spindown(MOUNTED='')

        self.assertEqual(spindown_result.returncode, 1)
        self.assertIn('not mounted', spindown_result.stderr)
        self.assertFalse(self.smartctl_log.exists())

    def write_stub(self, command_name, body):
        stub_path = self.stub_directory / command_name
        stub_path.write_text(f'#!/bin/sh\n{body}\n')
        stub_path.chmod(0o755)

    def run_spindown(self, **stub_environment):
        environment = {**os.environ, 'PATH': f'{self.stub_directory}:{os.environ["PATH"]}',
                       'SMARTCTL_LOG': str(self.smartctl_log), **stub_environment}

        return subprocess.run(['bash', str(self.root / 'scripts/storage-spindown')],
                              text=True, capture_output=True, env=environment, timeout=30)


if __name__ == '__main__':
    unittest.main()
