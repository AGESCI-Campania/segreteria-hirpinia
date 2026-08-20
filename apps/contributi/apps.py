from django.apps import AppConfig


class ContributiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contributi"
    verbose_name = "Contributi"

    def ready(self):
        from auditlog.registry import auditlog
        from django.db.models.signals import post_save

        from apps.anagrafica.models import TrasferimentoCapo

        from .models import Campagna, Partecipazione
        from .trasferimenti import su_trasferimento_capo

        auditlog.register(Campagna)
        auditlog.register(Partecipazione)
        post_save.connect(
            su_trasferimento_capo,
            sender=TrasferimentoCapo,
            dispatch_uid="contributi_riattribuzione_trasferimento",
        )
