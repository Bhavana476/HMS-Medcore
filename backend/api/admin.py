from django.contrib import admin
from .models import *
for m in [User,Department,Doctor,Appointment,DoctorAvailability,MedicalRecord,Prescription,Bill,Bed,Notification]: admin.site.register(m)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    def has_delete_permission(self,request,obj=None):
        return False
