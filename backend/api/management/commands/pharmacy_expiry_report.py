from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import MedicineBatch, Notification
from api.operations import pharmacy_alerts

class Command(BaseCommand):
    help='Nightly job: quarantine expired batches and report stock expiring within 30 days to pharmacists and admins.'
    def add_arguments(self,parser):
        parser.add_argument('--days',type=int,default=30)
        parser.add_argument('--email',action='store_true')
    def handle(self,*args,**options):
        quarantined=MedicineBatch.objects.filter(expiry_date__lte=timezone.localdate(),quarantined=False).update(quarantined=True)
        alerts=pharmacy_alerts(options['days'])
        lines=[f"{b['medicine_name']} batch {b['batch_number']}: {b['quantity']} units, expires {b['expiry_date']}" for b in alerts['expiring']]
        lines+=[f"LOW STOCK {m['name']}: {m['stock']} (reorder at {m['reorder_level']})" for m in alerts['low_stock']]
        recipients=get_user_model().objects.filter(role__in=['PHARMACIST','ADMIN'],is_active=True)
        if lines:
            body='\n'.join(lines)
            for user in recipients:
                Notification.objects.create(user=user,title='Pharmacy stock report',message=body[:2000])
            if options['email']:
                emails=[u.email for u in recipients if u.email]
                if emails: send_mail('MedCore pharmacy stock report',body,settings.DEFAULT_FROM_EMAIL,emails)
        self.stdout.write(f'{quarantined} batch(es) quarantined; {len(lines)} alert line(s) reported.')
