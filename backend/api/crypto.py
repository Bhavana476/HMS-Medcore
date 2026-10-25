"""Column-level encryption at rest for sensitive clinical text (Fernet: AES-128-CBC + HMAC-SHA256).

Values are stored as 'enc1:<token>'. Rows written before encryption was enabled are
read as plain text and encrypted the next time they are saved (and by migration 0014).
Losing FIELD_ENCRYPTION_KEY makes these columns unreadable: back it up with your secrets."""
import base64
import hashlib
from functools import lru_cache
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models

PREFIX='enc1:'

@lru_cache(maxsize=1)
def _fernet():
    keys=[k.strip() for k in (settings.FIELD_ENCRYPTION_KEY or '').split(',') if k.strip()]
    if not keys:
        # Development fallback only; production.py refuses to start without an explicit key.
        keys=[base64.urlsafe_b64encode(hashlib.sha256(f'medcore-field:{settings.SECRET_KEY}'.encode()).digest()).decode()]
    # First key encrypts; all keys decrypt, which allows key rotation.
    return MultiFernet([Fernet(k) for k in keys])

def encrypt(value):
    if value in (None,'') or str(value).startswith(PREFIX): return value
    return PREFIX+_fernet().encrypt(str(value).encode()).decode()

def decrypt(value):
    if not isinstance(value,str) or not value.startswith(PREFIX): return value
    try: return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        raise ValueError('Encrypted clinical data could not be decrypted. Check FIELD_ENCRYPTION_KEY.') from None

class EncryptedTextField(models.TextField):
    """TextField encrypted at rest. Not searchable or orderable in the database."""
    def from_db_value(self,value,expression,connection): return decrypt(value)
    def to_python(self,value): return decrypt(value)
    def get_prep_value(self,value): return encrypt(super().get_prep_value(value))
