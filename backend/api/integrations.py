"""External services use server-side credentials and fixed provider endpoints."""
import base64
import hashlib
import hmac
import json
import re
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view,permission_classes,authentication_classes
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,PermissionDenied
from .models import Bill,Payment,PaymentCheckout,AppointmentReminder

class ProviderUnavailable(Exception): pass

def provider_request(url,username,password,payload=None,form=False):
    body=None if payload is None else (urlencode(payload).encode() if form else json.dumps(payload).encode())
    auth=base64.b64encode(f'{username}:{password}'.encode()).decode()
    request=Request(url,data=body,headers={'Authorization':f'Basic {auth}','Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'})
    try:
        with urlopen(request,timeout=15) as response: return json.load(response)
    except (HTTPError,URLError,TimeoutError,OSError,ValueError):
        # Never expose provider responses, secrets or recipients in API errors/logs.
        raise ProviderUnavailable('Provider request could not be confirmed.') from None

def payment_ready():
    expected='rzp_live_' if settings.PAYMENT_MODE=='live' else 'rzp_test_'
    return bool(settings.PAYMENTS_ENABLED and settings.RAZORPAY_KEY_ID.startswith(expected) and settings.RAZORPAY_KEY_SECRET)

def razorpay(path,payload=None):
    if not payment_ready(): raise ProviderUnavailable('Online payments are not configured.')
    return provider_request('https://api.razorpay.com/v1/'+path,settings.RAZORPAY_KEY_ID,settings.RAZORPAY_KEY_SECRET,payload)

def sms_ready():
    return bool(settings.SMS_ENABLED and re.fullmatch(r'AC[0-9a-fA-F]{32}',settings.TWILIO_ACCOUNT_SID) and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER)

def send_sms(number,body):
    if not sms_ready(): raise ProviderUnavailable('SMS is not configured.')
    if not re.fullmatch(r'\+[1-9]\d{7,14}',number or ''): raise ProviderUnavailable('Recipient needs an international-format phone number.')
    result=provider_request(f'https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json',settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN,{'To':number,'From':settings.TWILIO_FROM_NUMBER,'Body':body},form=True)
    if not result.get('sid') or result.get('status') in {'failed','undelivered'}: raise ProviderUnavailable('SMS submission was not confirmed.')
    return result['sid']

def bill_for(request,pk):
    qs=Bill.objects.all()
    if request.user.role=='PATIENT': qs=qs.filter(patient__user=request.user)
    elif request.user.role!='ADMIN': raise PermissionDenied()
    return get_object_or_404(qs,pk=pk)

def checkout_data(checkout):
    return {'state':checkout.state,'url':checkout.url if checkout.state=='ACTIVE' else '', 'mode':checkout.mode}

def reconcile(checkout):
    if not checkout.provider_id: return checkout
    if checkout.mode!=settings.PAYMENT_MODE: raise ProviderUnavailable('Payment mode differs from the checkout.')
    link=razorpay('payment_links/'+checkout.provider_id)
    expected=int(checkout.amount*100)
    if link.get('id')!=checkout.provider_id or link.get('reference_id')!=str(checkout.reference) or link.get('amount')!=expected or link.get('currency')!='INR':
        raise ProviderUnavailable('Payment details do not match the bill.')
    with transaction.atomic():
        checkout=PaymentCheckout.objects.select_for_update().get(pk=checkout.pk)
        bill=Bill.objects.select_for_update().get(pk=checkout.bill_id)
        if link.get('status')=='paid' and link.get('amount_paid')==expected:
            Payment.objects.get_or_create(provider_reference=checkout.provider_id,defaults={'bill':bill,'amount':checkout.amount,'method':'RAZORPAY','status':'PAID'})
            if bill.total!=checkout.amount or bill.status not in {'Pending','Paid'}:
                checkout.state='REVIEW'
            else:
                checkout.state='PAID';bill.status='Paid';bill.save(update_fields=['status'])
        elif checkout.state!='PAID' and link.get('status') in {'cancelled','expired'}:
            checkout.state='EXPIRED'
        elif checkout.state!='PAID' and link.get('status')=='created' and bill.status=='Pending' and bill.total==checkout.amount:
            url=link.get('short_url','')
            parsed=urlparse(url)
            if parsed.scheme=='https' and parsed.hostname in {'rzp.io','rzp.co','razorpay.com'}:
                checkout.url=url;checkout.state='ACTIVE'
        checkout.save(update_fields=['state','url'])
    return checkout

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def integration_status(request):
    result={'payments':payment_ready(),'payment_mode':settings.PAYMENT_MODE,'sms':sms_ready(),'email':settings.EMAIL_BACKEND=='django.core.mail.backends.smtp.EmailBackend' and bool(settings.EMAIL_HOST)}
    if request.user.role=='ADMIN':
        try: result['scheduler_last_run']=json.loads(settings.REMINDER_HEARTBEAT_PATH.read_text()).get('last_run')
        except (OSError,ValueError): result['scheduler_last_run']=None
        result['reminders_needing_review']=AppointmentReminder.objects.filter(state__in=['UNKNOWN','SENDING']).count()
        result['payments_needing_review']=PaymentCheckout.objects.filter(state__in=['REVIEW','CREATING']).count()
    return Response(result)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_checkout(request,pk):
    bill=bill_for(request,pk)
    if not payment_ready(): return Response({'detail':'Online payments are not enabled. Please contact hospital billing.'},status=503)
    if bill.status!='Pending' or bill.total<=0: raise ValidationError('Only a positive pending bill can be paid online.')
    with transaction.atomic():
        bill=Bill.objects.select_for_update().get(pk=bill.pk)
        if bill.status!='Pending' or bill.total<=0: raise ValidationError('This bill is no longer payable.')
        checkout,created=PaymentCheckout.objects.get_or_create(bill=bill,defaults={'amount':bill.total,'mode':settings.PAYMENT_MODE})
    if not created:
        if checkout.mode!=settings.PAYMENT_MODE or checkout.amount!=bill.total: raise ValidationError('This checkout needs billing staff review.')
        if checkout.state in {'REVIEW','CREATING','EXPIRED'}: return Response({'detail':'This checkout needs billing staff review before another payment attempt.'},status=409)
        return Response(checkout_data(checkout))
    try:
        link=razorpay('payment_links/',{'amount':int(bill.total*100),'currency':'INR','accept_partial':False,'reference_id':str(checkout.reference),'description':f'MedCore invoice {bill.pk}','notify':{'sms':False,'email':False},'reminder_enable':False})
        host=urlparse(link.get('short_url',''))
        if not re.fullmatch(r'plink_[A-Za-z0-9]+',link.get('id','')) or host.scheme!='https' or host.hostname not in {'rzp.io','rzp.co','razorpay.com'}:
            raise ProviderUnavailable('Invalid provider checkout response.')
        checkout.provider_id=link['id'];checkout.url=link['short_url'];checkout.state='ACTIVE'
        checkout.save(update_fields=['provider_id','url','state'])
    except ProviderUnavailable:
        checkout.state='REVIEW';checkout.save(update_fields=['state'])
        return Response({'detail':'Checkout could not be confirmed. Contact billing before retrying to avoid a duplicate payment.'},status=502)
    return Response(checkout_data(checkout),status=201)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_payment(request,pk):
    bill=bill_for(request,pk)
    checkout=get_object_or_404(PaymentCheckout,bill=bill)
    try: checkout=reconcile(checkout)
    except ProviderUnavailable: return Response({'detail':'Could not verify with the payment provider. The bill has not been marked paid.'},status=503)
    return Response(checkout_data(checkout))

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_webhook(request):
    secret=settings.RAZORPAY_WEBHOOK_SECRET
    if not secret: return Response(status=503)
    expected=hmac.new(secret.encode(),request.body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,request.headers.get('X-Razorpay-Signature','')): return Response(status=403)
    try:
        event=json.loads(request.body)
        if event.get('event')!='payment_link.paid': return Response({'received':True})
        provider_id=event['payload']['payment_link']['entity']['id']
    except (ValueError,KeyError,TypeError,AttributeError): return Response(status=400)
    checkout=PaymentCheckout.objects.filter(provider_id=provider_id).first()
    if not checkout: return Response(status=404)
    try: reconcile(checkout)
    except ProviderUnavailable: return Response(status=503)
    return Response({'received':True})
