from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ImportedAdmission, Doctor, Patient, Appointment, MedicalRecord, DoctorAvailability, Prescription, Bill, Department


class ImportedAdmissionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(username='admissions_admin', password='test-password', role='ADMIN')
        self.patient = get_user_model().objects.create_user(username='admissions_patient', password='test-password', role='PATIENT')
        common = dict(age=30, gender='Female', blood_type='O+', doctor_name='Dr Smith',
                      hospital='Example Hospital', insurance_provider='Aetna',
                      billing_amount=Decimal('120.50'), room_number='12',
                      admission_type='Urgent', discharge_date=date(2024, 1, 4),
                      medication='Aspirin', test_results='Normal')
        ImportedAdmission.objects.create(source_row=2, patient_name='Older Patient',
                                         medical_condition='Asthma', admission_date=date(2023, 1, 1), **common)
        ImportedAdmission.objects.create(source_row=3, patient_name='Newer Patient',
                                         medical_condition='Cancer', admission_date=date(2024, 1, 1), **common)

    def test_admin_can_search_and_rows_are_newest_first(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/imported-admissions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual([row['patient_name'] for row in response.data['results']],
                         ['Newer Patient', 'Older Patient'])
        response = self.client.get('/api/imported-admissions/?q=Asthma')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['patient_name'], 'Older Patient')

    def test_patient_is_denied(self):
        self.client.force_authenticate(self.patient)
        self.assertEqual(self.client.get('/api/imported-admissions/').status_code, 403)

    def test_login_token_can_read_admissions(self):
        response = self.client.post('/api/login/', {'username': 'admissions_admin', 'password': 'test-password'})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get('/api/imported-admissions/').status_code, 200)

    def test_dashboard_shows_imported_count_and_recent_rows(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['historical_admissions'], 2)
        self.assertEqual(response.data['imported_doctor_names'], 1)
        self.assertEqual(Decimal(response.data['imported_billing_total']), Decimal('241.00'))
        self.assertEqual(response.data['revenue'], 0)
        self.assertEqual(response.data['recent_historical_admissions'][0]['patient_name'], 'Newer Patient')

    def test_patients_endpoint_contains_only_registered_profiles(self):
        Patient.objects.create(patient_id='LIVE-1',full_name='Registered Patient',gender='Female',phone='555')
        self.client.force_authenticate(self.admin)
        response=self.client.get('/api/patients/')
        self.assertEqual(response.status_code,200)
        self.assertEqual([patient['full_name'] for patient in response.data],['Registered Patient'])


class PatientDirectoryTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        User=get_user_model()
        self.admin=User.objects.create_user(username='directory_admin',password='test-password',role='ADMIN')
        self.receptionist=User.objects.create_user(username='directory_reception',password='test-password',role='RECEPTIONIST')
        self.patient_user=User.objects.create_user(username='directory_patient',password='test-password',role='PATIENT')
        for number in range(2):
            Patient.objects.create(patient_id=f'LIVE-{number}',full_name=f'Profile {number}',gender='Female',
                                   phone=f'555{number}',email=f'profile{number}@example.com',dob=date(2000,1,1),
                                   allergies='Penicillin')
        ImportedAdmission.objects.bulk_create([
            ImportedAdmission(source_row=number+2,patient_name=f'Visit {number}',age=30,gender='Male',blood_type='O+',
                              medical_condition='Asthma',admission_date=date(2024,1,1),doctor_name='Dr Smith',
                              hospital='Example Hospital',insurance_provider='Aetna',billing_amount=Decimal('120.50'),
                              room_number='12',admission_type='Urgent',discharge_date=date(2024,1,4),
                              medication='Aspirin',test_results='Normal')
            for number in range(51)
        ])

    def test_single_list_paginates_profiles_and_visits(self):
        self.client.force_authenticate(self.admin)
        first=self.client.get('/api/patient-directory/')
        second=self.client.get('/api/patient-directory/?page=2')
        self.assertEqual((first.status_code,second.status_code),(200,200))
        self.assertEqual(first.data['count'],53)
        self.assertEqual((len(first.data['results']),len(second.data['results'])),(50,3))
        self.assertEqual([r['record_type'] for r in first.data['results'][:3]],['Profile','Profile','Visit'])
        keys=[r['key'] for r in first.data['results']+second.data['results']]
        self.assertEqual(len(keys),len(set(keys)))
        profile,visit=first.data['results'][0],first.data['results'][2]
        self.assertEqual(set(profile),set(visit))
        self.assertEqual(profile['email'],'profile1@example.com')
        self.assertIsNotNone(profile['age'])
        self.assertEqual(visit['medication'],'Aspirin')
        self.assertEqual(visit['patient_id'],'PAT-03')
        self.assertIsNone(visit['date_of_birth'])
        self.assertEqual(visit['record_id'],'PROFILE-3')
        self.assertEqual(second.data['results'][0]['record_id'],'PROFILE-51')
        self.assertEqual(second.data['results'][0]['patient_id'],'PAT-51')

    def test_directory_ids_continue_existing_patient_ids_and_survive_search(self):
        patient=Patient.objects.first()
        patient.patient_id='PAT-01'
        patient.save(update_fields=['patient_id'])
        self.client.force_authenticate(self.admin)
        visit=self.client.get('/api/patient-directory/').data['results'][2]
        self.assertEqual(visit['patient_id'],'PAT-03')
        for query in [visit['patient_id'],visit['record_id'],visit['patient_name']]:
            results=self.client.get('/api/patient-directory/',{'q':query}).data['results']
            found=next(row for row in results if row['key']==visit['key'])
            self.assertEqual(found['record_id'],visit['record_id'])
            self.assertEqual(found['patient_id'],visit['patient_id'])

    def test_search_and_permissions(self):
        self.client.force_authenticate(self.receptionist)
        self.assertEqual(self.client.get('/api/patient-directory/?q=LIVE-0').data['count'],1)
        self.assertEqual(self.client.get('/api/patient-directory/?q=Asthma').data['count'],51)
        self.assertEqual(self.client.get('/api/patient-directory/?q=Aspirin').data['count'],51)
        self.client.force_authenticate(self.patient_user)
        self.assertEqual(self.client.get('/api/patient-directory/').status_code,403)

    def test_even_assignment_and_doctor_directory_isolation(self):
        from django.core.management import call_command
        from io import StringIO
        doctors=[]
        for number in range(3):
            user=get_user_model().objects.create_user(username=f'assignee-{number}',role='DOCTOR')
            doctors.append(Doctor.objects.create(user=user,doctor_id=f'ASSIGN-{number}',specialization='General'))
        hidden=Patient.objects.first()
        hidden.directory_hidden=True
        hidden.save(update_fields=['directory_hidden'])
        call_command('distribute_patients',stdout=StringIO())
        counts=[]
        all_keys=set()
        for doctor in doctors:
            self.client.force_authenticate(doctor.user)
            response=self.client.get('/api/patient-directory/')
            self.assertEqual(response.status_code,200)
            counts.append(response.data['count'])
            keys={row['key'] for row in response.data['results']}
            self.assertFalse(all_keys.intersection(keys))
            all_keys.update(keys)
            self.assertTrue(all(row['doctor_name']==doctor.user.username for row in response.data['results']))
        self.assertEqual(sum(counts),52)
        self.assertLessEqual(max(counts)-min(counts),1)
        hidden.refresh_from_db()
        self.assertIsNone(hidden.primary_doctor_id)

    def test_hidden_directory_rows_are_excluded_without_deleting_records(self):
        self.client.force_authenticate(self.admin)
        before=self.client.get('/api/patient-directory/').data
        profile=Patient.objects.get(pk=before['results'][0]['patient_pk'])
        profile.directory_hidden=True
        profile.save(update_fields=['directory_hidden'])
        visit=ImportedAdmission.objects.first()
        visit.directory_hidden=True
        visit.save(update_fields=['directory_hidden'])
        after=self.client.get('/api/patient-directory/').data
        self.assertEqual(after['count'],before['count']-2)
        self.assertEqual(after['results'][0]['record_id'],'PROFILE-1')
        self.assertEqual(after['results'][0]['patient_id'],'PAT-01')
        hidden_keys={before['results'][0]['key'],before['results'][2]['key']}
        self.assertFalse(hidden_keys.intersection(row['key'] for row in after['results']))
        self.assertEqual(Patient.objects.count(),2)
        self.assertEqual(ImportedAdmission.objects.count(),51)
        self.assertEqual(self.client.get('/api/patient-directory/',{'q':profile.patient_id}).data['count'],0)

    def test_directory_includes_existing_billing_and_admission_data(self):
        from .models import Bed, Bill
        patient=Patient.objects.get(patient_id='LIVE-0')
        Bed.objects.create(ward='General',bed_number='G-1',patient=patient,status='Occupied',admitted_on=date(2024,1,1))
        Bill.objects.create(patient=patient,consultation_fee=Decimal('250.00'))
        Bill.objects.create(patient=patient,consultation_fee=Decimal('900.00'),status='Cancelled')
        self.client.force_authenticate(self.admin)
        row=self.client.get('/api/patient-directory/',{'q':'LIVE-0'}).data['results'][0]
        self.assertEqual(row['room_number'],'General / G-1')
        self.assertEqual(row['admission_date'],date(2024,1,1))
        self.assertEqual(row['billing_amount'],Decimal('250.00'))

    def test_patient_profiles_cannot_be_deleted(self):
        self.client.force_authenticate(self.admin)
        patient=Patient.objects.get(patient_id='LIVE-0')
        response=self.client.delete(f'/api/patients/{patient.pk}/')
        self.assertEqual(response.status_code,405)
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())
        self.assertEqual(ImportedAdmission.objects.count(),51)
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                Patient.objects.filter(pk=patient.pk).delete()
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())

    def test_removing_a_login_preserves_its_patient_profile(self):
        patient=Patient.objects.get(patient_id='LIVE-0')
        patient.user=self.patient_user
        patient.save(update_fields=['user'])
        self.patient_user.delete()
        patient.refresh_from_db()
        self.assertIsNone(patient.user_id)


class CareWorkflowTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        User=get_user_model()
        self.doctor_user=User.objects.create_user(username='doctor_flow',password='test-password',role='DOCTOR')
        self.receptionist=User.objects.create_user(username='reception_flow',password='test-password',role='RECEPTIONIST')
        self.patient_user=User.objects.create_user(username='patient_flow',password='test-password',role='PATIENT')
        self.other_user=User.objects.create_user(username='other_flow',password='test-password',role='PATIENT')
        self.doctor=Doctor.objects.create(user=self.doctor_user,doctor_id='D-FLOW',specialization='General Medicine')
        self.patient=Patient.objects.create(user=self.patient_user,patient_id='P-FLOW',full_name='First Patient',gender='Female',phone='111')
        self.other=Patient.objects.create(user=self.other_user,patient_id='P-OTHER',full_name='Other Patient',gender='Male',phone='222')
        self.day=timezone.localdate()+timedelta(days=1)

    def test_patient_books_own_appointment_and_conflicts_are_rejected(self):
        self.client.force_authenticate(self.patient_user)
        payload={'doctor':self.doctor.pk,'date':self.day.isoformat(),'time':'10:00','reason':'Consultation'}
        first=self.client.post('/api/appointments/',payload)
        self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(Appointment.objects.get(pk=first.data['id']).patient,self.patient)
        self.assertEqual(self.client.post('/api/appointments/',payload).status_code,400)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.post('/api/appointments/',payload).status_code,400)
        self.assertEqual(self.client.post('/api/appointments/',{**payload,'patient':self.patient.pk,'time':'11:00'}).status_code,400)

    def test_status_sequence_and_record_are_enforced(self):
        appointment=Appointment.objects.create(patient=self.patient,doctor=self.doctor,date=self.day,time=time(10),status='Pending')
        self.client.force_authenticate(self.receptionist)
        url=f'/api/appointments/{appointment.pk}/'
        self.assertEqual(self.client.patch(url,{'status':'Completed'}).status_code,400)
        self.assertEqual(self.client.patch(url,{'status':'Confirmed'}).status_code,200)
        self.assertEqual(self.client.patch(url,{'status':'In Progress'}).status_code,400)
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(self.client.post('/api/medical-records/',{'appointment':appointment.pk,'diagnosis':'Migraine'}).status_code,403)
        admin=get_user_model().objects.create_user(username='care_admin',password='test-password',role='ADMIN')
        self.client.force_authenticate(admin)
        record=self.client.post('/api/medical-records/',{'appointment':appointment.pk,'diagnosis':'Migraine','symptoms':'Headache'})
        self.assertEqual(record.status_code,201,record.data)
        saved=MedicalRecord.objects.get(pk=record.data['id'])
        self.assertEqual((saved.patient,saved.doctor),(self.patient,self.doctor))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status,'In Progress')
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(self.client.get('/api/dashboard/').data['in_progress_appointments'],1)
        self.assertEqual(self.client.post('/api/medical-records/',{'appointment':appointment.pk,'diagnosis':'Again'}).status_code,403)
        self.assertEqual(self.client.patch(f'/api/medical-records/{saved.pk}/',{'diagnosis':'Changed'}).status_code,405)
        self.assertIn(self.client.delete(f'/api/medical-records/{saved.pk}/').status_code,{403,405})
        self.assertEqual(self.client.patch(url,{'status':'Completed'}).status_code,200)

    def test_doctor_and_patient_cannot_read_another_encounter(self):
        other_doctor_user=get_user_model().objects.create_user(username='second_doctor',password='test-password',role='DOCTOR')
        other_doctor=Doctor.objects.create(user=other_doctor_user,doctor_id='D-SECOND',specialization='General Medicine')
        appointment=Appointment.objects.create(patient=self.other,doctor=other_doctor,date=self.day,time=time(11),status='Confirmed')
        record=MedicalRecord.objects.create(patient=self.other,doctor=other_doctor,appointment=appointment,diagnosis='Confidential')
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(self.client.get(f'/api/medical-records/{record.pk}/').status_code,404)
        self.assertEqual(self.client.post('/api/medical-records/',{'appointment':appointment.pk,'diagnosis':'Wrong doctor'}).status_code,403)
        self.client.force_authenticate(self.patient_user)
        self.assertEqual(self.client.get(f'/api/medical-records/{record.pk}/').status_code,404)

    def test_patient_can_view_existing_entries_but_cannot_create_them(self):
        saved=MedicalRecord.objects.create(patient=self.patient,diagnosis='Recurring headache',source='Patient submitted')
        prescription=Prescription.objects.create(record=saved,medicine='Example medication',dosage='10 mg',frequency='Daily',duration='7 days',source='Patient submitted')
        other_record=MedicalRecord.objects.create(patient=self.other,doctor=self.doctor,diagnosis='Private')
        self.client.force_authenticate(self.patient_user)
        self.assertEqual(self.client.get(f'/api/medical-records/{saved.pk}/').data['source'],'Patient submitted')
        self.assertEqual(self.client.get(f'/api/prescriptions/{prescription.pk}/').data['source'],'Patient submitted')
        self.assertEqual(self.client.get('/api/timeline/').data[0]['source'],'Patient submitted')
        self.assertEqual(self.client.post('/api/medical-records/',{'diagnosis':'New concern'}).status_code,403)
        medication={'record':saved.pk,'medicine':'Another medication','dosage':'10 mg','frequency':'Daily','duration':'7 days'}
        self.assertEqual(self.client.post('/api/prescriptions/',medication).status_code,403)
        self.assertEqual(self.client.get(f'/api/medical-records/{other_record.pk}/').status_code,404)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(f'/api/medical-records/{saved.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/api/prescriptions/{prescription.pk}/').status_code,404)
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(self.client.post('/api/prescriptions/',medication).status_code,403)

    def test_availability_guides_booking(self):
        self.client.force_authenticate(self.doctor_user)
        slot=self.client.post('/api/availability/',{'date':self.day.isoformat(),'start_time':'09:00','end_time':'12:00','is_available':True})
        self.assertEqual(slot.status_code,201,slot.data)
        self.assertEqual(DoctorAvailability.objects.get(pk=slot.data['id']).doctor,self.doctor)
        self.assertEqual(self.client.post('/api/availability/',{'date':self.day.isoformat(),'start_time':'11:00','end_time':'13:00'}).status_code,400)
        self.client.force_authenticate(self.patient_user)
        payload={'doctor':self.doctor.pk,'date':self.day.isoformat(),'time':'13:00'}
        self.assertEqual(self.client.post('/api/appointments/',payload).status_code,400)
        self.assertEqual(self.client.post('/api/appointments/',{**payload,'time':'10:00'}).status_code,201)


class ModuleCreationTests(TestCase):
    def test_new_record_prescription_bill_and_department(self):
        client=APIClient()
        User=get_user_model()
        admin=User.objects.create_user(username='module_admin',password='test-password',role='ADMIN')
        doctor_user=User.objects.create_user(username='module_doctor',password='test-password',role='DOCTOR')
        receptionist=User.objects.create_user(username='module_reception',password='test-password',role='RECEPTIONIST')
        doctor=Doctor.objects.create(user=doctor_user,doctor_id='DOC-MODULE',specialization='General Medicine')
        patient=Patient.objects.create(patient_id='PAT-MODULE',full_name='Module Patient',gender='Female',phone='123')
        appointment=Appointment.objects.create(patient=patient,doctor=doctor,date=timezone.localdate()+timedelta(days=1),time=time(10),status='Confirmed')
        client.force_authenticate(admin)
        record=client.post('/api/medical-records/',{'appointment':appointment.pk,'diagnosis':'Migraine','symptoms':'Headache','treatment':'Rest','notes':'Follow up'})
        self.assertEqual(record.status_code,201,record.data)
        prescription=client.post('/api/prescriptions/',{'record':record.data['id'],'medicine':'Paracetamol','dosage':'500 mg','frequency':'Twice daily','duration':'3 days','instructions':'After food'})
        self.assertEqual(prescription.status_code,201,prescription.data)
        self.assertEqual(Prescription.objects.get(pk=prescription.data['id']).record_id,record.data['id'])
        bill=client.post('/api/bills/',{'patient':patient.pk,'appointment':appointment.pk,'consultation_fee':'100.00','medicine_charges':'20.00','lab_charges':'0.00','other_charges':'5.00','status':'Pending'})
        self.assertEqual(bill.status_code,201,bill.data)
        self.assertEqual(Bill.objects.get(pk=bill.data['id']).total,Decimal('125.00'))
        department=client.post('/api/departments/',{'name':'Neurology','description':'Brain and nerve care'})
        self.assertEqual(department.status_code,201,department.data)
        self.assertTrue(Department.objects.filter(name='Neurology').exists())
        client.force_authenticate(receptionist)
        # Per the PRD, reception generates invoices but cannot delete them.
        receptionist_bill=client.post('/api/bills/',{'patient':patient.pk})
        self.assertEqual(receptionist_bill.status_code,201)
        self.assertEqual(client.delete(f"/api/bills/{receptionist_bill.data['id']}/").status_code,403)
        self.assertEqual(client.post('/api/departments/',{'name':'Unauthorized'}).status_code,403)
