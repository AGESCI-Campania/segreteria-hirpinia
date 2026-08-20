from django.apps import AppConfig


class OrganizzazioneConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizzazione"
    verbose_name = "Organizzazione"

    def ready(self):
        from auditlog.registry import auditlog

        from .models import Gruppo

        # CLAUDE.md: ogni modifica a IBAN/intestazione_conto tracciata da
        # django-auditlog. Gap pre-esistente (nessun ready() in questa app),
        # colmato in M5 perché è il primo punto in cui l'IBAN inizia a
        # contare davvero (gate di chiusura campagna, D-14).
        auditlog.register(Gruppo)
