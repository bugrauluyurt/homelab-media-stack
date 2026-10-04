import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VpnFailoverComposeTests(unittest.TestCase):
    def test_default_keeps_custom_provider(self):
        compose_services = self.get_compose_services([])

        self.assertEqual(compose_services['gluetun']['environment']['VPN_SERVICE_PROVIDER'], 'custom')
        self.assertEqual(compose_services['gluetun']['image'], 'qmcgaw/gluetun:latest')
        self.assertNotIn('SERVER_NAMES', compose_services['gluetun']['environment'])

    def test_failover_keeps_network_and_security_settings(self):
        default_services = self.get_compose_services([])
        failover_services = self.get_compose_services(['compose.vpn-failover.yml'])
        gluetun_service = failover_services['gluetun']
        gluetun_environment = gluetun_service['environment']

        self.assertEqual(gluetun_environment['VPN_SERVICE_PROVIDER'], 'protonvpn')
        self.assertEqual(gluetun_environment['SERVER_COUNTRIES'], 'Netherlands')
        self.assertEqual(gluetun_environment['SERVER_NAMES'], 'NL#1,NL#2')
        self.assertEqual(gluetun_environment['SERVER_SELECTION_MODE'], 'ordered')
        self.assertEqual(gluetun_environment['PORT_FORWARD_ONLY'], 'on')
        self.assertEqual(gluetun_environment['SECURE_CORE_ONLY'], 'off')
        self.assertEqual(gluetun_environment['FREE_ONLY'], 'off')
        self.assertEqual(gluetun_environment['UPDATER_PERIOD'], '0')
        self.assertEqual(gluetun_environment['STORAGE_SERVERS_DIRECTORY_PATH'], '/gluetun/verified-servers')
        self.assertEqual(gluetun_service['entrypoint'], ['/bin/sh', '/gluetun/start-failover.sh'])
        self.assertEqual(
            gluetun_service['image'],
            'qmcgaw/gluetun@sha256:2733bb22b27e3efa7a9f2cef9057ec12791b8b225793fcd3dbfd0508404dfc25',
        )

        for environment_key, environment_value in default_services['gluetun']['environment'].items():
            if environment_key != 'VPN_SERVICE_PROVIDER':
                self.assertEqual(gluetun_environment[environment_key], environment_value)

        for service_key in ['ports', 'networks', 'sysctls', 'cap_add', 'devices', 'healthcheck']:
            self.assertEqual(gluetun_service[service_key], default_services['gluetun'][service_key])

        for service_name in ['qbittorrent', 'slskd']:
            self.assertEqual(failover_services[service_name], default_services[service_name])
            self.assertEqual(failover_services[service_name]['network_mode'], 'service:gluetun')

    def test_required_mounts_mask_the_old_peer_and_allow_catalog_writes(self):
        compose_services = self.get_compose_services(['compose.vpn-failover.yml'])
        gluetun_volumes = {
            volume['target']: volume for volume in compose_services['gluetun']['volumes']
        }
        required_sources = {
            '/gluetun/wireguard/wg0.conf': str(ROOT / 'apps/gluetun/failover-wg0.conf'),
            '/gluetun/start-failover.sh': str(ROOT / 'apps/gluetun/start-failover.sh'),
        }

        for mount_target, mount_source in required_sources.items():
            with self.subTest(mount_target=mount_target):
                mount_configuration = gluetun_volumes[mount_target]

                self.assertEqual(mount_configuration['type'], 'bind')
                self.assertEqual(mount_configuration['source'], mount_source)
                self.assertTrue(mount_configuration['read_only'])
                self.assertFalse(mount_configuration['bind'].get('create_host_path', False))

        self.assertEqual(gluetun_volumes['/gluetun']['source'], '/tmp/test-vpn-config/gluetun')
        self.assertTrue(gluetun_volumes['/gluetun/auth/config.toml']['read_only'])

        server_directory_mount = gluetun_volumes['/gluetun/verified-servers']

        self.assertEqual(server_directory_mount['type'], 'bind')
        self.assertEqual(server_directory_mount['source'], '/tmp/test-vpn-config/gluetun/verified-servers')
        self.assertFalse(server_directory_mount.get('read_only', False))
        self.assertFalse(server_directory_mount['bind'].get('create_host_path', False))
        self.assertNotIn('/gluetun/verified-servers/manifest.json', gluetun_volumes)
        self.assertNotIn('/gluetun/verified-servers/protonvpn.json', gluetun_volumes)

        seed_configuration = (ROOT / 'apps/gluetun/failover-wg0.conf').read_text()

        for forbidden_setting in ['PrivateKey', 'PublicKey', 'Endpoint']:
            self.assertNotIn(forbidden_setting, seed_configuration)

        self.assertIn('Address = 10.2.0.2/32', seed_configuration)
        self.assertIn('AllowedIPs = 0.0.0.0/0', seed_configuration)

    def test_failover_and_gpu_overrides_combine(self):
        compose_services = self.get_compose_services(['compose.gpu.yml', 'compose.vpn-failover.yml'])

        self.assertEqual(compose_services['gluetun']['environment']['SERVER_SELECTION_MODE'], 'ordered')

        for service_name in ['jellyfin', 'plex']:
            self.assertIn(
                {'source': '/dev/dri', 'target': '/dev/dri', 'permissions': 'rwm'},
                compose_services[service_name]['devices'],
            )

    def test_empty_selectors_refuse_configuration(self):
        for selector_name in ['VPN_COUNTRIES', 'VPN_SERVER_NAMES']:
            with self.subTest(selector_name=selector_name):
                compose_result = self.run_compose(['compose.vpn-failover.yml'], {selector_name: ''})

                self.assertNotEqual(compose_result.returncode, 0)
                self.assertIn(selector_name, compose_result.stderr)

    def get_compose_services(self, override_files):
        compose_result = self.run_compose(override_files, {})

        self.assertEqual(compose_result.returncode, 0, compose_result.stderr)

        return json.loads(compose_result.stdout)['services']

    @staticmethod
    def run_compose(override_files, environment_overrides):
        compose_command = ['docker', 'compose', '--env-file', '.env.example', '-f', 'docker-compose.yml']

        for override_file in override_files:
            compose_command.extend(['-f', override_file])

        compose_command.extend(['config', '--format', 'json'])
        compose_environment = dict(
            os.environ,
            COMPOSE_PROFILES='*',
            CONFIG_ROOT='/tmp/test-vpn-config',
            VPN_COUNTRIES='Netherlands',
            VPN_SERVER_NAMES='NL#1,NL#2',
        )
        compose_environment.update(environment_overrides)

        return subprocess.run(
            compose_command,
            cwd=ROOT,
            env=compose_environment,
            text=True,
            capture_output=True,
            check=False,
        )
