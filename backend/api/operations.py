"""Hospital operations for the roles beyond admin/doctor/receptionist/patient:
super admin (hospitals), pharmacist (inventory, dispensing), nurse (vitals),
accountant (invoice items, insurance claims, revenue), plus audit, search,
token logout and OTP verification."""
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from decimal import Decimal
from html import escape
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Sum, Count, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes, action, authentication_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .models import (Hospital, Patient, Doctor, Appointment, Bill, BillItem, Payment, Medicine, MedicineBatch,
                     Prescription, PrescriptionItem, InsuranceClaim, VitalsEntry, AuditLog, Notification, LabOrder,
                     VerificationCode, Department, Bed)
from .permissions import IsSuperAdmin, IsPharmacyStaff, IsFinanceStaff, IsNursingStaff, has_role
from .portal import visible_patients
from .integrations import send_sms, sms_ready, ProviderUnavailable, provider_request

# ---------------------------------------------------------------- throttling

class AuthThrottle(SimpleRateThrottle):
    """100 requests per 15 minutes per IP on authentication endpoints."""
    scope='auth'
    rate='100/15min'
    def parse_rate(self,rate): return (100,15*60)
    def get_cache_key(self,request,view): return self.cache_format%{'scope':self.scope,'ident':self.get_ident(request)}

REFRESH_COOKIE='medcore_refresh'

def _set_refresh_cookie(response):
    """Move the refresh token out of the JSON body into an httpOnly cookie that scripts cannot read."""
    token=response.data.pop('refresh',None)
    if token:
        response.set_cookie(REFRESH_COOKIE,token,max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
            httponly=True,secure=settings.REFRESH_COOKIE_SECURE,samesite='Strict',path='/api/')
    return response

class ThrottledLoginView(TokenObtainPairView):
    throttle_classes=[AuthThrottle]
    def post(self,request,*args,**kwargs):
        response=super().post(request,*args,**kwargs)
        return _set_refresh_cookie(response) if response.status_code==200 else response

class ThrottledRefreshView(TokenRefreshView):
    throttle_classes=[AuthThrottle]
    def post(self,request,*args,**kwargs):
        if not request.data.get('refresh') and request.COOKIES.get(REFRESH_COOKIE):
            request._full_data={'refresh':request.COOKIES[REFRESH_COOKIE]}
        response=super().post(request,*args,**kwargs)
        return _set_refresh_cookie(response) if response.status_code==200 else response

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def logout(request):
    """Blacklist the refresh token so it cannot be used again, and clear the cookie."""
    try: RefreshToken(request.data.get('refresh') or request.COOKIES.get(REFRESH_COOKIE,'')).blacklist()
    except TokenError: pass
    response=Response(status=205)
    response.delete_cookie(REFRESH_COOKIE,path='/api/',samesite='Strict')
    return response

# ---------------------------------------------------------------- OTP

def _hash_code(code): return hashlib.sha256(f'{settings.SECRET_KEY}:{code}'.encode()).hexdigest()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AuthThrottle])
def send_verification(request):
    channel=request.data.get('channel','email')
    user=request.user
    if channel not in {'email','phone'}: raise ValidationError({'channel':'Choose email or phone.'})
    if channel=='email' and not user.email: raise ValidationError('Add an email address to your account first.')
    if channel=='phone' and not user.phone: raise ValidationError('Add a phone number to your account first.')
    code=f'{secrets.randbelow(10**6):06d}'
    VerificationCode.objects.filter(user=user,channel=channel,used=False).update(used=True)
    VerificationCode.objects.create(user=user,channel=channel,code_hash=_hash_code(code),expires_at=timezone.now()+timedelta(minutes=10))
    message=f'Your MedCore verification code is {code}. It expires in 10 minutes.'
    try:
        if channel=='email': send_mail('Your MedCore verification code',message,settings.DEFAULT_FROM_EMAIL,[user.email])
        else: send_sms(user.phone,message)
    except ProviderUnavailable:
        raise ValidationError('SMS delivery is not configured. Verify by email instead.')
    return Response({'detail':f'A 6-digit code was sent to your {channel}.'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AuthThrottle])
def confirm_verification(request):
    channel=request.data.get('channel','email'); code=str(request.data.get('code','')).strip()
    entry=VerificationCode.objects.filter(user=request.user,channel=channel,used=False,expires_at__gt=timezone.now()).order_by('-created_at').first()
    if not entry: raise ValidationError('This code has expired. Request a new one.')
    entry.attempts+=1
    if entry.attempts>5: entry.used=True
    ok=entry.attempts<=5 and hmac.compare_digest(entry.code_hash,_hash_code(code))
    if ok: entry.used=True
    entry.save(update_fields=['attempts','used'])
    if not ok: raise ValidationError('That code is not correct.')
    field='email_verified' if channel=='email' else 'phone_verified'
    setattr(request.user,field,True); request.user.save(update_fields=[field])
    return Response({'detail':'Verified.',field:True})

# ---------------------------------------------------------------- hospitals (super admin)

class HospitalSerializer(serializers.ModelSerializer):
    user_count=serializers.IntegerField(source='users.count',read_only=True)
    patient_count=serializers.IntegerField(source='patients.count',read_only=True)
    class Meta: model=Hospital; fields=['id','name','code','address','phone','email','verified','created_at','user_count','patient_count']; read_only_fields=['verified','created_at']

class HospitalViewSet(viewsets.ModelViewSet):
    serializer_class=HospitalSerializer
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        u=self.request.user
        if u.role=='SUPER_ADMIN': return Hospital.objects.order_by('name')
        return Hospital.objects.filter(pk=u.hospital_id)
    def get_permissions(self):
        return [IsSuperAdmin()] if self.action not in {'list','retrieve'} else [IsAuthenticated()]
    @action(detail=True,methods=['post'])
    def verify(self,request,pk=None):
        hospital=self.get_object(); hospital.verified=True; hospital.save(update_fields=['verified'])
        return Response(self.get_serializer(hospital).data)

# ---------------------------------------------------------------- pharmacy

def usable_batches(medicine):
    return medicine.batches.filter(quarantined=False,expiry_date__gt=timezone.localdate(),quantity__gt=0)

class MedicineBatchSerializer(serializers.ModelSerializer):
    medicine_name=serializers.CharField(source='medicine.name',read_only=True)
    expired=serializers.SerializerMethodField()
    class Meta: model=MedicineBatch; fields=['id','medicine','medicine_name','batch_number','manufacturing_date','expiry_date','quantity','unit_cost','mrp','quarantined','expired']
    def get_expired(self,obj): return obj.expiry_date<=timezone.localdate()
    def validate(self,attrs):
        made=attrs.get('manufacturing_date',getattr(self.instance,'manufacturing_date',None))
        expires=attrs.get('expiry_date',getattr(self.instance,'expiry_date',None))
        if made and expires and expires<=made: raise serializers.ValidationError({'expiry_date':'Expiry must be after manufacturing date.'})
        return attrs

class MedicineSerializer(serializers.ModelSerializer):
    stock=serializers.SerializerMethodField(); low_stock=serializers.SerializerMethodField(); next_expiry=serializers.SerializerMethodField()
    class Meta: model=Medicine; fields=['id','name','form','manufacturer','reorder_level','active','stock','low_stock','next_expiry']
    def get_stock(self,obj): return usable_batches(obj).aggregate(n=Sum('quantity'))['n'] or 0
    def get_low_stock(self,obj): return self.get_stock(obj)<obj.reorder_level
    def get_next_expiry(self,obj):
        batch=usable_batches(obj).order_by('expiry_date').first()
        return batch.expiry_date if batch else None

class MedicineViewSet(viewsets.ModelViewSet):
    serializer_class=MedicineSerializer
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        qs=Medicine.objects.order_by('name')
        q=self.request.query_params.get('search','').strip()
        return qs.filter(Q(name__icontains=q)|Q(manufacturer__icontains=q)) if q else qs
    def get_permissions(self):
        if self.action in {'list','retrieve'}: return [has_role('ADMIN','PHARMACIST','DOCTOR')()]
        return [IsPharmacyStaff()]
    @action(detail=False,methods=['get'],url_path='alerts')
    def alerts(self,request):
        return Response(pharmacy_alerts())

def pharmacy_alerts(days=30):
    today=timezone.localdate()
    low=[m for m in MedicineSerializer(Medicine.objects.filter(active=True),many=True).data if m['low_stock']]
    expiring=MedicineBatch.objects.filter(quarantined=False,quantity__gt=0,expiry_date__lte=today+timedelta(days=days)).select_related('medicine').order_by('expiry_date')
    return {'low_stock':low,'expiring':MedicineBatchSerializer(expiring,many=True).data}

class MedicineBatchViewSet(viewsets.ModelViewSet):
    serializer_class=MedicineBatchSerializer
    permission_classes=[IsPharmacyStaff]
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        qs=MedicineBatch.objects.select_related('medicine')
        medicine=self.request.query_params.get('medicine')
        return qs.filter(medicine_id=medicine) if medicine else qs
    @action(detail=True,methods=['post'])
    def quarantine(self,request,pk=None):
        batch=self.get_object(); batch.quarantined=True; batch.save(update_fields=['quarantined'])
        return Response(self.get_serializer(batch).data)

class PrescriptionItemSerializer(serializers.ModelSerializer):
    medicine_name=serializers.CharField(source='medicine.name',read_only=True)
    patient_name=serializers.CharField(source='prescription.record.patient.full_name',read_only=True)
    class Meta: model=PrescriptionItem; fields=['id','prescription','medicine','medicine_name','patient_name','dosage','frequency','duration','instructions','dispensed_quantity','dispensed_at']; read_only_fields=['dispensed_quantity','dispensed_at']

class PrescriptionItemViewSet(viewsets.ModelViewSet):
    serializer_class=PrescriptionItemSerializer
    http_method_names=['get','post','head','options']
    def get_queryset(self):
        qs=PrescriptionItem.objects.select_related('medicine','prescription__record__patient')
        u=self.request.user
        if u.role in {'PHARMACIST','ADMIN'}: pass
        elif u.role=='DOCTOR': qs=qs.filter(prescription__record__doctor__user=u)
        elif u.role=='PATIENT': qs=qs.filter(prescription__record__patient__user=u)
        else: return qs.none()
        if self.request.query_params.get('pending'): qs=qs.filter(dispensed_at__isnull=True)
        return qs.order_by('-id')
    def perform_create(self,serializer):
        u=self.request.user
        if u.role not in {'ADMIN','DOCTOR'}: raise PermissionDenied('Only prescribers can add medicines.')
        prescription=serializer.validated_data['prescription']
        if u.role=='DOCTOR' and not (prescription.record.doctor and prescription.record.doctor.user_id==u.id): raise PermissionDenied()
        serializer.save()
    @action(detail=True,methods=['post'],permission_classes=[IsPharmacyStaff])
    def dispense(self,request,pk=None):
        quantity=serializers.IntegerField(min_value=1,max_value=10000).run_validation(request.data.get('quantity'))
        with transaction.atomic():
            item=get_object_or_404(PrescriptionItem.objects.select_for_update(),pk=pk)
            if item.dispensed_at: raise ValidationError('This item has already been dispensed.')
            dispense_fifo(item.medicine,quantity)
            item.dispensed_quantity=quantity; item.dispensed_at=timezone.now(); item.save(update_fields=['dispensed_quantity','dispensed_at'])
            patient_user=item.prescription.record.patient.user_id
            if patient_user: Notification.objects.create(user_id=patient_user,title='Prescription ready',message=f'{item.medicine.name} is ready for collection at the pharmacy.')
        return Response(self.get_serializer(item).data)

def dispense_fifo(medicine,quantity):
    """Consume stock oldest-expiry first. Expired or quarantined stock is never used."""
    batches=list(usable_batches(medicine).select_for_update().order_by('expiry_date','id'))
    if sum(b.quantity for b in batches)<quantity:
        expired=medicine.batches.filter(Q(expiry_date__lte=timezone.localdate())|Q(quarantined=True),quantity__gt=0).exists()
        raise ValidationError('Insufficient unexpired stock.'+(' Expired or quarantined batches cannot be dispensed.' if expired else ''))
    remaining=quantity; used=[]
    for batch in batches:
        take=min(batch.quantity,remaining)
        batch.quantity-=take; batch.save(update_fields=['quantity'])
        used.append((batch.batch_number,take)); remaining-=take
        if not remaining: break
    return used

# ---------------------------------------------------------------- billing

def recalculate_bill(bill):
    """Invoice totals always equal the sum of their line items."""
    totals={'CONSULTATION':Decimal(0),'LAB':Decimal(0),'PHARMACY':Decimal(0),'OTHER':Decimal(0)}
    for item in bill.items.all():
        key=item.category if item.category in totals else 'OTHER'
        totals[key]+=item.amount
    bill.consultation_fee=totals['CONSULTATION']; bill.lab_charges=totals['LAB']; bill.medicine_charges=totals['PHARMACY']; bill.other_charges=totals['OTHER']
    bill.save()

class BillItemSerializer(serializers.ModelSerializer):
    amount=serializers.DecimalField(max_digits=12,decimal_places=2,read_only=True)
    class Meta: model=BillItem; fields=['id','bill','category','description','quantity','unit_price','amount']

class BillItemViewSet(viewsets.ModelViewSet):
    serializer_class=BillItemSerializer
    http_method_names=['get','post','delete','head','options']
    def get_queryset(self):
        qs=BillItem.objects.select_related('bill')
        u=self.request.user
        if u.role=='PATIENT': qs=qs.filter(bill__patient__user=u)
        elif u.role not in {'ADMIN','ACCOUNTANT','RECEPTIONIST'}: return qs.none()
        bill=self.request.query_params.get('bill')
        return qs.filter(bill_id=bill) if bill else qs
    def get_permissions(self):
        return [IsAuthenticated()] if self.action in {'list','retrieve'} else [IsFinanceStaff()]
    def _editable(self,bill):
        if bill.status!='Pending': raise ValidationError('Only pending invoices can be changed.')
        if hasattr(bill,'checkout'): raise ValidationError('This invoice has an online checkout and is locked.')
    def perform_create(self,serializer):
        with transaction.atomic():
            bill=Bill.objects.select_for_update().get(pk=serializer.validated_data['bill'].pk); self._editable(bill)
            serializer.save(); recalculate_bill(bill)
    def perform_destroy(self,instance):
        with transaction.atomic():
            bill=Bill.objects.select_for_update().get(pk=instance.bill_id); self._editable(bill)
            instance.delete(); recalculate_bill(bill)

class InsuranceClaimSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='bill.patient.full_name',read_only=True)
    bill_total=serializers.DecimalField(source='bill.total',max_digits=10,decimal_places=2,read_only=True)
    class Meta: model=InsuranceClaim; fields=['id','bill','patient_name','bill_total','provider','policy_number','tpa_name','claimed_amount','approved_amount','status','notes','created_at','updated_at']; read_only_fields=['status','approved_amount','created_at','updated_at']
    def validate(self,attrs):
        bill=attrs.get('bill',getattr(self.instance,'bill',None)); amount=attrs.get('claimed_amount')
        if bill and amount is not None and amount>bill.total: raise serializers.ValidationError({'claimed_amount':'Claim cannot exceed the invoice total.'})
        return attrs

class InsuranceClaimViewSet(viewsets.ModelViewSet):
    serializer_class=InsuranceClaimSerializer
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        qs=InsuranceClaim.objects.select_related('bill__patient')
        u=self.request.user
        if u.role=='PATIENT': return qs.filter(bill__patient__user=u)
        return qs if u.role in {'ADMIN','ACCOUNTANT','RECEPTIONIST'} else qs.none()
    def get_permissions(self):
        return [IsAuthenticated()] if self.action in {'list','retrieve'} else [has_role('ADMIN','ACCOUNTANT')()]
    def perform_create(self,serializer): serializer.save(created_by=self.request.user)
    @action(detail=True,methods=['post'])
    def transition(self,request,pk=None):
        flow={'DRAFT':{'SUBMITTED'},'SUBMITTED':{'APPROVED','REJECTED'},'APPROVED':{'SETTLED'}}
        with transaction.atomic():
            claim=get_object_or_404(self.get_queryset().select_for_update(),pk=pk)
            status=request.data.get('status')
            if status not in flow.get(claim.status,set()): raise ValidationError(f'Cannot move a {claim.status.lower()} claim to {status}.')
            if status=='APPROVED':
                approved=serializers.DecimalField(max_digits=10,decimal_places=2,min_value=Decimal(0)).run_validation(request.data.get('approved_amount'))
                if approved>claim.claimed_amount: raise ValidationError('Approved amount cannot exceed the claimed amount.')
                claim.approved_amount=approved
            claim.status=status; claim.save()
        return Response(self.get_serializer(claim).data)

@api_view(['GET'])
@permission_classes([has_role('ADMIN','ACCOUNTANT','SUPER_ADMIN')])
def revenue_analytics(request):
    today=timezone.localdate()
    try:
        start=serializers.DateField().run_validation(request.query_params.get('from') or str(today-timedelta(days=29)))
        end=serializers.DateField().run_validation(request.query_params.get('to') or str(today))
    except ValidationError: raise ValidationError('Use YYYY-MM-DD dates.')
    if start>end: raise ValidationError('The start date must be before the end date.')
    paid=Bill.objects.filter(status='Paid',created_at__date__gte=start,created_at__date__lte=end)
    by_day={str(r['created_at__date']):float(r['total']) for r in paid.values('created_at__date').annotate(total=Sum('total'))}
    days=[(start+timedelta(days=i)) for i in range((end-start).days+1)]
    sums=paid.aggregate(consultation=Sum('consultation_fee'),lab=Sum('lab_charges'),pharmacy=Sum('medicine_charges'),other=Sum('other_charges'),total=Sum('total'))
    return Response({'from':start,'to':end,'daily':[{'date':str(d),'revenue':by_day.get(str(d),0)} for d in days],
        'by_category':{k:float(v or 0) for k,v in sums.items()},
        'outstanding':float(Bill.objects.filter(status='Pending').aggregate(x=Sum('total'))['x'] or 0),
        'claims':{s:InsuranceClaim.objects.filter(status=s).count() for s,_ in InsuranceClaim.STATUS}})

# ---------------------------------------------------------------- nursing

class VitalsSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    recorded_by_name=serializers.SerializerMethodField(); bmi=serializers.SerializerMethodField()
    class Meta: model=VitalsEntry; fields=['id','patient','patient_name','blood_pressure','pulse','temperature','spo2','height_cm','weight_kg','bmi','medication_notes','recorded_by_name','created_at']
    def get_recorded_by_name(self,obj): return obj.recorded_by.get_full_name() or obj.recorded_by.username
    def get_bmi(self,obj): return bmi(obj.height_cm,obj.weight_kg)

def bmi(height_cm,weight_kg):
    if not height_cm or not weight_kg: return None
    metres=float(height_cm)/100
    return round(float(weight_kg)/(metres*metres),1)

class VitalsViewSet(viewsets.ModelViewSet):
    serializer_class=VitalsSerializer
    http_method_names=['get','post','head','options']
    def get_queryset(self):
        qs=VitalsEntry.objects.filter(patient__in=visible_patients(self.request.user)).select_related('patient','recorded_by')
        patient=self.request.query_params.get('patient')
        return qs.filter(patient_id=patient) if patient else qs
    def get_permissions(self):
        return [IsAuthenticated()] if self.action in {'list','retrieve'} else [IsNursingStaff()]
    def perform_create(self,serializer):
        if not visible_patients(self.request.user).filter(pk=serializer.validated_data['patient'].pk).exists(): raise PermissionDenied()
        serializer.save(recorded_by=self.request.user)

# ---------------------------------------------------------------- audit & search

class AuditLogSerializer(serializers.ModelSerializer):
    username=serializers.CharField(source='user.username',read_only=True,default='')
    class Meta: model=AuditLog; fields=['id','username','method','path','status_code','ip_address','created_at']

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=AuditLogSerializer
    permission_classes=[has_role('ADMIN','SUPER_ADMIN')]
    def get_queryset(self): return AuditLog.objects.select_related('user')[:500]

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def global_search(request):
    q=request.query_params.get('q','').strip()
    if len(q)<2: return Response({'patients':[],'doctors':[],'medicines':[]})
    u=request.user
    patients=visible_patients(u).filter(Q(full_name__icontains=q)|Q(patient_id__icontains=q)|Q(phone__icontains=q))[:10]
    doctors=Doctor.objects.select_related('user','department').filter(Q(user__first_name__icontains=q)|Q(user__last_name__icontains=q)|Q(specialization__icontains=q)|Q(doctor_id__icontains=q))[:10]
    medicines=Medicine.objects.filter(name__icontains=q)[:10] if u.role in {'ADMIN','PHARMACIST','DOCTOR'} else []
    return Response({
        'patients':[{'id':p.pk,'patient_id':p.patient_id,'name':p.full_name,'phone':p.phone} for p in patients],
        'doctors':[{'id':d.pk,'name':d.user.get_full_name() or d.user.username,'specialization':d.specialization,'department':d.department.name if d.department else None} for d in doctors],
        'medicines':[{'id':m.pk,'name':m.name,'form':m.form} for m in medicines]})

# ---------------------------------------------------------------- prescription print

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def prescription_print(request,pk):
    """Print-ready prescription with letterhead and the doctor's signature."""
    qs=Prescription.objects.select_related('record__patient','record__doctor__user')
    u=request.user
    if u.role=='DOCTOR': qs=qs.filter(record__doctor__user=u)
    elif u.role=='PATIENT': qs=qs.filter(record__patient__user=u)
    elif u.role not in {'ADMIN','PHARMACIST'}: raise PermissionDenied()
    p=get_object_or_404(qs,pk=pk); record=p.record; doctor=record.doctor
    rows=[(p.medicine,p.form,p.dosage,p.frequency,p.duration,p.instructions)]
    rows+=[(i.medicine.name,i.medicine.form,i.dosage,i.frequency,i.duration,i.instructions) for i in p.items.select_related('medicine')]
    signature=doctor.signature if doctor and doctor.signature.startswith('data:image/png;base64,') else ''
    doctor_name=(doctor.user.get_full_name() or doctor.user.username) if doctor else 'Attending clinician'
    body=''.join('<tr>'+''.join(f'<td>{escape(str(c or ""))}</td>' for c in row)+'</tr>' for row in rows)
    html=f'''<!doctype html><html><head><meta charset="utf-8"><title>Prescription #{p.pk}</title>
<style>body{{font-family:system-ui,sans-serif;margin:40px;color:#111}}header{{border-bottom:3px solid #1f5fbf;padding-bottom:12px;display:flex;justify-content:space-between}}
h1{{margin:0;color:#1f5fbf}}table{{width:100%;border-collapse:collapse;margin-top:24px}}td,th{{border:1px solid #ccc;padding:8px;text-align:left}}
.sig{{margin-top:48px;text-align:right}}.sig img{{max-height:70px}}@media print{{button{{display:none}}}}</style></head><body>
<header><div><h1>MedCore HMS</h1><small>Prescription #{p.pk}</small></div><div>{escape(record.created_at.strftime("%d %b %Y"))}</div></header>
<p><b>Patient:</b> {escape(record.patient.full_name)} ({escape(record.patient.patient_id)})<br><b>Diagnosis:</b> {escape(record.diagnosis)}{f" (ICD-10 {escape(record.icd10_code)})" if record.icd10_code else ""}</p>
<table><thead><tr><th>Medicine</th><th>Form</th><th>Dosage</th><th>Frequency</th><th>Duration</th><th>Instructions</th></tr></thead><tbody>{body}</tbody></table>
<div class="sig">{f'<img alt="Signature" src="{signature}"><br>' if signature else '<br><br>______________________<br>'}Dr. {escape(doctor_name)}</div>
<button onclick="print()">Print / Save as PDF</button></body></html>'''
    response=HttpResponse(html,content_type='text/html; charset=utf-8')
    response['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'unsafe-inline'"
    return response

@api_view(['GET','PUT'])
@permission_classes([has_role('DOCTOR')])
def doctor_signature(request):
    doctor=get_object_or_404(Doctor,user=request.user)
    if request.method=='PUT':
        value=request.data.get('signature','')
        if value and (not value.startswith('data:image/png;base64,') or len(value)>300_000):
            raise ValidationError('Upload a PNG signature under 200 KB.')
        doctor.signature=value; doctor.save(update_fields=['signature'])
    return Response({'signature':doctor.signature})

# ---------------------------------------------------------------- Stripe

def stripe_ready(): return bool(settings.PAYMENTS_ENABLED and settings.STRIPE_SECRET_KEY.startswith('sk_') and settings.STRIPE_WEBHOOK_SECRET)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stripe_checkout(request,pk):
    qs=Bill.objects.all()
    if request.user.role=='PATIENT': qs=qs.filter(patient__user=request.user)
    elif request.user.role not in {'ADMIN','ACCOUNTANT'}: raise PermissionDenied()
    bill=get_object_or_404(qs,pk=pk)
    if bill.status!='Pending' or bill.total<=0: raise ValidationError('Only pending invoices with a balance can be paid.')
    if not stripe_ready(): return Response({'detail':'Card payments are not enabled. Please contact hospital billing.'},status=503)
    try:
        session=provider_request('https://api.stripe.com/v1/checkout/sessions',settings.STRIPE_SECRET_KEY,'',{
            'mode':'payment','success_url':f'{settings.FRONTEND_URL}/?payment=success','cancel_url':f'{settings.FRONTEND_URL}/?payment=cancelled',
            'line_items[0][price_data][currency]':'inr','line_items[0][price_data][unit_amount]':int(bill.total*100),
            'line_items[0][price_data][product_data][name]':f'MedCore invoice #{bill.pk}','line_items[0][quantity]':1,
            'metadata[bill_id]':bill.pk,'client_reference_id':bill.pk},form=True)
    except ProviderUnavailable:
        return Response({'detail':'The payment provider could not be reached. Please try again.'},status=502)
    return Response({'url':session.get('url','')})

def verify_stripe_signature(payload,header,secret,tolerance=300):
    try:
        parts=dict(item.split('=',1) for item in header.split(','))
        stamp=int(parts['t']); given=[v for k,v in (i.split('=',1) for i in header.split(',')) if k=='v1']
    except (ValueError,KeyError): return False
    if abs(time.time()-stamp)>tolerance: return False
    expected=hmac.new(secret.encode(),f'{stamp}.'.encode()+payload,hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected,g) for g in given)

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """Payment status comes only from Stripe's signed webhook, never from the browser."""
    if not settings.STRIPE_WEBHOOK_SECRET or not verify_stripe_signature(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET):
        return Response(status=400)
    event=json.loads(request.body)
    if event.get('type')=='checkout.session.completed':
        session=event['data']['object']
        if session.get('payment_status')=='paid':
            with transaction.atomic():
                bill=Bill.objects.select_for_update().filter(pk=session.get('metadata',{}).get('bill_id')).first()
                if bill and not Payment.objects.filter(provider_reference=session['id']).exists():
                    if session.get('amount_total')!=int(bill.total*100): return Response(status=400)
                    Payment.objects.create(bill=bill,amount=bill.total,method='STRIPE',status='PAID',provider_reference=session['id'])
                    bill.status='Paid'; bill.save(update_fields=['status'])
                    if bill.patient.user_id: Notification.objects.create(user_id=bill.patient.user_id,title='Payment received',message=f'Thank you. Invoice #{bill.pk} is paid.')
    return Response({'received':True})

# ---------------------------------------------------------------- dashboards for additional roles

def extra_dashboard(user):
    today=timezone.localdate()
    if user.role=='SUPER_ADMIN':
        return {'role':'SUPER_ADMIN','hospitals':Hospital.objects.count(),'verified_hospitals':Hospital.objects.filter(verified=True).count(),'users':type(user).objects.count(),'patients':Patient.objects.count(),'appointments':Appointment.objects.count(),
                'revenue':float(Bill.objects.filter(status='Paid').aggregate(x=Sum('total'))['x'] or 0)}
    if user.role=='PHARMACIST':
        alerts=pharmacy_alerts()
        return {'role':'PHARMACIST','medicines':Medicine.objects.filter(active=True).count(),'pending_dispense':PrescriptionItem.objects.filter(dispensed_at__isnull=True).count(),'low_stock_count':len(alerts['low_stock']),'expiring_count':len(alerts['expiring']),**alerts}
    if user.role=='NURSE':
        return {'role':'NURSE','admitted':Patient.objects.filter(admission_status='Admitted').count(),'beds_available':Bed.objects.filter(status='Available').count(),'beds_occupied':Bed.objects.filter(status='Occupied').count(),
                'vitals_today':VitalsEntry.objects.filter(created_at__date=today).count(),'emergency_patients':Patient.objects.filter(emergency_priority=True).count()}
    if user.role=='LAB_TECH':
        return {'role':'LAB_TECH',**{s.lower():LabOrder.objects.filter(status=s).count() for s in ['ORDERED','SAMPLE_COLLECTED','PROCESSING','REVIEW']},'approved_today':LabOrder.objects.filter(status='APPROVED',updated_at__date=today).count()}
    if user.role=='ACCOUNTANT':
        return {'role':'ACCOUNTANT','revenue':float(Bill.objects.filter(status='Paid').aggregate(x=Sum('total'))['x'] or 0),'revenue_today':float(Bill.objects.filter(status='Paid',created_at__date=today).aggregate(x=Sum('total'))['x'] or 0),
                'pending_bills':float(Bill.objects.filter(status='Pending').aggregate(x=Sum('total'))['x'] or 0),'open_claims':InsuranceClaim.objects.filter(status__in=['DRAFT','SUBMITTED']).count()}
    return None

def admin_extras():
    today=timezone.localdate()
    week=[today-timedelta(days=i) for i in range(6,-1,-1)]
    counts={r['date']:r['n'] for r in Appointment.objects.filter(date__gte=week[0],date__lte=today).values('date').annotate(n=Count('id'))}
    occupancy=[]
    for dept in Department.objects.annotate(doctors_n=Count('doctors',distinct=True)):
        load=Appointment.objects.filter(doctor__department=dept,date__gte=week[0],date__lte=today).exclude(status__in=['Cancelled','No Show']).count()
        occupancy.append({'name':dept.name,'doctors':dept.doctors_n,'appointments_7d':load})
    return {'patients_today':Patient.objects.filter(created_at__date=today).count()+Appointment.objects.filter(date=today).values('patient').distinct().count(),
            'revenue_today':float(Bill.objects.filter(status='Paid',created_at__date=today).aggregate(x=Sum('total'))['x'] or 0),
            'beds_occupied':Bed.objects.filter(status='Occupied').count(),'active_doctors':Doctor.objects.filter(available=True,deleted_at__isnull=True).count(),
            'appointments_7d':[{'date':str(d),'count':counts.get(d,0)} for d in week],'department_occupancy':occupancy,
            'low_stock':pharmacy_alerts()['low_stock'][:8],'recent_activity':AuditLogSerializer(AuditLog.objects.select_related('user')[:10],many=True).data}

def doctor_extras(doctor):
    today=timezone.localdate()
    from .serializers import AppointmentSerializer
    follow=Appointment.objects.filter(doctor=doctor,date__gte=today,date__lte=today+timedelta(days=31)).exclude(status__in=['Cancelled','No Show']).select_related('patient','doctor__user').order_by('date','time')
    pending_labs=LabOrder.objects.filter(record__doctor=doctor,status='REVIEW').select_related('test','record__patient')
    recent_rx=Prescription.objects.filter(record__doctor=doctor).select_related('record__patient').order_by('-id')[:6]
    return {'follow_ups':AppointmentSerializer(follow,many=True).data,
            'pending_lab_approvals':[{'id':o.id,'test':o.test.name,'patient':o.record.patient.full_name,'result':o.result_value} for o in pending_labs],
            'recent_prescriptions':[{'id':p.id,'medicine':p.medicine,'dosage':p.dosage,'patient':p.record.patient.full_name} for p in recent_rx]}
