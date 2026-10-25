"""Patient-facing workflows. No public endpoint exposes care records."""
import logging
import uuid
from datetime import datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.throttling import AnonRateThrottle
from .models import Patient, Doctor, Department, Appointment, DoctorAvailability, PatientDocument, Notification, LabTest, LabOrder, MedicalRecord
from .serializers import AppointmentSerializer

User=get_user_model()

def visible_patients(user):
    qs=Patient.objects.all()
    if user.role=='SUPER_ADMIN': return qs
    if user.role=='PATIENT': return qs.filter(user=user)
    # Tenant isolation: hospital-assigned staff never see another hospital's patients.
    if user.hospital_id: qs=qs.filter(Q(hospital_id=user.hospital_id)|Q(hospital__isnull=True))
    if user.role in {'ADMIN','NURSE'}: return qs
    if user.role=='DOCTOR':
        return qs.filter(Q(appointments__doctor__user=user)|Q(records__doctor__user=user)).distinct()
    if user.role=='LAB_TECH': return qs.filter(records__lab_orders__isnull=False).distinct()
    if user.role=='PHARMACIST': return qs.filter(records__prescriptions__isnull=False).distinct()
    if user.role=='ACCOUNTANT': return qs.filter(bills__isnull=False).distinct()
    return qs.none()

class RecoveryThrottle(AnonRateThrottle):
    rate='5/hour'

class SignupSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True,min_length=8,max_length=128,trim_whitespace=False)
    first_name=serializers.CharField(max_length=150)
    email=serializers.EmailField()
    phone=serializers.CharField(max_length=20)

    class Meta:
        model=User
        fields=['username','first_name','last_name','email','phone','password']

    def validate(self,data):
        if len((data['first_name']+' '+data.get('last_name','')).strip())>150:
            raise serializers.ValidationError({'first_name':'Your full name must be 150 characters or fewer.'})
        if self.initial_data.get('role','PATIENT')!='PATIENT':
            raise serializers.ValidationError({'role':'Contact hospital staff to create a staff account.'})
        try:
            validate_password(data['password'],User(**{k:v for k,v in data.items() if k!='password'}))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password':exc.messages})
        return data

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RecoveryThrottle])
def signup(request):
    serializer=SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        with transaction.atomic():
            user=User.objects.create_user(**serializer.validated_data,role='PATIENT')
            Patient.objects.create(user=user,patient_id=f'PAT-{uuid.uuid4().hex[:20]}',
                full_name=user.get_full_name(),phone=user.phone,email=user.email,gender='Other')
    except IntegrityError:
        raise ValidationError({'username':'That username is already in use. Please choose another.'})
    return Response({'detail':'Account created. You can now sign in.'},status=201)

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RecoveryThrottle])
def password_request(request):
    email=serializers.EmailField().run_validation(request.data.get('email'))
    for user in User.objects.filter(email__iexact=email,is_active=True):
        if not user.has_usable_password(): continue
        uid=urlsafe_base64_encode(force_bytes(user.pk))
        token=default_token_generator.make_token(user)
        url=f'{settings.FRONTEND_URL}/?reset_uid={uid}&reset_token={token}'
        try:
            send_mail('Reset your MedCore password',f'Use this link to choose a new password:\n{url}\n\nThis link expires in one hour. If you did not request this, ignore this message.',settings.DEFAULT_FROM_EMAIL,[user.email])
        except Exception:
            logging.getLogger(__name__).error('Password recovery email delivery failed.')
    return Response({'detail':'If an active account matches this email, a reset link will be sent. Contact reception if you need help.'})

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RecoveryThrottle])
def password_confirm(request):
    try:
        uid=urlsafe_base64_decode(request.data.get('uid','')).decode()
        user=User.objects.get(pk=uid,is_active=True)
    except (ValueError,TypeError,OverflowError,UnicodeDecodeError,User.DoesNotExist):
        raise ValidationError('This reset link is invalid or expired.')
    if not default_token_generator.check_token(user,request.data.get('token','')):
        raise ValidationError('This reset link is invalid or expired.')
    password=serializers.CharField(min_length=8,max_length=128,trim_whitespace=False).run_validation(request.data.get('password'))
    try: validate_password(password,user)
    except DjangoValidationError as exc: raise ValidationError({'password':exc.messages})
    user.set_password(password); user.save(update_fields=['password'])
    return Response({'detail':'Password updated. You can now sign in.'})

@api_view(['GET'])
@permission_classes([AllowAny])
def public_directory(request):
    doctors=Doctor.objects.filter(user__is_active=True,deleted_at__isnull=True).select_related('user','department')
    return Response({'departments':list(Department.objects.values('id','name','description')),
        'doctors':[{'id':d.pk,'name':d.user.get_full_name() or d.user.username,'specialization':d.specialization,
          'department':d.department.name if d.department else None,'qualifications':d.qualifications,
          'languages':d.languages,'experience':d.experience,'consultation_fee':str(d.consultation_fee),
          'bio':d.bio,'available':d.available} for d in doctors]})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reschedule(request,pk):
    with transaction.atomic():
        qs=Appointment.objects.select_for_update().filter(patient__in=visible_patients(request.user))
        if request.user.role=='RECEPTIONIST': qs=Appointment.objects.select_for_update()
        if request.user.role=='DOCTOR': raise PermissionDenied('Ask reception to reschedule this appointment.')
        appointment=get_object_or_404(qs,pk=pk)
        if appointment.status not in {'Pending','Confirmed'}:
            raise ValidationError('Only pending or confirmed appointments can be rescheduled.')
        day=serializers.DateField().run_validation(request.data.get('date'))
        time=serializers.TimeField().run_validation(request.data.get('time'))
        if timezone.make_aware(datetime.combine(day,time))<=timezone.now():
            raise ValidationError('Choose a future date and time.')
        if not appointment.doctor.available: raise ValidationError('This doctor is currently unavailable.')
        slots=DoctorAvailability.objects.filter(doctor=appointment.doctor,date=day)
        if not slots.filter(is_available=True,start_time__lte=time,end_time__gt=time).exists():
            raise ValidationError('Choose a time within the doctor\'s published availability.')
        conflict=Appointment.objects.filter(date=day,time=time).exclude(status__in=['Cancelled','No Show']).exclude(pk=pk)
        if conflict.filter(Q(doctor=appointment.doctor)|Q(patient=appointment.patient)).exists():
            raise ValidationError('The doctor or patient already has an appointment at that time.')
        appointment.date=day; appointment.time=time; appointment.status='Pending'
        try:
            with transaction.atomic(): appointment.save(update_fields=['date','time','status'])
        except IntegrityError: raise ValidationError('This slot was just booked. Choose another time.')
        for user_id in {appointment.patient.user_id,appointment.doctor.user_id}-{None}:
            Notification.objects.create(user_id=user_id,title='Appointment rescheduled',message=f'Appointment #{pk}: {day} at {time.strftime("%H:%M")}. Awaiting confirmation.')
    return Response(AppointmentSerializer(appointment).data)

class DocumentSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    source=serializers.SerializerMethodField()
    class Meta:
        model=PatientDocument
        fields=['id','patient','patient_name','title','category','filename','source','created_at']
        read_only_fields=['filename','created_at']
    def get_source(self,obj):
        return 'Patient submitted' if obj.uploaded_by.role=='PATIENT' else 'Staff uploaded'

class DocumentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes=[IsAuthenticated]
    serializer_class=DocumentSerializer
    def get_queryset(self):
        return PatientDocument.objects.filter(patient__in=visible_patients(self.request.user)).select_related('patient','uploaded_by')
    def create(self,request):
        patient=get_object_or_404(visible_patients(request.user),pk=request.data.get('patient'))
        file=request.FILES.get('file')
        if not file or file.size>5*1024*1024: raise ValidationError('Choose a PDF, PNG or JPEG file up to 5 MB.')
        content=file.read()
        content_type=('application/pdf' if content.startswith(b'%PDF-') else 'image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else None)
        if not content_type: raise ValidationError('Only PDF, PNG and JPEG documents are accepted.')
        from .scanning import scan_bytes,ScanUnavailable
        try: threat=scan_bytes(content)
        except ScanUnavailable: raise ValidationError('Uploads are paused because the virus scanner is unavailable. Please try again later.')
        if threat:
            logging.getLogger(__name__).warning('Rejected an infected upload (%s).',threat)
            raise ValidationError('This file was rejected by the virus scanner.')
        title=serializers.CharField(max_length=150).run_validation(request.data.get('title'))
        category=serializers.ChoiceField(choices=['Report','Prescription','Visit summary','Other']).run_validation(request.data.get('category'))
        extension={'application/pdf':'pdf','image/png':'png','image/jpeg':'jpg'}[content_type]
        document=PatientDocument.objects.create(patient=patient,title=title,category=category,content=content,content_type=content_type,filename=f'document.{extension}',uploaded_by=request.user)
        return Response(self.get_serializer(document).data,status=201)
    @action(detail=True,methods=['get'])
    def download(self,request,pk=None):
        document=self.get_object()
        response=HttpResponse(bytes(document.content),content_type=document.content_type)
        response['Content-Disposition']=f'attachment; filename="medcore-{document.pk}-{document.filename}"'
        response['X-Content-Type-Options']='nosniff'
        response['Cache-Control']='no-store'
        return response

class LabTestSerializer(serializers.ModelSerializer):
    class Meta: model=LabTest; fields=['id','name','unit','reference_range','price','active']

class LabOrderSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='record.patient.full_name',read_only=True)
    test_name=serializers.CharField(source='test.name',read_only=True)
    unit=serializers.CharField(source='test.unit',read_only=True)
    reference_range=serializers.CharField(source='test.reference_range',read_only=True)
    out_of_range=serializers.SerializerMethodField()
    class Meta:
        model=LabOrder
        fields=['id','record','test','patient_name','test_name','unit','reference_range','status','result_value','result_notes','out_of_range','created_at']
        read_only_fields=['status','created_at','result_value','result_notes']
    def get_out_of_range(self,obj):
        return out_of_range(obj.result_value,obj.test.reference_range)

def out_of_range(value,reference):
    """True/False when a numeric result can be compared with a 'low-high' range, else None."""
    import re
    match=re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)\s*',reference or '')
    number=re.match(r'\s*(-?\d+(?:\.\d+)?)',value or '')
    if not match or not number: return None
    low,high=float(match[1]),float(match[2]); result=float(number[1])
    return not (low<=result<=high)

class LabTestViewSet(viewsets.ModelViewSet):
    serializer_class=LabTestSerializer
    permission_classes=[IsAuthenticated]
    queryset=LabTest.objects.order_by('name')
    http_method_names=['get','post','patch','head','options']
    def get_permissions(self):
        # Only administrators manage the test catalogue.
        if self.request.method not in {'GET','HEAD','OPTIONS'}:
            from .permissions import IsAdmin
            return [IsAdmin()]
        return super().get_permissions()

class LabOrderViewSet(viewsets.ModelViewSet):
    serializer_class=LabOrderSerializer
    permission_classes=[IsAuthenticated]
    http_method_names=['get','post','head','options']
    def get_queryset(self):
        qs=LabOrder.objects.filter(record__patient__in=visible_patients(self.request.user)).select_related('record__patient','test')
        if self.request.user.role=='PATIENT': qs=qs.filter(status='APPROVED')
        return qs.order_by('-created_at')
    def perform_create(self,serializer):
        if self.request.user.role not in {'ADMIN','DOCTOR'}: raise PermissionDenied('Only clinical staff may order tests.')
        record=serializer.validated_data['record']
        if not visible_patients(self.request.user).filter(pk=record.patient_id).exists(): raise PermissionDenied()
        if not serializer.validated_data['test'].active: raise ValidationError('This test is inactive.')
        serializer.save(ordered_by=self.request.user)
    @action(detail=True,methods=['post'])
    def progress(self,request,pk=None):
        role=request.user.role
        if role not in {'ADMIN','DOCTOR','LAB_TECH'}: raise PermissionDenied()
        with transaction.atomic():
            order=get_object_or_404(self.get_queryset().select_for_update(),pk=pk)
            status=request.data.get('status')
            transitions={'ORDERED':{'SAMPLE_COLLECTED','CANCELLED'},'SAMPLE_COLLECTED':{'PROCESSING','CANCELLED'},'PROCESSING':{'REVIEW'},'REVIEW':{'APPROVED','PROCESSING'}}
            if status not in transitions.get(order.status,set()): raise ValidationError('Invalid lab status transition.')
            if role=='DOCTOR' and status!='APPROVED': raise PermissionDenied('The laboratory records sample and processing updates.')
            if role=='LAB_TECH' and status=='APPROVED' and order.result_entered_by_id==request.user.id:
                raise PermissionDenied('A different senior technician or doctor must approve this result.')
            if status=='REVIEW':
                order.result_value=serializers.CharField(max_length=120).run_validation(request.data.get('result_value'))
                order.result_notes=serializers.CharField(allow_blank=True,max_length=10000).run_validation(request.data.get('result_notes',''))
                order.result_entered_by=request.user
            if status=='APPROVED': order.approved_by=request.user
            order.status=status; order.save()
            if status=='APPROVED':
                for user_id in {order.record.patient.user_id,order.ordered_by_id}-{None}:
                    Notification.objects.create(user_id=user_id,title='Lab report approved',message=f'{order.test.name} result for {order.record.patient.full_name} is now available.')
        return Response(self.get_serializer(order).data)
