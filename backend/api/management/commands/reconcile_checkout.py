from django.core.management.base import BaseCommand,CommandError
from api.models import PaymentCheckout
from api.integrations import razorpay,reconcile,ProviderUnavailable
import re

class Command(BaseCommand):
    help='Reconcile an uncertain Razorpay checkout after locating its link in the provider dashboard.'
    def add_arguments(self,parser):
        parser.add_argument('--bill',type=int,required=True)
        parser.add_argument('--provider-id',required=True)
    def handle(self,*args,**options):
        if not re.fullmatch(r'plink_[A-Za-z0-9]+',options['provider_id']): raise CommandError('Invalid payment-link ID.')
        try: checkout=PaymentCheckout.objects.get(bill_id=options['bill'])
        except PaymentCheckout.DoesNotExist: raise CommandError('No checkout exists for this bill.')
        if checkout.provider_id and checkout.provider_id!=options['provider_id']: raise CommandError('This checkout is already linked to a different provider ID.')
        try: link=razorpay('payment_links/'+options['provider_id'])
        except ProviderUnavailable: raise CommandError('Could not fetch the provider link.')
        if link.get('reference_id')!=str(checkout.reference) or link.get('currency')!='INR' or link.get('amount')!=int(checkout.amount*100):
            raise CommandError('Provider reference, amount or currency does not match. No changes made.')
        checkout.provider_id=options['provider_id'];checkout.save(update_fields=['provider_id'])
        try: checkout=reconcile(checkout)
        except ProviderUnavailable: raise CommandError('Provider verification could not be completed.')
        self.stdout.write(f'Checkout state: {checkout.state}')
