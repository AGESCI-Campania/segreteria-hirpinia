from django.apps import AppConfig


class AnagraficaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.anagrafica"
    verbose_name = "Anagrafica"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import IncaricoUnita

        auditlog.register(IncaricoUnita)
