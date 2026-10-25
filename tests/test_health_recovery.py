import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HealthRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts/stack-env.sh', self.root / 'scripts/stack-env.sh')
        (self.root / '.env').write_text(f'CONFIG_ROOT={self.root}/config\n')

    def shell(self, body, **env):
        return subprocess.run(
            ['bash', '-c', 'source "$HELPER"\n' + body], text=True, capture_output=True,
            env={**os.environ, 'HELPER': str(self.root / 'scripts/stack-env.sh'), **env},
            timeout=10)

    def test_self_failure_is_ignored_but_other_units_are_not(self):
        cases = [('', 0), ('arr-health.service loaded failed failed checker', 0),
                 ('arr-youtube.service loaded failed failed sync', 1),
                 ('arr-health.service loaded failed failed checker\n'
                  'arr-port-sync.service loaded failed failed vpn', 1),
                 ('arr-health.service.extra loaded failed failed other', 1)]
        for output, expected in cases:
            with self.subTest(output=output):
                result = self.shell('systemctl() { printf "%s\\n" "$UNITS"; }; health_units_ok', UNITS=output)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_systemctl_failure_is_not_a_healthy_result(self):
        result = self.shell('systemctl() { return 1; }; health_units_ok')
        self.assertEqual(result.returncode, 1)

    def test_failure_then_recovery_notifies_once(self):
        result = self.shell('''
set -e
notify() { printf '%s\\n' "$1"; }
health_notify 0 110
health_notify 2 108 'port mismatch' 'failed job'
test -f "$STATE_ROOT/health-failed"
health_notify 0 110
test ! -f "$STATE_ROOT/health-failed"
health_notify 0 110
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'media stack: 2 health check(s) failing', 'media stack: recovered'])

    def test_failed_delivery_keeps_recovery_pending(self):
        result = self.shell('''
set -e
notify() { return 1; }
health_notify 1 109 'port mismatch' && exit 10
test -f "$STATE_ROOT/health-failed"
health_notify 0 110 && exit 11
test -f "$STATE_ROOT/health-failed"
notify() { return 0; }
health_notify 0 110
test ! -f "$STATE_ROOT/health-failed"
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_notification_http_errors_propagate(self):
        result = self.shell('''
NTFY_TOPIC=test-only
curl() { [[ "$1" == *f* ]] || exit 10; return 22; }
notify title tag body
''')
        self.assertEqual(result.returncode, 22, result.stderr)

    def test_only_indexers_down_for_over_six_hours_are_named(self):
        prowlarr_health = json.dumps([
            {'source': 'IndexerStatusCheck', 'type': 'warning', 'message': 'Indexers unavailable due to failures: Knaben'},
            {'source': 'IndexerLongTermStatusCheck', 'type': 'warning',
             'message': 'Indexers unavailable due to failures for more than 6 hours: World-torrent, Torrent9'},
            {'source': 'UpdateCheck', 'type': 'notice', 'message': 'New update is available: 2.7'},
        ])
        for health_json, expected in [(prowlarr_health, 'World-torrent, Torrent9'), ('[]', '')]:
            with self.subTest(expected=expected):
                result = self.shell('long_down_indexers <<< "$HEALTH"', HEALTH=health_json)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_drive_smart_passes_a_sleeping_drive_and_judges_an_awake_one(self):
        stubs = 'sudo() { "$@"; }; findmnt() { echo /dev/sdb1; }; lsblk() { echo usb; }; smartctl() { printf "%s" "$SMART_JSON"; }; '
        asleep = json.dumps({'smartctl': {'exit_status': 2, 'messages': [
            {'string': 'Device is in STANDBY mode, exit(2)', 'severity': 'information'}]}})

        def awake(passed=True, temperature=40, reallocated=0):
            return json.dumps({'smartctl': {'exit_status': 0}, 'smart_status': {'passed': passed},
                               'temperature': {'current': temperature},
                               'ata_smart_attributes': {'table': [{'name': 'Reallocated_Sector_Ct', 'raw': {'value': reallocated}}]}})

        cases = [(asleep, 'health', 0), (asleep, 'temperature', 0), (awake(), 'health', 0), (awake(), 'sectors', 0),
                 (awake(), 'temperature', 0), (awake(passed=False), 'health', 1), (awake(reallocated=8), 'sectors', 1),
                 (awake(temperature=55), 'temperature', 1)]
        for smart_json, smart_check, expected in cases:
            with self.subTest(smart_check=smart_check, smart_json=smart_json[:60]):
                result = self.shell(stubs + f'drive_smart /mnt/backup {smart_check}', SMART_JSON=smart_json)
                self.assertEqual(result.returncode, expected, result.stderr)

        calls = self.shell('sudo() { "$@"; }; findmnt() { echo /dev/sdb1; }; lsblk() { echo usb; }; '
                           'smartctl() { echo "$*" >&2; printf "%s" "$SMART_JSON"; }; drive_smart /mnt/backup health', SMART_JSON=asleep)
        self.assertIn('-n standby', calls.stderr)
        self.assertIn('-d sat', calls.stderr)

    def test_retry_budget_and_manual_check_boundary(self):
        unit = (ROOT / 'host/systemd/arr-health.service').read_text()
        for value in ['Restart=on-failure', 'RestartSec=5min',
                      'StartLimitIntervalSec=1h', 'StartLimitBurst=4',
                      'ConditionPathIsMountPoint=@STORAGE_MOUNT@']:
            self.assertIn(value, unit)
        script = (ROOT / 'scripts/stack-health').read_text()
        self.assertIn('if [ "${1:-}" = "--notify" ]; then\n  health_notify', script)
        self.assertIn('"health_units_ok"', script)


if __name__ == '__main__':
    unittest.main()
