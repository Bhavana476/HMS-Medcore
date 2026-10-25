from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from api.models import Doctor, Patient, ImportedAdmission


class Command(BaseCommand):
    help='Distribute visible patient directory entries evenly across active registered doctors.'

    @transaction.atomic
    def handle(self, *args, **options):
        doctors=list(Doctor.objects.filter(user__is_active=True,deleted_at__isnull=True).order_by('pk'))
        if not doctors:
            raise CommandError('No active registered doctors are available.')
        counts={doctor.pk:0 for doctor in doctors}
        index=0
        for model,ordering in [(Patient,('-created_at','-id')),(ImportedAdmission,('-admission_date','-source_row'))]:
            batch=[]
            for patient in model.objects.filter(directory_hidden=False).order_by(*ordering).iterator(chunk_size=1000):
                doctor=doctors[index%len(doctors)]
                patient.primary_doctor_id=doctor.pk
                counts[doctor.pk]+=1
                index+=1
                batch.append(patient)
                if len(batch)==1000:
                    model.objects.bulk_update(batch,['primary_doctor'],batch_size=250)
                    batch=[]
            if batch:
                model.objects.bulk_update(batch,['primary_doctor'],batch_size=250)
        self.stdout.write(f'Assigned {index} patient entries across {len(doctors)} doctors; each has {min(counts.values())}–{max(counts.values())} entries.')
