from django.apps import AppConfig


class ContributiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contributi"
    verbose_name = "Contributi"

    def ready(self):
        from auditlog.registry import auditlog
        from django.db.models.signals import post_save

        from apps.anagrafica.models import TrasferimentoCapo
        from apps.organizzazione.models import StatoGruppoAnno

        from .disattivazione_gruppo import su_disattivazione_gruppo
        from .models import (
            AllegatoPartecipazione,
            Campagna,
            ContributoPartecipazione,
            Partecipazione,
        )
        from .trasferimenti import su_trasferimento_capo

        auditlog.register(Campagna)
        auditlog.register(Partecipazione)
        auditlog.register(ContributoPartecipazione)
        auditlog.register(AllegatoPartecipazione)
        post_save.connect(
            su_trasferimento_capo,
            sender=TrasferimentoCapo,
            dispatch_uid="contributi_riattribuzione_trasferimento",
        )
        post_save.connect(
            su_disattivazione_gruppo,
            sender=StatoGruppoAnno,
            dispatch_uid="contributi_respingi_disattivazione_gruppo",
        )
