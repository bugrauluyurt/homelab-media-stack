import contextlib
import copy
import io
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
OPEN_SUBTITLES_GUID = '4b9ed42f518548b598036ff2989014c4'
PLUGIN_GUIDS = ['5e87cc92571a4d8d8d98d2d4147f9f90', '5b6550faa0144f4c8a2c59a43680ac6d',
                'b8298e012697407ab44daa8dc795e850', 'f69e946a4b3c4e9a8f0a8d7c1b2c4d9b',
                '91d87e32ea5f4d33830cb6eea8754064', 'f47b4d8874a2459aa0d6b211d773f89a',
                'bc4aad2ed3d04725a5e2fd07949e5b42', '170a157fac6c437aabddca9c25cebd39',
                '4fe3201ed6ae4f2e8917e12bda571281']
SUBTITLE_USERNAME = 'subtitle-user-test-only'
SUBTITLE_PASSWORD = 'subtitle-password-test-only'
VIEWER_PASSWORD = 'viewer-password-test-only'


class JellyfinApi:
    def __init__(self, *, subtitle_plugin_installed=False):
        self.plugin_statuses = {plugin_guid: 'Active' for plugin_guid in PLUGIN_GUIDS}

        if subtitle_plugin_installed:
            self.plugin_statuses[OPEN_SUBTITLES_GUID] = 'Active'

        self.configurations = {OPEN_SUBTITLES_GUID: {
            'Username': '', 'Password': '', 'CredentialsInvalid': False,
        }}
        self.repositories = []
        self.branding = {}
        self.system_configuration = {}
        self.install_requests = []
        self.policy_requests = []
        self.write_requests = []
        self.users = [
            {'Id': 'viewer', 'Name': 'viewer', 'Password': VIEWER_PASSWORD, 'Policy': {
                'IsAdministrator': False, 'IsDisabled': False, 'EnableSubtitleManagement': False,
                'EnableContentDeletion': False, 'EnableDownloads': True, 'BlockedTags': ['private'],
                'EnableAllFolders': False, 'EnabledFolders': ['movies-library'], 'CustomPolicy': {'keep': True},
            }},
            {'Id': 'admin', 'Name': 'admin', 'Policy': {
                'IsAdministrator': True, 'IsDisabled': False, 'EnableSubtitleManagement': False,
            }},
            {'Id': 'disabled', 'Name': 'disabled', 'Policy': {
                'IsAdministrator': False, 'IsDisabled': True, 'EnableSubtitleManagement': False,
            }},
        ]
        self.seerr_users = [{'id': 1, 'jellyfinUserId': 'viewer', 'permissions': 32}]

    def http(self, url, body=None, method=None, headers=None):
        request_url = urllib.parse.urlparse(url)
        request_path = request_url.path
        request_method = method or ('POST' if body is not None else 'GET')

        if request_method != 'GET':
            self.write_requests.append((request_path, copy.deepcopy(body), request_method))

        if request_path == '/Repositories':
            if body is not None:
                self.repositories = copy.deepcopy(body)

            return copy.deepcopy(self.repositories)

        if request_path == '/Plugins':
            return [{'Id': plugin_guid, 'Status': plugin_status}
                    for plugin_guid, plugin_status in self.plugin_statuses.items()]

        if request_path.startswith('/Packages/Installed/'):
            package_options = urllib.parse.parse_qs(request_url.query)
            plugin_guid = package_options['assemblyGuid'][0].replace('-', '')
            self.plugin_statuses[plugin_guid] = 'RestartRequired'
            self.install_requests.append((urllib.parse.unquote(request_path), package_options))

            return {}

        if request_path.startswith('/Plugins/') and request_path.endswith('/Configuration'):
            plugin_guid = request_path.split('/')[2]

            if body is not None:
                self.configurations[plugin_guid] = copy.deepcopy(body)

            return copy.deepcopy(self.configurations.get(plugin_guid, {'Sonarr': {}, 'Radarr': {}}))

        if request_path == '/System/Configuration/branding':
            if body is not None:
                self.branding = copy.deepcopy(body)

            return copy.deepcopy(self.branding)

        if request_path == '/System/Configuration':
            if body is not None:
                self.system_configuration = copy.deepcopy(body)

            return copy.deepcopy(self.system_configuration)

        if request_path == '/Library/VirtualFolders':
            return [{'CollectionType': 'movies', 'ItemId': 'movies-library'},
                    {'CollectionType': 'tvshows', 'ItemId': 'tv-library'}]

        if request_path == '/ScheduledTasks':
            return [{'Name': 'TMDb Box Sets', 'LastExecutionResult': {'Status': 'Completed'}}]

        if request_path == '/Users':
            return copy.deepcopy(self.users)

        if request_path == '/Users/New':
            self.users.append({'Id': 'new-viewer', 'Name': body['Name'], 'Password': body['Password'],
                               'Policy': {'EnableSubtitleManagement': False, 'CustomPolicy': {'keep': True}}})

            return copy.deepcopy(self.users[-1])

        if request_path.startswith('/Users/') and request_path.endswith('/Policy'):
            viewer_id = request_path.split('/')[2]
            viewer_user = next(viewer_user for viewer_user in self.users if viewer_user['Id'] == viewer_id)
            viewer_user['Policy'] = copy.deepcopy(body)
            self.policy_requests.append((viewer_id, copy.deepcopy(body)))

            return {}

        if request_path == '/api/v1/user':
            return {'results': copy.deepcopy(self.seerr_users)}

        if request_path == '/api/v1/user/import-from-jellyfin':
            self.seerr_users.append({'id': 2, 'jellyfinUserId': body['jellyfinUserIds'][0], 'permissions': 32})

            return {}

        raise AssertionError(f'Unexpected {request_method} request: {request_path}')

    def restart(self, command, **options):
        if command != ['docker', 'restart', 'jellyfin']:
            raise AssertionError(f'Unexpected command: {command}')

        self.plugin_statuses = {plugin_guid: 'Active' for plugin_guid in self.plugin_statuses}


class JellyfinSubtitleTests(unittest.TestCase):
    def test_credentials_install_official_plugin_and_only_grant_enabled_viewers(self):
        jellyfin_api = JellyfinApi()
        previous_users = copy.deepcopy(jellyfin_api.users)
        script_output, restart_calls = self._run_configure(jellyfin_api)

        self.assertEqual(len(jellyfin_api.install_requests), 1)
        package_path, package_options = jellyfin_api.install_requests[0]
        self.assertEqual(package_path, '/Packages/Installed/Open Subtitles')
        self.assertEqual(package_options['repositoryUrl'], ['https://repo.jellyfin.org/files/plugin/manifest.json'])
        self.assertEqual(package_options['assemblyGuid'], ['4b9ed42f-5185-48b5-9803-6ff2989014c4'])
        self.assertEqual(jellyfin_api.configurations[OPEN_SUBTITLES_GUID], {
            'Username': SUBTITLE_USERNAME, 'Password': SUBTITLE_PASSWORD, 'CredentialsInvalid': False,
        })
        self.assertEqual(jellyfin_api.users[0], {
            **previous_users[0], 'Policy': {**previous_users[0]['Policy'], 'EnableSubtitleManagement': True},
        })
        self.assertEqual(jellyfin_api.users[1:], previous_users[1:])
        self.assertEqual(restart_calls, 1)
        self.assertNotIn(SUBTITLE_USERNAME, script_output)
        self.assertNotIn(SUBTITLE_PASSWORD, script_output)
        self.assertNotIn(VIEWER_PASSWORD, script_output)

        jellyfin_api.write_requests.clear()
        jellyfin_api.install_requests.clear()
        jellyfin_api.policy_requests.clear()
        script_output, restart_calls = self._run_configure(jellyfin_api)

        self.assertEqual(jellyfin_api.write_requests, [])
        self.assertEqual(jellyfin_api.install_requests, [])
        self.assertEqual(jellyfin_api.policy_requests, [])
        self.assertEqual(restart_calls, 0)
        self.assertNotIn('  +', script_output)

    def test_missing_or_partial_credentials_do_not_install_configure_or_grant_viewers(self):
        for subtitle_credentials in [{}, {'OPENSUBTITLES_USER': SUBTITLE_USERNAME},
                                     {'OPENSUBTITLES_PASS': SUBTITLE_PASSWORD},
                                     {'OPENSUBTITLES_USER': '', 'OPENSUBTITLES_PASS': SUBTITLE_PASSWORD}]:
            for subtitle_plugin_installed in [False, True]:
                with self.subTest(subtitle_credentials=tuple(subtitle_credentials),
                                  subtitle_plugin_installed=subtitle_plugin_installed):
                    jellyfin_api = JellyfinApi(subtitle_plugin_installed=subtitle_plugin_installed)
                    previous_users = copy.deepcopy(jellyfin_api.users)
                    previous_configuration = {'Username': 'previous-user', 'Password': 'previous-password',
                                              'CredentialsInvalid': True, 'KeepSetting': True}
                    jellyfin_api.configurations[OPEN_SUBTITLES_GUID] = copy.deepcopy(previous_configuration)
                    script_output, restart_calls = self._run_configure(jellyfin_api, subtitle_credentials)

                    self.assertEqual(jellyfin_api.install_requests, [])
                    self.assertEqual(jellyfin_api.configurations[OPEN_SUBTITLES_GUID], previous_configuration)
                    self.assertEqual(jellyfin_api.users, previous_users)
                    self.assertEqual(jellyfin_api.policy_requests, [])
                    self.assertEqual(restart_calls, 0)
                    self.assertNotIn(SUBTITLE_USERNAME, script_output)
                    self.assertNotIn(SUBTITLE_PASSWORD, script_output)

    def test_changed_credentials_clear_invalid_flag_and_preserve_other_settings(self):
        for previous_username, previous_password in [('previous-user', SUBTITLE_PASSWORD),
                                                    (SUBTITLE_USERNAME, 'previous-password')]:
            with self.subTest(changed_username=previous_username != SUBTITLE_USERNAME):
                jellyfin_api = JellyfinApi(subtitle_plugin_installed=True)
                jellyfin_api.configurations[OPEN_SUBTITLES_GUID] = {
                    'Username': previous_username, 'Password': previous_password,
                    'CredentialsInvalid': True, 'KeepSetting': {'value': 'unchanged'},
                }
                self._run_configure(jellyfin_api)

                self.assertEqual(jellyfin_api.configurations[OPEN_SUBTITLES_GUID], {
                    'Username': SUBTITLE_USERNAME, 'Password': SUBTITLE_PASSWORD,
                    'CredentialsInvalid': False, 'KeepSetting': {'value': 'unchanged'},
                })

    def test_unchanged_credentials_do_not_clear_invalid_flag(self):
        jellyfin_api = JellyfinApi(subtitle_plugin_installed=True)
        subtitle_configuration = {'Username': SUBTITLE_USERNAME, 'Password': SUBTITLE_PASSWORD,
                                  'CredentialsInvalid': True, 'KeepSetting': {'value': 'unchanged'}}
        jellyfin_api.configurations[OPEN_SUBTITLES_GUID] = copy.deepcopy(subtitle_configuration)
        self._run_configure(jellyfin_api)

        self.assertEqual(jellyfin_api.configurations[OPEN_SUBTITLES_GUID], subtitle_configuration)
        self.assertFalse(any(request_path == f'/Plugins/{OPEN_SUBTITLES_GUID}/Configuration'
                             for request_path, _, _ in jellyfin_api.write_requests))

    def test_existing_viewer_add_grants_subtitles_without_changing_password(self):
        jellyfin_api = JellyfinApi()
        previous_viewer = copy.deepcopy(jellyfin_api.users[0])
        script_output = self._run_viewer_add(jellyfin_api, 'viewer', io.StringIO())

        self.assertTrue(jellyfin_api.users[0]['Policy']['EnableSubtitleManagement'])
        self.assertEqual(jellyfin_api.users[0]['Password'], previous_viewer['Password'])
        self.assertEqual(jellyfin_api.users[0]['Policy']['BlockedTags'], previous_viewer['Policy']['BlockedTags'])
        self.assertEqual(jellyfin_api.users[0]['Policy']['CustomPolicy'], previous_viewer['Policy']['CustomPolicy'])
        self.assertFalse(jellyfin_api.users[0]['Policy']['IsAdministrator'])
        self.assertFalse(jellyfin_api.users[0]['Policy']['EnableContentDeletion'])
        self.assertNotIn(VIEWER_PASSWORD, script_output)

        jellyfin_api.write_requests.clear()
        self._run_viewer_add(jellyfin_api, 'viewer', io.StringIO())

        self.assertEqual(jellyfin_api.write_requests, [])

    def test_new_viewer_add_enables_subtitles_and_keeps_media_deletion_disabled(self):
        jellyfin_api = JellyfinApi()
        script_output = self._run_viewer_add(jellyfin_api, 'new-viewer', io.StringIO(VIEWER_PASSWORD + '\n'))
        new_viewer = next(viewer_user for viewer_user in jellyfin_api.users if viewer_user['Id'] == 'new-viewer')

        self.assertTrue(new_viewer['Policy']['EnableSubtitleManagement'])
        self.assertFalse(new_viewer['Policy']['IsAdministrator'])
        self.assertFalse(new_viewer['Policy']['EnableContentDeletion'])
        self.assertEqual(new_viewer['Policy']['CustomPolicy'], {'keep': True})
        self.assertEqual(new_viewer['Password'], VIEWER_PASSWORD)
        self.assertNotIn(VIEWER_PASSWORD, script_output)

    def _run_configure(self, jellyfin_api, subtitle_credentials=None):
        script_environment = {'TAILSCALE_IP': '127.0.0.1', 'HOMEPAGE_ALLOWED_HOSTS': 'localhost:3000',
                              'SEERR_API_KEY': 'seerr-test-only'}
        script_environment.update(subtitle_credentials if subtitle_credentials is not None else {
            'OPENSUBTITLES_USER': SUBTITLE_USERNAME, 'OPENSUBTITLES_PASS': SUBTITLE_PASSWORD,
        })
        stack_environment = types.SimpleNamespace(ENV=script_environment, http=jellyfin_api.http,
                                                 jellyfin_headers=lambda: {'Authorization': 'test-only'})
        script_output = io.StringIO()

        with patch.dict(sys.modules, {'stack_env': stack_environment}), \
                patch('urllib.request.urlopen', return_value=io.BytesIO()), \
                patch('time.sleep', side_effect=AssertionError('Unexpected readiness wait')), \
                patch('subprocess.run', side_effect=jellyfin_api.restart) as restart_command, \
                contextlib.redirect_stdout(script_output):
            runpy.run_path(str(ROOT / 'scripts/configure-jellyfin-plugins.py'), run_name='__main__')

        return script_output.getvalue(), restart_command.call_count

    def _run_viewer_add(self, jellyfin_api, viewer_name, password_input):
        stack_environment = types.SimpleNamespace(ENV={'SEERR_API_KEY': 'seerr-test-only'},
                                                 http=jellyfin_api.http, jellyfin_headers=lambda: {},
                                                 enabled_services=lambda: set())
        games_accounts = types.SimpleNamespace(ensure=lambda *args: None, exists=lambda *args: False)
        script_output = io.StringIO()

        with patch.dict(sys.modules, {'stack_env': stack_environment, 'games_accounts': games_accounts}), \
                patch.object(sys, 'argv', ['viewer-add.py', viewer_name]), \
                patch.object(sys, 'stdin', password_input), \
                contextlib.redirect_stdout(script_output):
            with self.assertRaises(SystemExit) as script_exit:
                runpy.run_path(str(ROOT / 'scripts/viewer-add.py'), run_name='__main__')

        self.assertIsNone(script_exit.exception.code)

        return script_output.getvalue()
