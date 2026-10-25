from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
import uuid
from .crypto import EncryptedTextField

class Hospital(models.Model):
    name=models.CharField(max_length=180)
    code=models.CharField(max_length=30,unique=True)
    address=models.TextField(blank=True)
    phone=models.CharField(max_length=20,blank=True)
    email=models.EmailField(blank=True)
    verified=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class User(AbstractUser):
    ROLE_CHOICES=[('SUPER_ADMIN','Super Admin'),('ADMIN','Hospital Admin'),('DOCTOR','Doctor'),('NURSE','Nurse'),('RECEPTIONIST','Receptionist'),('LAB_TECH','Lab Technician'),('PHARMACIST','Pharmacist'),('ACCOUNTANT','Accountant'),('PATIENT','Patient')]
    role=models.CharField(max_length=20,choices=ROLE_CHOICES,default='PATIENT')
    phone=models.CharField(max_length=20,blank=True)
    hospital=models.ForeignKey(Hospital,on_delete=models.PROTECT,null=True,blank=True,related_name='users')
    email_verified=models.BooleanField(default=False)
    phone_verified=models.BooleanField(default=False)

    def save(self,*args,**kwargs):
        # Django's createsuperuser command sets this flag. Keep MedCore's
        # application-level role aligned with the Django administrator role.
        if self.is_superuser:
            self.role='ADMIN'
        super().save(*args,**kwargs)

class Department(models.Model):
    hospital=models.ForeignKey(Hospital,on_delete=models.PROTECT,null=True,blank=True,related_name='departments')
    name=models.CharField(max_length=100,unique=True)
    description=models.TextField(blank=True)
    def __str__(self): return self.name

class Doctor(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='doctor_profile')
    doctor_id=models.CharField(max_length=30,unique=True)
    specialization=models.CharField(max_length=120)
    department=models.ForeignKey(Department,on_delete=models.SET_NULL,null=True,related_name='doctors')
    experience=models.PositiveIntegerField(default=0)
    consultation_fee=models.DecimalField(max_digits=10,decimal_places=2,default=0,validators=[MinValueValidator(0)])
    available=models.BooleanField(default=True)
    bio=models.TextField(blank=True)
    qualifications=models.CharField(max_length=255,blank=True)
    languages=models.CharField(max_length=150,blank=True)
    # PNG data URL drawn or uploaded by the doctor; overlaid on printed prescriptions.
    signature=models.TextField(blank=True)
    deleted_at=models.DateTimeField(null=True,blank=True)
    def __str__(self): return f'Dr. {self.user.get_full_name() or self.user.username}'

class Patient(models.Model):
    primary_doctor=models.ForeignKey(Doctor,on_delete=models.SET_NULL,null=True,blank=True,related_name='assigned_patients')
    directory_hidden=models.BooleanField(default=False,db_index=True)
    GENDER=[('Male','Male'),('Female','Female'),('Other','Other')]
    user=models.OneToOneField(User,on_delete=models.SET_NULL,related_name='patient_profile',null=True,blank=True)
    hospital=models.ForeignKey(Hospital,on_delete=models.PROTECT,null=True,blank=True,related_name='patients')
    patient_id=models.CharField(max_length=30,unique=True)
    full_name=models.CharField(max_length=150)
    dob=models.DateField(null=True,blank=True)
    gender=models.CharField(max_length=10,choices=GENDER)
    phone=models.CharField(max_length=20)
    email=models.EmailField(blank=True)
    blood_group=models.CharField(max_length=5,blank=True)
    address=models.TextField(blank=True)
    emergency_contact=models.CharField(max_length=20,blank=True)
    emergency_priority=models.BooleanField(default=False)
    allergies=models.CharField(max_length=255,blank=True)
    primary_concern=models.CharField(max_length=255,blank=True)
    ADMISSION_STATUS=[('Outpatient','Outpatient'),('Admitted','Admitted'),('Discharged','Discharged')]
    admission_status=models.CharField(max_length=20,choices=ADMISSION_STATUS,default='Outpatient')
    discharged_on=models.DateField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    deleted_at=models.DateTimeField(null=True,blank=True)
    def __str__(self): return f'{self.patient_id} - {self.full_name}'

class Appointment(models.Model):
    STATUS=[('Pending','Pending'),('Confirmed','Confirmed'),('In Progress','In Progress'),('Completed','Completed'),('Cancelled','Cancelled'),('No Show','No Show')]
    patient=models.ForeignKey(Patient,on_delete=models.CASCADE,related_name='appointments')
    doctor=models.ForeignKey(Doctor,on_delete=models.CASCADE,related_name='appointments')
    department=models.ForeignKey(Department,on_delete=models.SET_NULL,null=True,blank=True,related_name='appointments')
    date=models.DateField(); time=models.TimeField()
    reason=models.CharField(max_length=255,blank=True)
    status=models.CharField(max_length=20,choices=STATUS,default='Pending')
    notes=models.TextField(blank=True)
    is_emergency=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    deleted_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        ordering=['-date','-time']
        indexes=[models.Index(fields=['date','time'])]
        constraints=[
            models.UniqueConstraint(fields=['doctor','date','time'],condition=~Q(status__in=['Cancelled','No Show']),name='unique_active_doctor_slot'),
            models.UniqueConstraint(fields=['patient','date','time'],condition=~Q(status__in=['Cancelled','No Show']),name='unique_active_patient_slot'),
        ]

class DoctorAvailability(models.Model):
    doctor=models.ForeignKey(Doctor,on_delete=models.CASCADE,related_name='availability_slots')
    date=models.DateField()
    start_time=models.TimeField()
    end_time=models.TimeField()
    is_available=models.BooleanField(default=True)
    class Meta: ordering=['date','start_time']
    def __str__(self): return f'{self.doctor} - {self.date} {self.start_time}'

class MedicalRecord(models.Model):
    SOURCE_CHOICES=[('Clinical','Clinical'),('Patient submitted','Patient submitted')]
    patient=models.ForeignKey(Patient,on_delete=models.CASCADE,related_name='records')
    doctor=models.ForeignKey(Doctor,on_delete=models.SET_NULL,null=True,blank=True,related_name='records')
    appointment=models.ForeignKey(Appointment,on_delete=models.SET_NULL,null=True,blank=True,related_name='record')
    source=models.CharField(max_length=20,choices=SOURCE_CHOICES,default='Clinical')
    # Clinical narrative is encrypted at rest (see api/crypto.py).
    diagnosis=EncryptedTextField(); symptoms=EncryptedTextField(blank=True); treatment=EncryptedTextField(blank=True); notes=EncryptedTextField(blank=True)
    blood_pressure=models.CharField(max_length=20,blank=True)
    pulse=models.PositiveSmallIntegerField(null=True,blank=True)
    temperature=models.DecimalField(max_digits=4,decimal_places=1,null=True,blank=True)
    spo2=models.PositiveSmallIntegerField(null=True,blank=True)
    height_cm=models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True)
    weight_kg=models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True)
    icd10_code=models.CharField(max_length=20,blank=True)
    adverse_reactions=EncryptedTextField(blank=True)
    vaccination_history=models.JSONField(default=list,blank=True)
    family_history=models.JSONField(default=dict,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at']
        constraints=[models.UniqueConstraint(fields=['appointment'],condition=Q(appointment__isnull=False),name='unique_record_per_appointment')]

class Prescription(models.Model):
    SOURCE_CHOICES=MedicalRecord.SOURCE_CHOICES
    record=models.ForeignKey(MedicalRecord,on_delete=models.CASCADE,related_name='prescriptions')
    source=models.CharField(max_length=20,choices=SOURCE_CHOICES,default='Clinical')
    medicine=models.CharField(max_length=150); form=models.CharField(max_length=30,blank=True); dosage=models.CharField(max_length=100); frequency=models.CharField(max_length=100); duration=models.CharField(max_length=100); instructions=models.TextField(blank=True)

class Bill(models.Model):
    STATUS=[('Pending','Pending'),('Paid','Paid'),('Cancelled','Cancelled')]
    patient=models.ForeignKey(Patient,on_delete=models.CASCADE,related_name='bills')
    appointment=models.ForeignKey(Appointment,on_delete=models.SET_NULL,null=True,blank=True)
    consultation_fee=models.DecimalField(max_digits=10,decimal_places=2,default=0); medicine_charges=models.DecimalField(max_digits=10,decimal_places=2,default=0); lab_charges=models.DecimalField(max_digits=10,decimal_places=2,default=0); other_charges=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    total=models.DecimalField(max_digits=10,decimal_places=2,default=0); status=models.CharField(max_length=20,choices=STATUS,default='Pending'); created_at=models.DateTimeField(auto_now_add=True)
    def save(self,*args,**kwargs):
        self.total=self.consultation_fee+self.medicine_charges+self.lab_charges+self.other_charges
        super().save(*args,**kwargs)

class Bed(models.Model):
    STATUS=[('Available','Available'),('Occupied','Occupied'),('Cleaning','Cleaning'),('Reserved','Reserved')]
    ward=models.CharField(max_length=100)
    bed_number=models.CharField(max_length=30,unique=True)
    status=models.CharField(max_length=20,choices=STATUS,default='Available')
    patient=models.ForeignKey(Patient,on_delete=models.SET_NULL,null=True,blank=True,related_name='bed_assignments')
    admitted_on=models.DateField(null=True,blank=True)
    def __str__(self): return f'{self.ward} / {self.bed_number}'

class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications')
    title=models.CharField(max_length=150); message=models.TextField(); read=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)

class PatientDocument(models.Model):
    patient=models.ForeignKey(Patient,on_delete=models.PROTECT,related_name='documents')
    title=models.CharField(max_length=150)
    category=models.CharField(max_length=30,choices=[('Report','Report'),('Prescription','Prescription'),('Visit summary','Visit summary'),('Other','Other')])
    # Stored privately and delivered only through an authenticated endpoint.
    content=models.BinaryField()
    filename=models.CharField(max_length=200)
    content_type=models.CharField(max_length=50)
    uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class AppointmentReminder(models.Model):
    appointment=models.ForeignKey(Appointment,on_delete=models.CASCADE)
    scheduled_date=models.DateField()
    scheduled_time=models.TimeField()
    channel=models.CharField(max_length=10)
    # 24H is sent the day before; 1H shortly before the visit.
    kind=models.CharField(max_length=5,default='24H')
    sent_at=models.DateTimeField(auto_now_add=True)
    state=models.CharField(max_length=20,default='SENT')
    provider_reference=models.CharField(max_length=150,blank=True)
    last_error=models.CharField(max_length=200,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['appointment','scheduled_date','scheduled_time','channel','kind'],name='unique_appointment_reminder_kind')]

class CommunicationPreference(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='communication_preferences')
    email_reminders=models.BooleanField(default=False)
    sms_reminders=models.BooleanField(default=False)

class CareThread(models.Model):
    patient=models.ForeignKey(Patient,on_delete=models.PROTECT,related_name='care_threads')
    doctor=models.ForeignKey(Doctor,on_delete=models.PROTECT,related_name='care_threads')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['patient','doctor'],name='unique_patient_doctor_thread')]
        ordering=['-updated_at']

class CareMessage(models.Model):
    thread=models.ForeignKey(CareThread,on_delete=models.PROTECT,related_name='messages')
    sender=models.ForeignKey(User,on_delete=models.PROTECT)
    body=models.TextField(max_length=4000)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at','-id']

class LabTest(models.Model):
    name=models.CharField(max_length=150,unique=True)
    unit=models.CharField(max_length=30,blank=True)
    reference_range=models.CharField(max_length=100,blank=True)
    price=models.DecimalField(max_digits=10,decimal_places=2,default=0,validators=[MinValueValidator(0)])
    active=models.BooleanField(default=True)
    def __str__(self): return self.name

class LabOrder(models.Model):
    STATUS=[('ORDERED','Ordered'),('SAMPLE_COLLECTED','Sample collected'),('PROCESSING','Processing'),('REVIEW','Review'),('APPROVED','Approved'),('CANCELLED','Cancelled')]
    record=models.ForeignKey(MedicalRecord,on_delete=models.PROTECT,related_name='lab_orders')
    test=models.ForeignKey(LabTest,on_delete=models.PROTECT,related_name='orders')
    ordered_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='lab_orders_created')
    status=models.CharField(max_length=30,choices=STATUS,default='ORDERED')
    result_value=models.CharField(max_length=120,blank=True)
    result_notes=models.TextField(blank=True)
    report_url=models.URLField(blank=True)
    result_entered_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='lab_results_entered')
    approved_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='lab_orders_approved')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

class Medicine(models.Model):
    name=models.CharField(max_length=150,unique=True)
    form=models.CharField(max_length=30)
    manufacturer=models.CharField(max_length=150,blank=True)
    reorder_level=models.PositiveIntegerField(default=10)
    active=models.BooleanField(default=True)
    def __str__(self): return self.name

class MedicineBatch(models.Model):
    medicine=models.ForeignKey(Medicine,on_delete=models.PROTECT,related_name='batches')
    batch_number=models.CharField(max_length=80)
    manufacturing_date=models.DateField()
    expiry_date=models.DateField(db_index=True)
    quantity=models.PositiveIntegerField(default=0)
    unit_cost=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0)])
    mrp=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0)])
    quarantined=models.BooleanField(default=False)
    class Meta:
        ordering=['expiry_date','id']
        constraints=[models.UniqueConstraint(fields=['medicine','batch_number'],name='unique_medicine_batch')]

class PrescriptionItem(models.Model):
    prescription=models.ForeignKey(Prescription,on_delete=models.PROTECT,related_name='items')
    medicine=models.ForeignKey(Medicine,on_delete=models.PROTECT,related_name='prescription_items')
    dosage=models.CharField(max_length=100)
    frequency=models.CharField(max_length=100)
    duration=models.CharField(max_length=100)
    instructions=models.TextField(blank=True)
    dispensed_quantity=models.PositiveIntegerField(default=0)
    dispensed_at=models.DateTimeField(null=True,blank=True)

class BillItem(models.Model):
    CATEGORY=[('CONSULTATION','Consultation'),('LAB','Laboratory'),('PHARMACY','Pharmacy'),('ROOM','Room'),('OTHER','Other')]
    bill=models.ForeignKey(Bill,on_delete=models.PROTECT,related_name='items')
    category=models.CharField(max_length=20,choices=CATEGORY)
    description=models.CharField(max_length=200)
    quantity=models.PositiveIntegerField(default=1)
    unit_price=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0)])
    @property
    def amount(self): return self.quantity*self.unit_price

class Payment(models.Model):
    METHOD=[('CASH','Cash'),('STRIPE','Stripe'),('RAZORPAY','Razorpay')]
    STATUS=[('PENDING','Pending'),('PAID','Paid'),('FAILED','Failed'),('REFUNDED','Refunded')]
    bill=models.ForeignKey(Bill,on_delete=models.PROTECT,related_name='payments')
    amount=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0)])
    method=models.CharField(max_length=20,choices=METHOD)
    status=models.CharField(max_length=20,choices=STATUS,default='PENDING')
    provider_reference=models.CharField(max_length=150,blank=True,unique=True,null=True)
    created_at=models.DateTimeField(auto_now_add=True)

class PaymentCheckout(models.Model):
    bill=models.OneToOneField(Bill,on_delete=models.PROTECT,related_name='checkout')
    reference=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    amount=models.DecimalField(max_digits=10,decimal_places=2)
    provider_id=models.CharField(max_length=150,unique=True,null=True,blank=True)
    url=models.URLField(blank=True)
    state=models.CharField(max_length=20,default='CREATING')
    mode=models.CharField(max_length=10,default='test')
    created_at=models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True)
    method=models.CharField(max_length=10)
    path=models.CharField(max_length=500)
    status_code=models.PositiveSmallIntegerField()
    ip_address=models.GenericIPAddressField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class VitalsEntry(models.Model):
    """Nurse-recorded observations. Append-only, like medical records."""
    patient=models.ForeignKey(Patient,on_delete=models.PROTECT,related_name='vitals')
    recorded_by=models.ForeignKey(User,on_delete=models.PROTECT,related_name='vitals_recorded')
    blood_pressure=models.CharField(max_length=20,blank=True)
    pulse=models.PositiveSmallIntegerField(null=True,blank=True)
    temperature=models.DecimalField(max_digits=4,decimal_places=1,null=True,blank=True)
    spo2=models.PositiveSmallIntegerField(null=True,blank=True)
    height_cm=models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True)
    weight_kg=models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True)
    medication_notes=EncryptedTextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class InsuranceClaim(models.Model):
    STATUS=[('DRAFT','Draft'),('SUBMITTED','Submitted to TPA'),('APPROVED','Approved'),('REJECTED','Rejected'),('SETTLED','Settled')]
    bill=models.ForeignKey(Bill,on_delete=models.PROTECT,related_name='claims')
    provider=models.CharField(max_length=120)
    policy_number=models.CharField(max_length=80)
    tpa_name=models.CharField(max_length=120,blank=True)
    claimed_amount=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0)])
    approved_amount=models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    status=models.CharField(max_length=20,choices=STATUS,default='DRAFT')
    notes=models.TextField(blank=True)
    created_by=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-created_at']

class VerificationCode(models.Model):
    """Single-use 6-digit OTP. Only a hash of the code is stored."""
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='verification_codes')
    channel=models.CharField(max_length=10,choices=[('email','Email'),('phone','Phone')])
    code_hash=models.CharField(max_length=128)
    expires_at=models.DateTimeField()
    attempts=models.PositiveSmallIntegerField(default=0)
    used=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)

@receiver(pre_delete,sender=VitalsEntry)
def preserve_vitals(sender,instance,**kwargs):
    raise ProtectedError('Vitals entries cannot be deleted.',[instance])

class ImportedAdmission(models.Model):
    primary_doctor=models.ForeignKey(Doctor,on_delete=models.SET_NULL,null=True,blank=True,related_name='assigned_imported_patients')
    directory_hidden=models.BooleanField(default=False,db_index=True)
    """One historical admission from the supplied CSV; no account is implied."""
    source_row=models.PositiveIntegerField(unique=True)
    patient_name=models.CharField(max_length=150)
    age=models.PositiveSmallIntegerField()
    gender=models.CharField(max_length=20)
    blood_type=models.CharField(max_length=5)
    medical_condition=models.CharField(max_length=120)
    admission_date=models.DateField(db_index=True)
    doctor_name=models.CharField(max_length=150)
    hospital=models.CharField(max_length=200)
    insurance_provider=models.CharField(max_length=120)
    billing_amount=models.DecimalField(max_digits=12,decimal_places=2)
    room_number=models.CharField(max_length=30)
    admission_type=models.CharField(max_length=30)
    discharge_date=models.DateField(null=True,blank=True)
    medication=models.CharField(max_length=150)
    test_results=models.CharField(max_length=100)
    class Meta:
        ordering=['-admission_date','-source_row']


@receiver(pre_delete,sender=Patient)
def preserve_patient_record(sender,instance,**kwargs):
    raise ProtectedError('Patient records cannot be deleted.',[instance])

@receiver(pre_delete,sender=MedicalRecord)
def preserve_medical_record(sender,instance,**kwargs):
    raise ProtectedError('Medical records cannot be permanently deleted.',[instance])
