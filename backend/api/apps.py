from django.apps import AppConfig
class ApiConfig(AppConfig):
    default_auto_field='django.db.models.BigAutoField'
    name='api'
    def ready(self):
        # Role checks run on anonymous users during OpenAPI generation; give them no role.
        from django.contrib.auth.models import AnonymousUser
        AnonymousUser.role=None
        AnonymousUser.hospital_id=None
