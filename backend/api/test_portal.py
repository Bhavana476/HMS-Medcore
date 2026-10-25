from datetime import timedelta,time
from decimal import Decimal
from pathlib import Path
import tempfile
from django.test import TestCase,override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.management import call_command
from django.core.cache import cache
from rest_framework.test import APIClient
from .models import Doctor,Patient,Department,Appointment,DoctorAvailability,PatientDocument,MedicalRecord,LabTest,LabOrder,ImportedAdmission,Notification

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        config=override_settings(REMINDER_HEARTBEAT_PATH=Path(self.temp.name)/'heartbeat.json');config.enable();self.addCleanup(config.disable)
        cache.clear()
        User=get_user_model()
        self.admin=User.objects.create_user('portal_admin',role='ADMIN',password='Test-password-923')
        self.user=User.objects.create_user('portal_patient',role='PATIENT',email='patient@example.test',password='Test-password-923')
        self.other=User.objects.create_user('portal_other',role='PATIENT',password='Test-password-923')
        self.clinician=User.objects.create_user('portal_doctor',role='DOCTOR',password='Test-password-923')
        self.department=Department.objects.create(name='Cardiology')
        self.doctor=Doctor.objects.create(user=self.clinician,doctor_id='D1',specialization='Cardiology',department=self.department)
        self.patient=Patient.objects.create(user=self.user,patient_id='P1',full_name='Patient One',gender='Other',phone='555')
        self.patient2=Patient.objects.create(user=self.other,patient_id='P2',full_name='Patient Two',gender='Other',phone='556')
        self.day=timezone.localdate()+timedelta(days=1)
        self.appointment=Appointment.objects.create(patient=self.patient,doctor=self.doctor,date=self.day,time=time(9),status='Confirmed')
        DoctorAvailability.objects.create(doctor=self.doctor,date=self.day,start_time=time(9),end_time=time(12))
        self.client=APIClient();self.client.force_authenticate(self.user)

    def upload(self,patient=None,content=b'%PDF-1.4\nexample'):
        return self.client.post('/api/documents/',{'patient':(patient or self.patient).pk,'title':'Test report','category':'Report','file':SimpleUploadedFile('report.pdf',content,content_type='application/pdf')},format='multipart')

    def test_document_owner_download_and_cross_patient_denial(self):
        response=self.upload();self.assertEqual(response.status_code,201)
        url=f"/api/documents/{response.data['id']}/download/"
        response=self.client.get(url);self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'no-store')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get('/api/documents/').data,[])
        self.assertEqual(self.upload().status_code,404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code,401)

    def test_reject_fake_pdf_and_large_file(self):
        self.assertEqual(self.upload(content=b'<script>bad()</script>').status_code,400)
        self.assertEqual(self.upload(content=b'%PDF-'+b'a'*(5*1024*1024)).status_code,400)
        self.assertEqual(PatientDocument.objects.count(),0)

    def test_doctor_only_sees_linked_documents(self):
        self.upload();self.client.force_authenticate(self.other);self.upload(self.patient2)
        self.client.force_authenticate(self.clinician)
        response=self.client.get('/api/documents/')
        self.assertEqual(len(response.data),1)
        self.assertEqual(response.data[0]['patient'],self.patient.pk)

    def test_reschedule_returns_pending_and_notifies(self):
        r=self.client.post(f'/api/appointments/{self.appointment.pk}/reschedule/',{'date':str(self.day),'time':'10:00'})
        self.assertEqual(r.status_code,200,r.data)
        self.appointment.refresh_from_db();self.assertEqual(self.appointment.status,'Pending')
        self.assertEqual(self.appointment.time,time(10));self.assertEqual(Notification.objects.count(),2)

    def test_reschedule_rejects_other_patient_past_outside_slots_and_conflict(self):
        url=f'/api/appointments/{self.appointment.pk}/reschedule/'
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url,{'date':str(self.day),'time':'10:00'}).status_code,404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(url,{'date':'2020-01-01','time':'10:00'}).status_code,400)
        self.assertEqual(self.client.post(url,{'date':str(self.day),'time':'18:00'}).status_code,400)
        Appointment.objects.create(patient=self.patient2,doctor=self.doctor,date=self.day,time=time(10))
        self.assertEqual(self.client.post(url,{'date':str(self.day),'time':'10:00'}).status_code,400)
        self.appointment.refresh_from_db();self.assertEqual(self.appointment.time,time(9))

    def test_completed_visit_cannot_reschedule(self):
        self.appointment.status='Completed';self.appointment.save()
        self.assertEqual(self.client.post(f'/api/appointments/{self.appointment.pk}/reschedule/',{'date':str(self.day),'time':'10:00'}).status_code,400)

    def test_recovery_generic_response_and_single_use_token(self):
        self.client.force_authenticate(None)
        found=self.client.post('/api/password-reset/',{'email':self.user.email})
        missing=self.client.post('/api/password-reset/',{'email':'missing@example.test'})
        self.assertEqual(found.data,missing.data);self.assertEqual(len(mail.outbox),1)
        self.assertIn('reset_token=',mail.outbox[0].body)
        uid=urlsafe_base64_encode(force_bytes(self.user.pk));token=default_token_generator.make_token(self.user)
        payload={'uid':uid,'token':token,'password':'New-unique-password-923'}
        self.assertEqual(self.client.post('/api/password-reset/confirm/',payload).status_code,200)
        self.assertEqual(self.client.post('/api/password-reset/confirm/',payload).status_code,400)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(payload['password']))

    def test_reset_rejects_short_password(self):
        self.client.force_authenticate(None)
        payload={'uid':urlsafe_base64_encode(force_bytes(self.user.pk)),'token':default_token_generator.make_token(self.user),'password':'abc'}
        self.assertEqual(self.client.post('/api/password-reset/confirm/',payload).status_code,400)

    def test_lab_results_hidden_until_approved(self):
        record=MedicalRecord.objects.create(patient=self.patient,doctor=self.doctor,diagnosis='Test encounter')
        test=LabTest.objects.create(name='Example test',price=Decimal('100'),unit='units')
        self.client.force_authenticate(self.admin)
        r=self.client.post('/api/lab-orders/',{'record':record.pk,'test':test.pk});self.assertEqual(r.status_code,201,r.data)
        url=f"/api/lab-orders/{r.data['id']}/progress/"
        self.assertEqual(self.client.post(url,{'status':'APPROVED'}).status_code,400)
        for status in ['SAMPLE_COLLECTED','PROCESSING','REVIEW']:
            self.assertEqual(self.client.post(url,{'status':status,'result_value':'12'}).status_code,200)
        self.client.force_authenticate(self.user);self.assertEqual(self.client.get('/api/lab-orders/').data,[])
        self.assertEqual(self.client.post(url,{'status':'APPROVED'}).status_code,403)
        self.client.force_authenticate(self.clinician)
        self.assertEqual(self.client.post(url,{'status':'APPROVED'}).status_code,200)
        self.client.force_authenticate(self.user)
        self.assertEqual(len(self.client.get('/api/lab-orders/').data),1)
        self.client.force_authenticate(self.other);self.assertEqual(self.client.get('/api/lab-orders/').data,[])

    def test_historical_directory_does_not_invent_credentials(self):
        ImportedAdmission.objects.create(source_row=1,patient_name='Historic',age=30,gender='Other',blood_type='O+',medical_condition='Example',admission_date=self.day,doctor_name='Historical Name',hospital='Other hospital',insurance_provider='Unknown',billing_amount=100,room_number='1',admission_type='Routine',medication='Unknown',test_results='Unknown')
        self.client.force_authenticate(self.admin)
        historical=[r for r in self.client.get('/api/doctor-directory/').data['results'] if not r['registered']][0]
        for key in ['doctor_id','specialization','department_name','experience','available']:self.assertIsNone(historical[key])
        visit=[r for r in self.client.get('/api/patient-directory/').data['results'] if r['record_type']=='Visit'][0]
        # Visits get a display-only directory number, never a registered patient or contact details.
        self.assertTrue(visit['patient_id'].startswith('PAT-'));self.assertIsNone(visit['patient_pk']);self.assertIsNone(visit['phone'])
        self.client.force_authenticate(None)
        public=self.client.get('/api/public-directory/').data
        self.assertEqual(len(public['doctors']),1)
        self.assertNotIn('email',public['doctors'][0]);self.assertNotIn('patient',public['doctors'][0])

    def test_admin_can_manage_department_patient_cannot(self):
        department=Department.objects.create(name='General Medicine')
        url=f'/api/doctors/{self.doctor.pk}/'
        self.assertEqual(self.client.patch(url,{'department':department.pk}).status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(url,{'department':department.pk,'qualifications':'Verified by hospital staff'}).status_code,200)
        self.client.force_authenticate(self.clinician)
        self.assertEqual(self.client.get('/api/dashboard/').data['doctor']['department_name'],'General Medicine')

    def test_reminders_are_idempotent(self):
        call_command('send_appointment_reminders',dry_run=True)
        self.assertEqual(Notification.objects.count(),0)
        call_command('send_appointment_reminders');call_command('send_appointment_reminders')
        self.assertEqual(Notification.objects.count(),1)
