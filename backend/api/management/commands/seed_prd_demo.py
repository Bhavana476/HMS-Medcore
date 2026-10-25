"""Invented demo data for reviewers: 2 hospitals, one login per role, 8 doctors,
30 patients and two weeks of appointments. Never run against a real hospital database."""
import random
from datetime import time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from api.models import (Hospital, Department, Doctor, Patient, Appointment, DoctorAvailability, MedicalRecord, Prescription,
                        PrescriptionItem, Bill, BillItem, Bed, LabTest, LabOrder, Medicine, MedicineBatch)

PASSWORD='Demo@12345'
ROLES=['SUPER_ADMIN','ADMIN','DOCTOR','NURSE','RECEPTIONIST','LAB_TECH','PHARMACIST','ACCOUNTANT','PATIENT']
SPECIALTIES=[('Cardiology','Cardiologist'),('Neurology','Neurologist'),('Orthopaedics','Orthopaedic Surgeon'),('Paediatrics','Paediatrician'),
             ('Dermatology','Dermatologist'),('General Medicine','General Physician'),('ENT','ENT Specialist'),('Gynaecology','Gynaecologist')]
FIRST=['Aarav','Diya','Kabir','Meera','Rohan','Saanvi','Vihaan','Ananya','Arjun','Isha','Reyansh','Kavya','Aditya','Nisha','Dev']
LAST=['Sharma','Iyer','Reddy','Nair','Gupta','Das','Menon','Rao','Patel','Khan']

class Command(BaseCommand):
    help='Create invented PRD demo data (demo_* logins, password Demo@12345).'
    def add_arguments(self,parser): parser.add_argument('--yes',action='store_true',help='Confirm this is a demo database.')
    def handle(self,*args,**options):
        if not options['yes']: raise CommandError('This writes invented data. Re-run with --yes on a demo database only.')
        User=get_user_model(); rng=random.Random(42); today=timezone.localdate()
        with transaction.atomic():
            north,_=Hospital.objects.get_or_create(code='DEMO-N',defaults={'name':'MedCore Demo North','verified':True,'address':'12 Demo Road, Bengaluru'})
            south,_=Hospital.objects.get_or_create(code='DEMO-S',defaults={'name':'MedCore Demo South','verified':True,'address':'45 Sample Street, Chennai'})
            def user(username,role,first,last,hospital=north,**extra):
                u,created=User.objects.get_or_create(username=username,defaults={'role':role,'first_name':first,'last_name':last,'hospital':hospital,'email':f'{username}@example.com',**extra})
                if created: u.set_password(PASSWORD); u.save()
                return u
            for role in ROLES:
                if role not in {'DOCTOR','PATIENT'}: user(f'demo_{role.lower()}',role,role.title().replace('_',' '),'Demo',None if role=='SUPER_ADMIN' else north)
            doctors=[]
            for i,(dept_name,title) in enumerate(SPECIALTIES):
                dept,_=Department.objects.get_or_create(name=dept_name,defaults={'hospital':north})
                u=user('demo_doctor' if i==0 else f'demo_doctor{i+1}','DOCTOR',FIRST[i],LAST[i],north if i<5 else south)
                d,_=Doctor.objects.get_or_create(user=u,defaults={'doctor_id':f'DEMO-D{i+1:02d}','specialization':title,'department':dept,'experience':5+i,'consultation_fee':Decimal(400+50*i),'qualifications':'MBBS, MD','languages':'English, Hindi'})
                doctors.append(d)
                for day in range(0,14):
                    DoctorAvailability.objects.get_or_create(doctor=d,date=today+timedelta(days=day),start_time=time(9),defaults={'end_time':time(13)})
            patients=[]
            for i in range(30):
                first,last=FIRST[i%len(FIRST)],LAST[(i*3)%len(LAST)]
                u=user('demo_patient' if i==0 else f'demo_patient{i+1}','PATIENT',first,last,None)
                p,_=Patient.objects.get_or_create(patient_id=f'DEMO-P{i+1:03d}',defaults={'user':u,'hospital':north if i<20 else south,'full_name':f'{first} {last}','gender':rng.choice(['Male','Female','Other']),'phone':f'+9198{i:08d}','blood_group':rng.choice(['A+','B+','O+','AB+','O-'])})
                patients.append(p)
            hb,_=LabTest.objects.get_or_create(name='Haemoglobin',defaults={'unit':'g/dL','reference_range':'13.0-17.5','price':Decimal('250')})
            LabTest.objects.get_or_create(name='Fasting blood sugar',defaults={'unit':'mg/dL','reference_range':'70-100','price':Decimal('150')})
            for name,form in [('Paracetamol 500','tablet'),('Amoxicillin 250','capsule'),('Cough syrup','syrup'),('Insulin','injection')]:
                med,_=Medicine.objects.get_or_create(name=name,defaults={'form':form,'reorder_level':50})
                MedicineBatch.objects.get_or_create(medicine=med,batch_number=f'{name[:3].upper()}-A',defaults={'manufacturing_date':today-timedelta(days=200),'expiry_date':today+timedelta(days=20),'quantity':40,'unit_cost':Decimal('2'),'mrp':Decimal('5')})
                MedicineBatch.objects.get_or_create(medicine=med,batch_number=f'{name[:3].upper()}-B',defaults={'manufacturing_date':today-timedelta(days=30),'expiry_date':today+timedelta(days=500),'quantity':300,'unit_cost':Decimal('2'),'mrp':Decimal('5')})
            for ward in ['General','ICU']:
                for n in range(1,7): Bed.objects.get_or_create(bed_number=f'DEMO-{ward[:3]}-{n}',defaults={'ward':ward,'status':rng.choice(['Available','Occupied','Cleaning'])})
            admin=User.objects.get(username='demo_admin')
            for day in range(-7,7):
                for slot in range(3):
                    p=patients[(day+7)*3%30+slot]; d=doctors[(day+slot)%len(doctors)]
                    when=today+timedelta(days=day); at=time(9+slot)
                    if Appointment.objects.filter(doctor=d,date=when,time=at).exists() or Appointment.objects.filter(patient=p,date=when,time=at).exists(): continue
                    status='Completed' if day<0 else rng.choice(['Pending','Confirmed'])
                    a=Appointment.objects.create(patient=p,doctor=d,department=d.department,date=when,time=at,status=status,reason='Demo consultation')
                    if status=='Completed':
                        r=MedicalRecord.objects.create(patient=p,doctor=d,appointment=a,diagnosis=rng.choice(['Viral fever','Hypertension','Migraine','Back pain']),pulse=rng.randint(60,95),blood_pressure='120/80',height_cm=Decimal('170'),weight_kg=Decimal('68'))
                        rx=Prescription.objects.create(record=r,medicine='Paracetamol 500',dosage='500 mg',frequency='TDS',duration='3 days')
                        PrescriptionItem.objects.create(prescription=rx,medicine=Medicine.objects.get(name='Paracetamol 500'),dosage='500 mg',frequency='TDS',duration='3 days')
                        LabOrder.objects.create(record=r,test=hb,ordered_by=d.user)
                        bill=Bill.objects.create(patient=p,appointment=a)
                        BillItem.objects.create(bill=bill,category='CONSULTATION',description='Consultation',unit_price=d.consultation_fee)
                        BillItem.objects.create(bill=bill,category='LAB',description='Haemoglobin',unit_price=hb.price)
                        from api.operations import recalculate_bill
                        recalculate_bill(bill)
                        if rng.random()<.6: bill.status='Paid'; bill.save()
        self.stdout.write(self.style.SUCCESS(f'Demo data ready. Logins: demo_<role> (e.g. demo_admin, demo_pharmacist), password {PASSWORD}'))
