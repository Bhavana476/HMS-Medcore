"""Copy the application's current Django records to MongoDB Atlas."""

import os
from datetime import date, datetime, time
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError


def mongo_value(value):
    """Preserve Django field values in BSON-compatible form."""
    if isinstance(value, Decimal):
        from bson.decimal128 import Decimal128
        return Decimal128(value)
    if isinstance(value, (date, time)) and not isinstance(value, datetime):
        return value.isoformat()
    return value


def mongo_document(instance):
    document = {'_id': instance.pk}
    for field in instance._meta.concrete_fields:
        if field.primary_key:
            continue
        document[field.attname] = mongo_value(getattr(instance, field.attname))
    for field in instance._meta.many_to_many:
        document[field.name] = list(getattr(instance, field.name).values_list('pk', flat=True))
    return document


class Command(BaseCommand):
    help = 'Upsert all MedCore application records into MongoDB collections.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default=os.getenv('MONGODB_DB_NAME', 'medcore_hms'))
        parser.add_argument('--dry-run', action='store_true', help='Validate every record without connecting or writing.')

    def handle(self, *args, **options):
        if options['dry_run']:
            try:
                from bson import BSON
                total = 0
                for model in apps.get_app_config('api').get_models():
                    count = 0
                    for instance in model.objects.order_by('pk').iterator(chunk_size=1000):
                        BSON.encode(mongo_document(instance))
                        count += 1
                    self.stdout.write(f'{model._meta.db_table}: {count} records validated')
                    total += count
            except Exception:
                raise CommandError('MongoDB export validation failed; check dependencies and source data.') from None
            self.stdout.write(self.style.SUCCESS(f'Validated {total} records.'))
            return
        uri = os.getenv('MONGODB_URI', '')
        if not uri or '<' in uri or '>' in uri:
            raise CommandError('Set MONGODB_URI with a complete Atlas database username and password.')
        try:
            from pymongo import MongoClient, ReplaceOne
            from pymongo.server_api import ServerApi
            client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
            client.admin.command('ping')
        except Exception:
            raise CommandError('MongoDB connection failed. Check the URI, database user, and Atlas network access.') from None

        database = client[options['database']]
        counts = {}
        try:
            for model in apps.get_app_config('api').get_models():
                name = model._meta.db_table
                collection = database[name]
                operations = []
                count = 0
                for instance in model.objects.order_by('pk').iterator(chunk_size=1000):
                    document = mongo_document(instance)
                    operations.append(ReplaceOne({'_id': document['_id']}, document, upsert=True))
                    if len(operations) == 1000:
                        collection.bulk_write(operations, ordered=False)
                        count += len(operations)
                        operations.clear()
                if operations:
                    collection.bulk_write(operations, ordered=False)
                    count += len(operations)
                remote_count = collection.count_documents({})
                if remote_count < count:
                    raise RuntimeError('Remote collection count is smaller than the source count.')
                counts[name] = count
                self.stdout.write(f'{name}: {count} records copied; {remote_count} in Atlas')
        except Exception:
            raise CommandError('MongoDB export stopped. Check source data and Atlas write permissions; rerun is safe.') from None
        finally:
            client.close()
        self.stdout.write(self.style.SUCCESS(f'Exported {sum(counts.values())} records from {len(counts)} models.'))
