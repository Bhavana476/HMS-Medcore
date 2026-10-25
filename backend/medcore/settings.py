from pathlib import Path
import os
from datetime import timedelta
BASE_DIR=Path(__file__).resolve().parent.parent
import json
# Optional private service configuration, shared by Django and scheduled commands.
service_file=BASE_DIR/'services.local.json'
if service_file.exists():
    service_values=json.loads(service_file.read_text(encoding='utf-8-sig'))
    service_keys={'MONGODB_URI','MONGODB_DB_NAME','EMAIL_BACKEND','EMAIL_HOST','EMAIL_PORT','EMAIL_USE_TLS','EMAIL_HOST_USER','EMAIL_HOST_PASSWORD','DEFAULT_FROM_EMAIL','FRONTEND_URL','PAYMENTS_ENABLED','PAYMENT_MODE','RAZORPAY_KEY_ID','RAZORPAY_KEY_SECRET','RAZORPAY_WEBHOOK_SECRET','SMS_ENABLED','TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_FROM_NUMBER','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','SENTRY_DSN','CORS_ALLOWED_ORIGINS','FIELD_ENCRYPTION_KEY','CLAMAV_HOST','CLAMAV_PORT'}
    for service_key,service_value in service_values.items():
        if service_key in service_keys: os.environ.setdefault(service_key,str(service_value))
# Override this through the SECRET_KEY environment variable in production.
# The development fallback is deliberately 32+ bytes so JWT signing is safe
# enough for local development and does not trigger PyJWT's key warning.
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-medcore-local-key-change-before-production-2026')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1'
    ).split(',')
    if host.strip()
]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','corsheaders','rest_framework','rest_framework_simplejwt.token_blacklist','drf_spectacular','api']
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.AuditLogMiddleware',
]
ROOT_URLCONF='medcore.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='medcore.wsgi.application'
DB_ENGINE=os.getenv('DB_ENGINE','sqlite')
if DB_ENGINE=='postgres':
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('DB_NAME','medcore_hms'),'USER':os.getenv('DB_USER','medcore'),'PASSWORD':os.getenv('DB_PASSWORD',''),'HOST':os.getenv('DB_HOST','localhost'),'PORT':os.getenv('DB_PORT','5432')}}
elif DB_ENGINE=='mysql':
    DATABASES={'default':{'ENGINE':'django.db.backends.mysql','NAME':os.getenv('DB_NAME','medcore_hms'),'USER':os.getenv('DB_USER','root'),'PASSWORD':os.getenv('DB_PASSWORD',''),'HOST':os.getenv('DB_HOST','localhost'),'PORT':os.getenv('DB_PORT','3306')}}
else:
    # SQLITE_PATH lets end-to-end tests use a throwaway database.
    DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':os.getenv('SQLITE_PATH') or BASE_DIR/'db.sqlite3'}}
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':8}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}]
LANGUAGE_CODE='en-us'; TIME_ZONE='Asia/Kolkata'; USE_I18N=True; USE_TZ=True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
FRONTEND_URL=os.getenv('FRONTEND_URL','http://localhost:5173')
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
AUTH_USER_MODEL='api.User'
# Strict allow-list. Add LAN or deployed frontend origins as a comma-separated list.
CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOW_CREDENTIALS=True  # needed for the httpOnly refresh cookie
CORS_ALLOWED_ORIGINS=[o.strip().rstrip('/') for o in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(',') if o.strip()]
# bcrypt (cost 12) for new and re-saved passwords; older PBKDF2 hashes still verify and upgrade on next login.
PASSWORD_HASHERS=['django.contrib.auth.hashers.BCryptSHA256PasswordHasher','django.contrib.auth.hashers.PBKDF2PasswordHasher','django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher','django.contrib.auth.hashers.Argon2PasswordHasher','django.contrib.auth.hashers.ScryptPasswordHasher']
REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES':('rest_framework_simplejwt.authentication.JWTAuthentication',),'DEFAULT_PERMISSION_CLASSES':('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_SCHEMA_CLASS':'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES':('rest_framework.throttling.AnonRateThrottle','rest_framework.throttling.UserRateThrottle'),
    'DEFAULT_THROTTLE_RATES':{'anon':'1000/min','user':'1000/min'}}
SPECTACULAR_SETTINGS={'TITLE':'MedCore HMS API','DESCRIPTION':'Role-based hospital management API. Authenticate with POST /api/login/ and send the access token as a Bearer header.','VERSION':'1.0.0','SERVE_INCLUDE_SCHEMA':False,'SERVE_PERMISSIONS':['rest_framework.permissions.AllowAny'],'SERVE_AUTHENTICATION':[]}
SIMPLE_JWT={'ACCESS_TOKEN_LIFETIME':timedelta(minutes=15),'REFRESH_TOKEN_LIFETIME':timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':True,'BLACKLIST_AFTER_ROTATION':True,'UPDATE_LAST_LOGIN':True}
SIMPLE_JWT['CHECK_REVOKE_TOKEN']=True
REDIS_URL=os.getenv('REDIS_URL','')
if REDIS_URL:
    CACHES={'default':{'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':REDIS_URL}}
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_REFERRER_POLICY='same-origin'
X_FRAME_OPTIONS='DENY'
TRUST_PROXY_HEADERS=os.getenv('TRUST_PROXY_HEADERS','False').lower()=='true'
# Comma-separated Fernet keys; the first encrypts, all decrypt (rotation). Generate with:
# python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY=os.getenv('FIELD_ENCRYPTION_KEY','')
# Optional ClamAV daemon for upload scanning, e.g. CLAMAV_HOST=clamav CLAMAV_PORT=3310.
CLAMAV_HOST=os.getenv('CLAMAV_HOST','')
CLAMAV_PORT=int(os.getenv('CLAMAV_PORT','3310'))
# Refresh tokens are sent as an httpOnly cookie scoped to the auth endpoints.
REFRESH_COOKIE_SECURE=os.getenv('REFRESH_COOKIE_SECURE','False').lower()=='true'
STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY','')
STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET','')
SENTRY_DSN=os.getenv('SENTRY_DSN','')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN,send_default_pii=False,traces_sample_rate=0.1)
PASSWORD_RESET_TIMEOUT=3600
# Local delivery writes emails to an ignored directory; configure SMTP for live email.
EMAIL_BACKEND=os.getenv('EMAIL_BACKEND','django.core.mail.backends.filebased.EmailBackend')
EMAIL_FILE_PATH=BASE_DIR/'private-outbox'
EMAIL_HOST=os.getenv('EMAIL_HOST','')
EMAIL_PORT=int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS=os.getenv('EMAIL_USE_TLS','True').lower()=='true'
EMAIL_TIMEOUT=10
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','MedCore <noreply@localhost>')
PAYMENTS_ENABLED=os.getenv('PAYMENTS_ENABLED','False').lower()=='true'
PAYMENT_MODE=os.getenv('PAYMENT_MODE','test')
RAZORPAY_KEY_ID=os.getenv('RAZORPAY_KEY_ID','')
RAZORPAY_KEY_SECRET=os.getenv('RAZORPAY_KEY_SECRET','')
RAZORPAY_WEBHOOK_SECRET=os.getenv('RAZORPAY_WEBHOOK_SECRET','')
SMS_ENABLED=os.getenv('SMS_ENABLED','False').lower()=='true'
TWILIO_ACCOUNT_SID=os.getenv('TWILIO_ACCOUNT_SID','')
TWILIO_AUTH_TOKEN=os.getenv('TWILIO_AUTH_TOKEN','')
TWILIO_FROM_NUMBER=os.getenv('TWILIO_FROM_NUMBER','')
# File-backed heartbeat is shared by the scheduler and web process.
REMINDER_HEARTBEAT_PATH=BASE_DIR/'private-outbox'/'reminder-heartbeat.json'
