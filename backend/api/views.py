from django.db import IntegrityError, transaction
from django.db.models import Q, Sum, Count
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Department,Doctor,Patient,Appointment,DoctorAvailability,MedicalRecord,Prescription,Bill,Bed,Notification,ImportedAdmission
from .permissions import IsAdmin,IsAdminOrDoctor,IsAdminOrReceptionist,IsStaff,IsFinanceStaff,has_role
from .serializers import RegisterSerializer,UserSerializer,DepartmentSerializer,DoctorSerializer,PatientSerializer,AppointmentSerializer,AvailabilitySerializer,MedicalRecordSerializer,PrescriptionSerializer,BillSerializer,BedSerializer,NotificationSerializer
User=get_user_model()

def notify(user_id,title,message,sms=False,phone=''):
    """In-app notification, plus SMS when configured. SMS failure never blocks the request."""
    if not user_id: return
    Notification.objects.create(user_id=user_id,title=title,message=message)
    if sms:
        from .integrations import send_sms,sms_ready,ProviderUnavailable
        if sms_ready():
            try: send_sms(phone,f'MedCore: {message}')
            except ProviderUnavailable: pass

def tenant_scope(qs,user,field='hospital'):
    """Users assigned to a hospital see only that hospital's rows (plus legacy rows without one)."""
    if user.role=='SUPER_ADMIN' or not user.hospital_id: return qs
    return qs.filter(Q(**{f'{field}_id':user.hospital_id})|Q(**{f'{field}__isnull':True}))
class RegisterViewSet(viewsets.GenericViewSet):
    # Account provisioning is performed by an authenticated administrator.
    permission_classes=[IsAdmin]
    def create(self,request):
        serializer=RegisterSerializer(data=request.data); serializer.is_valid(raise_exception=True); user=serializer.save(); return Response(UserSerializer(user).data,status=201)
class CRUD(viewsets.ModelViewSet): permission_classes=[IsAuthenticated]
class DepartmentViewSet(CRUD):
    queryset=Department.objects.all(); serializer_class=DepartmentSerializer
    def get_permissions(self): return [IsAdmin()] if self.action in {'create','update','partial_update','destroy'} else [IsAuthenticated()]
class DoctorViewSet(CRUD):
    queryset=Doctor.objects.select_related('user','department').all(); serializer_class=DoctorSerializer
    def get_queryset(self):
        qs=super().get_queryset(); return qs.filter(user=self.request.user) if self.request.user.role=='DOCTOR' else qs
    def get_permissions(self): return [IsAdmin()] if self.action in {'create','update','partial_update','destroy'} else [IsAuthenticated()]
class PatientViewSet(CRUD):
    queryset=Patient.objects.select_related('user').all(); serializer_class=PatientSerializer
    http_method_names=['get','post','put','patch','head','options']
    def get_queryset(self):
        from .portal import visible_patients
        u=self.request.user
        # Reception registers and looks up any patient in its hospital.
        qs=tenant_scope(Patient.objects.all(),u) if u.role in {'RECEPTIONIST','ACCOUNTANT'} else visible_patients(u)
        qs=qs.select_related('user')
        q=self.request.query_params.get('q')
        if q: qs=qs.filter(Q(patient_id__icontains=q)|Q(full_name__icontains=q)|Q(phone__icontains=q))
        return qs
    def get_permissions(self):
        if self.action in {'create','update','partial_update'}: return [IsStaff()]
        return [IsAuthenticated()]
class AppointmentViewSet(CRUD):
    queryset=Appointment.objects.select_related('patient','doctor__user').all(); serializer_class=AppointmentSerializer
    def get_queryset(self):
        qs=super().get_queryset(); u=self.request.user
        if u.role=='DOCTOR': qs=qs.filter(doctor__user=u)
        elif u.role=='PATIENT': qs=qs.filter(patient__user=u)
        q=self.request.query_params.get('q'); date=self.request.query_params.get('date'); status=self.request.query_params.get('status')
        if q: qs=qs.filter(Q(patient__patient_id__icontains=q)|Q(patient__phone__icontains=q)|Q(patient__full_name__icontains=q)|Q(doctor__user__first_name__icontains=q)|Q(doctor__user__last_name__icontains=q))
        if date: qs=qs.filter(date=date)
        if status: qs=qs.filter(status=status)
        return qs
    def get_permissions(self):
        if self.action=='create': return [IsAuthenticated()]
        if self.action in {'update','partial_update'}: return [IsStaff()]
        if self.action=='destroy': return [IsAdmin()]
        return [IsAuthenticated()]
    def perform_create(self,serializer):
        # The partial unique constraints on (doctor,date,time) and (patient,date,time)
        # make the database the arbiter when two bookings race for one slot.
        try:
            with transaction.atomic(): appointment=serializer.save()
        except IntegrityError:
            raise ValidationError({'time':'This appointment slot was just booked.'}) from None
        if appointment.is_emergency:
            notify(appointment.doctor.user_id,'Emergency appointment',f'Emergency: {appointment.patient.full_name} on {appointment.date} at {appointment.time.strftime("%H:%M")}.',sms=True,phone=appointment.doctor.user.phone)
    def perform_update(self,serializer):
        before=serializer.instance.status
        try:
            with transaction.atomic(): appointment=serializer.save()
        except IntegrityError:
            raise ValidationError({'time':'This appointment slot was just booked.'}) from None
        if before!='Confirmed' and appointment.status=='Confirmed':
            notify(appointment.patient.user_id,'Appointment confirmed',f'Your appointment on {appointment.date} at {appointment.time.strftime("%H:%M")} is confirmed.',sms=True,phone=appointment.patient.phone)
class AvailabilityViewSet(CRUD):
    queryset=DoctorAvailability.objects.select_related('doctor__user').all(); serializer_class=AvailabilitySerializer
    def get_queryset(self):
        qs=super().get_queryset(); u=self.request.user
        if u.role=='DOCTOR': qs=qs.filter(doctor__user=u)
        doctor=self.request.query_params.get('doctor'); date=self.request.query_params.get('date')
        if doctor: qs=qs.filter(doctor_id=doctor)
        if date: qs=qs.filter(date=date)
        return qs
    def get_permissions(self): return [IsStaff()] if self.action in {'create','update','partial_update','destroy'} else [IsAuthenticated()]
    def perform_create(self,serializer):
        if self.request.user.role=='DOCTOR': serializer.save(doctor=Doctor.objects.get(user=self.request.user))
        else: serializer.save()
class MedicalRecordViewSet(CRUD):
    queryset=MedicalRecord.objects.select_related('patient','doctor__user').all(); serializer_class=MedicalRecordSerializer
    http_method_names=['get','post','head','options']
    def get_queryset(self):
        qs=super().get_queryset(); u=self.request.user
        if u.role=='DOCTOR': qs=qs.filter(doctor__user=u)
        elif u.role=='PATIENT': qs=qs.filter(patient__user=u)
        return qs
    def get_permissions(self):
        if self.action=='create': return [IsAdmin()]
        if self.action=='destroy': return [IsAdmin()]
        return [IsAuthenticated()]
    def perform_create(self,serializer):
        appointment=serializer.validated_data['appointment']
        try:
            with transaction.atomic():
                serializer.save(patient=appointment.patient,doctor=appointment.doctor,source='Clinical')
                if appointment.status=='Confirmed':
                    appointment.status='In Progress'
                    appointment.save(update_fields=['status'])
        except IntegrityError:
            raise ValidationError({'appointment':'This appointment already has a medical record.'}) from None
class PrescriptionViewSet(CRUD):
    queryset=Prescription.objects.select_related('record__patient','record__doctor__user').all(); serializer_class=PrescriptionSerializer
    def get_queryset(self):
        qs=super().get_queryset(); u=self.request.user
        if u.role=='DOCTOR': qs=qs.filter(record__doctor__user=u)
        elif u.role=='PATIENT': qs=qs.filter(record__patient__user=u)
        return qs
    def get_permissions(self):
        if self.action=='create': return [IsAdmin()]
        if self.action in {'update','partial_update'}: return [IsAdmin()]
        if self.action=='destroy': return [IsAdmin()]
        return [IsAuthenticated()]
    def perform_create(self,serializer):
        record=serializer.validated_data['record']
        if record.source!='Clinical':
            raise ValidationError({'record':'Choose a clinical medical record for an administrator-created prescription.'})
        serializer.save(source='Clinical')
class BillViewSet(CRUD):
    queryset=Bill.objects.select_related('patient','appointment__doctor__user').all(); serializer_class=BillSerializer
    def perform_update(self,serializer):
        from .models import PaymentCheckout
        if PaymentCheckout.objects.filter(bill=serializer.instance).exists():
            raise ValidationError('This bill has an online checkout. Reconcile it with the payment provider before changing the invoice.')
        serializer.save()
    def get_queryset(self):
        qs=super().get_queryset(); u=self.request.user
        if u.role=='DOCTOR': qs=qs.filter(appointment__doctor__user=u)
        elif u.role=='PATIENT': qs=qs.filter(patient__user=u)
        elif u.role not in {'ADMIN','ACCOUNTANT','RECEPTIONIST'}: return qs.none()
        return qs
    def get_permissions(self):
        if self.action=='destroy': return [IsAdmin()]
        return [IsFinanceStaff()] if self.action in {'create','update','partial_update'} else [IsAuthenticated()]
    def perform_create(self,serializer):
        bill=serializer.save()
        notify(bill.patient.user_id,'Invoice generated',f'Invoice #{bill.pk} for ₹{bill.total} is ready in your portal.')
class BedViewSet(CRUD):
    queryset=Bed.objects.select_related('patient').all(); serializer_class=BedSerializer
    def get_permissions(self): return [has_role('ADMIN','DOCTOR','RECEPTIONIST','NURSE')()] if self.action in {'create','update','partial_update','destroy'} else [IsAuthenticated()]
    def get_queryset(self):
        qs=super().get_queryset()
        # Bed occupancy is operational data and is never exposed to patients.
        if self.request.user.role=='PATIENT': return qs.none()
        status=self.request.query_params.get('status'); ward=self.request.query_params.get('ward')
        if status: qs=qs.filter(status=status)
        if ward: qs=qs.filter(ward__icontains=ward)
        return qs
class NotificationViewSet(CRUD):
    queryset=Notification.objects.all()
    serializer_class=NotificationSerializer
    def get_queryset(self): return Notification.objects.filter(user=self.request.user)
    def perform_create(self,serializer): serializer.save(user=self.request.user)
    def get_permissions(self): return [IsAuthenticated()]
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request): return Response(UserSerializer(request.user).data)

@api_view(['GET','POST'])
@permission_classes([IsAdminOrReceptionist])
def accounts(request):
    """Front-desk account creation; passwords are never returned."""
    if request.method=='GET':
        users=User.objects.order_by('username')
        if request.user.role=='RECEPTIONIST': users=users.filter(role__in={'DOCTOR','PATIENT'})
        return Response(UserSerializer(users,many=True).data)

    data=request.data
    role=data.get('role')
    staff_roles={'RECEPTIONIST','NURSE','LAB_TECH','PHARMACIST','ACCOUNTANT'}
    if role not in {'DOCTOR','PATIENT'}|staff_roles:
        return Response({'role':'Choose a valid hospital role.'},status=400)
    if request.user.role=='RECEPTIONIST' and role in staff_roles:
        raise PermissionDenied('Only an administrator can create staff accounts.')
    if not data.get('username') or not data.get('password'):
        return Response({'detail':'Username and password are required.'},status=400)
    if len(data['password'])<8:
        return Response({'password':'Password must be at least 8 characters.'},status=400)
    if role=='DOCTOR' and (not data.get('doctor_id') or not data.get('specialization')):
        return Response({'detail':'Doctor ID and specialization are required.'},status=400)
    if role=='PATIENT' and (not data.get('patient_id') or not data.get('phone')):
        return Response({'detail':'Patient ID and phone are required.'},status=400)
    department=None
    if role=='DOCTOR' and data.get('department'):
        try: department=Department.objects.get(pk=data['department'])
        except (Department.DoesNotExist,ValueError,TypeError):
            raise ValidationError({'department':'Choose an existing department.'})

    try:
        with transaction.atomic():
            user=User.objects.create_user(
                username=data['username'], password=data['password'], role=role,
                first_name=data.get('first_name',''), last_name=data.get('last_name',''),
                email=data.get('email',''), phone=data.get('phone',''), hospital_id=request.user.hospital_id
            )
            if role=='DOCTOR':
                Doctor.objects.create(user=user,doctor_id=data['doctor_id'],specialization=data['specialization'],department=department)
            if role=='PATIENT':
                Patient.objects.create(user=user,hospital_id=request.user.hospital_id,patient_id=data['patient_id'],full_name=data.get('full_name') or user.get_full_name() or user.username,gender=data.get('gender','Other'),phone=data['phone'],primary_concern=data.get('primary_concern',''))
    except IntegrityError:
        return Response({'detail':'That username, doctor ID or patient ID is already in use.'},status=400)
    return Response(UserSerializer(user).data,status=201)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def timeline(request):
    u=request.user
    if u.role=='PATIENT': patient=Patient.objects.filter(user=u).first()
    elif u.role=='DOCTOR' and request.query_params.get('patient_id'):
        patient=Patient.objects.filter(id=request.query_params['patient_id']).filter(Q(appointments__doctor__user=u)|Q(records__doctor__user=u)).distinct().first()
    elif u.role in {'ADMIN','NURSE'} and request.query_params.get('patient_id'):
        from .portal import visible_patients
        patient=visible_patients(u).filter(id=request.query_params['patient_id']).first()
    else: patient=None
    if not patient: raise PermissionDenied('You do not have access to this patient timeline.')
    qs=MedicalRecord.objects.filter(patient=patient).select_related('doctor__user').order_by('-created_at')
    return Response([{'date':r.created_at.strftime('%Y-%m-%d'),'diagnosis':r.diagnosis,'symptoms':r.symptoms,'treatment':r.treatment,'doctor':(r.doctor.user.get_full_name() or r.doctor.user.username) if r.doctor_id else '', 'source':r.source} for r in qs])

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def discharges(request):
    qs=Patient.objects.filter(admission_status='Discharged',discharged_on__isnull=False)
    if request.user.role=='DOCTOR':
        qs=qs.filter(Q(appointments__doctor__user=request.user)|Q(records__doctor__user=request.user)).distinct()
    elif request.user.role=='PATIENT':
        qs=qs.filter(user=request.user)
    return Response([{
        'id':patient.id,
        'date':patient.discharged_on.isoformat(),
        'patient_name':patient.full_name,
        'doctor_name':((appointment.doctor.user.get_full_name() or appointment.doctor.user.username) if (appointment:=patient.appointments.select_related('doctor__user').order_by('-date','-time').first()) else ''),
        'status':'Discharged'
    } for patient in qs.order_by('-discharged_on')])
@api_view(['GET'])
@permission_classes([IsAdminOrReceptionist])
def imported_admissions(request):
    qs=ImportedAdmission.objects.all()
    q=request.query_params.get('q','').strip()
    if q:
        qs=qs.filter(Q(patient_name__icontains=q)|Q(medical_condition__icontains=q)|Q(doctor_name__icontains=q)|Q(hospital__icontains=q))
    try:
        page=max(1,int(request.query_params.get('page',1)))
    except ValueError:
        page=1
    page_size=50
    total=qs.count()
    rows=list(qs.values()[((page-1)*page_size):(page*page_size)])
    return Response({'count':total,'page':page,'page_size':page_size,'q':q,'results':rows})


@api_view(['GET'])
@permission_classes([IsAdminOrReceptionist])
def doctor_directory(request):
    """Page through registered doctors and doctors referenced by imported admissions."""
    q=request.query_params.get('q','').strip()
    registered=Doctor.objects.select_related('user','department').order_by('id')
    historical=ImportedAdmission.objects.exclude(doctor_name='')
    if q:
        registered=registered.filter(Q(doctor_id__icontains=q)|Q(user__first_name__icontains=q)|Q(user__last_name__icontains=q)|Q(specialization__icontains=q)|Q(department__name__icontains=q))
        historical=historical.filter(doctor_name__icontains=q)
    historical=historical.values('doctor_name').annotate(patient_count=Count('id')).order_by('doctor_name')
    try:
        page=max(1,int(request.query_params.get('page',1)))
    except (TypeError,ValueError):
        page=1
    page_size=50
    offset=(page-1)*page_size
    registered_count=registered.count()
    historical_count=historical.count()
    registered_rows=list(registered[offset:min(offset+page_size,registered_count)]) if offset<registered_count else []
    results=[{
        'key':f'registered-doctor-{doctor.pk}','id':doctor.pk,'doctor_id':doctor.doctor_id,
        'name':doctor.user.get_full_name() or doctor.user.username,
        'specialization':doctor.specialization,
        'department_name':doctor.department.name if doctor.department_id else doctor.specialization,
        'experience':doctor.experience,'available':doctor.available,
        'patient_count':doctor.assigned_patients.filter(directory_hidden=False).count()+doctor.assigned_imported_patients.filter(directory_hidden=False).count(),'registered':True,
    } for doctor in registered_rows]
    remaining=page_size-len(results)
    if remaining:
        historical_offset=max(0,offset-registered_count)
        for directory_index,row in enumerate(historical[historical_offset:historical_offset+remaining],start=registered_count+historical_offset+1):
            results.append({
                'key':f"historical-doctor-{row['doctor_name']}",'id':None,
                'doctor_id':None,'name':row['doctor_name'],
                'specialization':None,'department_name':None,
                'experience':None,'available':None,
                'patient_count':row['patient_count'],'registered':False,
            })
    return Response({'count':registered_count+historical_count,'page':page,'page_size':page_size,
                     'q':q,'results':results})


@api_view(['GET'])
@permission_classes([IsStaff])
def patient_directory(request):
    """Page through registered profiles and imported visits in one list."""
    q=request.query_params.get('q','').strip()
    live=Patient.objects.select_related('user','hospital','primary_doctor__user').order_by('-created_at','-id')
    visits=ImportedAdmission.objects.all()
    # Display IDs follow the visible directory order, including across pages.
    live=live.filter(directory_hidden=False)
    visits=visits.filter(directory_hidden=False)
    profile_numbers={pk:index for index,pk in enumerate(live.values_list('pk',flat=True),start=1)}
    directory_numbers={pk:index for index,pk in enumerate(visits.values_list('pk',flat=True),start=len(profile_numbers)+1)}
    if request.user.role=='DOCTOR':
        live=live.filter(primary_doctor__user=request.user)
        visits=visits.filter(primary_doctor__user=request.user)
    assigned_names={d.pk:d.user.get_full_name() or d.user.username for d in Doctor.objects.select_related('user')}
    if q:
        matching_profiles=[pk for pk,index in profile_numbers.items()
                           if q.lower() in f'PROFILE-{index}'.lower() or q.lower() in f'PAT-{index:02d}'.lower()]
        live=live.filter(Q(pk__in=matching_profiles)|Q(patient_id__icontains=q)|Q(full_name__icontains=q)|Q(phone__icontains=q)|Q(email__icontains=q)|Q(primary_concern__icontains=q)|Q(allergies__icontains=q))
        matching_ids=[pk for pk,index in directory_numbers.items()
                      if q.lower() in f'PROFILE-{index}'.lower()
                      or q.lower() in f'PAT-{index:02d}'.lower()]
        visits=visits.filter(Q(pk__in=matching_ids)|Q(patient_name__icontains=q)|Q(medical_condition__icontains=q)|Q(doctor_name__icontains=q)|Q(hospital__icontains=q)|Q(medication__icontains=q)|Q(insurance_provider__icontains=q))
    try:
        page=max(1,int(request.query_params.get('page',1)))
    except (TypeError,ValueError):
        page=1
    page_size=50
    offset=(page-1)*page_size
    live_count=live.count()
    visit_count=visits.count()
    live_rows=list(live[offset:min(offset+page_size,live_count)]) if offset<live_count else []
    results=[]
    today=timezone.localdate()
    for patient,details in zip(live_rows,PatientSerializer(live_rows,many=True).data):
        dob=patient.dob
        age=(today.year-dob.year-((today.month,today.day)<(dob.month,dob.day))) if dob else None
        bed=patient.bed_assignments.order_by('-admitted_on','-id').first()
        medicines=list(Prescription.objects.filter(record__patient=patient).values_list('medicine',flat=True).distinct())
        billed=patient.bills.exclude(status='Cancelled').aggregate(amount=Sum('total'))['amount']
        from .models import LabOrder
        approved_results=LabOrder.objects.filter(record__patient=patient,status='APPROVED').select_related('test')
        test_results='; '.join(f'{order.test.name}: {order.result_value or order.result_notes}' for order in approved_results)
        results.append({
            'key':f'profile-{patient.pk}','record_type':'Profile','patient_pk':patient.pk,
            'record_id':f'PROFILE-{profile_numbers[patient.pk]}','patient_id':f'PAT-{profile_numbers[patient.pk]:02d}',
            'patient_name':patient.full_name,'date_of_birth':dob,'age':age,
            'gender':patient.gender,'phone':patient.phone or (patient.user.phone if patient.user else None),
            'email':patient.email or (patient.user.email if patient.user else None),
            'blood_type':patient.blood_group or None,'address':patient.address or None,
            'emergency_contact':patient.emergency_contact or None,
            'emergency_priority':patient.emergency_priority,'allergies':patient.allergies or None,
            'medical_condition':patient.primary_concern or None,
            'registered_on':patient.created_at.date(),'admission_date':bed.admitted_on if bed else None,
            'appointment_date':details['appointment_date'],'doctor_name':details['assigned_doctor'] or None,
            'hospital':patient.hospital.name if patient.hospital else None,'admission_status':patient.admission_status,'admission_type':None,
            'room_number':f'{bed.ward} / {bed.bed_number}' if bed else None,'discharge_date':patient.discharged_on,
            'medication':', '.join(medicines) or None,'test_results':test_results or None,'insurance_provider':None,'billing_amount':billed,
        })
    remaining=page_size-len(results)
    if remaining:
        visit_offset=max(0,offset-live_count)
        for visit_index,row in enumerate(visits.values()[visit_offset:visit_offset+remaining],start=live_count+visit_offset+1):
            results.append({
                'key':f"imported-visit-{row['source_row']}",'record_type':'Visit','patient_pk':None,
                'record_id':f"PROFILE-{directory_numbers[row['id']]}",
                'patient_id':f"PAT-{directory_numbers[row['id']]:02d}",
                'patient_name':row['patient_name'],'date_of_birth':None,'age':row['age'],
                'gender':row['gender'],'phone':None,'email':None,'blood_type':row['blood_type'],
                'address':None,'emergency_contact':None,'emergency_priority':None,'allergies':None,
                'medical_condition':row['medical_condition'],'registered_on':None,
                'admission_date':row['admission_date'],'appointment_date':None,
                'doctor_name':assigned_names.get(row['primary_doctor_id'],row['doctor_name']),'hospital':row['hospital'],
                'admission_status':None,'admission_type':row['admission_type'],
                'room_number':row['room_number'],
                'discharge_date':row['discharge_date'],'medication':row['medication'],
                'test_results':row['test_results'],'insurance_provider':row['insurance_provider'],
                'billing_amount':row['billing_amount'],
            })
    return Response({'count':live_count+visit_count,'page':page,'page_size':page_size,
                     'q':q,'results':results})


def historical_summary():
    qs=ImportedAdmission.objects.all()
    return {
        'historical_admissions':qs.count(),
        'imported_doctor_names':qs.exclude(doctor_name='').order_by().values('doctor_name').distinct().count(),
        'imported_billing_total':str(qs.aggregate(total=Sum('billing_amount'))['total'] or 0),
        'recent_historical_admissions':list(qs.values('source_row','patient_name','medical_condition','admission_date','doctor_name','hospital')[:5]),
    }

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    from .operations import extra_dashboard,admin_extras,doctor_extras
    u=request.user; today=timezone.localdate()
    extra=extra_dashboard(u)
    if extra: return Response(extra)
    if u.role=='ADMIN':
        return Response({'role':'ADMIN',**historical_summary(),**admin_extras(),'patients':Patient.objects.count(),'doctors':Doctor.objects.count(),'departments':Department.objects.count(),'appointments':Appointment.objects.count(),'pending_appointments':Appointment.objects.filter(status='Pending').count(),'confirmed_appointments':Appointment.objects.filter(status='Confirmed').count(),'completed_appointments':Appointment.objects.filter(status='Completed').count(),'in_progress_appointments':Appointment.objects.filter(status='In Progress').count(),'no_show_appointments':Appointment.objects.filter(status='No Show').count(),'cancelled_appointments':Appointment.objects.filter(status='Cancelled').count(),'emergency_patients':Patient.objects.filter(emergency_priority=True).count(),'revenue':float(Bill.objects.filter(status='Paid').aggregate(x=Sum('total'))['x'] or 0),'pending_bills':float(Bill.objects.filter(status='Pending').aggregate(x=Sum('total'))['x'] or 0),'beds_total':Bed.objects.count(),'beds_available':Bed.objects.filter(status='Available').count(),'department_workload':list(Department.objects.annotate(workload=Count('doctors__appointments')).values('name','workload')),'recent_appointments':AppointmentSerializer(Appointment.objects.select_related('patient','doctor__user')[:8],many=True).data})
    if u.role=='DOCTOR':
        d=Doctor.objects.filter(user=u).first()
        if not d: raise PermissionDenied('This doctor account does not have a doctor profile.')
        qs=Appointment.objects.filter(doctor=d); pcount=Patient.objects.filter(primary_doctor=d,directory_hidden=False).count()+ImportedAdmission.objects.filter(primary_doctor=d,directory_hidden=False).count()
        return Response({'role':'DOCTOR',**doctor_extras(d),'doctor':{'name':u.get_full_name() or u.username,'specialization':d.specialization,'department_name':d.department.name if d.department else None},'patients':pcount,'appointments':qs.count(),'pending_appointments':qs.filter(status='Pending').count(),'completed_appointments':qs.filter(status='Completed').count(),'in_progress_appointments':qs.filter(status='In Progress').count(),'upcoming_appointments':qs.filter(date__gte=today,status__in=['Pending','Confirmed']).count(),'available_slots':DoctorAvailability.objects.filter(doctor=d,date__gte=today,is_available=True).count(),'emergency_patients':Patient.objects.filter(appointments__doctor=d,emergency_priority=True).distinct().count(),'recent_appointments':AppointmentSerializer(qs.select_related('patient','doctor__user').order_by('-date','-time')[:8],many=True).data})
    if u.role=='RECEPTIONIST':
        return Response({'role':'RECEPTIONIST',**historical_summary(),'patients':Patient.objects.count(),'doctors':Doctor.objects.filter(available=True).count(),'appointments_today':Appointment.objects.filter(date=today).count(),'pending_appointments':Appointment.objects.filter(status='Pending').count(),'emergency_patients':Patient.objects.filter(emergency_priority=True).count(),'beds_available':Bed.objects.filter(status='Available').count(),'pending_bills':float(Bill.objects.filter(status='Pending').aggregate(x=Sum('total'))['x'] or 0),'recent_appointments':AppointmentSerializer(Appointment.objects.select_related('patient','doctor__user')[:8],many=True).data})
    p=Patient.objects.filter(user=u).first(); qs=Appointment.objects.filter(patient=p) if p else Appointment.objects.none(); bills=Bill.objects.filter(patient=p) if p else Bill.objects.none()
    return Response({'role':'PATIENT','patient':{'full_name':p.full_name,'patient_id':p.patient_id,'blood_group':p.blood_group,'emergency_priority':p.emergency_priority,'primary_concern':p.primary_concern} if p else {},'appointments':qs.count(),'upcoming_appointments':qs.filter(date__gte=today,status__in=['Pending','Confirmed']).count(),'medical_records':MedicalRecord.objects.filter(patient=p).count() if p else 0,'prescriptions':Prescription.objects.filter(record__patient=p).count() if p else 0,'paid_total':float(bills.filter(status='Paid').aggregate(x=Sum('total'))['x'] or 0),'pending_total':float(bills.filter(status='Pending').aggregate(x=Sum('total'))['x'] or 0),'recent_appointments':AppointmentSerializer(qs.select_related('patient','doctor__user')[:8],many=True).data})
