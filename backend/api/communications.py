from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers,viewsets,mixins
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied,ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import CareThread,CareMessage,Patient,Doctor,Notification,CommunicationPreference

def threads_for(user):
    qs=CareThread.objects.select_related('patient','doctor__user')
    if user.role=='ADMIN': return qs
    if user.role=='PATIENT': return qs.filter(patient__user=user)
    if user.role=='DOCTOR': return qs.filter(doctor__user=user)
    return qs.none()

def linked(patient,doctor):
    return patient.appointments.filter(doctor=doctor).exists() or patient.records.filter(doctor=doctor).exists()

class ThreadSerializer(serializers.ModelSerializer):
    patient_name=serializers.CharField(source='patient.full_name',read_only=True)
    doctor_name=serializers.SerializerMethodField()
    class Meta:
        model=CareThread
        fields=['id','patient','doctor','patient_name','doctor_name','updated_at']
        read_only_fields=['updated_at']
    def get_doctor_name(self,obj): return obj.doctor.user.get_full_name() or obj.doctor.user.username

class ThreadViewSet(mixins.ListModelMixin,mixins.CreateModelMixin,viewsets.GenericViewSet):
    permission_classes=[IsAuthenticated]
    serializer_class=ThreadSerializer
    def get_queryset(self): return threads_for(self.request.user)
    def create(self,request):
        if request.user.role not in {'PATIENT','DOCTOR','ADMIN'}: raise PermissionDenied()
        data=self.get_serializer(data=request.data);data.is_valid(raise_exception=True)
        patient=data.validated_data['patient'];doctor=data.validated_data['doctor']
        if request.user.role=='PATIENT' and patient.user_id!=request.user.pk: raise PermissionDenied()
        if request.user.role=='DOCTOR' and doctor.user_id!=request.user.pk: raise PermissionDenied()
        if not linked(patient,doctor): raise ValidationError('Choose a doctor already linked to this patient\'s care.')
        thread,created=CareThread.objects.get_or_create(patient=patient,doctor=doctor)
        return Response(self.get_serializer(thread).data,status=201 if created else 200)

class MessagePagination(PageNumberPagination): page_size=30

class MessageSerializer(serializers.ModelSerializer):
    sender_name=serializers.SerializerMethodField()
    sender_role=serializers.CharField(source='sender.role',read_only=True)
    class Meta:
        model=CareMessage
        fields=['id','thread','sender','sender_name','sender_role','body','created_at']
        read_only_fields=['sender','created_at']
        extra_kwargs={'body':{'max_length':4000,'allow_blank':False}}
    def get_sender_name(self,obj): return obj.sender.get_full_name() or obj.sender.username

class MessageViewSet(mixins.ListModelMixin,mixins.CreateModelMixin,viewsets.GenericViewSet):
    permission_classes=[IsAuthenticated]
    serializer_class=MessageSerializer
    pagination_class=MessagePagination
    def get_queryset(self):
        qs=CareMessage.objects.filter(thread__in=threads_for(self.request.user)).select_related('sender')
        thread=self.request.query_params.get('thread')
        if not thread: return qs.none()
        thread_id=serializers.IntegerField(min_value=1).run_validation(thread)
        get_object_or_404(threads_for(self.request.user),pk=thread_id)
        return qs.filter(thread_id=thread_id)
    def perform_create(self,serializer):
        thread=get_object_or_404(threads_for(self.request.user),pk=serializer.validated_data['thread'].pk)
        with transaction.atomic():
            serializer.save(sender=self.request.user)
            thread.updated_at=timezone.now();thread.save(update_fields=['updated_at'])
            recipient_ids={thread.patient.user_id,thread.doctor.user_id}-{None,self.request.user.pk}
            for user_id in recipient_ids:
                Notification.objects.create(user_id=user_id,title='New care-team message',message='A new message is available in your secure Messages page.')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def care_contacts(request):
    user=request.user
    pairs=Patient.objects.filter(Q(appointments__isnull=False)|Q(records__doctor__isnull=False)).distinct()
    if user.role=='PATIENT': pairs=pairs.filter(user=user)
    elif user.role=='DOCTOR': pairs=pairs.filter(Q(appointments__doctor__user=user)|Q(records__doctor__user=user)).distinct()
    elif user.role!='ADMIN': return Response([])
    result=[]
    for patient in pairs:
        doctors=Doctor.objects.filter(Q(appointments__patient=patient)|Q(records__patient=patient)).distinct().select_related('user')
        if user.role=='DOCTOR': doctors=doctors.filter(user=user)
        for doctor in doctors:
            result.append({'patient':patient.pk,'doctor':doctor.pk,'label':f'{patient.full_name} — Dr. {doctor.user.get_full_name() or doctor.user.username}'})
    return Response(result)

class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model=CommunicationPreference
        fields=['email_reminders','sms_reminders']

@api_view(['GET','PATCH'])
@permission_classes([IsAuthenticated])
def communication_preferences(request):
    preference,_=CommunicationPreference.objects.get_or_create(user=request.user)
    if request.method=='PATCH':
        serializer=PreferenceSerializer(preference,data=request.data,partial=True)
        serializer.is_valid(raise_exception=True);serializer.save()
    return Response(PreferenceSerializer(preference).data)
