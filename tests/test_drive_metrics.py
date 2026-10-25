import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DriveMetricsTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

        (self.root / 'scripts').mkdir()
        for script_name in ['stack-env.sh', 'drive-metrics']:
            shutil.copy(ROOT / 'scripts' / script_name, self.root / 'scripts' / script_name)

        self.storage = self.root / 'storage'
        self.backup = self.root / 'backup'
        self.smartctl_log = self.root / 'smartctl.log'
        self.write_env(backup_uuid='backup-uuid')

        self.stub_directory = self.root / 'bin'
        self.stub_directory.mkdir()
        self.write_stub('mountpoint', '[ "$1" = -q ] && shift\ncase " $MOUNTED " in *" $1 "*) exit 0 ;; esac\nexit 1')
        self.write_stub('findmnt', 'for mount_path; do :; done\n'
                        'case "$mount_path" in "$STORAGE_PATH") echo /dev/sda1 ;; "$BACKUP_PATH") echo /dev/sdb1 ;; *) echo /dev/nvme0n1p2 ;; esac')
        self.write_stub('lsblk', 'for device_path; do :; done\n'
                        'case "$*" in *PKNAME*) basename "$device_path" | sed "s/[0-9p]*$//" ;; *TRAN*) echo usb ;; esac')
        self.write_stub('systemctl', 'echo "$MIRROR_STATE"\nexit "$SYSTEMCTL_EXIT"')
        self.write_stub('smartctl', 'echo "$*" >> "$SMARTCTL_LOG"\nfor disk; do :; done\n'
                        'case " $ASLEEP " in *" $disk "*) echo \'{"smartctl": {"exit_status": 2}}\'; exit 2 ;; esac\n'
                        'case "$disk" in /dev/sda) echo \'{"temperature": {"current": 54}}\' ;; /dev/sdb) echo \'{"temperature": {"current": 49}}\' ;;'
                        ' *) echo \'{"temperature": {"current": 38}}\' ;; esac')

    def test_both_drives_reported_during_mirror_without_waking_them(self):
        metrics_result = self.run_metrics()

        self.assertEqual(metrics_result.returncode, 0, metrics_result.stderr)
        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54',
                                          'arr_drive_temperature_celsius{drive="backup"} 49'])

        for smartctl_call in self.smartctl_log.read_text().splitlines():
            self.assertIn('-n standby', smartctl_call)
            self.assertIn('-d sat', smartctl_call)

    def test_no_backup_drive_without_backup_uuid(self):
        self.write_env(backup_uuid='')

        self.run_metrics()

        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54'])

    def test_sleeping_last_drive_still_publishes_the_others(self):
        metrics_result = self.run_metrics(ASLEEP='/dev/sdb')

        self.assertEqual(metrics_result.returncode, 0, metrics_result.stderr)
        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54'])

    def test_unmounted_drive_is_never_reported_as_the_system_disk(self):
        self.run_metrics(MOUNTED=str(self.backup))

        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="backup"} 49'])

    def test_idle_awake_backup_is_not_queried(self):
        for state in ['inactive', 'failed', 'deactivating', 'reloading', 'unknown', '']:
            with self.subTest(state=state):
                self.smartctl_log.unlink(missing_ok=True)
                result = self.run_metrics(MIRROR_STATE=state)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54'])
                self.assertNotIn('/dev/sdb', self.smartctl_log.read_text())

    def test_active_mirror_can_publish_backup_temperature(self):
        result = self.run_metrics(MIRROR_STATE='active')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('arr_drive_temperature_celsius{drive="backup"} 49', self.metrics())

    def test_systemctl_failure_skips_backup_even_with_output(self):
        result = self.run_metrics(MIRROR_STATE='active', SYSTEMCTL_EXIT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('/dev/sdb', self.smartctl_log.read_text())
        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54'])

    def test_mirror_stopping_removes_old_live_temperature(self):
        self.run_metrics(MIRROR_STATE='activating')
        self.assertIn('arr_drive_temperature_celsius{drive="backup"} 49', self.metrics())
        self.smartctl_log.unlink()
        self.run_metrics(MIRROR_STATE='inactive')
        self.assertEqual(self.metrics(), ['arr_drive_temperature_celsius{drive="media"} 54'])
        self.assertNotIn('/dev/sdb', self.smartctl_log.read_text())

    def test_no_mounts_publish_empty_file_without_smart_queries(self):
        result = self.run_metrics(MOUNTED='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.metrics(), [])
        self.assertFalse(self.smartctl_log.exists())

    def metrics(self):
        return (self.root / 'state/metrics/drives.prom').read_text().splitlines()

    def write_env(self, backup_uuid):
        (self.root / '.env').write_text(
            f'CONFIG_ROOT={self.root}/config\nSTORAGE_MOUNT={self.storage}\nBACKUP_MOUNT={self.backup}\n'
            f'BACKUP_UUID={backup_uuid}\n')

    def write_stub(self, command_name, body):
        stub_path = self.stub_directory / command_name
        stub_path.write_text(f'#!/bin/sh\n{body}\n')
        stub_path.chmod(0o755)

    def run_metrics(self, **stub_environment):
        environment = {
            **os.environ,
            'PATH': f'{self.stub_directory}:{os.environ["PATH"]}',
            'MOUNTED': f'{self.storage} {self.backup}',
            'STORAGE_PATH': str(self.storage),
            'BACKUP_PATH': str(self.backup),
            'SMARTCTL_LOG': str(self.smartctl_log),
            'ASLEEP': '',
            'MIRROR_STATE': 'activating',
            'SYSTEMCTL_EXIT': '0',
            **stub_environment,
        }

        return subprocess.run(['bash', str(self.root / 'scripts/drive-metrics')],
                              text=True, capture_output=True, env=environment, timeout=30)


if __name__ == '__main__':
    unittest.main()
