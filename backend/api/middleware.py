import logging
from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication

WRITE_METHODS={'POST','PUT','PATCH','DELETE'}
logger=logging.getLogger(__name__)

class AuditLogMiddleware:
    """Record every create/update/delete API call with user, IP and timestamp."""
    def __init__(self,get_response): self.get_response=get_response

    def __call__(self,request):
        response=self.get_response(request)
        if request.method in WRITE_METHODS and request.path.startswith('/api/'):
            try: self.record(request,response)
            except Exception:
                logger.exception('Audit log write failed.')
        return response

    def record(self,request,response):
        from .models import AuditLog
        user=getattr(request,'user',None)
        if not (user and user.is_authenticated):
            # DRF authenticates inside the view, so resolve the JWT here.
            try:
                result=JWTAuthentication().authenticate(request)
                user=result[0] if result else None
            except Exception:
                user=None
        # X-Forwarded-For is client-controlled unless a trusted proxy overwrites it.
        forwarded=request.META.get('HTTP_X_FORWARDED_FOR','') if getattr(settings,'TRUST_PROXY_HEADERS',False) else ''
        ip=forwarded.split(',')[-1].strip() if forwarded else request.META.get('REMOTE_ADDR')
        AuditLog.objects.create(user=user if user and user.is_authenticated else None,method=request.method,
            path=request.path[:500],status_code=response.status_code,ip_address=ip or None)
