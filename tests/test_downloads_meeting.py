import importlib.machinery
import importlib.util
import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
import unittest
from pathlib import Path

loader = importlib.machinery.SourceFileLoader('meeting', str(Path(__file__).resolve().parents[1] / 'scripts/downloads-meeting'))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class MeetingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'meeting.json'
        self.torrents = [{'hash': 'active', 'state': 'uploading'}, {'hash': 'manual', 'state': 'stoppedUP'}]
        self.pref = False
        self.now = 1000
        self.fail_stop = False
        self.controller = module.Meeting(self.path, self.api, lambda: self.now)

    def api(self, path, form=None):
        if path == '/torrents/info':
            return [dict(t) for t in self.torrents]
        if path == '/app/preferences':
            return {'add_stopped_enabled': self.pref}
        if path == '/app/setPreferences':
            self.pref = json.loads(form['json'])['add_stopped_enabled']
        if path == '/torrents/stop':
            if self.fail_stop:
                raise OSError('offline')
            for torrent in self.torrents:
                if not module.Meeting.stopped(torrent):
                    torrent['state'] = 'stoppedUP'
        if path == '/torrents/start':
            for torrent in self.torrents:
                if torrent['hash'] in form['hashes'].split('|'):
                    torrent['state'] = 'uploading'

    def test_pause_resume_preserves_manual_stops(self):
        self.controller.change('on')
        self.assertTrue(self.controller.status()['confirmed'])
        self.assertTrue(self.pref)
        self.controller.change('off')
        self.assertEqual([t['state'] for t in self.torrents], ['uploading', 'stoppedUP'])
        self.assertFalse(self.pref)

    def test_failed_stop_is_journaled_and_recovers_after_restart(self):
        self.fail_stop = True
        self.controller.change('on')
        self.assertFalse(self.controller.status()['confirmed'])
        self.assertEqual(json.loads(self.path.read_text())['resume'], ['active'])
        self.fail_stop = False
        restarted = module.Meeting(self.path, self.api, lambda: self.now)
        restarted.reconcile()
        restarted.change('off')
        self.assertEqual(self.torrents[0]['state'], 'uploading')

    def test_new_transfers_are_enforced_and_restored(self):
        self.controller.change('on')
        self.torrents.append({'hash': 'new', 'state': 'downloading'})
        self.controller.reconcile()
        self.assertTrue(all(t['state'] == 'stoppedUP' for t in self.torrents))
        self.controller.change('off')
        self.assertEqual(self.torrents[-1]['state'], 'uploading')

    def test_repeated_on_keeps_original_preferences(self):
        self.controller.change('on')
        self.controller.change('on')
        self.controller.change('off')
        self.assertFalse(self.pref)

    def test_expiry_uses_controlled_clock(self):
        self.controller.change('on', 3600)
        self.now += 3599
        self.controller.reconcile()
        self.assertTrue(self.controller.status()['enabled'])
        self.now += 1
        self.controller.reconcile()
        self.assertFalse(self.controller.status()['enabled'])

    def test_resume_failure_keeps_pending_state(self):
        self.controller.change('on')
        original = self.controller.api

        def fail(path, form=None):
            if path == '/torrents/start':
                raise OSError()
            return original(path, form)

        self.controller.api = fail
        self.controller.change('off')
        self.assertEqual(json.loads(self.path.read_text())['phase'], 'off')
        self.controller.api = original
        self.controller.reconcile()
        self.assertIsNone(json.loads(self.path.read_text()))

    def test_new_already_stopped_torrent_stays_stopped(self):
        self.controller.change('on')
        self.torrents.append({'hash': 'new', 'state': 'stoppedDL'})
        self.controller.reconcile()
        self.controller.change('off')
        self.assertEqual(self.torrents[-1]['state'], 'stoppedDL')


class ControlSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.controller = module.Meeting(Path(self.tmp.name) / 'state.json', lambda *_args: [])
        self.controller.confirmed = True
        self.server = HTTPServer(('127.0.0.1', 0), module.handler(self.controller, {'meeting.test:4536'}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def request(self, path, headers, data=None):
        request = urllib.request.Request(self.url + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def test_get_never_changes_state(self):
        code, body = self.request('/status', {'Host': 'meeting.test:4536'})
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(body)['enabled'])
        self.assertIsNone(self.controller.state)

    def test_untrusted_host_refused(self):
        self.assertEqual(self.request('/', {'Host': 'evil.test'})[0], 403)

    def test_post_requires_origin_and_token(self):
        for headers in ({'Host': 'meeting.test:4536'},
                        {'Host': 'meeting.test:4536', 'Origin': 'http://evil.test'},
                        {'Host': 'meeting.test:4536', 'Origin': 'http://meeting.test:4536'}):
            self.assertEqual(self.request('/mode', headers, b'{"mode":"on"}')[0], 403)
        self.assertIsNone(self.controller.state)
