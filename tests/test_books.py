import json
import os
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class BooksComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {k: v for k, v in os.environ.items() if not k.startswith('COMPOSE_')}
        env.update(COMPOSE_PROFILES='*', DATA_ROOT='/tmp/books-data', CONFIG_ROOT='/tmp/books-config')
        cls.services = json.loads(subprocess.check_output(
            ['docker', 'compose', '--env-file', str(ROOT / '.env.example'),
             '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json'],
            env=env, text=True))['services']

    def test_profile_auth_and_loopback_only(self):
        for name in ['shelfmark', 'calibre-web-automated']:
            service = self.services[name]
            self.assertEqual(service['profiles'], ['books'])
            self.assertGreater(int(service['mem_limit']), 0)
            self.assertTrue(service['healthcheck']['test'])
            self.assertTrue(all(p['host_ip'] == '127.0.0.1' for p in service['ports']))
            self.assertNotIn(':latest', service['image'])
        self.assertEqual(self.services['shelfmark']['environment']['AUTH_METHOD'], 'builtin')
        self.assertEqual(self.services['shelfmark']['environment']['OPENLIBRARY_ENABLED'], 'true')
        self.assertEqual(self.services['shelfmark']['environment']['METADATA_PROVIDER'], 'openlibrary')

    def test_downloader_boundary_and_non_destructive_import(self):
        env = self.services['shelfmark']['environment']
        self.assertEqual(env['QBITTORRENT_URL'], 'http://gluetun:8080')
        self.assertEqual(env['SABNZBD_URL'], 'http://sabnzbd:8080')
        self.assertEqual(env['PROWLARR_TORRENT_ACTION'], 'keep')
        self.assertEqual(env['PROWLARR_USENET_ACTION'], 'copy')
        self.assertEqual(env['HARDLINK_TORRENTS'], 'false')
        self.assertEqual(self.services['qbittorrent']['network_mode'], 'service:gluetun')
        mounts = {v['target']: v for v in self.services['shelfmark']['volumes']}
        for target in ['/data/torrents/books', '/data/usenet/complete/books', '/calibre-library']:
            self.assertTrue(mounts[target]['read_only'])
            self.assertFalse(mounts[target]['bind']['create_host_path'])
        cwa = {v['target']: v for v in self.services['calibre-web-automated']['volumes']}
        self.assertEqual(cwa['/cwa-book-ingest']['source'], mounts['/books']['source'])
        self.assertNotEqual(cwa['/cwa-book-ingest']['source'], mounts['/data/torrents/books']['source'])
        self.assertEqual(set(cwa), {'/config', '/cwa-book-ingest', '/calibre-library'})


class BooksBackupTests(unittest.TestCase):
    def test_catalogue_online_snapshot_without_book_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            library = data / 'media/books'
            library.mkdir(parents=True)
            (library / 'example.epub').write_bytes(b'not a settings backup')
            db = sqlite3.connect(library / 'metadata.db')
            db.execute('pragma journal_mode=wal')
            db.execute('create table books (title text)')
            db.execute("insert into books values ('Example')")
            db.commit()
            config = root / 'config'
            config.mkdir()
            stub = types.ModuleType('stack_env')
            stub.CONFIG, stub.STATE, stub.REPO, stub.STORAGE = config, root / 'state', root / 'repo', root
            stub.ENV = {'STACK_USER': 'root', 'DATA_ROOT': str(data), 'RESTIC_PASSWORD': 'test-only', 'HOST_NAME': 'test'}
            stub.enabled_services = lambda: ['calibre-web-automated']
            try:
                with patch.dict(sys.modules, stack_env=stub):
                    module = runpy.run_path(str(ROOT / 'scripts/stack-backup'))
                main = module['main']
                scope = main.__globals__
                stage = root / 'stage'
                observed = []

                def restic(*args, **kwargs):
                    if args[0] == 'backup':
                        with sqlite3.connect(stage / 'books/metadata.db') as saved:
                            observed.extend(saved.execute('select title from books').fetchall())
                        self.assertFalse(list(stage.rglob('*.epub')))
                    return types.SimpleNamespace(stdout='snapshot test saved\n', returncode=0)

                scope.update(STAGE=stage, STATE=root / 'state/last-success', EXTRA=[], HOST_FILES=[],
                             MIRROR=root / 'mirror/restic', OFFSITE=None, restic=restic,
                             forget=lambda *a: None, copy_to=lambda *a: None, write_backup_metric=lambda: None)
                with patch('os.path.ismount', return_value=True):
                    main([])
                self.assertEqual(observed, [('Example',)])
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
