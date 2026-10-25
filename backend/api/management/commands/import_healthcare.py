import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import ImportedAdmission


class Command(BaseCommand):
    help = 'Import historical admissions from healthcare_dataset.csv in source-row order.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=Path)

    def handle(self, *args, **options):
        path = options['csv_path']
        if not path.is_file():
            raise CommandError(f'CSV file not found: {path}')
        expected = ['Name', 'Age', 'Gender', 'Blood Type', 'Medical Condition',
                    'Date of Admission', 'Doctor', 'Hospital', 'Insurance Provider',
                    'Billing Amount', 'Room Number', 'Admission Type', 'Discharge Date',
                    'Medication', 'Test Results']
        existing = set(ImportedAdmission.objects.values_list('source_row', flat=True))
        batch = []
        added = 0
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != expected:
                raise CommandError('CSV columns do not match the healthcare dataset format.')
            for row_number, row in enumerate(reader, start=2):
                if row_number in existing:
                    continue
                try:
                    amount = Decimal(row['Billing Amount']).quantize(Decimal('0.01'))
                    admission = ImportedAdmission(
                        source_row=row_number,
                        patient_name=row['Name'].strip().title(),
                        age=int(row['Age']), gender=row['Gender'].strip(),
                        blood_type=row['Blood Type'].strip(),
                        medical_condition=row['Medical Condition'].strip(),
                        admission_date=date.fromisoformat(row['Date of Admission']),
                        doctor_name=row['Doctor'].strip(), hospital=row['Hospital'].strip(),
                        insurance_provider=row['Insurance Provider'].strip(),
                        billing_amount=amount, room_number=row['Room Number'].strip(),
                        admission_type=row['Admission Type'].strip(),
                        discharge_date=date.fromisoformat(row['Discharge Date']) if row['Discharge Date'] else None,
                        medication=row['Medication'].strip(), test_results=row['Test Results'].strip(),
                    )
                except (ValueError, InvalidOperation) as exc:
                    raise CommandError(f'Invalid data on CSV row {row_number}: {exc}') from exc
                batch.append(admission)
                if len(batch) == 1000:
                    ImportedAdmission.objects.bulk_create(batch, batch_size=1000)
                    added += len(batch)
                    batch.clear()
        if batch:
            ImportedAdmission.objects.bulk_create(batch, batch_size=1000)
            added += len(batch)
        self.stdout.write(self.style.SUCCESS(f'Imported {added} admissions; total {ImportedAdmission.objects.count()}.'))
