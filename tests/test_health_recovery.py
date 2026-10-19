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
