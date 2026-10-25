"""Create a consistent SQLite snapshot without stopping the application."""
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create and integrity-check a new SQLite backup; never overwrite an existing backup.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=str(settings.BASE_DIR / 'private-backups'))

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        if database['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('Use your database provider backup service for non-SQLite databases.')
        source = Path(database['NAME']).resolve()
        if not source.is_file():
            raise CommandError('The source database does not exist.')
        directory = Path(options['output_dir']).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"medcore-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.sqlite3"
        # Exclusive creation prevents accidental replacement of another backup.
        with destination.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
                with closing(sqlite3.connect(destination)) as backup:
                    original.backup(backup)
                    if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise CommandError('Backup integrity check failed.')
        except Exception as error:
            raise CommandError(f'Backup failed; inspect incomplete file {destination}: {error}') from error
        self.stdout.write(self.style.SUCCESS(f'Backup verified: {destination}'))
