# Copy these settings into your local shell and replace placeholders.
# Keep credentials out of source control. Settings are read from the environment.
$env:EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
$env:EMAIL_HOST = 'smtp.your-provider.example'
$env:EMAIL_PORT = '587'
$env:EMAIL_USE_TLS = 'True'
$env:EMAIL_HOST_USER = 'your-smtp-user'
$env:EMAIL_HOST_PASSWORD = 'your-smtp-password'
$env:DEFAULT_FROM_EMAIL = 'MedCore <verified-sender@your-domain.example>'
$env:FRONTEND_URL = 'http://localhost:5173'
# Restart the Django process after setting these variables.
