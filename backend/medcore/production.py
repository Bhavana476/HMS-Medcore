"""Opt-in deployment settings: DJANGO_SETTINGS_MODULE=medcore.production."""
from .settings import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY', '')
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('Production requires a unique SECRET_KEY of at least 50 characters.')

if not FIELD_ENCRYPTION_KEY:
    raise ImproperlyConfigured('Set FIELD_ENCRYPTION_KEY (a Fernet key) so clinical notes are encrypted with a dedicated key.')
REFRESH_COOKIE_SECURE = True

ALLOWED_HOSTS =[host.strip() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Set ALLOWED_HOSTS to explicit deployment hostnames.')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '')
if not FRONTEND_URL.startswith('https://'):
    raise ImproperlyConfigured('Set FRONTEND_URL to the HTTPS portal URL.')
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [FRONTEND_URL.rstrip('/')]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Enable only behind a private proxy that overwrites this request header.
if os.environ.get('TRUST_PROXY_HTTPS', 'False').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
