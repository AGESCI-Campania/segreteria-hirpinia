from django.apps import AppConfig


class NoteSpeseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.note_spese"
    verbose_name = "Note spese"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import CentroCosto, Evento, NotaSpese, RigaSpesa

        auditlog.register(CentroCosto)
        auditlog.register(Evento)
        auditlog.register(NotaSpese)
        auditlog.register(RigaSpesa)
