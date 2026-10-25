import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','medcore.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from api.models import Department,Doctor,Patient,Appointment,DoctorAvailability,MedicalRecord,Prescription,Bill,Bed,Notification
from datetime import date,time,timedelta
from decimal import Decimal
U=get_user_model(); today=date.today()

def user(username, role, first, last, phone, password):
    u,_=U.objects.get_or_create(username=username,defaults={'first_name':first,'last_name':last,'phone':phone,'role':role,'email':f'{username}@medcore.local'})
    u.first_name=first; u.last_name=last; u.phone=phone; u.role=role; u.email=f'{username}@medcore.local'; u.set_password(password)
    if role=='ADMIN': u.is_staff=True; u.is_superuser=True
    u.save(); return u

admin=user('admin','ADMIN','MedCore','Admin','9000000001','admin123')
reception=user('reception1','RECEPTIONIST','Riya','Reception','9000000002','reception123')

# 12 departments
D=[('Cardiology','Heart and cardiovascular care'),('Pediatrics','Child and adolescent care'),('Orthopedics','Bones, joints and mobility'),('Dermatology','Skin, hair and nail care'),('Neurology','Brain and nervous system'),('General Medicine','Primary and general medical care'),('Gynecology','Women health and maternity care'),('ENT','Ear, nose and throat care'),('Ophthalmology','Eye and vision care'),('Oncology','Cancer diagnosis and treatment'),('Pulmonology','Lung and respiratory care'),('Gastroenterology','Digestive system care')]
depts=[]
for n,desc in D: depts.append(Department.objects.get_or_create(name=n,defaults={'description':desc})[0])

# 12 doctors across specialties
doc_specs=[('doctor1','Ananya','Rao','DOC001','Cardiology',8,800),('doctor2','Vikram','Mehta','DOC002','Pediatrics',10,650),('doctor3','Priya','Nair','DOC003','Orthopedics',12,750),('doctor4','Arjun','Kapoor','DOC004','Dermatology',7,600),('doctor5','Neha','Iyer','DOC005','Neurology',11,900),('doctor6','Karan','Shah','DOC006','General Medicine',9,500),('doctor7','Meera','Das','DOC007','Gynecology',13,850),('doctor8','Rahul','Verma','DOC008','ENT',6,550),('doctor9','Sneha','Joshi','DOC009','Ophthalmology',8,700),('doctor10','Amit','Kulkarni','DOC010','Oncology',15,1200),('doctor11','Pooja','Menon','DOC011','Pulmonology',9,900),('doctor12','Suresh','Patel','DOC012','Gastroenterology',14,950)]
docs=[]
for i,(un,fn,ln,did,spec,exp,fee) in enumerate(doc_specs):
    du=user(un,'DOCTOR',fn,ln,f'91{8000000000+i}', 'doctor123' if un=='doctor1' else 'Doctor@123')
    dep=next(d for d in depts if d.name==spec)
    doc,_=Doctor.objects.get_or_create(user=du,defaults={'doctor_id':did,'specialization':spec,'department':dep,'experience':exp,'consultation_fee':fee,'available':True,'bio':f'{spec} specialist with {exp} years of clinical experience.'})
    doc.doctor_id=did; doc.department=dep; doc.specialization=spec; doc.experience=exp; doc.consultation_fee=fee; doc.available=True; doc.save(); docs.append(doc)

# 15 patients with varied demographics and emergency flags
pdata=[
('PAT001','Rahul Sharma','2001-04-15','Male','9876543210','O+','Bengaluru',False,'None'),('PAT002','Aisha Khan','1995-08-22','Female','9876543211','A+','Mysuru',False,'Penicillin'),('PAT003','Arjun Reddy','1988-01-10','Male','9876543212','B+','Hyderabad',True,'Peanuts'),('PAT004','Kavya Nair','2010-12-02','Female','9876543213','AB+','Kochi',False,'Dust'),('PAT005','Rohan Gupta','1978-06-19','Male','9876543214','O-','Delhi',True,'Aspirin'),('PAT006','Sneha Rao','1999-03-28','Female','9876543215','B-','Bengaluru',False,'None'),('PAT007','Imran Ali','1969-11-14','Male','9876543216','AB-','Chennai',True,'Sulfa drugs'),('PAT008','Diya Thomas','2005-07-30','Female','9876543217','O+','Mangaluru',False,'None'),('PAT009','Manoj Kumar','1958-02-17','Male','9876543218','A-','Bengaluru',True,'Latex'),('PAT010','Ananya Singh','1992-10-05','Female','9876543219','O-','Pune',False,'None'),('PAT011','Vivek Joshi','1984-09-09','Male','9876543220','B+','Hubballi',False,'Dust'),('PAT012','Megha Patel','1975-05-21','Female','9876543221','A+','Ahmedabad',False,'None'),('PAT013','Aditya Bose','2002-01-25','Male','9876543222','AB+','Kolkata',False,'Seafood'),('PAT014','Nisha George','1990-12-11','Female','9876543223','B+','Kochi',True,'None'),('PAT015','Farhan Sheikh','1962-07-07','Male','9876543224','O+','Bengaluru',False,'Penicillin')]
patients=[]
for idx,row in enumerate(pdata):
    pid,name,dob,gender,phone,bg,address,emergency,allergy=row
    uname='patient1' if idx==0 else f'patient{idx+1}'
    pu=user(uname,'PATIENT',*name.split(' ',1),phone,'patient123' if idx==0 else 'Patient@123')
    p,_=Patient.objects.get_or_create(patient_id=pid,defaults={'user':pu,'full_name':name,'dob':date.fromisoformat(dob),'gender':gender,'phone':phone,'email':f'{uname}@medcore.local','blood_group':bg,'address':address,'emergency_contact':phone,'emergency_priority':emergency,'allergies':allergy})
    p.user=pu; p.full_name=name; p.dob=date.fromisoformat(dob); p.gender=gender; p.phone=phone; p.email=f'{uname}@medcore.local'; p.blood_group=bg; p.address=address; p.emergency_contact=phone; p.emergency_priority=emergency; p.allergies=allergy; p.save(); patients.append(p)

# 30 appointments: all four statuses
statuses=['Pending','Confirmed','Completed','Cancelled']
reasons=['Routine consultation','Follow-up visit','Annual screening','Chest discomfort','Skin rash','Joint pain','Migraine review','Child wellness check','Breathing difficulty','Vision check']
apps=[]
for i in range(30):
    p=patients[i%len(patients)]; d=docs[i%len(docs)]; st=statuses[i%4]; day=today+timedelta(days=(i%18)-5); tm=time(9+(i%8), (i*15)%60)
    a,_=Appointment.objects.get_or_create(patient=p,doctor=d,date=day,time=tm,defaults={'reason':reasons[i%len(reasons)],'status':st,'notes':'Demo appointment generated for HMS testing.'})
    a.status=st; a.reason=reasons[i%len(reasons)]; a.save(); apps.append(a)

# 18 medical records and 25 prescriptions
for i,a in enumerate(apps[:18]):
    rec,_=MedicalRecord.objects.get_or_create(patient=a.patient,doctor=a.doctor,appointment=a,defaults={'diagnosis':['Hypertension','Seasonal allergy','Lower back pain','Migraine','Dermatitis','Asthma'][i%6],'symptoms':'Symptoms recorded during consultation.','treatment':'Clinical treatment plan and follow-up advised.','notes':'Timeline entry for demo data.'})
    rec.diagnosis=['Hypertension','Seasonal allergy','Lower back pain','Migraine','Dermatitis','Asthma'][i%6]; rec.save()
    for j in range(1+(i%2)):
        Prescription.objects.get_or_create(record=rec,medicine=['Amlodipine','Cetirizine','Paracetamol','Omeprazole','Vitamin D','Montelukast'][i%6],defaults={'dosage':'5 mg','frequency':'Once daily','duration':'14 days','instructions':'Take as directed after food.'})

# 24 bills with paid/pending/cancelled
for i,a in enumerate(apps[:24]):
    st=['Paid','Pending','Paid','Cancelled'][i%4]
    Bill.objects.update_or_create(patient=a.patient,appointment=a,defaults={'consultation_fee':Decimal(str(a.doctor.consultation_fee)),'lab_charges':Decimal(200+(i%4)*150),'medicine_charges':Decimal(100+(i%5)*80),'other_charges':Decimal(0 if i%3 else 150),'status':st})

# 36 availability slots for booking/calendar
for i in range(36):
    d=docs[i%len(docs)]; day=today+timedelta(days=i%14); start=time(9+(i%6),0); end=time(start.hour+1,0)
    DoctorAvailability.objects.get_or_create(doctor=d,date=day,start_time=start,defaults={'end_time':end,'is_available':i%5!=0})

# 24 beds across wards
wards=['General Ward','ICU','Pediatrics','Orthopedics','Maternity','Emergency']
for i in range(24):
    status=['Available','Occupied','Available','Cleaning','Reserved'][i%5]
    Bed.objects.update_or_create(bed_number=f'B{i+1:02d}',defaults={'ward':wards[i%len(wards)],'status':status,'patient':patients[i%len(patients)] if status=='Occupied' else None,'admitted_on':today if status=='Occupied' else None})

# Notifications for demo accounts
for u in [admin,reception]+[d.user for d in docs[:3]]+[patients[0].user]:
    Notification.objects.create(user=u,title='Appointment Reminder',message='You have an upcoming appointment. Please check the calendar for details.')
    Notification.objects.create(user=u,title='Payment Alert',message='A billing item has been updated in MedCore HMS.')
print('Rich demo data ready.')
print('Admin: admin / admin123')
print('Receptionist: reception1 / reception123')
print('Doctor: doctor1 / doctor123')
print('Patient: patient1 / patient123')
