from django.urls import path
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from .views import *
from .portal import DocumentViewSet,LabTestViewSet,LabOrderViewSet,password_request,password_confirm,public_directory,reschedule
from .communications import ThreadViewSet,MessageViewSet,care_contacts,communication_preferences
from .integrations import integration_status,start_checkout,check_payment,payment_webhook
from .portal import signup
from .operations import (ThrottledLoginView,ThrottledRefreshView,logout,send_verification,confirm_verification,HospitalViewSet,
    MedicineViewSet,MedicineBatchViewSet,PrescriptionItemViewSet,BillItemViewSet,InsuranceClaimViewSet,VitalsViewSet,
    AuditLogViewSet,revenue_analytics,global_search,prescription_print,stripe_checkout,stripe_webhook,doctor_signature)
r=DefaultRouter()
r.register('care-threads',ThreadViewSet,basename='care-thread')
r.register('care-messages',MessageViewSet,basename='care-message')
r.register('documents',DocumentViewSet,basename='document')
r.register('lab-tests',LabTestViewSet,basename='lab-test')
r.register('lab-orders',LabOrderViewSet,basename='lab-order')
r.register('hospitals',HospitalViewSet,basename='hospital')
r.register('medicines',MedicineViewSet,basename='medicine')
r.register('medicine-batches',MedicineBatchViewSet,basename='medicine-batch')
r.register('prescription-items',PrescriptionItemViewSet,basename='prescription-item')
r.register('bill-items',BillItemViewSet,basename='bill-item')
r.register('insurance-claims',InsuranceClaimViewSet,basename='insurance-claim')
r.register('vitals',VitalsViewSet,basename='vitals')
r.register('audit-logs',AuditLogViewSet,basename='audit-log')
for prefix, view in [('departments',DepartmentViewSet),('doctors',DoctorViewSet),('patients',PatientViewSet),('appointments',AppointmentViewSet),('availability',AvailabilityViewSet),('medical-records',MedicalRecordViewSet),('prescriptions',PrescriptionViewSet),('bills',BillViewSet),('beds',BedViewSet),('notifications',NotificationViewSet)]: r.register(prefix,view)
service_urls=[path('care-contacts/',care_contacts),path('communication-preferences/',communication_preferences),path('integration-status/',integration_status),path('bills/<int:pk>/checkout/',start_checkout),path('bills/<int:pk>/payment-status/',check_payment),path('webhooks/razorpay/',payment_webhook),
    path('bills/<int:pk>/stripe-checkout/',stripe_checkout),path('payments/webhook/stripe/',stripe_webhook)]
operation_urls=[path('logout/',logout),path('verify/send/',send_verification),path('verify/confirm/',confirm_verification),
    path('analytics/revenue/',revenue_analytics),path('search/',global_search),path('doctor-signature/',doctor_signature),path('prescriptions/<int:pk>/print/',prescription_print),
    path('schema/',SpectacularAPIView.as_view(),name='schema'),path('docs/',SpectacularSwaggerView.as_view(url_name='schema'),name='swagger-ui')]
urlpatterns=[path('password-reset/',password_request),path('password-reset/confirm/',password_confirm),path('public-directory/',public_directory),path('appointments/<int:pk>/reschedule/',reschedule),path('register/',RegisterViewSet.as_view({'post':'create'})),path('login/',ThrottledLoginView.as_view()),path('token/refresh/',ThrottledRefreshView.as_view()),path('me/',me),path('accounts/',accounts),path('dashboard/',dashboard),path('timeline/',timeline),path('discharges/',discharges),path('imported-admissions/',imported_admissions),path('doctor-directory/',doctor_directory),path('patient-directory/',patient_directory)]+r.urls
urlpatterns=operation_urls+service_urls+urlpatterns
urlpatterns=[path('signup/',signup)]+urlpatterns
