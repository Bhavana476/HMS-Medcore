import json
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from api.models import Appointment, AppointmentReminder, Notification, CommunicationPreference
from api.integrations import send_sms,sms_ready,ProviderUnavailable

class Command(BaseCommand):
    help='24-hour and 1-hour reminders; external delivery requires patient opt-in and provider configuration.'
    def add_arguments(self,parser):
        parser.add_argument('--email',action='store_true')
        parser.add_argument('--sms',action='store_true')
        parser.add_argument('--dry-run',action='store_true')
    def due(self):
        """Yield (appointment, kind). Run every 15 minutes so the 1-hour window is never missed."""
        active=Appointment.objects.filter(status__in=['Pending','Confirmed']).select_related('patient__user')
        for appointment in active.filter(date=timezone.localdate()+timedelta(days=1)): yield appointment,'24H'
        now=timezone.localtime()
        for appointment in active.filter(date=now.date(),status='Confirmed'):
            starts=timezone.make_aware(datetime.combine(appointment.date,appointment.time))
            if now<starts<=now+timedelta(minutes=75): yield appointment,'1H'
    def handle(self,*args,**options):
        count=0
        for appointment,kind in self.due():
            if not appointment.patient.user_id: continue
            user=appointment.patient.user
            preference=CommunicationPreference.objects.filter(user=user).first()
            channels=['app']
            if options['email'] and preference and preference.email_reminders and user.email and settings.EMAIL_BACKEND=='django.core.mail.backends.smtp.EmailBackend' and settings.EMAIL_HOST: channels.append('email')
            if options['sms'] and preference and preference.sms_reminders and sms_ready(): channels.append('sms')
            for channel in channels:
                key=dict(appointment=appointment,scheduled_date=appointment.date,scheduled_time=appointment.time,channel=channel,kind=kind)
                if AppointmentReminder.objects.filter(**key).exists(): continue
                count+=1
                if options['dry_run']: continue
                with transaction.atomic():
                    reminder,created=AppointmentReminder.objects.get_or_create(**key,defaults={'state':'SENDING'})
                    if not created: continue
                    message=f'Your appointment #{appointment.pk} is on {appointment.date} at {appointment.time.strftime("%H:%M")}. Sign in to MedCore for details.'
                    if channel=='app':
                        Notification.objects.create(user=user,title='Appointment in 1 hour' if kind=='1H' else 'Upcoming appointment',message=message)
                        reminder.state='SENT';reminder.save(update_fields=['state'])
                if channel=='app': continue
                # A timeout can follow successful submission. Do not blindly resend.
                try:
                    message=f'MedCore reminder: you have an appointment on {appointment.date} at {appointment.time.strftime("%H:%M")}. Sign in to your patient portal for details.'
                    if channel=='email':
                        if send_mail('MedCore appointment reminder',message,settings.DEFAULT_FROM_EMAIL,[user.email])!=1: raise ProviderUnavailable('Email not confirmed.')
                    else: reminder.provider_reference=send_sms(user.phone or appointment.patient.phone,message)
                    reminder.state='SUBMITTED'
                    reminder.save(update_fields=['state','provider_reference'])
                except Exception:
                    reminder.state='UNKNOWN';reminder.last_error='Delivery not confirmed. Check the provider before retrying.'
                    reminder.save(update_fields=['state','last_error'])
        if not options['dry_run']:
            path=settings.REMINDER_HEARTBEAT_PATH
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix('.tmp')
            temp.write_text(json.dumps({'last_run':timezone.now().isoformat()}))
            temp.replace(path)
        self.stdout.write(f'{count} reminder(s) '+('would be created.' if options['dry_run'] else 'processed.'))
