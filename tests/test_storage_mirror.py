import datetime
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_DATE = shutil.which('date')
NOW = int(datetime.datetime(2026, 10, 25, 12, tzinfo=datetime.timezone.utc).timestamp())
DAY = 86400


@unittest.skipUnless(shutil.which('rsync'), 'rsync is not installed')
class StorageMirrorTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)

        (self.root / 'scripts').mkdir()
        for script_name in ['stack-env.sh', 'storage-mirror']:
            shutil.copy(ROOT / 'scripts' / script_name, self.root / 'scripts' / script_name)

        self.storage = self.root / 'storage'
        self.backup = self.root / 'backup'
        self.data = self.storage / 'data'
        self.mount_log = self.root / 'mount.log'
        self.write_env(backup_uuid='backup-uuid')

        self.movie = self.data / 'media/movies/film.mkv'
        self.seeding_movie = self.data / 'torrents/movies/film.mkv'
        self.movie.parent.mkdir(parents=True)
        self.seeding_movie.parent.mkdir(parents=True)
        self.movie.write_text('film')
        os.link(self.movie, self.seeding_movie)

        for unfinished_download in ['usenet/incomplete/part.bin', 'soulseek/incomplete/song.flac']:
            (self.data / unfinished_download).parent.mkdir(parents=True)
            (self.data / unfinished_download).write_text('partial')

        (self.storage / 'lost+found').mkdir()
        (self.backup / 'lost+found').mkdir(parents=True)

        self.stub_directory = self.root / 'bin'
        self.stub_directory.mkdir()
        self.write_stub('mountpoint', '[ "$1" = -q ] && shift\ncase " $MOUNTED " in *" $1 "*) exit 0 ;; esac\nexit 1')
        self.write_stub('findmnt', 'for mount_path; do :; done\n'
                        'case "$mount_path" in "$STORAGE_PATH") echo "$STORAGE_FS_UUID" ;; "$BACKUP_PATH") echo "$BACKUP_FS_UUID" ;; esac')
        self.write_stub('mount', 'echo "$*" >> "$MOUNT_LOG"')
        self.write_stub('date', f'if [ "$1" = +%s ]; then echo "$FAKE_NOW"; else exec {REAL_DATE} "$@"; fi')

    def test_mirrors_with_hardlinks_and_skips_unfinished_downloads(self):
        mirror_result = self.run_mirror()

        self.assertEqual(mirror_result.returncode, 0, mirror_result.stderr)

        backup_movie = self.backup / 'data/media/movies/film.mkv'
        backup_seeding_movie = self.backup / 'data/torrents/movies/film.mkv'
        self.assertEqual(backup_movie.read_text(), 'film')
        self.assertEqual(backup_movie.stat().st_ino, backup_seeding_movie.stat().st_ino)

        self.assertFalse((self.backup / 'data/usenet/incomplete').exists())
        self.assertFalse((self.backup / 'data/soulseek/incomplete').exists())

        self.assertEqual(self.mount_log.read_text().splitlines(),
                         [f'-o remount,rw {self.backup}', f'-o remount,ro {self.backup}'])
        self.assertEqual((self.root / 'state/metrics/mirror.prom').read_text(),
                         f'arr_mirror_last_success_timestamp_seconds {NOW}\n')

    def test_deleted_and_overwritten_files_move_to_the_dated_trash(self):
        self.assertEqual(self.run_mirror().returncode, 0)

        self.seeding_movie.unlink()
        notes = self.data / 'media/movies/notes.txt'
        notes.write_text('new notes')
        next_day_result = self.run_mirror(now=NOW + DAY)

        self.assertEqual(next_day_result.returncode, 0, next_day_result.stderr)

        trash_day = self.backup / '.trash/2026-10-26/data'
        self.assertEqual((trash_day / 'torrents/movies/film.mkv').read_text(), 'film')
        self.assertFalse((self.backup / 'data/torrents/movies/film.mkv').exists())
        self.assertEqual((self.backup / 'data/media/movies/notes.txt').read_text(), 'new notes')

        notes.write_text('newer notes')
        self.assertEqual(self.run_mirror(now=NOW + 2 * DAY).returncode, 0)
        self.assertEqual((self.backup / '.trash/2026-10-27/data/media/movies/notes.txt').read_text(), 'new notes')

    def test_trash_older_than_30_days_is_removed(self):
        for trash_day_name in ['2026-09-24', '2026-09-25']:
            (self.backup / '.trash' / trash_day_name).mkdir(parents=True)
            (self.backup / '.trash' / trash_day_name / 'deleted.mkv').write_text('old')

        mirror_result = self.run_mirror()

        self.assertEqual(mirror_result.returncode, 0, mirror_result.stderr)
        self.assertFalse((self.backup / '.trash/2026-09-24').exists())
        self.assertTrue((self.backup / '.trash/2026-09-25/deleted.mkv').exists())
        self.assertIn('removed trash from 2026-09-24', mirror_result.stdout)

    def test_refuses_unless_both_named_drives_are_mounted_and_data_is_present(self):
        refusal_cases = {
            'backup not mounted': {'MOUNTED': str(self.storage)},
            'storage not mounted': {'MOUNTED': str(self.backup)},
            'another drive on the backup mount': {'BACKUP_FS_UUID': 'other-uuid'},
            'another drive on the storage mount': {'STORAGE_FS_UUID': 'other-uuid'},
        }

        for case_name, stub_environment in refusal_cases.items():
            with self.subTest(case_name=case_name):
                self.assert_refused(self.run_mirror(**stub_environment))

        with self.subTest(case_name='no BACKUP_UUID'):
            self.write_env(backup_uuid='')
            self.assert_refused(self.run_mirror())
            self.write_env(backup_uuid='backup-uuid')

        with self.subTest(case_name='empty data root'):
            shutil.rmtree(self.data)
            self.data.mkdir()
            self.assert_refused(self.run_mirror())

    def test_dry_run_changes_nothing(self):
        mirror_result = self.run_mirror('--dry-run')

        self.assertEqual(mirror_result.returncode, 0, mirror_result.stderr)
        self.assertIn('data/media/movies/film.mkv', mirror_result.stdout)
        self.assertFalse((self.backup / 'data').exists())
        self.assertFalse(self.mount_log.exists())
        self.assertFalse((self.root / 'state/metrics/mirror.prom').exists())

    def assert_refused(self, mirror_result):
        self.assertEqual(mirror_result.returncode, 1)
        self.assertIn('FATAL', mirror_result.stderr)
        self.assertFalse((self.backup / 'data').exists())
        self.assertFalse(self.mount_log.exists())

    def write_env(self, backup_uuid):
        (self.root / '.env').write_text(
            f'CONFIG_ROOT={self.root}/config\nSTORAGE_MOUNT={self.storage}\nBACKUP_MOUNT={self.backup}\n'
            f'DATA_ROOT={self.data}\nSTORAGE_UUID=storage-uuid\nBACKUP_UUID={backup_uuid}\n')

    def write_stub(self, command_name, body):
        stub_path = self.stub_directory / command_name
        stub_path.write_text(f'#!/bin/sh\n{body}\n')
        stub_path.chmod(0o755)

    def run_mirror(self, *arguments, now=NOW, **stub_environment):
        environment = {
            **os.environ,
            'PATH': f'{self.stub_directory}:{os.environ["PATH"]}',
            'TZ': 'UTC',
            'FAKE_NOW': str(now),
            'MOUNTED': f'{self.storage} {self.backup}',
            'STORAGE_PATH': str(self.storage),
            'BACKUP_PATH': str(self.backup),
            'STORAGE_FS_UUID': 'storage-uuid',
            'BACKUP_FS_UUID': 'backup-uuid',
            'MOUNT_LOG': str(self.mount_log),
            **stub_environment,
        }

        return subprocess.run(['bash', str(self.root / 'scripts/storage-mirror'), *arguments],
                              text=True, capture_output=True, env=environment, timeout=60)


if __name__ == '__main__':
    unittest.main()
