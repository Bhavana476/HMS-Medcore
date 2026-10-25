import io
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class BackupRecoveryTests(SimpleTestCase):
    def test_snapshot_can_be_restored_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.sqlite3'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, document BLOB)')
                connection.execute('INSERT INTO records VALUES (?, ?)', (1, b'test-only-document'))
                connection.commit()
            database = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': source}}
            with override_settings(DATABASES=database):
                call_command('backup_database', output_dir=str(root / 'backups'), stdout=io.StringIO())
                call_command('backup_database', output_dir=str(root / 'backups'), stdout=io.StringIO())
            snapshots = list((root / 'backups').glob('*.sqlite3'))
            self.assertEqual(len(snapshots), 2)
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('INSERT INTO records VALUES (?, ?)', (2, b'later-change'))
                connection.commit()
            restored = root / 'restored.sqlite3'
            shutil.copyfile(snapshots[0], restored)
            with closing(sqlite3.connect(restored)) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                self.assertEqual(connection.execute('SELECT * FROM records').fetchall(), [(1, b'test-only-document')])
            with closing(sqlite3.connect(source)) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM records').fetchone()[0], 2)

    def test_missing_database_does_not_create_empty_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': root / 'missing.sqlite3'}}
            with override_settings(DATABASES=database), self.assertRaises(CommandError):
                call_command('backup_database', output_dir=str(root / 'backups'), stdout=io.StringIO())
            self.assertFalse((root / 'backups').exists())
