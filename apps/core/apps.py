from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import ImpostazioniPiattaforma, TemplateEmail

        auditlog.register(ImpostazioniPiattaforma)
        auditlog.register(TemplateEmail)
