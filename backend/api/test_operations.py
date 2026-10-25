"""PRD mandatory scenarios plus pharmacy, billing, lab, OTP, audit and Stripe checks."""
import hashlib, hmac, json, time as clock
from datetime import date, time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (Hospital, Doctor, Patient, Appointment, MedicalRecord, Prescription, PrescriptionItem, Bill,
                     Medicine, MedicineBatch, LabTest, LabOrder, AuditLog, VerificationCode)

User=get_user_model()

class Base(TestCase):
    def setUp(self):
        self.c=APIClient()
        self.h1=Hospital.objects.create(name='North',code='N'); self.h2=Hospital.objects.create(name='South',code='S')
        self.admin1=User.objects.create_user('admin1',password='pw-12345678',role='ADMIN',hospital=self.h1)
        self.du=User.objects.create_user('doc',password='pw-12345678',role='DOCTOR',hospital=self.h1)
        self.doctor=Doctor.objects.create(user=self.du,doctor_id='D1',specialization='GP')
        self.pu=User.objects.create_user('pat',password='pw-12345678',role='PATIENT')
        self.patient=Patient.objects.create(user=self.pu,hospital=self.h1,patient_id='P1',full_name='Pat One',gender='Other',phone='1')
        self.other_pu=User.objects.create_user('pat2',password='pw-12345678',role='PATIENT')
        self.other=Patient.objects.create(user=self.other_pu,hospital=self.h2,patient_id='P2',full_name='Pat Two',gender='Other',phone='2')
        self.appt=Appointment.objects.create(patient=self.patient,doctor=self.doctor,date=timezone.localdate()+timedelta(days=1),time=time(10),status='Confirmed')
        self.record=MedicalRecord.objects.create(patient=self.patient,doctor=self.doctor,appointment=self.appt,diagnosis='Flu')
        self.other_record=MedicalRecord.objects.create(patient=self.other,diagnosis='Secret')

class MandatoryScenarios(Base):
    def test_tenancy_isolation(self):
        admin2=User.objects.create_user('admin2',password='pw-12345678',role='ADMIN',hospital=self.h2)
        self.c.force_authenticate(admin2)
        ids={p['id'] for p in self.c.get('/api/patients/').data}
        self.assertIn(self.other.pk,ids); self.assertNotIn(self.patient.pk,ids)
        self.assertEqual(self.c.get(f'/api/patients/{self.patient.pk}/').status_code,404)
        self.c.force_authenticate(self.du)
        self.assertNotIn(self.other_record.pk,[r['id'] for r in self.c.get('/api/medical-records/').data])

    def test_patient_cannot_view_other_records(self):
        self.c.force_authenticate(self.pu)
        ids=[r['id'] for r in self.c.get('/api/medical-records/').data]
        self.assertEqual(ids,[self.record.pk])
        self.assertEqual(self.c.get(f'/api/medical-records/{self.other_record.pk}/').status_code,404)

    def test_double_booking_only_one_succeeds(self):
        self.c.force_authenticate(self.admin1)
        slot={'patient':self.other.pk,'doctor':self.doctor.pk,'date':str(self.appt.date),'time':'10:00'}
        self.assertEqual(self.c.post('/api/appointments/',slot).status_code,400)
        # The database constraint is the final guard against a race between validators.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(patient=self.other,doctor=self.doctor,date=self.appt.date,time=time(10))

    def test_refresh_token_cannot_be_reused(self):
        login=self.c.post('/api/login/',{'username':'pat','password':'pw-12345678'})
        self.assertNotIn('refresh',login.data)  # never exposed to JavaScript
        cookie=login.cookies['medcore_refresh']
        self.assertTrue(cookie['httponly']); self.assertEqual(cookie['samesite'],'Strict')
        original=cookie.value
        first=self.c.post('/api/token/refresh/')  # uses the cookie
        self.assertEqual(first.status_code,200); self.assertIn('access',first.data)
        rotated=first.cookies['medcore_refresh'].value
        self.assertNotEqual(rotated,original)
        self.assertEqual(self.c.post('/api/token/refresh/',{'refresh':original}).status_code,401)
        self.c.post('/api/logout/')
        self.assertEqual(self.c.post('/api/token/refresh/',{'refresh':rotated}).status_code,401)

    def test_expired_medicine_cannot_be_dispensed_and_fifo(self):
        pharm=User.objects.create_user('ph',password='pw-12345678',role='PHARMACIST')
        med=Medicine.objects.create(name='Amox',form='capsule')
        today=timezone.localdate()
        MedicineBatch.objects.create(medicine=med,batch_number='OLD',manufacturing_date=today-timedelta(days=400),expiry_date=today-timedelta(days=1),quantity=50,unit_cost=1,mrp=2)
        rx=Prescription.objects.create(record=self.record,medicine='Amox',dosage='500mg',frequency='TDS',duration='5')
        item=PrescriptionItem.objects.create(prescription=rx,medicine=med,dosage='500mg',frequency='TDS',duration='5')
        self.c.force_authenticate(pharm)
        r=self.c.post(f'/api/prescription-items/{item.pk}/dispense/',{'quantity':10})
        self.assertEqual(r.status_code,400); self.assertIn('Expired',str(r.data))
        early=MedicineBatch.objects.create(medicine=med,batch_number='A',manufacturing_date=today-timedelta(days=30),expiry_date=today+timedelta(days=60),quantity=5,unit_cost=1,mrp=2)
        late=MedicineBatch.objects.create(medicine=med,batch_number='B',manufacturing_date=today-timedelta(days=30),expiry_date=today+timedelta(days=300),quantity=20,unit_cost=1,mrp=2)
        self.assertEqual(self.c.post(f'/api/prescription-items/{item.pk}/dispense/',{'quantity':8}).status_code,200)
        early.refresh_from_db(); late.refresh_from_db()
        self.assertEqual((early.quantity,late.quantity),(0,17))

    def test_invoice_total_matches_line_items(self):
        acct=User.objects.create_user('acct',password='pw-12345678',role='ACCOUNTANT')
        bill=Bill.objects.create(patient=self.patient)
        self.c.force_authenticate(acct)
        for cat,qty,price in [('CONSULTATION',1,'500'),('LAB',2,'150.50'),('PHARMACY',3,'20'),('ROOM',1,'1000')]:
            self.assertEqual(self.c.post('/api/bill-items/',{'bill':bill.pk,'category':cat,'description':cat,'quantity':qty,'unit_price':price}).status_code,201)
        bill.refresh_from_db()
        self.assertEqual(bill.total,sum(i.amount for i in bill.items.all()))
        self.assertEqual(bill.total,Decimal('1861.00'))

class ModuleTests(Base):
    def test_lab_flags_out_of_range_and_requires_second_approver(self):
        tech=User.objects.create_user('tech',password='pw-12345678',role='LAB_TECH')
        hb=LabTest.objects.create(name='Haemoglobin',unit='g/dL',reference_range='13.0-17.5')
        order=LabOrder.objects.create(record=self.record,test=hb,ordered_by=self.du)
        self.c.force_authenticate(tech)
        url=f'/api/lab-orders/{order.pk}/progress/'
        for s in ['SAMPLE_COLLECTED','PROCESSING']: self.assertEqual(self.c.post(url,{'status':s}).status_code,200)
        r=self.c.post(url,{'status':'REVIEW','result_value':'9.1'})
        self.assertTrue(r.data['out_of_range'])
        self.assertEqual(self.c.post(url,{'status':'APPROVED'}).status_code,403)
        self.c.force_authenticate(self.du)
        self.assertEqual(self.c.post(url,{'status':'APPROVED'}).status_code,200)

    def test_email_otp(self):
        self.pu.email='p@example.com'; self.pu.save()
        self.c.force_authenticate(self.pu)
        self.assertEqual(self.c.post('/api/verify/send/',{'channel':'email'}).status_code,200)
        self.assertEqual(self.c.post('/api/verify/confirm/',{'channel':'email','code':'000000x'}).status_code,400)
        entry=VerificationCode.objects.get(user=self.pu,used=False)
        from .operations import _hash_code
        code=next(f'{n:06d}' for n in range(10**6) if _hash_code(f'{n:06d}')==entry.code_hash)
        self.assertEqual(self.c.post('/api/verify/confirm/',{'channel':'email','code':code}).status_code,200)
        self.pu.refresh_from_db(); self.assertTrue(self.pu.email_verified)

    def test_writes_are_audited(self):
        self.c.force_authenticate(self.admin1)
        self.c.post('/api/departments/',{'name':'Cardiology'})
        self.assertTrue(AuditLog.objects.filter(path='/api/departments/',method='POST').exists())

    def test_vitals_append_only_with_bmi(self):
        nurse=User.objects.create_user('nurse',password='pw-12345678',role='NURSE',hospital=self.h1)
        self.c.force_authenticate(nurse)
        r=self.c.post('/api/vitals/',{'patient':self.patient.pk,'pulse':72,'height_cm':'180','weight_kg':'81'})
        self.assertEqual(r.status_code,201); self.assertEqual(r.data['bmi'],25.0)
        self.assertEqual(self.c.delete(f"/api/vitals/{r.data['id']}/").status_code,405)
        self.assertEqual(self.c.post('/api/vitals/',{'patient':self.other.pk,'pulse':80}).status_code,403)

    def test_demo_seed_is_idempotent_and_dashboards_load(self):
        from django.core.management import call_command
        call_command('seed_prd_demo','--yes',verbosity=0); call_command('seed_prd_demo','--yes',verbosity=0)
        self.assertEqual(Patient.objects.filter(patient_id__startswith='DEMO-P').count(),30)
        for role in ['super_admin','admin','doctor','nurse','receptionist','lab_tech','pharmacist','accountant','patient']:
            self.c.force_authenticate(User.objects.get(username=f'demo_{role}'))
            self.assertEqual(self.c.get('/api/dashboard/').status_code,200,role)

    def test_clinical_text_encrypted_at_rest(self):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SELECT diagnosis FROM api_medicalrecord WHERE id=%s',[self.record.pk])
            stored=cur.fetchone()[0]
        self.assertTrue(stored.startswith('enc1:')); self.assertNotIn('Flu',stored)
        self.assertEqual(MedicalRecord.objects.get(pk=self.record.pk).diagnosis,'Flu')

    def test_infected_upload_rejected(self):
        from unittest import mock
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.c.force_authenticate(self.pu)
        pdf=lambda:SimpleUploadedFile('r.pdf',b'%PDF-1.4 test',content_type='application/pdf')
        with mock.patch('api.scanning.scan_bytes',return_value='Eicar-Test-Signature'):
            r=self.c.post('/api/documents/',{'patient':self.patient.pk,'title':'Report','category':'Report','file':pdf()},format='multipart')
        self.assertEqual(r.status_code,400); self.assertIn('virus',str(r.data))
        with mock.patch('api.scanning.scan_bytes',return_value=None):
            self.assertEqual(self.c.post('/api/documents/',{'patient':self.patient.pk,'title':'Report','category':'Report','file':pdf()},format='multipart').status_code,201)

    def test_api_docs_served(self):
        self.assertEqual(self.c.get('/api/schema/').status_code,200)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_stripe_webhook_signature(self):
        bill=Bill.objects.create(patient=self.patient,consultation_fee=Decimal('100'))
        payload=json.dumps({'type':'checkout.session.completed','data':{'object':{'id':'cs_1','payment_status':'paid','amount_total':10000,'metadata':{'bill_id':str(bill.pk)}}}}).encode()
        self.assertEqual(self.c.post('/api/payments/webhook/stripe/',payload,content_type='application/json',HTTP_STRIPE_SIGNATURE='t=1,v1=bad').status_code,400)
        stamp=int(clock.time()); sig=hmac.new(b'whsec_test',f'{stamp}.'.encode()+payload,hashlib.sha256).hexdigest()
        self.assertEqual(self.c.post('/api/payments/webhook/stripe/',payload,content_type='application/json',HTTP_STRIPE_SIGNATURE=f't={stamp},v1={sig}').status_code,200)
        bill.refresh_from_db(); self.assertEqual(bill.status,'Paid')
