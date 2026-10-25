from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Department,Doctor,Patient,Appointment,DoctorAvailability,MedicalRecord,Prescription,Bill,Bed,Notification
User=get_user_model()
class RegisterSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True,min_length=6)
    class Meta: model=User; fields=['username','email','password','first_name','last_name','phone','role']
    def create(self,v): password=v.pop('password'); return User.objects.create_user(**v,password=password)
class UserSerializer(serializers.ModelSerializer):
    class Meta: model=User; fields=['id','username','email','first_name','last_name','phone','role','hospital','email_verified','phone_verified']; read_only_fields=['email_verified','phone_verified']
class DepartmentSerializer(serializers.ModelSerializer):
    doctor_count=serializers.IntegerField(source='doctors.count',read_only=True)
    class Meta: model=Department; fields='__all__'
class DoctorSerializer(serializers.ModelSerializer):
    name=serializers.SerializerMethodField()
    department_name=serializers.CharField(source='department.name',read_only=True)
    class Meta: model=Doctor; fields=['id','user','doctor_id','specialization','department','department_name','experience','consultation_fee','available','bio','qualifications','languages','name']
    def get_name(self,obj): return obj.user.get_full_name() or obj.user.username
class PatientSerializer(serializers.ModelSerializer):
    assigned_doctor=serializers.SerializerMethodField()
    appointment_date=serializers.SerializerMethodField()
    class Meta: model=Patient; fields='__all__'
    def get_next_appointment(self,obj):
        return obj.appointments.select_related('doctor__user').filter(date__gte=timezone.localdate()).order_by('date','time').first()
    def get_assigned_doctor(self,obj):
        if obj.primary_doctor_id:
            return obj.primary_doctor.user.get_full_name() or obj.primary_doctor.user.username
        appointment=self.get_next_appointment(obj)
        if not appointment: return ''
        return appointment.doctor.user.get_full_name() or appointment.doctor.user.username
    def get_appointment_date(self,obj):
        appointment=self.get_next_appointment(obj)
        return appointment.date.isoformat() if appointment else None
class AppointmentSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    doctor_name=serializers.SerializerMethodField()
    emergency_priority=serializers.BooleanField(source='patient.emergency_priority',read_only=True)
    class Meta: model=Appointment; fields='__all__'; validators=[]
    def get_doctor_name(self,obj): return obj.doctor.user.get_full_name() or obj.doctor.user.username
    def get_fields(self):
        fields=super().get_fields()
        request=self.context.get('request')
        if request and getattr(request.user,'role',None)=='DOCTOR': fields['doctor'].required=False
        if request and getattr(request.user,'role',None)=='PATIENT': fields['patient'].required=False
        return fields
    def validate(self,attrs):
        request=self.context.get('request')
        patient=attrs.get('patient',self.instance.patient if self.instance else None)
        doctor=attrs.get('doctor',self.instance.doctor if self.instance else None)
        if request and getattr(request.user,'role',None)=='PATIENT':
            own_patient=Patient.objects.filter(user=request.user).first()
            if not own_patient or (patient and patient!=own_patient):
                raise serializers.ValidationError({'patient':'You can only book your own appointment.'})
            patient=own_patient
            attrs['patient']=own_patient
        if request and getattr(request.user,'role',None)=='DOCTOR':
            own_doctor=Doctor.objects.filter(user=request.user).first()
            if not own_doctor or (doctor and doctor!=own_doctor):
                raise serializers.ValidationError({'doctor':'You can only schedule your own appointments.'})
            if self.instance and any(name in attrs for name in ('patient','doctor','date','time')):
                raise serializers.ValidationError('Doctors may update encounter status, reason, or notes only.')
            doctor=own_doctor
            attrs['doctor']=own_doctor
        day=attrs.get('date',self.instance.date if self.instance else None)
        slot=attrs.get('time',self.instance.time if self.instance else None)
        status=attrs.get('status',self.instance.status if self.instance else 'Pending')
        emergency=attrs.get('is_emergency',self.instance.is_emergency if self.instance else False)
        if attrs.get('is_emergency') and request and request.user.role=='PATIENT':
            raise serializers.ValidationError({'is_emergency':'Call the hospital for emergencies; staff will flag the booking.'})
        if self.instance is None:
            if status!='Pending':
                raise serializers.ValidationError({'status':'New appointments must start as Pending.'})
            if day and day<timezone.localdate():
                raise serializers.ValidationError({'date':'Choose today or a future date.'})
            if doctor and not doctor.available:
                raise serializers.ValidationError({'doctor':'This doctor is not available.'})
        elif status!=self.instance.status:
            transitions={
                'Pending':{'Confirmed','Cancelled'},
                'Confirmed':{'In Progress','Cancelled','No Show'},
                'In Progress':{'Completed'},
                'Completed':set(),'Cancelled':set(),'No Show':set(),
            }
            if status not in transitions.get(self.instance.status,set()):
                raise serializers.ValidationError({'status':f'Cannot change {self.instance.status} to {status}.'})
            if request and getattr(request.user,'role',None)=='RECEPTIONIST' and status in {'In Progress','Completed'}:
                raise serializers.ValidationError({'status':'Only a doctor can advance a clinical encounter.'})
        if patient and doctor and day and slot and status not in {'Cancelled','No Show'}:
            availability=DoctorAvailability.objects.filter(doctor=doctor,date=day)
            # Emergency bookings bypass published availability.
            if self.instance is None and availability.exists() and not emergency and not (patient and patient.emergency_priority):
                if not availability.filter(is_available=True,start_time__lte=slot,end_time__gt=slot).exists():
                    raise serializers.ValidationError({'time':'Choose a time inside the doctorâ€™s available hours.'})
            conflicts=Appointment.objects.filter(date=day,time=slot).exclude(status__in=['Cancelled','No Show'])
            if self.instance: conflicts=conflicts.exclude(pk=self.instance.pk)
            if conflicts.filter(doctor=doctor).exists():
                raise serializers.ValidationError({'time':'This doctor already has an appointment at that time.'})
            if conflicts.filter(patient=patient).exists():
                raise serializers.ValidationError({'time':'This patient already has an appointment at that time.'})
        return attrs
class AvailabilitySerializer(serializers.ModelSerializer):
    doctor_name=serializers.SerializerMethodField(); specialization=serializers.CharField(source='doctor.specialization',read_only=True)
    class Meta: model=DoctorAvailability; fields='__all__'
    def get_doctor_name(self,obj): return obj.doctor.user.get_full_name() or obj.doctor.user.username
    def get_fields(self):
        fields=super().get_fields()
        request=self.context.get('request')
        if request and getattr(request.user,'role',None)=='DOCTOR': fields['doctor'].required=False
        return fields
    def validate(self,attrs):
        request=self.context.get('request')
        doctor=attrs.get('doctor',self.instance.doctor if self.instance else None)
        if request and getattr(request.user,'role',None)=='DOCTOR':
            own=Doctor.objects.filter(user=request.user).first()
            if not own or (doctor and doctor!=own):
                raise serializers.ValidationError({'doctor':'You can only manage your own availability.'})
            doctor=own
            attrs['doctor']=own
        day=attrs.get('date',self.instance.date if self.instance else None)
        start=attrs.get('start_time',self.instance.start_time if self.instance else None)
        end=attrs.get('end_time',self.instance.end_time if self.instance else None)
        if start and end and start>=end:
            raise serializers.ValidationError({'end_time':'End time must be after start time.'})
        if self.instance is None and day and day<timezone.localdate():
            raise serializers.ValidationError({'date':'Choose today or a future date.'})
        if doctor and day and start and end:
            overlaps=DoctorAvailability.objects.filter(doctor=doctor,date=day,start_time__lt=end,end_time__gt=start)
            if self.instance: overlaps=overlaps.exclude(pk=self.instance.pk)
            if overlaps.exists():
                raise serializers.ValidationError({'start_time':'This slot overlaps another availability period.'})
        return attrs
FAMILY_FLAGS={'diabetes','hypertension','cancer','cardiac'}
class MedicalRecordSerializer(serializers.ModelSerializer):
    patient=serializers.CharField(source='patient.full_name',read_only=True); doctor=serializers.SerializerMethodField()
    bmi=serializers.SerializerMethodField()
    class Meta:
        model=MedicalRecord
        fields=['id','patient','doctor','appointment','source','diagnosis','icd10_code','symptoms','treatment','notes',
                'blood_pressure','pulse','temperature','spo2','height_cm','weight_kg','bmi','adverse_reactions',
                'vaccination_history','family_history','created_at']
        read_only_fields=['created_at','source']
    def get_doctor(self,obj): return (obj.doctor.user.get_full_name() or obj.doctor.user.username) if obj.doctor_id else ''
    def get_bmi(self,obj):
        from .operations import bmi
        return bmi(obj.height_cm,obj.weight_kg)
    def validate_family_history(self,value):
        if not isinstance(value,dict) or not set(value)<=FAMILY_FLAGS or not all(isinstance(v,bool) for v in value.values()):
            raise serializers.ValidationError('Use true/false flags for diabetes, hypertension, cancer and cardiac.')
        return value
    def validate_vaccination_history(self,value):
        if not isinstance(value,list) or not all(isinstance(v,dict) and v.get('vaccine') and v.get('date') for v in value):
            raise serializers.ValidationError('Each vaccination needs a vaccine name and date (batch and next due are optional).')
        return [{k:str(v.get(k,''))[:80] for k in ('vaccine','date','batch','next_due')} for v in value]
    def validate(self,attrs):
        appointment=attrs.get('appointment')
        if not appointment:
            raise serializers.ValidationError({'appointment':'Choose an appointment for this encounter.'})
        if appointment.status not in {'Confirmed','In Progress'}:
            raise serializers.ValidationError({'appointment':'Confirm the appointment before starting an encounter.'})
        if MedicalRecord.objects.filter(appointment=appointment).exists():
            raise serializers.ValidationError({'appointment':'This appointment already has a medical record.'})
        return attrs
class PrescriptionSerializer(serializers.ModelSerializer):
    patient=serializers.CharField(source='record.patient.full_name',read_only=True)
    class Meta: model=Prescription; fields='__all__'; read_only_fields=['source']
class BillSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    item_count=serializers.IntegerField(source='items.count',read_only=True)
    class Meta: model=Bill; fields='__all__'
    def validate(self,attrs):
        # Itemised invoices derive their totals from line items only.
        if self.instance and self.instance.items.exists() and {'consultation_fee','medicine_charges','lab_charges','other_charges'}&set(attrs):
            raise serializers.ValidationError('This invoice is itemised. Change its line items instead.')
        return attrs
class BedSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    class Meta: model=Bed; fields='__all__'
class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model=Notification; fields='__all__'; read_only_fields=['user']
