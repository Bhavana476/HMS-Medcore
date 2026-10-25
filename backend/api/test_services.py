import hashlib,hmac,json,tempfile
from pathlib import Path
from datetime import timedelta,time
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Doctor,Patient,Appointment,Bill,Payment,PaymentCheckout,CareThread,CareMessage,CommunicationPreference,AppointmentReminder
from .integrations import ProviderUnavailable

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ServicesTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.patient_user=User.objects.create_user('servicepatient',password='Patient-test-738',role='PATIENT',email='p@example.test',phone='+919876543210')
        self.doctor_user=User.objects.create_user('servicedoctor',password='Doctor-test-738',role='DOCTOR')
        self.other_user=User.objects.create_user('serviceother',password='Other-test-738',role='PATIENT')
        self.admin=User.objects.create_user('serviceadmin',password='Admin-test-738',role='ADMIN')
        self.patient=Patient.objects.create(user=self.patient_user,patient_id='S1',full_name='Service Patient',gender='Other',phone='+919876543210')
        self.other=Patient.objects.create(user=self.other_user,patient_id='S2',full_name='Other Patient',gender='Other',phone='+919876543211')
        self.doctor=Doctor.objects.create(user=self.doctor_user,doctor_id='SD1',specialization='General Medicine')
        self.appointment=Appointment.objects.create(patient=self.patient,doctor=self.doctor,date=timezone.localdate()+timedelta(days=1),time=time(10),status='Confirmed')
        self.bill=Bill.objects.create(patient=self.patient,consultation_fee=100)
        self.client=APIClient();self.client.force_authenticate(self.patient_user)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        settings=override_settings(REMINDER_HEARTBEAT_PATH=Path(self.temp.name)/'heartbeat.json');settings.enable();self.addCleanup(settings.disable)

    def test_messaging_authenticated_workflow_and_cross_patient_isolation(self):
        self.client.force_authenticate(None)
        token=self.client.post('/api/login/',{'username':'servicepatient','password':'Patient-test-738'}).data['access']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        created=self.client.post('/api/care-threads/',{'patient':self.patient.pk,'doctor':self.doctor.pk})
        self.assertEqual(created.status_code,201,created.data);thread=created.data['id']
        message=self.client.post('/api/care-messages/',{'thread':thread,'body':'Can we discuss my next visit?','sender':self.admin.pk})
        self.assertEqual(message.status_code,201);self.assertEqual(message.data['sender'],self.patient_user.pk)
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(self.client.get('/api/care-messages/',{'thread':thread}).data['count'],1)
        self.assertEqual(self.client.post('/api/care-messages/',{'thread':thread,'body':'Yes, at your next appointment.'}).status_code,201)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get('/api/care-messages/',{'thread':thread}).status_code,404)
        self.assertEqual(self.client.post('/api/care-messages/',{'thread':thread,'body':'Not my thread'}).status_code,404)
        self.assertEqual(self.client.get('/api/care-threads/').data,[])

    def test_unlinked_thread_and_oversized_message_rejected(self):
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post('/api/care-threads/',{'patient':self.other.pk,'doctor':self.doctor.pk}).status_code,400)
        self.client.force_authenticate(self.patient_user)
        thread=CareThread.objects.create(patient=self.patient,doctor=self.doctor)
        self.assertEqual(self.client.post('/api/care-messages/',{'thread':thread.pk,'body':'a'*4001}).status_code,400)
        self.assertEqual(self.client.post('/api/care-messages/',{'thread':thread.pk,'body':'   '}).status_code,400)

    def test_preferences_are_per_user(self):
        self.assertFalse(self.client.get('/api/communication-preferences/').data['sms_reminders'])
        self.assertEqual(self.client.patch('/api/communication-preferences/',{'sms_reminders':True}).status_code,200)
        self.client.force_authenticate(self.other_user)
        self.assertFalse(self.client.get('/api/communication-preferences/').data['sms_reminders'])

    @override_settings(PAYMENTS_ENABLED=False)
    @patch('api.integrations.razorpay')
    def test_disabled_checkout_and_other_patients_never_call_provider(self,provider):
        url=f'/api/bills/{self.bill.pk}/checkout/'
        self.assertEqual(self.client.post(url).status_code,503)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post(url).status_code,404)
        provider.assert_not_called()

    @override_settings(PAYMENTS_ENABLED=True,PAYMENT_MODE='test',RAZORPAY_KEY_ID='rzp_test_dummy',RAZORPAY_KEY_SECRET='test-secret')
    @patch('api.integrations.razorpay')
    def test_checkout_reuse_and_provider_verified_payment(self,provider):
        provider.return_value={'id':'plink_Test123','short_url':'https://rzp.io/test'}
        url=f'/api/bills/{self.bill.pk}/checkout/'
        self.assertEqual(self.client.post(url,{'amount':1}).status_code,201)
        self.assertEqual(provider.call_args.args[1]['amount'],10000)
        self.assertEqual(self.client.post(url).status_code,200)
        self.assertEqual(provider.call_count,1)
        checkout=PaymentCheckout.objects.get(bill=self.bill)
        payload={'id':checkout.provider_id,'reference_id':str(checkout.reference),'currency':'INR','amount':10000,'amount_paid':10000,'status':'paid'}
        provider.return_value=payload
        self.assertEqual(self.client.post(f'/api/bills/{self.bill.pk}/payment-status/').data['state'],'PAID')
        self.client.post(f'/api/bills/{self.bill.pk}/payment-status/')
        self.bill.refresh_from_db();self.assertEqual(self.bill.status,'Paid');self.assertEqual(Payment.objects.count(),1)

    @override_settings(PAYMENTS_ENABLED=True,PAYMENT_MODE='test',RAZORPAY_KEY_ID='rzp_test_dummy',RAZORPAY_KEY_SECRET='test-secret')
    @patch('api.integrations.razorpay')
    def test_payment_mismatch_does_not_mark_bill_paid(self,provider):
        checkout=PaymentCheckout.objects.create(bill=self.bill,amount=100,provider_id='plink_Test123',state='ACTIVE')
        provider.return_value={'id':checkout.provider_id,'reference_id':str(checkout.reference),'currency':'USD','amount':10000,'amount_paid':10000,'status':'paid'}
        self.assertEqual(self.client.post(f'/api/bills/{self.bill.pk}/payment-status/').status_code,503)
        self.bill.refresh_from_db();self.assertEqual(self.bill.status,'Pending');self.assertEqual(Payment.objects.count(),0)

    @override_settings(PAYMENTS_ENABLED=True,PAYMENT_MODE='test',RAZORPAY_KEY_ID='rzp_test_dummy',RAZORPAY_KEY_SECRET='test-secret')
    @patch('api.integrations.razorpay',side_effect=ProviderUnavailable('timeout'))
    def test_uncertain_checkout_not_recreated(self,provider):
        url=f'/api/bills/{self.bill.pk}/checkout/'
        self.assertEqual(self.client.post(url).status_code,502)
        self.assertEqual(self.client.post(url).status_code,409)
        self.assertEqual(provider.call_count,1)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='webhook-test')
    @patch('api.integrations.reconcile')
    def test_webhook_requires_signature(self,reconcile):
        checkout=PaymentCheckout.objects.create(bill=self.bill,amount=100,provider_id='plink_Test123',state='ACTIVE')
        payload=json.dumps({'event':'payment_link.paid','payload':{'payment_link':{'entity':{'id':checkout.provider_id}}}})
        self.assertEqual(self.client.post('/api/webhooks/razorpay/',payload,content_type='application/json').status_code,403)
        reconcile.assert_not_called()
        signature=hmac.new(b'webhook-test',payload.encode(),hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post('/api/webhooks/razorpay/',payload,content_type='application/json',HTTP_X_RAZORPAY_SIGNATURE=signature).status_code,200)
        reconcile.assert_called_once()

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',EMAIL_HOST='smtp.example.test')
    @patch('api.management.commands.send_appointment_reminders.send_mail')
    @patch('api.management.commands.send_appointment_reminders.send_sms',return_value='SMtest')
    @patch('api.management.commands.send_appointment_reminders.sms_ready',return_value=True)
    def test_reminders_require_opt_in_and_skip_duplicates(self,ready,sms,email):
        call_command('send_appointment_reminders',email=True,sms=True)
        sms.assert_not_called();email.assert_not_called()
        CommunicationPreference.objects.create(user=self.patient_user,sms_reminders=True)
        call_command('send_appointment_reminders',email=True,sms=True)
        call_command('send_appointment_reminders',email=True,sms=True)
        sms.assert_called_once();self.assertEqual(AppointmentReminder.objects.filter(channel='sms',state='SUBMITTED').count(),1)

    @patch('api.management.commands.send_appointment_reminders.sms_ready',return_value=True)
    @patch('api.management.commands.send_appointment_reminders.send_sms',side_effect=ProviderUnavailable('timeout'))
    def test_uncertain_sms_not_sent_twice(self,sms,ready):
        CommunicationPreference.objects.create(user=self.patient_user,sms_reminders=True)
        call_command('send_appointment_reminders',sms=True)
        call_command('send_appointment_reminders',sms=True)
        sms.assert_called_once();self.assertEqual(AppointmentReminder.objects.get(channel='sms').state,'UNKNOWN')

    def test_admin_invoice_changes_blocked_while_checkout_exists(self):
        PaymentCheckout.objects.create(bill=self.bill,amount=100,state='ACTIVE')
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(f'/api/bills/{self.bill.pk}/',{'consultation_fee':200}).status_code,400)

    def test_status_does_not_expose_secrets(self):
        result=self.client.get('/api/integration-status/')
        self.assertEqual(set(result.data),{'payments','payment_mode','sms','email'})

    @override_settings(PAYMENTS_ENABLED=True,PAYMENT_MODE='test',RAZORPAY_KEY_ID='rzp_test_dummy',RAZORPAY_KEY_SECRET='test-secret')
    @patch('api.integrations.razorpay')
    def test_reviewed_checkout_recovers_only_matching_provider_link(self,provider):
        checkout=PaymentCheckout.objects.create(bill=self.bill,amount=100,provider_id='plink_Test123',state='REVIEW')
        provider.return_value={'id':checkout.provider_id,'reference_id':str(checkout.reference),'currency':'INR','amount':10000,'amount_paid':0,'status':'created','short_url':'https://rzp.io/test'}
        result=self.client.post(f'/api/bills/{self.bill.pk}/payment-status/')
        self.assertEqual(result.data['state'],'ACTIVE')
        self.assertEqual(result.data['url'],'https://rzp.io/test')
        self.bill.refresh_from_db();self.assertEqual(self.bill.status,'Pending')
