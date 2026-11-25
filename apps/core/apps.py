from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        from auditlog.registry import auditlog
        from django.db.models import fields

        # Voce vuota dei menu a tendina: Django 6.1 non ne ha la traduzione
        # italiana; ridefinirla in ready() è il modo previsto da Django.
        fields.BLANK_CHOICE_LABEL = "- Seleziona -"

        from .models import ImpostazioniPiattaforma, TemplateEmail

        auditlog.register(ImpostazioniPiattaforma)
        auditlog.register(TemplateEmail)
