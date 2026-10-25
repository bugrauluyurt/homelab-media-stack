import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# apcaccess -u status from a Back-UPS ES 850G2 over USB, with the serial number replaced.
ONLINE_READINGS = '''APC      : 001,036,0866
DATE     : 2026-10-25 01:10:00 +0000
HOSTNAME : server
VERSION  : 3.14.14 (31 May 2016) debian
UPSNAME  : ups
CABLE    : USB Cable
DRIVER   : USB UPS Driver
UPSMODE  : Stand Alone
STARTTIME: 2026-10-25 01:00:00 +0000
MODEL    : Back-UPS ES 850G2
STATUS   : ONLINE
LINEV    : 119.0
LOADPCT  : 10.0
BCHARGE  : 100.0
TIMELEFT : 63.3
MBATTCHG : 10
MINTIMEL : 5
MAXTIME  : 0
SENSE    : Medium
LOTRANS  : 92.0
HITRANS  : 139.0
ALARMDEL : 30
BATTV    : 13.6
LASTXFER : No transfers since turnon
NUMXFERS : 2
TONBATT  : 0
CUMONBATT: 74
XOFFBATT : N/A
SELFTEST : NO
STATFLAG : 0x05000008
SERIALNO : 0B0000L00000
BATTDATE : 2026-06-23
NOMINV   : 120
NOMBATTV : 12.0
NOMPOWER : 450
FIRMWARE : 931.a10.D USB FW:a
END APC  : 2026-10-25 01:10:00 +0000
'''


class UpsTestCase(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

        (self.root / 'scripts').mkdir()
        for script_name in ['stack-env.sh', 'ups-event', 'ups-metrics']:
            shutil.copy(ROOT / 'scripts' / script_name, self.root / 'scripts' / script_name)
        (self.root / '.env').write_text(f'CONFIG_ROOT={self.root}/config\nNTFY_TOPIC=test-topic\n')

        self.readings = self.root / 'readings.txt'
        self.readings.write_text(ONLINE_READINGS)
        self.curl_log = self.root / 'curl.log'

        self.stub_directory = self.root / 'bin'
        self.stub_directory.mkdir()
        # -p NAME prints one value, as apcaccess does; no readings file means apcupsd is unreachable.
        self.write_stub('apcaccess', '[ -f "$READINGS" ] || exit 1\n'
                        'if [ "$2" = -p ]; then sed -n "s/^$3 *: *//p" "$READINGS"; else cat "$READINGS"; fi')
        self.write_stub('curl', 'printf "%s\\n" "$@" >> "$CURL_LOG"\nexit "${CURL_EXIT:-0}"')

    def write_stub(self, command_name, body):
        stub_path = self.stub_directory / command_name
        stub_path.write_text(f'#!/bin/sh\n{body}\n')
        stub_path.chmod(0o755)

    def run_script(self, script_path, **stub_environment):
        environment = {**os.environ, 'PATH': f'{self.stub_directory}:{os.environ["PATH"]}',
                       'READINGS': str(self.readings), 'CURL_LOG': str(self.curl_log), **stub_environment}

        return subprocess.run(['bash', str(script_path)], text=True, capture_output=True, env=environment, timeout=30)


class UpsMetricsTests(UpsTestCase):
    def test_readings_become_metrics(self):
        metrics_result = self.run_script(self.root / 'scripts/ups-metrics')

        self.assertEqual(metrics_result.returncode, 0, metrics_result.stderr)
        self.assertEqual(self.metrics(), [
            'arr_ups_up 1',
            'arr_ups_online 1',
            'arr_ups_on_battery 0',
            'arr_ups_battery_charge_percent 100',
            'arr_ups_runtime_seconds 3798',
            'arr_ups_load_percent 10',
            'arr_ups_input_voltage 119',
            'arr_ups_battery_voltage 13.6',
            'arr_ups_transfers_total 2',
            'arr_ups_on_battery_seconds_total 74',
            'arr_ups_shutdown_charge_percent 10',
            'arr_ups_shutdown_runtime_seconds 300',
            'arr_ups_load_watts 45',
        ])

    def test_on_battery_status_is_reported(self):
        self.readings.write_text(ONLINE_READINGS.replace('STATUS   : ONLINE', 'STATUS   : ONBATT'))

        self.run_script(self.root / 'scripts/ups-metrics')

        self.assertIn('arr_ups_online 0', self.metrics())
        self.assertIn('arr_ups_on_battery 1', self.metrics())

    def test_lost_ups_or_unreachable_apcupsd_writes_only_up_zero(self):
        for case_name in ['comm lost', 'apcupsd unreachable']:
            with self.subTest(case_name=case_name):
                if case_name == 'comm lost':
                    self.readings.write_text('STATUS   : COMMLOST\nMBATTCHG : 10\n')
                else:
                    self.readings.unlink()

                metrics_result = self.run_script(self.root / 'scripts/ups-metrics')

                self.assertEqual(metrics_result.returncode, 0, metrics_result.stderr)
                self.assertEqual(self.metrics(), ['arr_ups_up 0'])

    def metrics(self):
        return (self.root / 'state/metrics/ups.prom').read_text().splitlines()


class UpsEventTests(UpsTestCase):
    def test_event_comes_from_the_link_name(self):
        event_result = self.run_event('onbattery')

        self.assertEqual(event_result.returncode, 0, event_result.stderr)

        curl_arguments = self.curl_log.read_text()
        self.assertIn('Title: media stack: on battery', curl_arguments)
        self.assertIn('Battery 100%, about 63 min left.', curl_arguments)
        self.assertIn('shuts down at 5 min or 10% left', curl_arguments)

    def test_always_exits_zero_so_apccontrol_still_acts(self):
        for event_name in ['doshutdown', 'commfailure', 'not-an-event']:
            with self.subTest(event_name=event_name):
                self.assertEqual(self.run_event(event_name, CURL_EXIT='22').returncode, 0)

    def test_unknown_event_sends_nothing(self):
        self.run_event('powerout')

        self.assertFalse(self.curl_log.exists())

    def run_event(self, event_name, **stub_environment):
        event_link = self.root / 'apcupsd' / event_name
        event_link.parent.mkdir(exist_ok=True)
        event_link.unlink(missing_ok=True)
        event_link.symlink_to(self.root / 'scripts/ups-event')

        return self.run_script(event_link, **stub_environment)


if __name__ == '__main__':
    unittest.main()
