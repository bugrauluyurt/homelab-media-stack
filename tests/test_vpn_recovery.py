import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / 'scripts').mkdir()
        (self.repo / 'state').mkdir()
        shutil.copy2(ROOT / 'scripts/sync-port', self.repo / 'scripts/sync-port')
        self.prefs = {
            'listen_port': 49094,
            'current_interface_address': '10.2.0.2',
            'bypass_auth_subnet_whitelist': '100.64.0.0/10\n172.16.0.0/12',
            'web_ui_csrf_protection_enabled': True,
            'web_ui_host_header_validation_enabled': True,
            'web_ui_domain_list': 'gluetun;127.0.0.1;test;test.local;test.*.ts.net;',
        }
        (self.repo / 'scripts/stack-env.sh').write_text(r'''
REPO=$TEST_REPO
STATE_ROOT=$REPO/state
QBIT_PORT=8080
HOST_NAME=test
json_get() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"; }
tunnel_ip() { echo "${TUNNEL-10.2.0.2}"; }
forwarded_port() {
  if [ "${PORT_PENDING:-0}" = 1 ]; then
    local count
    count=$(cat "$REPO/port-reads" 2>/dev/null || echo 0)
    count=$((count + 1)); echo "$count" > "$REPO/port-reads"
    [ "$count" -ge 3 ] && echo 49094
  else
    echo "${PORT-49094}"
  fi
}
vpn_healthy() { [ "${READY:-1}" = 1 ]; }
vpn_apps_attached() { [ "${ATTACHED:-1}" = 1 ]; }
reattach_vpn_apps() { echo reattach >> "$REPO/events"; vpn_healthy && [ "${REATTACH_OK:-1}" = 1 ]; }
qbit_prefs() { printf '%s' "$PREFS"; }
notify() { echo "notify:$1" >> "$REPO/events"; }
sleep() { :; }
ip() { :; }
docker() {
  if [ "$1 $2 $3 $4" = 'compose restart --no-deps gluetun' ]; then
    echo restart >> "$REPO/events"
    if [ "${RECOVERS:-0}" = 1 ]; then READY=1; PORT=49094; TUNNEL=10.2.0.2; fi
  elif [ "$1 $2 $3" = 'exec gluetun sh' ]; then
    echo 1
  elif [ "$1 $2" = 'exec qbittorrent' ]; then
    echo write >> "$REPO/events"
    [ "${WRITE_OK:-1}" = 1 ]
  else
    echo "unexpected docker call" >&2
    return 1
  fi
}
''')

    def run_sync(self, **options):
        env = dict(os.environ, TEST_REPO=str(self.repo), PREFS=json.dumps(self.prefs))
        env.update(options)
        result = subprocess.run(['bash', str(self.repo / 'scripts/sync-port')],
                                env=env, text=True, capture_output=True, timeout=10)
        events = self.repo / 'events'
        return result, events.read_text().splitlines() if events.exists() else []

    def missing_long_enough(self):
        import time
        (self.repo / 'state/port-forward-missing-since').write_text(str(int(time.time()) - 1000))

    def test_healthy_idempotent(self):
        result, events = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, [])
        self.assertIn('already in sync', result.stdout)

    def test_healthy_before_port_is_ready_waits_then_restores_clients(self):
        result, events = self.run_sync(PORT_PENDING='1', ATTACHED='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ['reattach'])
        self.assertFalse((self.repo / 'state/port-forward-missing-since').exists())

    def test_spontaneous_recovery_reattaches_without_vpn_restart(self):
        result, events = self.run_sync(ATTACHED='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ['reattach'])

    def test_unhealthy_with_stale_port_does_not_touch_clients(self):
        result, events = self.run_sync(READY='0', ATTACHED='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, [])

    def test_failed_restart_never_reattaches(self):
        self.missing_long_enough()
        result, events = self.run_sync(READY='0', ATTACHED='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ['restart', 'notify:media stack: VPN still unavailable'])
        self.assertTrue((self.repo / 'state/port-forward-missing-since').exists())

    def test_successful_restart_reattaches_before_success_notice(self):
        self.missing_long_enough()
        result, events = self.run_sync(READY='0', ATTACHED='0', RECOVERS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ['restart', 'reattach', 'notify:media stack: VPN forwarded port restored'])
        self.assertFalse((self.repo / 'state/port-forward-missing-since').exists())

    def test_missing_tunnel_can_recover(self):
        self.missing_long_enough()
        result, events = self.run_sync(READY='0', TUNNEL='', PORT='', ATTACHED='0', RECOVERS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('reattach', events)

    def test_recreation_failure_stops_preferences_and_success_notice(self):
        result, events = self.run_sync(ATTACHED='0', REATTACH_OK='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ['reattach'])

    def test_invalid_preferences_never_write_guessed_defaults(self):
        for value in ['', 'Forbidden', '{}', '[]']:
            with self.subTest(value=value):
                result, events = self.run_sync(PREFS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(events, [])
                self.assertIn('refusing', result.stdout)

    def test_failed_preference_write_is_not_reported_as_verified(self):
        self.prefs['listen_port'] = 6881
        result, events = self.run_sync(WRITE_OK='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ['write'])
        self.assertNotIn('verified:', result.stdout)

    def test_restart_cooldown_still_applies(self):
        import time
        self.missing_long_enough()
        (self.repo / 'state/port-forward-last-heal').write_text(str(int(time.time())))
        result, events = self.run_sync(READY='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, [])

    def test_boot_and_update_defer_sync_until_healthy(self):
        probe = self.repo / 'scripts/sync-port'
        probe.write_text('#!/bin/sh\necho synced\n')
        probe.chmod(0o755)
        for name, marker in [('stack-up', 'if docker compose ps --status running'),
                             ('update', 'if [[ " ${recreate[*]} "')]:
            source = (ROOT / 'scripts' / name).read_text()
            start = source.index(marker)
            block = source[start:source.index('\nfi', start) + 3]
            for ready in ['0', '1']:
                with self.subTest(script=name, ready=ready):
                    prefix = '''REPO=$TEST_REPO
recreate=(gluetun)
docker() { echo gluetun; }
wait_gluetun_healthy() { [ "$READY" = 1 ]; }
'''
                    result = subprocess.run(['bash', '-c', prefix + block],
                                            env=dict(os.environ, TEST_REPO=str(self.repo), READY=ready),
                                            text=True, capture_output=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual('synced' in result.stdout, ready == '1')

    def test_actual_reattach_helper_guards_health_and_limits_scope(self):
        source = (ROOT / 'scripts/stack-env.sh').read_text()
        helper = source[source.index('reattach_vpn_apps() {'):]
        prefix = '''REPO=/unused
service_enabled() { [ "$MUSIC" = 1 ]; }
vpn_healthy() { [ "$READY" = 1 ]; }
vpn_apps_attached() { return 0; }
docker() { printf '%s\\n' "$*"; }
'''
        for ready, music, expected in [('0', '1', None), ('1', '0', 'qbittorrent'),
                                        ('1', '1', 'qbittorrent slskd')]:
            with self.subTest(ready=ready, music=music):
                result = subprocess.run(['bash', '-c', prefix + helper + '\nreattach_vpn_apps'],
                                        env=dict(os.environ, READY=ready, MUSIC=music),
                                        text=True, capture_output=True, check=False)
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('compose', result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('up -d --no-deps --force-recreate ' + expected, result.stdout)


if __name__ == '__main__':
    unittest.main()
